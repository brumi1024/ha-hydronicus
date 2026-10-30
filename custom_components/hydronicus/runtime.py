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

Every evaluation also tells the ``FlowHistory`` which loops pass flow, for the
runtime and duty cycle sensors. While a loop flows, a refresh updates those
sensors once a minute; it never evaluates and never sends a command.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    EventStateReportedData,
    HomeAssistant,
    callback,
)
from homeassistant.core import (
    State as HassState,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_state_report_event,
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
from .compressor import CompressorHistory
from .const import DOMAIN, OPTION_CONTROL, STORE_SAVE_DELAY, STORE_VERSION
from .core.comfort import Setbacks, next_period_target
from .core.dhw import DhwCommand, DhwState
from .core.model import (
    NUMERIC_ROLES,
    Desired,
    DigitalThermostat,
    ExternalThermostat,
    LearningMode,
    Mode,
    OutputRole,
    OutputTarget,
    Plant,
    Zone,
)
from .core.plant_file import entity_paths, export_plant
from .core.reconcile import Action, Reconciled, ReconcileState, reconcile, step_view
from .core.response import ZoneResponse, check_response
from .core.step import (
    TICK,
    DigitalThermostatState,
    NumericState,
    Observations,
    OptionState,
    OutputState,
    State,
    SwitchState,
    ThermostatState,
    step,
)
from .core.thermal import RecoveryEstimate, recovery_deficit
from .dispatch import Dispatcher
from .entity import zone_unique_id
from .flow_history import FlowHistory
from .forecast import WeatherForecast
from .issues import (
    NO_LOAD_REPAIR_TRIPS,
    Issue,
    IssueKind,
    UnusableInputs,
    async_sync_issues,
    condensation_inputs_unusable,
    evaluation_failed,
    invalid_plant,
    invalid_schedule_blocks,
    missing_area_sensor,
    missing_binding,
    output_not_responding,
    outputs_awaiting_confirmation,
    source_no_load,
    source_unhealthy,
    zone_area_issue,
    zone_not_responding,
    zone_sensor_unusable,
)
from .learning import LearningCoordinator, LearningSample
from .observe import (
    OutputMemory,
    SensorKind,
    external_thermostat,
    numeric_value,
    option_value,
    reading,
    schedule_state,
    switch_memory_value,
    switch_moving,
    switch_value,
    week_problems,
)
from .previous import PreviousConfiguration
from .storage import armed_outputs, control
from .view import PlantView, ZoneReadings, observed_flow, source_operation, zone_readings

_LOGGER = logging.getLogger(__name__)

# The action that returns a schedule helper's week, including each block's data.
SCHEDULE_DOMAIN: Final = "schedule"
SCHEDULE_GET: Final = "get_schedule"
# How many Dry run proposals diagnostics keep.
_PROPOSALS_KEPT: Final = 50
# How long after a failed evaluation the Plant evaluates again, in seconds.
EVALUATION_RETRY: Final = 60.0
# How often the flow counters are saved while nothing else changes, in seconds.
FLOW_SAVE_INTERVAL: Final = 900.0


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
        self.unusable = UnusableInputs()
        # Each calling zone's response check, by zone slug.
        self.responses: dict[str, ZoneResponse] = {}
        self.thermostats: dict[str, DigitalThermostatState] = {}
        # The owner's setbacks of each scheduled zone that has changed them, by zone slug.
        self.setbacks: dict[str, Setbacks] = {}
        # The owner's last DHW command, until an evaluation has applied it.
        self.dhw_command: DhwCommand | None = None
        # Each followed schedule helper's week from ``schedule.get_schedule``, or None
        # when it could not be read; absent until the first read finishes.
        self.schedule_weeks: dict[str, Mapping[str, Any] | None] = {}
        self.areas = AreaResolution()
        self.flow = FlowHistory()
        self.compressor = CompressorHistory()
        self.learning = LearningCoordinator(hass, entry.entry_id)
        self.forecast = (
            WeatherForecast(hass, plant.weather, self.request_evaluation)
            if plant.weather is not None and problem is None
            else None
        )
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
        self._report_listener: CALLBACK_TYPE | None = None
        self._area_listener: CALLBACK_TYPE | None = None
        self._tracked: frozenset[str] = frozenset()
        self._timer: CALLBACK_TYPE | None = None
        self._refresh: CALLBACK_TYPE | None = None
        self._hass_stop: CALLBACK_TYPE | None = None
        self._flow_saved_at = 0.0
        self.next_evaluation_at: float | None = None
        self.evaluation_error: str | None = None
        self._dispatcher = Dispatcher(hass, entry, plant.name, self._authorized)
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
        # Optional empirical data has its own store and cannot reset safety timers.
        await self.learning.async_load()
        data = await self.store.async_load()
        if not data:
            return
        try:
            self.state = State.from_dict(data.get("state", {}))
            self.reconcile_state = ReconcileState.from_dict(data.get("reconcile", {}))
            self.memory = OutputMemory.from_dict(data.get("outputs", {}))
            self.unusable = UnusableInputs.from_dict(data.get("unusable_inputs", {}))
            self.responses = {
                zone: ZoneResponse.from_dict(value)
                for zone, value in data.get("responses", {}).items()
            }
            self.flow = FlowHistory.from_dict(data.get("flow", {}))
            self.compressor = CompressorHistory.from_dict(data.get("compressor", {}))
            self.requested_mode = Mode(data.get("mode", Mode.OFF))
            self.setbacks = {
                zone: Setbacks(float(values["heat"]), float(values["cool"]))
                for zone, values in data.get("setbacks", {}).items()
            }
        except Exception as error:  # Whatever is wrong with it, the Plant starts over.
            _LOGGER.warning(
                "The persisted state of Plant %s could not be read and starts over: %s",
                self.entry.title,
                error,
            )
            self.state, self.reconcile_state = State(), ReconcileState()
            self.memory, self.requested_mode = OutputMemory(), Mode.OFF
            self.unusable, self.flow = UnusableInputs(), FlowHistory()
            self.compressor = CompressorHistory()
            self.setbacks, self.responses = {}, {}
        self.previous.load(data.get("commanding"))
        kept = set(self._outputs)
        if self.previous.persisted is not None:
            kept |= self.previous.persisted.outputs
        self.memory.forget_except(kept)
        if self.problem is None:
            # An invalid Plant keeps the counters for when it is fixed.
            plant = self.plant
            self.flow.forget_except(
                {str(loop.ref) for loop in plant.all_loops}, {zone.slug for zone in plant.zones}
            )
            scheduled = self.scheduled_zones()
            self.setbacks = {
                zone: values for zone, values in self.setbacks.items() if zone in scheduled
            }
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
        self._hass_stop = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._on_hass_stop
        )
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
        if self.forecast is not None:
            self.forecast.async_start()
        self.request_evaluation()

    async def async_stop(self) -> None:
        """Stop without sending a command, and save the persisted state now."""
        self._stop()
        await self._dispatcher.async_stop()
        if self.forecast is not None:
            await self.forecast.async_stop()
        await self.learning.async_stop()
        await self.store.async_save(self._data())

    @callback
    def _stop(self) -> None:
        """Cancel work immediately at every command-free lifecycle boundary."""
        self._stopped = True
        self.next_evaluation_at = None
        self._dispatcher.stop()
        if self.forecast is not None:
            self.forecast.stop()
        self.learning.stop(dt_util.utcnow().timestamp())
        for unsubscribe in (
            self._timer,
            self._refresh,
            self._hass_stop,
            self._state_listener,
            self._report_listener,
            self._area_listener,
            *self._unsubscribe,
        ):
            if unsubscribe is not None:
                unsubscribe()
        self._timer = self._refresh = self._hass_stop = None
        self._state_listener = self._report_listener = self._area_listener = None
        self._unsubscribe.clear()
        # The time until the next setup is not counted, whatever flows meanwhile.
        self.flow.pause(dt_util.utcnow().timestamp())

    @callback
    def _on_hass_stop(self, _event: Event) -> None:
        """Cancel work and save the final counters when Home Assistant stops.

        Home Assistant does not unload a Plant when it stops, so its stop event
        uses the same synchronous cancellation boundary as an unload.
        """
        self._hass_stop = None
        self._stop()
        self.store.async_delay_save(self._data)

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
    def reset_learning(self, zone: str) -> None:
        """Forget optional recovery history without changing targets or safety state."""
        self.learning.reset(zone)
        self.request_evaluation()

    def scheduled_zones(self) -> dict[str, DigitalThermostat]:
        """Each zone whose digital thermostat follows a schedule, by zone slug."""
        return {
            zone.slug: zone.thermostat
            for zone in self.plant.zones
            if isinstance(zone.thermostat, DigitalThermostat)
            and zone.thermostat.schedule is not None
        }

    def zone_setbacks(self, zone: str) -> Setbacks | None:
        """A scheduled zone's current setbacks: the owner's, else the configured ones."""
        config = self.scheduled_zones().get(zone)
        if config is None or config.schedule is None:
            return None
        return self.setbacks.get(
            zone, Setbacks(config.schedule.heat_setback, config.schedule.cool_setback)
        )

    @callback
    def set_setback(self, zone: str, mode: Mode, value: float) -> None:
        """Take a scheduled zone's new heating or cooling setback and evaluate."""
        current = self.zone_setbacks(zone)
        if current is None or mode is Mode.OFF:
            return
        self.setbacks[zone] = (
            replace(current, heat=value) if mode is Mode.HEAT else replace(current, cool=value)
        )
        self._save()
        self._publish()
        self.request_evaluation()

    @callback
    def command_dhw(
        self,
        *,
        on: bool | None = None,
        target: float | None = None,
        boost: float | None = None,
        boost_for: float | None = None,
        end_boost: bool = False,
    ) -> None:
        """Take the owner's DHW command from an entity or the boost action, and evaluate."""
        # Each command is stamped later than the last, so that each applies once.
        last = max(
            (
                at
                for at in (
                    self.state.dhw.command_at,
                    None if self.dhw_command is None else self.dhw_command.at,
                )
                if at is not None
            ),
            default=0.0,
        )
        at = max(dt_util.utcnow().timestamp(), last + 0.001)
        pending = self.dhw_command
        if pending is not None:
            # A command no evaluation has applied yet keeps what this one leaves alone.
            on = pending.on if on is None else on
            target = pending.target if target is None else target
            if boost is None and not end_boost:
                boost, boost_for, end_boost = pending.boost, pending.boost_for, pending.end_boost
        self.dhw_command = DhwCommand(at, on, target, boost, boost_for, end_boost)
        self.request_evaluation()

    @property
    def dhw(self) -> DhwState | None:
        """The owned DHW settings, None before the first evaluation or without DHW."""
        view = self.view
        return None if view is None else view.desired.dhw

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

    def _authorized(self, action: Action) -> bool:
        """Check the current authorization immediately before sending an output command."""
        stopping = self.previous.stopping
        armed = self.armed if stopping is None else stopping.outputs
        return (
            not self._stopped
            and self.state.live
            and action.entity in armed
            and self.view is not None
            and self.view.desired.outputs.get(action.entity) == action.target
        )

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
        self.evaluation_error = f"{type(error).__name__}: {error}"
        failed = evaluation_failed(self.plant.name, self.evaluation_error)
        current = (
            *(issue for issue in self.issues if issue.kind is not IssueKind.EVALUATION_FAILED),
            failed,
        )
        if current != self.issues:
            self.issues = current
            async_sync_issues(self.hass, self.entry.entry_id, current)
        self._publish()

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
        fingerprints = self._learning_fingerprints(plant, observations)
        self.learning.synchronize(fingerprints)
        observations = replace(
            observations, recovery=self._recovery_estimates(plant, observations, now)
        )
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
        self._log_source_reports(desired)
        for event in desired.dhw_events:
            _LOGGER.info("Plant %s: %s", self.entry.title, event)
        command = self.dhw_command
        if command is not None and (
            state.dhw.command_at is not None and state.dhw.command_at >= command.at
        ):
            self.dhw_command = None
        self.state, self.reconcile_state = state, result.state
        self._dispatcher.discard_obsolete(observations.armed, desired.outputs)
        self.evaluation_error = None
        self.unusable.update(
            {
                IssueKind.ZONE_SENSOR_UNUSABLE: desired.blocking_sensors,
                IssueKind.CONDENSATION_INPUT_UNUSABLE: desired.blocking_condensation_inputs,
                IssueKind.SOURCE_UNHEALTHY: {"source": (plant.source.health_sensor,)}
                if desired.source_fault is not None
                and plant.source is not None
                and plant.source.health_sensor is not None
                else {},
            },
            now,
        )
        # Only flow observed while the Plant is live counts, never a Dry run proposal.
        source_winding = plant.source is not None and plant.source.request in state.winding
        loops, zones = (
            observed_flow(self.plant, observations, now, source_winding=source_winding)
            if state.live
            else (frozenset(), frozenset())
        )
        self.flow.update(now, loops, zones)
        readings = {
            zone.slug: zone_readings(zone, observations, self.areas, now)
            for zone in self.plant.zones
        }
        response_due = self._check_responses(plant, observations, desired, zones, readings, now)
        if plant.source is not None and plant.source.compressor_sensor is not None:
            frequency = observations.sensors.get(plant.source.compressor_sensor)
            value = None if frequency is None else frequency.value
            self.compressor.observe(now, None if value is None else value > 0)
        self._sample_learning(plant, observations, desired, fingerprints, zones, now)
        self.proposals.extend(Proposal(now, a.entity, a.target) for a in result.proposed)
        if self.previous.stopping is not None and not state.live:
            self.previous.stopped()
            self.request_evaluation()
        self._save()
        if result.send:
            self._dispatcher.send(result.send, now)
        self._schedule(
            None if due is None else now + due,
            result.retry_at,
            self.unusable.next_report(now),
            self.learning.next_sample_at,
            response_due,
        )
        self._schedule_refresh(now)
        missing = self._sync_issues(result, plant, now)
        self.view = PlantView(
            plant=self.plant,
            at=now,
            observations=observations,
            seen=seen,
            desired=desired,
            reconciled=result,
            zones=readings,
            missing=missing,
            problem=self.problem,
            stopping=self.previous.stopping,
            source_winding=source_winding,
            live=state.live,
            not_responding=self.zones_not_responding,
        )
        self._publish()
        if result.proposed:
            # A Dry run proposal counts as observed, so it is a change that evaluates
            # again, as the observed result of a live call would be.
            self.request_evaluation()

    def _check_responses(
        self,
        plant: Plant,
        observations: Observations,
        desired: Desired,
        served: frozenset[str],
        readings: Mapping[str, ZoneReadings],
        now: float,
    ) -> float | None:
        """Advance each zone's response check, and return when the next one may fail.

        A zone is served while a loop serving it is observed passing flow, which
        only counts while the Plant is live, and the source, if any, is observed running.
        """
        running = plant.source is None or source_operation(plant, observations).active is True
        responses: dict[str, ZoneResponse] = {}
        due: list[float] = []
        for zone in self.plant.zones:
            demand = desired.demands.get(zone.slug)
            if zone.response_check is None or demand is None:
                continue
            response, fails_at = check_response(
                zone.response_check,
                self.responses.get(zone.slug),
                demand.mode,
                calling=demand.on and demand.mode is desired.mode,
                served=running and zone.slug in served,
                temperature=readings[zone.slug].temperature,
                now=now,
            )
            if response is not None:
                responses[zone.slug] = response
            if fails_at is not None:
                due.append(fails_at + TICK)
        self.responses = responses
        return min(due, default=None)

    @property
    def zones_not_responding(self) -> dict[str, float]:
        """Each zone whose response check failed, with when it did."""
        return {
            zone: response.failed_at
            for zone, response in self.responses.items()
            if response.failed_at is not None
        }

    def _plants(self) -> tuple[Plant, ...]:
        """The Plants the runtime reads: the configured one and one that is stopping."""
        stopping = self.previous.stopping
        return (self.plant,) if stopping is None else (self.plant, stopping.plant)

    def _learning_fingerprints(self, plant: Plant, observations: Observations) -> dict[str, str]:
        """Invalidate evidence before prediction when its physical or sensor context changes."""
        fingerprints: dict[str, str] = {}
        for zone in plant.zones:
            if not isinstance(zone.thermostat, DigitalThermostat) or (
                zone.thermostat.learning is LearningMode.OFF
            ):
                continue
            loops = plant.zone_loops(zone.slug)
            # Switching from observation to assist does not change the learned system.
            config = asdict(zone)
            config["thermostat"].pop("learning")
            config["thermostat"].pop("weather_aware")
            context = {
                "zone": config,
                "loops": [asdict(loop) for loop in loops],
                "pumps": [asdict(plant.pump(slug)) for slug in sorted({x.pump for x in loops})],
                "source": None if plant.source is None else asdict(plant.source),
                "weather": None if plant.weather is None else asdict(plant.weather),
                "areas": {area.area: observations.areas.get(area.area) for area in zone.areas},
            }
            fingerprints[zone.slug] = hashlib.sha256(
                json.dumps(context, sort_keys=True, default=str).encode()
            ).hexdigest()
        return fingerprints

    def _recovery_estimates(
        self, plant: Plant, observations: Observations, now: float
    ) -> dict[str, RecoveryEstimate]:
        estimates: dict[str, RecoveryEstimate] = {}
        for zone in plant.zones:
            config = zone.thermostat
            thermostat = observations.thermostats.get(zone.slug)
            if (
                not isinstance(config, DigitalThermostat)
                or config.learning is LearningMode.OFF
                or not isinstance(thermostat, DigitalThermostatState)
                or thermostat.hvac_mode is Mode.OFF
            ):
                continue
            temperature = zone_readings(zone, observations, self.areas, now).temperature
            if temperature is None:
                continue
            schedule = (
                None
                if config.schedule is None
                else observations.schedules.get(config.schedule.entity)
            )
            # Early start recovers towards the next scheduled period's level.
            following = (
                None
                if schedule is None
                else next_period_target(
                    config,
                    thermostat.hvac_mode,
                    thermostat.target,
                    schedule,
                    observations.setbacks.get(zone.slug),
                )
            )
            deficit = recovery_deficit(
                thermostat.hvac_mode,
                thermostat.target if following is None else following,
                temperature,
            )
            baseline = self.learning.estimate(zone.slug, thermostat.hvac_mode, deficit, now)
            estimates[zone.slug] = baseline
            if (
                not config.weather_aware
                or config.schedule is None
                or self.forecast is None
                or self.forecast.snapshot is None
            ):
                continue
            if schedule is None or following is None or schedule.next_event is None:
                continue
            end = schedule.next_event
            start = max(now, end - config.schedule.max_early_start)
            outdoor = self.forecast.snapshot.temperature_between(start, end, now)
            if outdoor is not None:
                candidate = self.learning.estimate(
                    zone.slug, thermostat.hvac_mode, deficit, now, outdoor
                )
                if candidate.confidence and candidate.weather_adjusted:
                    estimates[zone.slug] = replace(
                        candidate,
                        valid_until=min(
                            candidate.valid_until or now, self.forecast.snapshot.expires_at
                        ),
                    )
        return estimates

    def _log_source_reports(self, desired: Desired) -> None:
        """Log when a source fault, a handover, or a request without a path begins and ends."""
        before = None if self.view is None else self.view.desired
        fault = None if before is None else before.source_fault
        if desired.source_fault != fault:
            if desired.source_fault is not None:
                _LOGGER.warning(
                    "Plant %s releases its source: %s", self.entry.title, desired.source_fault
                )
            else:
                _LOGGER.info("Plant %s: the source reads healthy again", self.entry.title)
        if desired.source_handover != (before is not None and before.source_handover):
            _LOGGER.info(
                "Plant %s %s",
                self.entry.title,
                "hands its source to the source's own controller and sends it nothing"
                if desired.source_handover
                else "controls its source again",
            )
        if desired.source_without_path and not (before is not None and before.source_without_path):
            _LOGGER.warning(
                "Plant %s found its source request on with no open loop and a running pump; "
                "it releases the request",
                self.entry.title,
            )

    def _sample_learning(
        self,
        plant: Plant,
        observations: Observations,
        desired: Desired,
        fingerprints: dict[str, str],
        flowing_zones: frozenset[str],
        now: float,
    ) -> None:
        samples: dict[str, LearningSample] = {}
        outdoor = None if self.forecast is None else self.forecast.outdoor_observation(now)
        for zone in plant.zones:
            config = zone.thermostat
            thermostat = observations.thermostats.get(zone.slug)
            if not isinstance(config, DigitalThermostat) or zone.slug not in fingerprints:
                continue
            comfort = desired.comfort.get(zone.slug)
            temperature = zone_readings(zone, observations, self.areas, now).temperature
            reports = self._temperature_reports(zone, observations, now)
            mode = (
                thermostat.hvac_mode if isinstance(thermostat, DigitalThermostatState) else Mode.OFF
            )
            loops = plant.zone_loops(zone.slug)
            windows_clear = all(
                (contact := observations.readiness.get(entity)) is not None and contact.on is False
                for entity in zone.windows
            )
            permitted = (
                windows_clear
                and zone.slug not in self.state.windows_open
                and zone.slug not in desired.frost_protection
                and desired.exercise is None
                and desired.mode is mode
                and mode is not Mode.OFF
                and not any(
                    str(loop.ref) in desired.blocking_condensation_inputs
                    or (
                        self.state.guards.get(str(loop.ref)) is not None
                        and self.state.guards[str(loop.ref)].blocked
                    )
                    for loop in loops
                    if mode is Mode.COOL and mode in loop.modes
                )
            )
            samples[zone.slug] = LearningSample(
                zone=zone.slug,
                mode=mode,
                learning=config.learning,
                fingerprint=fingerprints[zone.slug],
                temperature=temperature,
                temperature_at=max((at for at, _ in reports), default=None),
                temperature_max_age=min((age for _, age in reports), default=0.0),
                target=None if comfort is None else comfort.target,
                preset=(
                    str(thermostat.preset)
                    if isinstance(thermostat, DigitalThermostatState)
                    else "unavailable"
                ),
                circulating=zone.slug in flowing_zones,
                live=self.state.live and observations.control and self.previous.stopping is None,
                permitted=permitted,
                reason=None
                if permitted
                else "control or safety condition prevents a clean recovery",
                outdoor_temperature=None if outdoor is None else outdoor.temperature,
            )
        self.learning.update(samples, now)

    @staticmethod
    def _temperature_reports(
        zone: Zone, observations: Observations, now: float
    ) -> list[tuple[float, float]]:
        inputs = [(sensor.entity, sensor.max_age) for sensor in zone.temperature]
        inputs.extend(
            (names.temperature, area.max_age)
            for area in zone.areas
            if (names := observations.areas.get(area.area)) is not None
            and names.temperature is not None
        )
        return [
            (sensor.updated, max_age)
            for entity, max_age in inputs
            if (sensor := observations.sensors.get(entity)) is not None
            and sensor.value is not None
            and sensor.updated <= now < sensor.updated + max_age
        ]

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
            elif role in NUMERIC_ROLES:
                value = numeric_value(state)
                outputs[entity] = NumericState(value, self.memory.since(entity, value, changed))
            else:
                since = self.memory.since(entity, switch_memory_value(state), changed)
                outputs[entity] = SwitchState(switch_value(state), since, switch_moving(state))
        readiness: dict[str, SwitchState] = {}
        for loop in plant.all_loops:
            for valve in loop.valves:
                if valve.readiness is not None:
                    state = states.get(valve.readiness)
                    readiness[valve.readiness] = SwitchState(
                        switch_value(state), now if state is None else state.last_changed_timestamp
                    )
        # A condensation switch or window that does not exist is left out: a missing
        # switch blocks cooling, and a missing window reads closed.
        for entity in contacts(plant):
            if (state := states.get(entity)) is not None:
                readiness[entity] = SwitchState(switch_value(state), state.last_changed_timestamp)
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
            schedules={
                zone.thermostat.schedule.entity: schedule_state(
                    states.get(zone.thermostat.schedule.entity),
                    self.schedule_weeks.get(zone.thermostat.schedule.entity),
                )
                for zone in plant.zones
                if isinstance(zone.thermostat, DigitalThermostat)
                and zone.thermostat.schedule is not None
            },
            setbacks={
                slug: setbacks
                for slug in self.scheduled_zones()
                if (setbacks := self.zone_setbacks(slug)) is not None
            },
            dhw_command=self.dhw_command,
        )

    def _sensor_kinds(self) -> dict[str, SensorKind]:
        """Every numeric sensor the Plants read now, with what it measures."""
        kinds: dict[str, SensorKind] = {}
        for plant in self._plants():
            self._add_sensor_kinds(plant, kinds)
        return kinds

    def _add_sensor_kinds(self, plant: Plant, kinds: dict[str, SensorKind]) -> None:
        if plant.weather is not None and plant.weather.outdoor_sensor is not None:
            kinds[plant.weather.outdoor_sensor] = SensorKind.AIR
        if (
            plant.source is not None
            and plant.source.supply is not None
            and plant.source.supply.outdoor_sensor is not None
        ):
            kinds[plant.source.supply.outdoor_sensor] = SensorKind.AIR
        for pump in plant.pumps:
            if pump.supply_temperature is not None:
                kinds[pump.supply_temperature] = SensorKind.WATER
        if plant.source is not None and (guard := plant.source.no_load) is not None:
            kinds[guard.supply_temperature] = SensorKind.WATER
            kinds[guard.return_temperature] = SensorKind.WATER
            kinds[guard.compressor_sensor] = SensorKind.LEVEL
        if plant.source is not None and plant.source.compressor_sensor is not None:
            kinds[plant.source.compressor_sensor] = SensorKind.LEVEL
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
            if self._report_listener is not None:
                self._report_listener()
            self._report_listener = async_track_state_report_event(
                self.hass,
                sorted(set(self._sensor_kinds()) | self._schedule_entities()),
                self._on_sensor_report,
            )
            for entity in self._schedule_entities() - set(self.schedule_weeks):
                self._refresh_week(entity)

    def _tracked_entities(self) -> frozenset[str]:
        tracked = set(self._roles()) | set(self._sensor_kinds())
        for plant in self._plants():
            if plant.weather is not None:
                tracked.add(plant.weather.entity)
            for loop in plant.all_loops:
                tracked.update(valve.readiness for valve in loop.valves if valve.readiness)
            tracked.update(contacts(plant))
            for zone in plant.zones:
                if isinstance(zone.thermostat, ExternalThermostat):
                    tracked.add(zone.thermostat.entity)
                elif zone.thermostat.schedule is not None:
                    tracked.add(zone.thermostat.schedule.entity)
        return frozenset(tracked)

    def _schedule_entities(self) -> frozenset[str]:
        return frozenset(
            zone.thermostat.schedule.entity
            for plant in self._plants()
            for zone in plant.zones
            if isinstance(zone.thermostat, DigitalThermostat)
            and zone.thermostat.schedule is not None
        )

    @callback
    def _refresh_week(self, entity: str) -> None:
        """Read a schedule helper's week again, since only its blocks name the next level."""
        self.entry.async_create_background_task(
            self.hass, self._async_refresh_week(entity), f"{DOMAIN} schedule week {entity}"
        )

    async def _async_refresh_week(self, entity: str) -> None:
        week: Mapping[str, Any] | None
        try:
            response = await self.hass.services.async_call(
                SCHEDULE_DOMAIN,
                SCHEDULE_GET,
                target={"entity_id": entity},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as error:
            _LOGGER.debug("The week of %s could not be read: %s", entity, error)
            week = None
        else:
            found = None if response is None else response.get(entity)
            week = found if isinstance(found, Mapping) else None
        if self._stopped or (entity in self.schedule_weeks and self.schedule_weeks[entity] == week):
            return
        self.schedule_weeks[entity] = week
        self.request_evaluation()

    @callback
    def _on_sensor_report(self, event: Event[EventStateReportedData]) -> None:
        """An unchanged report can recover a previously stale required sensor.

        A schedule helper reports unchanged when its blocks are edited without
        moving its state or next transition, so its week is read again.
        """
        if event.data["entity_id"] in self._schedule_entities():
            self._refresh_week(event.data["entity_id"])
        self.request_evaluation()

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        entity = event.data["entity_id"]
        if entity in self._schedule_entities():
            self._refresh_week(entity)
        role = self._roles().get(entity)
        new_state: HassState | None = event.data["new_state"]
        if role is not None and new_state is not None:
            # Every change of an output is remembered, so no change goes unseen
            # between two evaluations.
            value: bool | str | float | None
            if role is OutputRole.SOURCE_MODE:
                value = option_value(new_state)
            elif role in NUMERIC_ROLES:
                value = numeric_value(new_state)
            else:
                value = switch_memory_value(new_state)
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
        self.next_evaluation_at = min(times) if times else None
        if times:
            self._timer = async_track_point_in_utc_time(
                self.hass, self._on_timer, dt_util.utc_from_timestamp(min(times))
            )

    @callback
    def _on_timer(self, _now: datetime) -> None:
        self._timer = None
        self.next_evaluation_at = None
        self.request_evaluation()

    @callback
    def _schedule_refresh(self, now: float) -> None:
        """Refresh the flow sensors when they change next without an evaluation."""
        if self._refresh is not None:
            self._refresh()
            self._refresh = None
        if (at := self.flow.next_refresh(now)) is not None:
            self._refresh = async_track_point_in_utc_time(
                self.hass, self._on_refresh, dt_util.utc_from_timestamp(at)
            )

    @callback
    def _on_refresh(self, _now: datetime) -> None:
        """Count the flow up to now and publish it; this never evaluates."""
        self._refresh = None
        now = dt_util.utcnow().timestamp()
        self.flow.update(now)
        self._save()
        self._publish()
        self._schedule_refresh(now)

    def _data(self) -> dict[str, Any]:
        return {
            "state": self.state.to_dict(),
            "reconcile": self.reconcile_state.to_dict(),
            "outputs": self.memory.to_dict(),
            "unusable_inputs": self.unusable.to_dict(),
            "responses": {
                zone: response.to_dict() for zone, response in sorted(self.responses.items())
            },
            "flow": self.flow.to_dict(),
            "compressor": self.compressor.to_dict(),
            "mode": self.requested_mode.value,
            "setbacks": {
                zone: {"heat": values.heat, "cool": values.cool}
                for zone, values in sorted(self.setbacks.items())
            },
            "commanding": self.previous.to_persist(self.armed if self.state.live else frozenset()),
        }

    @callback
    def _save(self) -> None:
        data = self._data()
        if data == self._saved:
            return
        now = dt_util.utcnow().timestamp()
        if (
            self._saved is not None
            and {**data, "flow": None} == {**self._saved, "flow": None}
            and now < self._flow_saved_at + FLOW_SAVE_INTERVAL
        ):
            # Only the flow counters changed, which they do every minute while a loop flows.
            return
        self._saved, self._flow_saved_at = data, now
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
        for zone, config in self.scheduled_zones().items():
            assert config.schedule is not None
            entity = config.schedule.entity
            week = self.schedule_weeks.get(entity)
            if week is not None:
                problems = week_problems(week)
            else:
                # Without the week, only the active block's data can be read.
                observed = schedule_state(states.get(entity))
                problems = [] if observed.level.error is None else [observed.level.error]
            if problems:
                issues.append(invalid_schedule_blocks(plant, zone, entity, problems))
        # An input that does not exist already has its own Repair.
        issues.extend(
            zone_sensor_unusable(reconciled, zone, entity)
            for zone, entity in self.unusable.reported(IssueKind.ZONE_SENSOR_UNUSABLE, now)
            if entity not in missing
        )
        issues.extend(
            condensation_inputs_unusable(
                reconciled,
                (
                    (loop, entity)
                    for loop, entity in self.unusable.reported(
                        IssueKind.CONDENSATION_INPUT_UNUSABLE, now
                    )
                    if entity not in missing
                ),
            )
        )
        issues.extend(
            source_unhealthy(reconciled, entity)
            for _, entity in self.unusable.reported(IssueKind.SOURCE_UNHEALTHY, now)
            if entity not in missing
        )
        issues.extend(
            zone_not_responding(self.plant, zone, self.responses[zone])
            for zone in self.zones_not_responding
        )
        if len(trips := self.state.no_load_trips) >= NO_LOAD_REPAIR_TRIPS:
            issues.append(source_no_load(reconciled, len(trips)))
        current = tuple(issues)
        if current != self.issues or not self._issues_synced:
            self.issues, self._issues_synced = current, True
            async_sync_issues(self.hass, self.entry.entry_id, current)
        return missing


def contacts(plant: Plant) -> set[str]:
    """Every condensation switch, window, equipment proof, and source input a Plant reads."""
    found = {pump.condensation_switch for pump in plant.pumps}
    found.update(pump.running_sensor for pump in plant.pumps)
    found.update(pump.flow_sensor for pump in plant.pumps)
    if plant.source is not None:
        found.add(plant.source.running_sensor)
        found.add(plant.source.health_sensor)
        found.add(plant.source.handover_sensor)
        found.add(plant.source.inhibit_sensor)
    found.update(loop.condensation_switch for loop in plant.all_loops)
    found.update(window for zone in plant.zones for window in zone.windows)
    return {entity for entity in found if entity is not None}


def store_key(entry_id: str) -> str:
    """Return the Store key of a Plant's persisted state."""
    return f"{DOMAIN}.{entry_id}"
