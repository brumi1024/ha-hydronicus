"""Comfort targets never alter the user's target, mode, or safety decisions."""

from dataclasses import replace
from math import inf, nan

import pytest

from custom_components.hydronicus.core.comfort import ScheduleState, comfort_target
from custom_components.hydronicus.core.demand import DigitalThermostatState, zone_demand
from custom_components.hydronicus.core.model import (
    DigitalThermostat,
    LearningMode,
    Mode,
    Preset,
    Schedule,
    Zone,
)
from custom_components.hydronicus.core.thermal import RecoveryEstimate
from tests.core.test_demand import NOW, Clock


@pytest.mark.parametrize("mode,target,setback", [(Mode.HEAT, 21.0, 19.0), (Mode.COOL, 24.0, 26.0)])
def test_schedule_selects_comfort_and_directional_setback(
    mode: Mode, target: float, setback: float
) -> None:
    config = DigitalThermostat(schedule=Schedule("schedule.room"))
    for active, expected in ((True, target), (False, setback)):
        clock = Clock()
        result = comfort_target(
            config, mode, target, Preset.SCHEDULE, 20, ScheduleState(active, NOW + 300), NOW, clock
        )
        assert result.target == expected
        assert result.schedule_status == ("comfort" if active else "setback")
        assert not result.early_start
        assert clock.deadlines == [NOW + 300]


@pytest.mark.parametrize("mode,target,expected", [(Mode.HEAT, 5.5, 5.0), (Mode.COOL, 34.5, 35.0)])
def test_setback_is_bounded_to_the_thermostat_range(
    mode: Mode, target: float, expected: float
) -> None:
    result = comfort_target(
        DigitalThermostat(schedule=Schedule("schedule.room")),
        mode,
        target,
        Preset.SCHEDULE,
        20,
        ScheduleState(False),
        NOW,
        Clock(),
    )
    assert result.target == expected


@pytest.mark.parametrize("schedule", [None, ScheduleState(None)])
def test_an_unavailable_schedule_falls_back_to_the_manual_comfort_target(
    schedule: ScheduleState | None,
) -> None:
    config = DigitalThermostat(schedule=Schedule("schedule.room"))
    result = comfort_target(config, Mode.HEAT, 22.3, Preset.SCHEDULE, 20, schedule, NOW, Clock())
    assert result.target == 22.3
    assert result.schedule_status == "unavailable"
    assert not result.early_start


@pytest.mark.parametrize("event", [None, NOW - 1, NOW, nan, inf])
def test_a_missing_or_invalid_future_transition_cannot_start_early(event: float | None) -> None:
    config = DigitalThermostat(schedule=Schedule("schedule.room", max_early_start=3600))
    result = comfort_target(
        config, Mode.HEAT, 21, Preset.SCHEDULE, 10, ScheduleState(False, event), NOW, Clock()
    )
    assert result.target == 19
    assert result.schedule_status == "setback"


@pytest.mark.parametrize(
    "mode,target,temp,rate", [(Mode.HEAT, 21.0, 20.0, 2.0), (Mode.COOL, 24.0, 25.0, 2.0)]
)
def test_early_start_uses_the_mode_rate_and_schedules_its_deadline(
    mode: Mode, target: float, temp: float, rate: float
) -> None:
    config = DigitalThermostat(
        schedule=Schedule(
            "schedule.room", max_early_start=3600, heating_rate=rate, cooling_rate=rate
        )
    )
    event = NOW + 3600
    clock = Clock()
    waiting = comfort_target(
        config, mode, target, Preset.SCHEDULE, temp, ScheduleState(False, event), NOW, clock
    )
    assert not waiting.early_start
    assert clock.deadlines == [event, NOW + 1800]
    early = comfort_target(
        config,
        mode,
        target,
        Preset.SCHEDULE,
        temp,
        ScheduleState(False, event),
        NOW + 1800,
        Clock(NOW + 1800),
    )
    assert early.target == target
    assert early.early_start
    assert early.schedule_status == "early_start"


def test_early_start_is_capped_and_never_acts_in_the_wrong_direction() -> None:
    config = DigitalThermostat(schedule=Schedule("schedule.room", max_early_start=900))
    for mode, temperature in ((Mode.HEAT, 10), (Mode.COOL, 30)):
        clock = Clock()
        result = comfort_target(
            config,
            mode,
            21,
            Preset.SCHEDULE,
            temperature,
            ScheduleState(False, NOW + 1800),
            NOW,
            clock,
        )
        assert not result.early_start
        assert clock.deadlines == [NOW + 1800, NOW + 900]
    for mode, temperature in (
        (Mode.HEAT, 22),
        (Mode.COOL, 20),
        (Mode.HEAT, None),
        (Mode.HEAT, nan),
    ):
        result = comfort_target(
            config,
            mode,
            21,
            Preset.SCHEDULE,
            temperature,
            ScheduleState(False, NOW + 100),
            NOW,
            Clock(),
        )
        assert not result.early_start


def test_manual_mode_and_presets_ignore_schedule_and_use_the_correct_mode() -> None:
    config = DigitalThermostat(
        presets=((Preset.ECO, 18),),
        cool_presets=((Preset.ECO, 27),),
        schedule=Schedule("schedule.room", max_early_start=3600),
    )
    for mode, expected in ((Mode.HEAT, 18), (Mode.COOL, 27)):
        result = comfort_target(
            config, mode, 23, Preset.ECO, 30, ScheduleState(False, NOW + 1), NOW, Clock()
        )
        assert result.target == expected
        assert result.schedule_status == "manual"
    result = comfort_target(
        config, Mode.COOL, 24.7, None, 30, ScheduleState(False, NOW + 1), NOW, Clock()
    )
    assert result.target == 24.7
    assert not result.early_start
    result = comfort_target(
        config, Mode.OFF, 24.7, Preset.SCHEDULE, 30, ScheduleState(False, NOW + 1), NOW, Clock()
    )
    assert result.target == 24.7 and result.schedule_status == "off"
    result = comfort_target(
        replace(config, schedule=None), Mode.COOL, 24.7, Preset.SCHEDULE, 30, None, NOW, Clock()
    )
    assert result.target == 24.7


def test_early_start_stays_at_comfort_until_the_event_but_manual_override_clears_it() -> None:
    config = DigitalThermostat(
        schedule=Schedule("schedule.room", max_early_start=1800), min_on=0, min_off=0
    )
    zone = Zone("room", thermostat=config)
    thermostat = DigitalThermostatState(Mode.HEAT, 21, Preset.SCHEDULE)
    event = NOW + 1800
    schedule = ScheduleState(False, event)
    state, demand = zone_demand(zone, thermostat, 20, None, NOW, Clock(), schedule)
    assert demand.on and state.early_start_event == event
    state, demand = zone_demand(
        zone, thermostat, 21.2, state, NOW + 100, Clock(NOW + 100), schedule
    )
    assert not demand.on and state.early_start_event == event
    assert "early start" in demand.reason
    state, demand = zone_demand(
        zone, replace(thermostat, preset=None), 20, state, NOW + 100, Clock(NOW + 100), schedule
    )
    assert demand.on and state.early_start_event is None
    assert "early start" not in demand.reason


@pytest.mark.parametrize("new_cap", [0, 300])
def test_early_start_latch_does_not_survive_event_change_or_reduced_policy(new_cap: float) -> None:
    event = NOW + 900
    config = DigitalThermostat(schedule=Schedule("schedule.room", max_early_start=1800))
    result = comfort_target(
        config,
        Mode.HEAT,
        21,
        Preset.SCHEDULE,
        22,
        ScheduleState(False, event + 1),
        NOW,
        Clock(),
        event,
    )
    assert not result.early_start
    result = comfort_target(
        replace(config, schedule=Schedule("schedule.room", max_early_start=new_cap)),
        Mode.HEAT,
        21,
        Preset.SCHEDULE,
        20,
        ScheduleState(False, event),
        NOW,
        Clock(),
        event,
    )
    assert not result.early_start
    assert result.early_start_event is None
    assert result.target == 19


def _learned_recovery() -> RecoveryEstimate:
    return RecoveryEstimate(
        3600,
        True,
        "ready",
        "validated independent recovery history",
        valid_until=NOW + 600,
    )


def _assisted_config() -> DigitalThermostat:
    return DigitalThermostat(
        learning=LearningMode.ASSIST,
        schedule=Schedule("schedule.room", max_early_start=3600, heating_rate=2, cooling_rate=2),
    )


@pytest.mark.parametrize("learning", [LearningMode.OFF, LearningMode.OBSERVE])
def test_advisory_learning_cannot_change_the_configured_recovery_plan(
    learning: LearningMode,
) -> None:
    config = replace(_assisted_config(), learning=learning)
    clock = Clock()
    result = comfort_target(
        config,
        Mode.HEAT,
        21,
        Preset.SCHEDULE,
        20,
        ScheduleState(False, NOW + 2700),
        NOW,
        clock,
        recovery=_learned_recovery(),
    )
    assert result.target == 19
    assert not result.early_start
    assert result.recovery_seconds == 1800
    assert result.recovery_method == "configured"
    assert clock.deadlines == [NOW + 2700, NOW + 900]


@pytest.mark.parametrize(
    "mode,preset,schedule,expected_status",
    [
        (Mode.OFF, Preset.SCHEDULE, ScheduleState(False, NOW + 1), "off"),
        (Mode.HEAT, None, ScheduleState(False, NOW + 1), "manual"),
        (Mode.HEAT, Preset.SCHEDULE, ScheduleState(True, NOW + 1), "comfort"),
        (Mode.HEAT, Preset.SCHEDULE, ScheduleState(None), "unavailable"),
    ],
)
def test_a_learned_estimate_cannot_override_manual_off_or_current_comfort(
    mode: Mode,
    preset: Preset | None,
    schedule: ScheduleState,
    expected_status: str,
) -> None:
    result = comfort_target(
        _assisted_config(),
        mode,
        21,
        preset,
        20,
        schedule,
        NOW,
        Clock(),
        recovery=_learned_recovery(),
    )
    assert result.target == 21
    assert result.schedule_status == expected_status
    assert not result.early_start
    assert result.early_start_event is None
    assert result.recovery_seconds is None
    assert result.recovery_method == "configured"


@pytest.mark.parametrize(
    "recovery",
    [
        None,
        replace(_learned_recovery(), confidence=False),
        replace(_learned_recovery(), seconds=None),
        replace(_learned_recovery(), seconds=nan),
        replace(_learned_recovery(), seconds=inf),
        replace(_learned_recovery(), seconds=-1),
        replace(_learned_recovery(), valid_until=None),
        replace(_learned_recovery(), valid_until=nan),
        replace(_learned_recovery(), valid_until=inf),
        replace(_learned_recovery(), valid_until=NOW),
        replace(_learned_recovery(), valid_until=NOW - 1),
    ],
    ids=[
        "missing",
        "unconfident",
        "no-duration",
        "nan-duration",
        "infinite-duration",
        "negative-duration",
        "no-expiry",
        "nan-expiry",
        "infinite-expiry",
        "expired-now",
        "expired-earlier",
    ],
)
def test_an_unusable_estimate_returns_to_the_configured_rate(
    recovery: RecoveryEstimate | None,
) -> None:
    result = comfort_target(
        _assisted_config(),
        Mode.HEAT,
        21,
        Preset.SCHEDULE,
        20,
        ScheduleState(False, NOW + 2700),
        NOW,
        Clock(),
        recovery=recovery,
    )
    assert result.target == 19
    assert not result.early_start
    assert result.early_start_event is None
    assert result.recovery_seconds == 1800
    assert result.recovery_method == "configured"


@pytest.mark.parametrize("weather_aware", [False, True])
def test_weather_recovery_requires_separate_consent(weather_aware: bool) -> None:
    config = replace(_assisted_config(), weather_aware=weather_aware)
    result = comfort_target(
        config,
        Mode.HEAT,
        21,
        Preset.SCHEDULE,
        20,
        ScheduleState(False, NOW + 2700),
        NOW,
        Clock(),
        recovery=replace(_learned_recovery(), weather_adjusted=True),
    )
    assert result.early_start is weather_aware
    assert result.target == (21 if weather_aware else 19)
    assert result.recovery_method == ("weather" if weather_aware else "configured")
    assert result.recovery_seconds == (3600 if weather_aware else 1800)


@pytest.mark.parametrize("mode,temperature", [(Mode.HEAT, 20), (Mode.COOL, 22)])
def test_waiting_and_accepted_learned_proposals_publish_the_same_duration_and_method(
    mode: Mode, temperature: float
) -> None:
    event = NOW + 7200
    recovery = replace(_learned_recovery(), valid_until=NOW + 8000)
    clock = Clock()
    waiting = comfort_target(
        _assisted_config(),
        mode,
        21,
        Preset.SCHEDULE,
        temperature,
        ScheduleState(False, event),
        NOW,
        clock,
        recovery=recovery,
    )
    assert not waiting.early_start
    assert waiting.schedule_status == "setback"
    assert waiting.recovery_seconds == 3600
    assert waiting.recovery_method == "learned"
    assert waiting.target == (19 if mode is Mode.HEAT else 23)
    assert clock.deadlines == [event, recovery.valid_until, event - 3600]
    accepted = comfort_target(
        _assisted_config(),
        mode,
        21,
        Preset.SCHEDULE,
        temperature,
        ScheduleState(False, event),
        NOW + 3600,
        Clock(NOW + 3600),
        recovery=recovery,
    )
    assert accepted.early_start
    assert accepted.target == 21
    assert accepted.schedule_status == "early_start"
    assert accepted.early_start_event == event
    assert accepted.recovery_seconds == waiting.recovery_seconds
    assert accepted.recovery_method == waiting.recovery_method


def test_the_owners_cap_still_limits_a_long_learned_recovery() -> None:
    config = replace(
        _assisted_config(), schedule=Schedule("schedule.room", max_early_start=900, heating_rate=2)
    )
    recovery = replace(_learned_recovery(), seconds=12 * 3600, valid_until=NOW + 2000)
    clock = Clock()
    waiting = comfort_target(
        config,
        Mode.HEAT,
        21,
        Preset.SCHEDULE,
        20,
        ScheduleState(False, NOW + 1800),
        NOW,
        clock,
        recovery=recovery,
    )
    assert not waiting.early_start
    assert waiting.recovery_seconds == 12 * 3600
    assert waiting.recovery_method == "learned"
    assert clock.deadlines == [NOW + 1800, NOW + 2000, NOW + 900]
    accepted = comfort_target(
        config,
        Mode.HEAT,
        21,
        Preset.SCHEDULE,
        20,
        ScheduleState(False, NOW + 1800),
        NOW + 900,
        Clock(NOW + 900),
        recovery=recovery,
    )
    assert accepted.early_start
    assert accepted.early_start_event == NOW + 1800


@pytest.mark.parametrize(
    "recovery",
    [
        None,
        replace(_learned_recovery(), confidence=False),
        replace(_learned_recovery(), seconds=60),
        replace(_learned_recovery(), valid_until=NOW),
    ],
    ids=["forecast-outage", "withdrawn-confidence", "shorter-recovery", "expired-estimate"],
)
def test_an_accepted_event_survives_an_outage_or_a_changed_estimate(
    recovery: RecoveryEstimate | None,
) -> None:
    event = NOW + 2700
    config = replace(_assisted_config(), weather_aware=True)
    accepted = comfort_target(
        config,
        Mode.HEAT,
        21,
        Preset.SCHEDULE,
        20,
        ScheduleState(False, event),
        NOW,
        Clock(),
        recovery=replace(_learned_recovery(), weather_adjusted=True),
    )
    assert accepted.early_start_event == event
    clock = Clock(NOW + 100)
    latched = comfort_target(
        config,
        Mode.HEAT,
        21,
        Preset.SCHEDULE,
        21.2,
        ScheduleState(False, event),
        NOW + 100,
        clock,
        accepted.early_start_event,
        recovery,
    )
    assert latched.early_start
    assert latched.target == 21
    assert latched.early_start_event == event
    assert latched.recovery_method == "latched"
    assert latched.recovery_seconds is None
    assert clock.deadlines == [event]
    manual = comfort_target(
        config,
        Mode.HEAT,
        22,
        None,
        21.2,
        ScheduleState(False, event),
        NOW + 100,
        Clock(NOW + 100),
        accepted.early_start_event,
        recovery,
    )
    assert manual.target == 22
    assert not manual.early_start
    assert manual.early_start_event is None


def test_weather_expiry_rechecks_a_future_plan_before_early_start() -> None:
    config = replace(_assisted_config(), weather_aware=True)
    event = NOW + 6000
    # The adapter must clamp this deadline to forecast expiry when that expires
    # before the model. The pure policy honours the composite deadline.
    recovery = replace(_learned_recovery(), weather_adjusted=True, valid_until=NOW + 600)
    clock = Clock()
    waiting = comfort_target(
        config,
        Mode.HEAT,
        21,
        Preset.SCHEDULE,
        20,
        ScheduleState(False, event),
        NOW,
        clock,
        recovery=recovery,
    )
    assert not waiting.early_start
    assert waiting.recovery_method == "weather"
    assert NOW + 600 in clock.deadlines
    expired = comfort_target(
        config,
        Mode.HEAT,
        21,
        Preset.SCHEDULE,
        20,
        ScheduleState(False, event),
        NOW + 2400,
        Clock(NOW + 2400),
        recovery=recovery,
    )
    assert not expired.early_start
    assert expired.target == 19
    assert expired.recovery_seconds == 1800
    assert expired.recovery_method == "configured"
