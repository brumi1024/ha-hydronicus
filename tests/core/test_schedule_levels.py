"""A schedule block's data chooses its level, and early start recovers towards the next one."""

from math import inf, nan

import pytest

from custom_components.hydronicus.core.comfort import (
    BlockLevel,
    ComfortTarget,
    ScheduleState,
    Setbacks,
    block_level,
    comfort_target,
    next_period_target,
)
from custom_components.hydronicus.core.model import DigitalThermostat, Mode, Preset, Schedule
from tests.core.test_demand import NOW, Clock

CONFIG = DigitalThermostat(
    presets=((Preset.ECO, 19.0), (Preset.AWAY, 16.0)),
    cool_presets=((Preset.ECO, 26.0),),
    schedule=Schedule("schedule.room", max_early_start=7200, heating_rate=1, cooling_rate=1),
)
ECO = BlockLevel(preset=Preset.ECO)


@pytest.mark.parametrize(
    "data,expected",
    [
        (None, BlockLevel()),
        ({}, BlockLevel()),
        ({"owner": "anything"}, BlockLevel()),
        ({"preset": "eco"}, BlockLevel(preset=Preset.ECO)),
        ({"preset": "away", "note": "holiday"}, BlockLevel(preset=Preset.AWAY)),
        ({"heat_target": 20}, BlockLevel(heat_target=20.0)),
        ({"heat_target": 20.5, "cool_target": 25}, BlockLevel(heat_target=20.5, cool_target=25.0)),
    ],
)
def test_block_data_names_a_preset_or_targets_and_other_keys_are_the_owners(
    data: dict[str, object] | None, expected: BlockLevel
) -> None:
    assert block_level(data) == expected


@pytest.mark.parametrize(
    "data,fragment",
    [
        ({"preset": "schedule"}, "preset must be one of"),
        ({"preset": "boost"}, "preset must be one of"),
        ({"preset": 3}, "preset must be one of"),
        ({"preset": "eco", "heat_target": 20}, "not both"),
        ({"heat_target": True}, "heat_target must be a number"),
        ({"heat_target": "20"}, "heat_target must be a number"),
        ({"cool_target": 36}, "cool_target must be a number"),
        ({"heat_target": 4.5}, "heat_target must be a number"),
        ({"heat_target": nan}, "heat_target must be a number"),
        ({"heat_target": inf}, "heat_target must be a number"),
    ],
)
def test_unusable_block_data_is_reported_not_guessed(
    data: dict[str, object], fragment: str
) -> None:
    level = block_level(data)
    assert level.error is not None and fragment in level.error
    assert level.preset is None and level.heat_target is None and level.cool_target is None


def _active(level: BlockLevel, mode: Mode = Mode.HEAT, manual: float = 21.0) -> ComfortTarget:
    return comfort_target(
        CONFIG,
        mode,
        manual,
        Preset.SCHEDULE,
        20,
        ScheduleState(True, NOW + 3600, level),
        NOW,
        Clock(),
    )


@pytest.mark.parametrize(
    "level,mode,target,name,reason",
    [
        (BlockLevel(), Mode.HEAT, 21.0, "comfort", "scheduled comfort"),
        (ECO, Mode.HEAT, 19.0, "eco", "scheduled eco"),
        (ECO, Mode.COOL, 26.0, "eco", "scheduled eco"),
        (BlockLevel(preset=Preset.AWAY), Mode.HEAT, 16.0, "away", "scheduled away"),
        (BlockLevel(heat_target=20.0), Mode.HEAT, 20.0, "target", "scheduled target"),
        (BlockLevel(cool_target=25.0), Mode.COOL, 25.0, "target", "scheduled target"),
    ],
)
def test_an_active_block_holds_its_level_in_the_current_mode(
    level: BlockLevel, mode: Mode, target: float, name: str, reason: str
) -> None:
    result = _active(level, mode)
    assert result.target == target
    assert result.schedule_level == name
    assert result.schedule_status == "comfort"
    assert result.reason == reason


@pytest.mark.parametrize(
    "level,mode,reason",
    [
        (BlockLevel(preset=Preset.AWAY), Mode.COOL, "scheduled away is not a cooling preset"),
        (BlockLevel(cool_target=25.0), Mode.HEAT, "scheduled block has no heating target"),
        (BlockLevel(heat_target=20.0), Mode.COOL, "scheduled block has no cooling target"),
    ],
)
def test_a_level_the_mode_cannot_use_holds_manual_comfort_and_says_why(
    level: BlockLevel, mode: Mode, reason: str
) -> None:
    manual = 24.0 if mode is Mode.COOL else 21.0
    result = _active(level, mode, manual)
    assert result.target == manual
    assert result.schedule_level == "comfort"
    assert result.schedule_status == "comfort"
    assert result.reason == reason


def test_an_invalid_block_holds_manual_comfort_with_its_own_status() -> None:
    result = _active(block_level({"preset": "eco", "heat_target": 20}))
    assert result.target == 21.0
    assert result.schedule_status == "invalid_block"
    assert result.reason.startswith("invalid schedule block")


@pytest.mark.parametrize("mode,manual,expected", [(Mode.HEAT, 21.0, 17.5), (Mode.COOL, 24.0, 27.0)])
def test_the_owners_setbacks_replace_the_configured_ones(
    mode: Mode, manual: float, expected: float
) -> None:
    result = comfort_target(
        CONFIG,
        mode,
        manual,
        Preset.SCHEDULE,
        manual,
        ScheduleState(False, NOW + 60),
        NOW,
        Clock(),
        setbacks=Setbacks(heat=3.5, cool=3.0),
    )
    assert result.target == expected
    assert result.schedule_level == "setback"


def test_early_start_from_an_off_period_aims_at_the_next_blocks_level() -> None:
    event = NOW + 7200
    schedule = ScheduleState(False, event, next_active=True, next_level=ECO)
    # Setback is 19 (21 - 2) and the next block is eco at 19: nothing to recover.
    held = comfort_target(CONFIG, Mode.HEAT, 21, Preset.SCHEDULE, 18, schedule, NOW, Clock())
    assert not held.early_start and held.target == 19.0
    away = ScheduleState(False, event, next_active=True, next_level=BlockLevel(heat_target=20.5))
    clock = Clock()
    waiting = comfort_target(CONFIG, Mode.HEAT, 21, Preset.SCHEDULE, 19, away, NOW, clock)
    # 1.5 K at 1 K/h is 5400 s, inside the two-hour cap, so the deadline is the event minus it.
    assert not waiting.early_start and waiting.recovery_seconds == 5400
    assert clock.deadlines == [event, event - 5400]
    early = comfort_target(
        CONFIG, Mode.HEAT, 21, Preset.SCHEDULE, 19, away, event - 5400, Clock(event - 5400)
    )
    assert early.early_start and early.target == 20.5
    assert early.schedule_status == "early_start" and early.schedule_level == "target"


def test_early_start_raises_a_lower_block_to_the_next_ones_level() -> None:
    event = NOW + 3600
    schedule = ScheduleState(True, event, ECO, next_active=True, next_level=BlockLevel())
    early = comfort_target(CONFIG, Mode.HEAT, 21, Preset.SCHEDULE, 19, schedule, NOW, Clock())
    # 2 K at 1 K/h is two hours, more than the hour left, so it starts now.
    assert early.early_start and early.target == 21.0
    assert early.schedule_level == "comfort"


@pytest.mark.parametrize(
    "schedule",
    [
        ScheduleState(True, NOW + 600, next_active=True, next_level=ECO),
        ScheduleState(True, NOW + 600, next_active=False),
        ScheduleState(True, NOW + 600),
    ],
)
def test_no_early_start_towards_a_lower_or_unknown_period(schedule: ScheduleState) -> None:
    result = comfort_target(CONFIG, Mode.HEAT, 21, Preset.SCHEDULE, 15, schedule, NOW, Clock())
    assert not result.early_start
    assert result.target == 21.0 and result.recovery_seconds is None


def test_cooling_recovers_downwards_towards_the_next_level() -> None:
    event = NOW + 3600
    schedule = ScheduleState(True, event, ECO, next_active=True, next_level=BlockLevel())
    early = comfort_target(CONFIG, Mode.COOL, 24, Preset.SCHEDULE, 26, schedule, NOW, Clock())
    assert early.early_start and early.target == 24.0


def test_a_latched_early_start_keeps_the_next_levels_target() -> None:
    event = NOW + 600
    schedule = ScheduleState(False, event, next_active=True, next_level=BlockLevel(heat_target=22))
    latched = comfort_target(
        CONFIG, Mode.HEAT, 21, Preset.SCHEDULE, 22, schedule, NOW, Clock(), early_start_event=event
    )
    assert latched.early_start and latched.target == 22.0
    assert latched.recovery_method == "latched" and latched.schedule_level == "target"


@pytest.mark.parametrize(
    "schedule,mode,expected",
    [
        (ScheduleState(False, NOW + 60), Mode.HEAT, 21.0),
        (ScheduleState(True, NOW + 60), Mode.HEAT, None),
        (ScheduleState(True, NOW + 60, next_active=False), Mode.HEAT, 19.0),
        (ScheduleState(True, NOW + 60, next_active=False), Mode.COOL, 23.0),
        (ScheduleState(False, NOW + 60, next_active=True, next_level=ECO), Mode.HEAT, 19.0),
        (ScheduleState(False, NOW + 60, next_active=True, next_level=ECO), Mode.OFF, None),
        (
            ScheduleState(False, NOW + 60, next_active=True, next_level=block_level({"preset": 1})),
            Mode.HEAT,
            21.0,
        ),
    ],
)
def test_the_next_periods_target(
    schedule: ScheduleState, mode: Mode, expected: float | None
) -> None:
    manual = 21.0
    assert next_period_target(CONFIG, mode, manual, schedule) == expected


def test_a_thermostat_without_a_schedule_has_no_next_period() -> None:
    config = DigitalThermostat()
    assert next_period_target(config, Mode.HEAT, 21, ScheduleState(False, NOW + 60)) is None
