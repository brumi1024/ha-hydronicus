"""The invariants over random Plants and random event traces.

The profile ``sim-ci`` is deterministic, so CI sees the same examples on every
run; set ``HYPOTHESIS_SIM_PROFILE=sim-dev`` to explore many more.
"""

from __future__ import annotations

import os

import pytest
from hydronicus_core.model import MinFlow, Plant, RunKind
from hypothesis import HealthCheck, Phase, find, given, settings
from hypothesis import strategies as st

from tests.sim.strategies import Trace, plants, run, seasonal_traces, traces

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
    "sim-dev", max_examples=1000, deadline=None, suppress_health_check=_HEALTH
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
    ],
    ids=[
        "source-driven path pump",
        "switched pump",
        "cooling loop",
        "valveless loop",
        "with_source loop",
        "with_zones loop",
        "no source",
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
        "Unavailable",
        "CallFault",
        "SpontaneousOff",
        "Restart",
        "JumpClock",
        "Suspend",
    }
    seen: set[str] = set()

    def covers(case: tuple[Plant, Trace]) -> bool:
        seen.update(type(event).__name__ for _, event in case[1].events)
        return seen >= kinds

    find(cases(), covers, settings=settings(_FIND, max_examples=2000))
