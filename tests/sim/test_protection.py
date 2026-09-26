"""Frost protection and the exercise of idle pumps and valves, over simulated days.

Every scenario also checks the invariants after every event.
"""

from __future__ import annotations

import pytest

from custom_components.hydronicus.core.model import DEFAULT_EXERCISE_INTERVAL, Mode
from custom_components.hydronicus.core.step import DigitalThermostatState
from tests.sim.harness import Sim
from tests.sim.plants import (
    BOILER,
    FLOOR_PUMP,
    FLOOR_VALVE,
    LIVING_CEILING,
    REQUEST,
    TOWEL_PUMP,
    TWO_CEILINGS,
    plant,
    reference_plant,
)

REACTION = 15.0
OPENING = 180.0
DWELL = 3600.0
RUN = 60.0

BOILER_REQUEST = "switch.boiler_request"
CIRCULATOR = "switch.circulator_pump"
RADIATOR_VALVE = "switch.flat_radiator_valve"


def _on_between(sim: Sim, entity: str) -> list[tuple[float, float]]:
    """Each stretch an output was physically on, as (from, to)."""
    stretches: list[tuple[float, float]] = []
    start: float | None = None
    for t, on in sim.switched(entity):
        if on and start is None:
            start = t
        elif not on and start is not None:
            stretches.append((start, t))
            start = None
    if start is not None:
        stretches.append((start, sim.t))
    return stretches


# Frost protection


@pytest.mark.parametrize("mode", [Mode.OFF, Mode.HEAT])
def test_frost_protection_heats_a_zone_whose_thermostat_is_off(mode: Mode) -> None:
    """With the thermostat off, and the Plant's Mode select off or heat."""
    sim = Sim(plant(BOILER), mode=mode)
    sim.set_thermostat("flat", DigitalThermostatState(Mode.OFF, 21.0))
    sim.set_zone_temperature("flat", 3.0)
    sim.start()
    sim.run_until_true(
        lambda: sim.world.requested,
        OPENING + 3 * REACTION,
        "frost protection opens the valve, runs the pump, and asks the boiler for heat",
    )
    assert sim.flowing("flat.radiators")
    assert sim.desired.mode is Mode.HEAT and sim.desired.frost_protection == ("flat",)
    assert sim.desired.demands["flat"].reason == "frost protection: heat to 6.0 °C from 3.0 °C"

    sim.set_zone_temperature("flat", 5.5)
    sim.always_for(lambda: sim.world.requested, 600.0, "it heats on until 1 K above 5 °C")
    sim.set_zone_temperature("flat", 6.0)
    sim.run_until_true(
        lambda: not any(sim.is_on(entity) for entity in sim.world.switches),
        RUN + 3 * REACTION,
        "everything stops once the zone is 1 K above the frost protection temperature",
    )
    assert sim.desired.frost_protection == ()
    if mode is Mode.OFF:
        assert sim.desired.mode is Mode.OFF


def _cooling_offices() -> Sim:
    sim = Sim(plant(TWO_CEILINGS), mode=Mode.COOL)
    for zone in ("office", "den"):
        sim.set_target(zone, 24.0)
        sim.set_zone_temperature(zone, 26.0)
    sim.start()
    sim.run_until_true(
        lambda: sim.flowing("office.ceiling") and sim.flowing("den.ceiling"),
        OPENING + 2 * REACTION,
        "both ceilings cool",
    )
    return sim


def test_frost_protection_never_heats_while_the_plant_cools() -> None:
    sim = _cooling_offices()
    sim.set_zone_temperature("office", 3.0)
    sim.always_for(
        lambda: sim.desired.frost_protection == () and sim.desired.mode is Mode.COOL,
        DWELL,
        "a zone that cold while cooling has a broken sensor, and cooling goes on for the den",
    )
    assert sim.flowing("den.ceiling") and not sim.flowing("office.ceiling")


def test_frost_protection_after_cooling_waits_for_the_mode_dwell() -> None:
    sim = _cooling_offices()
    sim.set_mode(Mode.OFF)
    sim.run_until_true(
        lambda: not sim.flowing("office.ceiling") and not sim.flowing("den.ceiling"),
        2 * REACTION,
        "cooling stops without overrun",
    )
    ended = sim.checker.last_end[Mode.COOL]
    sim.set_zone_temperature("office", 3.0)
    started = sim.run_until_true(
        lambda: sim.flowing("office.ceiling"),
        DWELL + OPENING + 3 * REACTION,
        "frost protection heats the office once the dwell has passed",
    )
    assert started >= ended + DWELL
    assert not sim.flowing("den.ceiling"), "only the frosty zone heats"


# The exercise


def _idle_reference_plant(*, control: bool = True) -> Sim:
    sim = Sim(reference_plant(), mode=Mode.OFF, control=control)
    sim.start()
    return sim


def test_an_idle_plant_exercises_one_pump_at_a_time_and_never_asks_the_source() -> None:
    sim = _idle_reference_plant()
    sim.run_for(DEFAULT_EXERCISE_INTERVAL - 1.0)
    assert not any(sim.is_on(entity) for entity in sim.world.switches), "nothing is due yet"
    sim.run_for(3600.0)

    assert sim.switched(REQUEST) == [], "an exercise never asks the heat pump for heat"
    ceiling = _on_between(sim, LIVING_CEILING)
    floor_valve, floor_pump = _on_between(sim, FLOOR_VALVE), _on_between(sim, FLOOR_PUMP)
    towel = _on_between(sim, TOWEL_PUMP)
    assert [len(item) for item in (ceiling, floor_valve, floor_pump, towel)] == [1, 1, 1, 1]
    assert ceiling[0][1] - ceiling[0][0] == pytest.approx(OPENING, abs=REACTION), (
        "the heat pump's own loops open until they are ready, then close"
    )
    assert floor_valve[0][0] >= ceiling[0][1], "one pump at a time"
    assert floor_pump[0][0] - floor_valve[0][0] == pytest.approx(OPENING, abs=REACTION)
    assert floor_pump[0][1] - floor_pump[0][0] == pytest.approx(RUN, abs=REACTION), (
        "the pump runs for the exercise's run time, without overrun"
    )
    assert floor_valve[0][1] > floor_pump[0][1], "the valve closes once its pump is seen off"
    assert towel[0][0] >= floor_pump[0][1], "the towel dryer's pump runs after the floor pump"
    assert sim.desired.exercise is None

    sim.run_for(DEFAULT_EXERCISE_INTERVAL - 3600.0)
    assert len(_on_between(sim, FLOOR_PUMP)) == 1, "not again before the interval"
    sim.run_for(3600.0)
    assert len(_on_between(sim, FLOOR_PUMP)) == 2, "and again after it"


def test_an_exercise_in_dry_run_is_proposed_and_never_sent() -> None:
    sim = _idle_reference_plant(control=False)
    sim.run_until_true(
        lambda: sim.desired.exercise is not None,
        DEFAULT_EXERCISE_INTERVAL + REACTION,
        "the exercise is proposed in Dry run",
    )
    sim.run_for(3600.0)
    assert sim.world.calls == []


def test_an_exercise_goes_on_after_a_restart_and_yields_to_demand() -> None:
    sim = Sim(plant(BOILER), mode=Mode.HEAT)
    sim.start()
    sim.run_until_true(
        lambda: sim.is_on(CIRCULATOR),
        DEFAULT_EXERCISE_INTERVAL + OPENING + 2 * REACTION,
        "the circulator is exercised",
    )
    assert sim.restart() == [], "the first evaluation after a restart sends nothing"
    assert sim.desired.exercise == "circulator"

    sim.set_zone_temperature("flat", 19.0)
    sim.run_until_true(
        lambda: sim.world.requested, 2 * REACTION, "the boiler is asked for heat for the demand"
    )
    assert sim.desired.exercise is None
    assert _on_between(sim, CIRCULATOR)[0][1] == sim.t, "the circulator runs on for the demand"
    assert sim.is_on(RADIATOR_VALVE)
    assert sim.switched(BOILER_REQUEST)[0][0] >= sim.switched(CIRCULATOR)[0][0]
