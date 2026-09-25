"""Move and remove the entity and device registrations of Plant graph objects.

A graph edit can give an object another owner, such as a loop that a plant
file edit makes private to a zone, or drop an object altogether. The edit calls
these helpers in the same synchronous block that stores the edited graph.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CONF_PLANT_ID, DOMAIN

_UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_PLANT: Final = "plant"


def _object_of_unique_id(unique_id: str, plant_id: str, owners: Mapping[str, object]) -> str | None:
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
