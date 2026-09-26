"""Home Assistant states read as observations: units, plausibility, and the output memory."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from homeassistant.core import State
from hypothesis import given
from hypothesis import strategies as st

from custom_components.hydronicus.core.model import Mode
from custom_components.hydronicus.observe import (
    OutputMemory,
    SensorKind,
    celsius_from_unit,
    external_thermostat,
    option_value,
    reading,
    switch_value,
)

WHEN = datetime(2026, 9, 25, 12, tzinfo=UTC)


def state(value: str, **attributes: object) -> State:
    return State("sensor.x", value, attributes, last_changed=WHEN, last_reported=WHEN)


@given(st.floats(min_value=-50.0, max_value=100.0, allow_nan=False))
def test_a_fahrenheit_reading_is_the_same_temperature_in_celsius(celsius: float) -> None:
    fahrenheit = celsius * 9 / 5 + 32
    observed = reading(state(str(fahrenheit), unit_of_measurement="°F"), SensorKind.AIR, 0.0)
    assert observed.value == pytest.approx(celsius, abs=1e-6)
    assert observed.updated == WHEN.timestamp()


@pytest.mark.parametrize(
    ("value", "unit", "kind", "expected"),
    [
        ("21.5", "°C", SensorKind.AIR, 21.5),
        ("21.5", None, SensorKind.AIR, 21.5),
        ("294.15", "K", SensorKind.AIR, 21.0),
        ("-127", "°C", SensorKind.AIR, None),
        ("120", "°C", SensorKind.WATER, 120.0),
        ("120", "°C", SensorKind.AIR, None),
        ("55", "%", SensorKind.HUMIDITY, 55.0),
        ("55", "g/m³", SensorKind.HUMIDITY, None),
        ("21", "W", SensorKind.AIR, None),
        ("unavailable", "°C", SensorKind.AIR, None),
        ("nan", "°C", SensorKind.AIR, None),
    ],
)
def test_readings_outside_their_unit_or_plausible_range_carry_no_value(
    value: str, unit: str | None, kind: SensorKind, expected: float | None
) -> None:
    attributes = {} if unit is None else {"unit_of_measurement": unit}
    observed = reading(state(value, **attributes), kind, 0.0)
    assert observed.value == (None if expected is None else pytest.approx(expected))


def test_a_missing_sensor_reads_as_reported_now() -> None:
    assert reading(None, SensorKind.AIR, 42.0).updated == 42.0
    assert celsius_from_unit(10.0, "") == 10.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("on", True),
        ("open", True),
        ("opening", True),
        ("off", False),
        ("closed", False),
        ("closing", False),
        ("unavailable", None),
        ("unknown", None),
    ],
)
def test_switches_and_valves_read_as_commanded(value: str, expected: bool | None) -> None:
    assert switch_value(state(value)) is expected


def test_selects_and_external_thermostats() -> None:
    assert option_value(state("Heat")) == "Heat"
    assert option_value(state("unavailable")) is None
    assert option_value(None) is None
    assert external_thermostat(state("heat", hvac_action="heating")).action is Mode.HEAT
    assert external_thermostat(state("cool", hvac_action="heating")).action is None
    assert external_thermostat(state("heat", hvac_action="idle")).action is Mode.OFF
    assert external_thermostat(state("unavailable")).action is None
    assert external_thermostat(None).action is None


def test_the_output_memory_keeps_when_a_value_began_across_restarts_and_outages() -> None:
    memory = OutputMemory()
    assert memory.since("switch.valve", True, 100.0) == 100.0
    # A restart writes the same value again with a new last_changed.
    assert memory.since("switch.valve", True, 900.0) == 100.0
    # An outage says nothing about the valve, and the same value returning keeps its time.
    assert memory.since("switch.valve", None, 950.0) == 950.0
    assert memory.since("switch.valve", True, 960.0) == 100.0
    assert memory.since("switch.valve", False, 1000.0) == 1000.0

    restored = OutputMemory.from_dict(memory.to_dict())
    assert restored.since("switch.valve", False, 2000.0) == 1000.0
    restored.forget_except(set())
    assert restored.to_dict() == {}
    assert OutputMemory.from_dict({"switch.a": "junk", "switch.b": {"value": [1]}}).to_dict() == {}
