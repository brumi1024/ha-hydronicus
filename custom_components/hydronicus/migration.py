"""Migrate stored Hydronicus config entries to the current storage version.

Version 1.1 kept topology in zone, circuit, actuator, and source subentries, and
version 2.0 moved it into the parent while keeping one handle per object. Version
3.0 replaces the zone, circuit, and actuator handles with one ``room`` handle per
zone. The legacy subentry type names live only in this module.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    ACTUATOR_KIND_VALVE,
    CONF_ACTUATOR_KIND,
    CONF_CIRCUIT_IDS,
    CONF_CIRCUITS,
    CONF_PLANT_ID,
    CONF_REQUESTED_MODE,
    CONF_ROOM_OBJECTS,
    CONF_ROUTES,
    CONF_SOURCES,
    CONF_SUBENTRY_OBJECTS,
    CONF_TOPOLOGY,
    CONF_VALVES,
    CONF_ZONE_IDS,
    CONF_ZONES,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SUBENTRY_TYPE_ROOM,
    SUBENTRY_TYPE_SOURCE,
)
from .core.configuration import StoredTopologyError, plant_configuration_from_entry_data
from .core.model import PlantMode
from .core.ownership import derive_ownership
from .core.topology import compile_topology
from .entry_configuration import (
    canonical_id,
    invalidate_output_authorization,
    record_object_id,
    records,
    replace_record,
    topology_copy,
)

SUBENTRY_TYPE_ACTUATOR = "actuator"
SUBENTRY_TYPE_CIRCUIT = "circuit"
SUBENTRY_TYPE_ZONE = "zone"
LEGACY_SUBENTRY_TYPES = frozenset(
    {SUBENTRY_TYPE_ACTUATOR, SUBENTRY_TYPE_CIRCUIT, SUBENTRY_TYPE_ZONE}
)
VERSION_2_SUBENTRY_TYPES = LEGACY_SUBENTRY_TYPES | {SUBENTRY_TYPE_SOURCE}
LEGACY_UNIQUE_ID_PREFIX = "legacy:"
_COLLECTION_BY_SUBENTRY_TYPE = {
    SUBENTRY_TYPE_ACTUATOR: CONF_VALVES,
    SUBENTRY_TYPE_CIRCUIT: CONF_CIRCUITS,
    SUBENTRY_TYPE_SOURCE: CONF_SOURCES,
    SUBENTRY_TYPE_ZONE: CONF_ZONES,
}
_UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


# Version 1.1 to 2.0: fold the topology of legacy subentries into the parent.


@dataclass(frozen=True, slots=True)
class SubentryMigration:
    """One validated legacy subentry update applied after its graph is durable."""

    subentry: Any
    object_id: str


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """A restart-safe parent graph and the handles that should point into it."""

    data: Mapping[str, Any]
    subentries: tuple[SubentryMigration, ...]


def _required(data: Mapping[str, Any], key: str, owner: str) -> Any:
    try:
        return data[key]
    except KeyError as error:
        raise StoredTopologyError(f"{owner} is missing required field {key!r}.") from error


def _remove_records(
    topology: dict[str, Any],
    collection: str,
    predicate: Callable[[Mapping[str, Any]], bool],
) -> None:
    topology[collection] = [
        record for record in records(topology, collection) if not predicate(record)
    ]


def _version_2_handles(data: Mapping[str, Any]) -> dict[str, str]:
    """Return the version 1.1 and 2.0 object id -> legacy subentry type map."""
    raw_handles = data.get(CONF_SUBENTRY_OBJECTS, {})
    if not isinstance(raw_handles, Mapping):
        raise StoredTopologyError(f"Stored field {CONF_SUBENTRY_OBJECTS!r} must be an object.")
    handles: dict[str, str] = {}
    for raw_object_id, raw_subentry_type in raw_handles.items():
        object_id = record_object_id({"id": raw_object_id}, "Subentry-owned object")
        subentry_type = str(raw_subentry_type)
        if subentry_type not in VERSION_2_SUBENTRY_TYPES:
            raise StoredTopologyError(
                f"Subentry-owned object {object_id} has unsupported type {subentry_type!r}."
            )
        handles[object_id] = subentry_type
    return handles


def _object_exists(topology: Mapping[str, Any], subentry_type: str, object_id: str) -> bool:
    collection = _COLLECTION_BY_SUBENTRY_TYPE[subentry_type]
    return any(
        canonical_id(record.get("id")) == object_id for record in records(topology, collection)
    )


def _route_flag(route: Mapping[str, Any]) -> dict[str, Any]:
    return {"enabled": route["enabled"]} if "enabled" in route else {}


def _route_endpoint(raw_route: Any, key: str, owner: str) -> str:
    if not isinstance(raw_route, Mapping):
        raise StoredTopologyError(f"{owner} routes must be objects.")
    return record_object_id({"id": _required(raw_route, key, f"{owner} route")}, f"{owner} {key}")


def _apply_zone(topology: dict[str, Any], draft: Mapping[str, Any]) -> str:
    zone_id = record_object_id(draft, "Zone draft")
    circuit_ids = _required(draft, CONF_CIRCUIT_IDS, "Zone draft")
    routes = _required(draft, CONF_ROUTES, "Zone draft")
    if not isinstance(circuit_ids, list) or not isinstance(routes, list):
        raise StoredTopologyError("Zone draft relationships must be lists.")
    canonical = deepcopy(dict(draft))
    for key in (
        CONF_CIRCUIT_IDS,
        CONF_ROUTES,
        "temperature_sensors",
        "humidity_sensors",
        "configure_sensor_metadata",
    ):
        canonical.pop(key, None)
    replace_record(topology, CONF_ZONES, zone_id, canonical)
    _remove_records(
        topology, CONF_ROUTES, lambda route: canonical_id(route.get("zone_id")) == zone_id
    )
    for raw_route in routes:
        circuit_id = _route_endpoint(raw_route, "circuit_id", "Zone draft")
        records(topology, CONF_ROUTES).append(
            {
                "id": record_object_id(raw_route, "Zone draft route"),
                "zone_id": zone_id,
                "circuit_id": circuit_id,
                **_route_flag(raw_route),
            }
        )
    if {canonical_id(value) for value in circuit_ids} != {
        canonical_id(route["circuit_id"])
        for route in records(topology, CONF_ROUTES)
        if canonical_id(route.get("zone_id")) == zone_id
    }:
        raise StoredTopologyError("Zone draft routes must match its selected circuit ids.")
    return zone_id


def _apply_circuit(topology: dict[str, Any], draft: Mapping[str, Any]) -> str:
    circuit_id = record_object_id(draft, "Circuit draft")
    zone_ids = _required(draft, CONF_ZONE_IDS, "Circuit draft")
    routes = _required(draft, CONF_ROUTES, "Circuit draft")
    if not isinstance(zone_ids, list) or not isinstance(routes, list):
        raise StoredTopologyError("Circuit draft relationships must be lists.")
    canonical = deepcopy(dict(draft))
    canonical.pop(CONF_ZONE_IDS, None)
    canonical.pop(CONF_ROUTES, None)
    replace_record(topology, CONF_CIRCUITS, circuit_id, canonical)
    _remove_records(
        topology, CONF_ROUTES, lambda route: canonical_id(route.get("circuit_id")) == circuit_id
    )
    for raw_route in routes:
        zone_id = _route_endpoint(raw_route, "zone_id", "Circuit draft")
        records(topology, CONF_ROUTES).append(
            {
                "id": record_object_id(raw_route, "Circuit draft route"),
                "zone_id": zone_id,
                "circuit_id": circuit_id,
                **_route_flag(raw_route),
            }
        )
    if {canonical_id(value) for value in zone_ids} != {
        canonical_id(route["zone_id"])
        for route in records(topology, CONF_ROUTES)
        if canonical_id(route.get("circuit_id")) == circuit_id
    }:
        raise StoredTopologyError("Circuit draft routes must match its selected zone ids.")
    return circuit_id


def _apply_actuator(topology: dict[str, Any], draft: Mapping[str, Any]) -> str:
    kind = str(_required(draft, CONF_ACTUATOR_KIND, "Actuator draft"))
    if kind != ACTUATOR_KIND_VALVE:
        raise StoredTopologyError(f"Unsupported actuator draft kind {kind!r}.")
    actuator_id = record_object_id(draft, "Actuator draft")
    circuit_ids = _required(draft, CONF_CIRCUIT_IDS, "Actuator draft")
    if not isinstance(circuit_ids, list) or not circuit_ids:
        raise StoredTopologyError("Actuator draft requires at least one circuit id.")
    selected_circuit_ids = {
        record_object_id({"id": circuit_id}, "Actuator draft circuit") for circuit_id in circuit_ids
    }
    canonical = deepcopy(dict(draft))
    canonical.pop(CONF_ACTUATOR_KIND, None)
    canonical.pop(CONF_CIRCUIT_IDS, None)
    replace_record(topology, CONF_VALVES, actuator_id, canonical)
    known_circuit_ids = {
        record_object_id(circuit, "Stored circuit") for circuit in records(topology, CONF_CIRCUITS)
    }
    if unknown := selected_circuit_ids - known_circuit_ids:
        raise StoredTopologyError(
            "Actuator draft references unknown circuits: " + ", ".join(sorted(unknown)) + "."
        )
    for circuit in records(topology, CONF_CIRCUITS):
        circuit_id = record_object_id(circuit, "Stored circuit")
        raw_valve_ids = circuit.get("valve_ids", [])
        if not isinstance(raw_valve_ids, list):
            raise StoredTopologyError("Stored circuit valve ids must be a list.")
        valve_ids = [str(value) for value in raw_valve_ids if canonical_id(value) != actuator_id]
        if circuit_id in selected_circuit_ids:
            valve_ids.append(actuator_id)
        circuit["valve_ids"] = valve_ids
    return actuator_id


def _apply_source(topology: dict[str, Any], draft: Mapping[str, Any]) -> str:
    source_id = record_object_id(draft, "Source draft")
    replace_record(topology, CONF_SOURCES, source_id, draft)
    return source_id


_APPLY_BY_SUBENTRY_TYPE: dict[str, Callable[[dict[str, Any], Mapping[str, Any]], str]] = {
    SUBENTRY_TYPE_ACTUATOR: _apply_actuator,
    SUBENTRY_TYPE_CIRCUIT: _apply_circuit,
    SUBENTRY_TYPE_SOURCE: _apply_source,
    SUBENTRY_TYPE_ZONE: _apply_zone,
}


def migration_plan(entry: Any) -> MigrationPlan:
    """Build a restart-safe version 2 graph from version 1.1 hybrid storage."""
    data = deepcopy(dict(entry.data))
    topology = topology_copy(data)
    handles = _version_2_handles(data)
    updates: list[SubentryMigration] = []
    seen_object_ids: set[str] = set()
    for subentry in sorted(
        getattr(entry, "subentries", {}).values(), key=lambda item: item.subentry_id
    ):
        subentry_type = str(subentry.subentry_type)
        if subentry_type not in VERSION_2_SUBENTRY_TYPES:
            raise StoredTopologyError(f"Unsupported config subentry type {subentry_type!r}.")
        if not isinstance(subentry.data, Mapping):
            raise StoredTopologyError("Config subentry data must be an object.")
        object_id = record_object_id(subentry.data, f"Subentry {subentry.subentry_id}")
        if object_id in seen_object_ids:
            raise StoredTopologyError(f"Multiple subentries own object {object_id}.")
        seen_object_ids.add(object_id)
        if set(subentry.data) == {"id"}:
            if not _object_exists(topology, subentry_type, object_id):
                raise StoredTopologyError(
                    f"Migrated subentry {subentry.subentry_id} references missing "
                    f"object {object_id}."
                )
        else:
            _APPLY_BY_SUBENTRY_TYPE[subentry_type](topology, subentry.data)
        handles[object_id] = subentry_type
        updates.append(SubentryMigration(subentry=subentry, object_id=object_id))
    data[CONF_TOPOLOGY] = topology
    data[CONF_SUBENTRY_OBJECTS] = handles
    data.setdefault(CONF_REQUESTED_MODE, PlantMode.AUTO.value)
    data = invalidate_output_authorization(data)
    compile_topology(plant_configuration_from_entry_data(data))
    return MigrationPlan(data=data, subentries=tuple(updates))


@callback
def async_migrate_1_1_to_2_0(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Fold legacy subentry topology into the parent, then minimize the handles."""
    plan = migration_plan(entry)
    # Make every migrated object durable in the parent before minimizing any
    # legacy subentry. A restart can safely repeat either half.
    hass.config_entries.async_update_entry(entry, data=dict(plan.data))
    for update in plan.subentries:
        hass.config_entries.async_update_subentry(
            entry,
            update.subentry,
            data={"id": update.object_id},
            unique_id=update.object_id,
        )
    hass.config_entries.async_update_entry(entry, version=2, minor_version=0)


# Version 2.0 to 3.0: one room handle per zone, registrations follow ownership.


@dataclass(frozen=True, slots=True)
class RoomMigrationPlan:
    """The version 3 graph and owner of every object, computed from the topology alone."""

    data: Mapping[str, Any]
    room_titles: Mapping[str, str]  # zone id -> room title
    # Object id -> (subentry type, handle object id) of its owner, or None for the Plant.
    owners: Mapping[str, tuple[str, str] | None]


def room_migration_plan(entry: Any) -> RoomMigrationPlan:
    """Derive ownership from a version 2 topology, and the version 3 data it yields.

    The plan reads only the stored topology and the source handles, which no
    step changes, so a restart at any step computes the same plan again.
    """
    data = deepcopy(dict(entry.data))
    topology = topology_copy(data)
    configuration = plant_configuration_from_entry_data(data)
    compile_topology(configuration)
    ownership = derive_ownership(configuration)
    # Source handles are unchanged by this migration, so present ones stay.
    handled_sources = {
        source.id
        for source in configuration.sources
        if _subentry_for(entry, SUBENTRY_TYPE_SOURCE, source.id) is not None
    }
    owners: dict[str, tuple[str, str] | None] = {}
    for zone in configuration.zones:
        owners[zone.id] = (SUBENTRY_TYPE_ROOM, zone.id)
    for circuit in configuration.circuits:
        zone_id = ownership.room_objects.get(circuit.id)
        owners[circuit.id] = (SUBENTRY_TYPE_ROOM, zone_id) if zone_id else None
    for valve in configuration.valves:
        zone_id = ownership.room_objects.get(valve.id)
        owners[valve.id] = (SUBENTRY_TYPE_ROOM, zone_id) if zone_id else None
    for pump in configuration.pumps:
        owners[pump.id] = None
    for source in configuration.sources:
        owners[source.id] = (
            (SUBENTRY_TYPE_SOURCE, source.id) if source.id in handled_sources else None
        )
    handles = {zone.id: SUBENTRY_TYPE_ROOM for zone in configuration.zones}
    handles.update(
        {
            source.id: SUBENTRY_TYPE_SOURCE
            for source in configuration.sources
            if source.id in handled_sources
        }
    )
    data[CONF_TOPOLOGY] = topology
    data[CONF_SUBENTRY_OBJECTS] = handles
    data[CONF_ROOM_OBJECTS] = dict(ownership.room_objects)
    data.setdefault(CONF_REQUESTED_MODE, PlantMode.AUTO.value)
    return RoomMigrationPlan(
        data=invalidate_output_authorization(data),
        room_titles={zone.id: zone.name for zone in configuration.zones},
        owners=owners,
    )


def _subentry_for(entry: ConfigEntry, subentry_type: str, unique_id: str) -> ConfigSubentry | None:
    return next(
        (
            subentry
            for subentry in entry.subentries.values()
            if subentry.subentry_type == subentry_type and subentry.unique_id == unique_id
        ),
        None,
    )


def _legacy_subentries(entry: ConfigEntry) -> list[ConfigSubentry]:
    return [
        subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type in LEGACY_SUBENTRY_TYPES
    ]


def _migration_started(entry: ConfigEntry) -> bool:
    """Return whether step 2 or later ran: a room exists or a legacy handle was renamed."""
    return any(
        subentry.subentry_type == SUBENTRY_TYPE_ROOM
        or str(subentry.unique_id).startswith(LEGACY_UNIQUE_ID_PREFIX)
        for subentry in entry.subentries.values()
    )


def _remove_version_2_object(topology: dict[str, Any], subentry_type: str, object_id: str) -> None:
    """Remove one object the way version 2 removed it with its deleted handle."""
    collection = _COLLECTION_BY_SUBENTRY_TYPE[subentry_type]
    _remove_records(
        topology, collection, lambda record: canonical_id(record.get("id")) == object_id
    )
    if subentry_type == SUBENTRY_TYPE_ZONE:
        _remove_records(
            topology, CONF_ROUTES, lambda route: canonical_id(route.get("zone_id")) == object_id
        )
    elif subentry_type == SUBENTRY_TYPE_CIRCUIT:
        _remove_records(
            topology, CONF_ROUTES, lambda route: canonical_id(route.get("circuit_id")) == object_id
        )
    elif subentry_type == SUBENTRY_TYPE_ACTUATOR:
        for circuit in records(topology, CONF_CIRCUITS):
            raw_valve_ids = circuit.get("valve_ids", [])
            if isinstance(raw_valve_ids, list):
                circuit["valve_ids"] = [
                    valve_id for valve_id in raw_valve_ids if canonical_id(valve_id) != object_id
                ]


@callback
def async_complete_version_2_removals(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the objects whose version 2 handles were deleted while the entry was unloaded.

    Deleting a subentry of an unloaded entry clears its registrations, but no reload
    removes the object from the stored graph, and migration must not bring it back as
    a room or as Plant equipment. This runs before step 2 and writes version 2 data,
    so a restart finds nothing left to remove. Once step 2 has run it does nothing,
    because after step 6 every legacy handle is gone and would look deleted. A
    Plant without zones has no room to show that step 2 ran, so step 6 drops the
    legacy records from ``subentry_objects`` before it removes their handles.
    """
    if _migration_started(entry):
        return
    handles = _version_2_handles(entry.data)
    present = {
        (str(subentry.subentry_type), str(subentry.unique_id))
        for subentry in entry.subentries.values()
    }
    deleted = [
        (object_id, subentry_type)
        for object_id, subentry_type in handles.items()
        if (subentry_type, object_id) not in present
    ]
    if not deleted:
        return
    data = deepcopy(dict(entry.data))
    topology = topology_copy(data)
    for object_id, subentry_type in deleted:
        _remove_version_2_object(topology, subentry_type, object_id)
        del handles[object_id]
    data[CONF_TOPOLOGY] = topology
    data[CONF_SUBENTRY_OBJECTS] = handles
    data = invalidate_output_authorization(data)
    compile_topology(plant_configuration_from_entry_data(data))
    hass.config_entries.async_update_entry(entry, data=data)


def _owner_subentry_ids(entry: ConfigEntry, plan: RoomMigrationPlan) -> dict[str, str | None]:
    """Resolve every planned owner to the subentry id that now represents it."""
    resolved: dict[str, str | None] = {}
    for object_id, owner in plan.owners.items():
        if owner is None:
            resolved[object_id] = None
            continue
        subentry = _subentry_for(entry, *owner)
        if subentry is None:
            raise StoredTopologyError(f"Object {object_id} has no {owner[0]} subentry to move to.")
        resolved[object_id] = subentry.subentry_id
    return resolved


_PLANT: Final = "plant"


def _object_of_unique_id(unique_id: str, plant_id: str, owners: Mapping[str, Any]) -> str | None:
    """Return the object an entity unique ID names, ``_PLANT``, or ``None`` when unknown.

    The object is the first UUID in the unique ID, other than the Plant id, that
    ``owners`` knows. A unique ID with no such UUID at all belongs to the Plant. A
    unique ID naming only unknown objects is left alone: its object is gone, and
    its registration goes with its handle or is removed with its object.
    """
    candidates = [
        candidate for candidate in _UUID_PATTERN.findall(unique_id.lower()) if candidate != plant_id
    ]
    if not candidates:
        return _PLANT
    return next((candidate for candidate in candidates if candidate in owners), None)


def _object_of_device(device: dr.DeviceEntry, plant_id: str) -> str | None:
    """Return the object id of a ``<plant_id>:<kind>:<object_id>`` topology device."""
    for domain, identifier in device.identifiers:
        parts = identifier.split(":")
        if domain == DOMAIN and len(parts) == 3 and parts[0] == plant_id:
            return parts[2]
    return None


@callback
def _async_move_entities(
    hass: HomeAssistant, entry: ConfigEntry, owners: Mapping[str, str | None]
) -> None:
    registry = er.async_get(hass)
    plant_id = str(entry.data.get(CONF_PLANT_ID, ""))
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        object_id = _object_of_unique_id(str(registry_entry.unique_id), plant_id, owners)
        if object_id is None:
            continue
        target = None if object_id == _PLANT else owners[object_id]
        if registry_entry.config_subentry_id != target:
            registry.async_update_entity(
                registry_entry.entity_id,
                config_entry_id=entry.entry_id,
                config_subentry_id=target,
            )


@callback
def _async_move_devices(
    hass: HomeAssistant, entry: ConfigEntry, owners: Mapping[str, str | None]
) -> None:
    registry = dr.async_get(hass)
    plant_id = str(entry.data.get(CONF_PLANT_ID, ""))
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        object_id = _object_of_device(device, plant_id)
        if object_id is None or object_id not in owners:
            continue
        target = owners[object_id]
        if device.config_subentry_id != target:
            registry.async_update_device(device.id, new_config_subentry_id=target)


@callback
def async_move_object_registrations(
    hass: HomeAssistant, entry: ConfigEntry, owners: Mapping[str, str | None]
) -> None:
    """Move the entities and devices of every object in ``owners`` to its subentry.

    ``None`` moves them to the parent entry. Entities move before devices, because
    Home Assistant removes the entities a device leaves behind in its old subentry.
    Nothing is renamed: unique IDs and device identifiers carry no subentry id.
    """
    _async_move_entities(hass, entry, owners)
    _async_move_devices(hass, entry, owners)


@callback
def async_remove_object_registrations(
    hass: HomeAssistant, entry: ConfigEntry, object_ids: Collection[str]
) -> None:
    """Remove the entities and devices of objects that no longer exist in the graph.

    Graph edits that drop objects, such as removing a pump, a loop, or a valve,
    call this in the same synchronous block that stores the edited graph.
    """
    if not object_ids:
        return
    plant_id = str(entry.data.get(CONF_PLANT_ID, ""))
    entity_registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if any(object_id in str(registry_entry.unique_id) for object_id in object_ids):
            entity_registry.async_remove(registry_entry.entity_id)
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if any(
            identifier.split(":")[0] == plant_id and identifier.split(":")[-1] in object_ids
            for _domain, identifier in device.identifiers
        ):
            device_registry.async_remove_device(device.id)


@callback
def _step_free_object_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry, plan: RoomMigrationPlan
) -> None:
    """Step 2: give legacy handles ``legacy:<object id>`` so rooms can take the object ids."""
    for subentry in _legacy_subentries(entry):
        unique_id = str(subentry.unique_id)
        if not unique_id.startswith(LEGACY_UNIQUE_ID_PREFIX):
            hass.config_entries.async_update_subentry(
                entry, subentry, unique_id=f"{LEGACY_UNIQUE_ID_PREFIX}{unique_id}"
            )


@callback
def _step_add_rooms(hass: HomeAssistant, entry: ConfigEntry, plan: RoomMigrationPlan) -> None:
    """Step 3: add a room handle for every zone that has none."""
    for zone_id, title in plan.room_titles.items():
        if _subentry_for(entry, SUBENTRY_TYPE_ROOM, zone_id) is None:
            hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data=MappingProxyType({"id": zone_id}),
                    subentry_type=SUBENTRY_TYPE_ROOM,
                    title=title,
                    unique_id=zone_id,
                ),
            )


@callback
def _step_move_entities(hass: HomeAssistant, entry: ConfigEntry, plan: RoomMigrationPlan) -> None:
    """Step 4: move every object entity to the subentry of its target owner."""
    _async_move_entities(hass, entry, _owner_subentry_ids(entry, plan))


@callback
def _step_move_devices(hass: HomeAssistant, entry: ConfigEntry, plan: RoomMigrationPlan) -> None:
    """Step 5: move every topology device to the same owner as its entities."""
    _async_move_devices(hass, entry, _owner_subentry_ids(entry, plan))


@callback
def _step_remove_legacy_subentries(
    hass: HomeAssistant, entry: ConfigEntry, plan: RoomMigrationPlan
) -> None:
    """Step 6: remove the legacy handles, which by now own no entities or devices.

    Their records leave ``subentry_objects`` first, in the same synchronous block.
    A Plant whose every zone was deleted has no room, so after this step nothing
    marks the migration as started; with no legacy record left, a rerun of the
    version 2 removals then finds no deleted handle and removes nothing.
    """
    handles = _version_2_handles(entry.data)
    kept = {
        object_id: subentry_type
        for object_id, subentry_type in handles.items()
        if subentry_type not in LEGACY_SUBENTRY_TYPES
    }
    if kept != handles:
        data = deepcopy(dict(entry.data))
        data[CONF_SUBENTRY_OBJECTS] = kept
        hass.config_entries.async_update_entry(entry, data=data)
    for subentry in _legacy_subentries(entry):
        hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)


@callback
def _step_write_version_3(hass: HomeAssistant, entry: ConfigEntry, plan: RoomMigrationPlan) -> None:
    """Step 7: write the version 3 data and version in one update."""
    hass.config_entries.async_update_entry(
        entry,
        data=dict(plan.data),
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
    )


# Steps 2 to 7 of the K3 migration, in order. ``async_complete_version_2_removals``
# runs first, then step 1 is ``room_migration_plan``.
ROOM_MIGRATION_STEPS: tuple[
    Callable[[HomeAssistant, ConfigEntry, RoomMigrationPlan], None], ...
] = (
    _step_free_object_unique_ids,
    _step_add_rooms,
    _step_move_entities,
    _step_move_devices,
    _step_remove_legacy_subentries,
    _step_write_version_3,
)


@callback
def async_migrate_2_0_to_3_0(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Replace legacy handles with rooms; every step resumes safely after a restart."""
    async_complete_version_2_removals(hass, entry)
    plan = room_migration_plan(entry)
    for step in ROOM_MIGRATION_STEPS:
        step(hass, entry, plan)
