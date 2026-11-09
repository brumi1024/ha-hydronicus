"""The heat pump's DHW, which Hydronicus owns through the bridge.

A change on the wired controller is adopted and never written back, a target
outside 40 to 55 °C is clamped, and a boost raises T5S for a bounded time and
restores it, also across a restart and a lost link. The bridge's write interval
applies to the DHW outputs as to the source's others.
"""

from __future__ import annotations

from custom_components.hydronicus.core.model import Mode, NumericTarget
from tests.sim.harness import Sim
from tests.sim.plants import HEAT_PUMP_DHW, HEAT_PUMP_DHW_SETPOINT, HOME_HEAT_PUMP, plant

REACTION = 15.0
WRITE_INTERVAL = 300.0
MAX_BOOST = 10800.0


def _home() -> Sim:
    sim = Sim(plant(HOME_HEAT_PUMP), mode=Mode.HEAT)
    sim.world.seed_number(HEAT_PUMP_DHW_SETPOINT, 50.0)
    sim.seed_on(HEAT_PUMP_DHW)
    sim.start()
    return sim


def _setpoint(sim: Sim) -> float:
    return sim.world.number(HEAT_PUMP_DHW_SETPOINT)


def test_hydronicus_takes_the_dhw_as_it_finds_it_and_sends_nothing() -> None:
    sim = _home()
    sim.run_for(3600.0)

    assert sim.desired.dhw is not None
    assert (sim.desired.dhw.on, sim.desired.dhw.target) == (True, 50.0)
    assert sim.calls_to(HEAT_PUMP_DHW) == sim.calls_to(HEAT_PUMP_DHW_SETPOINT) == []


def test_the_owner_changes_the_dhw_through_hydronicus() -> None:
    sim = _home()
    sim.command_dhw(target=52.0, on=False)
    sim.run_until_true(
        lambda: _setpoint(sim) == 52.0 and not sim.is_on(HEAT_PUMP_DHW),
        REACTION,
        "the DHW target and switch follow the owner",
    )
    sim.command_dhw(target=53.0)
    sim.run_for(WRITE_INTERVAL - REACTION)
    assert _setpoint(sim) == 52.0, "the bridge's write interval holds the next write"
    sim.run_until_true(lambda: _setpoint(sim) == 53.0, 2 * REACTION, "then it is written")


def test_a_change_on_the_wired_controller_is_adopted_and_never_written_back() -> None:
    sim = _home()
    sim.run_for(60.0)

    sim.set_number(HEAT_PUMP_DHW_SETPOINT, 47.0)
    sim.world.set_switch(HEAT_PUMP_DHW, False)
    sim.run_for(3600.0)
    assert sim.desired.dhw is not None
    assert (sim.desired.dhw.on, sim.desired.dhw.target) == (False, 47.0)
    assert sim.calls_to(HEAT_PUMP_DHW) == sim.calls_to(HEAT_PUMP_DHW_SETPOINT) == []


def test_a_target_beyond_the_hard_limit_is_clamped() -> None:
    sim = _home()
    sim.run_for(WRITE_INTERVAL)

    sim.set_number(HEAT_PUMP_DHW_SETPOINT, 60.0)
    sim.run_until_true(
        lambda: _setpoint(sim) == 55.0, 2 * REACTION, "a 60 °C set on the controller becomes 55 °C"
    )
    assert sim.desired.dhw is not None and sim.desired.dhw.target == 55.0


def test_a_boost_is_restored_on_time_across_a_restart() -> None:
    sim = _home()
    sim.command_dhw(boost=55.0, boost_for=3600.0)
    boosted = sim.run_until_true(lambda: _setpoint(sim) == 55.0, REACTION, "the boost raises T5S")
    sim.run_for(1800.0)

    sim.restart()
    sim.always_for(
        lambda: _setpoint(sim) == 55.0,
        boosted + 3600.0 - sim.t - REACTION,
        "the boost goes on after the restart",
    )
    sim.run_until_true(
        lambda: _setpoint(sim) == 50.0, 2 * REACTION, "and T5S is restored when it would have ended"
    )


def test_a_boost_that_ends_while_the_link_is_lost_is_restored_when_it_returns() -> None:
    sim = _home()
    sim.command_dhw(boost=54.0)
    sim.run_until_true(lambda: _setpoint(sim) == 54.0, REACTION, "the boost raises T5S")

    sim.unavailable(HEAT_PUMP_DHW_SETPOINT, MAX_BOOST + 600.0)
    sim.run_for(MAX_BOOST + 600.0 - REACTION)
    assert _setpoint(sim) == 54.0
    sim.run_until_true(
        lambda: _setpoint(sim) == 50.0, 3 * REACTION, "T5S is restored once the link is back"
    )
    assert sim.desired.dhw is not None and sim.desired.dhw.target == 50.0


def test_a_change_on_the_controller_during_a_boost_ends_it_without_restoring() -> None:
    sim = _home()
    sim.command_dhw(boost=55.0, boost_for=3600.0)
    sim.run_until_true(lambda: _setpoint(sim) == 55.0, REACTION, "the boost raises T5S")
    sim.run_for(600.0)

    sim.set_number(HEAT_PUMP_DHW_SETPOINT, 48.0)
    sim.run_for(7200.0)
    assert _setpoint(sim) == 48.0
    assert sim.desired.dhw is not None and sim.desired.dhw.boost_until is None


def test_a_handover_sends_the_dhw_nothing_and_adopts_what_the_controller_did() -> None:
    sim = _home()
    sim.run_for(600.0)
    sim.handover(True)

    sim.command_dhw(target=45.0)
    sim.run_for(60.0)
    sim.set_number(HEAT_PUMP_DHW_SETPOINT, 49.0)
    sim.run_for(3600.0)
    assert sim.calls_to(HEAT_PUMP_DHW_SETPOINT) == []
    assert sim.desired.dhw is not None and sim.desired.dhw.target == 49.0

    sim.handover(False)
    sim.run_for(600.0)
    assert sim.calls_to(HEAT_PUMP_DHW_SETPOINT) == [], "the adopted value needs no write"


def test_dry_run_proposes_the_dhw_and_sends_nothing() -> None:
    sim = Sim(plant(HOME_HEAT_PUMP), mode=Mode.HEAT, control=False)
    sim.world.seed_number(HEAT_PUMP_DHW_SETPOINT, 50.0)
    sim.start()
    sim.command_dhw(target=45.0)
    sim.run_for(600.0)

    assert sim.desired.outputs[HEAT_PUMP_DHW_SETPOINT] == NumericTarget(45.0, 0.5)
    assert sim.calls_to(HEAT_PUMP_DHW_SETPOINT) == []
    assert _setpoint(sim) == 50.0
