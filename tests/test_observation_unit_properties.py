"""Generated checks for the observation unit policy at the runtime boundary."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, PERCENTAGE, UnitOfTemperature
from homeassistant.core import State
from homeassistant.util.unit_conversion import TemperatureConverter
from hypothesis import given
from hypothesis import strategies as st

from custom_components.hydronicus.core.controller import evaluate
from custom_components.hydronicus.core.model import (
    Circuit,
    DeliveryRoute,
    PlantConfiguration,
    PlantSnapshot,
    Pump,
    RuntimeState,
    TemperatureSensorMetadata,
    Valve,
    Zone,
    ZoneDecisionStatus,
)
from custom_components.hydronicus.core.topology import compile_topology
from custom_components.hydronicus.runtime import (
    _numeric_observation,
    celsius_from_unit,
    relative_humidity_from_unit,
)

NOW = datetime(2026, 7, 17, tzinfo=UTC)
TARGET = 21.0
SUPPORTED_TEMPERATURE_UNITS = (
    UnitOfTemperature.CELSIUS,
    UnitOfTemperature.FAHRENHEIT,
    UnitOfTemperature.KELVIN,
    None,
)
UNSUPPORTED_UNITS = st.text(max_size=8).filter(
    lambda unit: unit not in {"", *TemperatureConverter.VALID_UNITS}
)
COLD = st.floats(min_value=-20.0, max_value=19.0, allow_nan=False)
WARM = st.floats(min_value=23.0, max_value=60.0, allow_nan=False)


def _reported(celsius: float, unit: str | None) -> float:
    """Express a Celsius reading in the unit a sensor would report."""
    if unit is None:
        return celsius
    return TemperatureConverter.convert(celsius, UnitOfTemperature.CELSIUS, unit)


def _state(entity_id: str, value: float, unit: str | None) -> State:
    attributes = {} if unit is None else {ATTR_UNIT_OF_MEASUREMENT: unit}
    return State(entity_id, repr(value), attributes, last_reported=NOW, last_updated=NOW)


@given(
    celsius=st.floats(min_value=-50.0, max_value=150.0, allow_nan=False),
    unit=st.sampled_from(SUPPORTED_TEMPERATURE_UNITS),
)
def test_supported_temperature_units_round_trip_to_celsius(
    celsius: float, unit: str | None
) -> None:
    """Every supported unit, and a missing unit, yields the same Celsius value."""
    assert celsius_from_unit(_reported(celsius, unit), unit) == pytest.approx(celsius, abs=1e-9)


@given(value=st.floats(allow_nan=False), unit=UNSUPPORTED_UNITS)
def test_unsupported_temperature_units_are_never_usable(value: float, unit: str) -> None:
    """No reading with an unrecognized unit reaches the controller as a number."""
    assert celsius_from_unit(value, unit) is None


@given(value=st.floats(allow_nan=False), unit=st.text(max_size=8))
def test_humidity_is_usable_only_in_percent_or_without_a_unit(value: float, unit: str) -> None:
    """Relative humidity accepts only percent or no unit."""
    expected = value if unit in {"", PERCENTAGE} else None
    assert relative_humidity_from_unit(value, unit) == expected


@st.composite
def _zone_cases(draw: st.DrawFn) -> tuple[tuple[float, str | None, bool], ...]:
    """Generate zones whose single sensor reports in a supported or unsupported unit."""
    zone_count = draw(st.integers(min_value=1, max_value=6))
    cases = []
    for _ in range(zone_count):
        supported = draw(st.booleans())
        celsius = draw(st.one_of(COLD, WARM))
        unit = (
            draw(st.sampled_from(SUPPORTED_TEMPERATURE_UNITS))
            if supported
            else draw(UNSUPPORTED_UNITS)
        )
        cases.append((celsius, unit, supported))
    return tuple(cases)


@given(_zone_cases())
def test_generated_topologies_demand_only_from_usable_celsius_readings(
    cases: tuple[tuple[float, str | None, bool], ...],
) -> None:
    """An unsupported unit blocks its zone; a supported one drives demand in Celsius."""
    indices = range(len(cases))
    plant = compile_topology(
        PlantConfiguration(
            id="unit-plant",
            zones=tuple(
                Zone(
                    f"zone-{index}",
                    f"Zone {index}",
                    TARGET,
                    (TemperatureSensorMetadata(f"sensor.zone_{index}"),),
                )
                for index in indices
            ),
            valves=tuple(
                Valve(f"valve-{index}", f"Valve {index}", f"switch.valve_{index}")
                for index in indices
            ),
            pumps=(Pump("pump", "Pump", "switch.pump"),),
            circuits=tuple(
                Circuit(f"circuit-{index}", f"Circuit {index}", (f"valve-{index}",), "pump")
                for index in indices
            ),
            routes=tuple(
                DeliveryRoute(f"route-{index}", f"zone-{index}", f"circuit-{index}")
                for index in indices
            ),
        )
    )
    snapshot = PlantSnapshot(
        {
            f"sensor.zone_{index}": _numeric_observation(
                _state(
                    f"sensor.zone_{index}", _reported(celsius, unit if supported else None), unit
                ),
                celsius_from_unit,
            )
            for index, (celsius, unit, supported) in enumerate(cases)
        }
    )

    result = evaluate(plant, snapshot, RuntimeState(), NOW)

    for index, (celsius, _unit, supported) in enumerate(cases):
        decision = result.diagnostics.zone_decisions[f"zone-{index}"]
        if not supported:
            assert decision.status is ZoneDecisionStatus.SENSOR_BLOCKED
            assert decision.demand is False
        else:
            assert decision.aggregation is not None
            assert decision.aggregation.value == pytest.approx(celsius, abs=1e-9)
            assert decision.demand is (celsius < TARGET)
