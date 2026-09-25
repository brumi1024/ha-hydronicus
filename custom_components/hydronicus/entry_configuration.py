"""Own the persisted Plant graph behind small Home Assistant subentry handles.

Config entry version 3 keeps the complete graph in the parent entry. A ``room``
subentry is a handle for one zone, and through ``room_objects`` for that room's
private loops and valves; a ``source`` subentry is a handle for one source.
Every other object belongs to the Plant. Removing a handle removes exactly what
it owns, and deletion-closed ownership keeps the remaining graph valid.

The graph edit functions here are pure over mappings, import nothing from Home
Assistant, validate ownership, compile, and return data in Dry run.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol
from uuid import UUID

from .const import (
    CONF_CIRCUITS,
    CONF_DIAGNOSTICS_INCLUDE_ACTUATOR_DETAILS,
    CONF_DRY_RUN,
    CONF_NAME,
    CONF_OUTPUT_AUTHORIZATION,
    CONF_PLANT_ID,
    CONF_PUMPS,
    CONF_ROOM_OBJECTS,
    CONF_ROUTES,
    CONF_SOURCES,
    CONF_SUBENTRY_OBJECTS,
    CONF_TOPOLOGY,
    CONF_VALVES,
    CONF_ZONES,
    SUBENTRY_TYPE_ROOM,
    SUBENTRY_TYPE_SOURCE,
)
from .core.configuration import StoredTopologyError, plant_configuration_from_entry_data
from .core.model import CompiledPlant, PlantConfiguration
from .core.ownership import OwnershipError, PlantOwnership, validate_ownership, without_room
from .core.topology import TopologyValidationError, compile_topology

SUPPORTED_SUBENTRY_TYPES = frozenset({SUBENTRY_TYPE_ROOM, SUBENTRY_TYPE_SOURCE})
_COLLECTION_BY_SUBENTRY_TYPE = {
    SUBENTRY_TYPE_ROOM: CONF_ZONES,
    SUBENTRY_TYPE_SOURCE: CONF_SOURCES,
}
_TOPOLOGY_COLLECTIONS = (
    CONF_ZONES,
    CONF_VALVES,
    CONF_PUMPS,
    CONF_CIRCUITS,
    CONF_ROUTES,
    CONF_SOURCES,
)
# Collections of objects that own an id, and the word the plant file uses for each.
_OBJECT_KINDS = (
    (CONF_ZONES, "room"),
    (CONF_CIRCUITS, "loop"),
    (CONF_VALVES, "valve"),
    (CONF_PUMPS, "pump"),
    (CONF_SOURCES, "source"),
)
# Every error a rejected graph edit can raise, for callers that report rather than raise.
GRAPH_EDIT_ERRORS: tuple[type[Exception], ...] = (
    StoredTopologyError,
    TopologyValidationError,
    OwnershipError,
)


class ImportedPlantLike(Protocol):
    """The parts of an imported plant file that replace a Plant graph."""

    @property
    def name(self) -> str:
        """Return the imported Plant name."""

    @property
    def topology(self) -> Mapping[str, Any]:
        """Return the stored version 3 topology collections."""

    @property
    def ownership(self) -> PlantOwnership:
        """Return the imported room ownership."""


@dataclass(frozen=True, slots=True)
class EffectivePlant:
    """A validated, compiled Plant graph and the subentries that own its objects."""

    configuration: PlantConfiguration
    ownership: PlantOwnership
    compiled: CompiledPlant
    # Zone, room-owned circuit and valve, and source ids -> owning subentry id.
    object_subentry_ids: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class RoomDraft:
    """Everything one room owns, as stored records."""

    zone: dict[str, Any]
    circuits: list[dict[str, Any]]
    valves: list[dict[str, Any]]
    routes: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SubentrySync:
    """Subentry changes that make the handles of an entry match new entry data."""

    add: list[dict[str, Any]]
    remove: list[str]
    retitle: list[tuple[str, str]]


class EquipmentInUseError(ValueError):
    """Plant equipment cannot be removed while loops still use it."""

    def __init__(self, users: tuple[str, ...]) -> None:
        self.users = users
        super().__init__("The equipment is used by " + ", ".join(users) + ".")


def runtime_configuration_fingerprint(entry: Any) -> str:
    """Hash only fields that require rebuilding the compiled HA runtime."""
    handles = []
    for subentry in sorted(
        getattr(entry, "subentries", {}).values(), key=lambda item: item.subentry_id
    ):
        handles.append(
            {
                "subentry_id": subentry.subentry_id,
                "subentry_type": subentry.subentry_type,
                "unique_id": subentry.unique_id,
                "data": dict(subentry.data),
            }
        )
    payload = {
        CONF_NAME: entry.data.get(CONF_NAME),
        CONF_PLANT_ID: entry.data.get(CONF_PLANT_ID),
        CONF_DIAGNOSTICS_INCLUDE_ACTUATOR_DETAILS: bool(
            entry.data.get(CONF_DIAGNOSTICS_INCLUDE_ACTUATOR_DETAILS, False)
        ),
        CONF_TOPOLOGY: topology_copy(entry.data),
        CONF_SUBENTRY_OBJECTS: subentry_objects(entry.data),
        CONF_ROOM_OBJECTS: room_objects(entry.data),
        "subentries": handles,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _required(data: Mapping[str, Any], key: str, owner: str) -> Any:
    try:
        return data[key]
    except KeyError as error:
        raise StoredTopologyError(f"{owner} is missing required field {key!r}.") from error


def _uuid(value: Any, owner: str) -> str:
    try:
        return str(UUID(str(value)))
    except ValueError as error:
        raise StoredTopologyError(f"{owner} must be a UUID.") from error


def record_object_id(data: Mapping[str, Any], owner: str) -> str:
    """Return the canonical UUID of one stored record or handle."""
    return _uuid(_required(data, "id", owner), f"{owner} id")


def canonical_id(object_id: Any) -> str:
    """Return a stored id in the canonical UUID form the core decoder uses.

    A value that is not a UUID is returned as its string, so a malformed stored
    id still compares and reports as written; the decoder rejects it.
    """
    raw = str(object_id)
    try:
        return str(UUID(raw))
    except ValueError:
        return raw


def topology_copy(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep copy of the stored topology with every collection present."""
    raw_topology = data.get(CONF_TOPOLOGY, {})
    if not isinstance(raw_topology, Mapping):
        raise StoredTopologyError("Stored topology must be an object.")
    topology = deepcopy(dict(raw_topology))
    for collection in _TOPOLOGY_COLLECTIONS:
        raw_records = topology.get(collection, [])
        if not isinstance(raw_records, list) or not all(
            isinstance(record, Mapping) for record in raw_records
        ):
            raise StoredTopologyError(
                f"Stored topology field {collection!r} must be a list of objects."
            )
        topology[collection] = [deepcopy(dict(record)) for record in raw_records]
    return topology


def subentry_objects(data: Mapping[str, Any]) -> dict[str, str]:
    """Return the stored object id -> handle type map of every room and source handle."""
    raw_handles = data.get(CONF_SUBENTRY_OBJECTS, {})
    if not isinstance(raw_handles, Mapping):
        raise StoredTopologyError(f"Stored field {CONF_SUBENTRY_OBJECTS!r} must be an object.")
    handles: dict[str, str] = {}
    for raw_object_id, raw_subentry_type in raw_handles.items():
        object_id = _uuid(raw_object_id, "Subentry-owned object id")
        subentry_type = str(raw_subentry_type)
        if subentry_type not in SUPPORTED_SUBENTRY_TYPES:
            raise StoredTopologyError(
                f"Subentry-owned object {object_id} has unsupported type {subentry_type!r}."
            )
        handles[object_id] = subentry_type
    return handles


def room_objects(data: Mapping[str, Any]) -> dict[str, str]:
    """Return the stored private circuit or valve id -> owning zone id map."""
    raw_owners = data.get(CONF_ROOM_OBJECTS, {})
    if not isinstance(raw_owners, Mapping):
        raise StoredTopologyError(f"Stored field {CONF_ROOM_OBJECTS!r} must be an object.")
    return {
        _uuid(object_id, "Room-owned object id"): _uuid(zone_id, "Owning zone id")
        for object_id, zone_id in raw_owners.items()
    }


def plant_ownership(data: Mapping[str, Any]) -> PlantOwnership:
    """Return the stored room ownership of one Plant."""
    return PlantOwnership(room_objects=room_objects(data))


def records(topology: Mapping[str, Any], collection: str) -> list[dict[str, Any]]:
    """Return one stored topology collection, the list itself rather than a copy."""
    stored = topology[collection]
    if not isinstance(stored, list):
        raise StoredTopologyError(f"Stored topology field {collection!r} must be a list.")
    return stored


def _record_by_id(topology: Mapping[str, Any], collection: str, object_id: str) -> dict[str, Any]:
    matches = [
        record
        for record in records(topology, collection)
        if canonical_id(record.get("id")) == object_id
    ]
    if len(matches) != 1:
        raise StoredTopologyError(
            f"Stored {collection} must contain exactly one object with id {object_id}."
        )
    return deepcopy(matches[0])


def replace_record(
    topology: dict[str, Any], collection: str, object_id: str, record: Mapping[str, Any]
) -> None:
    """Replace the record with the canonical id ``object_id`` in place, or append it."""
    stored = records(topology, collection)
    for index, current in enumerate(stored):
        if canonical_id(current.get("id")) == object_id:
            stored[index] = deepcopy(dict(record))
            return
    stored.append(deepcopy(dict(record)))


def _all_handles(topology: Mapping[str, Any]) -> dict[str, str]:
    """Give every zone a room handle and every source a source handle."""
    handles = {
        canonical_id(zone.get("id")): SUBENTRY_TYPE_ROOM for zone in records(topology, CONF_ZONES)
    }
    handles.update(
        {
            canonical_id(source.get("id")): SUBENTRY_TYPE_SOURCE
            for source in records(topology, CONF_SOURCES)
        }
    )
    return handles


def _validated(data: Mapping[str, Any]) -> tuple[PlantConfiguration, PlantOwnership, CompiledPlant]:
    """Decode, check ownership and room handles, and compile one stored graph."""
    configuration = plant_configuration_from_entry_data(data)
    ownership = plant_ownership(data)
    validate_ownership(configuration, ownership)
    handles = subentry_objects(data)
    zone_ids = {zone.id for zone in configuration.zones}
    source_ids = {source.id for source in configuration.sources}
    for object_id, subentry_type in handles.items():
        if subentry_type == SUBENTRY_TYPE_ROOM and object_id not in zone_ids:
            raise StoredTopologyError(f"Room handle {object_id} does not name a stored zone.")
        if subentry_type == SUBENTRY_TYPE_SOURCE and object_id not in source_ids:
            raise StoredTopologyError(f"Source handle {object_id} does not name a stored source.")
    if unhandled := sorted(
        zone_id for zone_id in zone_ids if handles.get(zone_id) != SUBENTRY_TYPE_ROOM
    ):
        raise StoredTopologyError("Zones without a room handle: " + ", ".join(unhandled) + ".")
    return configuration, ownership, compile_topology(configuration)


def _subentry_object_id(subentry: Any) -> str:
    data = subentry.data
    if not isinstance(data, Mapping):
        raise StoredTopologyError("Config subentry data must be an object.")
    if set(data) != {"id"}:
        raise StoredTopologyError(
            f"Subentry {subentry.subentry_id} must contain only its object id."
        )
    object_id = record_object_id(data, f"Subentry {subentry.subentry_id}")
    if subentry.unique_id != object_id:
        raise StoredTopologyError(
            f"Subentry {subentry.subentry_id} unique id must match object id {object_id}."
        )
    return object_id


def _present_handles(entry: Any, handles: Mapping[str, str]) -> dict[str, str]:
    """Return object id -> subentry id for every valid handle subentry of an entry."""
    present: dict[str, str] = {}
    for subentry in getattr(entry, "subentries", {}).values():
        subentry_type = str(subentry.subentry_type)
        if subentry_type not in SUPPORTED_SUBENTRY_TYPES:
            raise StoredTopologyError(f"Unsupported config subentry type {subentry_type!r}.")
        object_id = _subentry_object_id(subentry)
        if object_id in present:
            raise StoredTopologyError(f"Multiple subentries own object {object_id}.")
        if handles.get(object_id) != subentry_type:
            raise StoredTopologyError(
                f"Subentry {subentry.subentry_id} has no matching parent ownership record."
            )
        present[object_id] = subentry.subentry_id
    return present


def effective_plant_from_data(data: Mapping[str, Any]) -> EffectivePlant:
    """Validate and compile stored data that has no subentries yet."""
    configuration, ownership, compiled = _validated(data)
    return EffectivePlant(
        configuration=configuration,
        ownership=ownership,
        compiled=compiled,
        object_subentry_ids={},
    )


def effective_plant(entry: Any) -> EffectivePlant:
    """Validate and compile the graph of an entry, with the subentry owning each object."""
    plant = effective_plant_from_data(entry.data)
    handles = subentry_objects(entry.data)
    present = _present_handles(entry, handles)
    if orphaned := sorted(set(handles) - set(present)):
        raise StoredTopologyError(
            "Subentry-owned objects without a config subentry: " + ", ".join(orphaned) + "."
        )
    owners = dict(present)
    owners.update(
        {object_id: present[zone_id] for object_id, zone_id in plant.ownership.room_objects.items()}
    )
    return EffectivePlant(
        configuration=plant.configuration,
        ownership=plant.ownership,
        compiled=plant.compiled,
        object_subentry_ids=owners,
    )


def _finalized(data: dict[str, Any]) -> dict[str, Any]:
    """Return to Dry run, then prove the edited graph valid before anyone stores it."""
    updated = invalidate_output_authorization(data)
    _validated(updated)
    return updated


def new_plant_data(
    *, name: str, plant_id: str, topology: Mapping[str, Any], ownership: PlantOwnership
) -> dict[str, Any]:
    """Return version 3 data for a new Plant, with a handle for every zone and source."""
    stored_topology = topology_copy({CONF_TOPOLOGY: topology})
    return _finalized(
        {
            CONF_NAME: name,
            CONF_PLANT_ID: plant_id,
            CONF_DRY_RUN: True,
            CONF_TOPOLOGY: stored_topology,
            CONF_SUBENTRY_OBJECTS: _all_handles(stored_topology),
            CONF_ROOM_OBJECTS: dict(ownership.room_objects),
        }
    )


def room_draft(data: Mapping[str, Any], zone_id: str) -> RoomDraft:
    """Return the stored records one room owns."""
    topology = topology_copy(data)
    owners = room_objects(data)
    zone_id = _uuid(zone_id, "Room zone id")

    def private(collection: str) -> list[dict[str, Any]]:
        return [
            deepcopy(record)
            for record in records(topology, collection)
            if owners.get(canonical_id(record.get("id"))) == zone_id
        ]

    return RoomDraft(
        zone=_record_by_id(topology, CONF_ZONES, zone_id),
        circuits=private(CONF_CIRCUITS),
        valves=private(CONF_VALVES),
        routes=[
            deepcopy(route)
            for route in records(topology, CONF_ROUTES)
            if _uuid(route.get("zone_id"), "Stored route zone id") == zone_id
        ],
    )


def _merged(
    stored: list[dict[str, Any]],
    replaceable_ids: set[str],
    drafted: Iterable[Mapping[str, Any]],
    collection: str,
) -> list[dict[str, Any]]:
    """Replace a room's records in place, drop the ones it no longer has, append new ones."""
    new_by_id: dict[str, dict[str, Any]] = {}
    for record in drafted:
        object_id = record_object_id(record, f"Room {collection} record")
        if object_id in new_by_id:
            raise StoredTopologyError(f"Room {collection} repeat id {object_id}.")
        new_by_id[object_id] = deepcopy(dict(record))
    stored_ids = {canonical_id(record.get("id")) for record in stored}
    if taken := sorted((set(new_by_id) & stored_ids) - replaceable_ids):
        raise StoredTopologyError(
            f"Room {collection} " + ", ".join(taken) + " belong to the Plant or another room."
        )
    merged: list[dict[str, Any]] = []
    for record in stored:
        object_id = canonical_id(record.get("id"))
        if object_id not in replaceable_ids:
            merged.append(record)
        elif object_id in new_by_id:
            merged.append(new_by_id.pop(object_id))
    merged.extend(new_by_id.values())
    return merged


def data_with_room(data: Mapping[str, Any], draft: RoomDraft) -> dict[str, Any]:
    """Insert a room, or replace everything the room with this zone id owns."""
    zone_id = record_object_id(draft.zone, "Room zone")
    for route in draft.routes:
        if _uuid(_required(route, "zone_id", "Room route"), "Room route zone id") != zone_id:
            raise StoredTopologyError("Every room route must start at the room's zone.")
    updated = deepcopy(dict(data))
    topology = topology_copy(updated)
    owners = room_objects(updated)
    private_ids = {object_id for object_id, owner in owners.items() if owner == zone_id}
    replaceable = {
        CONF_ZONES: {zone_id},
        CONF_CIRCUITS: private_ids,
        CONF_VALVES: private_ids,
        CONF_ROUTES: {
            canonical_id(route.get("id"))
            for route in records(topology, CONF_ROUTES)
            if _uuid(route.get("zone_id"), "Stored route zone id") == zone_id
        },
    }
    drafted = {
        CONF_ZONES: [draft.zone],
        CONF_CIRCUITS: draft.circuits,
        CONF_VALVES: draft.valves,
        CONF_ROUTES: draft.routes,
    }
    for collection, drafted_records in drafted.items():
        topology[collection] = _merged(
            records(topology, collection), replaceable[collection], drafted_records, collection
        )
    owners = {object_id: owner for object_id, owner in owners.items() if owner != zone_id}
    for record in (*draft.circuits, *draft.valves):
        owners[record_object_id(record, "Room record")] = zone_id
    handles = subentry_objects(updated)
    handles[zone_id] = SUBENTRY_TYPE_ROOM
    updated[CONF_TOPOLOGY] = topology
    updated[CONF_SUBENTRY_OBJECTS] = handles
    updated[CONF_ROOM_OBJECTS] = owners
    return _finalized(updated)


def data_with_pump(
    data: Mapping[str, Any], pump_id: str, record: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Insert or replace one Plant pump, or remove it when ``record`` is ``None``."""
    pump_id = _uuid(pump_id, "Pump id")
    updated = deepcopy(dict(data))
    topology = topology_copy(updated)
    if record is None:
        _record_by_id(topology, CONF_PUMPS, pump_id)
        if users := tuple(
            str(circuit.get(CONF_NAME, canonical_id(circuit.get("id"))))
            for circuit in records(topology, CONF_CIRCUITS)
            if str(circuit.get("pump_id")) == pump_id
        ):
            raise EquipmentInUseError(users)
        topology[CONF_PUMPS] = [
            pump
            for pump in records(topology, CONF_PUMPS)
            if canonical_id(pump.get("id")) != pump_id
        ]
    else:
        if "id" in record and record_object_id(record, "Pump record") != pump_id:
            raise StoredTopologyError("A pump record id must match its pump id.")
        replace_record(topology, CONF_PUMPS, pump_id, {"id": pump_id, **record})
    updated[CONF_TOPOLOGY] = topology
    return _finalized(updated)


def data_with_source(data: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    """Insert or replace one source that a source subentry owns."""
    source_id = record_object_id(record, "Source record")
    updated = deepcopy(dict(data))
    topology = topology_copy(updated)
    replace_record(topology, CONF_SOURCES, source_id, record)
    handles = subentry_objects(updated)
    handles[source_id] = SUBENTRY_TYPE_SOURCE
    updated[CONF_TOPOLOGY] = topology
    updated[CONF_SUBENTRY_OBJECTS] = handles
    return _finalized(updated)


def _objects_by_id(topology: Mapping[str, Any]) -> dict[str, tuple[str, Mapping[str, Any]]]:
    """Return object id -> (kind, record) for every zone, loop, valve, pump, and source."""
    return {
        canonical_id(record.get("id")): (kind, record)
        for collection, kind in _OBJECT_KINDS
        for record in records(topology, collection)
    }


def object_ids(data: Mapping[str, Any]) -> set[str]:
    """Return the id of every zone, loop, valve, pump, and source of stored data."""
    return set(_objects_by_id(topology_copy(data)))


def data_with_plant(data: Mapping[str, Any], imported: ImportedPlantLike) -> dict[str, Any]:
    """Replace the name, topology, and ownership, giving every zone and source a handle.

    An object id keeps its kind: a room, loop, valve, pump, or source cannot take
    the id of an object of another kind, even one the file removes, because the
    handles and registrations of that id belong to the old object.
    """
    updated = deepcopy(dict(data))
    topology = topology_copy({CONF_TOPOLOGY: imported.topology})
    try:
        current = _objects_by_id(topology_copy(data))
    except StoredTopologyError:
        # A stored graph whose collections do not even read can still be replaced.
        current = {}
    for object_id, (kind, record) in _objects_by_id(topology).items():
        if object_id in current and (old := current[object_id])[0] != kind:
            raise StoredTopologyError(
                f"The {kind} {record.get(CONF_NAME, object_id)} uses the id {object_id} of the "
                f"{old[0]} {old[1].get(CONF_NAME, object_id)}; give the {kind} its own id."
            )
    updated[CONF_NAME] = imported.name
    updated[CONF_TOPOLOGY] = topology
    updated[CONF_SUBENTRY_OBJECTS] = _all_handles(topology)
    updated[CONF_ROOM_OBJECTS] = dict(imported.ownership.room_objects)
    return _finalized(updated)


def subentries_for(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the room and source handles of stored data, for ``async_create_entry``."""
    topology = topology_copy(data)
    handles: list[dict[str, Any]] = []
    for object_id, subentry_type in subentry_objects(data).items():
        record = _record_by_id(topology, _COLLECTION_BY_SUBENTRY_TYPE[subentry_type], object_id)
        handles.append(
            {
                "data": {"id": object_id},
                "subentry_type": subentry_type,
                "title": str(record.get(CONF_NAME, "")),
                "unique_id": object_id,
            }
        )
    return handles


def subentry_sync(entry: Any, data: Mapping[str, Any]) -> SubentrySync:
    """Return the handles to add, remove, and retitle so an entry matches new data."""
    desired = {
        (handle["subentry_type"], handle["unique_id"]): handle for handle in subentries_for(data)
    }
    kept: set[tuple[str, str]] = set()
    remove: list[str] = []
    retitle: list[tuple[str, str]] = []
    for subentry in getattr(entry, "subentries", {}).values():
        key = (str(subentry.subentry_type), str(subentry.unique_id))
        handle = desired.get(key)
        if handle is None or key in kept:
            remove.append(subentry.subentry_id)
            continue
        kept.add(key)
        if subentry.title != handle["title"]:
            retitle.append((subentry.subentry_id, handle["title"]))
    return SubentrySync(
        add=[handle for key, handle in desired.items() if key not in kept],
        remove=remove,
        retitle=retitle,
    )


def subentry_draft(entry: Any, subentry: Any) -> dict[str, Any]:
    """Return the stored record behind one room or source handle."""
    subentry_type = str(subentry.subentry_type)
    if subentry_type not in SUPPORTED_SUBENTRY_TYPES:
        raise StoredTopologyError(f"Unsupported config subentry type {subentry_type!r}.")
    return _record_by_id(
        topology_copy(entry.data),
        _COLLECTION_BY_SUBENTRY_TYPE[subentry_type],
        _subentry_object_id(subentry),
    )


def _data_without_room(data: Mapping[str, Any], zone_id: str) -> dict[str, Any]:
    """Remove one room closure from stored data, keeping the order of the rest."""
    remaining, ownership = without_room(
        plant_configuration_from_entry_data(data), plant_ownership(data), zone_id
    )
    kept_ids = {
        CONF_ZONES: {zone.id for zone in remaining.zones},
        CONF_VALVES: {valve.id for valve in remaining.valves},
        CONF_CIRCUITS: {circuit.id for circuit in remaining.circuits},
        CONF_ROUTES: {route.id for route in remaining.routes},
    }
    updated = deepcopy(dict(data))
    topology = topology_copy(updated)
    for collection, object_ids in kept_ids.items():
        topology[collection] = [
            record
            for record in records(topology, collection)
            if canonical_id(record.get("id")) in object_ids
        ]
    updated[CONF_TOPOLOGY] = topology
    updated[CONF_ROOM_OBJECTS] = dict(ownership.room_objects)
    return updated


def _data_without_source(data: Mapping[str, Any], source_id: str) -> dict[str, Any]:
    updated = deepcopy(dict(data))
    topology = topology_copy(updated)
    topology[CONF_SOURCES] = [
        record
        for record in records(topology, CONF_SOURCES)
        if canonical_id(record.get("id")) != source_id
    ]
    updated[CONF_TOPOLOGY] = topology
    return updated


def reconcile_removed_subentries(entry: Any) -> dict[str, Any] | None:
    """Remove what each vanished room or source handle owned, or return ``None``."""
    handles = subentry_objects(entry.data)
    present = _present_handles(entry, handles)
    missing = [object_id for object_id in handles if object_id not in present]
    if not missing:
        return None
    data = deepcopy(dict(entry.data))
    try:
        for object_id in missing:
            if handles[object_id] == SUBENTRY_TYPE_ROOM:
                data = _data_without_room(data, object_id)
            else:
                data = _data_without_source(data, object_id)
            del handles[object_id]
        data[CONF_SUBENTRY_OBJECTS] = dict(handles)
        return _finalized(data)
    except GRAPH_EDIT_ERRORS as error:
        raise StoredTopologyError(
            "Removing the deleted subentries would leave an invalid Plant graph."
        ) from error


def output_authorization(data: Mapping[str, Any]) -> dict[str, Any]:
    """Bind one explicit authorization to this graph and exact physical outputs."""
    topology = topology_copy(data)
    fingerprint_input = {
        CONF_PLANT_ID: data.get(CONF_PLANT_ID),
        CONF_TOPOLOGY: topology,
    }
    fingerprint = sha256(
        json.dumps(
            fingerprint_input,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    outputs: list[dict[str, str]] = []
    for kind, collection in (("valve", CONF_VALVES), ("pump", CONF_PUMPS)):
        for record in records(topology, collection):
            entity_id = record.get("entity_id")
            if isinstance(entity_id, str) and entity_id:
                outputs.append(
                    {
                        "kind": kind,
                        "id": record_object_id(record, f"Stored {kind}"),
                        "entity_id": entity_id,
                    }
                )
    for record in records(topology, CONF_SOURCES):
        entity_id = record.get("source_demand_entity")
        if isinstance(entity_id, str) and entity_id:
            outputs.append(
                {
                    "kind": "source_demand",
                    "id": record_object_id(record, "Stored source"),
                    "entity_id": entity_id,
                }
            )
    outputs.sort(key=lambda item: (item["kind"], item["id"], item["entity_id"]))
    return {"schema": 1, "fingerprint": fingerprint, "outputs": outputs}


def output_authorization_is_valid(data: Mapping[str, Any]) -> bool:
    """Return whether stored authorization exactly matches the current graph."""
    stored = data.get(CONF_OUTPUT_AUTHORIZATION)
    return isinstance(stored, Mapping) and dict(stored) == output_authorization(data)


def authorize_outputs(data: Mapping[str, Any]) -> dict[str, Any]:
    """Persist an exact authorization and leave Dry run for the current graph."""
    updated = deepcopy(dict(data))
    updated[CONF_OUTPUT_AUTHORIZATION] = output_authorization(updated)
    updated[CONF_DRY_RUN] = False
    return updated


def invalidate_output_authorization(data: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed after any topology or binding change."""
    updated = deepcopy(dict(data))
    updated[CONF_DRY_RUN] = True
    updated.pop(CONF_OUTPUT_AUTHORIZATION, None)
    return updated


def exclusive_output_entity_ids(data: Mapping[str, Any]) -> frozenset[str]:
    """Return the entities a live Plant commands, which no other live Plant may command.

    These are exactly the authorized outputs. The source selector is left out
    because the runtime keeps every source-selector operation in Dry run, so no
    Plant ever commands it; add it here if that ever changes.
    """
    return frozenset(output["entity_id"] for output in output_authorization(data)["outputs"])


def authorization_output_lines(data: Mapping[str, Any]) -> str:
    """Render exact output bindings, and the source selector, for confirmation forms."""
    lines = [
        f"- {output['kind']}: {output['entity_id']}"
        for output in output_authorization(data)["outputs"]
    ]
    selector = topology_copy(data).get("source_selector")
    if isinstance(selector, Mapping) and isinstance(selector.get("entity_id"), str):
        lines.append(
            f"- source_selector: {selector['entity_id']} (source selection stays in Dry run)"
        )
    if not lines:
        return "- No physical outputs are configured"
    return "\n".join(lines)
