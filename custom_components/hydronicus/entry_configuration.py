"""Own the persisted Plant graph behind small Home Assistant subentry handles."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID

from .const import (
    ACTUATOR_KIND_VALVE,
    CONF_ACTUATOR_KIND,
    CONF_CIRCUIT_IDS,
    CONF_CIRCUITS,
    CONF_DIAGNOSTICS_INCLUDE_ACTUATOR_DETAILS,
    CONF_DRY_RUN,
    CONF_NAME,
    CONF_OUTPUT_AUTHORIZATION,
    CONF_PLANT_ID,
    CONF_PUMPS,
    CONF_REQUESTED_MODE,
    CONF_ROUTES,
    CONF_SOURCES,
    CONF_SUBENTRY_OBJECTS,
    CONF_TOPOLOGY,
    CONF_VALVES,
    CONF_ZONE_IDS,
    CONF_ZONES,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_CIRCUIT,
    SUBENTRY_TYPE_SOURCE,
    SUBENTRY_TYPE_ZONE,
)
from .core.configuration import StoredTopologyError, plant_configuration_from_entry_data
from .core.model import PlantConfiguration, PlantMode
from .core.topology import TopologyValidationError, compile_topology

_SUPPORTED_SUBENTRY_TYPES = frozenset(
    {
        SUBENTRY_TYPE_ACTUATOR,
        SUBENTRY_TYPE_CIRCUIT,
        SUBENTRY_TYPE_SOURCE,
        SUBENTRY_TYPE_ZONE,
    }
)
_COLLECTION_BY_SUBENTRY_TYPE = {
    SUBENTRY_TYPE_ACTUATOR: CONF_VALVES,
    SUBENTRY_TYPE_CIRCUIT: CONF_CIRCUITS,
    SUBENTRY_TYPE_SOURCE: CONF_SOURCES,
    SUBENTRY_TYPE_ZONE: CONF_ZONES,
}
_TOPOLOGY_COLLECTIONS = (
    CONF_ZONES,
    CONF_VALVES,
    CONF_PUMPS,
    CONF_CIRCUITS,
    CONF_ROUTES,
    CONF_SOURCES,
)


@dataclass(frozen=True, slots=True)
class EffectivePlantConfiguration:
    """A parent-owned Plant graph and entity-owning subentry ids."""

    configuration: PlantConfiguration
    actuator_subentry_ids: Mapping[str, str]
    zone_subentry_ids: Mapping[str, str]
    source_subentry_ids: Mapping[str, str]


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
        CONF_TOPOLOGY: _topology_copy(entry.data),
        CONF_SUBENTRY_OBJECTS: _ownership(entry.data),
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


def _object_id(data: Mapping[str, Any], owner: str) -> str:
    return _uuid(_required(data, "id", owner), f"{owner} id")


def _topology_copy(data: Mapping[str, Any]) -> dict[str, Any]:
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


def _ownership(data: Mapping[str, Any]) -> dict[str, str]:
    raw_ownership = data.get(CONF_SUBENTRY_OBJECTS, {})
    if not isinstance(raw_ownership, Mapping):
        raise StoredTopologyError(f"Stored field {CONF_SUBENTRY_OBJECTS!r} must be an object.")
    ownership: dict[str, str] = {}
    for raw_object_id, raw_subentry_type in raw_ownership.items():
        object_id = _uuid(raw_object_id, "Subentry-owned object id")
        subentry_type = str(raw_subentry_type)
        if subentry_type not in _SUPPORTED_SUBENTRY_TYPES:
            raise StoredTopologyError(
                f"Subentry-owned object {object_id} has unsupported type {subentry_type!r}."
            )
        ownership[object_id] = subentry_type
    return ownership


def _records(topology: Mapping[str, Any], collection: str) -> list[dict[str, Any]]:
    records = topology[collection]
    if not isinstance(records, list):
        raise StoredTopologyError(f"Stored topology field {collection!r} must be a list.")
    return records


def _record_by_id(topology: Mapping[str, Any], collection: str, object_id: str) -> dict[str, Any]:
    matches = [
        record for record in _records(topology, collection) if str(record.get("id")) == object_id
    ]
    if len(matches) != 1:
        raise StoredTopologyError(
            f"Stored {collection} must contain exactly one object with id {object_id}."
        )
    return deepcopy(matches[0])


def _object_exists(topology: Mapping[str, Any], subentry_type: str, object_id: str) -> bool:
    collection = _COLLECTION_BY_SUBENTRY_TYPE[subentry_type]
    return any(str(record.get("id")) == object_id for record in _records(topology, collection))


def _replace_record(
    topology: dict[str, Any], collection: str, object_id: str, record: Mapping[str, Any]
) -> None:
    records = _records(topology, collection)
    for index, current in enumerate(records):
        if str(current.get("id")) == object_id:
            records[index] = deepcopy(dict(record))
            return
    records.append(deepcopy(dict(record)))


def _remove_records(
    topology: dict[str, Any],
    collection: str,
    predicate: Callable[[Mapping[str, Any]], bool],
) -> None:
    topology[collection] = [
        record for record in _records(topology, collection) if not predicate(record)
    ]


def _remove_object(topology: dict[str, Any], subentry_type: str, object_id: str) -> None:
    collection = _COLLECTION_BY_SUBENTRY_TYPE[subentry_type]
    _remove_records(topology, collection, lambda record: str(record.get("id")) == object_id)
    if subentry_type == SUBENTRY_TYPE_ZONE:
        _remove_records(
            topology,
            CONF_ROUTES,
            lambda route: str(route.get("zone_id")) == object_id,
        )
    elif subentry_type == SUBENTRY_TYPE_CIRCUIT:
        _remove_records(
            topology,
            CONF_ROUTES,
            lambda route: str(route.get("circuit_id")) == object_id,
        )
    elif subentry_type == SUBENTRY_TYPE_ACTUATOR:
        for circuit in _records(topology, CONF_CIRCUITS):
            raw_valve_ids = circuit.get("valve_ids", [])
            if isinstance(raw_valve_ids, list):
                circuit["valve_ids"] = [
                    valve_id for valve_id in raw_valve_ids if str(valve_id) != object_id
                ]


def _route_flag(route: Mapping[str, Any]) -> dict[str, Any]:
    return {"enabled": route["enabled"]} if "enabled" in route else {}


def _apply_zone(topology: dict[str, Any], draft: Mapping[str, Any]) -> str:
    zone_id = _object_id(draft, "Zone draft")
    circuit_ids = _required(draft, CONF_CIRCUIT_IDS, "Zone draft")
    routes = _required(draft, CONF_ROUTES, "Zone draft")
    if not isinstance(circuit_ids, list) or not isinstance(routes, list):
        raise StoredTopologyError("Zone draft relationships must be lists.")
    canonical = deepcopy(dict(draft))
    canonical.pop(CONF_CIRCUIT_IDS, None)
    canonical.pop(CONF_ROUTES, None)
    canonical.pop("temperature_sensors", None)
    canonical.pop("humidity_sensors", None)
    canonical.pop("configure_sensor_metadata", None)
    _replace_record(topology, CONF_ZONES, zone_id, canonical)
    _remove_records(
        topology,
        CONF_ROUTES,
        lambda route: str(route.get("zone_id")) == zone_id,
    )
    for raw_route in routes:
        if not isinstance(raw_route, Mapping):
            raise StoredTopologyError("Zone draft routes must be objects.")
        circuit_id = _uuid(
            _required(raw_route, "circuit_id", "Zone draft route"),
            "Zone draft route circuit id",
        )
        route = {
            "id": _object_id(raw_route, "Zone draft route"),
            "zone_id": zone_id,
            "circuit_id": circuit_id,
            **_route_flag(raw_route),
        }
        _records(topology, CONF_ROUTES).append(route)
    if {str(value) for value in circuit_ids} != {
        str(route["circuit_id"])
        for route in _records(topology, CONF_ROUTES)
        if str(route.get("zone_id")) == zone_id
    }:
        raise StoredTopologyError("Zone draft routes must match its selected circuit ids.")
    return zone_id


def _apply_circuit(topology: dict[str, Any], draft: Mapping[str, Any]) -> str:
    circuit_id = _object_id(draft, "Circuit draft")
    zone_ids = _required(draft, CONF_ZONE_IDS, "Circuit draft")
    routes = _required(draft, CONF_ROUTES, "Circuit draft")
    if not isinstance(zone_ids, list) or not isinstance(routes, list):
        raise StoredTopologyError("Circuit draft relationships must be lists.")
    canonical = deepcopy(dict(draft))
    canonical.pop(CONF_ZONE_IDS, None)
    canonical.pop(CONF_ROUTES, None)
    _replace_record(topology, CONF_CIRCUITS, circuit_id, canonical)
    _remove_records(
        topology,
        CONF_ROUTES,
        lambda route: str(route.get("circuit_id")) == circuit_id,
    )
    for raw_route in routes:
        if not isinstance(raw_route, Mapping):
            raise StoredTopologyError("Circuit draft routes must be objects.")
        zone_id = _uuid(
            _required(raw_route, "zone_id", "Circuit draft route"),
            "Circuit draft route zone id",
        )
        route = {
            "id": _object_id(raw_route, "Circuit draft route"),
            "zone_id": zone_id,
            "circuit_id": circuit_id,
            **_route_flag(raw_route),
        }
        _records(topology, CONF_ROUTES).append(route)
    if {str(value) for value in zone_ids} != {
        str(route["zone_id"])
        for route in _records(topology, CONF_ROUTES)
        if str(route.get("circuit_id")) == circuit_id
    }:
        raise StoredTopologyError("Circuit draft routes must match its selected zone ids.")
    return circuit_id


def _apply_actuator(topology: dict[str, Any], draft: Mapping[str, Any]) -> str:
    kind = str(_required(draft, CONF_ACTUATOR_KIND, "Actuator draft"))
    if kind != ACTUATOR_KIND_VALVE:
        raise StoredTopologyError(f"Unsupported actuator draft kind {kind!r}.")
    actuator_id = _object_id(draft, "Actuator draft")
    circuit_ids = _required(draft, CONF_CIRCUIT_IDS, "Actuator draft")
    if not isinstance(circuit_ids, list) or not circuit_ids:
        raise StoredTopologyError("Actuator draft requires at least one circuit id.")
    selected_circuit_ids = {
        _uuid(circuit_id, "Actuator draft circuit id") for circuit_id in circuit_ids
    }
    canonical = deepcopy(dict(draft))
    canonical.pop(CONF_ACTUATOR_KIND, None)
    canonical.pop(CONF_CIRCUIT_IDS, None)
    _replace_record(topology, CONF_VALVES, actuator_id, canonical)
    known_circuit_ids = {
        _object_id(circuit, "Stored circuit") for circuit in _records(topology, CONF_CIRCUITS)
    }
    if unknown := selected_circuit_ids - known_circuit_ids:
        raise StoredTopologyError(
            "Actuator draft references unknown circuits: " + ", ".join(sorted(unknown)) + "."
        )
    for circuit in _records(topology, CONF_CIRCUITS):
        circuit_id = _object_id(circuit, "Stored circuit")
        raw_valve_ids = circuit.get("valve_ids", [])
        if not isinstance(raw_valve_ids, list):
            raise StoredTopologyError("Stored circuit valve ids must be a list.")
        valve_ids = [str(value) for value in raw_valve_ids if str(value) != actuator_id]
        if circuit_id in selected_circuit_ids:
            valve_ids.append(actuator_id)
        circuit["valve_ids"] = valve_ids
    return actuator_id


def _apply_source(topology: dict[str, Any], draft: Mapping[str, Any]) -> str:
    source_id = _object_id(draft, "Source draft")
    _replace_record(topology, CONF_SOURCES, source_id, draft)
    return source_id


def _apply_draft(topology: dict[str, Any], subentry_type: str, draft: Mapping[str, Any]) -> str:
    if subentry_type == SUBENTRY_TYPE_ZONE:
        return _apply_zone(topology, draft)
    if subentry_type == SUBENTRY_TYPE_CIRCUIT:
        return _apply_circuit(topology, draft)
    if subentry_type == SUBENTRY_TYPE_ACTUATOR:
        return _apply_actuator(topology, draft)
    if subentry_type == SUBENTRY_TYPE_SOURCE:
        return _apply_source(topology, draft)
    raise StoredTopologyError(f"Unsupported subentry type {subentry_type!r}.")


def _subentry_object_id(subentry: Any, *, require_descriptor: bool) -> str:
    data = subentry.data
    if not isinstance(data, Mapping):
        raise StoredTopologyError("Config subentry data must be an object.")
    if require_descriptor and set(data) != {"id"}:
        raise StoredTopologyError(
            f"Version 2 subentry {subentry.subentry_id} must contain only its object id."
        )
    object_id = _object_id(data, f"Subentry {subentry.subentry_id}")
    if subentry.unique_id != object_id:
        raise StoredTopologyError(
            f"Subentry {subentry.subentry_id} unique id must match object id {object_id}."
        )
    return object_id


def _subentry_maps(
    entry: Any,
    topology: Mapping[str, Any],
    ownership: Mapping[str, str],
    *,
    excluded_subentry_id: str | None = None,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    actuator_ids: dict[str, str] = {}
    zone_ids: dict[str, str] = {}
    source_ids: dict[str, str] = {}
    seen_object_ids: set[str] = set()
    for subentry in getattr(entry, "subentries", {}).values():
        if subentry.subentry_id == excluded_subentry_id:
            continue
        subentry_type = str(subentry.subentry_type)
        if subentry_type not in _SUPPORTED_SUBENTRY_TYPES:
            raise StoredTopologyError(f"Unsupported config subentry type {subentry_type!r}.")
        object_id = _subentry_object_id(subentry, require_descriptor=True)
        if object_id in seen_object_ids:
            raise StoredTopologyError(f"Multiple subentries own object {object_id}.")
        seen_object_ids.add(object_id)
        if ownership.get(object_id) != subentry_type:
            raise StoredTopologyError(
                f"Subentry {subentry.subentry_id} has no matching parent ownership record."
            )
        if not _object_exists(topology, subentry_type, object_id):
            raise StoredTopologyError(
                f"Subentry {subentry.subentry_id} references missing object {object_id}."
            )
        target = {
            SUBENTRY_TYPE_ACTUATOR: actuator_ids,
            SUBENTRY_TYPE_ZONE: zone_ids,
            SUBENTRY_TYPE_SOURCE: source_ids,
        }.get(subentry_type)
        if target is not None:
            target[object_id] = subentry.subentry_id
    return actuator_ids, zone_ids, source_ids


def _entry_data_with_drafts(
    entry: Any,
    *,
    proposed_actuators: Sequence[Mapping[str, Any]] = (),
    proposed_circuits: Sequence[Mapping[str, Any]] = (),
    proposed_zones: Sequence[Mapping[str, Any]] = (),
    proposed_sources: Sequence[Mapping[str, Any]] = (),
    excluded_subentry_id: str | None = None,
    claim_subentry_objects: bool = False,
    invalidate_authorization: bool = False,
) -> dict[str, Any]:
    data = deepcopy(dict(entry.data))
    topology = _topology_copy(data)
    ownership = _ownership(data)
    excluded_object_id: str | None = None
    excluded_type: str | None = None
    if excluded_subentry_id is not None:
        try:
            subentry = entry.subentries[excluded_subentry_id]
        except KeyError as error:
            raise StoredTopologyError(
                f"Unknown excluded subentry {excluded_subentry_id}."
            ) from error
        excluded_type = str(subentry.subentry_type)
        excluded_object_id = _subentry_object_id(subentry, require_descriptor=True)
        _remove_object(topology, excluded_type, excluded_object_id)

    applied: list[tuple[str, str]] = []
    for subentry_type, drafts in (
        (SUBENTRY_TYPE_ACTUATOR, proposed_actuators),
        (SUBENTRY_TYPE_CIRCUIT, proposed_circuits),
        (SUBENTRY_TYPE_ZONE, proposed_zones),
        (SUBENTRY_TYPE_SOURCE, proposed_sources),
    ):
        for draft in drafts:
            object_id = _apply_draft(topology, subentry_type, draft)
            applied.append((object_id, subentry_type))

    if excluded_object_id is not None and applied != [(excluded_object_id, excluded_type)]:
        raise StoredTopologyError(
            "A subentry reconfiguration must replace the same object and object type."
        )
    if claim_subentry_objects:
        ownership.update(applied)
    data[CONF_TOPOLOGY] = topology
    data[CONF_SUBENTRY_OBJECTS] = ownership
    if invalidate_authorization:
        data = invalidate_output_authorization(data)
    return data


def effective_plant_configuration(
    entry: Any,
    *,
    proposed_actuators: Sequence[Mapping[str, Any]] = (),
    proposed_circuits: Sequence[Mapping[str, Any]] = (),
    proposed_zones: Sequence[Mapping[str, Any]] = (),
    proposed_sources: Sequence[Mapping[str, Any]] = (),
    excluded_subentry_id: str | None = None,
) -> EffectivePlantConfiguration:
    """Read only the parent graph and optionally compile one flow proposal."""
    data = _entry_data_with_drafts(
        entry,
        proposed_actuators=proposed_actuators,
        proposed_circuits=proposed_circuits,
        proposed_zones=proposed_zones,
        proposed_sources=proposed_sources,
        excluded_subentry_id=excluded_subentry_id,
    )
    topology = _topology_copy(data)
    ownership = _ownership(data)
    actuator_ids, zone_ids, source_ids = _subentry_maps(
        entry,
        topology,
        ownership,
        excluded_subentry_id=excluded_subentry_id,
    )
    return EffectivePlantConfiguration(
        configuration=plant_configuration_from_entry_data(data),
        actuator_subentry_ids=actuator_ids,
        zone_subentry_ids=zone_ids,
        source_subentry_ids=source_ids,
    )


def entry_data_with_subentry_draft(
    entry: Any,
    subentry_type: str,
    draft: Mapping[str, Any],
    *,
    excluded_subentry_id: str | None = None,
) -> dict[str, Any]:
    """Persist one validated draft into the parent graph and return to Dry run."""
    proposals: dict[str, tuple[Mapping[str, Any], ...]] = {
        SUBENTRY_TYPE_ACTUATOR: (),
        SUBENTRY_TYPE_CIRCUIT: (),
        SUBENTRY_TYPE_ZONE: (),
        SUBENTRY_TYPE_SOURCE: (),
    }
    if subentry_type not in proposals:
        raise StoredTopologyError(f"Unsupported subentry type {subentry_type!r}.")
    proposals[subentry_type] = (draft,)
    data = _entry_data_with_drafts(
        entry,
        proposed_actuators=proposals[SUBENTRY_TYPE_ACTUATOR],
        proposed_circuits=proposals[SUBENTRY_TYPE_CIRCUIT],
        proposed_zones=proposals[SUBENTRY_TYPE_ZONE],
        proposed_sources=proposals[SUBENTRY_TYPE_SOURCE],
        excluded_subentry_id=excluded_subentry_id,
        claim_subentry_objects=True,
        invalidate_authorization=True,
    )
    compile_topology(plant_configuration_from_entry_data(data))
    return data


def subentry_draft(entry: Any, subentry: Any) -> dict[str, Any]:
    """Rebuild the complete UI draft for one minimal subentry handle."""
    topology = _topology_copy(entry.data)
    object_id = _subentry_object_id(subentry, require_descriptor=True)
    subentry_type = str(subentry.subentry_type)
    if subentry_type not in _SUPPORTED_SUBENTRY_TYPES:
        raise StoredTopologyError(f"Unsupported config subentry type {subentry_type!r}.")
    record = _record_by_id(
        topology,
        _COLLECTION_BY_SUBENTRY_TYPE[subentry_type],
        object_id,
    )
    if subentry_type == SUBENTRY_TYPE_ZONE:
        routes = [
            {
                "id": route["id"],
                "circuit_id": route["circuit_id"],
                **_route_flag(route),
            }
            for route in _records(topology, CONF_ROUTES)
            if str(route.get("zone_id")) == object_id
        ]
        return {
            **record,
            CONF_CIRCUIT_IDS: [route["circuit_id"] for route in routes],
            CONF_ROUTES: routes,
        }
    if subentry_type == SUBENTRY_TYPE_CIRCUIT:
        routes = [
            {
                "id": route["id"],
                "zone_id": route["zone_id"],
                **_route_flag(route),
            }
            for route in _records(topology, CONF_ROUTES)
            if str(route.get("circuit_id")) == object_id
        ]
        return {
            **record,
            CONF_ZONE_IDS: [route["zone_id"] for route in routes],
            CONF_ROUTES: routes,
        }
    if subentry_type == SUBENTRY_TYPE_ACTUATOR:
        circuit_ids = [
            circuit["id"]
            for circuit in _records(topology, CONF_CIRCUITS)
            if object_id in [str(value) for value in circuit.get("valve_ids", [])]
        ]
        return {
            **record,
            CONF_ACTUATOR_KIND: ACTUATOR_KIND_VALVE,
            CONF_CIRCUIT_IDS: circuit_ids,
        }
    return record


def subentry_owned_ids(data: Mapping[str, Any], subentry_type: str) -> frozenset[str]:
    """Return ids excluded from dependency selectors for deletion-safe flows."""
    if subentry_type not in _SUPPORTED_SUBENTRY_TYPES:
        raise StoredTopologyError(f"Unsupported subentry type {subentry_type!r}.")
    return frozenset(
        object_id
        for object_id, owned_type in _ownership(data).items()
        if owned_type == subentry_type
    )


def migration_plan(entry: Any) -> MigrationPlan:
    """Build a restart-safe version 2 graph from version 1.1 hybrid storage."""
    data = deepcopy(dict(entry.data))
    topology = _topology_copy(data)
    ownership = _ownership(data)
    updates: list[SubentryMigration] = []
    seen_object_ids: set[str] = set()
    for subentry in sorted(
        getattr(entry, "subentries", {}).values(), key=lambda item: item.subentry_id
    ):
        subentry_type = str(subentry.subentry_type)
        if subentry_type not in _SUPPORTED_SUBENTRY_TYPES:
            raise StoredTopologyError(f"Unsupported config subentry type {subentry_type!r}.")
        if not isinstance(subentry.data, Mapping):
            raise StoredTopologyError("Config subentry data must be an object.")
        object_id = _object_id(subentry.data, f"Subentry {subentry.subentry_id}")
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
            _apply_draft(topology, subentry_type, subentry.data)
        ownership[object_id] = subentry_type
        updates.append(SubentryMigration(subentry=subentry, object_id=object_id))
    data[CONF_TOPOLOGY] = topology
    data[CONF_SUBENTRY_OBJECTS] = ownership
    data.setdefault(CONF_REQUESTED_MODE, PlantMode.AUTO.value)
    data = invalidate_output_authorization(data)
    compile_topology(plant_configuration_from_entry_data(data))
    return MigrationPlan(data=data, subentries=tuple(updates))


def reconcile_removed_subentries(entry: Any) -> Mapping[str, Any] | None:
    """Remove graph objects whose deletion-safe Home Assistant handles vanished."""
    data = deepcopy(dict(entry.data))
    topology = _topology_copy(data)
    ownership = _ownership(data)
    present: dict[str, str] = {}
    for subentry in getattr(entry, "subentries", {}).values():
        subentry_type = str(subentry.subentry_type)
        if subentry_type not in _SUPPORTED_SUBENTRY_TYPES:
            raise StoredTopologyError(f"Unsupported config subentry type {subentry_type!r}.")
        object_id = _subentry_object_id(subentry, require_descriptor=True)
        if object_id in present:
            raise StoredTopologyError(f"Multiple subentries own object {object_id}.")
        if ownership.get(object_id) != subentry_type:
            raise StoredTopologyError(
                f"Subentry {subentry.subentry_id} has no matching parent ownership record."
            )
        present[object_id] = subentry_type
    missing_ids = sorted(set(ownership) - set(present))
    if not missing_ids:
        return None
    for object_id in missing_ids:
        _remove_object(topology, ownership[object_id], object_id)
        ownership.pop(object_id)
    data[CONF_TOPOLOGY] = topology
    data[CONF_SUBENTRY_OBJECTS] = ownership
    data = invalidate_output_authorization(data)
    try:
        compile_topology(plant_configuration_from_entry_data(data))
    except (StoredTopologyError, TopologyValidationError) as error:
        raise StoredTopologyError(
            "Removing the subentry would violate the deletion-safe topology boundary."
        ) from error
    return data


def output_authorization(data: Mapping[str, Any]) -> dict[str, Any]:
    """Bind one explicit authorization to this graph and exact physical outputs."""
    topology = _topology_copy(data)
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
        for record in _records(topology, collection):
            entity_id = record.get("entity_id")
            if isinstance(entity_id, str) and entity_id:
                outputs.append(
                    {
                        "kind": kind,
                        "id": _object_id(record, f"Stored {kind}"),
                        "entity_id": entity_id,
                    }
                )
    for record in _records(topology, CONF_SOURCES):
        entity_id = record.get("source_demand_entity")
        if isinstance(entity_id, str) and entity_id:
            outputs.append(
                {
                    "kind": "source_demand",
                    "id": _object_id(record, "Stored source"),
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


def authorization_output_lines(data: Mapping[str, Any]) -> str:
    """Render exact output bindings for Home Assistant confirmation forms."""
    outputs = output_authorization(data)["outputs"]
    if not outputs:
        return "- No physical outputs are configured"
    return "\n".join(f"- {output['kind']}: {output['entity_id']}" for output in outputs)
