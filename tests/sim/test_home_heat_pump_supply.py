"""The maintainer's house: who owns the heating supply temperature of its heat pump.

The heat pump heats on its own weather curve until the owner chooses a fixed
supply temperature on its zone 1 setpoint, from Home Assistant or by switching
the curve off on the wired controller. On 2026-11-09 a curve switched off in
Home Assistant for a warm-up was switched on again within 25 seconds, and the
heating request dropped while it was off; these scenarios pin the fix.
"""

from __future__ import annotations

from custom_components.hydronicus.core.model import HeatingSupply, Mode
from tests.sim.harness import Sim
from tests.sim.plants import (
    HEAT_PUMP_CURVE,
    HEAT_PUMP_CURVE_NUMBER,
    HEAT_PUMP_REQUEST,
    HEAT_PUMP_SETPOINT,
    HOME_HEAT_PUMP,
    plant,
)

REACTION = 15.0
OPENING = 15.0
WRITE_INTERVAL = 300.0
COLD = 19.5
WARM = 21.5


def _heating() -> Sim:
    """The house on the heat pump's own curve, with the bedrooms calling for heat."""
    sim = Sim(plant(HOME_HEAT_PUMP), mode=Mode.HEAT)
    sim.seed_on(HEAT_PUMP_CURVE)
    sim.world.seed_number(HEAT_PUMP_SETPOINT, 30.0)
    sim.world.seed_number(HEAT_PUMP_CURVE_NUMBER, 6.0)
    for zone in ("basement", "living_area"):
        sim.set_zone_temperature(zone, WARM)
    sim.set_zone_temperature("bedroom_area", COLD)
    sim.start()
    sim.run_until_true(
        lambda: sim.is_on(HEAT_PUMP_REQUEST),
        OPENING + 3 * REACTION,
        "the bedrooms' call runs the heat pump on its curve",
    )
    return sim


def _strategy(sim: Sim) -> HeatingSupply:
    supply = sim.desired.heating_supply
    assert supply is not None
    return supply.strategy


def test_the_curve_switched_off_for_a_warm_up_stays_off_and_the_heat_pump_keeps_heating() -> None:
    sim = _heating()
    assert not sim.calls_to(HEAT_PUMP_SETPOINT), "the curve keeps the heating setpoint"

    sim.set_number(HEAT_PUMP_SETPOINT, 34.0)
    sim.switch_elsewhere(HEAT_PUMP_CURVE, False)
    sim.always_for(
        lambda: not sim.is_on(HEAT_PUMP_CURVE) and sim.is_on(HEAT_PUMP_REQUEST),
        3 * WRITE_INTERVAL,
        "the owner's warm-up keeps the curve off and the heat pump heating",
    )
    assert _strategy(sim) is HeatingSupply.FIXED
    assert sim.world.number(HEAT_PUMP_SETPOINT) == 34.0
    assert not sim.calls_to(HEAT_PUMP_CURVE), "Hydronicus never writes the owner's change back"
    assert not sim.calls_to(HEAT_PUMP_SETPOINT), "the controller's own fixed setpoint stays"

    sim.switch_elsewhere(HEAT_PUMP_CURVE, True)
    sim.always_for(
        lambda: sim.is_on(HEAT_PUMP_CURVE) and sim.is_on(HEAT_PUMP_REQUEST),
        WRITE_INTERVAL,
        "the curve back on is the owner's choice too",
    )
    assert _strategy(sim) is HeatingSupply.SOURCE_CURVE


def test_a_fixed_supply_chosen_in_home_assistant_turns_the_curve_off_then_sets_it() -> None:
    sim = _heating()
    sim.command_supply(strategy=HeatingSupply.FIXED, fixed=34.0)
    sim.run_until_true(
        lambda: sim.world.number(HEAT_PUMP_SETPOINT) == 34.0,
        2 * WRITE_INTERVAL + 3 * REACTION,
        "the setpoint follows once the curve is off",
    )
    assert not sim.is_on(HEAT_PUMP_CURVE)
    (curve,) = sim.calls_to(HEAT_PUMP_CURVE)
    assert curve.t < sim.calls_to(HEAT_PUMP_SETPOINT)[0].t
    assert all(on for _, on in sim.switched(HEAT_PUMP_REQUEST)), "heating never stopped"

    sim.command_supply(strategy=HeatingSupply.SOURCE_CURVE)
    sim.run_until_true(
        lambda: sim.is_on(HEAT_PUMP_CURVE),
        WRITE_INTERVAL + 3 * REACTION,
        "back on the heat pump's own curve",
    )
    assert sim.is_on(HEAT_PUMP_REQUEST)


def test_a_warm_up_on_the_curve_holds_a_fixed_temperature_until_the_bedrooms_are_warm() -> None:
    sim = _heating()
    sim.command_supply(warm_up=True)
    sim.run_until_true(
        lambda: sim.world.number(HEAT_PUMP_SETPOINT) == 40.0,
        2 * WRITE_INTERVAL + 3 * REACTION,
        "a warm-up turns the curve off, then holds the setpoint at its temperature",
    )
    assert not sim.is_on(HEAT_PUMP_CURVE) and sim.is_on(HEAT_PUMP_REQUEST)
    (off,) = sim.calls_to(HEAT_PUMP_CURVE)
    assert off.t < sim.calls_to(HEAT_PUMP_SETPOINT)[0].t, "the curve goes off first"
    assert _strategy(sim) is HeatingSupply.SOURCE_CURVE, "the select keeps the curve"

    sim.set_zone_temperature("bedroom_area", WARM)
    sim.run_until_true(
        lambda: sim.is_on(HEAT_PUMP_CURVE),
        WRITE_INTERVAL + 3 * REACTION,
        "once the bedrooms are warm the warm-up ends and the curve comes back",
    )
    supply = sim.desired.heating_supply
    assert supply is not None and not supply.state.warming
    assert _strategy(sim) is HeatingSupply.SOURCE_CURVE, "its own writes are never adopted"
    assert len(sim.calls_to(HEAT_PUMP_CURVE)) == 2, "off and on again, once each"
    assert len(sim.calls_to(HEAT_PUMP_SETPOINT)) == 1, "the setpoint is left as it was"
    assert not sim.calls_to(HEAT_PUMP_CURVE_NUMBER), "the curve number is not touched"
    assert sim.is_on(HEAT_PUMP_REQUEST)
    assert all(on for _, on in sim.switched(HEAT_PUMP_REQUEST)), "heating never stopped"
