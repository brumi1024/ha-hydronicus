"""The maintainer's house with its heat pump as the source, through a heating day.

The heat pump heats a plate heat exchanger with no bypass, so the zones are its
only load. Every scenario also checks the invariants after every event, and
invariant 3 is the one this house depends on: the heat pump is requested only
while a zone loop is ready and the pump that loads it runs.
"""

from __future__ import annotations

from dataclasses import replace

from custom_components.hydronicus.core.model import Mode, Plant
from custom_components.hydronicus.core.step import START_WINDOW
from tests.sim.harness import Sim
from tests.sim.plants import (
    BASEMENT_CEILING,
    BEDROOM_CEILING,
    FLOOR_PUMP,
    FLOOR_VALVE,
    HEAT_PUMP_HEALTHY,
    HEAT_PUMP_REQUEST,
    HOME_HEAT_PUMP,
    LIVING_CEILING,
    plant,
)

REACTION = 15.0
OPENING = 15.0
OVERRUN = 240.0
MIN_ON = 1500.0
MIN_OFF = 720.0
# The digital thermostats' target is 21 °C and the heat sink overshoot 0.5 K, so a
# zone at 21.2 °C is satisfied with room for heat, and one at 21.5 °C is full.
WARM = 21.5
ROOM = 21.2
COLD = 19.5
HOLD = 14400.0
VALVES = (BASEMENT_CEILING, BEDROOM_CEILING, LIVING_CEILING, FLOOR_VALVE)


def _house(home: Plant | None = None) -> Sim:
    sim = Sim(home or plant(HOME_HEAT_PUMP), mode=Mode.HEAT)
    for zone in ("basement", "bedroom_area", "living_area"):
        sim.set_zone_temperature(zone, WARM)
    sim.start()
    return sim


def _first(sim: Sim, entity: str, on: bool, after: float = 0.0) -> float:
    return next(t for t, value in sim.switched(entity) if value is on and t >= after)


def _heat_basement(sim: Sim) -> float:
    """Let the basement call and return when the heat pump is requested."""
    sim.set_zone_temperature("basement", COLD)
    return sim.run_until_true(
        lambda: sim.is_on(HEAT_PUMP_REQUEST),
        OPENING + 3 * REACTION,
        "the heat pump is requested once the basement's loop runs",
    )


def _requested_or_open(sim: Sim) -> bool:
    return not sim.is_on(HEAT_PUMP_REQUEST) or (
        sim.is_on(FLOOR_PUMP) and any(sim.is_on(valve) for valve in VALVES)
    )


def test_a_call_opens_the_valve_then_runs_the_pump_then_requests_the_heat_pump() -> None:
    sim = _house()
    called = sim.t

    requested = _heat_basement(sim)

    opened = _first(sim, BASEMENT_CEILING, True)
    pumped = _first(sim, FLOOR_PUMP, True)
    assert called <= opened < pumped < requested
    assert pumped >= opened + OPENING, "the pump waits for the valve's travel and margin"


def test_the_heat_pump_stops_first_and_the_pump_and_valve_overrun() -> None:
    sim = _house()
    requested = _heat_basement(sim)
    sim.run_until(requested + MIN_ON + 60.0)

    sim.set_zone_temperature("basement", WARM)
    released = sim.run_until_true(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST), REACTION, "the heat pump stops first"
    )
    assert sim.is_on(FLOOR_PUMP) and sim.is_on(BASEMENT_CEILING)
    stopped = sim.run_until_true(
        lambda: not sim.is_on(FLOOR_PUMP), OVERRUN + REACTION, "the pump stops after its overrun"
    )
    assert stopped >= released + OVERRUN
    assert sim.is_on(BASEMENT_CEILING), "the last valve stays open while the pump may run"
    sim.run_until_true(
        lambda: not sim.is_on(BASEMENT_CEILING), REACTION, "the valve closes once the pump is off"
    )


def test_a_run_that_outlasts_demand_runs_into_every_heat_sink_until_its_minimum_ends() -> None:
    sim = _house()
    requested = _heat_basement(sim)
    sim.run_for(300.0)

    sim.set_zone_temperature("basement", WARM)
    sim.run_until_true(
        lambda: all(sim.is_on(valve) for valve in VALVES),
        REACTION,
        "every heat sink opens, the satisfied basement among them",
    )
    sim.always_for(
        lambda: sim.is_on(HEAT_PUMP_REQUEST) and sim.is_on(FLOOR_PUMP),
        requested + MIN_ON - sim.t - REACTION,
        "the heat pump runs out its minimum run into the heat sinks, however warm the zones",
    )
    released = sim.run_until_true(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST),
        2 * REACTION,
        "the heat pump stops once its minimum run ends, since every zone is full",
    )
    assert released >= requested + MIN_ON
    sim.run_until_true(
        lambda: not sim.is_on(FLOOR_PUMP) and not any(sim.is_on(valve) for valve in VALVES),
        OVERRUN + 2 * REACTION,
        "every loop closes after the pump's overrun",
    )


def test_the_heat_pump_is_held_after_demand_while_a_heat_sink_has_room() -> None:
    sim = _house()
    for zone in ("bedroom_area", "living_area"):
        sim.set_zone_temperature(zone, ROOM)
    requested = _heat_basement(sim)
    sim.run_until(requested + MIN_ON + 60.0)

    sim.set_zone_temperature("basement", WARM)
    sim.run_until_true(
        lambda: not sim.is_on(BASEMENT_CEILING),
        OPENING + 3 * REACTION,
        "the full basement closes while the zones with room take the heat",
    )
    sim.always_for(
        lambda: (
            sim.is_on(HEAT_PUMP_REQUEST)
            and sim.is_on(FLOOR_VALVE)
            and sim.is_on(BEDROOM_CEILING)
            and sim.is_on(FLOOR_PUMP)
        ),
        1800.0,
        "the heat pump is held into the heat sinks beyond its minimum run",
    )
    assert sim.desired.reasons["source"] == "held after demand, into its heat sink"

    sim.set_zone_temperature("bedroom_area", WARM)
    sim.run_until_true(
        lambda: not sim.is_on(BEDROOM_CEILING),
        OPENING + 3 * REACTION,
        "a heat sink closes once its zone is full",
    )
    assert sim.is_on(HEAT_PUMP_REQUEST)
    assert sim.desired.reasons["bedroom_area.ceiling"] == (
        "heat sink full: bedroom_area reads 21.5 °C"
    )
    sim.set_sensor_available("sensor.living_area_temperature", False)
    sim.run_until_true(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST),
        2 * REACTION,
        "a heat sink whose zone reads nothing has no room, so the heat pump stops",
    )
    assert sim.is_on(FLOOR_PUMP), "the heating pump overruns after the heat pump"


def test_the_hold_after_demand_ends_after_its_time() -> None:
    sim = _house()
    for zone in ("bedroom_area", "living_area"):
        sim.set_zone_temperature(zone, ROOM)
    _heat_basement(sim)
    sim.run_for(600.0)
    sim.set_zone_temperature("basement", WARM)
    ended = sim.t

    sim.always_for(
        lambda: sim.is_on(HEAT_PUMP_REQUEST),
        HOLD - REACTION,
        "the heat pump is held for the whole hold after demand",
    )
    released = sim.run_until_true(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST), 2 * REACTION, "and released at its end"
    )
    assert released >= ended + HOLD


def test_a_call_during_the_hold_needs_no_new_start() -> None:
    sim = _house()
    for zone in ("bedroom_area", "living_area"):
        sim.set_zone_temperature(zone, ROOM)
    _heat_basement(sim)
    sim.run_for(600.0)
    sim.set_zone_temperature("basement", WARM)
    sim.run_for(MIN_ON + 600.0)
    starts = len(sim.state.source_starts)

    sim.set_zone_temperature("basement", COLD)
    sim.always_for(
        lambda: sim.is_on(HEAT_PUMP_REQUEST),
        1800.0,
        "the held heat pump goes on heating for the new call without stopping",
    )
    assert sim.is_on(BASEMENT_CEILING)
    assert sim.desired.reasons["source"] == "requested"
    assert len(sim.state.source_starts) == starts


def test_a_hold_survives_a_restart() -> None:
    sim = _house()
    for zone in ("bedroom_area", "living_area"):
        sim.set_zone_temperature(zone, ROOM)
    _heat_basement(sim)
    sim.run_for(600.0)
    sim.set_zone_temperature("basement", WARM)
    ended = sim.t
    sim.run_for(MIN_ON + 600.0)

    sim.restart()
    sim.always_for(
        lambda: sim.is_on(HEAT_PUMP_REQUEST),
        ended + HOLD - sim.t - REACTION,
        "the hold goes on from where it was",
    )
    sim.run_until_true(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST), 2 * REACTION, "and ends when it would have"
    )


def test_the_heat_pump_never_runs_with_every_valve_closed() -> None:
    sim = _house()
    sim.set_zone_temperature("basement", COLD)
    sim.always_for(lambda: _requested_or_open(sim), 600.0, "a valve is open while requested")
    sim.set_zone_temperature("basement", WARM)
    sim.always_for(lambda: _requested_or_open(sim), MIN_ON + OVERRUN, "and while it winds down")


def test_the_heat_pump_rests_for_its_minimum_off_time() -> None:
    sim = _house()
    requested = _heat_basement(sim)
    sim.run_until(requested + MIN_ON + 60.0)
    sim.set_zone_temperature("basement", WARM)
    released = sim.run_until_true(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST), REACTION, "the heat pump stops"
    )

    sim.set_zone_temperature("bedroom_area", COLD)
    sim.always_for(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST),
        released + MIN_OFF - sim.t - REACTION,
        "the heat pump rests while the bedroom's loop already runs",
    )
    assert sim.is_on(BEDROOM_CEILING) and sim.is_on(FLOOR_PUMP)
    again = sim.run_until_true(
        lambda: sim.is_on(HEAT_PUMP_REQUEST),
        3 * REACTION,
        "the heat pump starts again after its minimum off time",
    )
    assert again >= released + MIN_OFF


def _short_cycles() -> Plant:
    home = plant(HOME_HEAT_PUMP)
    assert home.source is not None
    return replace(home, source=replace(home.source, min_on=120.0, min_off=120.0))


def _cycle(sim: Sim) -> float:
    """Run the heat pump once for its short minimum run and return when it started."""
    started = _heat_basement(sim)
    sim.run_until(started + 130.0)
    sim.set_zone_temperature("basement", WARM)
    sim.run_until_true(lambda: not sim.is_on(HEAT_PUMP_REQUEST), 2 * REACTION, "the short run ends")
    sim.run_for(130.0)
    return started


def test_the_heat_pump_starts_at_most_three_times_an_hour_even_across_a_restart() -> None:
    sim = _house(_short_cycles())
    first = _cycle(sim)
    _cycle(sim)
    _cycle(sim)
    sim.restart()

    sim.set_zone_temperature("basement", COLD)
    sim.always_for(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST),
        first + START_WINDOW - sim.t - REACTION,
        "a fourth start waits until the first start is an hour old",
    )
    assert sim.desired.reasons["source"] == "held off: 3 starts within the last hour"
    fourth = sim.run_until_true(
        lambda: sim.is_on(HEAT_PUMP_REQUEST), 3 * REACTION, "the fourth start comes then"
    )
    assert fourth >= first + START_WINDOW


def test_a_health_fault_stops_the_heat_pump_at_once_and_keeps_it_off() -> None:
    sim = _house()
    requested = _heat_basement(sim)
    sim.run_for(300.0)

    sim.set_contact(HEAT_PUMP_HEALTHY, False)
    sim.run_until_true(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST),
        REACTION,
        "a fault releases the request within its minimum run",
    )
    assert sim.t < requested + MIN_ON
    assert sim.desired.source_fault == f"source health sensor {HEAT_PUMP_HEALTHY} reports a fault"
    sim.set_contact(HEAT_PUMP_HEALTHY, None)
    sim.always_for(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST) and sim.is_on(BASEMENT_CEILING),
        3600.0,
        "the heat pump stays off while its link is lost, and the calling zone still circulates",
    )
    assert sim.desired.source_fault == f"source health sensor {HEAT_PUMP_HEALTHY} is unavailable"

    sim.set_contact(HEAT_PUMP_HEALTHY, True)
    sim.run_until_true(
        lambda: sim.is_on(HEAT_PUMP_REQUEST), 2 * REACTION, "the heat pump resumes once healthy"
    )
    assert sim.desired.source_fault is None


def test_a_start_threshold_waits_for_enough_demand() -> None:
    home = plant(HOME_HEAT_PUMP)
    assert home.source is not None
    sim = _house(replace(home, source=replace(home.source, start_threshold=2.0)))

    sim.set_zone_temperature("basement", COLD)
    sim.always_for(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST), 300.0, "one ceiling loop is not enough demand"
    )
    assert sim.is_on(BASEMENT_CEILING) and sim.is_on(FLOOR_PUMP)
    assert sim.desired.reasons["source"] == "demand 1 below the start threshold 2"

    sim.set_zone_temperature("bedroom_area", COLD)
    sim.run_until_true(
        lambda: sim.is_on(HEAT_PUMP_REQUEST),
        OPENING + 3 * REACTION,
        "two calling loops start the heat pump",
    )
