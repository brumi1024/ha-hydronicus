"""Zone demand: fresh readings, aggregation, the dew point, and thermostats."""

from __future__ import annotations

import math

import pytest
from hydronicus_core.demand import (
    AreaSensors,
    DemandState,
    DigitalThermostatState,
    ExternalThermostatState,
    Reading,
    aggregate,
    dew_point,
    external_action,
    fresh,
    worst_dew_point,
    zone_demand,
    zone_values,
)
from hydronicus_core.model import (
    Aggregation,
    DigitalThermostat,
    ExternalThermostat,
    Mode,
    Preset,
    Sensor,
    Zone,
    ZoneArea,
)

NOW = 1_800_000_000.0


class Clock:
    """A ``reached`` callback that records the deadlines it was asked about."""

    def __init__(self, now: float = NOW) -> None:
        self.now = now
        self.deadlines: list[float] = []

    def __call__(self, deadline: float) -> bool:
        if self.now >= deadline:
            return True
        self.deadlines.append(deadline)
        return False


def _zone(**kwargs: object) -> Zone:
    return Zone(slug="room", **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("action", "mode", "expected"),
    [
        ("heating", "heat", Mode.HEAT),
        ("preheating", "auto", Mode.HEAT),
        ("heating", None, Mode.HEAT),
        ("heating", "off", None),
        ("heating", "cool", None),
        ("cooling", "cool", Mode.COOL),
        ("cooling", "heat", None),
        ("idle", "heat", Mode.OFF),
        ("off", "off", Mode.OFF),
        ("drying", "dry", None),
        (None, "heat", None),
    ],
)
def test_an_external_action_is_normalized_against_its_own_mode(
    action: str | None, mode: str | None, expected: Mode | None
) -> None:
    assert external_action(action, mode) is expected


def test_a_reading_is_usable_until_it_is_older_than_its_max_age() -> None:
    clock = Clock()
    assert fresh(Reading(20.0, NOW - 100), 600, clock) == 20.0
    assert clock.deadlines == [NOW + 500], "the evaluation is due when the reading goes stale"
    assert fresh(Reading(20.0, NOW - 601), 600, clock) is None
    assert fresh(Reading(None, NOW), 600, clock) is None
    assert fresh(Reading(math.nan, NOW), 600, clock) is None
    assert fresh(None, 600, clock) is None
    # A reading stamped after now, as after a backward clock step, is fresh.
    assert fresh(Reading(20.0, NOW + 300), 600, clock) == 20.0


def test_zone_values_fail_closed_on_a_required_sensor_and_skip_an_optional_one() -> None:
    zone = _zone(
        temperature=(Sensor("sensor.a"), Sensor("sensor.b", required=False, max_age=60)),
        areas=(ZoneArea("kitchen"), ZoneArea("attic"), ZoneArea("hall", required=True)),
    )
    areas = {"kitchen": AreaSensors("sensor.kitchen", "sensor.kitchen_rh"), "hall": AreaSensors()}
    sensors = {
        "sensor.a": Reading(20.0, NOW),
        "sensor.b": Reading(30.0, NOW - 120),
        "sensor.kitchen": Reading(22.0, NOW),
        "sensor.kitchen_rh": Reading(55.0, NOW),
    }
    clock = Clock()
    # sensor.b is stale and optional; attic is missing and hall names no sensor.
    assert zone_values(zone, areas, sensors, clock) == [20.0, 22.0]
    assert zone_values(zone, areas, sensors, clock, humidity=True) == [55.0]
    assert zone_values(zone, areas, {**sensors, "sensor.a": Reading(None, NOW)}, clock) is None
    assert zone_values(_zone(), {}, {}, clock) is None


def test_aggregation_is_mean_min_or_max() -> None:
    assert aggregate([20.0, 21.0, 25.0], Aggregation.MEAN) == pytest.approx(22.0)
    assert aggregate([20.0, 21.0, 25.0], Aggregation.MIN) == 20.0
    assert aggregate([20.0, 21.0, 25.0], Aggregation.MAX) == 25.0


def test_the_dew_point_follows_magnus_inside_its_range() -> None:
    assert dew_point(26.0, 50.0) == pytest.approx(14.77, abs=0.01)
    assert dew_point(20.0, 100.0) == pytest.approx(20.0)
    for temperature, humidity in [(20.0, 0.0), (20.0, 101.0), (math.inf, 50.0), (-250.0, 50.0)]:
        assert dew_point(temperature, humidity) is None


def test_the_worst_case_dew_point_pairs_the_warmest_and_most_humid_readings() -> None:
    zone = _zone(
        temperature=(Sensor("sensor.t1"), Sensor("sensor.t2")),
        humidity=(Sensor("sensor.h1"), Sensor("sensor.h2")),
    )
    sensors = {
        "sensor.t1": Reading(20.0, NOW),
        "sensor.t2": Reading(26.0, NOW),
        "sensor.h1": Reading(70.0, NOW),
        "sensor.h2": Reading(40.0, NOW),
    }
    assert worst_dew_point(zone, {}, sensors, Clock()) == pytest.approx(dew_point(26.0, 70.0))
    del sensors["sensor.h1"]
    assert worst_dew_point(zone, {}, sensors, Clock()) is None


def _digital(target: float = 21.0, **kwargs: object) -> Zone:
    return _zone(
        temperature=(Sensor("sensor.t"),),
        thermostat=DigitalThermostat(target=target, **kwargs),  # type: ignore[arg-type]
    )


def _demand(
    zone: Zone,
    temperature: float | None,
    previous: DemandState | None = None,
    *,
    mode: Mode = Mode.HEAT,
    target: float = 21.0,
    preset: Preset | None = None,
    clock: Clock | None = None,
) -> tuple[DemandState, bool, float]:
    state, demand = zone_demand(
        zone,
        DigitalThermostatState(mode, target, preset),
        temperature,
        previous,
        NOW,
        clock or Clock(),
    )
    return state, demand.on, demand.level


def test_heating_demand_has_hysteresis_and_a_level() -> None:
    zone = _digital(proportional_band=2.0)
    state, on, level = _demand(zone, 20.7)
    assert on and state == DemandState(Mode.HEAT, True, NOW)
    assert level == pytest.approx(0.15)
    assert _demand(zone, 20.8)[1] is False, "inside the band a zone that was off stays off"
    assert _demand(zone, 21.05, state)[1] is True, "inside the band a zone that was on stays on"
    assert _demand(zone, 21.1, state)[1:] == (False, 0.0)
    assert _demand(zone, 17.0)[2] == 1.0


def test_cooling_demand_mirrors_heating() -> None:
    zone = _digital()
    state, on, _ = _demand(zone, 21.3, mode=Mode.COOL)
    assert on and state.mode is Mode.COOL
    assert _demand(zone, 20.95, state, mode=Mode.COOL)[1] is True
    assert _demand(zone, 20.9, state, mode=Mode.COOL)[1] is False
    # A heating decision does not carry over into cooling.
    heating = DemandState(Mode.HEAT, True, NOW - 10)
    assert _demand(zone, 21.1, heating, mode=Mode.COOL)[1] is False


def test_a_preset_the_thermostat_defines_overrides_the_manual_target() -> None:
    zone = _digital(presets=((Preset.ECO, 18.0),))
    assert _demand(zone, 19.0, preset=Preset.ECO)[1] is False
    assert _demand(zone, 19.0, preset=Preset.AWAY)[1] is True, "an unset preset keeps the target"


def test_minimum_on_and_off_times_hold_a_decision() -> None:
    zone = _digital(min_on=300.0, min_off=120.0)
    clock = Clock()
    on = DemandState(Mode.HEAT, True, NOW - 100)
    state, demand_on, _ = _demand(zone, 22.0, on, clock=clock)
    assert demand_on and state == on
    assert clock.deadlines == [NOW + 200]
    assert _demand(zone, 22.0, DemandState(Mode.HEAT, True, NOW - 300))[1] is False
    off = DemandState(Mode.HEAT, False, NOW - 60)
    assert _demand(zone, 19.0, off)[1] is False
    assert _demand(zone, 19.0, DemandState(Mode.HEAT, False, NOW - 120))[1] is True


def test_demand_fails_closed_without_temperature_or_thermostat() -> None:
    zone = _digital(min_on=600.0)
    on = DemandState(Mode.HEAT, True, NOW - 10)
    state, on_now, _ = _demand(zone, None, on)
    assert not on_now and state == DemandState(Mode.HEAT, False, NOW), "no minimum on time applies"
    assert _demand(zone, 18.0, mode=Mode.OFF)[1] is False
    state, demand = zone_demand(zone, None, 18.0, None, NOW, Clock())
    assert not demand.on and demand.reason == "thermostat not restored"
    # A kept decision keeps the time of its last change.
    off = DemandState(Mode.OFF, False, NOW - 500)
    assert zone_demand(zone, None, 18.0, off, NOW, Clock())[0] is off


def test_an_external_thermostat_demands_from_its_action_only() -> None:
    zone = _zone(thermostat=ExternalThermostat("climate.room"))
    for action, on in [(Mode.HEAT, True), (Mode.COOL, True), (Mode.OFF, False), (None, False)]:
        state, demand = zone_demand(zone, ExternalThermostatState(action), 30.0, None, NOW, Clock())
        assert demand.on is on
        assert demand.level == (1.0 if on else 0.0)
        assert state.mode is (action or Mode.OFF)
