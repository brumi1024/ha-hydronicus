"""The maintainer's house cooling through its ceilings on a summer day.

The heat pump's leaving water, Tw_out, is the ceilings' condensation reference,
and the zone 1 setpoint is the cooling supply target. The simulator has no
cooling physics, so each scenario sets Tw_out where the heat pump would hold
it. Every scenario also checks the invariants after every event, among them
invariant 6: a ceiling cools only while its condensation guard permits.
"""

from __future__ import annotations

from custom_components.hydronicus.core.model import Mode, NumericTarget
from custom_components.hydronicus.core.step import GUARD_MIN_BLOCKED, GUARD_REFERENCE_MAX_AGE
from tests.sim.harness import Sim
from tests.sim.invariants import dew_point
from tests.sim.plants import (
    BASEMENT_CEILING,
    BEDROOM_CEILING,
    FLOOR_PUMP,
    FLOOR_VALVE,
    HEAT_PUMP_MODE,
    HEAT_PUMP_REQUEST,
    HEAT_PUMP_SETPOINT,
    HEAT_PUMP_WATER_OUTLET,
    HOME_HEAT_PUMP,
    LIVING_CEILING,
    plant,
)

REACTION = 15.0
OPENING = 15.0
WRITE_INTERVAL = 300.0
MIN_ON = 1500.0
MIN_OFF = 720.0
DWELL = 7200.0
CEILINGS = (BASEMENT_CEILING, BEDROOM_CEILING, LIVING_CEILING)
ZONES = ("basement", "bedroom_area", "living_area")
# The cooling target is 24 °C, so 25 °C calls and 23.5 °C is satisfied.
WARM = 25.0
COOL = 23.5


def _summer(*, temperature: float = WARM, humidity: float = 45.0) -> Sim:
    sim = Sim(plant(HOME_HEAT_PUMP), mode=Mode.COOL)
    for zone in ZONES:
        sim.set_zone_temperature(zone, temperature)
        sim.set_zone_humidity(zone, humidity)
    sim.set_sensor(HEAT_PUMP_WATER_OUTLET, 18.0)
    sim.start()
    return sim


def _cooling(sim: Sim) -> bool:
    return sim.is_on(HEAT_PUMP_REQUEST) and all(sim.is_on(valve) for valve in CEILINGS)


def _start(sim: Sim) -> float:
    return sim.run_until_true(
        lambda: _cooling(sim), OPENING + 6 * REACTION, "the ceilings cool with the heat pump"
    )


def test_a_cooling_call_sets_the_mode_then_the_setpoint_then_runs_the_ceilings() -> None:
    sim = _summer()
    _start(sim)

    mode = next(call for call in sim.calls_to(HEAT_PUMP_MODE))
    setpoint = next(call for call in sim.calls_to(HEAT_PUMP_SETPOINT))
    request = next(call for call in sim.calls_to(HEAT_PUMP_REQUEST))
    assert mode.t < setpoint.t < request.t, "the setpoint waits for the mode select"
    assert setpoint.target == NumericTarget(18.0, 0.5)
    assert sim.world.number(HEAT_PUMP_SETPOINT) == 18.0
    assert not sim.is_on(FLOOR_VALVE), "the floor heats only"
    assert sim.is_on(FLOOR_PUMP)


def test_a_humid_afternoon_raises_the_setpoint_then_the_guard_and_the_cutoff_block() -> None:
    sim = _summer()
    _start(sim)
    sim.run_for(WRITE_INTERVAL)

    # 60 % at 25 °C: a dew point of 16.7 °C, so the supply must stay at 20.2 °C or above.
    for zone in ZONES:
        sim.set_zone_humidity(zone, 60.0)
    point = dew_point(WARM, 60.0)
    assert point is not None
    sim.run_until_true(
        lambda: not any(sim.is_on(valve) for valve in CEILINGS),
        OPENING + 3 * REACTION,
        "18 °C water is below the dew point and its margin, so the ceilings close",
    )
    assert not sim.is_on(HEAT_PUMP_REQUEST), "the heat pump stops with them"
    assert sim.desired.reasons["living_area.ceiling.guard"].startswith(
        "condensation guard blocks: reference 18.0 °C"
    )
    sim.run_until_true(
        lambda: sim.world.number(HEAT_PUMP_SETPOINT) == 21.0,
        3 * REACTION,
        "the setpoint rises to the next whole degree above the dew point and its margins",
    )
    assert 21.0 >= point + 2.0 + 1.0 + 0.5 > 20.0

    sim.set_sensor(HEAT_PUMP_WATER_OUTLET, 21.0)
    resumed = sim.run_until_true(
        lambda: _cooling(sim),
        GUARD_MIN_BLOCKED + MIN_OFF + OPENING + 6 * REACTION,
        "the ceilings cool again on 21 °C water once the guard releases",
    )
    assert resumed >= GUARD_MIN_BLOCKED

    for zone in ZONES:
        sim.set_zone_humidity(zone, 68.0)
    sim.run_until_true(
        lambda: (
            not any(sim.is_on(valve) for valve in CEILINGS) and not sim.is_on(HEAT_PUMP_REQUEST)
        ),
        OPENING + 3 * REACTION,
        "above 65 % the humidity cutoff stops cooling whatever the water",
    )
    assert "humidity" in sim.desired.reasons["living_area.ceiling.guard"]


def test_a_stale_reference_stops_the_cooling() -> None:
    sim = _summer()
    started = _start(sim)

    sim.set_sensor_stale(HEAT_PUMP_WATER_OUTLET, True)
    sim.always_for(
        lambda: _cooling(sim),
        started + GUARD_REFERENCE_MAX_AGE - sim.t - REACTION,
        "a reference within its maximum age still guards",
    )
    sim.run_until_true(
        lambda: not any(sim.is_on(valve) for valve in CEILINGS),
        OPENING + 3 * REACTION,
        "a stale Tw_out blocks every ceiling",
    )
    assert not sim.is_on(HEAT_PUMP_REQUEST)
    assert HEAT_PUMP_WATER_OUTLET in sim.desired.blocking_condensation_inputs["living_area.ceiling"]

    sim.set_sensor_stale(HEAT_PUMP_WATER_OUTLET, False)
    sim.run_until_true(
        lambda: _cooling(sim),
        GUARD_MIN_BLOCKED + MIN_OFF + OPENING + 6 * REACTION,
        "cooling resumes once Tw_out reports again",
    )


def test_a_handover_while_cooling_stops_the_heat_pump_and_raises_nothing() -> None:
    sim = _summer()
    _start(sim)
    calls = len(sim.calls_to(HEAT_PUMP_REQUEST))

    sim.handover(True, request=False)
    sim.run_for(3600.0)
    assert not sim.is_on(HEAT_PUMP_REQUEST), "the wired controller does not cool unattended"
    assert len(sim.calls_to(HEAT_PUMP_REQUEST)) == calls, "and Hydronicus sends it nothing"
    assert sim.desired.source_handover
    assert sim.repairs() == frozenset()

    sim.handover(False)
    sim.run_until_true(
        lambda: _cooling(sim),
        MIN_OFF + 6 * REACTION,
        "back in control, Hydronicus cools again for the zones that still call",
    )


def test_a_change_to_heating_stops_cooling_waits_the_dwell_and_leaves_the_setpoint() -> None:
    sim = _summer()
    started = _start(sim)

    sim.set_mode(Mode.HEAT)
    for zone in ZONES:
        sim.set_zone_temperature(zone, 19.5)
    stopped = sim.run_until_true(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST) and not sim.is_on(FLOOR_PUMP),
        started + MIN_ON - sim.t + 3 * REACTION,
        "cooling runs out the heat pump's minimum run and stops without an overrun",
    )
    assert stopped >= started + MIN_ON
    setpoint_calls = len(sim.calls_to(HEAT_PUMP_SETPOINT))
    sim.always_for(
        lambda: not sim.is_on(HEAT_PUMP_REQUEST) and not sim.is_on(FLOOR_PUMP),
        stopped + DWELL - sim.t - REACTION,
        "nothing runs during the mode dwell",
    )
    sim.run_until_true(
        lambda: sim.world.option(HEAT_PUMP_MODE) == "Heat" and sim.is_on(HEAT_PUMP_REQUEST),
        OPENING + 6 * REACTION + WRITE_INTERVAL,
        "after the dwell the heat pump heats",
    )
    assert sim.is_on(FLOOR_VALVE)
    assert len(sim.calls_to(HEAT_PUMP_SETPOINT)) == setpoint_calls, (
        "the weather curve keeps the heating setpoint"
    )
    assert sim.desired.reasons["source_supply"] == "kept by the source's own controller in heat"
