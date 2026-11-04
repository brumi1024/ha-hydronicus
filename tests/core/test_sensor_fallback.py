"""A zone's sensor fallback: a bounded share of heating while it has no usable temperature."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from custom_components.hydronicus.core.model import Mode, Plant
from custom_components.hydronicus.core.plant_file import (
    PlantFileError,
    export_plant,
    read_plant_file,
)
from custom_components.hydronicus.core.step import (
    DigitalThermostatState,
    Observations,
    Reading,
    State,
    step,
)

from .test_step import NOW, RADIATOR, _plant, observe

FALLBACK = RADIATOR.replace(
    "    thermostat: {digital: {min_on: 0, min_off: 0}}",
    "    thermostat: {digital: {min_on: 0, min_off: 0}}\n"
    "    sensor_fallback: {after: 3600, duty: 0.25, period: 7200}",
)
LOST = {"sensor.room": Reading(None, NOW)}


def lost(mode: Mode = Mode.HEAT, thermostat: Mode = Mode.HEAT) -> tuple[Plant, Observations]:
    plant = _plant(FALLBACK)
    observations = observe(plant, mode=mode, sensors=LOST)
    return plant, replace(
        observations, thermostats={"room": DigitalThermostatState(thermostat, 21.0)}
    )


def evaluate(state: State, now: float, **kwargs: Mode) -> tuple[State, bool, str]:
    plant, observations = lost(**kwargs)
    state, desired, _ = step(plant, observations, state, now)
    return state, desired.demands["room"].on, desired.reasons["room"]


def test_it_waits_for_its_after_then_heats_for_its_duty_of_each_period() -> None:
    state = State(live=True, mode=Mode.HEAT)
    state, on, reason = evaluate(state, NOW)
    assert not on and reason == "idle: no usable temperature"
    assert state.sensorless == {"room": NOW}
    state, on, _ = evaluate(state, NOW + 3599)
    assert not on
    state, on, reason = evaluate(state, NOW + 3600)
    assert on
    assert (
        reason == "demands: sensor fallback: heat 25% of every 120 min without a usable temperature"
    )
    state, on, _ = evaluate(state, NOW + 3600 + 1799)
    assert on
    state, on, _ = evaluate(state, NOW + 3600 + 1800)
    assert not on
    state, on, _ = evaluate(state, NOW + 3600 + 7200)
    assert on


def test_its_clock_survives_a_restart() -> None:
    state, _, _ = evaluate(State(live=True, mode=Mode.HEAT), NOW)
    restored = State.from_dict(state.to_dict())
    _, on, _ = evaluate(restored, NOW + 3600)
    assert on


def test_a_returning_reading_ends_it_and_starts_its_clock_again() -> None:
    plant = _plant(FALLBACK)
    state, _, _ = evaluate(State(live=True, mode=Mode.HEAT), NOW)
    state, on, _ = evaluate(state, NOW + 3600)
    assert on
    back = observe(plant, sensors={"sensor.room": Reading(21.0, NOW + 3700)})
    state, desired, _ = step(plant, back, state, NOW + 3700)
    assert not desired.demands["room"].on
    assert state.sensorless == {}
    state, on, _ = evaluate(state, NOW + 3800)
    assert not on and state.sensorless == {"room": NOW + 3800}


@pytest.mark.parametrize(
    ("mode", "thermostat"), [(Mode.COOL, Mode.COOL), (Mode.OFF, Mode.HEAT), (Mode.HEAT, Mode.OFF)]
)
def test_it_never_acts_outside_heating(mode: Mode, thermostat: Mode) -> None:
    state, _, _ = evaluate(State(live=True), NOW, mode=mode, thermostat=thermostat)
    _, on, _ = evaluate(state, NOW + 3600, mode=mode, thermostat=thermostat)
    assert not on


def test_without_a_fallback_the_zone_stays_unheated() -> None:
    plant = _plant(RADIATOR)
    observations = observe(plant, sensors=LOST)
    state, _, _ = step(plant, observations, State(live=True, mode=Mode.HEAT), NOW)
    _, desired, _ = step(plant, observations, state, NOW + 86400)
    assert not desired.demands["room"].on


@given(st.lists(st.floats(1, 900), min_size=20, max_size=200))
def test_it_never_heats_more_than_its_duty(steps: list[float]) -> None:
    """Evaluated at random times and at every deadline it asks for, as the runtime does."""
    plant, observations = lost()
    state, _, _ = step(plant, observations, State(live=True, mode=Mode.HEAT), NOW)
    now = NOW + 3600
    state, desired, due = step(plant, observations, state, now)
    on_time = total = 0.0
    for delta in steps:
        if due is not None:
            delta = min(delta, due)
        if desired.demands["room"].on:
            on_time += delta
        total += delta
        now += delta
        state, desired, due = step(plant, observations, state, now)
    # Within one period the share may run ahead of the duty by one on spell.
    assert on_time <= 0.25 * total + 1800 + 1


def test_the_fallback_survives_an_export() -> None:
    plant = read_plant_file(FALLBACK)
    zone = export_plant(plant)["zones"]["room"]
    assert zone["sensor_fallback"] == {"duty": 0.25}
    default = read_plant_file(FALLBACK.replace("{after: 3600, duty: 0.25, period: 7200}", "true"))
    assert export_plant(default)["zones"]["room"]["sensor_fallback"] is True


@pytest.mark.parametrize(
    ("setting", "path"),
    [
        ("{duty: 0.6}", "zones.room.sensor_fallback.duty"),
        ("{duty: 0.05, period: 7200}", "zones.room.sensor_fallback.duty"),
        ("{after: 60}", "zones.room.sensor_fallback.after"),
        ("{period: 600}", "zones.room.sensor_fallback.period"),
        ("{every: 1}", "zones.room.sensor_fallback.every"),
    ],
)
def test_its_settings_are_checked(setting: str, path: str) -> None:
    text = FALLBACK.replace("{after: 3600, duty: 0.25, period: 7200}", setting)
    with pytest.raises(PlantFileError) as error:
        read_plant_file(text)
    assert error.value.path == path


def test_it_needs_a_digital_thermostat() -> None:
    text = FALLBACK.replace(
        "thermostat: {digital: {min_on: 0, min_off: 0}}", "thermostat: {external: climate.room}"
    )
    with pytest.raises(PlantFileError) as error:
        read_plant_file(text)
    assert error.value.path == "zones.room.sensor_fallback"
