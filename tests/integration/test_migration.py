"""Integration tests for config-entry schema migrations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus import async_migrate_entry, async_setup_entry
from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_ROOM_OBJECTS,
    CONF_SUBENTRY_OBJECTS,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SUBENTRY_TYPE_ROOM,
    SUBENTRY_TYPE_SOURCE,
)
from custom_components.hydronicus.entry_configuration import authorize_outputs
from custom_components.hydronicus.migration import (
    ROOM_MIGRATION_STEPS,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_CIRCUIT,
    SUBENTRY_TYPE_ZONE,
    async_complete_version_2_removals,
    migration_plan,
    room_migration_plan,
)
from tests.integration.plant_fixtures import plant_data, plant_entry

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


def _room_id(entry: MockConfigEntry, zone_id: str) -> str:
    return next(
        subentry.subentry_id
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_ROOM and subentry.unique_id == zone_id
    )


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


async def test_version_1_1_reaches_version_3_in_one_setup(hass) -> None:
    """A version 1.1 entry chains through 2.0 to rooms in the same setup."""
    hass.states.async_set("sensor.living_temperature", "21.0")
    hass.states.async_set("sensor.office_temperature", "20.0")
    entry = _legacy_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (entry.version, entry.minor_version) == (3, 0)
    assert (CONFIG_ENTRY_VERSION, CONFIG_ENTRY_MINOR_VERSION) == (3, 0)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_DRY_RUN] is True
    assert "output_authorization" not in entry.data
    assert entry.data[CONF_SUBENTRY_OBJECTS] == {
        ZONE_ID: SUBENTRY_TYPE_ROOM,
        DYNAMIC_ZONE_ID: SUBENTRY_TYPE_ROOM,
        SOURCE_ID: SUBENTRY_TYPE_SOURCE,
    }
    # The backup circuit is routed only from the living room, so it became private;
    # the base circuit serves two rooms and both valves serve a Plant circuit.
    assert entry.data[CONF_ROOM_OBJECTS] == {DYNAMIC_CIRCUIT_ID: ZONE_ID}
    assert sorted(
        (subentry.subentry_type, subentry.unique_id, subentry.title)
        for subentry in entry.subentries.values()
    ) == [
        (SUBENTRY_TYPE_ROOM, ZONE_ID, "Living room"),
        (SUBENTRY_TYPE_ROOM, DYNAMIC_ZONE_ID, "Office"),
        (SUBENTRY_TYPE_SOURCE, SOURCE_ID, "Boiler"),
    ]
    assert all(
        subentry.data == {"id": subentry.unique_id} for subentry in entry.subentries.values()
    )

    topology = entry.data["topology"]
    assert {item["id"] for item in topology["zones"]} == {ZONE_ID, DYNAMIC_ZONE_ID}
    assert {item["id"] for item in topology["valves"]} == {VALVE_ID, DYNAMIC_VALVE_ID}
    assert {item["id"] for item in topology["circuits"]} == {CIRCUIT_ID, DYNAMIC_CIRCUIT_ID}
    assert {item["id"] for item in topology["sources"]} == {SOURCE_ID}
    assert {item["id"] for item in topology["routes"]} == {
        ROUTE_ID,
        DYNAMIC_ZONE_ROUTE_ID,
        DYNAMIC_CIRCUIT_ROUTE_ID,
    }
    base_circuit = next(item for item in topology["circuits"] if item["id"] == CIRCUIT_ID)
    assert base_circuit["valve_ids"] == [VALVE_ID, DYNAMIC_VALVE_ID]

    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    plant_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, PLANT_ID), entry.entry_id
    )
    assert plant_device is not None
    assert plant_device.config_subentry_id is None
    object_entities = {
        DYNAMIC_ZONE_ID: (f"{PLANT_ID}_{DYNAMIC_ZONE_ID}_demand", "zone"),
        DYNAMIC_VALVE_ID: (f"{PLANT_ID}_valve_{DYNAMIC_VALVE_ID}_requested", "valve"),
        SOURCE_ID: (f"{PLANT_ID}_{SOURCE_ID}_demand", "source"),
    }
    owners = {
        DYNAMIC_ZONE_ID: _room_id(entry, DYNAMIC_ZONE_ID),
        DYNAMIC_VALVE_ID: None,
        SOURCE_ID: "01LEGACYSOURCE000000000000",
    }
    for object_id, (unique_id, kind) in object_entities.items():
        entity_id = registry.async_get_entity_id("binary_sensor", DOMAIN, unique_id)
        assert entity_id is not None
        entity = registry.async_get(entity_id)
        assert entity is not None
        assert entity.config_subentry_id == owners[object_id]
        device = device_registry.async_get(entity.device_id)
        assert device is not None
        assert device.identifiers == {(DOMAIN, f"{PLANT_ID}:{kind}:{object_id}")}
        assert device.config_subentry_id == owners[object_id]
        assert device.via_device_id == plant_device.id


async def test_migration_resumes_after_the_1_1_parent_graph_was_already_written(hass) -> None:
    """Repeating migration after the first half of the 1.1 step is safe and idempotent."""
    entry = _legacy_entry()
    entry.add_to_hass(hass)
    first_plan = migration_plan(entry)
    hass.config_entries.async_update_entry(entry, data=dict(first_plan.data))
    first_topology = first_plan.data["topology"]

    assert await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (3, 0)
    assert entry.data["topology"] == first_topology
    assert {subentry.subentry_type for subentry in entry.subentries.values()} == {
        SUBENTRY_TYPE_ROOM,
        SUBENTRY_TYPE_SOURCE,
    }


# The cross-wired manifold from the Evidence section of the setup redesign plan:
# Living room and Bedroom each got a valve and share one pump, but the version 2
# flows could only offer the first objects, so Bedroom routes to the Living loop,
# Living room routes to the Bedroom loop, and both loops use the Living loop valve.
LIVING = "00000000-0000-4000-8000-00000000a001"
BEDROOM = "00000000-0000-4000-8000-00000000a002"
LIVING_LOOP = "00000000-0000-4000-8000-00000000b001"
BEDROOM_LOOP = "00000000-0000-4000-8000-00000000b002"
LIVING_VALVE = "00000000-0000-4000-8000-00000000c001"
BEDROOM_VALVE = "00000000-0000-4000-8000-00000000c002"
PUMP = "00000000-0000-4000-8000-00000000d001"
BOILER = "00000000-0000-4000-8000-00000000e001"
LIVING_TO_LIVING_LOOP = "00000000-0000-4000-8000-00000000f001"
BEDROOM_TO_LIVING_LOOP = "00000000-0000-4000-8000-00000000f002"
LIVING_TO_BEDROOM_LOOP = "00000000-0000-4000-8000-00000000f003"
LEGACY_BEDROOM = "01EVIDENCEZONE000000000000"
LEGACY_BEDROOM_LOOP = "01EVIDENCECIRCUIT000000000"
LEGACY_BEDROOM_VALVE = "01EVIDENCEVALVE00000000000"
BOILER_SUBENTRY = "01EVIDENCESOURCE0000000000"


def _evidence_topology() -> dict[str, Any]:
    return {
        "zones": [
            {
                "id": LIVING,
                "name": "Living room",
                "thermostat": {"kind": "hydronicus", "initial_target_temperature": 21.0},
                "temperature_sensor_metadata": [{"entity_id": "sensor.living_temperature"}],
            },
            {
                "id": BEDROOM,
                "name": "Bedroom",
                "thermostat": {"kind": "hydronicus", "initial_target_temperature": 20.0},
                "temperature_sensor_metadata": [{"entity_id": "sensor.bedroom_temperature"}],
            },
        ],
        "valves": [
            {"id": LIVING_VALVE, "name": "Living loop valve", "entity_id": "switch.living_valve"},
            {"id": BEDROOM_VALVE, "name": "Bedroom valve", "entity_id": "switch.bedroom_valve"},
        ],
        "pumps": [{"id": PUMP, "name": "Manifold pump", "entity_id": "switch.manifold_pump"}],
        "circuits": [
            {
                "id": LIVING_LOOP,
                "name": "Living loop",
                "valve_ids": [LIVING_VALVE, BEDROOM_VALVE],
                "pump_id": PUMP,
            },
            {
                "id": BEDROOM_LOOP,
                "name": "Bedroom loop",
                "valve_ids": [LIVING_VALVE],
                "pump_id": PUMP,
            },
        ],
        "routes": [
            {"id": LIVING_TO_LIVING_LOOP, "zone_id": LIVING, "circuit_id": LIVING_LOOP},
            {"id": BEDROOM_TO_LIVING_LOOP, "zone_id": BEDROOM, "circuit_id": LIVING_LOOP},
            {"id": LIVING_TO_BEDROOM_LOOP, "zone_id": LIVING, "circuit_id": BEDROOM_LOOP},
        ],
        "sources": [
            {
                "id": BOILER,
                "name": "Boiler",
                "source_type": "external",
                "source_demand_entity": "switch.boiler_demand",
            }
        ],
    }


def _evidence_version_2_entry() -> MockConfigEntry:
    """Return the cross-wired manifold as version 2 data with legacy handles."""
    data = authorize_outputs(
        {
            "name": "Hydronic plant",
            "plant_id": PLANT_ID,
            "dry_run": True,
            "requested_mode": "auto",
            "topology": _evidence_topology(),
            CONF_SUBENTRY_OBJECTS: {
                BEDROOM: SUBENTRY_TYPE_ZONE,
                BEDROOM_LOOP: SUBENTRY_TYPE_CIRCUIT,
                BEDROOM_VALVE: SUBENTRY_TYPE_ACTUATOR,
                BOILER: SUBENTRY_TYPE_SOURCE,
            },
        }
    )

    def handle(subentry_id: str, subentry_type: str, object_id: str, title: str):
        return {
            "subentry_id": subentry_id,
            "subentry_type": subentry_type,
            "title": title,
            "unique_id": object_id,
            "data": {"id": object_id},
        }

    return MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        version=2,
        minor_version=0,
        data=data,
        subentries_data=[
            handle(LEGACY_BEDROOM, SUBENTRY_TYPE_ZONE, BEDROOM, "Bedroom"),
            handle(LEGACY_BEDROOM_LOOP, SUBENTRY_TYPE_CIRCUIT, BEDROOM_LOOP, "Bedroom loop"),
            handle(LEGACY_BEDROOM_VALVE, SUBENTRY_TYPE_ACTUATOR, BEDROOM_VALVE, "Bedroom valve"),
            handle(BOILER_SUBENTRY, SUBENTRY_TYPE_SOURCE, BOILER, "Boiler"),
        ],
    )


# Every object-scoped registration a version 2 install has, with its version 2 owner.
_VERSION_2_OWNERS = {
    LIVING: None,
    BEDROOM: LEGACY_BEDROOM,
    LIVING_VALVE: None,
    BEDROOM_VALVE: LEGACY_BEDROOM_VALVE,
    PUMP: None,
    BOILER: BOILER_SUBENTRY,
}
_OBJECT_SLUGS = {
    LIVING: "living_room",
    BEDROOM: "bedroom",
    LIVING_VALVE: "living_loop_valve",
    BEDROOM_VALVE: "bedroom_valve",
    PUMP: "manifold_pump",
    BOILER: "boiler",
}
_KINDS = {
    LIVING: "zone",
    BEDROOM: "zone",
    LIVING_VALVE: "valve",
    BEDROOM_VALVE: "valve",
    PUMP: "pump",
    BOILER: "source",
}


def _version_2_registrations(object_id: str) -> list[tuple[str, str, str]]:
    """Return (domain, unique ID, suggested object id) of every entity of one object."""
    slug = f"hydronic_plant_{_OBJECT_SLUGS[object_id]}"
    kind = _KINDS[object_id]
    prefix = f"{PLANT_ID}_{object_id}"
    if kind == "zone":
        return [
            ("binary_sensor", f"{prefix}_demand", f"{slug}_demand"),
            ("binary_sensor", f"{prefix}_blocked", f"{slug}_blocked"),
            ("binary_sensor", f"{prefix}_cooling_demand", f"{slug}_cooling_demand"),
            ("binary_sensor", f"{prefix}_cooling_blocked", f"{slug}_cooling_blocked"),
            ("climate", f"{prefix}_climate", slug),
            ("sensor", f"{prefix}_explanation", f"{slug}_explanation"),
            ("sensor", f"{prefix}_aggregate_temperature", f"{slug}_aggregate_temperature"),
            ("sensor", f"{prefix}_blocked_reason", f"{slug}_blocked_reason"),
            ("sensor", f"{prefix}_cooling_blocked_reason", f"{slug}_cooling_blocked_reason"),
            ("sensor", f"{prefix}_dew_point", f"{slug}_dew_point"),
            ("sensor", f"{prefix}_condensation_margin", f"{slug}_condensation_margin"),
        ]
    if kind == "source":
        return [
            ("binary_sensor", f"{prefix}_demand", f"{slug}_demand"),
            ("binary_sensor", f"{prefix}_available", f"{slug}_available"),
            ("binary_sensor", f"{prefix}_active", f"{slug}_active"),
            ("binary_sensor", f"{prefix}_blocked", f"{slug}_blocked"),
            ("sensor", f"{prefix}_blocked_reason", f"{slug}_blocked_reason"),
        ]
    return [
        ("binary_sensor", f"{PLANT_ID}_{kind}_{object_id}_requested", f"{slug}_requested"),
        ("binary_sensor", f"{prefix}_mismatch", f"{slug}_mismatch"),
        ("binary_sensor", f"{prefix}_blocked", f"{slug}_blocked"),
    ]


CUSTOMIZED_ROOM_ENTITY = "binary_sensor.bedroom_heat_call"
CUSTOMIZED_PLANT_ENTITY = "binary_sensor.bedroom_valve_open"


def _install_version_2_registry(hass, entry: MockConfigEntry) -> dict[str, str]:
    """Register what a version 2 install owns, and customize two entities.

    Returns unique ID -> entity ID for every object-scoped entity.
    """
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    plant_device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, PLANT_ID)},
        name="Hydronic plant",
        manufacturer="Hydronicus",
        model="Hydronicus Plant",
    )
    entity_ids: dict[str, str] = {}
    for object_id, subentry_id in _VERSION_2_OWNERS.items():
        kind = _KINDS[object_id]
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            config_subentry_id=subentry_id,
            identifiers={(DOMAIN, f"{PLANT_ID}:{kind}:{object_id}")},
            name=f"Hydronic plant {_OBJECT_SLUGS[object_id]}",
            manufacturer="Hydronicus",
            model=f"Hydronicus {kind.title()}",
            via_device_id=plant_device.id,
        )
        for domain, unique_id, object_slug in _version_2_registrations(object_id):
            registry_entry = entities.async_get_or_create(
                domain,
                DOMAIN,
                unique_id,
                suggested_object_id=object_slug,
                config_entry=entry,
                config_subentry_id=subentry_id,
                device_id=device.id,
            )
            entity_ids[unique_id] = registry_entry.entity_id
    customizations = {
        f"{PLANT_ID}_{BEDROOM}_demand": (CUSTOMIZED_ROOM_ENTITY, "Bedroom heat call"),
        f"{PLANT_ID}_valve_{BEDROOM_VALVE}_requested": (
            CUSTOMIZED_PLANT_ENTITY,
            "Bedroom valve open",
        ),
    }
    for unique_id, (new_entity_id, name) in customizations.items():
        entities.async_update_entity(
            entity_ids[unique_id], new_entity_id=new_entity_id, name=name, icon="mdi:radiator"
        )
        entity_ids[unique_id] = new_entity_id
    return entity_ids


def _record_removals(hass) -> list[tuple[str, str]]:
    """Record every entity and device the registries remove from now on."""
    removals: list[tuple[str, str]] = []

    @callback
    def record_entity(event) -> None:
        if event.data["action"] == "remove":
            removals.append(("entity", event.data["entity_id"]))

    @callback
    def record_device(event) -> None:
        if event.data["action"] == "remove":
            removals.append(("device", event.data["device_id"]))

    hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, record_entity)
    hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, record_device)
    return removals


def _registration_ids(hass, entry: MockConfigEntry) -> set[tuple[str, str]]:
    """Return the internal ids of every entity and device of an entry."""
    return {
        ("entity", registry_entry.id)
        for registry_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    } | {
        ("device", device.id)
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    }


def _set_evidence_states(hass) -> None:
    for entity_id in ("sensor.living_temperature", "sensor.bedroom_temperature"):
        hass.states.async_set(entity_id, "20.0")
    for entity_id in (
        "switch.living_valve",
        "switch.bedroom_valve",
        "switch.manifold_pump",
        "switch.boiler_demand",
    ):
        hass.states.async_set(entity_id, "off")


def _assert_migrated_evidence_plant(
    hass, entry: MockConfigEntry, entity_ids: dict[str, str]
) -> None:
    """Assert the one final state that every migration path must reach."""
    assert (entry.version, entry.minor_version) == (3, 0)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data["topology"] == _evidence_topology()
    assert entry.data[CONF_DRY_RUN] is True
    assert "output_authorization" not in entry.data
    assert entry.data["requested_mode"] == "auto"
    # Derived ownership: the Bedroom loop is used only by the living room, and
    # everything the two rooms share stays with the Plant.
    assert entry.data[CONF_ROOM_OBJECTS] == {BEDROOM_LOOP: LIVING}
    assert entry.data[CONF_SUBENTRY_OBJECTS] == {
        LIVING: SUBENTRY_TYPE_ROOM,
        BEDROOM: SUBENTRY_TYPE_ROOM,
        BOILER: SUBENTRY_TYPE_SOURCE,
    }
    assert sorted(
        (subentry.subentry_type, subentry.unique_id, subentry.title, dict(subentry.data))
        for subentry in entry.subentries.values()
    ) == [
        (SUBENTRY_TYPE_ROOM, LIVING, "Living room", {"id": LIVING}),
        (SUBENTRY_TYPE_ROOM, BEDROOM, "Bedroom", {"id": BEDROOM}),
        (SUBENTRY_TYPE_SOURCE, BOILER, "Boiler", {"id": BOILER}),
    ]
    assert entry.subentries[BOILER_SUBENTRY].unique_id == BOILER

    targets = {
        LIVING: _room_id(entry, LIVING),
        BEDROOM: _room_id(entry, BEDROOM),
        LIVING_VALVE: None,
        BEDROOM_VALVE: None,
        PUMP: None,
        BOILER: BOILER_SUBENTRY,
    }
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    for object_id, target in targets.items():
        kind = _KINDS[object_id]
        device = devices.async_get_device_by_identifier(
            (DOMAIN, f"{PLANT_ID}:{kind}:{object_id}"), entry.entry_id
        )
        assert device is not None, object_id
        assert device.config_subentry_id == target, object_id
        for domain, unique_id, _slug in _version_2_registrations(object_id):
            registry_entry = entities.async_get(entity_ids[unique_id])
            assert registry_entry is not None, unique_id
            assert registry_entry.unique_id == unique_id
            assert registry_entry.domain == domain
            assert registry_entry.config_subentry_id == target, unique_id
            assert registry_entry.device_id == device.id, unique_id
            assert hass.states.get(entity_ids[unique_id]) is not None, unique_id
    for entity_id, name in (
        (CUSTOMIZED_ROOM_ENTITY, "Bedroom heat call"),
        (CUSTOMIZED_PLANT_ENTITY, "Bedroom valve open"),
    ):
        registry_entry = entities.async_get(entity_id)
        assert registry_entry is not None
        assert (registry_entry.name, registry_entry.icon) == (name, "mdi:radiator")
    # No entity was registered twice under a new entity ID.
    all_entity_ids = [
        registry_entry.entity_id
        for registry_entry in er.async_entries_for_config_entry(entities, entry.entry_id)
    ]
    assert not [entity_id for entity_id in all_entity_ids if entity_id.endswith("_2")]
    runtime = entry.runtime_data
    assert set(runtime.plant.zones) == {LIVING, BEDROOM}
    assert set(runtime.plant.circuits) == {LIVING_LOOP, BEDROOM_LOOP}
    assert runtime.plant.circuits[LIVING_LOOP].valve_ids == (LIVING_VALVE, BEDROOM_VALVE)


async def test_cross_wired_version_2_manifold_migrates_without_losing_registrations(
    hass,
) -> None:
    """Migration keeps entity IDs, customizations, device identifiers, and the graph."""
    _set_evidence_states(hass)
    entry = _evidence_version_2_entry()
    entry.add_to_hass(hass)
    entity_ids = _install_version_2_registry(hass, entry)
    registrations = _registration_ids(hass, entry)
    removals = _record_removals(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    _assert_migrated_evidence_plant(hass, entry, entity_ids)
    # Every registration was moved in place, never removed and restored.
    assert removals == []
    assert registrations <= _registration_ids(hass, entry)


# 0 means only the removal of objects deleted before migration has run.
_INTERRUPTIONS = range(len(ROOM_MIGRATION_STEPS))
_INTERRUPTION_IDS = ["after_version_2_removals"] + [
    f"after_step_{step}" for step in range(2, len(ROOM_MIGRATION_STEPS) + 1)
]


def _run_until_interrupted(hass, entry: MockConfigEntry, completed_steps: int) -> None:
    """Run the removal step and the first migration steps, as before a restart."""
    async_complete_version_2_removals(hass, entry)
    plan = room_migration_plan(entry)
    for step in ROOM_MIGRATION_STEPS[:completed_steps]:
        step(hass, entry, plan)
    assert (entry.version, entry.minor_version) == (2, 0)


@pytest.mark.parametrize("completed_steps", _INTERRUPTIONS, ids=_INTERRUPTION_IDS)
async def test_interrupted_migration_resumes_to_the_same_final_state(
    hass, completed_steps: int
) -> None:
    """A restart after the removal step or any of steps 2 to 6 resumes to the same result."""
    _set_evidence_states(hass)
    entry = _evidence_version_2_entry()
    entry.add_to_hass(hass)
    entity_ids = _install_version_2_registry(hass, entry)
    registrations = _registration_ids(hass, entry)
    removals = _record_removals(hass)
    _run_until_interrupted(hass, entry, completed_steps)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    _assert_migrated_evidence_plant(hass, entry, entity_ids)
    assert removals == []
    assert registrations <= _registration_ids(hass, entry)


@pytest.mark.parametrize(
    "completed_steps", [None, *_INTERRUPTIONS], ids=["uninterrupted", *_INTERRUPTION_IDS]
)
async def test_objects_deleted_before_migration_are_not_resurrected(
    hass, completed_steps: int | None
) -> None:
    """Handles deleted while a version 2 entry was unloaded delete their objects."""
    _set_evidence_states(hass)
    entry = _evidence_version_2_entry()
    entry.add_to_hass(hass)
    entity_ids = _install_version_2_registry(hass, entry)
    # Deleting a subentry of an unloaded entry clears its registrations, but no
    # reload runs to remove the objects from the stored graph.
    assert hass.config_entries.async_remove_subentry(entry, LEGACY_BEDROOM)
    assert hass.config_entries.async_remove_subentry(entry, LEGACY_BEDROOM_VALVE)
    assert BEDROOM in {zone["id"] for zone in entry.data["topology"]["zones"]}
    if completed_steps is not None:
        _run_until_interrupted(hass, entry, completed_steps)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (entry.version, entry.minor_version) == (3, 0)
    assert entry.state is ConfigEntryState.LOADED
    topology = entry.data["topology"]
    assert [zone["id"] for zone in topology["zones"]] == [LIVING]
    assert [valve["id"] for valve in topology["valves"]] == [LIVING_VALVE]
    assert [(circuit["id"], circuit["valve_ids"]) for circuit in topology["circuits"]] == [
        (LIVING_LOOP, [LIVING_VALVE]),
        (BEDROOM_LOOP, [LIVING_VALVE]),
    ]
    assert [route["id"] for route in topology["routes"]] == [
        LIVING_TO_LIVING_LOOP,
        LIVING_TO_BEDROOM_LOOP,
    ]
    assert entry.data[CONF_SUBENTRY_OBJECTS] == {
        LIVING: SUBENTRY_TYPE_ROOM,
        BOILER: SUBENTRY_TYPE_SOURCE,
    }
    assert entry.data[CONF_ROOM_OBJECTS] == {
        LIVING_LOOP: LIVING,
        BEDROOM_LOOP: LIVING,
        LIVING_VALVE: LIVING,
    }
    assert entry.data[CONF_DRY_RUN] is True
    assert "output_authorization" not in entry.data
    assert sorted(
        (subentry.subentry_type, subentry.unique_id) for subentry in entry.subentries.values()
    ) == [(SUBENTRY_TYPE_ROOM, LIVING), (SUBENTRY_TYPE_SOURCE, BOILER)]
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    for object_id in (BEDROOM, BEDROOM_VALVE):
        for _domain, unique_id, _slug in _version_2_registrations(object_id):
            assert entities.async_get(entity_ids[unique_id]) is None, unique_id
        assert (
            devices.async_get_device_by_identifier(
                (DOMAIN, f"{PLANT_ID}:{_KINDS[object_id]}:{object_id}"), entry.entry_id
            )
            is None
        )
    living_room = _room_id(entry, LIVING)
    for _domain, unique_id, _slug in _version_2_registrations(LIVING_VALVE):
        registry_entry = entities.async_get(entity_ids[unique_id])
        assert registry_entry is not None
        assert registry_entry.config_subentry_id == living_room
    assert set(entry.runtime_data.plant.zones) == {LIVING}


_OFFICE_PLANT = "00000000-0000-4000-8000-0000000a0001"
_OFFICE = "00000000-0000-4000-8000-0000000a0002"
_OFFICE_VALVE = "00000000-0000-4000-8000-0000000a0003"
_OFFICE_PUMP = "00000000-0000-4000-8000-0000000a0004"
_OFFICE_LOOP = "00000000-0000-4000-8000-0000000a0005"
_OFFICE_ROUTE = "00000000-0000-4000-8000-0000000a0006"


def _office_version_2_entry() -> MockConfigEntry:
    """Return a version 2 Plant whose one zone, loop, and valve all have legacy handles."""
    data = authorize_outputs(
        {
            "name": "Hydronic plant",
            "plant_id": _OFFICE_PLANT,
            "dry_run": True,
            "requested_mode": "auto",
            "topology": {
                "zones": [
                    {
                        "id": _OFFICE,
                        "name": "Office",
                        "thermostat": {"kind": "hydronicus"},
                        "temperature_sensor_metadata": [{"entity_id": "sensor.office"}],
                    }
                ],
                "valves": [{"id": _OFFICE_VALVE, "name": "Office valve", "entity_id": "switch.ov"}],
                "pumps": [{"id": _OFFICE_PUMP, "name": "Pump", "entity_id": "switch.op"}],
                "circuits": [
                    {
                        "id": _OFFICE_LOOP,
                        "name": "Office loop",
                        "valve_ids": [_OFFICE_VALVE],
                        "pump_id": _OFFICE_PUMP,
                    }
                ],
                "routes": [{"id": _OFFICE_ROUTE, "zone_id": _OFFICE, "circuit_id": _OFFICE_LOOP}],
            },
            "subentry_objects": {
                _OFFICE: SUBENTRY_TYPE_ZONE,
                _OFFICE_LOOP: SUBENTRY_TYPE_CIRCUIT,
                _OFFICE_VALVE: SUBENTRY_TYPE_ACTUATOR,
            },
        }
    )

    def handle(subentry_id: str, subentry_type: str, object_id: str) -> dict[str, Any]:
        return {
            "subentry_id": subentry_id,
            "subentry_type": subentry_type,
            "title": subentry_type,
            "unique_id": object_id,
            "data": {"id": object_id},
        }

    return MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        version=2,
        minor_version=0,
        data=data,
        subentries_data=[
            handle("LEGACYZONE", SUBENTRY_TYPE_ZONE, _OFFICE),
            handle("LEGACYLOOP", SUBENTRY_TYPE_CIRCUIT, _OFFICE_LOOP),
            handle("LEGACYVALVE", SUBENTRY_TYPE_ACTUATOR, _OFFICE_VALVE),
        ],
    )


@pytest.mark.parametrize(
    "completed_steps", [None, *_INTERRUPTIONS], ids=["uninterrupted", *_INTERRUPTION_IDS]
)
async def test_a_plant_whose_every_zone_was_deleted_keeps_its_equipment_when_resumed(
    hass, completed_steps: int | None
) -> None:
    """Without zones, a restart after any step still keeps the loop and valve as Plant equipment.

    After step 6 such a Plant has neither a room nor a legacy handle, which must not
    look like a migration that has not started, whose deleted handles delete objects.
    """
    entry = _office_version_2_entry()
    entry.add_to_hass(hass)
    # The only zone is deleted while the version 2 entry is unloaded.
    assert hass.config_entries.async_remove_subentry(entry, "LEGACYZONE")
    if completed_steps is not None:
        _run_until_interrupted(hass, entry, completed_steps)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (entry.version, entry.minor_version) == (3, 0)
    assert entry.state is ConfigEntryState.LOADED
    topology = entry.data["topology"]
    assert {
        key: [record["id"] for record in topology.get(key, [])]
        for key in ("zones", "valves", "pumps", "circuits", "routes")
    } == {
        "zones": [],
        "valves": [_OFFICE_VALVE],
        "pumps": [_OFFICE_PUMP],
        "circuits": [_OFFICE_LOOP],
        "routes": [],
    }
    assert entry.data[CONF_SUBENTRY_OBJECTS] == {}
    assert entry.data[CONF_ROOM_OBJECTS] == {}
    assert not entry.subentries


async def test_version_2_removals_that_break_the_graph_fail_migration(hass) -> None:
    """A reconciled version 2 graph that does not compile fails like other bad graphs."""
    entry = _evidence_version_2_entry()
    entry.add_to_hass(hass)
    data = deepcopy(dict(entry.data))
    # The Bedroom loop uses only the Bedroom valve, so deleting the valve empties it.
    data["topology"]["circuits"][1]["valve_ids"] = [BEDROOM_VALVE]
    hass.config_entries.async_update_entry(entry, data=data)
    assert hass.config_entries.async_remove_subentry(entry, LEGACY_BEDROOM_VALVE)
    stored = deepcopy(dict(entry.data))

    assert not await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (2, 0)
    assert dict(entry.data) == stored
    assert LEGACY_BEDROOM in entry.subentries
    assert not [
        subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_ROOM
        or str(subentry.unique_id).startswith("legacy:")
    ]


async def test_version_3_rejects_legacy_subentry_types(hass) -> None:
    """A version 3 entry carrying a zone, circuit, or actuator handle is invalid."""
    data = plant_data(_evidence_topology())
    entry = plant_entry(data)
    legacy = deepcopy(entry.subentries[f"handle-{BEDROOM}"].as_dict())
    corrupt = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        data=dict(entry.data),
        subentries_data=[
            *(
                subentry.as_dict()
                for subentry in entry.subentries.values()
                if subentry.unique_id != BEDROOM
            ),
            {**legacy, "subentry_type": SUBENTRY_TYPE_ZONE},
        ],
    )
    corrupt.add_to_hass(hass)

    with pytest.raises(ConfigEntryError) as error:
        await async_setup_entry(hass, corrupt)

    assert error.value.translation_key == "invalid_stored_graph"
    placeholders = error.value.translation_placeholders
    assert "Unsupported config subentry type 'zone'" in placeholders["error"]
