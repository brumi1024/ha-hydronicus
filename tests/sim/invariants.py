"""The plan's invariants 1 to 8, checked on the simulated physical state.

Each check reads the world, not the controller's belief, with two exceptions
that the controller declares: the mode label of a flow is the last heat or cool
``Desired.mode`` before the flow started, and the Repairs are what
``reconcile()`` reports. The condensation guard is judged on the sensor values
the controller could see, since no controller can act on a reading it never
received.

Exemptions and bounds, all in physical seconds:

- A spontaneous physical change, such as a relay turning off by itself, exempts
  invariant 3 for ``SPONTANEOUS_GRACE`` after it; invariants 2 and 4 need no
  exemption because a valve closing by itself still passes flow for its travel
  time, which is when the controller must have reacted. When the controller may
  command neither the pump's stop output nor the valve that closed by itself,
  because they are unarmed, unavailable, or the Plant is in Dry run, it cannot
  react without breaking invariant 1, and invariants 2 and 4 are exempt for that
  pump until one reaction, ``SPONTANEOUS_GRACE``, after one of them could be
  commanded again.
- Invariant 3 is exempt while the controller desires the source request off
  but cannot get it off: the request has been unarmed, unavailable, or under a
  call fault within the last ``CALL_TIMEOUT + LATENCY``, or an off call to it
  has failed since it was last on. Keeping a pump running for the source then
  would carry water through a loop the controller is stopping, such as a
  cooling loop whose condensation guard blocks, against invariant 6.
- Invariant 6 allows a cooling loop to flow on while its guard blocks for one
  call, a valve's travel, and a second of slack, and not at all otherwise,
  except a loop of a source-driven pump during the source's post-run, and
  except while an output that stops the loop (its valves, its pump's switch,
  the source request) has been unarmed, unavailable, or failing calls since
  the guard blocked, because then no controller can stop the flow. While no
  evaluation can run, because the event loop is blocked or the runtime is down,
  no controller can react either, so the bound counts only the time in which
  evaluations can run.
- Invariant 7 requires an output whose target is unmet after
  ``REPAIR_AFTER`` failed calls to be reported ``REPAIR_GRACE`` after the last
  one, and every armed output to match its target once the trace has settled.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from hydronicus_core.model import (
    DEFAULT_MAX_AGE,
    Desired,
    DigitalThermostat,
    Loop,
    LoopRef,
    MinFlow,
    Mode,
    OptionTarget,
    OutputRole,
    OutputTarget,
    Plant,
    Pump,
    SwitchTarget,
    Zone,
)
from hydronicus_core.reconcile import CALL_TIMEOUT, REPAIR_AFTER
from hydronicus_core.step import (
    CONDENSATION_MARGIN,
    DigitalThermostatState,
    ExternalThermostatState,
)

from tests.sim.world import EPSILON, LATENCY, WALL_BASE, Call, World

if TYPE_CHECKING:
    from collections.abc import Callable

SPONTANEOUS_GRACE: Final = 2 * CALL_TIMEOUT + LATENCY
REPAIR_GRACE: Final = 60.0
# Seconds a reading may be older than its max_age before the oracle calls it stale.
STALE_SLACK: Final = 1.0
# Kelvin the oracle allows below the guard's threshold, for rounding.
GUARD_TOLERANCE: Final = 0.05
# Kelvin below target, beyond the start delta, at which a zone surely demands heat.
DEMAND_MARGIN: Final = 0.2

_DEW_POINT_A: Final = 17.62
_DEW_POINT_B: Final = 243.12


class InvariantViolation(AssertionError):
    """A plan invariant does not hold on the simulated physical state."""

    def __init__(self, number: int | str, t: float, message: str) -> None:
        self.number = number
        self.t = t
        super().__init__(f"Invariant {number} at t={t:.1f}s: {message}")


def dew_point(temperature: float, humidity: float) -> float | None:
    """The Magnus dew point, independent of the core's own implementation."""
    if humidity <= 0.0:
        return None
    gamma = math.log(humidity / 100.0) + _DEW_POINT_A * temperature / (_DEW_POINT_B + temperature)
    return _DEW_POINT_B * gamma / (_DEW_POINT_A - gamma)


@dataclass(slots=True)
class Flow:
    """A loop flowing physically, labeled with the mode it started in."""

    ref: LoopRef
    label: Mode
    start: float
    end: float | None = None


@dataclass(slots=True)
class Unmet:
    """An armed output whose observed state differs from its desired target."""

    target: OutputTarget
    since: float
    failed: int = 0
    last_failed: float = 0.0


class Checker:
    """Checks the invariants after every event of a simulation."""

    def __init__(self, world: World, repairs: Callable[[], frozenset[str]]) -> None:
        self.world = world
        self._repairs = repairs
        self.label: Mode | None = None
        self.flows: dict[LoopRef, Flow] = {}
        self.flow_log: list[Flow] = []
        self.last_end: dict[Mode, float] = {}
        self.dry = False
        self.stopping = False
        self.blocked_since: dict[LoopRef, float] = {}
        # When each output was last unarmed, unavailable, or under a call fault.
        self.impaired_at: dict[str, float] = {}
        # When each output was last unarmed, unavailable, or in Dry run.
        self.uncommandable_at: dict[str, float] = {}
        self.unmet: dict[str, Unmet] = {}
        self.started = False
        # The controller desires the source request off, and an off call to it has failed.
        self.release_wanted = False
        self.release_failed = False
        # Evaluations cannot run before this time: a blocked event loop or a downtime.
        self.paused_until = -math.inf

    @property
    def plant(self) -> Plant:
        return self.world.plant

    def start(self, label: Mode | None) -> None:
        """Take the initial physical state, with the label of flows that already run."""
        self.started = True
        self.label = label if label is not None else _mode_label(self.world.mode)
        # Control equipment off at setup is Dry run from the first evaluation.
        self.dry = not self.world.control
        self.check(self.world.t)

    # Hooks from the harness

    def on_control(self, on: bool) -> None:
        if on:
            self.dry = self.stopping = False
        elif not self.dry:
            self.stopping = not self.world.all_stopped()
            self.dry = not self.stopping

    def pause(self, until: float) -> None:
        """No evaluation runs from now until ``until``, which the guard bound does not count."""
        pause = max(0.0, until - max(self.world.t, self.paused_until))
        self.paused_until = max(self.paused_until, until)
        for ref, since in self.blocked_since.items():
            self.blocked_since[ref] = since + pause

    def on_desired(self, desired: Desired) -> None:
        """Check the shape of a desired state and take its mode as the label of new flows."""
        outputs = self.plant.outputs()
        for entity, target in desired.outputs.items():
            role = outputs.get(entity)
            if role is None:
                raise InvariantViolation("K2", self.world.t, f"Desired names {entity}, no output")
            expected = OptionTarget if role is OutputRole.SOURCE_MODE else SwitchTarget
            if not isinstance(target, expected):
                raise InvariantViolation("K2", self.world.t, f"Desired {entity}: {target}")
        label = _mode_label(desired.mode)
        if label is not None:
            self.label = label
        self.release_wanted = not desired.source_request

    def on_dispatch(self, call: Call) -> None:
        t = self.world.t
        if call.entity not in self.world.armed:
            raise InvariantViolation(1, t, f"unarmed output {call.entity} was sent {call.target}")
        if self.dry:
            raise InvariantViolation(1, t, f"{call.entity} was sent {call.target} in Dry run")
        source = self.plant.source
        if source is not None and call.entity == source.request:
            self.release_failed = call.target == SwitchTarget(False) and (
                call.failed or self.release_failed
            )
        unmet = self.unmet.get(call.entity)
        if unmet is not None and unmet.target == call.target and call.failed:
            unmet.failed += 1
            unmet.last_failed = t

    def on_evaluated(self, desired: Desired, live: bool) -> None:
        """Track the armed outputs whose target is unmet, for invariant 7."""
        t = self.world.t
        tracked = set()
        if live and self.world.control:
            for entity, target in desired.outputs.items():
                if entity not in self.world.armed or self.matches(entity, target):
                    continue
                tracked.add(entity)
                unmet = self.unmet.get(entity)
                if unmet is None or unmet.target != target:
                    self.unmet[entity] = Unmet(target, t)
        for entity in set(self.unmet) - tracked:
            del self.unmet[entity]

    def on_restart(self, calls: list[Call]) -> None:
        if calls:
            sent = ", ".join(f"{call.entity} {call.target}" for call in calls)
            raise InvariantViolation(
                8, self.world.t, f"the first evaluation after a restart sent {sent}"
            )

    # Checks after every event

    def check(self, t: float) -> None:
        if not self.world.control and self.stopping and self.world.all_stopped():
            self.stopping, self.dry = False, True
        self._note_impaired(t)
        self._check_flows(t)
        self._check_paths(t)
        self._check_source(t)
        self._check_guards(t)
        self._check_repairs(t)

    def _note_impaired(self, t: float) -> None:
        world = self.world
        for entity in self.plant.outputs():
            body = world.switches.get(entity) or world.selects.get(entity)
            if (
                entity not in world.armed
                or (body is not None and not body.available)
                or world.fault_for(entity, t) is not None
            ):
                self.impaired_at[entity] = t
            if self.dry or entity not in world.armed or (body is not None and not body.available):
                self.uncommandable_at[entity] = t

    def _check_flows(self, t: float) -> None:
        """Invariant 5: heating and cooling flows never overlap and keep the dwell apart."""
        flowing = {loop.ref: loop for loop in self.plant.all_loops if self.world.flowing(loop)}
        for ref in list(self.flows):
            if ref not in flowing:
                flow = self.flows.pop(ref)
                flow.end = t
                self.last_end[flow.label] = t
        for ref, loop in flowing.items():
            if ref in self.flows:
                continue
            label = self.label
            if label is None:
                raise InvariantViolation(5, t, f"loop {ref} flows before any mode ran")
            if label not in loop.modes:
                raise InvariantViolation(
                    5, t, f"loop {ref} flows in {label}, which it does not run"
                )
            for other in self.flows.values():
                if other.label is not label:
                    raise InvariantViolation(
                        5,
                        t,
                        f"loop {ref} flows in {label} while {other.ref} flows in {other.label}",
                    )
            opposite = Mode.COOL if label is Mode.HEAT else Mode.HEAT
            ended = self.last_end.get(opposite)
            if ended is not None and t < ended + self.plant.mode_dwell - EPSILON:
                raise InvariantViolation(
                    5,
                    t,
                    f"loop {ref} flows in {label} {t - ended:.0f}s after the last {opposite} flow "
                    f"ended; the dwell is {self.plant.mode_dwell:.0f}s",
                )
            flow = Flow(ref, label, t)
            self.flows[ref] = flow
            self.flow_log.append(flow)
        source_mode = self.world.source_mode()
        if self.world.requested and self.plant.source is not None and self.plant.source.mode:
            for flow in self.flows.values():
                if source_mode is not flow.label:
                    raise InvariantViolation(
                        5,
                        t,
                        f"the source runs in {source_mode} while loop {flow.ref} flows in "
                        f"{flow.label}",
                    )

    def _check_paths(self, t: float) -> None:
        """Invariants 2 and 4: a pump with min_flow: path never runs without an open path."""
        for pump in self.plant.pumps:
            if pump.min_flow is not MinFlow.PATH or not self.world.pump_running(pump):
                continue
            loops = self.plant.pump_loops(pump.slug)
            if any(self.world.path_open(loop) for loop in loops) or self._beyond_control(pump, t):
                continue
            number = 4 if pump.driven_by_source else 2
            why = self._source_phase() if pump.driven_by_source else "switched on"
            raise InvariantViolation(number, t, f"pump {pump.slug} runs ({why}) with no open path")

    def _beyond_control(self, pump: Pump, t: float) -> bool:
        """A valve closed by itself under a pump, and no output that could react was commandable.

        The pump's stop output and every such valve must have been uncommandable
        within one reaction, ``SPONTANEOUS_GRACE``.
        """
        world = self.world
        valves = {
            valve.entity for loop in self.plant.pump_loops(pump.slug) for valve in loop.valves
        }
        closed = {entity for _, entity in world.spontaneous if entity in valves}
        source = self.plant.source
        stop = pump.switch or (source.request if source is not None else None)
        return bool(closed) and all(
            t - self.uncommandable_at.get(entity, -math.inf) <= SPONTANEOUS_GRACE
            for entity in (*closed, stop)
            if entity is not None
        )

    def _release_impossible(self, t: float) -> bool:
        """The controller desires the source request off, and nothing it sends can do that."""
        source = self.plant.source
        if source is None or not self.release_wanted:
            return False
        impaired = self.impaired_at.get(source.request, -math.inf)
        return self.release_failed or t - impaired <= CALL_TIMEOUT + LATENCY

    def _source_phase(self) -> str:
        return "source requested" if self.world.requested else "source post-run"

    def _check_source(self, t: float) -> None:
        """Invariant 3: the source is requested only with a ready loop of the mode and its pump."""
        if not self.world.requested:
            self.release_failed = False
            return
        if any(t - when <= SPONTANEOUS_GRACE for when, _ in self.world.spontaneous):
            return
        if self._release_impossible(t):
            return
        label = self.label
        for loop in self.plant.all_loops:
            if label not in loop.modes or not self.world.path_open(loop):
                continue
            pump = self.plant.pump(loop.pump)
            if pump.driven_by_source or self.world.pump_running(pump):
                return
        raise InvariantViolation(
            3, t, f"the source is requested with no ready {label} loop whose pump runs"
        )

    def _check_guards(self, t: float) -> None:
        """Invariant 6: a cooling loop flows only while its condensation guard permits."""
        for loop in self.plant.all_loops:
            if not loop.cools:
                continue
            if not self.guard_blocked(loop):
                self.blocked_since.pop(loop.ref, None)
                continue
            since = self.blocked_since.setdefault(loop.ref, max(t, self.paused_until))
            flow = self.flows.get(loop.ref)
            if flow is None or flow.label is not Mode.COOL:
                continue
            pump = self.plant.pump(loop.pump)
            if pump.driven_by_source and self.world.post_running:
                continue
            if any(
                self.impaired_at.get(entity, -math.inf) >= since for entity in self._stops(loop)
            ):
                continue
            if t - since > _guard_bound(loop) + EPSILON:
                raise InvariantViolation(
                    6,
                    t,
                    f"cooling loop {loop.ref} has flowed {t - since:.0f}s while its "
                    "condensation guard blocks",
                )

    def _stops(self, loop: Loop) -> Iterator[str]:
        """The outputs that can stop a loop's flow."""
        yield from (valve.entity for valve in loop.valves)
        pump = self.plant.pump(loop.pump)
        if pump.switch is not None:
            yield pump.switch
        elif self.plant.source is not None:
            yield self.plant.source.request

    def _check_repairs(self, t: float) -> None:
        """Invariant 7 during a trace: a persistent failure is reported as a Repair."""
        for entity, unmet in self.unmet.items():
            if unmet.failed < REPAIR_AFTER or t < unmet.last_failed + REPAIR_GRACE:
                continue
            if self.matches(entity, unmet.target) or entity in self._repairs():
                continue
            raise InvariantViolation(
                7,
                t,
                f"{entity} missed {unmet.target} after {unmet.failed} failed calls "
                "and is not reported as a Repair",
            )

    def next_check_time(self) -> float | None:
        """The next deadline at which a check can fail without any event."""
        t = self.world.t
        times: list[float] = []
        for ref, since in self.blocked_since.items():
            try:
                loop = self.plant.loop(ref)
            except KeyError:
                continue
            times.append(since + _guard_bound(loop) + 2 * EPSILON)
        times.extend(when + SPONTANEOUS_GRACE + EPSILON for when, _ in self.world.spontaneous)
        times.extend(
            unmet.last_failed + REPAIR_GRACE
            for unmet in self.unmet.values()
            if unmet.failed >= REPAIR_AFTER
        )
        for entity, max_age in self.max_ages().items():
            sensor = self.world.sensors[entity]
            if sensor.stale:
                times.append(
                    sensor.stale_since
                    + max_age
                    + STALE_SLACK
                    - WALL_BASE
                    - self.world.wall_offset
                    + EPSILON
                )
        later = [time for time in times if time > t + EPSILON]
        return min(later) if later else None

    # After the trace settles

    def check_settled(self, live: bool, desired: Desired | None) -> None:
        """Invariant 7 at the end, and progress: a demanding zone gets heat."""
        t = self.world.t
        if not self.world.control:
            return
        for entity, target in desired.outputs.items() if desired is not None else ():
            if entity in self.world.armed and not self.matches(entity, target):
                raise InvariantViolation(
                    7, t, f"{entity} never reached {target} after the trace settled"
                )
        self._check_progress(t)
        if not live:
            raise InvariantViolation("K2", t, "Control equipment is on but the Plant is not live")

    def _check_progress(self, t: float) -> None:
        if self.world.mode is not Mode.HEAT:
            return
        for zone in self.plant.zones:
            candidates = [loop for loop in zone.loops if self._can_heat(loop)]
            if not candidates or not self.demands_heat(zone):
                continue
            if not any(self.world.flowing(loop) for loop in zone.loops):
                raise InvariantViolation(
                    "progress",
                    t,
                    f"zone {zone.slug} demands heat and loop {candidates[0].ref} can run, "
                    "but none of its loops flows",
                )

    def _can_heat(self, loop: Loop) -> bool:
        """A heat loop on a switched pump whose outputs, and the source's, are all usable."""
        pump = self.plant.pump(loop.pump)
        if Mode.HEAT not in loop.modes or pump.switch is None:
            return False
        entities = [pump.switch, *(valve.entity for valve in loop.valves)]
        if not all(entity in self.world.armed for entity in self.plant.outputs()):
            # An unarmed source output or valve elsewhere may keep a careful controller idle.
            return False
        if not all(
            entity in self.world.armed and self.world.switches[entity].available
            for entity in entities
        ):
            return False
        # A valveless loop that cannot heat would carry heating water on the same pump.
        return all(
            other.valves or Mode.HEAT in other.modes for other in self.plant.pump_loops(pump.slug)
        )

    # Oracles

    def matches(self, entity: str, target: OutputTarget) -> bool:
        if isinstance(target, SwitchTarget):
            body = self.world.switches[entity]
            return body.available and body.on == target.on
        if isinstance(target, OptionTarget):
            select = self.world.selects[entity]
            return select.available and select.option == target.option
        return False

    def max_ages(self) -> dict[str, float]:
        """Every sensor's max_age, as the plant file sets it."""
        ages: dict[str, float] = {}
        for zone in self.plant.zones:
            for sensor in (*zone.temperature, *zone.humidity):
                ages[sensor.entity] = sensor.max_age
            for area in zone.areas:
                names = self.world.areas[area.area]
                for entity in (names.temperature, names.humidity):
                    if entity is not None:
                        ages[entity] = area.max_age
        for entity in self.world.sensors:
            ages.setdefault(entity, DEFAULT_MAX_AGE)
        return ages

    def fresh(self, entity: str, max_age: float) -> float | None:
        reading = self.world.reading(entity)
        if reading.value is None or self.world.wall() - reading.updated > max_age + STALE_SLACK:
            return None
        return reading.value

    def _zone_values(self, zone: Zone, humidity: bool) -> list[float] | None:
        """Fresh values of a zone's temperature or humidity; None when a required one is missing."""
        values: list[float] = []
        for entity, required, max_age in self._zone_sensors(zone, humidity):
            value = self.fresh(entity, max_age)
            if value is None and required:
                return None
            if value is not None:
                values.append(value)
        return values or None

    def _zone_sensors(self, zone: Zone, humidity: bool) -> Iterator[tuple[str, bool, float]]:
        for sensor in zone.humidity if humidity else zone.temperature:
            yield sensor.entity, sensor.required, sensor.max_age
        for area in zone.areas:
            names = self.world.areas[area.area]
            entity = names.humidity if humidity else names.temperature
            if entity is not None:
                yield entity, area.required, area.max_age

    def guard_blocked(self, loop: Loop) -> bool:
        """Whether the condensation guard must block, on the readings the controller sees."""
        pump = self.plant.pump(loop.pump)
        references = [
            entity for entity in (pump.supply_temperature, loop.surface_temperature) if entity
        ]
        values = [self.fresh(entity, DEFAULT_MAX_AGE) for entity in references]
        if not values or any(value is None for value in values):
            return True
        zones = [self.plant.zone(loop.zone)] if loop.zone is not None else list(self.plant.zones)
        worst: float | None = None
        for zone in zones:
            temperatures = self._zone_values(zone, humidity=False)
            humidities = self._zone_values(zone, humidity=True)
            if temperatures is None or humidities is None:
                return True
            point = dew_point(max(temperatures), max(humidities))
            if point is None:
                return True
            worst = point if worst is None else max(worst, point)
        if worst is None:
            return True
        threshold = worst + CONDENSATION_MARGIN - GUARD_TOLERANCE
        return any(value < threshold for value in values if value is not None)

    def demands_heat(self, zone: Zone) -> bool:
        """Whether the zone surely demands heat, beyond any hysteresis."""
        state = self.world.thermostats.get(zone.slug)
        if isinstance(state, ExternalThermostatState):
            return state.action is Mode.HEAT
        if not isinstance(state, DigitalThermostatState) or state.hvac_mode is not Mode.HEAT:
            return False
        thermostat = zone.thermostat
        assert isinstance(thermostat, DigitalThermostat)
        target = state.target
        if state.preset is not None:
            target = thermostat.preset_targets.get(state.preset, target)
        values = self._zone_values(zone, humidity=False)
        if values is None:
            return False
        combined = _aggregate(zone, values)
        return combined < target - thermostat.heat_start_delta - DEMAND_MARGIN


def _aggregate(zone: Zone, values: Iterable[float]) -> float:
    items = list(values)
    match zone.aggregation.value:
        case "min":
            return min(items)
        case "max":
            return max(items)
        case _:
            return sum(items) / len(items)


def _guard_bound(loop: Loop) -> float:
    travel = max((valve.opening_time for valve in loop.valves), default=0.0)
    return CALL_TIMEOUT + LATENCY + travel + 1.0


def _mode_label(mode: Mode) -> Mode | None:
    return mode if mode in (Mode.HEAT, Mode.COOL) else None
