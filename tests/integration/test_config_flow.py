"""Tests for config flow setup of Hydronicus."""

from __future__ import annotations

from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv
from probatio import to_field_list
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.config_flow import HydronicClimateConfigFlow
from custom_components.hydronicus.const import (
    CONF_CALIBRATION_OFFSET,
    CONF_CONFIGURE_SENSOR_METADATA,
    CONF_COOLING_ENABLED,
    CONF_DESIGNATED_REFERENCE,
    CONF_DRY_RUN,
    CONF_DRY_RUN_CONFIRMATION,
    CONF_MAX_AGE,
    CONF_NAME,
    CONF_PLANT_ID,
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
from custom_components.hydronicus.core.topology import TopologyValidationError, compile_topology
from tests.integration.flow_forms import form_fields, form_value


def _schema_fields(result) -> set[str]:
    """Return the field names exposed by a Home Assistant form schema."""
    return {
        str(field["name"])
        for field in to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer)
    }


async def test_reconfigure_cannot_disable_dry_run_without_loaded_runtime(hass) -> None:
    """Leaving Dry run requires a live runtime to own activation safety."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: "00000000-0000-4000-8000-000000000001",
            CONF_DRY_RUN: True,
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_DRY_RUN: False}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dry_run_confirmation"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_DRY_RUN_CONFIRMATION: True}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "dry_run_runtime_unavailable"}
    assert entry.data[CONF_DRY_RUN] is True


async def test_reconfigure_can_enable_dry_run_without_loaded_runtime(hass) -> None:
    """Re-enabling Dry run is a safe persisted fallback when runtime is unloaded."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: "00000000-0000-4000-8000-000000000001",
            CONF_DRY_RUN: False,
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_DRY_RUN: True}
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_DRY_RUN] is True


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
    to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer)


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


async def test_initial_review_explains_topology_validation_error(hass, monkeypatch) -> None:
    """The review should expose the compiler reason for any otherwise unexplained rejection."""

    def reject(configuration):
        raise TopologyValidationError("Synthetic compiler reason.")

    monkeypatch.setattr("custom_components.hydronicus.config_flow.compile_topology", reject)
    result = await _start_first_circuit(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=_FIRST_CIRCUIT
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "review"
    assert result["errors"] == {"base": "invalid_topology"}
    assert "Synthetic compiler reason." in result["description_placeholders"]["logic"]


async def test_initial_sensor_policy_explains_designated_reference_count(hass) -> None:
    """Two designated references are rejected on the policy form instead of at the review."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "Hydronic plant"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Living room",
            CONF_TEMPERATURE_SENSORS: ["sensor.living_a", "sensor.living_b"],
            CONF_CONFIGURE_SENSOR_METADATA: True,
        },
    )
    for sensor_id in ("sensor.living_a", "sensor.living_b"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_SENSOR_ENTITY: sensor_id, CONF_DESIGNATED_REFERENCE: True},
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_TEMPERATURE_AGGREGATION: "mean"}
    )

    assert result["step_id"] == "sensor_policy"
    assert result["errors"] == {"base": "designated_reference_count"}


_FIRST_CIRCUIT = {
    "name": "Floor loop",
    CONF_VALVE_ENTITY: "switch.floor_valve",
    CONF_PUMP_ENTITY: "switch.floor_pump",
    CONF_VALVE_OPENING_TIME: 30,
    CONF_PUMP_OVERRUN: 120,
}


async def _start_first_circuit(hass):
    """Advance a fresh setup flow past a zone without humidity sensors."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "Hydronic plant"}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Living room", CONF_TEMPERATURE_SENSORS: ["sensor.living"]},
    )


async def test_initial_circuit_explains_missing_cooling_reference(hass) -> None:
    """Cooling without a reference is rejected on the circuit form, where it can be fixed."""
    result = await _start_first_circuit(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={**_FIRST_CIRCUIT, "cooling": {CONF_COOLING_ENABLED: True}},
    )

    assert result["step_id"] == "circuit"
    assert result["errors"] == {"base": "cooling_reference_required"}
    assert form_value(result, "cooling.cooling_enabled") is True

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=_FIRST_CIRCUIT
    )
    assert result["step_id"] == "review"
    assert not result["errors"]


async def test_initial_circuit_explains_missing_zone_humidity_for_cooling(hass) -> None:
    """Cooling for a first zone without humidity sensors is explained on the circuit form."""
    result = await _start_first_circuit(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            **_FIRST_CIRCUIT,
            "cooling": {
                CONF_COOLING_ENABLED: True,
                "supply_temperature_sensor": "sensor.floor_supply",
            },
        },
    )

    assert result["step_id"] == "circuit"
    assert result["errors"] == {"base": "cooling_requires_zone_observations"}


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


async def _start_initial_zone(hass, thermostat_kind: str = THERMOSTAT_KIND_HYDRONICUS):
    """Advance a fresh setup flow to the first Zone details form."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "Hydronic plant"}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_THERMOSTAT_KIND: thermostat_kind}
    )


async def test_initial_zone_error_keeps_the_form_and_submitted_values(hass) -> None:
    """A rejected Zone details form is shown again with fields and the user's input."""
    result = await _start_initial_zone(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "   ",
            CONF_TEMPERATURE_SENSORS: ["sensor.living_temperature"],
            CONF_TEMPERATURE_AGGREGATION: "median",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "zone_details"
    assert result["errors"] == {"base": "name_required"}
    assert form_value(result, CONF_TEMPERATURE_SENSORS) == ["sensor.living_temperature"]
    assert form_value(result, CONF_TEMPERATURE_AGGREGATION) == "median"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Living room",
            CONF_TEMPERATURE_SENSORS: ["sensor.living_temperature"],
        },
    )
    assert result["step_id"] == "circuit"


async def test_initial_hydronicus_zone_rejects_empty_temperature_sensors(hass) -> None:
    """An empty sensor list, as a lazily loaded picker can submit, stays on Zone details."""
    result = await _start_initial_zone(hass)
    zone = {
        CONF_NAME: "Z",
        CONF_TEMPERATURE_SENSORS: [],
        CONF_TEMPERATURE_AGGREGATION: "median",
        "heating_start_delta": 0.3,
        "heating_stop_delta": 0.1,
        "minimum_active_duration_seconds": 0,
        "minimum_idle_duration_seconds": 0,
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=zone)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "zone_details"
    assert result["errors"] == {CONF_TEMPERATURE_SENSORS: "temperature_sensors_required"}
    assert form_value(result, CONF_NAME) == "Z"
    assert form_value(result, CONF_TEMPERATURE_SENSORS) == []
    assert form_value(result, CONF_TEMPERATURE_AGGREGATION) == "median"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={**zone, CONF_TEMPERATURE_SENSORS: ["sensor.living_temperature"]},
    )
    assert result["step_id"] == "circuit"


async def test_initial_external_zone_accepts_empty_temperature_sensors(hass) -> None:
    """An external climate entity supplies temperature, so zone sensors stay optional."""
    result = await _start_initial_zone(hass, THERMOSTAT_KIND_EXTERNAL_CLIMATE)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Office",
            CONF_TEMPERATURE_SENSORS: [],
            "external_climate_entity": "climate.office",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "circuit"
    assert not result["errors"]


async def test_initial_forms_use_typed_selectors(hass) -> None:
    """Names, numbers, sensors, and choices use selectors the frontend renders natively."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert "text" in form_fields(result)[CONF_NAME]["selector"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "Hydronic plant"}
    )
    kind = form_fields(result)[CONF_THERMOSTAT_KIND]["selector"]["select"]
    assert kind["translation_key"] == CONF_THERMOSTAT_KIND
    assert kind["options"] == [THERMOSTAT_KIND_HYDRONICUS, THERMOSTAT_KIND_EXTERNAL_CLIMATE]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_THERMOSTAT_KIND: THERMOSTAT_KIND_HYDRONICUS}
    )
    fields = form_fields(result)
    assert fields[CONF_TEMPERATURE_SENSORS]["selector"]["entity"]["domain"] == ["sensor"]
    assert fields[CONF_TEMPERATURE_SENSORS]["selector"]["entity"]["device_class"] == ["temperature"]
    assert fields["humidity_sensors"]["selector"]["entity"]["device_class"] == ["humidity"]
    aggregation = fields[CONF_TEMPERATURE_AGGREGATION]["selector"]["select"]
    assert aggregation["translation_key"] == CONF_TEMPERATURE_AGGREGATION
    assert aggregation["options"] == ["mean", "median", "minimum", "maximum"]
    assert fields["heating_start_delta"]["selector"]["number"] == {
        "min": 0.0,
        "mode": "box",
        "step": 0.1,
        "unit_of_measurement": "°C",
    }
    assert fields["minimum_idle_duration_seconds"]["selector"]["number"]["unit_of_measurement"] == (
        "s"
    )
    assert fields["comfort"]["selector"]["number"]["min"] == 5.0
    assert fields["comfort"]["selector"]["number"]["max"] == 35.0
    assert fields["cooling"]["expanded"] is False
    assert {"cooling.cooling_start_delta", "cooling.cooling_stop_delta"} <= set(fields)
    assert "cooling_start_delta" not in fields

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_NAME: "Living room", CONF_TEMPERATURE_SENSORS: ["sensor.room"]},
    )
    fields = form_fields(result)
    assert result["step_id"] == "circuit"
    assert fields["feedback"]["expanded"] is False
    assert fields["cooling"]["expanded"] is False
    assert {
        "feedback.readiness_entity_id",
        "feedback.position_feedback_entity",
        "feedback.fault_feedback_max_age_seconds",
        "cooling.cooling_enabled",
        "cooling.supply_temperature_sensor",
        "cooling.condensation_margin",
    } <= set(fields)
    assert fields["cooling.supply_temperature_sensor"]["selector"]["entity"]["device_class"] == [
        "temperature"
    ]
    assert fields[CONF_VALVE_OPENING_TIME]["selector"]["number"]["unit_of_measurement"] == "s"


async def test_initial_flow_flattens_sections_and_keeps_persisted_types(hass) -> None:
    """Sections are a form concern only; persisted data keeps its flat shape and types."""
    result = await _start_initial_zone(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Living room",
            CONF_TEMPERATURE_SENSORS: ["sensor.living_temperature"],
            "humidity_sensors": ["sensor.living_humidity"],
            "heating_start_delta": 1,
            "minimum_active_duration_seconds": 60,
            "comfort": 22,
            "cooling": {"cooling_start_delta": 1, "cooling_stop_delta": 0.25},
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Floor loop",
            CONF_VALVE_ENTITY: "switch.floor_valve",
            CONF_PUMP_ENTITY: "switch.floor_pump",
            CONF_VALVE_OPENING_TIME: 30,
            CONF_PUMP_OVERRUN: 120,
            "feedback": {
                "readiness_entity_id": "binary_sensor.synthetic_valve_ready",
                "position_feedback_entity": "sensor.valve_position",
                "position_feedback_max_age_seconds": 600,
                "fault_feedback_entity": "binary_sensor.pump_fault",
            },
            "cooling": {
                CONF_COOLING_ENABLED: True,
                "supply_temperature_sensor": "sensor.supply",
                "condensation_margin": 3,
            },
        },
    )
    assert result["step_id"] == "review", result.get("errors")
    assert result.get("errors") is None, result["description_placeholders"]["logic"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    topology = result["data"]["topology"]

    thermostat = topology["zones"][0]["thermostat"]
    assert thermostat["heating_start_delta"] == 1.0
    assert type(thermostat["heating_start_delta"]) is float
    assert type(thermostat["minimum_active_duration_seconds"]) is float
    assert thermostat["cooling_start_delta"] == 1.0
    assert thermostat["cooling_stop_delta"] == 0.25
    assert thermostat["preset_targets"] == {"comfort": 22.0}
    valve = topology["valves"][0]
    assert valve["readiness_entity_id"] == "binary_sensor.synthetic_valve_ready"
    assert valve["position_feedback_entity"] == "sensor.valve_position"
    assert valve["position_feedback_max_age_seconds"] == 600.0
    assert type(valve["opening_time_seconds"]) is float
    pump = topology["pumps"][0]
    assert pump["fault_feedback_entity"] == "binary_sensor.pump_fault"
    assert pump["fault_feedback_max_age_seconds"] == 1800.0
    assert type(pump["overrun_seconds"]) is float
    circuit = topology["circuits"][0]
    assert circuit[CONF_COOLING_ENABLED] is True
    assert circuit["supply_temperature_sensor"] == "sensor.supply"
    assert circuit["condensation_margin"] == 3.0
    assert type(circuit["condensation_margin"]) is float
    for record in (thermostat, valve, pump, circuit):
        assert "feedback" not in record
        assert "cooling" not in record


def test_parent_flow_steps_return_config_flow_results() -> None:
    """Parent flow steps use the specific ConfigFlowResult type, not FlowResult."""
    steps = [
        getattr(HydronicClimateConfigFlow, name)
        for name in dir(HydronicClimateConfigFlow)
        if name.startswith("async_step_") and name not in {"async_step_ignore"}
    ]
    own = [step for step in steps if step.__module__ == HydronicClimateConfigFlow.__module__]

    assert own
    assert {step.__annotations__["return"] for step in own} == {"config_entries.ConfigFlowResult"}
