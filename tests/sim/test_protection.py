"""Frost protection and the exercise of idle pumps and valves, over simulated days.

Every scenario also checks the invariants after every event.
"""

from __future__ import annotations

import pytest

from custom_components.hydronicus.core.model import DEFAULT_EXERCISE_INTERVAL, Mode
from custom_components.hydronicus.core.step import EXERCISE_GRACE, DigitalThermostatState
from tests.sim.harness import Sim
from tests.sim.plants import (
    BASEMENT_CEILING,
    BEDROOM_CEILING,
    BOILER,
    FLOOR_PUMP,
    FLOOR_VALVE,
    HEATING_PUMP,
    HOME,
    LIVING_CEILING,
    REQUEST,
    TOWEL_PUMP,
    TWO_CEILINGS,
    plant,
    reference_plant,
)
from tests.sim.world import FaultKind

REACTION = 15.0
OPENING = 180.0
DWELL = 3600.0
RUN = 60.0
DAY = 86400.0

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


def _on_time(sim: Sim, entity: str) -> float:
    return sum(end - start for start, end in _on_between(sim, entity))


def test_an_exercise_gives_up_on_a_valve_that_never_opens_and_moves_on() -> None:
    """The basement valve's relay stops responding just before the heating pump is due."""
    sim = Sim(plant(HOME), mode=Mode.OFF)
    sim.start()
    sim.run_for(DEFAULT_EXERCISE_INTERVAL - 60.0)
    sim.fault(BASEMENT_CEILING, FaultKind.REJECT, 10 * DAY)
    sim.run_for(DAY)

    assert _on_time(sim, HEATING_PUMP) <= 2 * OPENING + RUN + EXERCISE_GRACE, (
        "the heating pump runs until the exercise gives up on the basement valve"
    )
    assert len(_on_between(sim, TOWEL_PUMP)) == 1, "the towel dryer's pump goes next"
    assert sim.state.exercise is None and not any(sim.is_on(e) for e in sim.world.switches)


def test_a_pump_whose_switch_is_unavailable_is_not_exercised_and_holds_up_nothing() -> None:
    sim = Sim(plant(HOME), mode=Mode.OFF)
    sim.start()
    sim.unavailable(HEATING_PUMP)
    sim.run_for(DEFAULT_EXERCISE_INTERVAL + 3600.0)

    assert len(_on_between(sim, TOWEL_PUMP)) == 1, "the towel dryer's pump is exercised"
    assert not any(sim.switched(valve) for valve in (BASEMENT_CEILING, BEDROOM_CEILING)), (
        "the valves of a pump that may run unseen are not opened"
    )
    assert sim.state.exercise is None


def test_a_new_plant_cools_without_the_dwell_after_an_exercise() -> None:
    sim = Sim(plant(TWO_CEILINGS), mode=Mode.OFF)
    sim.start()
    sim.run_for(DEFAULT_EXERCISE_INTERVAL + 3600.0)
    assert _on_between(sim, "switch.office_pump"), "the office's pump was exercised in heat"

    for zone in ("office", "den"):
        sim.set_zone_temperature(zone, 26.0)
    sim.set_mode(Mode.COOL)
    for zone in ("office", "den"):
        sim.set_target(zone, 24.0)
    sim.run_until_true(
        lambda: sim.flowing("office.ceiling"),
        OPENING + 2 * REACTION,
        "the first mode of a new Plant needs no dwell, whatever its exercises did",
    )


def test_a_plant_that_sat_in_dry_run_exercises_its_equipment_once_control_is_on() -> None:
    sim = _idle_reference_plant(control=False)
    sim.run_for(2 * DEFAULT_EXERCISE_INTERVAL)
    assert sim.world.calls == [], "the exercises were only proposed"

    sim.set_control(True)
    sim.run_until_true(
        lambda: sim.is_on(FLOOR_PUMP),
        3 * OPENING + 4 * REACTION,
        "the floor pump is exercised soon after Control equipment turns on",
    )


# The office's ceiling has its own surface sensor.
SURFACE_CEILING = TWO_CEILINGS.replace(
    "ceiling: {valves: [switch.office_ceiling_valve], pump: office, modes: [heat, cool]}",
    "ceiling: {valves: [switch.office_ceiling_valve], pump: office, modes: [heat, cool], "
    "surface_temperature: sensor.office_surface}",
)


def test_after_cooling_a_ceiling_below_its_surface_minimum_is_still_exercised() -> None:
    sim = Sim(plant(SURFACE_CEILING), mode=Mode.COOL)
    sim.set_sensor("sensor.office_surface", 22.0)
    for zone in ("office", "den"):
        sim.set_target(zone, 24.0)
        sim.set_zone_temperature(zone, 26.0)
    sim.start()
    sim.run_until_true(
        lambda: sim.flowing("office.ceiling"), OPENING + 2 * REACTION, "the office cools"
    )
    sim.set_mode(Mode.OFF)
    ended = sim.run_until_true(
        lambda: not sim.flowing("office.ceiling"), 2 * REACTION, "cooling stops"
    )
    # Below its surface minimum the guard blocks cooling, but the dew point is far below.
    sim.set_sensor("sensor.office_surface", 19.0)
    sim.set_zone_humidity("office", 30.0)
    sim.run_for(DEFAULT_EXERCISE_INTERVAL + 3600.0)
    assert sim.runtime is not None and sim.state.guards["office.ceiling"].blocked
    assert any(t > ended and on for t, on in sim.switched("switch.office_pump")), (
        "no chilled water flows in an exercise, so only the checks against condensation apply"
    )
