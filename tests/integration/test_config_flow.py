"""Tests for config flow setup of Hydronicus."""

from __future__ import annotations

import voluptuous_serialize
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv

from custom_components.hydronicus.const import (
    CONF_CALIBRATION_OFFSET,
    CONF_CONFIGURE_SENSOR_METADATA,
    CONF_COOLING_ENABLED,
    CONF_DESIGNATED_REFERENCE,
    CONF_MAX_AGE,
    CONF_PUMP_ENTITY,
    CONF_PUMP_OVERRUN,
    CONF_REQUIRED,
    CONF_SENSOR_ENTITY,
    CONF_TARGET_TEMPERATURE,
    CONF_TEMPERATURE_AGGREGATION,
    CONF_TEMPERATURE_SENSORS,
    CONF_THERMOSTAT_KIND,
    CONF_VALVE_ENTITY,
    CONF_VALVE_OPENING_TIME,
    CONF_WEIGHT,
    DOMAIN,
    THERMOSTAT_KIND_EXTERNAL_CLIMATE,
    THERMOSTAT_KIND_HYDRONICUS,
)
from custom_components.hydronicus.core.configuration import (
    plant_configuration_from_entry_data,
)
from custom_components.hydronicus.core.model import TemperatureSensorMetadata
from custom_components.hydronicus.core.topology import compile_topology


def _schema_fields(result) -> set[str]:
    """Return the field names exposed by a Home Assistant form schema."""
    return {
        str(field["name"])
        for field in voluptuous_serialize.convert(
            result["data_schema"], custom_serializer=cv.custom_serializer
        )
    }


async def test_initial_internal_thermostat_has_no_target_question(hass) -> None:
    """Hydronicus owns the fresh 21 °C fallback, not the Zone setup form."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "Hydronic plant"}
    )
    assert result["step_id"] == "zone"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_THERMOSTAT_KIND: THERMOSTAT_KIND_HYDRONICUS}
    )

    fields = _schema_fields(result)
    assert "target_temperature" not in fields
    assert "initial_target_temperature" not in fields
    assert "heating_start_delta" in fields
    assert "minimum_idle_duration_seconds" in fields


async def test_initial_external_thermostat_selects_existing_climate_entity(hass) -> None:
    """External setup asks for one climate entity and hides internal policy fields."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "External plant"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_THERMOSTAT_KIND: THERMOSTAT_KIND_EXTERNAL_CLIMATE}
    )

    fields = _schema_fields(result)
    assert "external_climate_entity" in fields
    assert "target_temperature" not in fields
    assert "heating_start_delta" not in fields
    assert "comfort" not in fields


async def test_user_config_flow_creates_entry(hass) -> None:
    """A user flow should persist one validated shadow topology."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Hydronic plant"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "zone"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Living room",
            CONF_TARGET_TEMPERATURE: 21.5,
            CONF_TEMPERATURE_SENSORS: ["sensor.living_temperature"],
            CONF_TEMPERATURE_AGGREGATION: "median",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "circuit"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Floor loop",
            CONF_VALVE_ENTITY: "switch.floor_valve",
            CONF_PUMP_ENTITY: "switch.floor_pump",
            CONF_VALVE_OPENING_TIME: 30,
            CONF_PUMP_OVERRUN: 120,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "review"
    assert result["description_placeholders"]["zone"] == "Living room"
    assert result["description_placeholders"]["circuit"] == "Floor loop"
    assert result["description_placeholders"]["logic"] == (
        "- Circuit Floor loop opens valves Floor loop valve before requesting pump "
        "Floor loop pump.\n"
        "- Zone Living room can request circuit Floor loop."
    )
    assert result["description_placeholders"]["warnings"] == "- None"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hydronic plant"
    assert result["data"]["dry_run"] is True
    topology = result["data"]["topology"]
    assert topology["zones"][0]["name"] == "Living room"
    assert "temperature_sensors" not in topology["zones"][0]
    assert topology["zones"][0]["temperature_sensor_metadata"] == [
        {
            "entity_id": "sensor.living_temperature",
            "required": True,
            "weight": 1.0,
            "calibration_offset": 0.0,
            "max_age_seconds": 1800.0,
            "designated_reference": False,
        }
    ]
    assert topology["zones"][0][CONF_TEMPERATURE_AGGREGATION] == "median"
    assert topology["valves"][0]["entity_id"] == "switch.floor_valve"
    assert topology["pumps"][0]["entity_id"] == "switch.floor_pump"
    assert topology["circuits"][0]["valve_ids"] == [topology["valves"][0]["id"]]
    assert topology["circuits"][0]["pump_id"] == topology["pumps"][0]["id"]

    configuration = plant_configuration_from_entry_data(result["data"])
    compiled = compile_topology(configuration)
    zone = next(iter(compiled.zones.values()))
    circuit = next(iter(compiled.circuits.values()))
    assert zone.temperature_sensor_metadata == (
        TemperatureSensorMetadata("sensor.living_temperature"),
    )
    assert zone.aggregation.value == "median"
    assert circuit.valve_ids == tuple(compiled.valves)
    assert circuit.pump_id == next(iter(compiled.pumps))
    assert compiled.logic_summary == (
        "Circuit Floor loop opens valves Floor loop valve before requesting pump Floor loop pump.",
        "Zone Living room can request circuit Floor loop.",
    )


async def test_initial_zone_schema_serializes_for_home_assistant_ui(hass) -> None:
    """The initial zone form must be serializable by Home Assistant's HTTP view."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "Hydronic plant"}
    )

    assert result["step_id"] == "zone"
    voluptuous_serialize.convert(result["data_schema"], custom_serializer=cv.custom_serializer)


async def test_initial_circuit_rejects_duplicate_actuator_entity(hass) -> None:
    """The initial flow should explain a valve and pump entity collision inline."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "Hydronic plant"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Living room",
            CONF_TARGET_TEMPERATURE: 21.5,
            CONF_TEMPERATURE_SENSORS: ["sensor.living_temperature"],
            CONF_TEMPERATURE_AGGREGATION: "median",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Floor loop",
            CONF_VALVE_ENTITY: "switch.shared_equipment",
            CONF_PUMP_ENTITY: "switch.shared_equipment",
            CONF_VALVE_OPENING_TIME: 30,
            CONF_PUMP_OVERRUN: 120,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "circuit"
    assert result["errors"] == {"base": "duplicate_actuator_entity"}


async def test_initial_review_explains_topology_validation_error(hass) -> None:
    """The review should expose the compiler reason for other invalid topology."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "Hydronic plant"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Living room",
            CONF_TARGET_TEMPERATURE: 21.5,
            CONF_TEMPERATURE_SENSORS: ["sensor.living_temperature"],
            CONF_TEMPERATURE_AGGREGATION: "median",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Floor loop",
            CONF_VALVE_ENTITY: "switch.floor_valve",
            CONF_PUMP_ENTITY: "switch.floor_pump",
            CONF_VALVE_OPENING_TIME: 30,
            CONF_PUMP_OVERRUN: 120,
            CONF_COOLING_ENABLED: True,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "review"
    assert result["errors"] == {"base": "invalid_topology"}
    assert (
        "requires a supply or surface temperature reference"
        in result["description_placeholders"]["logic"]
    )


async def test_advanced_sensor_editor_persists_metadata_and_weighted_policy(hass) -> None:
    """The weighted policy is reachable only through complete typed metadata forms."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "Hydronic plant"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Living room",
            CONF_TARGET_TEMPERATURE: 21.5,
            CONF_TEMPERATURE_SENSORS: [
                "sensor.living_temperature",
                "sensor.living_temperature_backup",
            ],
            CONF_TEMPERATURE_AGGREGATION: "mean",
            CONF_CONFIGURE_SENSOR_METADATA: True,
        },
    )
    assert result["step_id"] == "sensor_metadata"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_SENSOR_ENTITY: "sensor.living_temperature",
            CONF_REQUIRED: True,
            CONF_WEIGHT: 2.0,
            CONF_CALIBRATION_OFFSET: -0.25,
            CONF_MAX_AGE: 300,
            CONF_DESIGNATED_REFERENCE: True,
        },
    )
    assert result["step_id"] == "sensor_metadata"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_SENSOR_ENTITY: "sensor.living_temperature_backup",
            CONF_REQUIRED: False,
            CONF_WEIGHT: 1.0,
            CONF_CALIBRATION_OFFSET: 0.5,
            CONF_MAX_AGE: 900,
            CONF_DESIGNATED_REFERENCE: False,
        },
    )
    assert result["step_id"] == "sensor_policy"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_TEMPERATURE_AGGREGATION: "weighted_mean"},
    )
    assert result["step_id"] == "circuit"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Floor loop",
            CONF_VALVE_ENTITY: "switch.floor_valve",
            CONF_PUMP_ENTITY: "switch.floor_pump",
            CONF_VALVE_OPENING_TIME: 30,
            CONF_PUMP_OVERRUN: 120,
        },
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})

    metadata = result["data"]["topology"]["zones"][0]["temperature_sensor_metadata"]
    assert metadata == [
        {
            "entity_id": "sensor.living_temperature",
            CONF_REQUIRED: True,
            CONF_WEIGHT: 2.0,
            CONF_CALIBRATION_OFFSET: -0.25,
            CONF_MAX_AGE: 300.0,
            CONF_DESIGNATED_REFERENCE: True,
        },
        {
            "entity_id": "sensor.living_temperature_backup",
            CONF_REQUIRED: False,
            CONF_WEIGHT: 1.0,
            CONF_CALIBRATION_OFFSET: 0.5,
            CONF_MAX_AGE: 900.0,
            CONF_DESIGNATED_REFERENCE: False,
        },
    ]
    assert result["data"]["topology"]["zones"][0][CONF_TEMPERATURE_AGGREGATION] == ("weighted_mean")
