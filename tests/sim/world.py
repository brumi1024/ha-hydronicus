"""The physical side of a simulated Plant.

The world owns what really happens, independent of what the controller
believes: switch outputs, valve travel, switched pumps, the source with its
source-driven pumps and post-run, the mode select, sensors, thermostats, and
the service calls in flight with their faults.

Time ``t`` is physical and monotonic, in seconds from the start of the
simulation. Home Assistant stamps observations with the wall clock, which is
``WALL_BASE + t + wall_offset``; a clock jump changes only ``wall_offset``.

Valve model: a valve moves linearly between closed and open over its opening
time, in both directions. It passes flow only once it has opened fully and
keeps passing flow until it has closed fully, so opening is judged
pessimistically and closing realistically, and a controller that waits for a
valve's opening time after observing it on always finds it passing flow.

Service call model: a call normally takes effect ``LATENCY`` seconds after it
is sent. A fault window makes calls to one entity take effect after a longer
delay, fail at once (rejected), or never take effect (timed out). A delayed
call always takes effect before ``CALL_TIMEOUT``, and calls to one entity take
effect in the order they were sent. An unavailable entity rejects calls and
keeps its physical state.
"""

from __future__ import annotations

import heapq
import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from hydronicus_core.model import (
    ExternalThermostat,
    Loop,
    LoopRef,
    Mode,
    OptionTarget,
    OutputRole,
    OutputTarget,
    Plant,
    Pump,
    SwitchTarget,
    Valve,
)
from hydronicus_core.reconcile import CALL_TIMEOUT, Action
from hydronicus_core.step import (
    AreaSensors,
    DigitalThermostatState,
    ExternalThermostatState,
    Observations,
    OptionState,
    OutputState,
    Reading,
    SwitchState,
    ThermostatState,
)

WALL_BASE: Final = 1_800_000_000.0
# How long a healthy service call takes to act.
LATENCY: Final = 0.5
# Tolerance for comparing times that come from sums of floats.
EPSILON: Final = 1e-6

DEFAULT_TEMPERATURE: Final = 21.0
DEFAULT_HUMIDITY: Final = 50.0
DEFAULT_REFERENCE: Final = 20.0


class FaultKind(StrEnum):
    DELAY = "delay"
    REJECT = "reject"
    TIMEOUT = "timeout"


class Outcome(StrEnum):
    PENDING = "pending"
    LANDED = "landed"
    REJECTED = "rejected"
    TIMED_OUT = "timed out"
    # The entity became unavailable before the call acted.
    DROPPED = "dropped"


@dataclass(frozen=True, slots=True)
class Fault:
    """Calls to ``entity`` sent in ``[start, end)`` are delayed, rejected, or time out."""

    entity: str
    start: float
    end: float
    kind: FaultKind
    delay: float = 0.0


@dataclass(slots=True)
class Call:
    """One service call the runtime dispatched."""

    t: float
    entity: str
    target: OutputTarget
    outcome: Outcome
    lands_at: float | None

    @property
    def failed(self) -> bool:
        return self.outcome in (Outcome.REJECTED, Outcome.TIMED_OUT, Outcome.DROPPED)


@dataclass(slots=True)
class SwitchBody:
    """A switch output or binary sensor: its state, when it changed, and availability."""

    on: bool = False
    # Wall time of the last change of the observed state.
    changed: float = WALL_BASE
    available: bool = True

    def observe(self) -> SwitchState:
        return SwitchState(self.on if self.available else None, self.changed)


@dataclass(slots=True)
class SelectBody:
    option: str | None = None
    changed: float = WALL_BASE
    available: bool = True

    def observe(self) -> OptionState:
        return OptionState(self.option if self.available else None, self.changed)


@dataclass(slots=True)
class ValveBody:
    """A valve's travel; its switch is the ``SwitchBody`` of the same entity."""

    valve: Valve
    loop: LoopRef
    # Position at ``t0``, from 0 closed to 1 open, and the direction since then.
    p0: float = 0.0
    t0: float = 0.0
    opening: bool = False
    # Passes flow: set when fully open, cleared when fully closed.
    passes: bool = False
    # Invalidates scheduled end-of-travel events after a reversal.
    version: int = 0

    @property
    def travel(self) -> float:
        return self.valve.opening_time

    def position(self, t: float) -> float:
        moved = (t - self.t0) / self.travel
        return min(1.0, self.p0 + moved) if self.opening else max(0.0, self.p0 - moved)

    def end_time(self) -> float | None:
        if self.opening and self.p0 < 1.0:
            return self.t0 + (1.0 - self.p0) * self.travel
        if not self.opening and self.p0 > 0.0:
            return self.t0 + self.p0 * self.travel
        return None

    @property
    def fully_open(self) -> bool:
        return self.opening and self.p0 >= 1.0


@dataclass(slots=True)
class SensorBody:
    value: float
    available: bool = True
    # A stale sensor stops reporting: it keeps showing ``stale_value`` from its
    # last report at ``stale_since``, in wall time.
    stale: bool = False
    stale_since: float = WALL_BASE
    stale_value: float = 0.0


@dataclass(order=True, slots=True)
class _Happening:
    t: float
    seq: int
    run: Callable[[], None] = field(compare=False)


class World:
    """The simulated physical Plant."""

    def __init__(self, plant: Plant) -> None:
        self.t = 0.0
        self.wall_offset = 0.0
        self.plant = plant
        self.mode = Mode.OFF
        self.control = False
        self.armed: frozenset[str] = frozenset()
        self.switches: dict[str, SwitchBody] = {}
        self.selects: dict[str, SelectBody] = {}
        self.valves: dict[str, ValveBody] = {}
        self.readiness: dict[str, SwitchBody] = {}
        self.sensors: dict[str, SensorBody] = {}
        self.areas: dict[str, AreaSensors] = {}
        self.thermostats: dict[str, ThermostatState] = {}
        self.faults: list[Fault] = []
        self.calls: list[Call] = []
        # Physical switch changes, for scenario assertions: (t, entity, on).
        self.switch_log: list[tuple[float, str, bool]] = []
        # Times of spontaneous physical changes, for the invariant exemptions.
        self.spontaneous: list[tuple[float, str]] = []
        # Incremented on every change a Home Assistant state listener would see.
        self.version = 0
        self.post_run_end = 0.0
        self._queue: list[_Happening] = []
        self._seq = itertools.count()
        self._last_landing: dict[str, float] = {}
        self._in_flight: dict[int, Call] = {}
        self.adopt(plant)

    # Construction

    def adopt(self, plant: Plant) -> None:
        """Create the entities of ``plant`` that do not exist yet; keep the others."""
        self.plant = plant
        for entity, role in plant.outputs().items():
            if role is OutputRole.SOURCE_MODE:
                assert plant.source is not None and plant.source.mode is not None
                self.selects.setdefault(entity, SelectBody(option=plant.source.mode.heat))
            else:
                self.switches.setdefault(entity, SwitchBody(changed=self.wall()))
        for loop in plant.all_loops:
            for valve in loop.valves:
                self.valves.setdefault(valve.entity, ValveBody(valve, loop.ref, t0=self.t))
                if valve.readiness is not None:
                    self.readiness.setdefault(valve.readiness, SwitchBody(changed=self.wall()))
            if loop.surface_temperature is not None:
                self._sensor(loop.surface_temperature, DEFAULT_REFERENCE)
        for pump in plant.pumps:
            if pump.supply_temperature is not None:
                self._sensor(pump.supply_temperature, DEFAULT_REFERENCE)
        for zone in plant.zones:
            for sensor in zone.temperature:
                self._sensor(sensor.entity, DEFAULT_TEMPERATURE)
            for sensor in zone.humidity:
                self._sensor(sensor.entity, DEFAULT_HUMIDITY)
            for area in zone.areas:
                names = AreaSensors(
                    f"sensor.{area.area}_temperature", f"sensor.{area.area}_humidity"
                )
                self.areas.setdefault(area.area, names)
                assert names.temperature is not None and names.humidity is not None
                self._sensor(names.temperature, DEFAULT_TEMPERATURE)
                self._sensor(names.humidity, DEFAULT_HUMIDITY)
            if isinstance(zone.thermostat, ExternalThermostat):
                self.thermostats.setdefault(zone.slug, ExternalThermostatState(Mode.OFF))
            else:
                self.thermostats.setdefault(
                    zone.slug, DigitalThermostatState(Mode.OFF, zone.thermostat.target)
                )

    def _sensor(self, entity: str, value: float) -> None:
        self.sensors.setdefault(entity, SensorBody(value))

    # Time

    def wall(self, t: float | None = None) -> float:
        return WALL_BASE + (self.t if t is None else t) + self.wall_offset

    def next_time(self) -> float | None:
        return self._queue[0].t if self._queue else None

    def advance_to(self, t: float) -> None:
        """Let every physical happening up to ``t`` take place, in order."""
        while self._queue and self._queue[0].t <= t + EPSILON:
            happening = heapq.heappop(self._queue)
            self.t = max(self.t, happening.t)
            happening.run()
        self.t = max(self.t, t)

    def at(self, t: float, run: Callable[[], None]) -> None:
        heapq.heappush(self._queue, _Happening(t, next(self._seq), run))

    def changed(self) -> None:
        self.version += 1

    # Physical state

    def is_on(self, entity: str) -> bool:
        return self.switches[entity].on

    def switched(self, entity: str) -> list[tuple[float, bool]]:
        """Every physical change of a switch output, as (t, on)."""
        return [(t, on) for t, name, on in self.switch_log if name == entity]

    def option(self, entity: str) -> str | None:
        return self.selects[entity].option

    @property
    def requested(self) -> bool:
        source = self.plant.source
        return source is not None and self.switches[source.request].on

    @property
    def post_running(self) -> bool:
        return not self.requested and self.t < self.post_run_end - EPSILON

    def pump_running(self, pump: Pump) -> bool:
        if pump.switch is None:
            return self.requested or self.post_running
        return self.switches[pump.switch].on

    def valve_passes(self, entity: str) -> bool:
        return self.valves[entity].passes

    def path_open(self, loop: Loop) -> bool:
        """A loop with no valve is always open; otherwise every valve passes flow."""
        return all(self.valves[valve.entity].passes for valve in loop.valves)

    def flowing(self, loop: Loop) -> bool:
        return self.pump_running(self.plant.pump(loop.pump)) and self.path_open(loop)

    def source_mode(self) -> Mode | None:
        """The mode the source's select physically shows, if it has one."""
        source = self.plant.source
        if source is None or source.mode is None:
            return None
        option = self.selects[source.mode.entity].option
        return {source.mode.heat: Mode.HEAT, source.mode.cool: Mode.COOL}.get(option or "")

    def in_flight(self) -> bool:
        return bool(self._in_flight)

    def all_stopped(self) -> bool:
        """Every armed switch output is off, the source is not post-running, and no call waits."""
        return (
            not self.in_flight()
            and not self.post_running
            and not any(body.on for entity, body in self.switches.items() if entity in self.armed)
        )

    # Physical changes

    def set_switch(self, entity: str, on: bool) -> None:
        """Change a switch output physically, with its consequences."""
        body = self.switches[entity]
        if body.on == on:
            return
        body.on = on
        if body.available:
            body.changed = self.wall()
            self.changed()
        self.switch_log.append((self.t, entity, on))
        source = self.plant.source
        if source is not None and entity == source.request and not on:
            self.post_run_end = self.t + source.post_run
            self.at(self.post_run_end, lambda: None)
        if entity in self.valves:
            self._move_valve(entity, on)

    def _move_valve(self, entity: str, opening: bool) -> None:
        body = self.valves[entity]
        body.p0 = body.position(self.t)
        body.t0 = self.t
        body.opening = opening
        body.version += 1
        self._set_readiness(body)
        end = body.end_time()
        if end is not None:
            version = body.version
            self.at(end, lambda: self._valve_end(entity, version))

    def _valve_end(self, entity: str, version: int) -> None:
        body = self.valves[entity]
        if body.version != version:
            return
        body.p0 = 1.0 if body.opening else 0.0
        body.t0 = self.t
        body.passes = body.opening
        self._set_readiness(body)

    def _set_readiness(self, body: ValveBody) -> None:
        if body.valve.readiness is None:
            return
        readiness = self.readiness[body.valve.readiness]
        if readiness.on != body.fully_open:
            readiness.on = body.fully_open
            readiness.changed = self.wall()
            self.changed()

    def seed_open(self, entity: str, since: float) -> None:
        """Start with a valve switched on ``since`` seconds ago and fully open."""
        body = self.valves[entity]
        self.switches[entity].on = True
        self.switches[entity].changed = self.wall() - since
        body.p0, body.t0, body.opening, body.passes = 1.0, self.t, True, True
        if body.valve.readiness is not None:
            self.readiness[body.valve.readiness].on = True
            self.readiness[body.valve.readiness].changed = self.wall() - since + body.travel
        self.changed()

    def seed_on(self, entity: str, since: float) -> None:
        """Start with a switch output on since ``since`` seconds ago."""
        if entity in self.valves:
            self.seed_open(entity, since)
            return
        self.switches[entity].on = True
        self.switches[entity].changed = self.wall() - since
        self.changed()

    def seed_option(self, entity: str, option: str, since: float) -> None:
        self.selects[entity].option = option
        self.selects[entity].changed = self.wall() - since
        self.changed()

    def spontaneous_off(self, entity: str) -> None:
        """A switch output turns off by itself, such as a relay rebooting."""
        if self.switches[entity].on and self.switches[entity].available:
            self.spontaneous.append((self.t, entity))
            self.set_switch(entity, False)

    def set_available(self, entity: str, available: bool) -> None:
        body: SwitchBody | SelectBody = (
            self.switches[entity] if entity in self.switches else self.selects[entity]
        )
        if body.available != available:
            body.available = available
            body.changed = self.wall()
            self.changed()

    def set_sensor(self, entity: str, value: float) -> None:
        sensor = self.sensors[entity]
        if sensor.value != value:
            sensor.value = value
            if sensor.available and not sensor.stale:
                self.changed()

    def set_sensor_state(
        self, entity: str, *, available: bool | None = None, stale: bool | None = None
    ) -> None:
        sensor = self.sensors[entity]
        if stale is not None and stale != sensor.stale:
            sensor.stale = stale
            sensor.stale_since = self.wall()
            sensor.stale_value = sensor.value
            self.changed()
        if available is not None and available != sensor.available:
            sensor.available = available
            self.changed()

    def set_thermostat(self, zone: str, state: ThermostatState) -> None:
        if self.thermostats.get(zone) != state:
            self.thermostats[zone] = state
            self.changed()

    # Service calls

    def fault_for(self, entity: str, t: float) -> Fault | None:
        for fault in self.faults:
            if fault.entity == entity and fault.start <= t < fault.end:
                return fault
        return None

    def dispatch(self, action: Action) -> Call:
        """Send one service call and schedule its effect."""
        entity = self.plant_check(action)
        available = (
            self.switches[entity].available
            if entity in self.switches
            else self.selects[entity].available
        )
        fault = self.fault_for(entity, self.t)
        call = Call(self.t, entity, action.target, Outcome.PENDING, None)
        self.calls.append(call)
        if not available or (fault is not None and fault.kind is FaultKind.REJECT):
            call.outcome = Outcome.REJECTED
            return call
        if fault is not None and fault.kind is FaultKind.TIMEOUT:
            call.outcome = Outcome.TIMED_OUT
            return call
        delay = LATENCY
        if fault is not None and fault.kind is FaultKind.DELAY:
            delay = min(max(fault.delay, LATENCY), CALL_TIMEOUT - LATENCY)
        lands_at = max(self.t + delay, self._last_landing.get(entity, 0.0))
        self._last_landing[entity] = lands_at
        call.lands_at = lands_at
        key = id(call)
        self._in_flight[key] = call
        self.at(lands_at, lambda: self._land(key))
        return call

    def plant_check(self, action: Action) -> str:
        role = self.plant.outputs().get(action.entity)
        if role is None:
            raise AssertionError(f"reconcile() sent {action} to an entity that is no output")
        expected = OptionTarget if role is OutputRole.SOURCE_MODE else SwitchTarget
        if not isinstance(action.target, expected):
            raise AssertionError(f"reconcile() sent {action}, but {action.entity} is a {role}")
        return action.entity

    def _land(self, key: int) -> None:
        call = self._in_flight.pop(key)
        entity = call.entity
        if entity in self.switches:
            if not self.switches[entity].available:
                call.outcome = Outcome.DROPPED
                return
            assert isinstance(call.target, SwitchTarget)
            call.outcome = Outcome.LANDED
            self.set_switch(entity, call.target.on)
            return
        select = self.selects[entity]
        if not select.available:
            call.outcome = Outcome.DROPPED
            return
        assert isinstance(call.target, OptionTarget)
        call.outcome = Outcome.LANDED
        if select.option != call.target.option:
            select.option = call.target.option
            select.changed = self.wall()
            self.changed()

    # Observation

    def observe(self) -> Observations:
        """Take the snapshot the runtime would take from Home Assistant now."""
        now = self.wall()
        outputs: dict[str, OutputState] = {}
        for entity, role in self.plant.outputs().items():
            if role is OutputRole.SOURCE_MODE:
                outputs[entity] = self.selects[entity].observe()
            else:
                outputs[entity] = self.switches[entity].observe()
        return Observations(
            mode=self.mode,
            control=self.control,
            armed=self.armed,
            outputs=outputs,
            readiness={entity: body.observe() for entity, body in self.readiness.items()},
            sensors={entity: self.reading(entity, now) for entity in self.sensors},
            areas=dict(self.areas),
            thermostats=dict(self.thermostats),
        )

    def reading(self, entity: str, now: float | None = None) -> Reading:
        sensor = self.sensors[entity]
        now = self.wall() if now is None else now
        if not sensor.available:
            return Reading(None, now)
        if sensor.stale:
            return Reading(sensor.stale_value, sensor.stale_since)
        return Reading(sensor.value, now)
