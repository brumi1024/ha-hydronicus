"""Fixed and outdoor-compensated source targets preserve bounds and freshness."""

from dataclasses import replace
from math import exp, inf, nan

import pytest
from hypothesis import given
from hypothesis import strategies as st

from custom_components.hydronicus.core.demand import Reading
from custom_components.hydronicus.core.model import (
    MAX_CURVE_OFFSET,
    Mode,
    RoomInfluence,
    SupplyControl,
)
from custom_components.hydronicus.core.supply import (
    DampedOutdoor,
    Outdoor,
    SupplyTarget,
    outdoor_temperature,
    room_shift,
    supply_target,
    warm_weather,
)

NOW = 1_800_000_000.0
FIXED = SupplyControl("number.supply")
CURVE = replace(FIXED, outdoor_sensor="sensor.outdoor")


def test_fixed_targets_and_off_do_not_need_a_sensor() -> None:
    assert supply_target(FIXED, Mode.HEAT, {}, NOW) == SupplyTarget(35.0)
    assert supply_target(FIXED, Mode.COOL, {}, NOW) == SupplyTarget(18.0)
    assert supply_target(CURVE, Mode.COOL, {}, NOW) == SupplyTarget(18.0)
    assert supply_target(CURVE, Mode.OFF, {}, NOW) == SupplyTarget(None)


@pytest.mark.parametrize(("outdoor", "target"), [(-40, 45), (-10, 45), (5, 35), (20, 25), (50, 25)])
def test_the_heating_curve_interpolates_and_clamps_its_endpoints(
    outdoor: float, target: float
) -> None:
    assert supply_target(
        CURVE, Mode.HEAT, {"sensor.outdoor": Reading(outdoor, NOW)}, NOW
    ) == SupplyTarget(target)


@pytest.mark.parametrize("mode", [Mode.HEAT, Mode.COOL])
def test_fixed_targets_are_bounded_by_the_configured_limits(mode: Mode) -> None:
    low = replace(FIXED, heat_temperature=-5, cool_temperature=-5)
    high = replace(FIXED, heat_temperature=100, cool_temperature=100)
    assert supply_target(low, mode, {}, NOW).target == 5
    assert supply_target(high, mode, {}, NOW).target == 60


def test_a_curve_is_also_bounded_by_the_configured_limits() -> None:
    config = replace(CURVE, minimum=30, maximum=40)
    assert supply_target(config, Mode.HEAT, {"sensor.outdoor": Reading(-30, NOW)}, NOW).target == 40
    assert supply_target(config, Mode.HEAT, {"sensor.outdoor": Reading(30, NOW)}, NOW).target == 30


@pytest.mark.parametrize(
    ("reading", "reason"),
    [
        (None, "outdoor temperature unavailable"),
        (Reading(None, NOW), "outdoor temperature unavailable"),
        (Reading(nan, NOW), "outdoor temperature invalid"),
        (Reading(inf, NOW), "outdoor temperature invalid"),
        (Reading(5, nan), "outdoor temperature invalid"),
        (Reading(5, NOW - 3600), "outdoor temperature stale"),
        (Reading(5, NOW - 7200), "outdoor temperature stale"),
    ],
)
def test_an_unusable_outdoor_reading_blocks_without_falling_back_to_fixed_heat(
    reading: Reading | None, reason: str
) -> None:
    sensors = {} if reading is None else {"sensor.outdoor": reading}
    assert supply_target(CURVE, Mode.HEAT, sensors, NOW) == SupplyTarget(None, reason)


def test_freshness_uses_the_report_timestamp_and_configured_max_age() -> None:
    config = replace(CURVE, max_age=120)
    assert (
        supply_target(config, Mode.HEAT, {"sensor.outdoor": Reading(5, NOW - 119)}, NOW).target
        == 35
    )
    assert (
        supply_target(config, Mode.HEAT, {"sensor.outdoor": Reading(5, NOW - 120)}, NOW).target
        is None
    )
    # Like other core readings, a backward clock correction retains the reading.
    assert (
        supply_target(config, Mode.HEAT, {"sensor.outdoor": Reading(5, NOW + 120)}, NOW).target
        == 35
    )


@pytest.mark.parametrize(
    "config",
    [
        replace(FIXED, minimum=60, maximum=5),
        replace(FIXED, minimum=5, maximum=5),
        replace(FIXED, minimum=nan),
        replace(FIXED, maximum=inf),
        replace(FIXED, heat_temperature=nan),
        replace(CURVE, outdoor_warm=-10),
        replace(CURVE, outdoor_warm=-20),
        replace(CURVE, heat_cold=inf),
    ],
)
def test_invalid_direct_model_values_never_produce_an_unsafe_numeric_target(
    config: SupplyControl,
) -> None:
    result = supply_target(config, Mode.HEAT, {"sensor.outdoor": Reading(5, NOW)}, NOW)
    assert result.target is None and result.reason is not None


# The heating curve's offset, damping, fallback, heating limit, and room influence


def outdoor_at(value: float) -> dict[str, Reading]:
    return {"sensor.outdoor": Reading(value, NOW)}


def test_the_offset_shifts_heating_targets_within_the_bounds() -> None:
    assert supply_target(replace(FIXED, offset=2), Mode.HEAT, {}, NOW).target == 37
    assert supply_target(FIXED, Mode.HEAT, {}, NOW, offset=-3).target == 32
    assert supply_target(CURVE, Mode.HEAT, outdoor_at(5), NOW, offset=1.5).target == 36.5
    assert supply_target(replace(FIXED, maximum=36), Mode.HEAT, {}, NOW, offset=5).target == 36


def test_the_offset_and_room_shift_never_move_the_cooling_target() -> None:
    assert supply_target(FIXED, Mode.COOL, {}, NOW, offset=5, room_shift=3).target == 18


def test_without_damping_the_curve_follows_the_reading() -> None:
    previous = DampedOutdoor(-10.0, NOW - 600)
    outdoor = outdoor_temperature(CURVE, outdoor_at(5), NOW, previous)
    assert outdoor == Outdoor(5.0, DampedOutdoor(5.0, NOW))


def test_damping_moves_towards_the_reading_by_its_time_constant() -> None:
    config = replace(CURVE, outdoor_damping=3600)
    outdoor = outdoor_temperature(config, outdoor_at(10), NOW, DampedOutdoor(0.0, NOW - 3600))
    assert outdoor is not None and outdoor.value is not None
    assert outdoor.value == pytest.approx(10 * (1 - exp(-1)))
    assert outdoor.damped == DampedOutdoor(outdoor.value, NOW)


@pytest.mark.parametrize(
    "previous", [None, DampedOutdoor(0.0, NOW - 7200), DampedOutdoor(0.0, NOW + 60)]
)
def test_damping_starts_again_after_a_gap_or_a_clock_step(previous: DampedOutdoor | None) -> None:
    config = replace(CURVE, outdoor_damping=3600)
    outdoor = outdoor_temperature(config, outdoor_at(10), NOW, previous)
    assert outdoor is not None and outdoor.value == 10


def test_a_fallback_replaces_an_unusable_reading_and_keeps_the_damped_value() -> None:
    config = replace(CURVE, outdoor_fallback=0.0)
    previous = DampedOutdoor(3.0, NOW - 600)
    outdoor = outdoor_temperature(config, {}, NOW, previous)
    assert outdoor is not None
    assert (outdoor.value, outdoor.fallback, outdoor.damped) == (0.0, True, previous)
    assert (
        outdoor.reason
        == "outdoor temperature unavailable, curve at its fallback of 0.0 °C outdoors"
    )
    assert supply_target(config, Mode.HEAT, {}, NOW, outdoor=outdoor).target == pytest.approx(
        45 - 10 / 30 * 20
    )


def test_frost_protection_heats_at_the_frost_outdoor_without_a_reading_or_fallback() -> None:
    assert supply_target(CURVE, Mode.HEAT, {}, NOW).target is None
    assert supply_target(CURVE, Mode.HEAT, {}, NOW, frost_outdoor=0.0).target == pytest.approx(
        45 - 10 / 30 * 20
    )


@pytest.mark.parametrize(
    ("value", "active", "warm"),
    [(15.9, False, False), (16.0, False, True), (15.5, True, True), (15.0, True, False)],
)
def test_the_heating_limit_starts_at_the_limit_and_ends_one_kelvin_below(
    value: float, active: bool, warm: bool
) -> None:
    config = replace(CURVE, heating_limit=16.0)
    assert warm_weather(config, Outdoor(value), active) is warm


def test_a_fallback_or_a_missing_reading_never_keeps_the_heating_limit() -> None:
    config = replace(CURVE, heating_limit=16.0)
    assert warm_weather(config, Outdoor(20.0, fallback=True), True) is False
    assert warm_weather(config, Outdoor(None), True) is False
    assert warm_weather(CURVE, Outdoor(30.0), True) is False


def test_room_influence_shifts_by_its_factor_within_its_limit() -> None:
    config = replace(CURVE, room_influence=RoomInfluence("living", factor=2.0, limit=3.0))
    assert room_shift(config, 21.0, 20.5) == 1.0
    assert room_shift(config, 21.0, 19.0) == 3.0
    assert room_shift(config, 21.0, 23.0) == -3.0
    assert room_shift(config, None, 20.0) == 0.0
    assert room_shift(config, 21.0, None) == 0.0
    assert room_shift(CURVE, 21.0, 18.0) == 0.0


@given(
    outdoor=st.floats(-40, 40),
    offset=st.floats(-MAX_CURVE_OFFSET, MAX_CURVE_OFFSET),
    shift=st.floats(-6, 6),
)
def test_every_heating_target_stays_in_bounds_and_falls_as_it_warms(
    outdoor: float, offset: float, shift: float
) -> None:
    def target(value: float) -> float:
        result = supply_target(
            CURVE, Mode.HEAT, outdoor_at(value), NOW, offset=offset, room_shift=shift
        ).target
        assert result is not None
        return result

    assert CURVE.minimum <= target(outdoor) <= CURVE.maximum
    assert target(outdoor + 1) <= target(outdoor)
