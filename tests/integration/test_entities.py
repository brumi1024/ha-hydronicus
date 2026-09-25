"""Entity presentation contract: names, IDs, classes, icons, and climate actions."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from homeassistant.core import State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.hydronicus.const import (
    CONF_CONDENSATION_MARGIN,
    CONF_COOLING_ENABLED,
    CONF_DIAGNOSTICS_INCLUDE_ACTUATOR_DETAILS,
    CONF_DRY_RUN,
    CONF_NAME,
    CONF_PLANT_ID,
    CONF_SUPPLY_TEMPERATURE_SENSOR,
    DOMAIN,
)
from custom_components.hydronicus.core.legacy.model import (
    PlantMode,
    SourceSelectionPhase,
    ThermostatHvacMode,
)
from tests.integration.plant_fixtures import plant_entry

INTEGRATION = Path(__file__).parents[2] / "custom_components" / "hydronicus"
PLANT_ID = "00000000-0000-4000-8000-000000000001"
ZONE_ID = "00000000-0000-4000-8000-000000000002"
VALVE_ID = "00000000-0000-4000-8000-000000000003"
PUMP_ID = "00000000-0000-4000-8000-000000000004"
CIRCUIT_ID = "00000000-0000-4000-8000-000000000005"
ROUTE_ID = "00000000-0000-4000-8000-000000000006"
SOURCE_ID = "00000000-0000-4000-8000-000000000007"
CLIMATE = "climate.living"
# The room sensor already holds sensor.living_temperature, so the zone's own
# Temperature entity takes the next free entity ID.
TEMPERATURE = "sensor.living_combined_temperature"


def _entry() -> MockConfigEntry:
    """Return one Dry run plant that creates every Hydronicus entity type."""
    return plant_entry(
        {
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: PLANT_ID,
            CONF_DRY_RUN: True,
            CONF_DIAGNOSTICS_INCLUDE_ACTUATOR_DETAILS: True,
            "topology": {
                "zones": [
                    {
                        "id": ZONE_ID,
                        "name": "Living",
                        "thermostat": {
                            "kind": "hydronicus",
                            "initial_target_temperature": 24.0,
                            "cooling_start_delta": 0.5,
                            "cooling_stop_delta": 0.2,
                        },
                        "temperature_sensor_metadata": [{"entity_id": "sensor.living_temperature"}],
                        "humidity_sensor_metadata": [{"entity_id": "sensor.living_humidity"}],
                    }
                ],
                "valves": [
                    {
                        "id": VALVE_ID,
                        "name": "Cooling valve",
                        "entity_id": "switch.cooling_valve",
                        "opening_time_seconds": 0.0,
                    }
                ],
                "pumps": [
                    {
                        "id": PUMP_ID,
                        "name": "Cooling pump",
                        "entity_id": "switch.cooling_pump",
                        "overrun_seconds": 120.0,
                    }
                ],
                "circuits": [
                    {
                        "id": CIRCUIT_ID,
                        "name": "Cooling circuit",
                        "valve_ids": [VALVE_ID],
                        "pump_id": PUMP_ID,
                        CONF_COOLING_ENABLED: True,
                        CONF_SUPPLY_TEMPERATURE_SENSOR: "sensor.cooling_supply",
                        CONF_CONDENSATION_MARGIN: 2.0,
                    }
                ],
                "routes": [{"id": ROUTE_ID, "zone_id": ZONE_ID, "circuit_id": CIRCUIT_ID}],
                "sources": [
                    {
                        "id": SOURCE_ID,
                        "name": "Boiler",
                        "source_demand_entity": "switch.synthetic_source",
                    }
                ],
            },
        },
        title="Hydronic plant",
        source_handles=False,
    )


@pytest.fixture
def actuator_calls(hass) -> list[tuple[str, str]]:
    """Record every actuator service call so Dry run can be asserted."""
    calls: list[tuple[str, str]] = []

    async def record(call) -> None:
        calls.append((call.domain, call.service))

    for domain, service in (
        ("switch", "turn_on"),
        ("switch", "turn_off"),
        ("valve", "open_valve"),
        ("valve", "close_valve"),
    ):
        hass.services.async_register(domain, service, record)
    return calls


async def _setup(hass) -> MockConfigEntry:
    """Load the synthetic plant with a cooling-ready observation set."""
    hass.states.async_set("sensor.living_temperature", "25.0")
    hass.states.async_set("sensor.living_humidity", "50.0")
    hass.states.async_set("sensor.cooling_supply", "18.0")
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# Every entity the synthetic plant creates: unique ID suffix -> (entity ID, English name).
EXPECTED_ENTITIES: dict[str, tuple[str, str]] = {
    f"{PLANT_ID}_dry_run": ("binary_sensor.hydronic_plant_dry_run", "Hydronic plant Dry run"),
    f"{PLANT_ID}_mode_changeover_lockout": (
        "binary_sensor.hydronic_plant_mode_changeover_lockout",
        "Hydronic plant Mode changeover lockout",
    ),
    f"{PLANT_ID}_{ZONE_ID}_demand": (
        "binary_sensor.living_heating_demand",
        "Living Heating demand",
    ),
    f"{PLANT_ID}_{ZONE_ID}_blocked": (
        "binary_sensor.living_blocked",
        "Living Blocked",
    ),
    f"{PLANT_ID}_{ZONE_ID}_cooling_demand": (
        "binary_sensor.living_cooling_demand",
        "Living Cooling demand",
    ),
    f"{PLANT_ID}_{ZONE_ID}_cooling_blocked": (
        "binary_sensor.living_cooling_blocked",
        "Living Cooling blocked",
    ),
    f"{PLANT_ID}_{SOURCE_ID}_demand": (
        "binary_sensor.boiler_demand",
        "Boiler Demand",
    ),
    f"{PLANT_ID}_{SOURCE_ID}_available": (
        "binary_sensor.boiler_available",
        "Boiler Available",
    ),
    f"{PLANT_ID}_{SOURCE_ID}_active": (
        "binary_sensor.boiler_active",
        "Boiler Active",
    ),
    f"{PLANT_ID}_{SOURCE_ID}_blocked": (
        "binary_sensor.boiler_blocked",
        "Boiler Blocked",
    ),
    f"{PLANT_ID}_valve_{VALVE_ID}_requested": (
        "binary_sensor.cooling_valve_requested",
        "Cooling valve Requested",
    ),
    f"{PLANT_ID}_{VALVE_ID}_mismatch": (
        "binary_sensor.cooling_valve_mismatch",
        "Cooling valve Mismatch",
    ),
    f"{PLANT_ID}_{VALVE_ID}_blocked": (
        "binary_sensor.cooling_valve_blocked",
        "Cooling valve Blocked",
    ),
    f"{PLANT_ID}_pump_{PUMP_ID}_requested": (
        "binary_sensor.cooling_pump_requested",
        "Cooling pump Requested",
    ),
    f"{PLANT_ID}_{PUMP_ID}_mismatch": (
        "binary_sensor.cooling_pump_mismatch",
        "Cooling pump Mismatch",
    ),
    f"{PLANT_ID}_{PUMP_ID}_blocked": (
        "binary_sensor.cooling_pump_blocked",
        "Cooling pump Blocked",
    ),
    f"{PLANT_ID}_safe_shutdown": (
        "button.hydronic_plant_safe_shutdown",
        "Hydronic plant Safe shutdown",
    ),
    f"{PLANT_ID}_{ZONE_ID}_climate": (CLIMATE, "Living"),
    f"{PLANT_ID}_requested_mode": (
        "select.hydronic_plant_requested_mode",
        "Hydronic plant Requested mode",
    ),
    f"{PLANT_ID}_controller_status": (
        "sensor.hydronic_plant_controller_status",
        "Hydronic plant Controller status",
    ),
    f"{PLANT_ID}_reconciliation_status": (
        "sensor.hydronic_plant_reconciliation_status",
        "Hydronic plant Reconciliation status",
    ),
    f"{PLANT_ID}_topology_preview": (
        "sensor.hydronic_plant_topology_preview",
        "Hydronic plant Topology preview",
    ),
    f"{PLANT_ID}_operating_mode": (
        "sensor.hydronic_plant_operating_mode",
        "Hydronic plant Operating mode",
    ),
    f"{PLANT_ID}_mode_changeover_explanation": (
        "sensor.hydronic_plant_mode_changeover_explanation",
        "Hydronic plant Mode changeover explanation",
    ),
    f"{PLANT_ID}_active_source": (
        "sensor.hydronic_plant_active_source",
        "Hydronic plant Active source",
    ),
    f"{PLANT_ID}_source_changeover": (
        "sensor.hydronic_plant_source_changeover",
        "Hydronic plant Source changeover",
    ),
    f"{PLANT_ID}_source_dwell": (
        "sensor.hydronic_plant_source_dwell",
        "Hydronic plant Source dwell",
    ),
    f"{PLANT_ID}_recommended_source": (
        "sensor.hydronic_plant_recommended_source",
        "Hydronic plant Recommended source",
    ),
    f"{PLANT_ID}_source_recommendation": (
        "sensor.hydronic_plant_source_recommendation",
        "Hydronic plant Source recommendation",
    ),
    f"{PLANT_ID}_{SOURCE_ID}_blocked_reason": (
        "sensor.boiler_blocked_reason",
        "Boiler Blocked reason",
    ),
    f"{PLANT_ID}_{ZONE_ID}_explanation": (
        "sensor.living_explanation",
        "Living Explanation",
    ),
    f"{PLANT_ID}_{ZONE_ID}_aggregate_temperature": (
        TEMPERATURE,
        "Living Combined temperature",
    ),
    f"{PLANT_ID}_{ZONE_ID}_blocked_reason": (
        "sensor.living_blocked_reason",
        "Living Blocked reason",
    ),
    f"{PLANT_ID}_{ZONE_ID}_cooling_blocked_reason": (
        "sensor.living_cooling_blocked_reason",
        "Living Cooling blocked reason",
    ),
    f"{PLANT_ID}_{ZONE_ID}_dew_point": (
        "sensor.living_cooling_dew_point",
        "Living Cooling dew point",
    ),
    f"{PLANT_ID}_{ZONE_ID}_condensation_margin": (
        "sensor.living_cooling_condensation_margin",
        "Living Cooling condensation margin",
    ),
    f"{PLANT_ID}_{VALVE_ID}_feedback_reason": (
        "sensor.cooling_valve_feedback_reason",
        "Cooling valve Feedback reason",
    ),
    f"{PLANT_ID}_{PUMP_ID}_feedback_reason": (
        "sensor.cooling_pump_feedback_reason",
        "Cooling pump Feedback reason",
    ),
}


async def test_entity_ids_and_english_names_are_unchanged(hass, actuator_calls) -> None:
    """Translated names generate exactly the entity IDs and names of the hard-coded era."""
    entry = await _setup(hass)
    registry = er.async_get(hass)

    registered = {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert registered == {
        unique_id: entity_id for unique_id, (entity_id, _name) in EXPECTED_ENTITIES.items()
    }
    for entity_id, name in EXPECTED_ENTITIES.values():
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.attributes["friendly_name"] == name, entity_id
    assert actuator_calls == []


async def test_condensation_margin_converts_as_a_temperature_delta(hass, actuator_calls) -> None:
    """A 4.15 degC margin reads 7.47 degF under US customary units, not 39.47 degF."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = await _setup(hass)
    await entry.runtime_data.async_set_zone_hvac_mode(ZONE_ID, ThermostatHvacMode.COOL, hass=hass)
    await hass.async_block_till_done()

    assert entry.runtime_data.zone_condensation_margin(ZONE_ID) == pytest.approx(4.1484, abs=1e-3)
    state = hass.states.get("sensor.living_cooling_condensation_margin")
    assert state.attributes["unit_of_measurement"] == "°F"
    assert float(state.state) == pytest.approx(7.47, abs=0.01)
    assert state.attributes["device_class"] == "temperature_delta"
    assert actuator_calls == []


async def _climate_action(hass, service: str) -> None:
    await hass.services.async_call("climate", service, {"entity_id": CLIMATE}, blocking=True)
    await hass.async_block_till_done()


async def test_climate_turn_off_on_and_toggle_restore_the_last_mode(hass, actuator_calls) -> None:
    """Turn on restores the zone's last non-off mode instead of guessing heat_cool."""
    entry = await _setup(hass)
    assert hass.states.get(CLIMATE).state == "off"

    await _climate_action(hass, "turn_on")
    assert hass.states.get(CLIMATE).state == "heat"

    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": CLIMATE, "hvac_mode": "cool"}, blocking=True
    )
    await _climate_action(hass, "turn_off")
    assert hass.states.get(CLIMATE).state == "off"
    assert entry.runtime_data.zone_hvac_modes[ZONE_ID] is ThermostatHvacMode.OFF

    await _climate_action(hass, "turn_on")
    assert hass.states.get(CLIMATE).state == "cool"

    await _climate_action(hass, "toggle")
    assert hass.states.get(CLIMATE).state == "off"
    await _climate_action(hass, "toggle")
    assert hass.states.get(CLIMATE).state == "cool"
    assert actuator_calls == []


async def test_climate_turn_on_remembers_modes_set_outside_the_entity(hass, actuator_calls) -> None:
    """A mode set through the runtime, such as from the card, is the one turn on restores."""
    entry = await _setup(hass)
    await entry.runtime_data.async_set_zone_hvac_mode(
        ZONE_ID, ThermostatHvacMode.HEAT_COOL, hass=hass
    )
    await hass.async_block_till_done()
    await entry.runtime_data.async_set_zone_hvac_mode(ZONE_ID, ThermostatHvacMode.OFF, hass=hass)
    await hass.async_block_till_done()

    await _climate_action(hass, "turn_on")
    assert hass.states.get(CLIMATE).state == "heat_cool"
    assert actuator_calls == []


async def test_turn_on_restores_the_mode_persisted_before_a_restart(hass, actuator_calls) -> None:
    """The last active mode survives a restart in restore state, beside the zone mode."""
    mock_restore_cache_with_extra_data(
        hass,
        [(State(CLIMATE, "off", {"temperature": 23.0}), {"last_active_hvac_mode": "cool"})],
    )
    await _setup(hass)
    assert hass.states.get(CLIMATE).state == "off"

    await _climate_action(hass, "turn_on")
    assert hass.states.get(CLIMATE).state == "cool"
    entity = hass.data[DATA_INSTANCES]["climate"].get_entity(CLIMATE)
    assert entity.extra_restore_state_data.as_dict() == {
        "last_active_hvac_mode": "cool",
        "target_temperature_celsius": 23.0,
    }
    assert actuator_calls == []


async def test_restored_setpoint_is_converted_from_the_display_unit(hass, actuator_calls) -> None:
    """A setpoint restored as 70 degF under US customary units is about 21.1 degC internally."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    mock_restore_cache_with_extra_data(hass, [(State(CLIMATE, "heat", {"temperature": 70.0}), {})])
    entry = await _setup(hass)

    assert entry.runtime_data.zone_target_temperatures[ZONE_ID] == pytest.approx(21.11, abs=0.01)
    assert hass.states.get(CLIMATE).attributes["temperature"] == pytest.approx(70.0, abs=0.1)
    assert actuator_calls == []


async def test_fahrenheit_display_does_not_drift_the_persisted_setpoint(
    hass, actuator_calls
) -> None:
    """A 20.5 degC target shows as whole degF but is persisted and restored in Celsius."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = await _setup(hass)
    await entry.runtime_data.async_set_zone_target_temperature(ZONE_ID, 20.5, hass=hass)
    await hass.async_block_till_done()

    state = hass.states.get(CLIMATE)
    assert state.attributes["temperature"] == 69
    entity = hass.data[DATA_INSTANCES]["climate"].get_entity(CLIMATE)
    extra = entity.extra_restore_state_data.as_dict()
    assert extra["target_temperature_celsius"] == 20.5
    assert actuator_calls == []

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    mock_restore_cache_with_extra_data(hass, [(state, extra)])
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.zone_target_temperatures[ZONE_ID] == 20.5
    assert actuator_calls == []


@pytest.mark.parametrize("stored", [None, "warm", float("nan"), 99.0, True])
async def test_unusable_persisted_setpoint_falls_back_to_the_display_attribute(
    hass, actuator_calls, stored
) -> None:
    """Older or corrupt restore data falls back to converting the displayed setpoint."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    mock_restore_cache_with_extra_data(
        hass,
        [(State(CLIMATE, "heat", {"temperature": 70.0}), {"target_temperature_celsius": stored})],
    )
    entry = await _setup(hass)

    assert entry.runtime_data.zone_target_temperatures[ZONE_ID] == pytest.approx(21.11, abs=0.01)
    assert actuator_calls == []


@pytest.mark.parametrize("stored", ["off", "fan_only", "not-a-mode", None])
async def test_turn_on_ignores_unusable_persisted_modes(hass, actuator_calls, stored) -> None:
    """Stored data that is off or not a supported mode falls back to heat."""
    mock_restore_cache_with_extra_data(
        hass, [(State(CLIMATE, "off"), {"last_active_hvac_mode": stored})]
    )
    await _setup(hass)

    await _climate_action(hass, "turn_on")
    assert hass.states.get(CLIMATE).state == "heat"
    assert actuator_calls == []


async def test_unsupported_hvac_mode_is_rejected_by_the_climate_base_class(hass) -> None:
    """Home Assistant rejects modes outside hvac_modes with a translated error."""
    await _setup(hass)

    with pytest.raises(ServiceValidationError) as error:
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": CLIMATE, "hvac_mode": "fan_only"},
            blocking=True,
        )
    assert error.value.translation_domain == "climate"
    assert hass.states.get(CLIMATE).state == "off"


async def test_climate_exposes_zone_humidity_only_when_the_zone_has_sensors(hass) -> None:
    """current_humidity is the evaluated zone humidity aggregate."""
    await _setup(hass)
    assert hass.states.get(CLIMATE).attributes["current_humidity"] == 50.0

    hass.states.async_set("sensor.living_humidity", "55.5")
    await hass.async_block_till_done()
    assert hass.states.get(CLIMATE).attributes["current_humidity"] == 55.5


async def test_climate_omits_humidity_for_zones_without_humidity_sensors(hass) -> None:
    """A zone with no humidity binding does not report a humidity."""
    hass.states.async_set("sensor.living_temperature", "25.0")
    hass.states.async_set("sensor.cooling_supply", "18.0")
    data = deepcopy(dict(_entry().data))
    del data["topology"]["zones"][0]["humidity_sensor_metadata"]
    # Cooling requires humidity, so this zone is heating only.
    data["topology"]["circuits"][0][CONF_COOLING_ENABLED] = False
    entry = plant_entry(data, title="Hydronic plant", source_handles=False)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert "current_humidity" not in hass.states.get(CLIMATE).attributes


@pytest.mark.parametrize(
    ("units", "registered_unit", "expected_value"),
    [(US_CUSTOMARY_SYSTEM, "°F", 7.47), (METRIC_SYSTEM, "°C", 4.15)],
)
async def test_existing_condensation_margin_keeps_its_unit_and_converts_as_a_delta(
    hass, actuator_calls, units, registered_unit, expected_value
) -> None:
    """An entity registered as an absolute temperature keeps its unit after the upgrade."""
    hass.config.units = units
    entry = _entry()
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"{PLANT_ID}_{ZONE_ID}_condensation_margin",
        suggested_object_id="living_cooling_condensation_margin",
        config_entry=entry,
        original_device_class="temperature",
        unit_of_measurement=registered_unit,
    )
    hass.states.async_set("sensor.living_temperature", "25.0")
    hass.states.async_set("sensor.living_humidity", "50.0")
    hass.states.async_set("sensor.cooling_supply", "18.0")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await entry.runtime_data.async_set_zone_hvac_mode(ZONE_ID, ThermostatHvacMode.COOL, hass=hass)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.living_cooling_condensation_margin")
    assert state.attributes["unit_of_measurement"] == registered_unit
    assert float(state.state) == pytest.approx(expected_value, abs=0.01)
    assert actuator_calls == []


# Entity ID -> (device class, entity category); every other entity has neither.
EXPECTED_CLASSES: dict[str, tuple[str | None, str | None]] = {
    "binary_sensor.hydronic_plant_mode_changeover_lockout": (None, "diagnostic"),
    "binary_sensor.living_blocked": ("problem", "diagnostic"),
    "binary_sensor.living_cooling_blocked": ("problem", "diagnostic"),
    "binary_sensor.boiler_available": (None, "diagnostic"),
    "binary_sensor.boiler_active": ("running", None),
    "binary_sensor.boiler_blocked": ("problem", "diagnostic"),
    "binary_sensor.cooling_valve_mismatch": ("problem", "diagnostic"),
    "binary_sensor.cooling_valve_blocked": ("problem", "diagnostic"),
    "binary_sensor.cooling_pump_mismatch": ("problem", "diagnostic"),
    "binary_sensor.cooling_pump_blocked": ("problem", "diagnostic"),
    "sensor.hydronic_plant_controller_status": ("enum", "diagnostic"),
    "sensor.hydronic_plant_reconciliation_status": ("enum", "diagnostic"),
    "sensor.hydronic_plant_topology_preview": (None, "diagnostic"),
    "sensor.hydronic_plant_operating_mode": ("enum", None),
    "sensor.hydronic_plant_source_changeover": ("enum", None),
    "sensor.hydronic_plant_source_dwell": ("duration", "diagnostic"),
    "sensor.hydronic_plant_source_recommendation": (None, "diagnostic"),
    "sensor.hydronic_plant_mode_changeover_explanation": (None, "diagnostic"),
    "sensor.boiler_blocked_reason": (None, "diagnostic"),
    "sensor.living_explanation": (None, "diagnostic"),
    "sensor.living_blocked_reason": (None, "diagnostic"),
    "sensor.living_cooling_blocked_reason": (None, "diagnostic"),
    TEMPERATURE: ("temperature", None),
    "sensor.living_cooling_dew_point": ("temperature", None),
    "sensor.living_cooling_condensation_margin": ("temperature_delta", None),
    "sensor.cooling_valve_feedback_reason": (None, "diagnostic"),
    "sensor.cooling_pump_feedback_reason": (None, "diagnostic"),
}


async def test_device_classes_and_entity_categories(hass) -> None:
    """Every entity carries the device class and category of the presentation contract."""
    entry = await _setup(hass)
    registry = er.async_get(hass)

    actual = {
        item.entity_id: (
            item.original_device_class,
            item.entity_category.value if item.entity_category else None,
        )
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    for entity_id, expected in EXPECTED_CLASSES.items():
        assert actual.pop(entity_id) == expected, entity_id
    assert set(actual.values()) == {(None, None)}

    dwell = hass.states.get("sensor.hydronic_plant_source_dwell")
    assert dwell.attributes["unit_of_measurement"] == "s"
    assert float(dwell.state) == 0.0


async def test_temperature_sensors_suggest_one_decimal(hass) -> None:
    """Converted temperatures display one decimal instead of float noise."""
    await _setup(hass)
    registry = er.async_get(hass)

    for entity_id in (
        TEMPERATURE,
        "sensor.living_cooling_dew_point",
        "sensor.living_cooling_condensation_margin",
    ):
        options = registry.async_get(entity_id).options["sensor"]
        assert options["suggested_display_precision"] == 1, entity_id


async def test_source_dwell_suggests_whole_seconds(hass) -> None:
    """The dwell countdown displays whole seconds instead of "0.00 s"."""
    await _setup(hass)
    options = er.async_get(hass).async_get("sensor.hydronic_plant_source_dwell").options
    assert options["sensor"]["suggested_display_precision"] == 0


ENUM_SENSORS = {
    "sensor.hydronic_plant_operating_mode": "operating_mode",
    "sensor.hydronic_plant_controller_status": "controller_status",
    "sensor.hydronic_plant_reconciliation_status": "reconciliation_status",
    "sensor.hydronic_plant_source_changeover": "source_changeover",
}


async def test_enum_sensors_keep_raw_states_and_translate_every_option(hass) -> None:
    """Enum states keep their raw values, and each option has an English display string."""
    await _setup(hass)
    entity_strings = _strings()["entity"]

    for entity_id, key in ENUM_SENSORS.items():
        state = hass.states.get(entity_id)
        options = state.attributes["options"]
        assert state.state in options, entity_id
        assert set(entity_strings["sensor"][key]["state"]) == set(options), entity_id
    assert hass.states.get("sensor.hydronic_plant_operating_mode").state == "idle"
    assert hass.states.get("sensor.hydronic_plant_controller_status").state == "idle"
    assert hass.states.get("sensor.hydronic_plant_reconciliation_status").state == "not_started"
    assert hass.states.get("sensor.hydronic_plant_source_changeover").state == "idle"
    controller_options = hass.states.get("sensor.hydronic_plant_controller_status").attributes[
        "options"
    ]
    assert set(controller_options) == {
        "stopped",
        "safe_shutdown",
        "initializing",
        "blocked",
        *(mode.value for mode in PlantMode),
    }
    assert set(hass.states.get("sensor.hydronic_plant_operating_mode").attributes["options"]) == {
        mode.value for mode in PlantMode
    }
    assert set(
        hass.states.get("sensor.hydronic_plant_source_changeover").attributes["options"]
    ) == {phase.value for phase in SourceSelectionPhase}

    select = hass.states.get("select.hydronic_plant_requested_mode")
    assert select.state == "auto"
    assert set(entity_strings["select"]["requested_mode"]["state"]) == set(
        select.attributes["options"]
    )


async def test_translation_keys_have_names_and_icons(hass) -> None:
    """Every entity translation key has an English name, and icons reference real keys."""
    entry = await _setup(hass)
    registry = er.async_get(hass)
    strings = _strings()
    icons = json.loads((INTEGRATION / "icons.json").read_text())["entity"]
    assert (INTEGRATION / "translations" / "en.json").read_bytes() == (
        INTEGRATION / "strings.json"
    ).read_bytes()

    used: set[tuple[str, str]] = set()
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        if item.translation_key is None:
            assert item.domain == "climate"
            continue
        used.add((item.domain, item.translation_key))
        assert strings["entity"][item.domain][item.translation_key]["name"]
    declared = {(platform, key) for platform, keys in strings["entity"].items() for key in keys}
    assert used == declared
    for platform, keys in icons.items():
        for key, icon in keys.items():
            assert (platform, key) in declared
            assert icon["default"].startswith("mdi:")
            assert all(value.startswith("mdi:") for value in icon.get("state", {}).values())
    for state in hass.states.async_all():
        if state.entity_id in registry.entities:
            assert "icon" not in state.attributes, state.entity_id


def test_platform_modules_do_not_hard_code_names_or_icons() -> None:
    """Names and icons live in strings.json and icons.json, not in platform code."""
    for module in ("sensor", "binary_sensor", "select", "button", "climate"):
        source = (INTEGRATION / f"{module}.py").read_text()
        assert "_attr_name =" not in source, module
        assert "_attr_icon =" not in source, module


async def test_volatile_attributes_are_excluded_from_the_recorder(hass) -> None:
    """Prose, operation lists, deadlines, and countdowns are not recorded."""
    await _setup(hass)
    expected = {
        "sensor.hydronic_plant_controller_status": {"operations"},
        "binary_sensor.hydronic_plant_dry_run": {"operations"},
        "sensor.hydronic_plant_topology_preview": {"logic_summary", "warnings"},
        "sensor.living_explanation": {"aggregation_explanation", "deadline"},
        "sensor.living_cooling_dew_point": {"interlocks"},
        "sensor.hydronic_plant_operating_mode": {"explanation", "changeover_deadline"},
        "sensor.hydronic_plant_source_changeover": {"explanation", "dwell_remaining_seconds"},
        "sensor.cooling_valve_feedback_reason": {
            "execution_failure",
            "stale_feedback",
        },
        "binary_sensor.hydronic_plant_mode_changeover_lockout": {"reason", "deadline"},
        "binary_sensor.cooling_valve_blocked": {
            "reason",
            "execution_failure",
            "stale_feedback",
        },
    }
    for entity_id, attributes in expected.items():
        state = hass.states.get(entity_id)
        assert attributes <= set(state.attributes), entity_id
        assert attributes <= state.state_info["unrecorded_attributes"], entity_id
    # Low-cardinality structured state stays recorded.
    for entity_id, attribute in (
        ("sensor.hydronic_plant_controller_status", "dry_run"),
        ("binary_sensor.living_blocked", "blocking_required_sensor_ids"),
        ("sensor.hydronic_plant_operating_mode", "requested_mode"),
    ):
        state = hass.states.get(entity_id)
        assert attribute in state.attributes
        assert attribute not in state.state_info["unrecorded_attributes"]


def _strings() -> dict:
    return json.loads((INTEGRATION / "strings.json").read_text())
