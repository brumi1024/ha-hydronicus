"""Entity provision and stale registry cleanup for one Plant setup.

Which entities a Plant provides depends on its graph: cooling entities exist
only for rooms that can cool, and source entities only when the Plant has a
source. Every platform adds its entities through ``async_add_plant_entities``,
which records the unique IDs it provided, so setup can then remove the
registry entries of this Plant that no platform provides any more.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .runtime import HydronicRuntime


@callback
def async_add_plant_entities(
    runtime: HydronicRuntime,
    domain: str,
    async_add_entities: AddConfigEntryEntitiesCallback,
    parent_entities: Sequence[Entity],
    subentry_entities: Mapping[str, Sequence[Entity]] | None = None,
) -> None:
    """Add a platform's complete entity set and record it as provided.

    ``subentry_entities`` maps a config subentry id to the entities it owns;
    all other entities belong to the parent Plant entry. Each platform calls
    this exactly once, and disabled entities count as provided, because their
    registry entries hold the user's choice to disable them.
    """
    subentry_entities = subentry_entities or {}
    entities = [*parent_entities, *(e for group in subentry_entities.values() for e in group)]
    runtime.provided_entities[domain] = frozenset(
        cast(str, entity.unique_id) for entity in entities
    )
    async_add_entities(parent_entities)
    for subentry_id, owned in subentry_entities.items():
        async_add_entities(owned, config_subentry_id=subentry_id)


@callback
def async_remove_unprovided_entities(
    hass: HomeAssistant, entry: ConfigEntry, runtime: HydronicRuntime
) -> None:
    """Remove this Plant's registry entries that no platform provides any more.

    Only platforms that recorded their entity set in this setup are cleaned, so
    a platform that failed to set up keeps its registry entries. Entries owned by
    config subentries belong to this entry too and are judged the same way.
    """
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.platform != DOMAIN:
            continue
        provided = runtime.provided_entities.get(registry_entry.domain)
        if provided is not None and registry_entry.unique_id not in provided:
            registry.async_remove(registry_entry.entity_id)
