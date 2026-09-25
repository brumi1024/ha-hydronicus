"""A simulated Plant, run by the core exactly as the runtime will run it.

``Sim`` couples a physical ``World`` with a runtime that, on every change a
state listener would see and at every due time, observes, calls ``step()``,
calls ``reconcile()``, dispatches the actions, persists both States as JSON,
and schedules the next evaluation. A ``Checker`` asserts the invariants after
every event, so a scenario or a property fails at the first violation.

A restart tears the runtime down and builds a new one from the persisted JSON,
as a reload or a Home Assistant restart would; the world keeps running.
"""

from __future__ import annotations

import heapq
import itertools
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Final

from hydronicus_core.model import Desired, LoopRef, Mode, Plant
from hydronicus_core.reconcile import Reconciled, ReconcileState, reconcile, step_view
from hydronicus_core.step import (
    DigitalThermostatState,
    ExternalThermostatState,
    State,
    ThermostatState,
    step,
)

from tests.sim.invariants import Checker, InvariantViolation
from tests.sim.world import EPSILON, Call, Fault, FaultKind, World

# Evaluations one instant may need before the harness calls it a livelock.
MAX_EVALUATIONS_PER_INSTANT: Final = 20
# The oldest a seeded output is, in seconds.
SEEDED_SINCE: Final = 3600.0


@dataclass(slots=True)
class Runtime:
    """What the runtime holds between evaluations, restored from the store."""

    plant: Plant
    state: State
    reconcile_state: ReconcileState
    seen_version: int = -1
    due_at: float | None = None
    desired: Desired | None = None
    result: Reconciled | None = None

    @classmethod
    def restore(cls, plant: Plant, store: dict[str, str]) -> Runtime:
        state = State.from_dict(json.loads(store["state"])) if "state" in store else State()
        reconciled = (
            ReconcileState.from_dict(json.loads(store["reconcile"]))
            if "reconcile" in store
            else ReconcileState()
        )
        return cls(plant, state, reconciled)


@dataclass(order=True, slots=True)
class _Scheduled:
    t: float
    seq: int
    run: Callable[[], None] = field(compare=False)


class Sim:
    """A simulated Plant with its runtime and invariant checks."""

    def __init__(
        self,
        plant: Plant,
        *,
        mode: Mode = Mode.OFF,
        control: bool = True,
        armed: Iterable[str] | None = None,
    ) -> None:
        self.world = World(plant)
        self.world.mode = mode
        self.world.control = control
        self.world.armed = frozenset(plant.outputs() if armed is None else armed)
        self._follow_mode(mode)
        self.store: dict[str, str] = {}
        self.runtime: Runtime | None = Runtime.restore(plant, self.store)
        self.checker = Checker(self.world, self.repairs)
        self.evaluations = 0
        self.suspended_until = 0.0
        self._repairs: frozenset[str] = frozenset()
        self._scheduled: list[_Scheduled] = []
        self._seq = itertools.count()

    # Reading

    @property
    def t(self) -> float:
        return self.world.t

    @property
    def plant(self) -> Plant:
        return self.world.plant

    @property
    def desired(self) -> Desired:
        assert self.runtime is not None and self.runtime.desired is not None
        return self.runtime.desired

    @property
    def state(self) -> State:
        assert self.runtime is not None
        return self.runtime.state

    def repairs(self) -> frozenset[str]:
        """The Repairs last reported; like Home Assistant's issues, they outlive a restart."""
        return self._repairs

    def is_on(self, entity: str) -> bool:
        return self.world.is_on(entity)

    def pump_running(self, slug: str) -> bool:
        return self.world.pump_running(self.plant.pump(slug))

    def flowing(self, ref: str) -> bool:
        return self.world.flowing(self.plant.loop(LoopRef.parse(ref)))

    def calls_to(self, entity: str) -> list[Call]:
        return [call for call in self.world.calls if call.entity == entity]

    def switched(self, entity: str) -> list[tuple[float, bool]]:
        """Every physical change of a switch output, as (t, on)."""
        return self.world.switched(entity)

    # Seeding the physical state before the first evaluation

    def seed_on(self, entity: str, since: float = SEEDED_SINCE) -> None:
        self.world.seed_on(entity, since)

    def seed_running(self, ref: str, since: float = SEEDED_SINCE) -> None:
        """Start with a loop's valves open for ``since`` seconds and its switched pump on."""
        loop = self.plant.loop(LoopRef.parse(ref))
        for valve in loop.valves:
            self.world.seed_on(valve.entity, since)
        pump = self.plant.pump(loop.pump)
        if pump.switch is not None:
            self.world.seed_on(pump.switch, since)

    def seed_option(self, entity: str, option: str, since: float = SEEDED_SINCE) -> None:
        self.world.seed_option(entity, option, since)

    def start(self, label: Mode | None = None) -> list[Call]:
        """Set the Plant up: take the initial state and run the first evaluation.

        ``label`` is the mode of loops seeded as flowing; it defaults to the Plant mode.
        """
        if self.checker.started:
            return []
        self.checker.start(label)
        return self._evaluate()

    # Inputs

    def set_mode(self, mode: Mode, *, thermostats: bool = True) -> None:
        self.world.mode = mode
        if thermostats:
            self._follow_mode(mode)
        self.world.changed()

    def _follow_mode(self, mode: Mode) -> None:
        for zone, state in self.world.thermostats.items():
            if isinstance(state, DigitalThermostatState):
                self.world.thermostats[zone] = replace(state, hvac_mode=mode)

    def set_control(self, on: bool) -> None:
        if on != self.world.control:
            self.world.control = on
            self.checker.on_control(on)
            self.world.changed()

    def set_armed(self, armed: Iterable[str]) -> None:
        self.world.armed = frozenset(armed)
        self.world.changed()

    def set_sensor(self, entity: str, value: float) -> None:
        self.world.set_sensor(entity, value)

    def zone_sensors(self, zone: str, *, humidity: bool = False) -> list[str]:
        found = self.plant.zone(zone)
        sensors = [sensor.entity for sensor in (found.humidity if humidity else found.temperature)]
        for area in found.areas:
            names = self.world.areas[area.area]
            entity = names.humidity if humidity else names.temperature
            if entity is not None:
                sensors.append(entity)
        return sensors

    def set_zone_temperature(self, zone: str, value: float) -> None:
        for entity in self.zone_sensors(zone):
            self.world.set_sensor(entity, value)

    def set_zone_humidity(self, zone: str, value: float) -> None:
        for entity in self.zone_sensors(zone, humidity=True):
            self.world.set_sensor(entity, value)

    def set_thermostat(self, zone: str, state: ThermostatState) -> None:
        self.world.set_thermostat(zone, state)

    def set_target(self, zone: str, target: float) -> None:
        state = self.world.thermostats[zone]
        assert isinstance(state, DigitalThermostatState)
        self.world.set_thermostat(zone, replace(state, target=target, preset=None))

    def set_action(self, zone: str, action: Mode | None) -> None:
        self.world.set_thermostat(zone, ExternalThermostatState(action))

    def set_sensor_stale(self, entity: str, stale: bool) -> None:
        self.world.set_sensor_state(entity, stale=stale)

    def set_sensor_available(self, entity: str, available: bool) -> None:
        self.world.set_sensor_state(entity, available=available)

    def fault(self, entity: str, kind: FaultKind, duration: float, *, delay: float = 0.0) -> None:
        """Delay, reject, or time out every call to ``entity`` for ``duration`` seconds."""
        self.world.faults.append(Fault(entity, self.t, self.t + duration, kind, delay))
        self.world.at(self.t + duration, lambda: None)

    def unavailable(self, entity: str, duration: float = math.inf) -> None:
        """Make an output unavailable, frozen in its physical state, for ``duration``."""
        self.world.set_available(entity, False)
        if math.isfinite(duration):
            self.world.at(self.t + duration, lambda: self.world.set_available(entity, True))

    def spontaneous_off(self, entity: str) -> None:
        self.world.spontaneous_off(entity)

    def jump_clock(self, seconds: float) -> None:
        """Step the wall clock; physical time goes on as before."""
        self.world.wall_offset += seconds

    def suspend(self, seconds: float) -> None:
        """Let no evaluation run for ``seconds``, as when the event loop is blocked."""
        self.suspended_until = self.t + seconds
        self.checker.pause(self.suspended_until)
        self.schedule(self.suspended_until, lambda: None)

    def restart(self, *, downtime: float = 0.0, plant: Plant | None = None) -> list[Call]:
        """Tear the runtime down and build it again from the persisted state.

        A restart without downtime and without a new Plant happens right after an
        evaluation that saw every change, so its first evaluation must send
        nothing (invariant 8). Return the calls of that first evaluation.
        """
        self.start()
        self._maybe_evaluate()
        assert self.runtime is not None
        new_plant = self.runtime.plant if plant is None else plant
        if plant is not None:
            self.world.adopt(plant)
        self.runtime = None
        if downtime > 0:
            self.checker.pause(self.t + downtime)
            self.schedule(self.t + downtime, lambda: self._boot(new_plant))
            return []
        calls = self._boot(new_plant)
        if plant is None:
            self.checker.on_restart(calls)
        return calls

    def _boot(self, plant: Plant) -> list[Call]:
        self.runtime = Runtime.restore(plant, self.store)
        return self._evaluate()

    def schedule(self, t: float, run: Callable[[], None]) -> None:
        heapq.heappush(self._scheduled, _Scheduled(t, next(self._seq), run))

    # Running

    def run_for(self, seconds: float) -> None:
        self.run_until(self.t + seconds)

    def run_until(self, end: float) -> None:
        self.start()
        while (t := self._next_time()) is not None and t <= end + EPSILON:
            self._tick(t)
        if end > self.t:
            self._tick(end)

    def run_until_true(self, predicate: Callable[[], bool], within: float, message: str) -> float:
        """Run until ``predicate`` holds and return that time; fail after ``within`` seconds."""
        self.start()
        end = self.t + within
        if predicate():
            return self.t
        while (t := self._next_time()) is not None and t <= end + EPSILON:
            self._tick(t)
            if predicate():
                return self.t
        self._tick(end)
        if predicate():
            return self.t
        raise AssertionError(f"{message} (not within {within:.0f}s, t={self.t:.1f}s)")

    def always_for(self, predicate: Callable[[], bool], seconds: float, message: str) -> None:
        """Run for ``seconds`` and fail as soon as ``predicate`` stops holding."""
        self.start()
        end = self.t + seconds
        if not predicate():
            raise AssertionError(f"{message} (t={self.t:.1f}s)")
        while (t := self._next_time()) is not None and t <= end + EPSILON:
            self._tick(t)
            if not predicate():
                raise AssertionError(f"{message} (t={self.t:.1f}s)")
        self._tick(max(end, self.t))

    def settle(self, seconds: float) -> None:
        """Run a quiet period, then check that every difference resolved (invariant 7)."""
        self.run_for(seconds)
        runtime = self.runtime
        self.checker.check_settled(
            runtime is not None and runtime.state.live,
            None if runtime is None else runtime.desired,
        )

    def _next_time(self) -> float | None:
        world = self.world
        candidates = [world.next_time(), self.checker.next_check_time()]
        if self._scheduled:
            candidates.append(self._scheduled[0].t)
        runtime = self.runtime
        if runtime is not None:
            ready = max(world.t, self.suspended_until)
            if runtime.seen_version != world.version:
                candidates.append(ready)
            if runtime.due_at is not None:
                candidates.append(max(runtime.due_at, ready))
        times = [time for time in candidates if time is not None]
        return min(times) if times else None

    def _tick(self, t: float) -> None:
        self.world.advance_to(t)
        while self._scheduled and self._scheduled[0].t <= self.t + EPSILON:
            heapq.heappop(self._scheduled).run()
        self._maybe_evaluate()
        self.checker.check(self.t)

    def _maybe_evaluate(self) -> None:
        if self.t < self.suspended_until - EPSILON:
            return
        for _ in range(MAX_EVALUATIONS_PER_INSTANT):
            runtime = self.runtime
            if runtime is None:
                return
            due = runtime.due_at is not None and runtime.due_at <= self.t + EPSILON
            if runtime.seen_version == self.world.version and not due:
                return
            self._evaluate()
        raise InvariantViolation(
            "K2", self.t, "step() or reconcile() keeps asking for another evaluation now"
        )

    def _evaluate(self) -> list[Call]:
        """One evaluation: observe, step, reconcile, persist, dispatch, and schedule."""
        world, runtime = self.world, self.runtime
        assert runtime is not None
        now = world.wall()
        observations = world.observe()
        view = step_view(observations, runtime.reconcile_state)
        state, desired, due = step(runtime.plant, view, runtime.state, now)
        if due is not None and not (math.isfinite(due) and due >= 0):
            raise InvariantViolation("K2", self.t, f"step() returned a due time of {due}")
        self.checker.on_desired(desired)
        result = reconcile(
            runtime.plant,
            desired,
            observations.outputs,
            runtime.reconcile_state,
            now,
            armed=observations.armed,
            live=state.live,
        )
        runtime.state, runtime.reconcile_state = state, result.state
        runtime.desired, runtime.result = desired, result
        self._repairs = result.repairs
        self.store["state"] = json.dumps(state.to_dict())
        self.store["reconcile"] = json.dumps(result.state.to_dict())
        runtime.seen_version = world.version
        calls = []
        for action in result.send:
            call = world.dispatch(action)
            self.checker.on_dispatch(call)
            calls.append(call)
        due_at = None if due is None else self.t + due
        if result.retry_at is not None:
            retry_at = self.t + max(0.0, result.retry_at - now)
            due_at = retry_at if due_at is None else min(due_at, retry_at)
        runtime.due_at = due_at
        self.checker.on_evaluated(desired, state.live)
        self.evaluations += 1
        return calls
