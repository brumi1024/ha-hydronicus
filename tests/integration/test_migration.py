"""Integration tests for config-entry schema migrations."""

from __future__ import annotations

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus import async_migrate_entry
from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_SUBENTRY_OBJECTS,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_CIRCUIT,
    SUBENTRY_TYPE_SOURCE,
    SUBENTRY_TYPE_ZONE,
)
from custom_components.hydronicus.core.configuration import StoredTopologyError
from custom_components.hydronicus.entry_configuration import (
    effective_plant_configuration,
    migration_plan,
)

PLANT_ID = "00000000-0000-4000-8000-000000000001"
ZONE_ID = "00000000-0000-4000-8000-000000000002"
VALVE_ID = "00000000-0000-4000-8000-000000000003"
PUMP_ID = "00000000-0000-4000-8000-000000000004"
CIRCUIT_ID = "00000000-0000-4000-8000-000000000005"
ROUTE_ID = "00000000-0000-4000-8000-000000000006"
DYNAMIC_ZONE_ID = "00000000-0000-4000-8000-000000000007"
DYNAMIC_ZONE_ROUTE_ID = "00000000-0000-4000-8000-000000000008"
DYNAMIC_VALVE_ID = "00000000-0000-4000-8000-000000000009"
DYNAMIC_CIRCUIT_ID = "00000000-0000-4000-8000-000000000010"
DYNAMIC_CIRCUIT_ROUTE_ID = "00000000-0000-4000-8000-000000000011"
SOURCE_ID = "00000000-0000-4000-8000-000000000012"


def _legacy_entry() -> MockConfigEntry:
    """Return one version 1.1 entry with every legacy subentry shape."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Legacy Hydronic plant",
        version=1,
        minor_version=1,
        data={
            "name": "Legacy Hydronic plant",
            "plant_id": PLANT_ID,
            "dry_run": False,
            "topology": {
                "zones": [
                    {
                        "id": ZONE_ID,
                        "name": "Living room",
                        "thermostat": {
                            "kind": "hydronicus",
                            "initial_target_temperature": 21.0,
                        },
                        "temperature_sensor_metadata": [{"entity_id": "sensor.living_temperature"}],
                    }
                ],
                "valves": [
                    {
                        "id": VALVE_ID,
                        "name": "Base valve",
                        "entity_id": "switch.floor_valve",
                        "opening_time_seconds": 30.0,
                    }
                ],
                "pumps": [
                    {
                        "id": PUMP_ID,
                        "name": "Base pump",
                        "entity_id": "switch.floor_pump",
                        "overrun_seconds": 120.0,
                    }
                ],
                "circuits": [
                    {
                        "id": CIRCUIT_ID,
                        "name": "Base circuit",
                        "valve_ids": [VALVE_ID],
                        "pump_id": PUMP_ID,
                    }
                ],
                "routes": [
                    {
                        "id": ROUTE_ID,
                        "zone_id": ZONE_ID,
                        "circuit_id": CIRCUIT_ID,
                    }
                ],
            },
        },
        subentries_data=[
            {
                "subentry_id": "01LEGACYZONE00000000000000",
                "subentry_type": SUBENTRY_TYPE_ZONE,
                "title": "Office",
                "unique_id": DYNAMIC_ZONE_ID,
                "data": {
                    "id": DYNAMIC_ZONE_ID,
                    "name": "Office",
                    "thermostat": {
                        "kind": "hydronicus",
                        "initial_target_temperature": 20.0,
                    },
                    "temperature_sensor_metadata": [{"entity_id": "sensor.office_temperature"}],
                    "temperature_aggregation": "mean",
                    "circuit_ids": [CIRCUIT_ID],
                    "routes": [{"id": DYNAMIC_ZONE_ROUTE_ID, "circuit_id": CIRCUIT_ID}],
                },
            },
            {
                "subentry_id": "01LEGACYVALVE0000000000000",
                "subentry_type": SUBENTRY_TYPE_ACTUATOR,
                "title": "Return valve",
                "unique_id": DYNAMIC_VALVE_ID,
                "data": {
                    "id": DYNAMIC_VALVE_ID,
                    "actuator_kind": "valve",
                    "name": "Return valve",
                    "entity_id": "switch.return_valve",
                    "opening_time_seconds": 45.0,
                    "position_feedback_entity": None,
                    "position_feedback_max_age_seconds": 1800.0,
                    "circuit_ids": [CIRCUIT_ID],
                },
            },
            {
                "subentry_id": "01LEGACYCIRCUIT00000000000",
                "subentry_type": SUBENTRY_TYPE_CIRCUIT,
                "title": "Backup circuit",
                "unique_id": DYNAMIC_CIRCUIT_ID,
                "data": {
                    "id": DYNAMIC_CIRCUIT_ID,
                    "name": "Backup circuit",
                    "zone_ids": [ZONE_ID],
                    "valve_ids": [VALVE_ID],
                    "pump_id": PUMP_ID,
                    "cooling_enabled": False,
                    "condensation_margin": 2.0,
                    "supply_temperature_max_age_seconds": 1800.0,
                    "surface_temperature_max_age_seconds": 1800.0,
                    "routes": [{"id": DYNAMIC_CIRCUIT_ROUTE_ID, "zone_id": ZONE_ID}],
                },
            },
            {
                "subentry_id": "01LEGACYSOURCE000000000000",
                "subentry_type": SUBENTRY_TYPE_SOURCE,
                "title": "Boiler",
                "unique_id": SOURCE_ID,
                "data": {
                    "id": SOURCE_ID,
                    "name": "Boiler",
                    "source_type": "external",
                    "priority": 10,
                    "availability_entity": None,
                    "source_demand_entity": None,
                    "temperature_entity": None,
                    "minimum_temperature": 0.0,
                    "maximum_age_seconds": 1800.0,
                    "hysteresis": 0.5,
                },
            },
        ],
    )


async def test_migrate_1_1_to_2_0_builds_one_parent_graph_and_safe_handles(hass) -> None:
    """Migration must preserve the graph while removing topology from subentries."""
    hass.states.async_set("sensor.living_temperature", "21.0")
    hass.states.async_set("sensor.office_temperature", "20.0")
    entry = _legacy_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == CONFIG_ENTRY_VERSION
    assert entry.minor_version == CONFIG_ENTRY_MINOR_VERSION
    assert entry.data[CONF_DRY_RUN] is True
    assert "output_authorization" not in entry.data
    assert entry.data[CONF_SUBENTRY_OBJECTS] == {
        DYNAMIC_ZONE_ID: SUBENTRY_TYPE_ZONE,
        DYNAMIC_VALVE_ID: SUBENTRY_TYPE_ACTUATOR,
        DYNAMIC_CIRCUIT_ID: SUBENTRY_TYPE_CIRCUIT,
        SOURCE_ID: SUBENTRY_TYPE_SOURCE,
    }
    assert all(
        subentry.data == {"id": subentry.unique_id} for subentry in entry.subentries.values()
    )

    topology = entry.data["topology"]
    assert {item["id"] for item in topology["zones"]} == {ZONE_ID, DYNAMIC_ZONE_ID}
    assert {item["id"] for item in topology["valves"]} == {VALVE_ID, DYNAMIC_VALVE_ID}
    assert {item["id"] for item in topology["circuits"]} == {
        CIRCUIT_ID,
        DYNAMIC_CIRCUIT_ID,
    }
    assert {item["id"] for item in topology["sources"]} == {SOURCE_ID}
    assert {item["id"] for item in topology["routes"]} == {
        ROUTE_ID,
        DYNAMIC_ZONE_ROUTE_ID,
        DYNAMIC_CIRCUIT_ROUTE_ID,
    }
    base_circuit = next(item for item in topology["circuits"] if item["id"] == CIRCUIT_ID)
    assert base_circuit["valve_ids"] == [VALVE_ID, DYNAMIC_VALVE_ID]

    runtime = entry.runtime_data
    assert set(runtime.plant.zones) == {ZONE_ID, DYNAMIC_ZONE_ID}
    assert set(runtime.plant.valves) == {VALVE_ID, DYNAMIC_VALVE_ID}
    assert set(runtime.plant.circuits) == {CIRCUIT_ID, DYNAMIC_CIRCUIT_ID}
    assert set(runtime.plant.sources) == {SOURCE_ID}

    registry = er.async_get(hass)
    office_demand = registry.async_get("binary_sensor.legacy_hydronic_plant_office_demand")
    assert office_demand is not None
    assert office_demand.config_subentry_id == "01LEGACYZONE00000000000000"

    device_registry = dr.async_get(hass)
    plant_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, PLANT_ID), entry.entry_id
    )
    assert plant_device is not None
    assert plant_device.config_entry_id == entry.entry_id
    assert plant_device.config_subentry_id is None

    object_entities = {
        DYNAMIC_ZONE_ID: (
            f"{PLANT_ID}_{DYNAMIC_ZONE_ID}_demand",
            "01LEGACYZONE00000000000000",
            "zone",
        ),
        DYNAMIC_VALVE_ID: (
            f"{PLANT_ID}_valve_{DYNAMIC_VALVE_ID}_requested",
            "01LEGACYVALVE0000000000000",
            "valve",
        ),
        SOURCE_ID: (
            f"{PLANT_ID}_{SOURCE_ID}_demand",
            "01LEGACYSOURCE000000000000",
            "source",
        ),
    }
    for object_id, (unique_id, subentry_id, kind) in object_entities.items():
        entity_id = registry.async_get_entity_id("binary_sensor", DOMAIN, unique_id)
        assert entity_id is not None
        entity = registry.async_get(entity_id)
        assert entity is not None
        assert entity.config_entry_id == entry.entry_id
        assert entity.config_subentry_id == subentry_id
        assert entity.device_id is not None
        device = device_registry.async_get(entity.device_id)
        assert device is not None
        assert device.identifiers == {(DOMAIN, f"{PLANT_ID}:{kind}:{object_id}")}
        assert device.config_entry_id == entry.entry_id
        assert device.config_subentry_id == subentry_id
        assert device.via_device_id == plant_device.id


async def test_migration_resumes_after_the_parent_graph_was_already_written(hass) -> None:
    """Repeating migration after an interrupted first half is safe and idempotent."""
    entry = _legacy_entry()
    entry.add_to_hass(hass)
    first_plan = migration_plan(entry)
    hass.config_entries.async_update_entry(entry, data=first_plan.data)
    first_topology = first_plan.data["topology"]

    assert await async_migrate_entry(hass, entry)

    assert entry.version == CONFIG_ENTRY_VERSION
    assert entry.minor_version == CONFIG_ENTRY_MINOR_VERSION
    assert entry.data["topology"] == first_topology
    assert all(
        dict(subentry.data) == {"id": subentry.unique_id} for subentry in entry.subentries.values()
    )


def test_version_2_rejects_a_handle_whose_parent_object_is_missing() -> None:
    """A minimal handle cannot silently resurrect topology absent from the parent graph."""
    legacy = _legacy_entry()
    data = dict(legacy.data)
    data[CONF_SUBENTRY_OBJECTS] = {DYNAMIC_ZONE_ID: SUBENTRY_TYPE_ZONE}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Corrupt Hydronic plant",
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        data=data,
        subentries_data=[
            {
                "subentry_id": "01CORRUPTZONE0000000000000",
                "subentry_type": SUBENTRY_TYPE_ZONE,
                "title": "Missing zone",
                "unique_id": DYNAMIC_ZONE_ID,
                "data": {"id": DYNAMIC_ZONE_ID},
            }
        ],
    )

    with pytest.raises(StoredTopologyError, match="references missing object"):
        effective_plant_configuration(entry)
