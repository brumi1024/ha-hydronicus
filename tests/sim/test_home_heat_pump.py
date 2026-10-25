"""The maintainer's house with its heat pump as the source, through a heating day.

The heat pump heats a plate heat exchanger with no bypass, so the zones are its
only load. Every scenario also checks the invariants after every event, and
invariant 3 is the one this house depends on: the heat pump is requested only
while a zone loop is ready and the pump that loads it runs.
"""

from __future__ import annotations

from dataclasses import replace

from custom_components.hydronicus.core.model import Mode, Plant
from custom_components.hydronicus.core.reconcile import STATUS_RETRY
from custom_components.hydronicus.core.step import START_WINDOW
from tests.sim.harness import Sim
from tests.sim.plants import (
    BASEMENT_CEILING,
    BEDROOM_CEILING,
    FIREPLACE_HEATING,
    FLOOR_PUMP,
    FLOOR_VALVE,
    HEAT_PUMP_COMPRESSOR,
    HEAT_PUMP_HEALTHY,
    HEAT_PUMP_REQUEST,
    HEAT_PUMP_WATER_INLET,
    HEAT_PUMP_WATER_OUTLET,
    HOME_HEAT_PUMP,
    LIVING_CEILING,
    plant,
)
from tests.sim.world import FaultKind

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
WRITE_INTERVAL = 300.0
NO_LOAD_DURATION = 600.0
NO_LOAD_HOLD_OFF = 1800.0
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
    return replace(
        home, source=replace(home.source, min_on=120.0, min_off=120.0, write_interval=None)
    )


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


def test_a_handover_keeps_a_heat_sink_open_and_sends_the_heat_pump_nothing() -> None:
    sim = _house()
    sim.run_for(600.0)
    calls = len(sim.calls_to(HEAT_PUMP_REQUEST))

    sim.handover(True, request=True)
    sim.run_until_true(
        lambda: sim.is_on(FLOOR_PUMP) and all(sim.is_on(valve) for valve in VALVES),
        OPENING + 3 * REACTION,
        "every heat sink opens while the wired controller heats",
    )
    assert sim.desired.source_handover
    assert sim.desired.reasons["source"] == "handed over: the source's own controller runs it"
    assert sim.desired.reasons["living_area.floor"] == "heat sink while the source runs by itself"
    sim.always_for(
        lambda: sim.is_on(FLOOR_PUMP) and sim.is_on(FLOOR_VALVE),
        7200.0,
        "the heat sinks stay open, however warm the zones, while the heat pump may heat",
    )
    assert len(sim.calls_to(HEAT_PUMP_REQUEST)) == calls, "the heat pump is sent nothing"
    assert sim.repairs() == frozenset()

    sim.handover(False)
    sim.run_until_true(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST),
        2 * REACTION,
        "back in control, Hydronicus releases the heat pump that no zone needs",
    )
    sim.run_until_true(
        lambda: not sim.is_on(FLOOR_PUMP) and not any(sim.is_on(valve) for valve in VALVES),
        OVERRUN + 2 * REACTION,
        "and closes the heat sinks after the pump's overrun",
    )


def test_a_call_during_a_handover_runs_its_loop_and_hydronicus_takes_over_from_there() -> None:
    sim = _house()
    sim.handover(True, request=True)
    sim.run_for(60.0)

    sim.set_zone_temperature("basement", COLD)
    sim.run_until_true(
        lambda: sim.is_on(BASEMENT_CEILING) and sim.is_on(FLOOR_PUMP),
        OPENING + 3 * REACTION,
        "the calling basement circulates",
    )
    sim.handover(False)
    sim.always_for(
        lambda: sim.is_on(HEAT_PUMP_REQUEST) and sim.is_on(BASEMENT_CEILING),
        1800.0,
        "the heat pump the controller started goes on for the calling zone without a stop",
    )
    assert sim.desired.reasons["source"] == "requested"


def test_a_write_the_bridge_ignores_is_retried_at_its_interval_then_hourly() -> None:
    sim = _house()
    sim.fault(HEAT_PUMP_REQUEST, FaultKind.TIMEOUT, 1800.0)
    sim.set_zone_temperature("basement", COLD)
    sim.run_until_true(
        lambda: bool(sim.calls_to(HEAT_PUMP_REQUEST)),
        OPENING + 3 * REACTION,
        "the heat pump is asked for heat once the basement's loop runs",
    )
    first = sim.calls_to(HEAT_PUMP_REQUEST)[0].t

    sim.run_until(first + 2 * WRITE_INTERVAL - REACTION)
    assert len(sim.calls_to(HEAT_PUMP_REQUEST)) == 2, "retried no faster than the bridge allows"
    assert HEAT_PUMP_REQUEST not in sim.repairs(), "a refusal within the interval raises nothing"
    sim.run_until(first + 2 * WRITE_INTERVAL + REACTION)
    assert HEAT_PUMP_REQUEST in sim.repairs(), "three writes not taken raise the Repair"

    sim.run_until(first + 2 * WRITE_INTERVAL + STATUS_RETRY - REACTION)
    assert len(sim.calls_to(HEAT_PUMP_REQUEST)) == 3, "then the Repair is the status"
    sim.run_until_true(
        lambda: sim.is_on(HEAT_PUMP_REQUEST),
        2 * REACTION,
        "the hourly retry starts the heat pump once the bridge takes writes again",
    )
    sim.run_for(REACTION)
    assert HEAT_PUMP_REQUEST not in sim.repairs()


def test_the_fireplace_buffer_keeps_the_heat_pump_off_while_the_zones_still_heat() -> None:
    sim = _house()
    requested = _heat_basement(sim)
    sim.run_for(300.0)

    sim.set_contact(FIREPLACE_HEATING, True)
    sim.run_until_true(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST),
        REACTION,
        "the heat pump is released at once, within its minimum run",
    )
    assert sim.t < requested + MIN_ON
    assert sim.desired.reasons["source"] == (
        f"another source supplies the zones: {FIREPLACE_HEATING} is on"
    )
    sim.always_for(
        lambda: (
            not sim.is_on(HEAT_PUMP_REQUEST)
            and sim.is_on(BASEMENT_CEILING)
            and sim.is_on(FLOOR_PUMP)
        ),
        3600.0,
        "the basement goes on heating from the buffer",
    )
    assert sim.desired.source_fault is None and sim.repairs() == frozenset()

    sim.set_contact(FIREPLACE_HEATING, False)
    sim.run_until_true(
        lambda: sim.is_on(HEAT_PUMP_REQUEST),
        2 * REACTION,
        "the heat pump heats again once the buffer is no longer selected",
    )


def _running_without_load(sim: Sim) -> None:
    """The compressor runs while the water comes back as warm as it left."""
    sim.set_sensor(HEAT_PUMP_COMPRESSOR, 35.0)
    sim.set_sensor(HEAT_PUMP_WATER_OUTLET, 34.0)
    sim.set_sensor(HEAT_PUMP_WATER_INLET, 33.6)


def test_a_heat_pump_running_without_a_load_is_released_and_held_off() -> None:
    sim = _house()
    requested = _heat_basement(sim)
    sim.set_sensor(HEAT_PUMP_COMPRESSOR, 35.0)
    sim.run_for(300.0)

    _running_without_load(sim)
    tripped = sim.run_until_true(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST),
        NO_LOAD_DURATION + 2 * REACTION,
        "the no-load guard releases the heat pump, within its minimum run",
    )
    assert tripped >= requested + 300.0 + NO_LOAD_DURATION - REACTION
    assert sim.t < requested + MIN_ON
    sim.set_sensor(HEAT_PUMP_COMPRESSOR, 0.0)
    sim.always_for(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST),
        tripped + NO_LOAD_HOLD_OFF - sim.t - REACTION,
        "and holds it off, while the basement still calls",
    )
    assert sim.desired.source_no_load is not None
    assert len(sim.desired.no_load_trips) == 1
    assert abs(sim.desired.no_load_trips[0] - sim.world.wall(tripped)) <= 1.0
    sim.run_until_true(
        lambda: sim.is_on(HEAT_PUMP_REQUEST), 2 * REACTION, "the heat pump may start again then"
    )


def test_a_compressor_that_has_just_started_is_not_taken_for_no_load() -> None:
    sim = _house()
    _heat_basement(sim)
    _running_without_load(sim)

    sim.always_for(
        lambda: sim.is_on(HEAT_PUMP_REQUEST),
        NO_LOAD_DURATION - REACTION,
        "the water needs time to warm after a start",
    )
    sim.set_sensor(HEAT_PUMP_WATER_INLET, 30.0)
    sim.always_for(
        lambda: sim.is_on(HEAT_PUMP_REQUEST), 3600.0, "a heat pump that delivers heat runs on"
    )


def test_arming_the_heat_pump_found_heating_takes_it_over_without_a_stop() -> None:
    home = plant(HOME_HEAT_PUMP)
    sim = Sim(home, mode=Mode.HEAT, armed=set(home.outputs()) - {HEAT_PUMP_REQUEST})
    for zone in ("bedroom_area", "living_area"):
        sim.set_zone_temperature(zone, WARM)
    sim.set_zone_temperature("basement", COLD)
    # Its own controller runs the heat pump into the basement's ceiling.
    sim.seed_on(HEAT_PUMP_REQUEST)
    sim.seed_running("basement.ceiling")
    sim.start()
    sim.run_for(600)
    assert sim.is_on(HEAT_PUMP_REQUEST)

    sim.set_armed(home.outputs())
    sim.run_for(MIN_ON + MIN_OFF)

    assert sim.switched(HEAT_PUMP_REQUEST) == [], "arming a running heat pump stops nothing"
    assert sim.calls_to(HEAT_PUMP_REQUEST) == []
