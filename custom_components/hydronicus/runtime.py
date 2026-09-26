"""The Home Assistant runtime of one Plant (contract K5).

Every evaluation snapshots the entities the Plant reads, calls ``step()`` on the
view that ``step_view`` shows it, calls ``reconcile()``, persists both States,
sends the actions, raises the Repairs, publishes the entities, and schedules the
next evaluation at the earlier of ``step()``'s due time and the reconciler's
next retry. Evaluations are coalesced: any number of state changes in one pass
of the event loop cause one evaluation.

The evaluation itself never awaits, so it needs no lock. Actions are sent
afterwards by the Plant's ``Dispatcher``, in the order the reconciler gave
them, each limited to ``CALL_TIMEOUT`` after the evaluation that decided it.
Each evaluation ends with a ``PlantView``, which the entities publish.

Setup loads the persisted State and the digital thermostats restore their
entities before the first evaluation, which waits until Home Assistant has
started. Stopping, as on unload and reload, only cancels timers, listeners, and
the dispatcher, and saves; it never sends a command.

The persisted state also holds the last valid Plant with the outputs it was
commanding, which ``PreviousConfiguration`` stops before a new configuration
runs when that removes an output that is on or is not valid.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, replace
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
from .const import DOMAIN, OPTION_CONTROL, STORE_SAVE_DELAY, STORE_VERSION
from .core.model import (
    DigitalThermostat,
    ExternalThermostat,
    Mode,
    OutputRole,
    OutputTarget,
    Plant,
)
from .core.plant_file import entity_paths, export_plant
from .core.reconcile import Reconciled, ReconcileState, reconcile, step_view
from .core.step import (
    DigitalThermostatState,
    Observations,
    OptionState,
    OutputState,
    State,
    SwitchState,
    ThermostatState,
    step,
)
from .dispatch import Dispatcher
from .entity import zone_unique_id
from .issues import (
    BlockingSensors,
    Issue,
    IssueKind,
    async_sync_issues,
    evaluation_failed,
    invalid_plant,
    missing_area_sensor,
    missing_binding,
    output_not_responding,
    outputs_awaiting_confirmation,
    zone_area_issue,
    zone_sensor_unusable,
)
from .observe import (
    OutputMemory,
    SensorKind,
    external_thermostat,
    option_value,
    reading,
    switch_value,
)
from .previous import PreviousConfiguration
from .storage import armed_outputs, control
from .view import PlantView, zone_readings

_LOGGER = logging.getLogger(__name__)

# How many Dry run proposals diagnostics keep.
_PROPOSALS_KEPT: Final = 50
# How long after a failed evaluation the Plant evaluates again, in seconds.
EVALUATION_RETRY: Final = 60.0


@dataclass(frozen=True, slots=True)
class Proposal:
    """An action that Dry run recorded instead of sending."""

    at: float
    entity: str
    target: OutputTarget


class PlantRuntime:
    """Runs one Plant: observe, step, reconcile, send, persist, and publish."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, plant: Plant, problem: str | None = None
    ) -> None:
        self.hass = hass
        self.entry = entry
        # The Plant the entities show. While the configuration is not valid, it is an
        # empty Plant with the stored ID and name, and ``problem`` says what is wrong.
        self.plant = plant
        self.problem = problem
        # The configured Plant's plant file, exported once.
        self.document = export_plant(plant)
        self.previous = PreviousConfiguration(
            entry.title, plant, self.document if problem is None else None
        )
        self.store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, store_key(entry.entry_id))
        self.state = State()
        self.reconcile_state = ReconcileState()
        self.requested_mode = Mode.OFF
        self.memory = OutputMemory()
        self.blocking = BlockingSensors()
        self.thermostats: dict[str, DigitalThermostatState] = {}
        self.areas = AreaResolution()
        # The last evaluation, as the entities read it; None until the first one.
        self.view: PlantView | None = None
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
        self._dispatcher = Dispatcher(hass, entry, plant.name)
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
            self.blocking = BlockingSensors.from_dict(data.get("blocking_sensors", {}))
            self.requested_mode = Mode(data.get("mode", Mode.OFF))
        except Exception as error:  # Whatever is wrong with it, the Plant starts over.
            _LOGGER.warning(
                "The persisted state of Plant %s could not be read and starts over: %s",
                self.entry.title,
                error,
            )
            self.state, self.reconcile_state = State(), ReconcileState()
            self.memory, self.requested_mode = OutputMemory(), Mode.OFF
            self.blocking = BlockingSensors()
        self.previous.load(data.get("commanding"))
        kept = set(self._outputs)
        if self.previous.persisted is not None:
            kept |= self.previous.persisted.outputs
        self.memory.forget_except(kept)
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
        await self._dispatcher.async_stop()
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
            self.entry, options={**self.entry.options, OPTION_CONTROL: on}
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
        if self._stopped:
            return
        try:
            self.evaluate()
        except Exception as error:  # A failed evaluation must not stop the Plant for good.
            _LOGGER.exception(
                "Plant %s could not evaluate and tries again in %s seconds",
                self.plant.name,
                int(EVALUATION_RETRY),
            )
            self._evaluation_failed(error)

    @callback
    def _evaluation_failed(self, error: Exception) -> None:
        """Raise the Repair next to the others, and evaluate again after ``EVALUATION_RETRY``.

        The outputs keep what they were last sent, and the next evaluation that
        succeeds clears the Repair.
        """
        self._schedule(dt_util.utcnow().timestamp() + EVALUATION_RETRY)
        failed = evaluation_failed(self.plant.name, f"{type(error).__name__}: {error}")
        current = (
            *(issue for issue in self.issues if issue.kind is not IssueKind.EVALUATION_FAILED),
            failed,
        )
        if current != self.issues:
            self.issues = current
            async_sync_issues(self.hass, self.entry.entry_id, current)

    @property
    def control_plant(self) -> Plant:
        """The Plant whose outputs the evaluations drive: the previous one while it stops."""
        stopping = self.previous.stopping
        return self.plant if stopping is None else stopping.plant

    @callback
    def evaluate(self) -> None:
        """Run one evaluation now."""
        now = dt_util.utcnow().timestamp()
        if not self.previous.decided and self.previous.decide(
            self.hass.states, self.reconcile_state.attempts, self._outputs, self.problem is None
        ):
            # The persisted Plant was live, so its off sequence commands.
            self.state = replace(self.state, live=True)
        plant = self.control_plant
        self._resolve_areas()
        observations = self._observe(now, plant)
        seen = step_view(observations, self.reconcile_state)
        state, desired, due = step(plant, seen, self.state, now)
        result = reconcile(
            plant,
            desired,
            observations.outputs,
            self.reconcile_state,
            now,
            armed=observations.armed,
            live=state.live,
        )
        self.state, self.reconcile_state = state, result.state
        self.blocking.update(desired.blocking_sensors, now)
        self.proposals.extend(Proposal(now, a.entity, a.target) for a in result.proposed)
        if self.previous.stopping is not None and not state.live:
            self.previous.stopped()
            self.request_evaluation()
        self._save()
        if result.send:
            self._dispatcher.send(result.send, now)
        self._schedule(
            None if due is None else now + due, result.retry_at, self.blocking.next_report(now)
        )
        missing = self._sync_issues(result, plant, now)
        self.view = PlantView(
            plant=self.plant,
            at=now,
            observations=observations,
            seen=seen,
            desired=desired,
            reconciled=result,
            zones={
                zone.slug: zone_readings(zone, observations, self.areas, now)
                for zone in self.plant.zones
            },
            missing=missing,
            problem=self.problem,
            stopping=self.previous.stopping,
        )
        self._publish()
        if result.proposed:
            # A Dry run proposal counts as observed, so it is a change that evaluates
            # again, as the observed result of a live call would be.
            self.request_evaluation()

    def _plants(self) -> tuple[Plant, ...]:
        """The Plants the runtime reads: the configured one and one that is stopping."""
        stopping = self.previous.stopping
        return (self.plant,) if stopping is None else (self.plant, stopping.plant)

    def _roles(self) -> dict[str, OutputRole]:
        """Every output of the Plants the runtime reads, with its role."""
        roles = dict(self._outputs)
        if (stopping := self.previous.stopping) is not None:
            roles.update(stopping.plant.outputs())
        return roles

    def _observe(self, now: float, plant: Plant) -> Observations:
        states = self.hass.states
        outputs: dict[str, OutputState] = {}
        for entity, role in plant.outputs().items():
            state = states.get(entity)
            changed = now if state is None else state.last_changed_timestamp
            if role is OutputRole.SOURCE_MODE:
                option = option_value(state)
                outputs[entity] = OptionState(option, self.memory.since(entity, option, changed))
            else:
                on = switch_value(state)
                outputs[entity] = SwitchState(on, self.memory.since(entity, on, changed))
        readiness: dict[str, SwitchState] = {}
        for loop in plant.all_loops:
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
        for zone in plant.zones:
            if isinstance(zone.thermostat, ExternalThermostat):
                thermostats[zone.slug] = external_thermostat(states.get(zone.thermostat.entity))
            elif (digital := self.thermostats.get(zone.slug)) is not None:
                thermostats[zone.slug] = digital
        # A stopping Plant runs its off sequence, as with Control equipment off, and an
        # invalid configuration only observes.
        stopping = self.previous.stopping
        return Observations(
            mode=self.requested_mode,
            control=self.control and stopping is None and self.problem is None,
            armed=self.armed if stopping is None else stopping.outputs,
            outputs=outputs,
            readiness=readiness,
            sensors=sensors,
            areas=dict(self.areas.area_sensors),
            thermostats=thermostats,
        )

    def _sensor_kinds(self) -> dict[str, SensorKind]:
        """Every numeric sensor the Plants read now, with what it measures."""
        kinds: dict[str, SensorKind] = {}
        for plant in self._plants():
            self._add_sensor_kinds(plant, kinds)
        return kinds

    def _add_sensor_kinds(self, plant: Plant, kinds: dict[str, SensorKind]) -> None:
        for pump in plant.pumps:
            if pump.supply_temperature is not None:
                kinds[pump.supply_temperature] = SensorKind.WATER
        for loop in plant.all_loops:
            if loop.surface_temperature is not None:
                kinds[loop.surface_temperature] = SensorKind.AIR
        for zone in plant.zones:
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

    # Areas and the state listener

    @callback
    def _resolve_areas(self) -> None:
        """Re-read the covered areas and follow what they name now, without a reload."""
        covered = tuple(
            dict.fromkeys(area for plant in self._plants() for area in covered_area_ids(plant))
        )
        areas = resolve_area_sensors(self.hass, covered)
        if areas != self.areas or self._area_listener is None:
            self.areas = areas
            if self._area_listener is not None:
                self._area_listener()
            self._area_listener = async_track_area_changes(
                self.hass, covered, areas, self.request_evaluation
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
        tracked = set(self._roles()) | set(self._sensor_kinds())
        for plant in self._plants():
            for loop in plant.all_loops:
                tracked.update(valve.readiness for valve in loop.valves if valve.readiness)
            for zone in plant.zones:
                if isinstance(zone.thermostat, ExternalThermostat):
                    tracked.add(zone.thermostat.entity)
        return frozenset(tracked)

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        entity = event.data["entity_id"]
        role = self._roles().get(entity)
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

    # Scheduling and persistence

    @callback
    def _schedule(self, *at: float | None) -> None:
        """Evaluate again at the earliest of the given timestamps, if any."""
        if self._timer is not None:
            self._timer()
            self._timer = None
        times = [time for time in at if time is not None]
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
            "blocking_sensors": self.blocking.to_dict(),
            "mode": self.requested_mode.value,
            "commanding": self.previous.to_persist(self.armed if self.state.live else frozenset()),
        }

    @callback
    def _save(self) -> None:
        data = self._data()
        if data != self._saved:
            self._saved = data
            self.store.async_delay_save(lambda: data, STORE_SAVE_DELAY)

    # Repairs

    @callback
    def _sync_issues(self, result: Reconciled, reconciled: Plant, now: float) -> dict[str, str]:
        """Raise the current Repairs; ``reconciled`` is the Plant ``result`` drove.

        Return each bound entity that does not exist, with where the Plant binds it.
        """
        plant, states = self.plant, self.hass.states
        issues: list[Issue] = []
        if self.problem is not None:
            issues.append(invalid_plant(self.entry.title, self.problem))
        issues.extend(output_not_responding(reconciled, entity) for entity in result.repairs)
        armed = self.armed
        # A new Plant starts with nothing armed, and its owner arms it in Plant settings,
        # so a Repair then would only repeat that step. Once any output is armed, an
        # unarmed one is new, such as a new zone's valve, and waits for confirmation.
        if armed and (unarmed := set(self._outputs) - armed):
            issues.append(outputs_awaiting_confirmation(plant, unarmed))
        missing = {
            entity: path
            for entity, path in entity_paths(plant).items()
            if states.get(entity) is None
        }
        issues.extend(
            missing_binding(plant, self.document, entity, path) for entity, path in missing.items()
        )
        for area_id, names in self.areas.area_sensors.items():
            for entity in (names.temperature, names.humidity):
                if entity is not None and states.get(entity) is None:
                    missing[entity] = f"area {area_id}"
                    issues.append(missing_area_sensor(plant, self.areas.name(area_id), entity))
        issues.extend(
            zone_area_issue(plant, problem, self.areas)
            for problem in zone_area_problems(plant, self.areas)
        )
        # A sensor that does not exist already has its own Repair.
        issues.extend(
            zone_sensor_unusable(reconciled, zone, entity)
            for zone, entity in self.blocking.reported(now)
            if entity not in missing
        )
        current = tuple(issues)
        if current != self.issues or not self._issues_synced:
            self.issues, self._issues_synced = current, True
            async_sync_issues(self.hass, self.entry.entry_id, current)
        return missing


def store_key(entry_id: str) -> str:
    """Return the Store key of a Plant's persisted state."""
    return f"{DOMAIN}.{entry_id}"
