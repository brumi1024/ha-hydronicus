"""Hydronicus: control a hydronic Plant from its persisted state.

A Plant is one config entry of version 5: the Plant in the entry data, each zone
in a ``zone`` subentry, and the arming in the options. A change to the data or
the subentries reloads the Plant, which never sends a command; a change to the
options only evaluates it again.
"""

from __future__ import annotations

import json
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    PLATFORMS,
    STORE_VERSION,
)
from .core.model import Plant
from .core.plant_file import PlantFileError, describe_path
from .entity import async_remove_unprovided_entities
from .issues import async_delete_issues, async_sync_issues, invalid_plant
from .runtime import PlantRuntime, store_key
from .services import async_setup_services
from .storage import plant_from_entry, pruned_entry_data, pruned_options, stored_document
from .zone_area import async_place_new_zone_climates, zones_without_climate

type HydronicusConfigEntry = ConfigEntry[PlantRuntime]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the Hydronicus actions."""
    async_setup_services(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Refuse a config entry of another storage version, which is never migrated.

    Home Assistant calls this only when the stored version differs from the
    current one. An older entry comes from an earlier version, whose Plant has to
    be set up again; a newer one comes from a later release.
    """
    if entry.version < CONFIG_ENTRY_VERSION:
        _LOGGER.error(
            "Hydronicus Plant %s was created by an earlier version (config entry version "
            "%s.%s) and cannot be migrated; remove it and set the Plant up again, for "
            "example by importing a plant file",
            entry.title,
            entry.version,
            entry.minor_version,
        )
    return (
        entry.version == CONFIG_ENTRY_VERSION and entry.minor_version == CONFIG_ENTRY_MINOR_VERSION
    )


def configuration_fingerprint(entry: ConfigEntry) -> str:
    """Return what a Plant is built from: its data and its zone subentries."""
    return json.dumps(
        {
            "data": dict(entry.data),
            "subentries": {
                subentry.subentry_id: [
                    subentry.subentry_type,
                    subentry.unique_id,
                    dict(subentry.data),
                ]
                for subentry in entry.subentries.values()
            },
        },
        sort_keys=True,
        default=str,
    )


async def async_setup_entry(hass: HomeAssistant, entry: HydronicusConfigEntry) -> bool:
    """Set up a Plant: read it, restore its state, add its entities, and start it."""
    if (pruned := pruned_entry_data(entry)) is not None:
        hass.config_entries.async_update_entry(entry, data=pruned)
    # What the Plant is read from, taken before anything awaits.
    fingerprint = configuration_fingerprint(entry)
    problem: str | None = None
    try:
        plant = plant_from_entry(entry)
    except PlantFileError as error:
        # The Plant loads without its objects: the runtime stops what the last valid
        # configuration commanded, then only observes until a reconfigure fixes it.
        problem = f"{describe_path(stored_document(entry), error.path)}: {error.message}"
        _LOGGER.warning(
            "Hydronicus Plant %s is not valid, so it stops what it commanded and then only "
            "observes until its configuration is fixed: %s",
            entry.title,
            problem,
        )
        async_sync_issues(hass, entry.entry_id, [invalid_plant(entry.title, problem)])
        plant = invalid_placeholder(entry)
    else:
        # The arming of an invalid Plant is kept for when it is fixed.
        if (options := pruned_options(entry, plant)) is not None:
            hass.config_entries.async_update_entry(entry, options=options)

    runtime = PlantRuntime(hass, entry, plant, problem)
    await runtime.async_load()
    entry.runtime_data = runtime
    runtime.plant_device_id = (
        dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, plant.id)},
            name=plant.name,
            manufacturer="Hydronicus",
            model="Hydronicus Plant",
        )
        .id
    )
    new_climates = zones_without_climate(hass, plant)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        if problem is None:
            # An invalid Plant provides only the Plant's own entities and keeps the rest.
            async_place_new_zone_climates(hass, plant, new_climates)
            async_remove_unprovided_entities(hass, entry, runtime)
    except Exception:
        await runtime.async_stop()
        raise
    runtime.fingerprint = fingerprint
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    runtime.async_start()
    return True


def invalid_placeholder(entry: ConfigEntry) -> Plant:
    """Return the empty Plant an invalid configuration shows: its stored ID and name only."""
    plant_id = entry.unique_id or entry.data.get("id")
    return Plant(id=plant_id if isinstance(plant_id, str) else entry.entry_id, name=entry.title)


async def _async_update_listener(hass: HomeAssistant, entry: HydronicusConfigEntry) -> None:
    """Prune references to removed zones, reload on a new configuration, else evaluate."""
    if (pruned := pruned_entry_data(entry)) is not None:
        # The update calls this listener again with the pruned data.
        hass.config_entries.async_update_entry(entry, data=pruned)
        return
    runtime: PlantRuntime | None = getattr(entry, "runtime_data", None)
    if runtime is not None:
        if runtime.fingerprint == configuration_fingerprint(entry):
            # Only the options changed: arming or Control equipment.
            runtime.request_evaluation()
            return
        if runtime.reloading:
            # A flow that changes the data and several subentries at once calls this
            # for each change; the one reload reads them all.
            return
        runtime.reloading = True
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HydronicusConfigEntry) -> bool:
    """Unload a Plant without sending a command; the equipment stays as it is."""
    runtime = entry.runtime_data
    await runtime.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the Plant's Repairs and persisted state."""
    async_delete_issues(hass, entry.entry_id)
    await Store[dict[str, object]](hass, STORE_VERSION, store_key(entry.entry_id)).async_remove()
