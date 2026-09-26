"""The maintainer's house without its source, run through a heating day.

One switched pump drives every ceiling loop and the underfloor loop, and the
towel dryer runs with the zones. Every scenario also checks the invariants
after every event.
"""

from __future__ import annotations

from hydronicus_core.model import Mode

from tests.sim.harness import Sim
from tests.sim.plants import (
    BASEMENT_CEILING,
    BEDROOM_CEILING,
    FLOOR_VALVE,
    HEATING_PUMP,
    HOME,
    LIVING_CEILING,
    TOWEL_PUMP,
    ZONES,
    plant,
)

REACTION = 15.0
OPENING = 180.0
OVERRUN = 180.0
TOWEL_OVERRUN = 120.0


def _warm_house() -> Sim:
    sim = Sim(plant(HOME), mode=Mode.HEAT)
    for zone in ZONES:
        sim.set_zone_temperature(zone, 21.5)
    sim.start()
    return sim


def _last(sim: Sim, entity: str, on: bool) -> float:
    return [t for t, value in sim.switched(entity) if value is on][-1]


def test_one_pump_serves_every_loop_and_waits_for_an_open_valve() -> None:
    sim = _warm_house()
    sim.always_for(lambda: not sim.is_on(HEATING_PUMP), 60.0, "nothing runs while no zone calls")

    sim.set_zone_temperature("living_area", 19.5)
    sim.run_until_true(
        lambda: sim.is_on(FLOOR_VALVE) and sim.is_on(LIVING_CEILING),
        REACTION,
        "the living area's valves open when it calls for heat",
    )
    sim.run_until_true(
        lambda: sim.is_on(TOWEL_PUMP), REACTION, "the towel dryer runs while a zone heats"
    )
    assert not sim.is_on(HEATING_PUMP), "the heating pump waits for a valve to open"
    sim.run_until_true(
        lambda: sim.flowing("living_area.floor") and sim.flowing("living_area.ceiling"),
        OPENING + REACTION,
        "the heating pump runs both living area loops once their valves have opened",
    )
    assert not sim.is_on(BASEMENT_CEILING)
    assert not sim.is_on(BEDROOM_CEILING)


def test_a_zone_that_is_warm_closes_its_valves_while_the_pump_serves_another() -> None:
    sim = _warm_house()
    sim.set_zone_temperature("living_area", 19.5)
    sim.set_zone_temperature("basement", 19.5)
    sim.run_until_true(
        lambda: sim.flowing("basement.ceiling") and sim.flowing("living_area.floor"),
        OPENING + 2 * REACTION,
        "the pump serves the basement and the living area together",
    )

    sim.set_zone_temperature("living_area", 21.5)
    sim.run_until_true(
        lambda: not sim.is_on(FLOOR_VALVE) and not sim.is_on(LIVING_CEILING),
        OPENING + REACTION,
        "the living area's valves close once it is warm",
    )
    assert sim.is_on(HEATING_PUMP), "the pump keeps running for the basement"
    assert sim.flowing("basement.ceiling")


def test_the_house_stops_with_overrun_and_closes_the_last_valve_after_the_pump() -> None:
    sim = _warm_house()
    sim.set_zone_temperature("bedroom_area", 19.5)
    sim.run_until_true(
        lambda: sim.flowing("bedroom_area.ceiling"),
        OPENING + 2 * REACTION,
        "the bedroom area heats",
    )

    sim.set_zone_temperature("bedroom_area", 21.5)
    sim.run_until_true(
        lambda: not sim.is_on(HEATING_PUMP) and not sim.is_on(TOWEL_PUMP),
        OVERRUN + 2 * REACTION,
        "both pumps stop after their overrun",
    )
    sim.run_until_true(
        lambda: not sim.is_on(BEDROOM_CEILING),
        REACTION,
        "the bedroom valve closes once the pump is off",
    )
    assert _last(sim, BEDROOM_CEILING, False) > _last(sim, HEATING_PUMP, False), (
        "the last open valve closes only after the pump is observed off"
    )
    assert _last(sim, TOWEL_PUMP, False) < _last(sim, HEATING_PUMP, False), (
        "the towel dryer's shorter overrun ends first"
    )
