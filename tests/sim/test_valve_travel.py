"""Valve entities that report their travel, as motorized valves do.

A valve that shows opening or closing is on its way: it is not ready, it may
pass flow, and it is not asked again while it moves. One that stalls on its
way is reported once its opening time and the retries' worth have passed, and
retried. Every scenario also checks the invariants after every event.
"""

from __future__ import annotations

from typing import Final

from custom_components.hydronicus.core.model import Mode, SwitchTarget
from custom_components.hydronicus.core.reconcile import BACKOFF_MAX, TRAVEL_GRACE
from tests.sim.harness import Sim
from tests.sim.plants import plant
from tests.sim.world import EPSILON, FaultKind

REACTION = 15.0
OPENING = 60.0
VALVE: Final = "valve.study_radiator"
PUMP: Final = "switch.radiator_pump"
ON = SwitchTarget(True)

# One zone whose radiator loop has a motorized valve.
MOTORIZED: Final = f"""
hydronicus: 2
name: Motorized
pumps:
  radiators: {{switch: {PUMP}, overrun: 60}}
zones:
  study:
    temperature: [sensor.study_temperature]
    loops:
      radiator:
        valves: [{{entity: {VALVE}, opening_time: {OPENING:.0f}}}]
        pump: radiators
"""


def _calling() -> Sim:
    sim = Sim(plant(MOTORIZED), mode=Mode.HEAT)
    sim.set_zone_temperature("study", 19.0)
    return sim


def test_an_opening_valve_is_waited_for_and_its_opening_time_counts_from_open() -> None:
    sim = _calling()
    sim.run_until_true(lambda: sim.world.moving(VALVE), REACTION, "the valve shows opening")
    arrived = sim.run_until_true(
        lambda: not sim.world.moving(VALVE), OPENING + REACTION, "the valve shows open"
    )
    assert not sim.is_on(PUMP), "the pump does not start while the valve opens"
    started = sim.run_until_true(
        lambda: sim.is_on(PUMP), OPENING + REACTION, "the pump starts once the valve is ready"
    )
    assert started >= arrived + OPENING - EPSILON, "the opening time counts from open"
    assert [call.target for call in sim.calls_to(VALVE)] == [ON], (
        "the valve is not asked again while it opens"
    )


def test_a_valve_that_stalls_while_opening_is_reported_and_retried() -> None:
    sim = _calling()
    sim.fault(VALVE, FaultKind.STALL, 900.0)
    sim.run_until_true(lambda: sim.world.moving(VALVE), REACTION, "the valve shows opening")
    sim.always_for(
        lambda: VALVE not in sim.repairs() and len(sim.calls_to(VALVE)) == 1,
        OPENING + TRAVEL_GRACE - REACTION,
        "a valve on its way is neither reported nor asked again",
    )
    sim.run_until_true(
        lambda: VALVE in sim.repairs(), 2 * REACTION, "a valve that does not arrive is reported"
    )
    assert not sim.is_on(PUMP), "the pump waits for a valve that does not arrive"
    sim.run_until_true(
        lambda: sim.is_on(PUMP),
        900.0 + BACKOFF_MAX + 2 * OPENING + REACTION,
        "a retry after the stall moves the valve, and the pump runs once it is ready",
    )
    assert VALVE not in sim.repairs(), "the Repair clears once the valve arrives"
