"""Hypothesis strategies for random Plants and the event traces run over them.

Plants follow contract K9: 1 to 4 pumps of both kinds, 1 to 6 loops with 0 to 3
valves, 1 to 4 zones, and an optional source. They are valid by construction:
the strategy only draws combinations that ``validate_plant`` accepts, and it
calls ``validate_plant`` to prove it. Plant loops heat only, so a loop that
cools always belongs to one zone, whose dew point it answers to, and a
source-driven pump's min-flow loops run in every mode its other loops run in.

A trace starts from initial inputs and optionally from loops found running,
then applies timed events: mode and Control equipment changes, arming, sensor
changes, stale and unavailable sensors, thermostat changes, unavailable
outputs, delayed, rejected, and timed out calls, spontaneous relay drops,
restarts with and without downtime, backward clock jumps, and blocked event
loops. Nothing else happens during a downtime or a blocked event loop, and a
spontaneous change never falls near a fault, so the controller always gets one
fair chance to react to it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Protocol

from hydronicus_core.model import (
    RUNS_WITH_SOURCE,
    RUNS_WITH_ZONE,
    Aggregation,
    DigitalThermostat,
    ExternalThermostat,
    Loop,
    LoopRef,
    LoopRun,
    MinFlow,
    Mode,
    OutputRole,
    Plant,
    Pump,
    RunKind,
    Sensor,
    Source,
    SourceModeSelect,
    Thermostat,
    Valve,
    Zone,
)
from hydronicus_core.plant_file import validate_plant
from hydronicus_core.step import (
    DigitalThermostatState,
    ExternalThermostatState,
    ThermostatState,
)
from hypothesis import strategies as st

from tests.sim.harness import Sim
from tests.sim.invariants import SPONTANEOUS_GRACE
from tests.sim.world import FaultKind

PLANT_ID: Final = "0b6f3c7a-9a51-4b1e-8d43-6f0c2b9e7d15"
MAX_EVENTS: Final = 16
# The quiet period after the last event, beyond the Plant's mode dwell.
SETTLE: Final = 3600.0

_TEMPERATURES = st.integers(32, 54).map(lambda half: half / 2)
_HUMIDITIES = st.integers(30, 80).map(float)
_REFERENCES = st.integers(20, 60).map(lambda half: half / 2)
_TARGETS = st.integers(38, 48).map(lambda half: half / 2)


# Plants


@st.composite
def plants(draw: st.DrawFn) -> Plant:
    source = draw(st.none() | _sources())
    pump_count = draw(st.integers(1, 4))
    driven = [source is not None and draw(st.booleans()) for _ in range(pump_count)]
    supplies = [draw(st.booleans()) for _ in range(pump_count)]
    zone_slugs = [f"z{index}" for index in range(draw(st.integers(1, 4)))]

    plant_loops: list[Loop] = []
    zone_loops: dict[str, list[Loop]] = {slug: [] for slug in zone_slugs}
    for index in range(draw(st.integers(1, 6))):
        owner = draw(st.sampled_from([*zone_slugs, None]))
        pump = draw(st.integers(0, pump_count - 1))
        ref = LoopRef(owner, f"l{index}")
        prefix = f"{owner or 'plant'}_l{index}"
        valves = tuple(
            Valve(
                entity=f"switch.{prefix}_valve_{number}",
                opening_time=draw(st.sampled_from([30.0, 60.0, 180.0])),
                readiness=f"binary_sensor.{prefix}_valve_{number}_open"
                if draw(st.booleans())
                else None,
            )
            for number in range(draw(st.integers(0, 3)))
        )
        if owner is None:
            runs = (
                RUNS_WITH_SOURCE
                if source is not None and draw(st.booleans())
                else LoopRun(
                    RunKind.WITH_ZONES,
                    tuple(draw(st.lists(st.sampled_from(zone_slugs), min_size=1, unique=True))),
                )
            )
            plant_loops.append(Loop(ref, valves, f"p{pump}", frozenset({Mode.HEAT}), runs, None))
            continue
        surface = f"sensor.{prefix}_surface" if draw(st.booleans()) else None
        modes = (
            draw(
                st.sampled_from(
                    [
                        frozenset({Mode.HEAT}),
                        frozenset({Mode.HEAT, Mode.COOL}),
                        frozenset({Mode.COOL}),
                    ]
                )
            )
            if surface is not None or supplies[pump]
            else frozenset({Mode.HEAT})
        )
        zone_loops[owner].append(Loop(ref, valves, f"p{pump}", modes, RUNS_WITH_ZONE, surface))

    all_loops = [*plant_loops, *(loop for loops in zone_loops.values() for loop in loops)]
    pumps = tuple(
        _pump(draw, index, driven[index], supplies[index], all_loops) for index in range(pump_count)
    )
    zones = tuple(
        Zone(
            slug=slug,
            loops=tuple(zone_loops[slug]),
            temperature=tuple(
                Sensor(
                    f"sensor.{slug}_temperature_{number}",
                    required=draw(st.booleans()),
                    max_age=draw(st.sampled_from([600.0, 1800.0])),
                )
                for number in range(draw(st.integers(1, 2)))
            ),
            humidity=(Sensor(f"sensor.{slug}_humidity"),),
            aggregation=draw(st.sampled_from(list(Aggregation))),
            thermostat=draw(_thermostats(slug)),
        )
        for slug in zone_slugs
    )
    plant = Plant(
        id=PLANT_ID,
        name="Generated",
        # At least the longest valve travel, so a closing valve never carries
        # the old mode's water into the new one.
        mode_dwell=draw(st.sampled_from([300.0, 1800.0])),
        source=source,
        pumps=pumps,
        loops=tuple(plant_loops),
        zones=zones,
    )
    validate_plant(plant)
    return plant


def _sources() -> st.SearchStrategy[Source]:
    return st.builds(
        Source,
        request=st.just("switch.source_request"),
        mode=st.none() | st.just(SourceModeSelect("select.source_mode", "Heat", "Cool")),
        post_run=st.sampled_from([0.0, 60.0, 180.0]),
        min_on=st.sampled_from([0.0, 120.0, 600.0]),
        min_off=st.sampled_from([0.0, 120.0, 600.0]),
    )


def _thermostats(slug: str) -> st.SearchStrategy[Thermostat]:
    digital = st.builds(
        DigitalThermostat,
        min_on=st.sampled_from([0.0, 120.0]),
        min_off=st.sampled_from([0.0, 120.0]),
    )
    return digital | st.just(ExternalThermostat(f"climate.{slug}"))


def _pump(draw: st.DrawFn, index: int, driven: bool, supply: bool, loops: list[Loop]) -> Pump:
    slug = f"p{index}"
    overrun = draw(st.sampled_from([0.0, 60.0, 180.0]))
    supply_temperature = f"sensor.{slug}_supply" if supply else None
    if not driven:
        return Pump(
            slug,
            f"switch.{slug}_pump",
            overrun=overrun,
            min_flow=draw(st.sampled_from(list(MinFlow))),
            supply_temperature=supply_temperature,
        )
    own = [loop for loop in loops if loop.pump == slug]
    modes: frozenset[Mode] = frozenset().union(*(loop.modes for loop in own))
    eligible = [loop.ref for loop in own if loop.modes >= modes]
    if eligible and draw(st.booleans()):
        refs = tuple(draw(st.lists(st.sampled_from(eligible), min_size=1, unique=True)))
        return Pump(
            slug,
            None,
            overrun=overrun,
            min_flow=MinFlow.PATH,
            min_flow_loops=refs,
            supply_temperature=supply_temperature,
        )
    return Pump(
        slug,
        None,
        overrun=overrun,
        min_flow=MinFlow.GUARANTEED,
        supply_temperature=supply_temperature,
    )


# Traces


class Event(Protocol):
    def apply(self, sim: Sim) -> None: ...


@dataclass(frozen=True)
class SetMode:
    mode: Mode
    thermostats: bool

    def apply(self, sim: Sim) -> None:
        sim.set_mode(self.mode, thermostats=self.thermostats)


@dataclass(frozen=True)
class SetControl:
    on: bool

    def apply(self, sim: Sim) -> None:
        sim.set_control(self.on)


@dataclass(frozen=True)
class Arm:
    entity: str
    armed: bool

    def apply(self, sim: Sim) -> None:
        armed = set(sim.world.armed)
        if self.armed:
            armed.add(self.entity)
        else:
            armed.discard(self.entity)
        sim.set_armed(armed)


@dataclass(frozen=True)
class SetSensor:
    entity: str
    value: float

    def apply(self, sim: Sim) -> None:
        sim.set_sensor(self.entity, self.value)


@dataclass(frozen=True)
class SensorFault:
    entity: str
    stale: bool | None = None
    available: bool | None = None

    def apply(self, sim: Sim) -> None:
        if self.stale is not None:
            sim.set_sensor_stale(self.entity, self.stale)
        if self.available is not None:
            sim.set_sensor_available(self.entity, self.available)


@dataclass(frozen=True)
class SetThermostat:
    zone: str
    state: ThermostatState

    def apply(self, sim: Sim) -> None:
        sim.set_thermostat(self.zone, self.state)


@dataclass(frozen=True)
class Unavailable:
    entity: str
    duration: float

    def apply(self, sim: Sim) -> None:
        sim.unavailable(self.entity, self.duration)


@dataclass(frozen=True)
class CallFault:
    entity: str
    kind: FaultKind
    duration: float
    delay: float = 0.0

    def apply(self, sim: Sim) -> None:
        sim.fault(self.entity, self.kind, self.duration, delay=self.delay)


@dataclass(frozen=True)
class SpontaneousOff:
    entity: str

    def apply(self, sim: Sim) -> None:
        sim.spontaneous_off(self.entity)


@dataclass(frozen=True)
class Restart:
    downtime: float

    def apply(self, sim: Sim) -> None:
        sim.restart(downtime=self.downtime)


@dataclass(frozen=True)
class JumpClock:
    seconds: float

    def apply(self, sim: Sim) -> None:
        sim.jump_clock(self.seconds)


@dataclass(frozen=True)
class Suspend:
    seconds: float

    def apply(self, sim: Sim) -> None:
        sim.suspend(self.seconds)


@dataclass(frozen=True)
class Trace:
    """Initial inputs, loops found running, and timed events."""

    mode: Mode
    control: bool
    armed: frozenset[str]
    running: tuple[str, ...]
    sensors: tuple[tuple[str, float], ...]
    thermostats: tuple[tuple[str, ThermostatState], ...]
    events: tuple[tuple[float, Event], ...]

    @property
    def end(self) -> float:
        """When the last event, fault, or outage is over."""
        end = 0.0
        for t, event in self.events:
            end = max(end, t + _window(event))
        return end


def _window(event: Event) -> float:
    match event:
        case Unavailable(duration=duration) | CallFault(duration=duration):
            return duration
        case Restart(downtime=seconds) | Suspend(seconds=seconds):
            return seconds
        case _:
            return 0.0


@st.composite
def traces(draw: st.DrawFn, plant: Plant) -> Trace:
    outputs = plant.outputs()
    switches = [entity for entity, role in outputs.items() if role is not OutputRole.SOURCE_MODE]
    commandable = list(outputs)
    # Disarming a running source request would leave the source on for good.
    disarmable = [
        entity for entity, role in outputs.items() if role is not OutputRole.SOURCE_REQUEST
    ]
    outages = [entity for entity, role in outputs.items() if role in _OUTAGE_ROLES]
    sensors = sorted(_sensors(plant))
    mode = draw(st.sampled_from([Mode.HEAT, Mode.HEAT, Mode.COOL, Mode.OFF]))
    armed = (
        frozenset(outputs)
        if draw(st.booleans())
        else frozenset(draw(st.lists(st.sampled_from(commandable), unique=True)))
    )
    running: tuple[str, ...] = ()
    if mode is not Mode.COOL:
        candidates = [str(loop.ref) for loop in plant.all_loops if _may_seed(plant, loop)]
        if candidates:
            running = tuple(draw(st.lists(st.sampled_from(candidates), unique=True)))

    events: list[tuple[float, Event]] = []
    t = 0.0
    for _ in range(draw(st.integers(0, MAX_EVENTS))):
        t += draw(st.integers(1, 1800))
        event = draw(_events(plant, switches, commandable, disarmable, outages, sensors))
        events.append((t, event))
        t += _window(event) if isinstance(event, Restart | Suspend) else 0.0
    return Trace(
        mode=mode,
        control=draw(st.sampled_from([True, True, True, False])),
        armed=armed,
        running=running,
        sensors=tuple((entity, draw(_sensor_values(entity))) for entity in sensors),
        thermostats=tuple(
            (zone.slug, draw(_thermostat_states(zone, mode))) for zone in plant.zones
        ),
        events=_fair(events),
    )


_OUTAGE_ROLES: Final = (OutputRole.VALVE, OutputRole.PUMP)


def _may_seed(plant: Plant, loop: Loop) -> bool:
    """A heating loop on a switched pump whose valveless loops all heat."""
    pump = plant.pump(loop.pump)
    return (
        pump.switch is not None
        and Mode.HEAT in loop.modes
        and all(other.valves or Mode.HEAT in other.modes for other in plant.pump_loops(pump.slug))
    )


def _sensors(plant: Plant) -> set[str]:
    found: set[str] = set()
    for pump in plant.pumps:
        if pump.supply_temperature is not None:
            found.add(pump.supply_temperature)
    for loop in plant.all_loops:
        if loop.surface_temperature is not None:
            found.add(loop.surface_temperature)
    for zone in plant.zones:
        found.update(sensor.entity for sensor in (*zone.temperature, *zone.humidity))
    return found


def _sensor_values(entity: str) -> st.SearchStrategy[float]:
    if "humidity" in entity:
        return _HUMIDITIES
    if entity.endswith(("_supply", "_surface")):
        return _REFERENCES
    return _TEMPERATURES


def _thermostat_states(zone: Zone, mode: Mode) -> st.SearchStrategy[ThermostatState]:
    if isinstance(zone.thermostat, ExternalThermostat):
        return st.builds(
            ExternalThermostatState, st.sampled_from([Mode.HEAT, Mode.COOL, Mode.OFF, None])
        )
    return st.builds(
        DigitalThermostatState,
        hvac_mode=st.sampled_from([mode, mode, Mode.HEAT, Mode.COOL, Mode.OFF]),
        target=_TARGETS,
    )


def _events(
    plant: Plant,
    switches: list[str],
    commandable: list[str],
    disarmable: list[str],
    outages: list[str],
    sensors: list[str],
) -> st.SearchStrategy[Event]:
    durations = st.sampled_from([10.0, 60.0, 300.0, 900.0])
    choices: list[st.SearchStrategy[Event]] = [
        st.builds(SetMode, st.sampled_from(list(Mode)), st.booleans()),
        st.builds(SetControl, st.booleans()),
        st.builds(Arm, st.sampled_from(commandable), st.just(True)),
        st.sampled_from(sensors).flatmap(
            lambda entity: st.builds(SetSensor, st.just(entity), _sensor_values(entity))
        ),
        st.builds(SensorFault, st.sampled_from(sensors), stale=st.booleans()),
        st.builds(SensorFault, st.sampled_from(sensors), available=st.booleans()),
        st.sampled_from(plant.zones).flatmap(
            lambda zone: st.builds(
                SetThermostat, st.just(zone.slug), _thermostat_states(zone, Mode.HEAT)
            )
        ),
        st.builds(
            CallFault,
            st.sampled_from(commandable),
            st.sampled_from(list(FaultKind)),
            durations,
            st.sampled_from([2.0, 5.0, 9.0]),
        ),
        st.builds(SpontaneousOff, st.sampled_from(switches)),
        st.builds(Restart, st.sampled_from([0.0, 0.0, 30.0, 600.0])),
        st.builds(JumpClock, st.sampled_from([-30.0, -300.0])),
        st.builds(Suspend, st.sampled_from([30.0, 600.0])),
    ]
    if disarmable:
        choices.append(st.builds(Arm, st.sampled_from(disarmable), st.just(False)))
    if outages:
        choices.append(st.builds(Unavailable, st.sampled_from(outages), durations))
    return st.one_of(choices)


def _fair(events: list[tuple[float, Event]]) -> tuple[tuple[float, Event], ...]:
    """Drop spontaneous changes that fall near a fault, an outage, or a pause."""
    windows = [
        (t - SPONTANEOUS_GRACE, t + _window(event) + SPONTANEOUS_GRACE)
        for t, event in events
        if isinstance(event, CallFault | Unavailable | Restart | Suspend)
    ]
    return tuple(
        (t, event)
        for t, event in events
        if not isinstance(event, SpontaneousOff)
        or not any(start <= t <= end for start, end in windows)
    )


# Running a trace


def run(plant: Plant, trace: Trace) -> Sim:
    """Run a trace to its end and let it settle, checking every invariant on the way."""
    sim = Sim(plant, mode=trace.mode, control=trace.control, armed=trace.armed)
    for entity, value in trace.sensors:
        sim.set_sensor(entity, value)
    for zone, state in trace.thermostats:
        sim.set_thermostat(zone, state)
    for ref in trace.running:
        sim.seed_running(ref)
    sim.start(label=Mode.HEAT if trace.running else None)
    for t, event in trace.events:
        sim.run_until(t)
        event.apply(sim)
    sim.run_until(max(sim.t, trace.end) + 1.0)
    sim.settle(plant.mode_dwell + SETTLE)
    assert math.isfinite(sim.t)
    return sim
