"""The invariants over random Plants and random event traces.

The profile ``sim-ci`` is deterministic, so CI sees the same examples on every
run; set ``HYPOTHESIS_SIM_PROFILE=sim-dev`` to explore many more, as the weekly
``sim-explore`` job of the Validate workflow does. ``sim-dev`` keeps failing
examples in ``.hypothesis/`` and prints a ``@reproduce_failure`` blob for each.
"""

from __future__ import annotations

import os

import pytest
from hypothesis import HealthCheck, Phase, find, given, settings
from hypothesis import strategies as st

from custom_components.hydronicus.core.model import MinFlow, Mode, Plant, RunKind
from tests.sim.strategies import (
    CallFault,
    Trace,
    idle_thermostats,
    plants,
    run,
    seasonal_traces,
    traces,
)
from tests.sim.world import FaultKind

# Hypothesis 6.156 on Python 3.14 misjudges its own PRNG as garbage when it
# first seeds one for a derandomized run; the warning is about Hypothesis itself.
pytestmark = pytest.mark.filterwarnings(
    "ignore:It looks like `register_random`:hypothesis.errors.HypothesisWarning"
)

_HEALTH = [HealthCheck.too_slow, HealthCheck.data_too_large]
settings.register_profile(
    "sim-ci",
    max_examples=60,
    derandomize=True,
    database=None,
    deadline=None,
    report_multiple_bugs=False,
    suppress_health_check=_HEALTH,
)
settings.register_profile(
    "sim-dev",
    max_examples=1000,
    deadline=None,
    print_blob=True,
    suppress_health_check=_HEALTH,
)
SIM = settings.get_profile(os.environ.get("HYPOTHESIS_SIM_PROFILE", "sim-ci"))
# Finding an example is enough to show a strategy reaches it; no need to shrink it.
_FIND = settings(SIM, phases=(Phase.generate,))


@st.composite
def cases(draw: st.DrawFn) -> tuple[Plant, Trace]:
    plant = draw(plants())
    return plant, draw(traces(plant))


@SIM
@given(cases())
def test_the_invariants_hold_on_random_plants_and_traces(case: tuple[Plant, Trace]) -> None:
    run(*case)


@st.composite
def seasonal_cases(draw: st.DrawFn) -> tuple[Plant, Trace]:
    plant = draw(plants().filter(lambda plant: any(loop.cools for loop in plant.all_loops)))
    return plant, draw(seasonal_traces(plant))


@SIM
@given(seasonal_cases())
def test_the_invariants_hold_through_changes_of_season(case: tuple[Plant, Trace]) -> None:
    """Random traces rarely both heat and cool; these change between the two on purpose."""
    run(*case)


@st.composite
def exercised_cases(draw: st.DrawFn) -> tuple[Plant, Trace]:
    plant = draw(plants().filter(lambda plant: plant.exercise is not None))
    return plant, draw(traces(plant))


# Seconds one exercise may take: the longest opening time, the longest run, and calls.
_EXERCISE_SLACK = 600.0


@SIM
@given(exercised_cases())
def test_an_idle_plant_exercises_every_pump_and_valve(case: tuple[Plant, Trace]) -> None:
    """After any trace, a Plant left idle in heat exercises every output it may.

    Every output is armed and available, every sensor reports a room far from
    frost, and every thermostat is off. Each switched pump with a heating loop
    and no valveless loop that only cools must run, and each valve of a heating
    loop must open, within two intervals of the dwell ending, one pump at a time.
    """
    plant, trace = case
    assert plant.exercise is not None
    sim = run(plant, trace)
    sim.set_control(True)
    sim.set_armed(plant.outputs())
    for zone in plant.zones:
        for sensor in (*zone.temperature, *zone.humidity):
            sim.set_sensor_stale(sensor.entity, False)
            sim.set_sensor_available(sensor.entity, True)
        sim.set_zone_temperature(zone.slug, 21.0)
    idle_thermostats(sim)
    sim.set_mode(Mode.HEAT, thermostats=False)
    sim.run_for(plant.mode_dwell)
    start = sim.t
    expected = {entity: sim.is_on(entity) for entity in _exercised(plant)}
    sim.run_for(2 * plant.exercise.interval + len(plant.pumps) * _EXERCISE_SLACK)
    missed = sorted(
        entity
        for entity, on in expected.items()
        if not on and not any(on for t, on in sim.switched(entity) if t >= start)
    )
    assert not missed, f"never exercised: {missed}"


def _exercised(plant: Plant) -> set[str]:
    """The outputs an exercise in heat reaches."""
    expected: set[str] = set()
    for pump in plant.pumps:
        loops = plant.pump_loops(pump.slug)
        heating = [loop for loop in loops if Mode.HEAT in loop.modes]
        if not heating:
            continue
        if pump.switch is not None and all(
            Mode.HEAT in loop.modes for loop in loops if not loop.valves
        ):
            expected.add(pump.switch)
        expected.update(valve.entity for loop in heating for valve in loop.valves)
    return expected


@settings(SIM, max_examples=200)
@given(plants())
def test_generated_plants_stay_within_the_contract(plant: Plant) -> None:
    assert 1 <= len(plant.pumps) <= 4
    assert 1 <= len(plant.all_loops) <= 6
    assert 1 <= len(plant.zones) <= 4
    assert all(len(loop.valves) <= 3 for loop in plant.all_loops)


@pytest.mark.parametrize(
    "feature",
    [
        lambda plant: any(p.driven_by_source and p.min_flow is MinFlow.PATH for p in plant.pumps),
        lambda plant: any(not p.driven_by_source for p in plant.pumps),
        lambda plant: any(loop.cools for loop in plant.all_loops),
        lambda plant: any(not loop.valves for loop in plant.all_loops),
        lambda plant: any(loop.runs.kind is RunKind.WITH_SOURCE for loop in plant.loops),
        lambda plant: any(loop.runs.kind is RunKind.WITH_ZONES for loop in plant.loops),
        lambda plant: plant.source is None,
        lambda plant: any(
            valve.entity.startswith("valve.") for loop in plant.all_loops for valve in loop.valves
        ),
        lambda plant: (
            any(pump.condensation_switch for pump in plant.pumps)
            and any(loop.condensation_switch for loop in plant.all_loops)
        ),
        lambda plant: any(loop.cools and loop.surface_minimum is None for loop in plant.all_loops),
        lambda plant: any(zone.windows for zone in plant.zones),
    ],
    ids=[
        "source-driven path pump",
        "switched pump",
        "cooling loop",
        "valveless loop",
        "with_source loop",
        "with_zones loop",
        "no source",
        "valve entity",
        "condensation switches",
        "surface minimum off",
        "windows",
    ],
)
def test_generated_plants_reach_every_feature(feature: object) -> None:
    assert callable(feature)
    find(plants(), feature, settings=settings(_FIND, max_examples=500))  # type: ignore[arg-type]


def test_generated_traces_reach_every_event() -> None:
    kinds = {
        "SetMode",
        "SetControl",
        "Arm",
        "SetSensor",
        "SensorFault",
        "SetThermostat",
        "SetContact",
        "Unavailable",
        "CallFault",
        "SpontaneousOff",
        "Restart",
        "JumpClock",
        "Suspend",
        "Idle",
    }
    seen: set[str] = set()

    def covers(case: tuple[Plant, Trace]) -> bool:
        seen.update(type(event).__name__ for _, event in case[1].events)
        return seen >= kinds

    find(cases(), covers, settings=settings(_FIND, max_examples=2000))


def test_generated_traces_stall_valves_that_report_their_travel() -> None:
    def stalls(case: tuple[Plant, Trace]) -> bool:
        return any(
            isinstance(event, CallFault) and event.kind is FaultKind.STALL
            for _, event in case[1].events
        )

    find(cases(), stalls, settings=settings(_FIND, max_examples=500))
