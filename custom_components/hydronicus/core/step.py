"""One pure evaluation: from configuration, observations, and state to the desired state.

``step()`` is the whole control policy. It reads a snapshot of what the runtime
observed, the State persisted by the previous evaluation, and the time, and
returns the next State, the desired state of every output, and the seconds until
the next evaluation is due. It never talks to Home Assistant; the runtime builds
``Observations`` from entity states, and the reconciler in ``reconcile`` drives
the outputs to the desired state.

The desired state already carries every hydraulic sequence: a valve stays open
while a pump that may still run needs it as its path, a pump stays on while the
source request may still be on and needs it, and the source is requested only
once its loops are ready and their pumps are observed running. The reconciler
therefore only orders the calls of one evaluation, retries, and counts failures.

Times are POSIX timestamps in seconds from the wall clock, the same clock that
stamps each observation. The clock may step backwards, so an observation can
carry a time later than ``now``; such an interval counts as not yet elapsed.
Readiness that was once observed is kept in State, so a backward step never
takes a ready loop away.

A decision never counts on a call having acted: a call sent less than
``CALL_TIMEOUT`` ago that no observation has confirmed may still act, so a pump
or the source it may start counts as possibly running, and one it may stop
counts as possibly stopped.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from .demand import (
    AreaSensors,
    DemandState,
    DigitalThermostatState,
    ExternalThermostatState,
    Reading,
    ThermostatState,
    aggregate,
    coldest_temperature,
    fresh,
    frost_demand,
    unusable_sensors,
    worst_dew_point,
    zone_demand,
    zone_values,
)
from .model import (
    Demand,
    Desired,
    DigitalThermostat,
    Exercise,
    Loop,
    MinFlow,
    Mode,
    OptionTarget,
    OutputRole,
    OutputTarget,
    Plant,
    Pump,
    RunKind,
    SwitchTarget,
    Valve,
    Zone,
)

__all__ = [
    "CALL_TIMEOUT",
    "CONDENSATION_MARGIN",
    "GUARD_MIN_BLOCKED",
    "GUARD_REFERENCE_MAX_AGE",
    "GUARD_RELEASE",
    "HUMIDITY_RELEASE",
    "TICK",
    "AreaSensors",
    "DemandState",
    "DigitalThermostatState",
    "ExerciseState",
    "ExternalThermostatState",
    "GuardState",
    "Observations",
    "OptionState",
    "OutputState",
    "Reading",
    "Sent",
    "State",
    "SwitchState",
    "ThermostatState",
    "satisfies",
    "step",
    "value_of",
]

# The guard blocks a cooling loop below the worst-case dew point plus this margin, in kelvin.
CONDENSATION_MARGIN: Final = 2.0
# A blocked guard releases only this far above the blocking threshold, in kelvin.
GUARD_RELEASE: Final = 1.0
# A blocked guard releases only after it has blocked this long, in seconds.
GUARD_MIN_BLOCKED: Final = 300.0
# A humidity cutoff releases only this far below its limit, in percentage points.
HUMIDITY_RELEASE: Final = 5.0
# A condensation reference is stale this long after its last report, in seconds.
# Supply and surface temperatures fall fast once cooling starts, so a reference
# must be fresher than a room reading.
GUARD_REFERENCE_MAX_AGE: Final = 1800.0
# How long the runtime waits for one service call; one sent longer ago has acted or never will.
CALL_TIMEOUT: Final = 10.0
# Seconds after a deadline at which the next evaluation runs, so that it finds it passed.
TICK: Final = 0.001

ON: Final = SwitchTarget(True)
OFF: Final = SwitchTarget(False)


# Observations


@dataclass(frozen=True, slots=True)
class SwitchState:
    """A switch, valve, or binary sensor as observed."""

    # None while the entity is unavailable or unknown.
    on: bool | None
    # When the observed state last changed (``last_changed``), including a
    # change to or from unavailable, and from moving to arrived.
    since: float
    # The entity reports that it is still on its way to ``on``, as a valve entity
    # does while it is opening or closing. A moving valve does not show its
    # target yet and may pass flow either way.
    moving: bool = False


@dataclass(frozen=True, slots=True)
class OptionState:
    """A select as observed."""

    option: str | None
    since: float


type OutputState = SwitchState | OptionState


@dataclass(frozen=True, slots=True)
class Sent:
    """A call the reconciler sent that no observation has confirmed yet."""

    target: OutputTarget
    # When it was sent; it may act until ``CALL_TIMEOUT`` after that.
    at: float


@dataclass(frozen=True, slots=True)
class Observations:
    """One snapshot of everything ``step()`` reads, taken by the runtime."""

    # The Plant mode the mode select requests.
    mode: Mode
    # The Control equipment switch.
    control: bool
    # The output entities the owner has confirmed Hydronicus may command.
    armed: frozenset[str]
    # Every output of ``Plant.outputs()``; a missing entity counts as unavailable.
    outputs: Mapping[str, OutputState] = field(default_factory=dict)
    # Every binary sensor the Plant reads: valve readiness sensors, condensation
    # switches, and windows; a missing one counts as unavailable.
    readiness: Mapping[str, SwitchState] = field(default_factory=dict)
    # Every numeric sensor the Plant reads: zone temperature and humidity,
    # explicit or named by an area, pump supply, and loop surface temperatures.
    sensors: Mapping[str, Reading] = field(default_factory=dict)
    # Each covered area's current sensors, resolved by the runtime on every evaluation.
    areas: Mapping[str, AreaSensors] = field(default_factory=dict)
    # Each zone's thermostat, by zone slug.
    thermostats: Mapping[str, ThermostatState] = field(default_factory=dict)
    # The reconciler's unconfirmed calls, by output entity; ``reconcile.step_view`` fills it.
    sent: Mapping[str, Sent] = field(default_factory=dict)


def satisfies(state: OutputState | None, target: OutputTarget) -> bool:
    """Whether an observed output shows a target."""
    match target, state:
        case SwitchTarget(on=on), SwitchState(on=observed, moving=moving):
            return observed is on and not moving
        case OptionTarget(option=option), OptionState(option=observed):
            return observed == option
        case _:
            return False


def value_of(state: OutputState) -> bool | str | None:
    """The observed value of an output, None while it is unavailable."""
    match state:
        case SwitchState(on=on):
            return on
        case OptionState(option=option):
            return option


# State


@dataclass(frozen=True, slots=True)
class GuardState:
    """A cooling loop's condensation guard and when it last changed, for its minimum time."""

    blocked: bool
    since: float


@dataclass(frozen=True, slots=True)
class ExerciseState:
    """The exercise of one pump's idle switch or valves, see ``_Plan.exercise``."""

    pump: str
    # When the switched pump was first seen running in the exercise.
    started: float | None = None
    # The exercise is over and its pump, still possibly running, stops without overrun.
    done: bool = False


@dataclass(frozen=True, slots=True)
class State:
    """What ``step()`` carries from one evaluation to the next.

    The runtime persists it with ``to_dict`` after every evaluation that changes
    it and restores it with ``from_dict`` before the first evaluation, so a
    reload or restart continues every timer. The runtime reads only ``live``;
    the other fields belong to ``step()``.
    """

    # Outputs are commanded: Control equipment is on, or it was turned off and
    # the off-mode sequence has not finished. False is Dry run.
    live: bool = False
    # The mode the outputs run in, ``Desired.mode``: during a changeover it stays
    # the old mode until the old mode's loops have stopped, and it is off during the dwell.
    mode: Mode = Mode.OFF
    # The last heat or cool mode that ran, which labels any flow; off before any ran.
    last_mode: Mode = Mode.OFF
    # Whether a loop could flow at the last evaluation, and when the last such
    # flow was seen to end; the opposite mode starts ``mode_dwell`` after that.
    flowing: bool = False
    flow_ended: float | None = None
    # The source request of the last evaluation and when it last changed, for min_on and min_off.
    source_request: bool = False
    source_changed: float | None = None
    # Each zone's demand, by zone slug.
    demands: Mapping[str, DemandState] = field(default_factory=dict)
    # Each cooling loop's condensation guard, by ``str(LoopRef)``.
    guards: Mapping[str, GuardState] = field(default_factory=dict)
    # When each switched pump's overrun started, by pump slug.
    overruns: Mapping[str, float] = field(default_factory=dict)
    # Each valve observed ready, with the observed ``since`` it was ready at, so
    # it stays ready until its observed state changes.
    ready: Mapping[str, float] = field(default_factory=dict)
    # The valves and the source request that may have been on, whose closing or
    # post-run may still go on once they are observed off.
    winding: frozenset[str] = frozenset()
    # The zones whose demand an open window turns off, by slug.
    windows_open: frozenset[str] = frozenset()
    # The zones that frost protection heats, by zone slug, until they are warm again.
    frost: frozenset[str] = frozenset()
    # Since when each switched pump and valve has not been seen on, by entity, or
    # None while it is on; the clock of a new one starts when it is first seen.
    idle_since: Mapping[str, float | None] = field(default_factory=dict)
    # The exercise in progress, if any.
    exercise: ExerciseState | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-friendly data that ``from_dict`` reads back."""
        return {
            "live": self.live,
            "mode": self.mode.value,
            "last_mode": self.last_mode.value,
            "flowing": self.flowing,
            "flow_ended": self.flow_ended,
            "source_request": self.source_request,
            "source_changed": self.source_changed,
            "demands": {
                slug: {"mode": demand.mode.value, "on": demand.on, "since": demand.since}
                for slug, demand in self.demands.items()
            },
            "guards": {
                ref: {"blocked": guard.blocked, "since": guard.since}
                for ref, guard in self.guards.items()
            },
            "overruns": dict(self.overruns),
            "ready": dict(self.ready),
            "winding": sorted(self.winding),
            "windows_open": sorted(self.windows_open),
            "frost": sorted(self.frost),
            "idle_since": dict(self.idle_since),
            "exercise": None
            if self.exercise is None
            else {
                "pump": self.exercise.pump,
                "started": self.exercise.started,
                "done": self.exercise.done,
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> State:
        """Read persisted data; a missing key takes its initial value."""
        return cls(
            live=bool(data.get("live", False)),
            mode=Mode(data.get("mode", Mode.OFF)),
            last_mode=Mode(data.get("last_mode", Mode.OFF)),
            flowing=bool(data.get("flowing", False)),
            flow_ended=_optional_float(data.get("flow_ended")),
            source_request=bool(data.get("source_request", False)),
            source_changed=_optional_float(data.get("source_changed")),
            demands={
                slug: DemandState(
                    Mode(value["mode"]), bool(value["on"]), _optional_float(value["since"])
                )
                for slug, value in data.get("demands", {}).items()
            },
            guards={
                ref: GuardState(bool(value["blocked"]), float(value["since"]))
                for ref, value in data.get("guards", {}).items()
            },
            overruns={slug: float(value) for slug, value in data.get("overruns", {}).items()},
            ready={entity: float(value) for entity, value in data.get("ready", {}).items()},
            winding=frozenset(str(entity) for entity in data.get("winding", ())),
            windows_open=frozenset(str(zone) for zone in data.get("windows_open", ())),
            frost=frozenset(str(zone) for zone in data.get("frost", ())),
            idle_since={
                entity: _optional_float(value)
                for entity, value in data.get("idle_since", {}).items()
            },
            exercise=_exercise_state(data.get("exercise")),
        )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


@dataclass(frozen=True, slots=True)
class _Check:
    """One condition of a condensation guard: whether it blocks, whether it releases, and why."""

    blocks: bool
    releases: bool
    reason: str


def _exercise_state(value: Any) -> ExerciseState | None:
    if value is None:
        return None
    return ExerciseState(str(value["pump"]), _optional_float(value["started"]), bool(value["done"]))


# Evaluation


def step(
    plant: Plant, observations: Observations, state: State, now: float
) -> tuple[State, Desired, float | None]:
    """Return the next State, the desired state, and the seconds until the next evaluation.

    The seconds are None when only a change of observation needs a new
    evaluation. Safe shutdown is this same evaluation with the Plant mode
    forced to off: with Control equipment off, a live Plant runs the off-mode
    sequence and then goes to Dry run, where it evaluates the requested mode
    against the proposed outputs.
    """
    return _Evaluation(plant, observations, state, now).run()


class _Evaluation:
    """The stages of one ``step()``, with the caches and deadlines they share."""

    def __init__(self, plant: Plant, obs: Observations, state: State, now: float) -> None:
        self.plant, self.obs, self.state, self.now = plant, obs, state, now
        self.deadlines: list[float] = []
        self.reasons: dict[str, str] = {}
        # The zones whose demand an open window turns off now.
        self.windows_open: set[str] = set()
        # The zones that frost protection heats, which the demands stage finds.
        self.frost: list[str] = []
        # This evaluation's condensation guards, and since when each output is idle.
        self.guard_states: dict[str, GuardState] = {}
        self.idle_times: dict[str, float | None] = {}
        self._ready: dict[Loop, bool] = {}
        self._pumps = {pump.slug: pump for pump in plant.pumps}
        self._loops_of: dict[str, list[Loop]] = {pump.slug: [] for pump in plant.pumps}
        for loop in plant.all_loops:
            self._loops_of[loop.pump].append(loop)

    # Time

    def reached(self, deadline: float) -> bool:
        """Whether ``deadline`` has passed; if not, the evaluation is due then."""
        if self.now >= deadline:
            return True
        self.deadlines.append(deadline)
        return False

    # Outputs as observed, with the calls that may still act

    def switch(self, entity: str) -> bool | None:
        """Whether an output is observed on; None while it is unknown or still moving."""
        observed = self.obs.outputs.get(entity)
        if not isinstance(observed, SwitchState) or observed.moving:
            return None
        return observed.on

    def since(self, entity: str) -> float:
        observed = self.obs.outputs.get(entity)
        return self.now if observed is None else observed.since

    def pending(self, entity: str) -> OutputTarget | None:
        """The target of a call to ``entity`` that may still act."""
        sent = self.obs.sent.get(entity)
        if sent is None or satisfies(self.obs.outputs.get(entity), sent.target):
            return None
        return None if self.reached(sent.at + CALL_TIMEOUT) else sent.target

    def may_be_on(self, entity: str) -> bool:
        return self.switch(entity) is not False or self.pending(entity) == ON

    def surely_on(self, entity: str) -> bool:
        return self.switch(entity) is True and self.pending(entity) != OFF

    def usable(self, entity: str) -> bool:
        """Armed and available, so a call can reach it."""
        observed = self.obs.outputs.get(entity)
        return entity in self.obs.armed and observed is not None and value_of(observed) is not None

    # Valves and loops

    def valve_ready(self, valve: Valve) -> bool:
        """Observed open for its opening time, or confirmed by its readiness sensor."""
        entity = valve.entity
        if self.switch(entity) is not True or self.pending(entity) == OFF:
            return False
        since = self.since(entity)
        if self.state.ready.get(entity) == since:
            return True
        if valve.readiness is not None:
            readiness = self.obs.readiness.get(valve.readiness)
            if readiness is not None and readiness.on is True:
                return True
        return self.reached(since + valve.opening_time)

    def winding_down(self, entity: str, duration: float) -> bool:
        """Observed off for less than ``duration`` after it may have been on.

        That is a valve still closing or the source in its post-run. Only an
        output that may have been on at the last evaluation counts, so outputs
        found off when the Plant starts are not taken for still running.
        """
        return (
            entity in self.state.winding
            and self.switch(entity) is False
            and not self.reached(self.since(entity) + duration)
        )

    def valve_may_pass(self, valve: Valve) -> bool:
        """Possibly passing flow: on, unknown, about to open, or still closing."""
        return self.may_be_on(valve.entity) or self.winding_down(valve.entity, valve.opening_time)

    def ready(self, loop: Loop) -> bool:
        if loop not in self._ready:
            self._ready[loop] = all(self.valve_ready(valve) for valve in loop.valves)
        return self._ready[loop]

    def may_pass(self, loop: Loop) -> bool:
        return all(self.valve_may_pass(valve) for valve in loop.valves)

    def loops_of(self, pump: Pump) -> list[Loop]:
        return self._loops_of[pump.slug]

    # The source and pumps

    def source_may_run(self) -> bool:
        """The source may be requested or in its post-run, so its pumps may run."""
        source = self.plant.source
        if source is None:
            return False
        return self.may_be_on(source.request) or self.winding_down(source.request, source.post_run)

    def pump_may_run(self, pump: Pump) -> bool:
        return self.source_may_run() if pump.switch is None else self.may_be_on(pump.switch)

    # The pipeline

    def run(self) -> tuple[State, Desired, float | None]:
        plant, obs, state, now = self.plant, self.obs, self.state, self.now
        demands, demand_states = self.demands()
        guards = self.guards()
        self.guard_states = guards
        self.idle_times = self.idle_since()
        flowing = self.source_may_run() or any(
            self.pump_may_run(self._pumps[loop.pump]) and self.may_pass(loop)
            for loop in plant.all_loops
        )
        flow_ended = now if state.flowing and not flowing else state.flow_ended
        mode, leaving = self.mode(flowing, flow_ended)
        label = mode if mode is not Mode.OFF else state.last_mode
        active = mode is not Mode.OFF and not leaving
        # A mode the select changed keeps the source for its minimum on time, as the
        # end of demand does; Control equipment off stops it at once.
        winding_down = leaving and not self.forced_off

        blocked_by_guard = {
            loop: mode is Mode.COOL and guards.get(str(loop.ref), GuardState(False, now)).blocked
            for loop in plant.all_loops
        }
        if mode is not Mode.COOL:
            # A guard blocks only cooling; outside it, it only follows its reference.
            for key in [f"{ref}.guard" for ref in guards]:
                self.reasons.pop(key, None)
        # With the Mode select off, the Plant heats only for frost protection.
        plan_demands = (
            demands
            if obs.mode is not Mode.OFF
            else {slug: demand for slug, demand in demands.items() if slug in self.frost}
        )
        plan = _Plan(self, mode, label, active, winding_down, plan_demands, blocked_by_guard)
        outputs = plan.outputs()

        live = obs.control or (state.live and not self.finished())
        ready = {
            valve.entity: self.since(valve.entity)
            for loop in plant.all_loops
            for valve in loop.valves
            if self.valve_ready(valve)
        }
        winding = {
            valve.entity
            for loop in plant.all_loops
            for valve in loop.valves
            if self.valve_may_pass(valve)
        }
        if plant.source is not None and self.source_may_run():
            winding.add(plant.source.request)
        source_changed = now if plan.request != state.source_request else state.source_changed
        next_state = State(
            live=live,
            mode=mode,
            last_mode=plan.label,
            flowing=flowing,
            flow_ended=flow_ended,
            source_request=plan.request,
            source_changed=source_changed,
            demands=demand_states,
            guards=guards,
            overruns=plan.overruns,
            ready=ready,
            winding=frozenset(winding),
            windows_open=frozenset(self.windows_open),
            frost=frozenset(self.frost),
            idle_since=self.idle_times,
            exercise=plan.next_exercise,
        )
        desired = Desired(
            outputs=outputs,
            source_request=plan.request,
            mode=mode,
            reasons=self.reasons,
            demands=demands,
            blocking_sensors=self.blocking_sensors(),
            frost_protection=tuple(self.frost),
            exercise=plan.exercising,
        )
        later = [deadline for deadline in self.deadlines if deadline > now]
        due = min(later) - now + TICK if later else None
        return next_state, desired, due

    def demands(self) -> tuple[dict[str, Demand], dict[str, DemandState]]:
        """Stage 2: aggregate each zone's temperature, evaluate its thermostat, then its windows."""
        obs = self.obs
        demands: dict[str, Demand] = {}
        states: dict[str, DemandState] = {}
        for zone in self.plant.zones:
            values = zone_values(zone, obs.areas, obs.sensors, self.reached)
            temperature = None if values is None else aggregate(values, zone.aggregation)
            state, demand = zone_demand(
                zone,
                obs.thermostats.get(zone.slug),
                temperature,
                self.state.demands.get(zone.slug),
                self.now,
                self.reached,
            )
            state, demand = self.window_inhibit(zone, state, demand)
            # Frost protection overrides the thermostat and an open window alike,
            # and leaves the thermostat's decision underneath as it is.
            frost = self.frost_protection(zone)
            if frost is not None:
                demand = frost
                self.frost.append(zone.slug)
            states[zone.slug], demands[zone.slug] = state, demand
            self.reasons[zone.slug] = f"{'demands' if demand.on else 'idle'}: {demand.reason}"
        return demands, states

    def window_inhibit(
        self, zone: Zone, state: DemandState, demand: Demand
    ) -> tuple[DemandState, Demand]:
        """Turn a zone's demand off while a window is open, after its thermostat decided.

        The thermostat's own decision goes on underneath, so its hysteresis and
        minimum times are the same when the window closes. A decision that is on
        then counts its minimum on time from the end of the inhibit, because the
        zone's valves have closed meanwhile, so it cannot end as soon as it resumes.
        """
        was_open = zone.slug in self.state.windows_open
        if self.window_open(zone, was_open):
            self.windows_open.add(zone.slug)
            return state, Demand(demand.mode, False, "window open")
        if was_open and state.on:
            state = DemandState(state.mode, True, self.now)
        return state, demand

    def window_open(self, zone: Zone, was_open: bool) -> bool:
        """Whether a zone's windows turn its demand off.

        They do once a window has read open for the open delay, and stop once
        every window has read closed for the close delay. An unavailable or
        unknown window reads closed, so a lost sensor never stops heating.
        """
        windows = [self.obs.readiness.get(entity) for entity in zone.windows]
        if not was_open:
            return any(
                window is not None
                and window.on is True
                and self.reached(window.since + zone.window_open_delay)
                for window in windows
            )
        return not all(
            window is None
            or (window.on is not True and self.reached(window.since + zone.window_close_delay))
            for window in windows
        )

    def frost_protection(self, zone: Zone) -> Demand | None:
        """Frost protection's demand, which overrides the thermostat's, or None.

        It heats a zone whose coldest usable reading is below the frost protection
        temperature, whatever its thermostat and the Mode select say, but never
        while the Plant runs or is asked to run cool: a zone that cold in cooling
        has a broken sensor.
        """
        frost = self.plant.frost_protection
        if frost is None or Mode.COOL in (self.obs.mode, self.state.mode):
            return None
        obs = self.obs
        coldest = coldest_temperature(zone, obs.areas, obs.sensors, self.reached)
        return frost_demand(frost, coldest, zone.slug in self.state.frost)

    def idle_since(self) -> dict[str, float | None]:
        """Since when each switched pump and valve has not been seen on, or None while on."""
        plant, previous = self.plant, self.state.idle_since
        entities = [pump.switch for pump in plant.pumps if pump.switch is not None]
        entities.extend(valve.entity for loop in plant.all_loops for valve in loop.valves)
        idle: dict[str, float | None] = {}
        for entity in entities:
            if self.switch(entity) is True:
                idle[entity] = None
            elif entity not in previous:
                # A new output's clock starts now, so a new Plant is not overdue.
                idle[entity] = self.now
            else:
                last = previous[entity]
                idle[entity] = self.since(entity) if last is None else last
        return idle

    def blocking_sensors(self) -> dict[str, tuple[str, ...]]:
        """Each zone's required sensors that are not usable, among the readings it needs.

        A digital thermostat needs its zone's temperature, and a condensation
        guard needs the temperature and humidity of each zone whose dew point it reads.
        """
        plant, obs = self.plant, self.obs
        guarded = {
            zone.slug
            for loop in plant.all_loops
            if loop.cools
            for zone in plant.dew_point_zones(loop)
        }
        blocking: dict[str, tuple[str, ...]] = {}
        for zone in plant.zones:
            needs = [False] if isinstance(zone.thermostat, DigitalThermostat) else []
            if zone.slug in guarded:
                needs = [False, True]
            entities = [
                entity
                for humidity in needs
                for entity in unusable_sensors(
                    zone, obs.areas, obs.sensors, self.reached, humidity=humidity
                )
            ]
            if entities:
                blocking[zone.slug] = tuple(dict.fromkeys(entities))
        return blocking

    def guards(self) -> dict[str, GuardState]:
        """The condensation guard of every loop that cools."""
        guards: dict[str, GuardState] = {}
        for loop in self.plant.all_loops:
            if loop.cools:
                guards[str(loop.ref)] = self.guard(loop)
        return guards

    def guard(self, loop: Loop) -> GuardState:
        """Block at once on any of the guard's checks; release once all of them release.

        The dew point check comes first and always applies. The condensation
        switches, the surface minimum, and the humidity cutoff only add to it.
        """
        now = self.now
        checks = [
            self.dew_point_check(loop),
            *self.switch_checks(loop),
            *self.surface_checks(loop),
            *self.humidity_checks(loop),
        ]
        previous = self.state.guards.get(str(loop.ref))
        blocking = any(check.blocks for check in checks)
        releasing = all(check.releases for check in checks)
        if blocking:
            reason = "; ".join(check.reason for check in checks if check.blocks)
        elif releasing:
            reason = f"{checks[0].reason}, held for its minimum blocked time"
        else:
            reason = "; ".join(check.reason for check in checks if not check.releases)
        if previous is None or not previous.blocked:
            guard = GuardState(blocking, now) if previous is None or blocking else previous
        elif releasing and self.reached(previous.since + GUARD_MIN_BLOCKED):
            guard = GuardState(False, now)
        else:
            guard = previous
        if guard.blocked:
            self.reasons[f"{loop.ref}.guard"] = f"condensation guard blocks: {reason}"
        return guard

    def dew_point_check(self, loop: Loop) -> _Check:
        """Block below the worst-case dew point plus the margin; release 1 K above it."""
        plant, obs = self.plant, self.obs
        pump = self._pumps[loop.pump]
        references = [e for e in (pump.supply_temperature, loop.surface_temperature) if e]
        values = [
            fresh(obs.sensors.get(entity), GUARD_REFERENCE_MAX_AGE, self.reached)
            for entity in references
        ]
        points = [
            worst_dew_point(zone, obs.areas, obs.sensors, self.reached)
            for zone in plant.dew_point_zones(loop)
        ]
        usable = [value for value in values if value is not None]
        known = [point for point in points if point is not None]
        if not usable or len(usable) < len(values) or not known or len(known) < len(points):
            return _Check(True, False, "no usable condensation reference or dew point")
        threshold = max(known) + CONDENSATION_MARGIN
        reference = min(usable)
        if reference < threshold:
            return _Check(True, False, f"reference {reference:.1f} °C below {threshold:.1f} °C")
        if reference >= threshold + GUARD_RELEASE:
            return _Check(False, True, f"reference {reference:.1f} °C")
        return _Check(
            False,
            False,
            f"reference {reference:.1f} °C, releases at {threshold + GUARD_RELEASE:.1f} °C",
        )

    def switch_checks(self, loop: Loop) -> Iterator[_Check]:
        """Block at once while a condensation switch reads on or is unavailable.

        The loop's own switch and its pump's switch cover it, and each releases
        once it has read off for the guard's minimum blocked time.
        """
        pump = self._pumps[loop.pump]
        for entity in (pump.condensation_switch, loop.condensation_switch):
            if entity is None:
                continue
            switch = self.obs.readiness.get(entity)
            if switch is None or switch.on is None:
                yield _Check(True, False, f"condensation switch {entity} unavailable")
            elif switch.on:
                yield _Check(True, False, f"condensation switch {entity} on")
            elif self.reached(switch.since + GUARD_MIN_BLOCKED):
                yield _Check(False, True, f"condensation switch {entity} off")
            else:
                yield _Check(
                    False,
                    False,
                    f"condensation switch {entity} off for less than {GUARD_MIN_BLOCKED:.0f} s",
                )

    def surface_checks(self, loop: Loop) -> Iterator[_Check]:
        """Block below the loop's surface minimum; release 1 K above it.

        Without a usable surface reading the dew point check already blocks.
        """
        minimum = loop.surface_minimum
        if loop.surface_temperature is None or minimum is None:
            return
        surface = fresh(
            self.obs.sensors.get(loop.surface_temperature), GUARD_REFERENCE_MAX_AGE, self.reached
        )
        if surface is None:
            return
        if surface < minimum:
            yield _Check(True, False, f"surface {surface:.1f} °C below its minimum {minimum:g} °C")
        elif surface >= minimum + GUARD_RELEASE:
            yield _Check(False, True, f"surface {surface:.1f} °C")
        else:
            yield _Check(
                False,
                False,
                f"surface {surface:.1f} °C, releases at {minimum + GUARD_RELEASE:g} °C",
            )

    def humidity_checks(self, loop: Loop) -> Iterator[_Check]:
        """Block while a zone whose dew point guards the loop is above its humidity limit.

        It releases 5 points below the limit. Without a usable humidity the dew
        point check already blocks.
        """
        obs = self.obs
        for zone in self.plant.dew_point_zones(loop):
            limit = zone.max_humidity
            if limit is None:
                continue
            values = zone_values(zone, obs.areas, obs.sensors, self.reached, humidity=True)
            if values is None:
                continue
            humidity = max(values)
            where = f"humidity {humidity:.1f} % in zone {zone.slug}"
            if humidity > limit:
                yield _Check(True, False, f"{where} above {limit:g} %")
            elif humidity <= limit - HUMIDITY_RELEASE:
                yield _Check(False, True, where)
            else:
                yield _Check(False, False, f"{where}, releases at {limit - HUMIDITY_RELEASE:g} %")

    @property
    def forced_off(self) -> bool:
        """Control equipment is off while outputs are still commanded: the off sequence."""
        return not self.obs.control and self.state.live

    def requested(self) -> Mode:
        """The mode asked for: the Mode select's, or heat for frost protection while it is off.

        Control equipment turned off asks for off, so its off sequence runs and
        then nothing, frost protection included.
        """
        if self.forced_off:
            return Mode.OFF
        if self.obs.mode is Mode.OFF and self.frost:
            return Mode.HEAT
        return self.obs.mode

    def mode(self, flowing: bool, flow_ended: float | None) -> tuple[Mode, bool]:
        """Stage 3: the mode the outputs run in, and whether it is being left."""
        state = self.state
        requested = self.requested()
        mode = state.mode
        if mode is not Mode.OFF and requested is not mode:
            if flowing:
                self.reasons["mode"] = f"stopping {mode.value} before {requested.value}"
                return mode, True
            mode = Mode.OFF
        if mode is Mode.OFF and requested is not Mode.OFF:
            fresh_start = (
                state.last_mode is Mode.OFF and state.flow_ended is None and not state.flowing
            )
            if (
                state.last_mode is requested
                or fresh_start
                or (
                    not flowing
                    and (flow_ended is None or self.reached(flow_ended + self.plant.mode_dwell))
                )
            ):
                mode = requested
            else:
                self.reasons["mode"] = f"waiting for the mode dwell before {requested.value}"
        return mode, False

    def finished(self) -> bool:
        """The off-mode sequence is over: armed outputs are off and nothing may still act."""
        for entity, role in self.plant.outputs().items():
            if entity not in self.obs.armed:
                continue
            if self.pending(entity) is not None:
                return False
            if role is not OutputRole.SOURCE_MODE and self.switch(entity) is not False:
                return False
        source = self.plant.source
        return (
            source is None or self.switch(source.request) is not False or not self.source_may_run()
        )


class _Plan:
    """Stages 4 to 9: wanted loops, readiness, min flow, valves, pumps, and the source."""

    def __init__(
        self,
        ev: _Evaluation,
        mode: Mode,
        label: Mode,
        active: bool,
        winding_down: bool,
        demands: Mapping[str, Demand],
        guard_blocked: Mapping[Loop, bool],
    ) -> None:
        self.ev, self.mode, self.label, self.active = ev, mode, label, active
        # The mode is being left for another the select asked for, and a request
        # already on may be held for its minimum on time.
        self.winding_down = winding_down
        self.demands = demands
        self.guard_blocked = guard_blocked
        self.plant = ev.plant
        self.request = False
        self.overruns: dict[str, float] = {}

    def outputs(self) -> dict[str, OutputTarget]:
        ev, plant = self.ev, self.plant
        source = plant.source
        self.surely_requested = source is not None and ev.surely_on(source.request)
        self.wanted = {loop for loop in plant.all_loops if self.is_wanted(loop)}
        self.exercise()
        self.blocked = {pump.slug: self.pump_blocked(pump) for pump in plant.pumps}
        self.source_wanted = (
            self.active
            and source is not None
            and ev.usable(source.request)
            and any(self.calls_source(loop) and not self.blocked[loop.pump] for loop in self.wanted)
        )
        self.paths = {pump.slug: self.path(pump) for pump in plant.pumps}
        self.pumps_on = {
            pump.slug: self.pump_on(pump) for pump in plant.pumps if pump.switch is not None
        }
        self.request = self.source_request()
        held = self.hold_for_source()

        outputs: dict[str, OutputTarget] = {}
        if source is not None:
            outputs[source.request] = SwitchTarget(self.request)
            option = None if source.mode is None else source.mode.option(self.mode)
            if option is not None and source.mode is not None:
                outputs[source.mode.entity] = OptionTarget(option)
        for pump in plant.pumps:
            if pump.switch is not None:
                outputs[pump.switch] = SwitchTarget(self.pumps_on[pump.slug])
        open_loops = {loop for loops in self.paths.values() for loop in loops} | held
        for loop in plant.all_loops:
            for valve in loop.valves:
                outputs[valve.entity] = SwitchTarget(loop in open_loops)
            if loop in open_loops:
                ev.reasons.setdefault(str(loop.ref), "held open as a path")
        return outputs

    # Stage 4: wanted loops

    def is_wanted(self, loop: Loop) -> bool:
        ev, key = self.ev, str(loop.ref)
        if not self.active or self.mode not in loop.modes:
            return False
        match loop.runs.kind:
            case RunKind.ZONE:
                assert loop.zone is not None
                wants = self.zone_demands(loop.zone)
            case RunKind.WITH_ZONES:
                wants = any(self.zone_demands(zone) for zone in loop.runs.zones)
            case _:
                wants = self.surely_requested
        if not wants:
            return False
        missing = [entity for entity in self.needs(loop) if not ev.usable(entity)]
        if missing:
            ev.reasons[key] = f"dropped: {', '.join(missing)} unarmed or unavailable"
            return False
        if self.guard_blocked[loop]:
            ev.reasons[key] = "dropped: condensation guard blocks"
            return False
        ev.reasons[key] = "wanted"
        return True

    def calls_source(self, loop: Loop) -> bool:
        """A wanted loop asks the source for heat, unless it runs with it or is exercised."""
        return loop.runs.kind is not RunKind.WITH_SOURCE and loop not in self.exercised

    def zone_demands(self, slug: str) -> bool:
        demand = self.demands.get(slug)
        return demand is not None and demand.on and demand.mode is self.mode

    def needs(self, loop: Loop) -> Iterable[str]:
        yield from (valve.entity for valve in loop.valves)
        pump = self.ev._pumps[loop.pump]
        if pump.switch is not None:
            yield pump.switch
        elif self.plant.source is not None:
            yield self.plant.source.request

    def pump_blocked(self, pump: Pump) -> bool:
        """A pump must not run when a loop on it would flow where it must not.

        That is a loop that does not run in the mode, or whose condensation guard
        blocks, and that is valveless or whose valves may pass. A pump already
        running may go on while a blocked loop closes, since stopping it would
        not end that flow sooner.
        """
        ev, mode = self.ev, self.label
        if mode is Mode.OFF:
            return True
        source = self.plant.source
        stop = pump.switch or (source.request if source is not None else None)
        running = stop is not None and ev.surely_on(stop)
        for loop in ev.loops_of(pump):
            if mode not in loop.modes:
                if not loop.valves or ev.may_pass(loop):
                    return True
            elif self.guard_blocked[loop] and (
                not loop.valves or (not running and ev.may_pass(loop))
            ):
                return True
        return False

    # Stages 5 to 7: readiness, min flow, and the valves each pump needs open

    def path(self, pump: Pump) -> set[Loop]:
        """The loops to keep open for a pump: wanted, held as its last path, or min flow."""
        ev = self.ev
        loops = ev.loops_of(pump)
        wanted = [loop for loop in loops if loop in self.wanted]
        path = set(wanted)
        # A valveless loop is always open, and a ready wanted loop is path enough.
        if any(not loop.valves for loop in loops) or any(ev.ready(loop) for loop in wanted):
            return path
        held: list[Loop] = []
        may_run = ev.pump_may_run(pump)
        if pump.min_flow is MinFlow.PATH and may_run:
            ready = [loop for loop in loops if loop.valves and ev.ready(loop)]
            held = ready or [loop for loop in loops if loop.valves and ev.may_pass(loop)]
            path.update(held)
        if (
            pump.driven_by_source
            and pump.min_flow is MinFlow.PATH
            and (may_run or self.source_wanted)
            and not wanted
            and not any(ev.ready(loop) for loop in held)
        ):
            for ref in pump.min_flow_loops:
                loop = self.plant.loop(ref)
                if (
                    self.label in loop.modes
                    and (may_run or not self.guard_blocked[loop])
                    and all(ev.usable(valve.entity) for valve in loop.valves)
                ):
                    path.add(loop)
                    ev.reasons[str(loop.ref)] = "min-flow path"
        return path

    def carries(self, pump: Pump, loop: Loop) -> bool:
        """The loop is an open path for its pump that stays open."""
        return self.ev.ready(loop) and (not loop.valves or loop in self.paths[pump.slug])

    def path_ready(self, pump: Pump) -> bool:
        """The pump has an open path of the mode whose guard permits."""
        return any(
            self.carries(pump, loop) and self.label in loop.modes and not self.guard_blocked[loop]
            for loop in self.ev.loops_of(pump)
        )

    # Stage 8: switched pumps

    def pump_on(self, pump: Pump) -> bool:
        ev, now = self.ev, self.ev.now
        assert pump.switch is not None
        if self.blocked[pump.slug] or self.exercise_stops(pump):
            return False
        if any(ev.ready(loop) for loop in self.paths[pump.slug] if loop in self.wanted):
            return True
        started = ev.state.overruns.get(pump.slug)
        if self.label is not Mode.HEAT or pump.overrun <= 0 or ev.switch(pump.switch) is False:
            return False
        if started is None:
            if ev.switch(pump.switch) is not True:
                return False
            started = now
        self.overruns[pump.slug] = started
        if ev.reached(started + pump.overrun):
            return False
        ev.reasons[pump.switch] = "overrun"
        return pump.min_flow is MinFlow.GUARANTEED or any(
            self.carries(pump, loop) for loop in ev.loops_of(pump)
        )

    # Stage 9: the source

    def qualifies(self, loop: Loop) -> bool:
        """A loop the source may run for: ready in the mode with its pump running."""
        pump = self.ev._pumps[loop.pump]
        if (
            self.mode not in loop.modes
            or self.guard_blocked[loop]
            or self.blocked[pump.slug]
            or not self.ev.ready(loop)
        ):
            return False
        if pump.switch is None:
            return self.carries(pump, loop)
        return self.pumps_on[pump.slug] and self.ev.surely_on(pump.switch)

    def source_request(self) -> bool:
        ev, source = self.ev, self.plant.source
        if source is None:
            return False
        reasons = ev.reasons
        if not (self.active or self.winding_down) or not ev.usable(source.request):
            reasons["source"] = "off"
            return False
        driven = [pump for pump in self.plant.pumps if pump.driven_by_source]
        if source.mode is not None:
            target = OptionTarget(source.mode.option(self.mode) or "")
            select = source.mode.entity
            if not satisfies(ev.obs.outputs.get(select), target) or ev.pending(select):
                reasons["source"] = "waiting for the source mode"
                return False
        if any(self.blocked[pump.slug] for pump in driven):
            wrong_mode = any(
                self.label not in loop.modes and (not loop.valves or ev.may_pass(loop))
                for pump in driven
                for loop in ev.loops_of(pump)
            )
            reasons["source"] = (
                "a source-driven pump would run a loop in the wrong mode"
                if wrong_mode
                else "a condensation guard blocks a loop the source drives"
            )
            return False
        if any(
            self.guard_blocked[loop] and (not loop.valves or loop in self.paths[pump.slug])
            for pump in driven
            for loop in ev.loops_of(pump)
        ):
            reasons["source"] = "a condensation guard blocks a loop the source drives"
            return False
        if any(pump.min_flow is MinFlow.PATH and not self.path_ready(pump) for pump in driven):
            reasons["source"] = "waiting for a path for every source-driven pump"
            return False
        qualifying = [loop for loop in self.plant.all_loops if self.qualifies(loop)]
        demanded = any(loop in self.wanted and self.calls_source(loop) for loop in qualifying)
        state = ev.state
        if state.source_request:
            changed = state.source_changed if state.source_changed is not None else ev.now
            if qualifying and (demanded or not ev.reached(changed + source.min_on)):
                reasons["source"] = "requested" if demanded else "held for its minimum on time"
                return True
            reasons["source"] = "released"
            return False
        if not demanded:
            reasons["source"] = "no ready loop calls"
            return False
        if state.source_changed is not None and not ev.reached(
            state.source_changed + source.min_off
        ):
            reasons["source"] = "held off for its minimum off time"
            return False
        reasons["source"] = "requested"
        return True

    def hold_for_source(self) -> set[Loop]:
        """Keep a running pump and its path while a released request may still be on."""
        ev, source = self.ev, self.plant.source
        if source is None or self.request or not ev.may_be_on(source.request):
            return set()
        label = self.label
        if any(
            pump.driven_by_source and not self.blocked[pump.slug] and self.path_ready(pump)
            for pump in self.plant.pumps
        ):
            return set()
        held: set[Loop] = set()
        for pump in self.plant.pumps:
            if pump.switch is None or self.blocked[pump.slug] or not ev.surely_on(pump.switch):
                continue
            loops = [
                loop
                for loop in ev.loops_of(pump)
                if ev.ready(loop) and label in loop.modes and not self.guard_blocked[loop]
            ]
            if loops:
                self.pumps_on[pump.slug] = True
                ev.reasons[pump.switch] = "held until the source request is off"
                held.update(loops)
        return held

    # The exercise: an idle pump or valve runs now and then, so it does not seize

    def exercise(self) -> None:
        """Choose the loops to exercise while the Plant is idle, and the exercise's next state.

        One pump is exercised at a time, once its switch or a valve of its loops
        has not been seen on for the exercise interval. Its loops that may carry
        the mode that labels any flow open, and once they are ready its switched
        pump runs for the exercise's run time; the pump then stops without
        overrun, and the valves close once it is seen off, as at the end of
        demand. A source-driven pump is never commanded, so its loops only open
        until they are ready. An exercise never asks the source for heat, and it
        yields at once to any wanted loop.
        """
        ev = self.ev
        self.exercised: set[Loop] = set()
        self.exercise_runs = False
        self.next_exercise: ExerciseState | None = None
        settings = self.plant.exercise
        idle = self.exercise_idle()
        # A Plant that never ran a mode labels its exercise heat.
        unlabelled = self.label is Mode.OFF
        if unlabelled:
            self.label = Mode.HEAT
        previous = ev.state.exercise
        pump = None if previous is None else ev._pumps.get(previous.pump)
        if pump is not None and previous is not None:
            if idle and settings is not None and not previous.done:
                loops, runs = self.exercise_loops(pump)
                started = previous.started
                if runs and started is None and pump.switch and ev.surely_on(pump.switch):
                    started = ev.now
                ran = not runs or (started is not None and ev.reached(started + settings.run))
                if loops and not (ran and all(ev.ready(loop) for loop in loops)):
                    self.begin_exercise(pump, loops, runs, started)
                    return
            if (
                pump.switch is not None
                and ev.may_be_on(pump.switch)
                and not any(loop in self.wanted for loop in ev.loops_of(pump))
            ):
                self.next_exercise = ExerciseState(pump.slug, previous.started, done=True)
                ev.reasons[pump.switch] = "exercise over"
                return
        # The previous exercise is over, so the next pump that is due may start.
        if idle and settings is not None:
            for pump in self.plant.pumps:
                loops, runs = self.exercise_loops(pump)
                if loops and (
                    (runs and pump.switch is not None and self.due(pump.switch, settings))
                    or any(
                        self.due(valve.entity, settings) for loop in loops for valve in loop.valves
                    )
                ):
                    self.begin_exercise(pump, loops, runs, None)
                    return
        if unlabelled:
            self.label = Mode.OFF

    def exercise_idle(self) -> bool:
        """Nothing else runs: no loop is wanted, the source is at rest, and no other pump runs."""
        ev = self.ev
        if ev.forced_off or self.wanted or "mode" in ev.reasons:
            return False
        if ev.state.source_request or ev.source_may_run():
            return False
        exercised = ev.state.exercise.pump if ev.state.exercise is not None else None
        return not any(
            pump.switch is not None
            and pump.slug != exercised
            and (ev.switch(pump.switch) is True or ev.pending(pump.switch) == ON)
            for pump in self.plant.pumps
        )

    def exercise_loops(self, pump: Pump) -> tuple[list[Loop], bool]:
        """The loops of a pump to open in an exercise, and whether its switched pump runs.

        A loop opens when it runs in the mode that labels the flow, its valves are
        armed and available, and in cooling its condensation guard permits. The
        pump runs only when it is armed and available and no other loop of it
        may pass flow, and without it only loops with valves are exercised.
        """
        ev, label = self.ev, self.label

        def carries(loop: Loop) -> bool:
            # After cooling the running mode is off, where ``guard_blocked`` never
            # blocks, so the exercise reads the guard itself, with all its checks.
            guard = ev.guard_states.get(str(loop.ref))
            blocked = label is Mode.COOL and (guard is None or guard.blocked)
            return label in loop.modes and not blocked

        loops = ev.loops_of(pump)
        chosen = [
            loop
            for loop in loops
            if carries(loop) and all(ev.usable(valve.entity) for valve in loop.valves)
        ]
        runs = (
            pump.switch is not None
            and ev.usable(pump.switch)
            and not self.pump_blocked(pump)
            and not any(
                not carries(loop) and (not loop.valves or ev.may_pass(loop)) for loop in loops
            )
        )
        if not runs:
            chosen = [loop for loop in chosen if loop.valves]
        return chosen, runs

    def due(self, entity: str, settings: Exercise) -> bool:
        """An output has not been seen on for the exercise interval."""
        since = self.ev.idle_times.get(entity)
        return since is not None and self.ev.reached(since + settings.interval)

    def begin_exercise(
        self, pump: Pump, loops: list[Loop], runs: bool, started: float | None
    ) -> None:
        """Run an exercise now: its loops are wanted, and its pump runs only if ``runs``."""
        ev = self.ev
        self.exercised = set(loops)
        self.exercise_runs = runs
        self.wanted |= self.exercised
        self.next_exercise = ExerciseState(pump.slug, started)
        for loop in loops:
            ev.reasons[str(loop.ref)] = "exercise"
        if runs and pump.switch is not None:
            ev.reasons[pump.switch] = "exercise"

    @property
    def exercising(self) -> str | None:
        """The slug of the pump whose exercise runs now, not one that is stopping."""
        exercise = self.next_exercise
        return None if exercise is None or exercise.done else exercise.pump

    def exercise_stops(self, pump: Pump) -> bool:
        """The pump belongs to an exercise that must not run it, or that is over."""
        exercise = self.next_exercise
        return (
            exercise is not None
            and exercise.pump == pump.slug
            and (exercise.done or not self.exercise_runs)
        )
