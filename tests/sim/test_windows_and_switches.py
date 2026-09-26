"""Condensation switches and windows, run through their scenarios.

Every scenario also checks the invariants after every event.
"""

from __future__ import annotations

from typing import Final

from custom_components.hydronicus.core.model import Mode
from custom_components.hydronicus.core.step import GUARD_MIN_BLOCKED
from tests.sim.harness import Sim
from tests.sim.plants import BOILER, TWO_CEILINGS, plant

# Seconds for a change of observation to become a physical change.
REACTION: Final = 15.0
OPENING: Final = 180.0
DELAY: Final = 60.0
MIN_ON: Final = 600.0

DEW_SWITCH: Final = "binary_sensor.office_supply_dew_point"
OFFICE_PUMP: Final = "switch.office_pump"
WINDOW: Final = "binary_sensor.flat_window"
RADIATOR_VALVE: Final = "switch.flat_radiator_valve"


def test_a_tripped_condensation_switch_stops_cooling_until_it_has_cleared_for_five_minutes() -> (
    None
):
    text = TWO_CEILINGS.replace(
        "supply_temperature: sensor.office_supply}",
        f"supply_temperature: sensor.office_supply, condensation_switch: {DEW_SWITCH}}}",
    )
    sim = Sim(plant(text), mode=Mode.COOL)
    for zone in ("office", "den"):
        sim.set_zone_temperature(zone, 26.0)
        sim.set_sensor(f"sensor.{zone}_supply", 20.0)
    sim.start()
    sim.run_until_true(
        lambda: sim.flowing("office.ceiling") and sim.flowing("den.ceiling"),
        OPENING + REACTION,
        "both ceilings cool",
    )

    sim.set_contact(DEW_SWITCH, True)
    sim.run_until_true(
        lambda: not sim.is_on(OFFICE_PUMP), REACTION, "the tripped switch stops the office pump"
    )
    assert sim.flowing("den.ceiling"), "a switch covers only the loops of its pump"

    # Unavailable counts as tripped, and the release waits for it to read off.
    sim.run_for(600.0)
    sim.set_contact(DEW_SWITCH, None)
    sim.run_for(600.0)
    sim.set_contact(DEW_SWITCH, False)
    cleared = sim.t
    sim.always_for(
        lambda: not sim.is_on(OFFICE_PUMP),
        GUARD_MIN_BLOCKED - 1.0,
        "the office pump stays off until the switch has read off for five minutes",
    )
    sim.run_until_true(
        lambda: sim.flowing("office.ceiling"),
        OPENING + 2 * REACTION,
        "the office ceiling cools again",
    )
    assert sim.t >= cleared + GUARD_MIN_BLOCKED
    sim.settle(600.0)


def test_an_open_window_stops_heating_through_a_restart_and_resumes_without_a_flap() -> None:
    text = BOILER.replace(
        "    temperature: [sensor.flat_temperature]\n",
        f"    temperature: [sensor.flat_temperature]\n    windows: [{WINDOW}]\n",
    )
    sim = Sim(plant(text), mode=Mode.HEAT)
    sim.set_zone_temperature("flat", 19.0)
    sim.start()
    sim.run_until_true(
        lambda: sim.flowing("flat.radiators"), OPENING + 2 * REACTION, "the flat is heated"
    )

    sim.set_contact(WINDOW, True)
    opened = sim.t
    sim.run_until_true(
        lambda: not sim.is_on(RADIATOR_VALVE), DELAY + OPENING, "the open window closes the valve"
    )
    assert sim.t >= opened + DELAY, "only once the window has been open for its delay"
    assert sim.restart() == [], "a restart keeps the window's inhibit"
    sim.run_for(1800.0)
    assert not sim.is_on(RADIATOR_VALVE)

    sim.set_contact(WINDOW, False)
    closed = sim.t
    sim.run_until_true(
        lambda: sim.is_on(RADIATOR_VALVE), DELAY + REACTION, "the closed window opens the valve"
    )
    assert sim.t >= closed + DELAY, "only once the window has been closed for its delay"

    # Warm enough at once, the zone still keeps its demand for its minimum on time
    # from when it resumed, so the valve does not close before its pump ever ran.
    sim.set_zone_temperature("flat", 21.5)
    sim.always_for(
        lambda: sim.is_on(RADIATOR_VALVE),
        MIN_ON - REACTION,
        "the resumed demand holds for its minimum on time",
    )
    sim.run_until_true(
        lambda: not sim.is_on(RADIATOR_VALVE),
        2 * REACTION + 60.0,
        "the warm flat closes its valve after the minimum on time and the overrun",
    )
    sim.settle(600.0)
