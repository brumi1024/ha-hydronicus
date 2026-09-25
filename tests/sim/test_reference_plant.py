"""The reference plant of the redesign plan, run through its operating scenarios.

Every scenario also checks the invariants after every event.
"""

from __future__ import annotations

from hydronicus_core.model import Mode

from tests.sim.harness import Sim
from tests.sim.plants import (
    BASEMENT_CEILING,
    BEDROOM_CEILING,
    FLOOR_PUMP,
    FLOOR_VALVE,
    LIVING_CEILING,
    SOURCE_MODE,
    SUPPLY,
    TOWEL_PUMP,
    ZONES,
    reference_plant,
)

# Seconds for a change of observation to become a physical change.
REACTION = 15.0
OPENING = 180.0
POST_RUN = 180.0
MIN_ON = 600.0
DWELL = 3600.0


def _heating() -> Sim:
    sim = Sim(reference_plant(), mode=Mode.HEAT)
    for zone in ZONES:
        sim.set_zone_temperature(zone, 21.5)
    sim.start()
    return sim


def _cooling() -> Sim:
    sim = Sim(reference_plant(), mode=Mode.COOL)
    for zone in ZONES:
        sim.set_target(zone, 24.0)
        sim.set_zone_temperature(zone, 23.0)
    sim.set_sensor(SUPPLY, 18.0)
    sim.start()
    return sim


def _all_off(sim: Sim) -> bool:
    return not any(sim.is_on(entity) for entity in sim.world.switches) and not (
        sim.world.post_running
    )


def _first(sim: Sim, entity: str, on: bool) -> float:
    return next(t for t, value in sim.switched(entity) if value is on)


def _last(sim: Sim, entity: str, on: bool) -> float:
    return [t for t, value in sim.switched(entity) if value is on][-1]


def _heat_living_area(sim: Sim) -> float:
    """Let the living area call for heat until the source runs; return when it was requested."""
    sim.set_zone_temperature("living_area", 19.5)
    sim.run_until_true(
        lambda: sim.is_on(FLOOR_VALVE) and sim.is_on(LIVING_CEILING),
        REACTION,
        "the living area's valves open when it calls for heat",
    )
    sim.run_until_true(
        lambda: sim.flowing("living_area.floor"),
        OPENING + REACTION,
        "the floor pump runs once the floor valve has opened",
    )
    return sim.run_until_true(
        lambda: sim.world.requested,
        OPENING + REACTION,
        "the heat pump is requested once the ceiling loop is ready",
    )


def test_heating_a_zone_opens_its_loops_then_runs_its_pump_and_the_source() -> None:
    sim = _heating()
    sim.always_for(lambda: _all_off(sim), 60.0, "nothing runs while no zone calls")
    requested = _heat_living_area(sim)
    assert sim.world.option(SOURCE_MODE) == "Heat"
    assert sim.flowing("living_area.ceiling")
    assert not sim.is_on(BASEMENT_CEILING)
    assert not sim.is_on(BEDROOM_CEILING)
    sim.run_until_true(
        lambda: sim.is_on(TOWEL_PUMP), REACTION, "the towel dryer runs with the source"
    )
    assert _first(sim, TOWEL_PUMP, True) > requested

    for zone in ZONES:
        sim.set_zone_temperature(zone, 21.5)
    sim.run_until_true(
        lambda: _all_off(sim),
        MIN_ON + POST_RUN + OPENING + 4 * REACTION,
        "everything stops once the living area is warm",
    )
    assert _last(sim, FLOOR_VALVE, False) > _last(sim, FLOOR_PUMP, False), (
        "the floor valve closes only after its pump is observed off"
    )


def test_cooling_a_zone_stops_at_the_condensation_guard() -> None:
    sim = _cooling()
    sim.set_zone_temperature("living_area", 26.0)
    sim.run_until_true(
        lambda: sim.is_on(LIVING_CEILING), REACTION, "the living area's ceiling valve opens"
    )
    requested = sim.run_until_true(
        lambda: sim.world.requested,
        OPENING + REACTION,
        "the heat pump is requested for cooling once the ceiling loop is ready",
    )
    assert sim.world.option(SOURCE_MODE) == "Cool"
    sim.run_until_true(
        lambda: sim.flowing("living_area.ceiling"), REACTION, "the ceiling loop cools"
    )
    sim.run_until(requested + 300.0)

    # 26 °C at 50 % has a dew point of 14.8 °C, so 15 °C is inside the 2 K margin.
    sim.set_sensor(SUPPLY, 15.0)
    sim.run_until_true(
        lambda: not sim.world.requested,
        REACTION,
        "the guard releases the source at once, even inside its minimum on time",
    )
    sim.run_until_true(
        lambda: not sim.is_on(LIVING_CEILING),
        POST_RUN + 2 * REACTION,
        "the ceiling valve closes after the post-run",
    )
    sim.always_for(
        lambda: not sim.world.requested, 600.0, "the source stays off while the guard blocks"
    )
    for entity in (FLOOR_VALVE, FLOOR_PUMP, TOWEL_PUMP):
        assert sim.switched(entity) == [], f"{entity} never runs in cooling"


def test_a_mode_change_releases_heating_and_waits_for_the_dwell() -> None:
    sim = _heating()
    requested = _heat_living_area(sim)
    sim.run_until(requested + MIN_ON + 60.0)

    for zone in ZONES:
        sim.set_target(zone, 24.0)
        sim.set_zone_temperature(zone, 23.0)
    sim.set_zone_temperature("living_area", 26.0)
    sim.set_sensor(SUPPLY, 18.0)
    sim.set_mode(Mode.COOL)
    sim.run_until_true(
        lambda: not sim.world.requested, REACTION, "a mode change releases the source first"
    )
    sim.run_until_true(
        lambda: not sim.checker.flows,
        POST_RUN + OPENING + 4 * REACTION,
        "every heating loop stops",
    )
    heat_ended = max(flow.end or 0.0 for flow in sim.checker.flow_log)
    cooled = sim.run_until_true(
        lambda: any(flow.label is Mode.COOL for flow in sim.checker.flow_log),
        DWELL + 2 * OPENING + 4 * REACTION,
        "cooling starts after the mode dwell",
    )
    assert cooled >= heat_ended + DWELL
    assert sim.world.option(SOURCE_MODE) == "Cool"


def test_a_mode_change_keeps_the_source_for_its_minimum_on_time() -> None:
    sim = _heating()
    requested = _heat_living_area(sim)
    sim.run_until(requested + 60.0)

    sim.set_mode(Mode.OFF)
    sim.always_for(
        lambda: sim.world.requested and sim.world.option(SOURCE_MODE) == "Heat",
        MIN_ON - 60.0 - REACTION,
        "a mode change keeps the source heating for its minimum on time",
    )
    released = sim.run_until_true(
        lambda: not sim.world.requested,
        2 * REACTION,
        "the source is released once its minimum on time has passed",
    )
    assert released >= requested + MIN_ON
    sim.run_until_true(
        lambda: _all_off(sim),
        POST_RUN + OPENING + 4 * REACTION,
        "everything stops after the release",
    )
    assert _last(sim, LIVING_CEILING, False) > released + POST_RUN - REACTION, (
        "the min-flow loop stays open through the post-run"
    )


def test_the_towel_dryer_runs_with_the_source_and_its_overrun() -> None:
    sim = _heating()
    sim.set_zone_temperature("basement", 19.5)
    requested = sim.run_until_true(
        lambda: sim.world.requested,
        OPENING + 2 * REACTION,
        "the heat pump is requested for the basement",
    )
    sim.run_until_true(
        lambda: sim.is_on(TOWEL_PUMP), REACTION, "the towel dryer pump follows the source"
    )
    assert _first(sim, TOWEL_PUMP, True) > requested
    sim.set_zone_temperature("basement", 21.5)
    released = sim.run_until_true(
        lambda: not sim.world.requested,
        MIN_ON + REACTION,
        "the heat pump is released once the basement is warm",
    )
    stopped = sim.run_until_true(
        lambda: not sim.is_on(TOWEL_PUMP),
        120.0 + REACTION,
        "the towel dryer pump stops after its overrun",
    )
    assert stopped - released >= 120.0 - REACTION


def test_the_min_flow_path_serves_the_heat_pump_while_no_zone_calls() -> None:
    sim = _heating()
    sim.set_zone_temperature("bedroom_area", 19.5)
    sim.run_until_true(
        lambda: sim.world.requested,
        OPENING + 2 * REACTION,
        "the heat pump is requested for the bedroom area",
    )
    sim.run_for(60.0)
    sim.set_zone_temperature("bedroom_area", 21.5)
    sim.run_for(1.0)
    assert sim.pump_running("heat_pump"), "the heat pump still runs while no zone calls"
    # Invariant 4 holds the path open through the minimum on time and the post-run.
    sim.run_until_true(
        lambda: _all_off(sim),
        MIN_ON + POST_RUN + OPENING + 4 * REACTION,
        "the heat pump stops and every valve closes",
    )
    assert not sim.is_on(LIVING_CEILING)
    assert not sim.is_on(BEDROOM_CEILING)
