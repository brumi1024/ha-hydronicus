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

from collections.abc import Iterable, Mapping
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
    fresh,
    worst_dew_point,
    zone_demand,
    zone_values,
)
from .model import (
    DEFAULT_MAX_AGE,
    Demand,
    Desired,
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
    ValueTarget,
    Valve,
)

__all__ = [
    "CALL_TIMEOUT",
    "CONDENSATION_MARGIN",
    "GUARD_MIN_BLOCKED",
    "GUARD_RELEASE",
    "TICK",
    "AreaSensors",
    "DemandState",
    "DigitalThermostatState",
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
    "ValueState",
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
    # change to or from unavailable.
    since: float


@dataclass(frozen=True, slots=True)
class OptionState:
    """A select as observed."""

    option: str | None
    since: float


@dataclass(frozen=True, slots=True)
class ValueState:
    """A number as observed; used by the setpoint strategy from iteration 2."""

    value: float | None
    since: float


type OutputState = SwitchState | OptionState | ValueState


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
    # Every valve readiness binary sensor.
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
        case SwitchTarget(on=on), SwitchState(on=observed):
            return observed is on
        case OptionTarget(option=option), OptionState(option=observed):
            return observed == option
        case ValueTarget(value=value), ValueState(value=observed):
            return observed == value
        case _:
            return False


def value_of(state: OutputState) -> bool | str | float | None:
    """The observed value of an output, None while it is unavailable."""
    match state:
        case SwitchState(on=on):
            return on
        case OptionState(option=option):
            return option
        case ValueState(value=value):
            return value


# State


@dataclass(frozen=True, slots=True)
class GuardState:
    """A cooling loop's condensation guard and when it last changed, for its minimum time."""

    blocked: bool
    since: float


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
                slug: DemandState(Mode(value["mode"]), bool(value["on"]), float(value["since"]))
                for slug, value in data.get("demands", {}).items()
            },
            guards={
                ref: GuardState(bool(value["blocked"]), float(value["since"]))
                for ref, value in data.get("guards", {}).items()
            },
            overruns={slug: float(value) for slug, value in data.get("overruns", {}).items()},
            ready={entity: float(value) for entity, value in data.get("ready", {}).items()},
            winding=frozenset(str(entity) for entity in data.get("winding", ())),
        )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


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
        observed = self.obs.outputs.get(entity)
        return observed.on if isinstance(observed, SwitchState) else None

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
        flowing = self.source_may_run() or any(
            self.pump_may_run(self._pumps[loop.pump]) and self.may_pass(loop)
            for loop in plant.all_loops
        )
        flow_ended = now if state.flowing and not flowing else state.flow_ended
        mode, leaving = self.mode(flowing, flow_ended)
        label = mode if mode is not Mode.OFF else state.last_mode
        active = mode is not Mode.OFF and not leaving

        blocked_by_guard = {
            loop: mode is Mode.COOL and guards.get(str(loop.ref), GuardState(False, now)).blocked
            for loop in plant.all_loops
        }
        plan = _Plan(self, mode, label, active, demands, blocked_by_guard)
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
            last_mode=label,
            flowing=flowing,
            flow_ended=flow_ended,
            source_request=plan.request,
            source_changed=source_changed,
            demands=demand_states,
            guards=guards,
            overruns=plan.overruns,
            ready=ready,
            winding=frozenset(winding),
        )
        desired = Desired(
            outputs=outputs,
            source_request=plan.request,
            mode=mode,
            flow_setpoint=None,
            reasons=self.reasons,
            demands=demands,
        )
        later = [deadline for deadline in self.deadlines if deadline > now]
        due = min(later) - now + TICK if later else None
        return next_state, desired, due

    def demands(self) -> tuple[dict[str, Demand], dict[str, DemandState]]:
        """Stage 2: aggregate each zone's temperature and evaluate its thermostat."""
        obs = self.obs
        demands: dict[str, Demand] = {}
        states: dict[str, DemandState] = {}
        for zone in self.plant.zones:
            values = zone_values(zone, obs.areas, obs.sensors, self.reached)
            temperature = None if values is None else aggregate(values, zone.aggregation)
            states[zone.slug], demands[zone.slug] = zone_demand(
                zone,
                obs.thermostats.get(zone.slug),
                temperature,
                self.state.demands.get(zone.slug),
                self.now,
                self.reached,
            )
            demand = demands[zone.slug]
            self.reasons[zone.slug] = f"{'demands' if demand.on else 'idle'}: {demand.reason}"
        return demands, states

    def guards(self) -> dict[str, GuardState]:
        """The condensation guard of every loop that cools."""
        guards: dict[str, GuardState] = {}
        for loop in self.plant.all_loops:
            if loop.cools:
                guards[str(loop.ref)] = self.guard(loop)
        return guards

    def guard(self, loop: Loop) -> GuardState:
        """Block below the worst-case dew point plus the margin; release 1 K above it."""
        plant, obs, now = self.plant, self.obs, self.now
        pump = self._pumps[loop.pump]
        references = [e for e in (pump.supply_temperature, loop.surface_temperature) if e]
        values = [fresh(obs.sensors.get(e), DEFAULT_MAX_AGE, self.reached) for e in references]
        zones = [plant.zone(loop.zone)] if loop.zone is not None else list(plant.zones)
        points = [worst_dew_point(zone, obs.areas, obs.sensors, self.reached) for zone in zones]
        usable = [value for value in values if value is not None]
        known = [point for point in points if point is not None]
        previous = self.state.guards.get(str(loop.ref))
        if not usable or len(usable) < len(values) or not known or len(known) < len(points):
            blocking, releasing = True, False
            reason = "no usable condensation reference or dew point"
        else:
            threshold = max(known) + CONDENSATION_MARGIN
            blocking = min(usable) < threshold
            releasing = min(usable) >= threshold + GUARD_RELEASE
            reason = f"reference {min(usable):.1f} °C against {threshold:.1f} °C"
        if previous is None or not previous.blocked:
            guard = GuardState(blocking, now) if previous is None or blocking else previous
        elif releasing and self.reached(previous.since + GUARD_MIN_BLOCKED):
            guard = GuardState(False, now)
        else:
            guard = previous
        if guard.blocked:
            self.reasons[f"{loop.ref}.guard"] = f"condensation guard blocks: {reason}"
        return guard

    def mode(self, flowing: bool, flow_ended: float | None) -> tuple[Mode, bool]:
        """Stage 3: the mode the outputs run in, and whether it is being left."""
        state, obs = self.state, self.obs
        requested = obs.mode if obs.control or not state.live else Mode.OFF
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
        demands: Mapping[str, Demand],
        guard_blocked: Mapping[Loop, bool],
    ) -> None:
        self.ev, self.mode, self.label, self.active = ev, mode, label, active
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
        self.blocked = {pump.slug: self.pump_blocked(pump) for pump in plant.pumps}
        self.source_wanted = (
            self.active
            and source is not None
            and ev.usable(source.request)
            and any(
                loop.runs.kind is not RunKind.WITH_SOURCE and not self.blocked[loop.pump]
                for loop in self.wanted
            )
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
        if self.blocked[pump.slug]:
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
        if not self.active or not ev.usable(source.request):
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
            reasons["source"] = "a source-driven pump would run a loop in the wrong mode"
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
        demanded = any(
            loop in self.wanted and loop.runs.kind is not RunKind.WITH_SOURCE for loop in qualifying
        )
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
