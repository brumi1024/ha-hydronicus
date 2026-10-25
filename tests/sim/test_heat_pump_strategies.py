"""The control strategies for the maintainer's heat pump keep what the plan concludes.

The table in ``docs/plans/midea-source.md`` comes from ``heat_pump_strategies``;
these checks keep its conclusions true as the core changes, on one mild day.
"""

from __future__ import annotations

from tests.sim.heat_pump import Metrics
from tests.sim.heat_pump_strategies import STRATEGIES, Strategy, run

MILD = 7.0


def _run(name: str) -> Metrics:
    item: Strategy = next(item for item in STRATEGIES if item.name == name)
    return run(item, MILD, days=1)


def test_the_hybrid_restarts_the_internal_pump_far_less_than_a_request_per_call() -> None:
    per_call = _run("a: request per call")
    hybrid = _run("c: hold 4 h, all loops, +0.5 K")

    assert len(hybrid.pump_starts) <= 0.6 * len(per_call.pump_starts)
    assert len(hybrid.compressor_starts) < len(per_call.compressor_starts)
    assert hybrid.sink_violation == per_call.sink_violation == 0.0
    assert max(hybrid.peak.values()) < 21.0 + 0.5 + 0.2
    assert max(hybrid.cold.values()) == 0.0


def test_today_the_heat_pump_heats_into_closed_valves() -> None:
    assert _run("today: no source").sink_violation > 600.0


def test_holding_into_the_floor_without_a_bound_overheats_the_living_area() -> None:
    assert _run("b: always on, floor sink").peak["living_area"] > 22.5
