"""The Home Assistant runtime of one Plant (contract K5).

Every evaluation snapshots the entities the Plant reads, calls ``step()`` on the
view that ``step_view`` shows it, calls ``reconcile()``, persists both States,
sends the actions, raises the Repairs, publishes the entities, and schedules the
next evaluation at the earlier of ``step()``'s due time and the reconciler's
next retry. Evaluations are coalesced: any number of state changes in one pass
of the event loop cause one evaluation.

The evaluation itself never awaits, so it needs no lock. Actions are sent
afterwards by one chain of tasks, in the order the reconciler gave them, each
limited to ``CALL_TIMEOUT`` after the evaluation that decided it, so calls to
one entity act in the order they were decided and none acts later than
``step()`` assumes. A returned call is not a confirmation; the next observation
is.

Setup loads the persisted State and the digital thermostats restore their
entities before the first evaluation, which waits until Home Assistant has
started. Stopping, as on unload and reload, only cancels timers, listeners, and
unsent actions, and saves; it never sends a command.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.core import (
    State as HassState,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .areas import (
    AreaResolution,
    async_track_area_changes,
    covered_area_ids,
    resolve_area_sensors,
    zone_area_problems,
)
from .const import DOMAIN, STORE_SAVE_DELAY, STORE_VERSION
from .core.demand import aggregate, dew_point, zone_values
from .core.model import (
    Desired,
    DigitalThermostat,
    ExternalThermostat,
    Loop,
    Mode,
    OptionTarget,
    OutputRole,
    OutputTarget,
    Plant,
    SwitchTarget,
    ValueTarget,
    Zone,
)
from .core.plant_file import entity_paths
from .core.reconcile import Action, Reconciled, ReconcileState, reconcile, step_view
from .core.step import (
    CALL_TIMEOUT,
    DigitalThermostatState,
    Observations,
    OptionState,
    OutputState,
    Reading,
    State,
    SwitchState,
    ThermostatState,
    step,
)
from .entity import zone_unique_id
from .issues import (
    Issue,
    async_sync_issues,
    missing_area_sensor,
    missing_binding,
    output_not_responding,
    outputs_awaiting_confirmation,
    zone_area_issue,
)
from .observe import (
    OutputMemory,
    SensorKind,
    external_thermostat,
    option_value,
    reading,
    switch_value,
)
from .storage import armed_outputs, control

_LOGGER = logging.getLogger(__name__)

# How many Dry run proposals diagnostics keep.
_PROPOSALS_KEPT: Final = 50


@dataclass(frozen=True, slots=True)
class Proposal:
    """An action that Dry run recorded instead of sending."""

    at: float
    entity: str
    target: OutputTarget


@dataclass(frozen=True, slots=True)
class ZoneReadings:
    """What a zone's sensors show now, for its entities."""

    temperature: float | None = None
    humidity: float | None = None
    dew_point: float | None = None
    # Each covered area with the sensors it names and their readings.
    areas: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    # Each explicit temperature sensor with its reading.
    sensors: Mapping[str, float | None] = field(default_factory=dict)


def service_call(action: Action) -> tuple[str, str, dict[str, Any]]:
    """Return the domain, service, and data of the call that drives an output to a target."""
    entity = action.entity
    domain = entity.partition(".")[0]
    data: dict[str, Any] = {"entity_id": entity}
    match action.target:
        case SwitchTarget(on=on):
            if domain == "valve":
                return domain, "open_valve" if on else "close_valve", data
            if domain in ("switch", "input_boolean"):
                return domain, "turn_on" if on else "turn_off", data
            return "homeassistant", "turn_on" if on else "turn_off", data
        case OptionTarget(option=option):
            return domain, "select_option", {**data, "option": option}
        case ValueTarget(value=value):
            return domain, "set_value", {**data, "value": value}


class PlantRuntime:
    """Runs one Plant: observe, step, reconcile, send, persist, and publish."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, plant: Plant) -> None:
        self.hass = hass
        self.entry = entry
        self.plant = plant
        self.store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, store_key(entry.entry_id))
        self.state = State()
        self.reconcile_state = ReconcileState()
        self.requested_mode = Mode.OFF
        self.memory = OutputMemory()
        self.thermostats: dict[str, DigitalThermostatState] = {}
        self.areas = AreaResolution()
        # The last evaluation: what was observed, what step() saw, and what it decided.
        self.observations: Observations | None = None
        self.view: Observations | None = None
        self.desired: Desired | None = None
        self.reconciled: Reconciled | None = None
        self.evaluated_at: float | None = None
        self.zone_readings: dict[str, ZoneReadings] = {}
        self.missing: dict[str, str] = {}
        self.proposals: deque[Proposal] = deque(maxlen=_PROPOSALS_KEPT)
        self.issues: tuple[Issue, ...] = ()
        # The first evaluation always syncs, which clears Repairs of an earlier setup,
        # such as an invalid Plant that a reconfigure has fixed.
        self._issues_synced = False
        # The unique IDs each platform provided in this setup, by entity domain.
        self.provided: dict[str, frozenset[str]] = {}
        # The configuration this runtime was built from; a change reloads the Plant.
        self.fingerprint: str = ""
        # Whether a changed configuration has already asked for a reload.
        self.reloading = False
        # The device registry ID of the Plant device, which zone and source devices are under.
        self.plant_device_id = ""
        self._outputs = plant.outputs()
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsubscribe: list[CALLBACK_TYPE] = []
        self._state_listener: CALLBACK_TYPE | None = None
        self._area_listener: CALLBACK_TYPE | None = None
        self._tracked: frozenset[str] = frozenset()
        self._timer: CALLBACK_TYPE | None = None
        self._dispatch: asyncio.Task[None] | None = None
        self._saved: dict[str, Any] | None = None
        self._queued = False
        self._set_up = False
        self._hass_started = False
        self._began = False
        self._stopped = False
        self._awaiting_restore = {
            zone.slug for zone in plant.zones if isinstance(zone.thermostat, DigitalThermostat)
        }

    # Lifecycle

    async def async_load(self) -> None:
        """Restore the persisted State, reconciler State, output memory, and Plant mode."""
        data = await self.store.async_load()
        if not data:
            return
        try:
            self.state = State.from_dict(data.get("state", {}))
            self.reconcile_state = ReconcileState.from_dict(data.get("reconcile", {}))
            self.memory = OutputMemory.from_dict(data.get("outputs", {}))
            self.requested_mode = Mode(data.get("mode", Mode.OFF))
        except (KeyError, TypeError, ValueError) as error:
            _LOGGER.warning(
                "The persisted state of Plant %s could not be read and starts over: %s",
                self.entry.title,
                error,
            )
            self.state, self.reconcile_state = State(), ReconcileState()
            self.memory, self.requested_mode = OutputMemory(), Mode.OFF
        self.memory.forget_except(set(self._outputs))
        self._saved = self._data()

    @callback
    def async_start(self) -> None:
        """Begin once Home Assistant has started and every digital thermostat has restored.

        A zone whose climate entity is disabled never restores and counts as
        restored; its thermostat reads as not restored, so the zone never calls.
        """
        self._set_up = True
        if "climate" not in self.provided and self._awaiting_restore:
            _LOGGER.warning(
                "The thermostats of Plant %s did not load; its zones with a digital "
                "thermostat do not call until they do",
                self.plant.name,
            )
            self._awaiting_restore.clear()
        registry = er.async_get(self.hass)
        for slug in tuple(self._awaiting_restore):
            entity_id = registry.async_get_entity_id(
                "climate", DOMAIN, zone_unique_id(self.plant.id, slug, "climate")
            )
            entry = registry.async_get(entity_id) if entity_id is not None else None
            if entry is not None and entry.disabled_by is not None:
                self._awaiting_restore.discard(slug)
        self._unsubscribe.append(async_at_started(self.hass, self._async_on_started))
        self._maybe_begin()

    async def _async_on_started(self, _hass: HomeAssistant) -> None:
        self._hass_started = True
        self._maybe_begin()

    @callback
    def _maybe_begin(self) -> None:
        if self._began or self._stopped:
            return
        if not (self._set_up and self._hass_started) or self._awaiting_restore:
            return
        self._began = True
        self.request_evaluation()

    async def async_stop(self) -> None:
        """Stop without sending a command, and save the persisted state now."""
        self._stopped = True
        if self._timer is not None:
            self._timer()
            self._timer = None
        for unsubscribe in (self._state_listener, self._area_listener, *self._unsubscribe):
            if unsubscribe is not None:
                unsubscribe()
        self._state_listener = self._area_listener = None
        self._unsubscribe.clear()
        if self._dispatch is not None and not self._dispatch.done():
            self._dispatch.cancel()
            await asyncio.wait([self._dispatch])
        await self.store.async_save(self._data())

    # Inputs from the Plant's own entities

    @callback
    def restore_thermostat(self, zone: str, thermostat: DigitalThermostatState) -> None:
        """Take a digital thermostat's restored state before the first evaluation."""
        self.thermostats[zone] = thermostat
        self._awaiting_restore.discard(zone)
        self._maybe_begin()

    @callback
    def set_thermostat(self, zone: str, thermostat: DigitalThermostatState) -> None:
        """Take a change of a digital thermostat and evaluate."""
        self.thermostats[zone] = thermostat
        self.request_evaluation()

    @callback
    def set_mode(self, mode: Mode) -> None:
        """Take the Plant mode the mode select requests."""
        self.requested_mode = mode
        self._save()
        self._publish()
        self.request_evaluation()

    @callback
    def set_control(self, on: bool) -> None:
        """Turn Control equipment on or off; it is stored in the entry options."""
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, "control": on}
        )
        self._publish()
        self.request_evaluation()

    @property
    def control(self) -> bool:
        return control(self.entry)

    @property
    def armed(self) -> frozenset[str]:
        return armed_outputs(self.entry) & set(self._outputs)

    # Entities

    @callback
    def async_add_listener(self, listener: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Call ``listener`` after every evaluation; return the function that removes it."""
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    @callback
    def _publish(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    # Evaluation

    @callback
    def request_evaluation(self) -> None:
        """Evaluate soon; requests until then share one evaluation."""
        if not self._began or self._stopped or self._queued:
            return
        self._queued = True
        self.hass.async_create_task(
            self._async_evaluate(),
            f"Evaluate Hydronicus Plant {self.plant.name}",
            eager_start=False,
        )

    async def _async_evaluate(self) -> None:
        self._queued = False
        if not self._stopped:
            self.evaluate()

    @callback
    def evaluate(self) -> None:
        """Run one evaluation now."""
        now = dt_util.utcnow().timestamp()
        self._resolve_areas()
        observations = self._observe(now)
        view = step_view(observations, self.reconcile_state)
        state, desired, due = step(self.plant, view, self.state, now)
        result = reconcile(
            self.plant,
            desired,
            observations.outputs,
            self.reconcile_state,
            now,
            armed=observations.armed,
            live=state.live,
        )
        self.state, self.reconcile_state = state, result.state
        self.observations, self.view, self.desired, self.reconciled = (
            observations,
            view,
            desired,
            result,
        )
        self.evaluated_at = now
        self.proposals.extend(Proposal(now, a.entity, a.target) for a in result.proposed)
        self.zone_readings = {
            zone.slug: _zone_readings(zone, observations, self.areas, now)
            for zone in self.plant.zones
        }
        self._save()
        if result.send:
            self._send(result.send, now)
        self._schedule(now, due, result.retry_at)
        self._sync_issues(result)
        self._publish()
        if result.proposed:
            # A Dry run proposal counts as observed, so it is a change that evaluates
            # again, as the observed result of a live call would be.
            self.request_evaluation()

    def _observe(self, now: float) -> Observations:
        states = self.hass.states
        outputs: dict[str, OutputState] = {}
        for entity, role in self._outputs.items():
            state = states.get(entity)
            changed = now if state is None else state.last_changed_timestamp
            if role is OutputRole.SOURCE_MODE:
                option = option_value(state)
                outputs[entity] = OptionState(option, self.memory.since(entity, option, changed))
            else:
                on = switch_value(state)
                outputs[entity] = SwitchState(on, self.memory.since(entity, on, changed))
        readiness: dict[str, SwitchState] = {}
        for loop in self.plant.all_loops:
            for valve in loop.valves:
                if valve.readiness is not None:
                    state = states.get(valve.readiness)
                    readiness[valve.readiness] = SwitchState(
                        switch_value(state), now if state is None else state.last_changed_timestamp
                    )
        sensors = {
            entity: reading(states.get(entity), kind, now)
            for entity, kind in self._sensor_kinds().items()
        }
        thermostats: dict[str, ThermostatState] = {}
        for zone in self.plant.zones:
            if isinstance(zone.thermostat, ExternalThermostat):
                thermostats[zone.slug] = external_thermostat(states.get(zone.thermostat.entity))
            elif (digital := self.thermostats.get(zone.slug)) is not None:
                thermostats[zone.slug] = digital
        return Observations(
            mode=self.requested_mode,
            control=self.control,
            armed=self.armed,
            outputs=outputs,
            readiness=readiness,
            sensors=sensors,
            areas=dict(self.areas.area_sensors),
            thermostats=thermostats,
        )

    def _sensor_kinds(self) -> dict[str, SensorKind]:
        """Every numeric sensor the Plant reads now, with what it measures."""
        kinds: dict[str, SensorKind] = {}
        for pump in self.plant.pumps:
            if pump.supply_temperature is not None:
                kinds[pump.supply_temperature] = SensorKind.WATER
        for loop in self.plant.all_loops:
            if loop.surface_temperature is not None:
                kinds[loop.surface_temperature] = SensorKind.AIR
        for zone in self.plant.zones:
            for sensor in zone.temperature:
                kinds[sensor.entity] = SensorKind.AIR
            for sensor in zone.humidity:
                kinds[sensor.entity] = SensorKind.HUMIDITY
            for area in zone.areas:
                names = self.areas.area_sensors.get(area.area)
                if names is None:
                    continue
                if names.temperature is not None:
                    kinds[names.temperature] = SensorKind.AIR
                if names.humidity is not None:
                    kinds[names.humidity] = SensorKind.HUMIDITY
        return kinds

    # Areas and the state listener

    @callback
    def _resolve_areas(self) -> None:
        """Re-read the covered areas and follow what they name now, without a reload."""
        areas = resolve_area_sensors(self.hass, covered_area_ids(self.plant))
        if areas != self.areas or self._area_listener is None:
            self.areas = areas
            if self._area_listener is not None:
                self._area_listener()
            self._area_listener = async_track_area_changes(
                self.hass, covered_area_ids(self.plant), areas, self.request_evaluation
            )
        tracked = self._tracked_entities()
        if tracked != self._tracked or self._state_listener is None:
            self._tracked = tracked
            if self._state_listener is not None:
                self._state_listener()
            self._state_listener = async_track_state_change_event(
                self.hass, sorted(tracked), self._on_state_change
            )

    def _tracked_entities(self) -> frozenset[str]:
        tracked = set(self._outputs) | set(self._sensor_kinds())
        for loop in self.plant.all_loops:
            tracked.update(valve.readiness for valve in loop.valves if valve.readiness)
        for zone in self.plant.zones:
            if isinstance(zone.thermostat, ExternalThermostat):
                tracked.add(zone.thermostat.entity)
        return frozenset(tracked)

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        entity = event.data["entity_id"]
        role = self._outputs.get(entity)
        new_state: HassState | None = event.data["new_state"]
        if role is not None and new_state is not None:
            # Every change of an output is remembered, so no change goes unseen
            # between two evaluations.
            value: bool | str | None = (
                option_value(new_state)
                if role is OutputRole.SOURCE_MODE
                else switch_value(new_state)
            )
            self.memory.since(entity, value, new_state.last_changed_timestamp)
        self.request_evaluation()

    # Sending

    @callback
    def _send(self, actions: Iterable[Action], sent_at: float) -> None:
        previous = self._dispatch
        self._dispatch = self.hass.async_create_task(
            self._async_send(tuple(actions), sent_at, previous),
            f"Send Hydronicus Plant {self.plant.name} actions",
            eager_start=False,
        )

    async def _async_send(
        self, actions: tuple[Action, ...], sent_at: float, previous: asyncio.Task[None] | None
    ) -> None:
        if previous is not None and not previous.done():
            await asyncio.wait([previous])
        for action in actions:
            remaining = sent_at + CALL_TIMEOUT - dt_util.utcnow().timestamp()
            if remaining <= 0:
                _LOGGER.warning(
                    "Plant %s did not send %s to %s in time; it retries",
                    self.plant.name,
                    action.target,
                    action.entity,
                )
                continue
            domain, service, data = service_call(action)
            try:
                async with asyncio.timeout(remaining):
                    await self.hass.services.async_call(domain, service, data, blocking=True)
            except TimeoutError:
                _LOGGER.warning(
                    "Plant %s: %s.%s for %s did not return in time",
                    self.plant.name,
                    domain,
                    service,
                    action.entity,
                )
            except Exception as error:  # Any failure is retried and surfaced as a Repair.
                _LOGGER.warning(
                    "Plant %s: %s.%s for %s failed: %s",
                    self.plant.name,
                    domain,
                    service,
                    action.entity,
                    error,
                )

    # Scheduling and persistence

    @callback
    def _schedule(self, now: float, due: float | None, retry_at: float | None) -> None:
        if self._timer is not None:
            self._timer()
            self._timer = None
        times = [
            time for time in (None if due is None else now + due, retry_at) if time is not None
        ]
        if times:
            self._timer = async_track_point_in_utc_time(
                self.hass, self._on_timer, dt_util.utc_from_timestamp(min(times))
            )

    @callback
    def _on_timer(self, _now: datetime) -> None:
        self._timer = None
        self.request_evaluation()

    def _data(self) -> dict[str, Any]:
        return {
            "state": self.state.to_dict(),
            "reconcile": self.reconcile_state.to_dict(),
            "outputs": self.memory.to_dict(),
            "mode": self.requested_mode.value,
        }

    @callback
    def _save(self) -> None:
        data = self._data()
        if data != self._saved:
            self._saved = data
            self.store.async_delay_save(lambda: data, STORE_SAVE_DELAY)

    # Repairs

    @callback
    def _sync_issues(self, result: Reconciled) -> None:
        plant, states = self.plant, self.hass.states
        issues: list[Issue] = [output_not_responding(plant, entity) for entity in result.repairs]
        armed = self.armed
        # A new Plant arms its outputs at setup; later additions wait for confirmation.
        if armed and (unarmed := set(self._outputs) - armed):
            issues.append(outputs_awaiting_confirmation(plant, unarmed))
        self.missing = {
            entity: path
            for entity, path in entity_paths(plant).items()
            if states.get(entity) is None
        }
        issues.extend(missing_binding(plant, entity, path) for entity, path in self.missing.items())
        for area_id, names in self.areas.area_sensors.items():
            for entity in (names.temperature, names.humidity):
                if entity is not None and states.get(entity) is None:
                    self.missing[entity] = f"area {area_id}"
                    issues.append(missing_area_sensor(plant, self.areas.name(area_id), entity))
        issues.extend(
            zone_area_issue(plant, problem, self.areas)
            for problem in zone_area_problems(plant, self.areas)
        )
        current = tuple(issues)
        if current != self.issues or not self._issues_synced:
            self.issues, self._issues_synced = current, True
            async_sync_issues(self.hass, self.entry.entry_id, current)

    # What the entities show

    def running_mode(self) -> Mode:
        return Mode.OFF if self.desired is None else self.desired.mode

    def loop_flowing(self, loop: Loop) -> bool:
        """Whether a loop passes flow in the view ``step()`` saw, including Dry run proposals."""
        view = self.view
        if view is None:
            return False
        if not all(_on(view.outputs.get(valve.entity)) for valve in loop.valves):
            return False
        pump = self.plant.pump(loop.pump)
        if pump.switch is not None:
            return _on(view.outputs.get(pump.switch))
        source = self.plant.source
        return source is not None and _on(view.outputs.get(source.request))

    def status(self) -> str | None:
        """Off, idle, heating, cooling, changing over, or degraded."""
        desired, result = self.desired, self.reconciled
        if desired is None or result is None:
            return None
        if result.repairs or self.missing:
            return "degraded"
        if "mode" in desired.reasons:
            return "changing_over"
        if desired.mode is Mode.OFF:
            return "off" if self.requested_mode is Mode.OFF else "idle"
        # Anything asked to run, from a valve opening to a pump's overrun, is work in the mode.
        if any(target == SwitchTarget(True) for target in desired.outputs.values()) or any(
            self.loop_flowing(loop) for loop in self.plant.all_loops
        ):
            return "heating" if desired.mode is Mode.HEAT else "cooling"
        return "idle"

    def blocked_zones(self) -> dict[str, str]:
        """Each zone that cannot get what its thermostat asks for, with the reason."""
        desired = self.desired
        if desired is None:
            return {}
        blocked: dict[str, str] = {}
        for zone in self.plant.zones:
            demand = desired.demands.get(zone.slug)
            if demand is None:
                continue
            if demand.on and demand.mode is not desired.mode and desired.mode is not Mode.OFF:
                blocked[zone.slug] = (
                    f"thermostat asks to {demand.mode.value} while the Plant runs "
                    f"{desired.mode.value}"
                )
                continue
            dropped = [
                reason
                for loop in zone.loops
                if (reason := desired.reasons.get(str(loop.ref), "")).startswith("dropped")
            ]
            if demand.on and dropped:
                blocked[zone.slug] = dropped[0]
            elif not demand.on and demand.reason in _BLOCKING_REASONS:
                blocked[zone.slug] = demand.reason
        return blocked


_BLOCKING_REASONS: Final = frozenset(
    {"thermostat unavailable", "thermostat not restored", "no usable temperature"}
)


def _on(state: OutputState | None) -> bool:
    return isinstance(state, SwitchState) and state.on is True


def _zone_readings(
    zone: Zone, observations: Observations, areas: AreaResolution, now: float
) -> ZoneReadings:
    """The combined temperature, the highest humidity, and the worst-case dew point of a zone."""

    def reached(deadline: float) -> bool:
        return now >= deadline

    sensors, names = observations.sensors, observations.areas
    temperatures = zone_values(zone, names, sensors, reached)
    humidities = zone_values(zone, names, sensors, reached, humidity=True)
    temperature = None if temperatures is None else aggregate(temperatures, zone.aggregation)
    humidity = None if humidities is None else max(humidities)
    worst = (
        None
        if temperatures is None or humidities is None
        else dew_point(max(temperatures), max(humidities))
    )
    breakdown: dict[str, dict[str, Any]] = {}
    for area in zone.areas:
        named = names.get(area.area)
        entry: dict[str, Any] = {"name": areas.name(area.area)}
        for key, entity in (
            ("temperature", None if named is None else named.temperature),
            ("humidity", None if named is None else named.humidity),
        ):
            entry[f"{key}_sensor"] = entity
            entry[key] = None if entity is None else _value(sensors.get(entity))
        breakdown[area.area] = entry
    return ZoneReadings(
        temperature=temperature,
        humidity=humidity,
        dew_point=worst,
        areas=breakdown,
        sensors={sensor.entity: _value(sensors.get(sensor.entity)) for sensor in zone.temperature},
    )


def _value(reading_: Reading | None) -> float | None:
    return None if reading_ is None else reading_.value


def store_key(entry_id: str) -> str:
    """Return the Store key of a Plant's persisted state."""
    return f"{DOMAIN}.{entry_id}"
