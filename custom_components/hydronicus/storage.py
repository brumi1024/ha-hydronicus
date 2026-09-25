"""The Plant as a config entry stores it: the entry data plus one subentry per zone.

The config entry's data is the plant file without ``zones``, and each ``zone``
subentry holds one zone's mapping plus its slug, which is also the subentry's
unique ID (contract K1). ``core.plant_file`` owns the schema; this module only
moves it in and out of Home Assistant's config entry objects.

Home Assistant cannot veto the removal of a subentry, so Plant-level references
to a removed zone, in a pump's ``min_flow_loops`` and a plant loop's
``with_zones``, are pruned from the entry data before the Plant is read again.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigSubentry,
    ConfigSubentryData,
)
from homeassistant.core import HomeAssistant, callback

from .const import OPTION_ARMED_OUTPUTS, OPTION_CONTROL, SUBENTRY_TYPE_ZONE
from .core.model import LoopRef, Plant
from .core.plant_file import from_storage, to_storage

_SLUG = "slug"


def zone_data(entry: ConfigEntry) -> dict[str, Mapping[str, Any]]:
    """Return each zone subentry's data by zone slug."""
    zones: dict[str, Mapping[str, Any]] = {}
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_ZONE:
            continue
        slug = subentry.unique_id or subentry.data.get(_SLUG)
        if isinstance(slug, str):
            zones[slug] = subentry.data
    return zones


def zone_subentry_ids(entry: ConfigEntry) -> dict[str, str]:
    """Return each zone subentry's ID by zone slug."""
    return {
        slug: subentry.subentry_id
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_ZONE
        and isinstance(slug := subentry.unique_id or subentry.data.get(_SLUG), str)
    }


def stored_document(entry: ConfigEntry) -> dict[str, Any]:
    """Return the plant file a config entry stores, valid or not, as plain data to edit."""
    document = deepcopy(dict(entry.data))
    zones = {
        slug: {key: deepcopy(value) for key, value in data.items() if key != _SLUG}
        for slug, data in zone_data(entry).items()
    }
    if zones:
        document["zones"] = zones
    return document


def plant_from_entry(entry: ConfigEntry) -> Plant:
    """Return the validated Plant a config entry stores; raise ``PlantFileError`` otherwise."""
    return from_storage(entry.data, zone_data(entry))


def new_entry(plant: Plant) -> tuple[dict[str, Any], list[ConfigSubentryData]]:
    """Return the entry data and zone subentries that store a new Plant."""
    data, zones = to_storage(plant)
    subentries: list[ConfigSubentryData] = [
        ConfigSubentryData(
            data=zone,
            subentry_type=SUBENTRY_TYPE_ZONE,
            title=plant.zone(slug).title,
            unique_id=slug,
        )
        for slug, zone in zones.items()
    ]
    return data, subentries


@callback
def async_store_plant(hass: HomeAssistant, entry: ConfigEntry, plant: Plant) -> None:
    """Store a Plant over an entry: its zone subentries by slug, and its data.

    New and changed zones are stored first, then the data, then removed zones
    go, so every state in between keeps the references it holds and the update
    listener never prunes one. The listener reloads a loaded Plant once.
    """
    data, zones = to_storage(plant)
    subentries = {
        subentry.unique_id: subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_ZONE
    }
    for slug, zone in zones.items():
        title = plant.zone(slug).title
        if (subentry := subentries.get(slug)) is None:
            hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data=MappingProxyType(zone),
                    subentry_type=SUBENTRY_TYPE_ZONE,
                    title=title,
                    unique_id=slug,
                ),
            )
        else:
            hass.config_entries.async_update_subentry(entry, subentry, data=zone, title=title)
    hass.config_entries.async_update_entry(entry, data=data, title=plant.name)
    for slug, subentry in subentries.items():
        if slug not in zones:
            hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)
    async_reload_if_failed(hass, entry)


@callback
def async_reload_if_failed(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up again a Plant that failed to set up, after its configuration changed.

    A loaded Plant reloads from its update listener; one that failed has none.
    """
    if entry.state in (ConfigEntryState.SETUP_ERROR, ConfigEntryState.SETUP_RETRY):
        hass.config_entries.async_schedule_reload(entry.entry_id)


def new_options() -> dict[str, Any]:
    """Return the options of a new Plant: nothing armed and control off (contract K6)."""
    return {OPTION_ARMED_OUTPUTS: [], OPTION_CONTROL: False}


def armed_outputs(entry: ConfigEntry) -> frozenset[str]:
    """Return the output entities the owner has confirmed."""
    armed = entry.options.get(OPTION_ARMED_OUTPUTS, ())
    return frozenset(entity for entity in armed if isinstance(entity, str))


def control(entry: ConfigEntry) -> bool:
    """Return the Control equipment setting."""
    return entry.options.get(OPTION_CONTROL) is True


def pruned_options(entry: ConfigEntry, plant: Plant) -> dict[str, Any] | None:
    """Return options without armed outputs the Plant no longer has, or None if unchanged.

    Removing an output disarms it silently, so the same entity bound again later
    is a new output that needs a new confirmation.
    """
    armed = list(entry.options.get(OPTION_ARMED_OUTPUTS, ()))
    kept = [entity for entity in armed if entity in plant.outputs()]
    if kept == armed and OPTION_CONTROL in entry.options:
        return None
    return {**entry.options, OPTION_ARMED_OUTPUTS: kept, OPTION_CONTROL: control(entry)}


def pruned_entry_data(entry: ConfigEntry) -> dict[str, Any] | None:
    """Return entry data without references to zones that have no subentry, or None.

    A removed zone leaves its slug in plant loops' ``with_zones`` and its loops
    in source-driven pumps' ``min_flow_loops``. Pruning them may still leave an
    invalid Plant, such as a pump with no min-flow loop left, which reading the
    Plant then reports.
    """
    zones = set(zone_data(entry))
    data = deepcopy(dict(entry.data))
    changed = False
    pumps = data.get("pumps")
    if isinstance(pumps, dict):
        for pump in pumps.values():
            refs = pump.get("min_flow_loops") if isinstance(pump, dict) else None
            if not isinstance(refs, list):
                continue
            kept = [ref for ref in refs if _zone_of(ref) is None or _zone_of(ref) in zones]
            if kept != refs:
                pump["min_flow_loops"] = kept
                changed = True
    loops = data.get("loops")
    if isinstance(loops, dict):
        for loop in loops.values():
            runs = loop.get("runs") if isinstance(loop, dict) else None
            if not isinstance(runs, dict) or not isinstance(
                members := runs.get("with_zones"), list
            ):
                continue
            kept = [slug for slug in members if slug in zones]
            if kept != members:
                runs["with_zones"] = kept
                changed = True
    return data if changed else None


def _zone_of(ref: object) -> str | None:
    """Return the zone of a stored loop reference, or None for a plant loop or bad data."""
    if not isinstance(ref, str):
        return None
    try:
        return LoopRef.parse(ref).zone
    except ValueError:
        return None
