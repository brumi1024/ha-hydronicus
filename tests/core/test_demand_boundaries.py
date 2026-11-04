"""Characterization of digital thermostat hysteresis at and around its boundaries.

These pin the current behaviour of ``zone_demand``: where a call starts and
stops, how minimum times hold a reading that toggles across a boundary, and how
a change of thermostat mode or target acts on a decision that is on.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from custom_components.hydronicus.core.demand import (
    DemandState,
    DigitalThermostatState,
    zone_demand,
)
from custom_components.hydronicus.core.model import DigitalThermostat, Mode, Sensor, Zone

NOW = 1_800_000_000.0


def reached_at(now: float) -> Callable[[float], bool]:
    """A ``reached`` callback for a fixed clock."""
    return lambda deadline: now >= deadline


def thermostat_zone(**settings: float) -> Zone:
    return Zone(
        slug="room",
        temperature=(Sensor("sensor.room"),),
        thermostat=DigitalThermostat(**settings),
    )


def evaluate(
    zone: Zone,
    temperature: float | None,
    previous: DemandState | None = None,
    *,
    mode: Mode = Mode.HEAT,
    target: float = 21.0,
    now: float = NOW,
) -> DemandState:
    state, _ = zone_demand(
        zone, DigitalThermostatState(mode, target), temperature, previous, now, reached_at(now)
    )
    return state


NO_HOLD = {"min_on": 0.0, "min_off": 0.0}


# Boundaries at the default deltas


def test_heating_starts_exactly_at_the_start_delta_below_the_target() -> None:
    zone = thermostat_zone(**NO_HOLD)
    assert evaluate(zone, 20.7).on is True
    assert evaluate(zone, 20.71).on is False


def test_heating_stops_exactly_at_the_stop_delta_above_the_target() -> None:
    zone = thermostat_zone(**NO_HOLD)
    calling = DemandState(Mode.HEAT, True, NOW - 60)
    assert evaluate(zone, 21.09, calling).on is True
    assert evaluate(zone, 21.1, calling).on is False


def test_cooling_starts_and_stops_at_the_mirrored_boundaries() -> None:
    zone = thermostat_zone(**NO_HOLD)
    assert evaluate(zone, 24.3, mode=Mode.COOL, target=24.0).on is True
    assert evaluate(zone, 24.29, mode=Mode.COOL, target=24.0).on is False
    calling = DemandState(Mode.COOL, True, NOW - 60)
    assert evaluate(zone, 23.91, calling, mode=Mode.COOL, target=24.0).on is True
    assert evaluate(zone, 23.9, calling, mode=Mode.COOL, target=24.0).on is False


def test_inside_the_band_the_previous_decision_is_kept() -> None:
    zone = thermostat_zone(**NO_HOLD)
    idle = DemandState(Mode.HEAT, False, NOW - 60)
    calling = DemandState(Mode.HEAT, True, NOW - 60)
    for reading in (20.8, 21.0, 21.05):
        assert evaluate(zone, reading, idle).on is False, reading
        assert evaluate(zone, reading, calling).on is True, reading


# Boundaries at a configured delta of 0.2 K
#
# Sensors report decimal steps such as 0.1 K, and ``zone_demand`` compares the
# float difference to the delta without a tolerance. 21.0 - 20.8 is
# 0.19999999999999929 in floats, so a reading exactly at the boundary misses it
# and a configured 0.2 K delta behaves as 0.3 K.

FLOAT_BOUNDARY = "the delta is compared without a tolerance, so float rounding moves the boundary"


@pytest.mark.xfail(reason=FLOAT_BOUNDARY, strict=True)
def test_heating_starts_exactly_at_a_configured_delta_of_two_tenths() -> None:
    zone = thermostat_zone(heat_start_delta=0.2, **NO_HOLD)
    assert evaluate(zone, 20.8).on is True


@pytest.mark.xfail(reason=FLOAT_BOUNDARY, strict=True)
def test_heating_stops_exactly_at_a_configured_delta_of_two_tenths() -> None:
    zone = thermostat_zone(heat_stop_delta=0.2, **NO_HOLD)
    assert evaluate(zone, 21.2, DemandState(Mode.HEAT, True, NOW - 60)).on is False


@pytest.mark.xfail(reason=FLOAT_BOUNDARY, strict=True)
def test_cooling_starts_exactly_at_a_configured_delta_of_two_tenths() -> None:
    zone = thermostat_zone(cool_start_delta=0.2, **NO_HOLD)
    assert evaluate(zone, 24.2, mode=Mode.COOL, target=24.0).on is True


def test_a_configured_delta_of_two_tenths_starts_one_sensor_step_later_today() -> None:
    """What the xfails above describe, pinned as it behaves now."""
    zone = thermostat_zone(heat_start_delta=0.2, **NO_HOLD)
    assert evaluate(zone, 20.8).on is False
    assert evaluate(zone, 20.7).on is True


# A reading that toggles across a boundary


def test_a_reading_that_toggles_across_the_stop_boundary_is_held_on_for_min_on() -> None:
    zone = thermostat_zone(min_on=300.0, min_off=300.0)
    state = evaluate(zone, 20.5)
    assert state == DemandState(Mode.HEAT, True, NOW)
    # Above the stop boundary, below it, and above it again, all inside min_on.
    for offset, reading in ((60, 21.2), (120, 21.0), (180, 21.2), (299, 21.2)):
        state = evaluate(zone, reading, state, now=NOW + offset)
        assert state == DemandState(Mode.HEAT, True, NOW), offset
    state = evaluate(zone, 21.2, state, now=NOW + 300)
    assert state == DemandState(Mode.HEAT, False, NOW + 300)


def test_a_reading_that_toggles_across_the_start_boundary_is_held_off_for_min_off() -> None:
    zone = thermostat_zone(min_on=300.0, min_off=300.0)
    stopped = DemandState(Mode.HEAT, False, NOW)
    for offset, reading in ((60, 20.6), (120, 20.8), (180, 20.6), (299, 20.6)):
        state = evaluate(zone, reading, stopped, now=NOW + offset)
        assert state == stopped, offset
    assert evaluate(zone, 20.6, stopped, now=NOW + 300) == DemandState(Mode.HEAT, True, NOW + 300)


def test_a_reading_back_inside_the_band_when_min_off_ends_does_not_call() -> None:
    zone = thermostat_zone(min_on=300.0, min_off=300.0)
    stopped = DemandState(Mode.HEAT, False, NOW)
    assert evaluate(zone, 20.8, stopped, now=NOW + 300) == stopped


# A change of thermostat mode or target while heating


def test_turning_the_thermostat_off_ends_a_call_at_once_despite_min_on() -> None:
    zone = thermostat_zone(min_on=600.0, min_off=600.0)
    calling = DemandState(Mode.HEAT, True, NOW - 10)
    assert evaluate(zone, 19.0, calling, mode=Mode.OFF) == DemandState(Mode.OFF, False, None)


def test_heat_off_heat_calls_again_at_once_without_min_off() -> None:
    """Documented: a zone that has not called since its thermostat changed mode may call at once."""
    zone = thermostat_zone(min_on=600.0, min_off=600.0)
    calling = DemandState(Mode.HEAT, True, NOW - 10)
    off = evaluate(zone, 19.0, calling, mode=Mode.OFF, now=NOW)
    assert evaluate(zone, 19.0, off, now=NOW + 5) == DemandState(Mode.HEAT, True, NOW + 5)


def test_heat_cool_heat_drops_the_heating_call_and_starts_it_afresh() -> None:
    zone = thermostat_zone(min_on=600.0, min_off=600.0)
    calling = DemandState(Mode.HEAT, True, NOW - 10)
    cooling = evaluate(zone, 19.0, calling, mode=Mode.COOL, target=24.0, now=NOW)
    assert cooling == DemandState(Mode.COOL, False, None)
    assert evaluate(zone, 19.0, cooling, now=NOW + 5) == DemandState(Mode.HEAT, True, NOW + 5)


def test_lowering_the_target_below_the_room_keeps_a_call_for_min_on() -> None:
    zone = thermostat_zone(min_on=600.0, min_off=600.0)
    calling = DemandState(Mode.HEAT, True, NOW - 10)
    assert evaluate(zone, 20.0, calling, target=18.0) == calling
    assert evaluate(zone, 20.0, calling, target=18.0, now=NOW + 590).on is False


def test_raising_the_target_above_the_room_calls_after_min_off() -> None:
    zone = thermostat_zone(min_on=600.0, min_off=600.0)
    stopped = DemandState(Mode.HEAT, False, NOW - 10)
    assert evaluate(zone, 20.0, stopped, target=23.0) == stopped
    assert evaluate(zone, 20.0, stopped, target=23.0, now=NOW + 590).on is True
