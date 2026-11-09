"""The DHW schedule's targets and the disinfection cycle."""

from __future__ import annotations

from dataclasses import replace

import pytest

from custom_components.hydronicus.core.dhw import DhwResult, DhwSchedule, DhwState, dhw_step
from custom_components.hydronicus.core.model import Dhw, Disinfect, NumericTarget
from custom_components.hydronicus.core.plant_file import (
    PlantFileError,
    export_plant,
    read_plant_file,
)

NOW = 1_800_000_000.0
DAY = 86400.0
WEEK = 7 * DAY
SWITCH = "switch.dhw"
SETPOINT = "number.dhw_setpoint"
TANK = "sensor.tank"
CYCLE = Disinfect(TANK)
CONFIG = Dhw(switch=SWITCH, setpoint=SETPOINT, disinfect=CYCLE)
OWNED = DhwState(on=True, target=50.0, seen_on=True, seen_target=50.0)


def _step(
    state: DhwState = OWNED,
    now: float = NOW,
    *,
    setpoint: float | None = 50.0,
    tank: float | None = None,
    window: bool | None = None,
    schedule: DhwSchedule | None = None,
    switch: bool | None = True,
    commands: bool = True,
    config: Dhw = CONFIG,
) -> DhwResult:
    return dhw_step(
        config,
        switch,
        setpoint,
        lambda _entity: True,
        state,
        None,
        now,
        lambda at: now >= at,
        commands=commands,
        schedule=schedule,
        tank=tank,
        window=window,
    )


def setpoint(result: DhwResult) -> float | None:
    target = result.targets.get(SETPOINT)
    return target.value if isinstance(target, NumericTarget) else None


# Schedule


def test_a_running_block_holds_its_target_and_a_boost_still_wins() -> None:
    config = replace(CONFIG, disinfect=None, schedule="schedule.dhw")
    result = _step(config=config, schedule=DhwSchedule(True, 54.0))
    assert setpoint(result) == 54.0 and result.reason == "on, scheduled 54 °C"
    assert result.state.target == 50.0, "the owned target is kept"
    assert setpoint(_step(config=config, schedule=DhwSchedule(False, 54.0))) == 50.0
    assert setpoint(_step(config=config, schedule=DhwSchedule(True))) == 50.0
    boosted = replace(OWNED, boost=53.0, boost_until=NOW + 600)
    assert setpoint(_step(boosted, config=config, schedule=DhwSchedule(True, 45.0))) == 53.0


def test_a_scheduled_target_is_kept_within_the_hard_limits() -> None:
    config = replace(CONFIG, disinfect=None, schedule="schedule.dhw")
    assert setpoint(_step(config=config, schedule=DhwSchedule(True, 70.0))) == 55.0


def test_a_scheduled_target_landing_is_not_adopted() -> None:
    config = replace(CONFIG, disinfect=None, schedule="schedule.dhw")
    result = dhw_step(
        config,
        True,
        54.0,
        lambda _entity: False,
        OWNED,
        None,
        NOW,
        lambda at: at <= NOW,
        commands=True,
        schedule=DhwSchedule(True, 54.0),
    )
    assert result.state.target == 50.0 and result.events == ()


# Disinfect


def test_its_clock_starts_when_first_seen() -> None:
    result = _step()
    assert result.state.disinfect_last == NOW
    assert result.state.disinfect_started is None
    assert setpoint(result) == 50.0


def due() -> DhwState:
    return replace(OWNED, disinfect_last=NOW - WEEK)


def test_a_due_cycle_raises_the_setpoint_beyond_the_maximum() -> None:
    result = _step(due())
    assert result.state.disinfect_started == NOW
    assert setpoint(result) == 60.0
    assert result.reason == "on, disinfection cycle at 60 °C"
    assert result.events == ("the disinfection cycle starts, to 60 °C",)


def test_it_finishes_once_the_tank_holds_the_temperature() -> None:
    started = _step(due()).state
    heating = _step(started, NOW + 3600, setpoint=60.0, tank=59.6).state
    assert heating.disinfect_held == NOW + 3600
    done = _step(heating, NOW + 3600 + 1800, setpoint=60.0, tank=60.2)
    assert done.state.disinfect_started is None
    assert done.state.disinfect_last == done.state.disinfect_done == NOW + 5400
    assert setpoint(done) == 50.0
    assert "is done" in done.events[0]


def test_a_cooler_tank_or_a_lost_reading_resets_or_keeps_the_hold() -> None:
    started = _step(due()).state
    held = _step(started, NOW + 600, setpoint=60.0, tank=60.0).state
    kept = _step(held, NOW + 900, setpoint=60.0, tank=None).state
    assert kept.disinfect_held == NOW + 600
    reset = _step(kept, NOW + 1200, setpoint=60.0, tank=55.0).state
    assert reset.disinfect_held is None


def test_it_gives_up_after_its_timeout_and_tries_again_a_day_later() -> None:
    started = _step(due()).state
    failed = _step(started, NOW + 10800, setpoint=60.0, tank=57.0)
    assert failed.state.disinfect_started is None
    assert failed.state.disinfect_failed == NOW + 10800
    assert failed.state.disinfect_done is None
    assert setpoint(failed) == 50.0
    assert _step(failed.state, NOW + 10800 + DAY - 1).state.disinfect_started is None
    assert _step(failed.state, NOW + 10800 + DAY).state.disinfect_started == NOW + 10800 + DAY


@pytest.mark.parametrize(
    ("switch", "commands", "window"),
    [(False, True, None), (True, False, None), (True, True, False)],
)
def test_it_waits_while_the_dhw_is_off_commands_are_held_or_its_window_is_closed(
    switch: bool, commands: bool, window: bool | None
) -> None:
    state = due() if switch else replace(due(), on=False, seen_on=False)
    result = _step(state, switch=switch, commands=commands, window=window)
    assert result.state.disinfect_started is None


def test_it_stops_when_the_dhw_is_turned_off() -> None:
    started = _step(due()).state
    stopped = _step(replace(started, on=False), NOW + 60, switch=False, setpoint=60.0)
    assert stopped.state.disinfect_started is None
    assert "stopped" in stopped.events[-1]


def test_its_state_survives_a_restart() -> None:
    started = _step(due()).state
    assert DhwState.from_dict(started.to_dict()) == started


# Plant file


PLANT = """
hydronicus: 2
name: Flat
source:
  request: switch.boiler
  dhw:
    setpoint: number.dhw_setpoint
    schedule: schedule.dhw
    disinfect: {tank_temperature: sensor.tank, temperature: 65, window: schedule.night}
pumps:
  pump: {switch: switch.pump}
zones:
  flat:
    temperature: [sensor.flat]
    loops:
      radiator: {valves: [switch.valve], pump: pump}
"""


def test_the_dhw_settings_survive_an_export() -> None:
    plant = read_plant_file(PLANT)
    dhw = export_plant(plant)["source"]["dhw"]
    assert dhw["schedule"] == "schedule.dhw"
    assert dhw["disinfect"] == {
        "tank_temperature": "sensor.tank",
        "temperature": 65,
        "window": "schedule.night",
    }


@pytest.mark.parametrize(
    ("old", "new", "path"),
    [
        ("temperature: 65", "temperature: 80", "source.dhw.disinfect.temperature"),
        ("temperature: 65", "timeout: 2000", "source.dhw.disinfect.timeout"),
        ("setpoint: number.dhw_setpoint", "switch: switch.dhw", "source.dhw.disinfect"),
    ],
)
def test_the_disinfect_settings_are_checked(old: str, new: str, path: str) -> None:
    with pytest.raises(PlantFileError) as error:
        read_plant_file(PLANT.replace(old, new))
    assert error.value.path == path
