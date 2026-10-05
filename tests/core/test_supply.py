"""Fixed and outdoor-compensated source targets preserve bounds and freshness."""

from dataclasses import replace
from math import inf, nan

import pytest

from custom_components.hydronicus.core.demand import Reading
from custom_components.hydronicus.core.model import Mode, SupplyControl
from custom_components.hydronicus.core.supply import SupplyTarget, supply_target

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
