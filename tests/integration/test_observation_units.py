"""Observation unit policy at the Home Assistant runtime boundary."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, PERCENTAGE, UnitOfTemperature
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_NAME,
    CONF_PLANT_ID,
)
from custom_components.hydronicus.core.legacy.model import ExternalClimateThermostatState
from tests.integration.plant_fixtures import plant_entry

PLANT_ID = "00000000-0000-4000-8000-000000000301"
ZONE_ID = "00000000-0000-4000-8000-000000000302"
VALVE_ID = "00000000-0000-4000-8000-000000000303"
PUMP_ID = "00000000-0000-4000-8000-000000000304"
CIRCUIT_ID = "00000000-0000-4000-8000-000000000305"
ROUTE_ID = "00000000-0000-4000-8000-000000000306"
SOURCE_ID = "00000000-0000-4000-8000-000000000307"

ZONE_SENSOR = "sensor.units_zone_temperature"
HUMIDITY_SENSOR = "sensor.units_zone_humidity"
SUPPLY_SENSOR = "sensor.units_supply_temperature"
SURFACE_SENSOR = "sensor.units_surface_temperature"
SOURCE_SENSOR = "sensor.units_source_temperature"
EXTERNAL_CLIMATE = "climate.units_external_room"
CLIMATE_ENTITY = "climate.units_zone"
DEMAND_ENTITY = "binary_sensor.units_zone_heating_demand"
BLOCKED_ENTITY = "binary_sensor.units_zone_blocked"
BLOCKED_REASON_ENTITY = "sensor.units_zone_blocked_reason"


def _entry(*, external: bool = False) -> MockConfigEntry:
    """Build a Dry run Plant that binds every observation kind the runtime reads."""
    thermostat: dict[str, Any] = (
        {"kind": "external_climate", "entity_id": EXTERNAL_CLIMATE}
        if external
        else {"kind": "hydronicus", "initial_target_temperature": 21.0}
    )
    return plant_entry(
        {
            CONF_NAME: "Unit plant",
            CONF_PLANT_ID: PLANT_ID,
            CONF_DRY_RUN: True,
            "topology": {
                "zones": [
                    {
                        "id": ZONE_ID,
                        "name": "Units zone",
                        "thermostat": thermostat,
                        "temperature_sensor_metadata": []
                        if external
                        else [{"entity_id": ZONE_SENSOR}],
                        "humidity_sensor_metadata": [{"entity_id": HUMIDITY_SENSOR}],
                    }
                ],
                "valves": [{"id": VALVE_ID, "name": "Valve", "entity_id": "switch.test_valve"}],
                "pumps": [{"id": PUMP_ID, "name": "Pump", "entity_id": "switch.test_pump"}],
                "circuits": [
                    {
                        "id": CIRCUIT_ID,
                        "name": "Circuit",
                        "valve_ids": [VALVE_ID],
                        "pump_id": PUMP_ID,
                        "supply_temperature_sensor": SUPPLY_SENSOR,
                        "surface_temperature_sensor": SURFACE_SENSOR,
                    }
                ],
                "routes": [{"id": ROUTE_ID, "zone_id": ZONE_ID, "circuit_id": CIRCUIT_ID}],
                "sources": [
                    {
                        "id": SOURCE_ID,
                        "name": "Boiler",
                        "source_type": "temperature_qualified_buffer",
                        "temperature_entity": SOURCE_SENSOR,
                        "minimum_temperature": 30.0,
                    }
                ],
            },
        },
        title="Unit plant",
        source_handles=False,
    )


def _set(hass, entity_id: str, value: str, unit: str | None) -> None:
    attributes = {} if unit is None else {ATTR_UNIT_OF_MEASUREMENT: unit}
    hass.states.async_set(entity_id, value, attributes)


async def _setup_heating(hass, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": CLIMATE_ENTITY, "hvac_mode": "heat"},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_fahrenheit_zone_sensor_is_converted_and_drives_heating_demand(hass) -> None:
    """A 64.4 °F zone sensor is 18 °C, which is below a 21 °C target."""
    _set(hass, ZONE_SENSOR, "64.4", UnitOfTemperature.FAHRENHEIT)
    entry = _entry()

    await _setup_heating(hass, entry)

    runtime = entry.runtime_data
    assert runtime.zone_current_temperature(ZONE_ID) == pytest.approx(18.0)
    assert runtime.snapshot.temperatures[ZONE_SENSOR].value == pytest.approx(18.0)
    assert hass.states.get(CLIMATE_ENTITY).attributes["current_temperature"] == pytest.approx(18.0)
    assert hass.states.get(DEMAND_ENTITY).state == "on"
    assert hass.states.get(BLOCKED_ENTITY).state == "off"


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        ("18.0", UnitOfTemperature.CELSIUS, 18.0),
        ("291.15", UnitOfTemperature.KELVIN, 18.0),
        ("18.0", None, 18.0),
    ],
)
async def test_supported_zone_temperature_units_normalize_to_celsius(
    hass, value: str, unit: str | None, expected: float
) -> None:
    """Celsius, kelvin, and unit-less readings all reach the controller as Celsius."""
    _set(hass, ZONE_SENSOR, value, unit)
    entry = _entry()

    await _setup_heating(hass, entry)

    assert entry.runtime_data.zone_current_temperature(ZONE_ID) == pytest.approx(expected)
    assert hass.states.get(DEMAND_ENTITY).state == "on"


@pytest.mark.parametrize("unit", ["W", "%", "°", "degC", "celsius"])
async def test_unsupported_zone_temperature_unit_fails_closed(hass, unit: str) -> None:
    """An unrecognized unit makes the sensor unusable, so the zone blocks demand."""
    _set(hass, ZONE_SENSOR, "10.0", unit)
    entry = _entry()

    await _setup_heating(hass, entry)

    runtime = entry.runtime_data
    assert runtime.snapshot.temperatures[ZONE_SENSOR].value is None
    assert runtime.zone_current_temperature(ZONE_ID) is None
    assert runtime.zone_is_blocked(ZONE_ID)
    assert hass.states.get(BLOCKED_ENTITY).state == "on"
    assert hass.states.get(DEMAND_ENTITY).state == "off"
    assert runtime.last_execution is not None
    assert runtime.last_execution.executed == ()
    assert hass.states.get(BLOCKED_REASON_ENTITY).state == (
        "Blocked: required temperature sensors are unusable: "
        f"{ZONE_SENSOR} (unsupported unit {unit!r})"
    )


@pytest.mark.parametrize(
    ("value", "unit", "celsius"),
    [
        ("0", UnitOfTemperature.KELVIN, "-273.15"),
        ("30.03", UnitOfTemperature.KELVIN, "-243.12"),
        ("-127", UnitOfTemperature.CELSIUS, "-127.00"),
        ("-50.1", UnitOfTemperature.CELSIUS, "-50.10"),
        ("100.1", UnitOfTemperature.CELSIUS, "100.10"),
        ("250", UnitOfTemperature.FAHRENHEIT, "121.11"),
    ],
)
async def test_implausible_zone_temperature_fails_closed(
    hass, value: str, unit: str, celsius: str
) -> None:
    """A reading in a valid unit but outside the air band never drives demand."""
    _set(hass, ZONE_SENSOR, value, unit)
    entry = _entry()

    await _setup_heating(hass, entry)

    runtime = entry.runtime_data
    assert runtime.snapshot.temperatures[ZONE_SENSOR].value is None
    assert runtime.zone_is_blocked(ZONE_ID)
    assert hass.states.get(DEMAND_ENTITY).state == "off"
    assert hass.states.get(BLOCKED_REASON_ENTITY).state == (
        "Blocked: required temperature sensors are unusable: "
        f"{ZONE_SENSOR} (implausible value {celsius} °C)"
    )


@pytest.mark.parametrize("value", ["-50.0", "100.0"])
async def test_zone_temperature_at_the_band_edges_is_usable(hass, value: str) -> None:
    """The air band is inclusive, so its edges are still plausible readings."""
    _set(hass, ZONE_SENSOR, value, UnitOfTemperature.CELSIUS)
    entry = _entry()

    await _setup_heating(hass, entry)

    assert entry.runtime_data.snapshot.temperatures[ZONE_SENSOR].value == float(value)
    assert hass.states.get(BLOCKED_ENTITY).state == "off"


async def test_water_temperatures_use_a_wider_band_than_surface_temperatures(hass) -> None:
    """Supply and source water may read up to 150 °C; a surface above 100 °C is implausible."""
    _set(hass, ZONE_SENSOR, "20.0", UnitOfTemperature.CELSIUS)
    _set(hass, SUPPLY_SENSOR, "120.0", UnitOfTemperature.CELSIUS)
    _set(hass, SURFACE_SENSOR, "120.0", UnitOfTemperature.CELSIUS)
    _set(hass, SOURCE_SENSOR, "150.0", UnitOfTemperature.CELSIUS)
    entry = _entry()

    await _setup_heating(hass, entry)

    snapshot = entry.runtime_data.snapshot
    assert snapshot.supply_temperatures[SUPPLY_SENSOR].value == 120.0
    assert snapshot.source_temperatures[SOURCE_ID].value == 150.0
    surface = snapshot.surface_temperatures[SURFACE_SENSOR]
    assert surface.value is None
    assert surface.invalid_reason == "implausible value 120.00 °C"

    _set(hass, SUPPLY_SENSOR, "0", UnitOfTemperature.KELVIN)
    _set(hass, SOURCE_SENSOR, "150.1", UnitOfTemperature.CELSIUS)
    await hass.async_block_till_done()

    snapshot = entry.runtime_data.snapshot
    assert snapshot.supply_temperatures[SUPPLY_SENSOR].value is None
    assert snapshot.source_temperatures[SOURCE_ID].value is None
    assert snapshot.source_temperatures[SOURCE_ID].invalid_reason == ("implausible value 150.10 °C")


async def test_zone_recovers_when_a_unit_becomes_supported(hass) -> None:
    """The fail-closed path is re-evaluated on every state change."""
    _set(hass, ZONE_SENSOR, "64.4", "fahrenheit")
    entry = _entry()
    await _setup_heating(hass, entry)
    assert hass.states.get(BLOCKED_ENTITY).state == "on"

    _set(hass, ZONE_SENSOR, "64.4", UnitOfTemperature.FAHRENHEIT)
    await hass.async_block_till_done()

    assert hass.states.get(BLOCKED_ENTITY).state == "off"
    assert hass.states.get(DEMAND_ENTITY).state == "on"


async def test_reference_and_source_temperatures_normalize_to_celsius(hass) -> None:
    """Supply, surface, and source temperatures follow the same unit policy."""
    _set(hass, ZONE_SENSOR, "20.0", UnitOfTemperature.CELSIUS)
    _set(hass, SUPPLY_SENSOR, "95.0", UnitOfTemperature.FAHRENHEIT)
    _set(hass, SURFACE_SENSOR, "297.15", UnitOfTemperature.KELVIN)
    _set(hass, SOURCE_SENSOR, "140.0", UnitOfTemperature.FAHRENHEIT)
    entry = _entry()

    await _setup_heating(hass, entry)

    snapshot = entry.runtime_data.snapshot
    assert snapshot.supply_temperatures[SUPPLY_SENSOR].value == pytest.approx(35.0)
    assert snapshot.surface_temperatures[SURFACE_SENSOR].value == pytest.approx(24.0)
    assert snapshot.source_temperatures[SOURCE_ID].value == pytest.approx(60.0)


async def test_reference_and_source_temperatures_with_unsupported_units_are_unusable(
    hass,
) -> None:
    """Supply, surface, and source readings fail closed on an unrecognized unit."""
    _set(hass, ZONE_SENSOR, "20.0", UnitOfTemperature.CELSIUS)
    _set(hass, SUPPLY_SENSOR, "35.0", "bar")
    _set(hass, SURFACE_SENSOR, "24.0", PERCENTAGE)
    _set(hass, SOURCE_SENSOR, "60.0", "kW")
    entry = _entry()

    await _setup_heating(hass, entry)

    snapshot = entry.runtime_data.snapshot
    assert snapshot.supply_temperatures[SUPPLY_SENSOR].value is None
    assert snapshot.surface_temperatures[SURFACE_SENSOR].value is None
    assert snapshot.source_temperatures[SOURCE_ID].value is None


@pytest.mark.parametrize(
    ("unit", "expected"),
    [(PERCENTAGE, 55.0), (None, 55.0), ("g/m³", None), (UnitOfTemperature.CELSIUS, None)],
)
async def test_humidity_accepts_only_percent_or_no_unit(
    hass, unit: str | None, expected: float | None
) -> None:
    """Humidity is relative humidity in percent; any other unit is unusable."""
    _set(hass, ZONE_SENSOR, "20.0", UnitOfTemperature.CELSIUS)
    _set(hass, HUMIDITY_SENSOR, "55.0", unit)
    entry = _entry()

    await _setup_heating(hass, entry)

    assert entry.runtime_data.snapshot.humidities[HUMIDITY_SENSOR].value == expected


@pytest.mark.parametrize(
    ("value", "expected", "reason"),
    [
        ("0", 0.0, None),
        ("100", 100.0, None),
        ("100.5", None, "implausible value 100.50 %"),
        ("-1", None, "implausible value -1.00 %"),
    ],
)
async def test_humidity_outside_zero_to_one_hundred_percent_is_implausible(
    hass, value: str, expected: float | None, reason: str | None
) -> None:
    """Relative humidity is usable only from 0 to 100 percent."""
    _set(hass, ZONE_SENSOR, "20.0", UnitOfTemperature.CELSIUS)
    _set(hass, HUMIDITY_SENSOR, value, PERCENTAGE)
    entry = _entry()

    await _setup_heating(hass, entry)

    observation = entry.runtime_data.snapshot.humidities[HUMIDITY_SENSOR]
    assert observation.value == expected
    assert observation.invalid_reason == reason


async def test_external_climate_temperatures_are_converted_from_the_system_unit(hass) -> None:
    """External climate attributes arrive in the system unit and are stored in Celsius."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    hass.states.async_set(
        EXTERNAL_CLIMATE,
        "heat",
        {"hvac_action": "heating", "temperature": 71.6, "current_temperature": 66.2},
    )
    entry = _entry(external=True)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    state = runtime.snapshot.thermostats[ZONE_ID]
    assert isinstance(state, ExternalClimateThermostatState)
    assert state.current_temperature == pytest.approx(19.0)
    assert state.target_temperature == pytest.approx(22.0)
    zone = next(zone for zone in runtime.presentation_snapshot()["zones"] if zone["id"] == ZONE_ID)
    assert zone["thermostat"]["current_temperature"] == pytest.approx(19.0)
    assert zone["thermostat"]["target_temperature"] == pytest.approx(22.0)
