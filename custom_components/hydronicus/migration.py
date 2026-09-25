"""Migrate stored Hydronicus config entries to the current storage version."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .const import CONF_REQUESTED_MODE, CONF_SUBENTRY_OBJECTS, CONF_TOPOLOGY
from .core.configuration import StoredTopologyError, plant_configuration_from_entry_data
from .core.model import PlantMode
from .core.topology import compile_topology
from .entry_configuration import (
    SUPPORTED_SUBENTRY_TYPES,
    apply_draft,
    invalidate_output_authorization,
    object_exists,
    record_object_id,
    subentry_objects,
    topology_copy,
)


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


def migration_plan(entry: Any) -> MigrationPlan:
    """Build a restart-safe version 2 graph from version 1.1 hybrid storage."""
    data = deepcopy(dict(entry.data))
    topology = topology_copy(data)
    ownership = subentry_objects(data)
    updates: list[SubentryMigration] = []
    seen_object_ids: set[str] = set()
    for subentry in sorted(
        getattr(entry, "subentries", {}).values(), key=lambda item: item.subentry_id
    ):
        subentry_type = str(subentry.subentry_type)
        if subentry_type not in SUPPORTED_SUBENTRY_TYPES:
            raise StoredTopologyError(f"Unsupported config subentry type {subentry_type!r}.")
        if not isinstance(subentry.data, Mapping):
            raise StoredTopologyError("Config subentry data must be an object.")
        object_id = record_object_id(subentry.data, f"Subentry {subentry.subentry_id}")
        if object_id in seen_object_ids:
            raise StoredTopologyError(f"Multiple subentries own object {object_id}.")
        seen_object_ids.add(object_id)
        if set(subentry.data) == {"id"}:
            if not object_exists(topology, subentry_type, object_id):
                raise StoredTopologyError(
                    f"Migrated subentry {subentry.subentry_id} references missing "
                    f"object {object_id}."
                )
        else:
            apply_draft(topology, subentry_type, subentry.data)
        ownership[object_id] = subentry_type
        updates.append(SubentryMigration(subentry=subentry, object_id=object_id))
    data[CONF_TOPOLOGY] = topology
    data[CONF_SUBENTRY_OBJECTS] = ownership
    data.setdefault(CONF_REQUESTED_MODE, PlantMode.AUTO.value)
    data = invalidate_output_authorization(data)
    compile_topology(plant_configuration_from_entry_data(data))
    return MigrationPlan(data=data, subentries=tuple(updates))
