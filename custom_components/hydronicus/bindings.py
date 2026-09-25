"""The entities a Plant binds, checked against Home Assistant and other Plants.

A Plant never binds an entity Hydronicus provides, which would feed the Plant
back into itself, and an output entity belongs to one Plant (decision 18).
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .core.model import Plant
from .core.plant_file import PlantFileError, entity_paths
from .storage import plant_from_entry


def is_hydronicus_owned(hass: HomeAssistant, entity_id: str) -> bool:
    """Return whether an entity is provided by this integration."""
    registry_entry = er.async_get(hass).async_get(entity_id)
    return registry_entry is not None and registry_entry.platform == DOMAIN


def own_entity(hass: HomeAssistant, plant: Plant) -> tuple[str, str] | None:
    """Return the plant file path and entity ID of the first Hydronicus entity a Plant binds."""
    for entity_id, path in entity_paths(plant).items():
        if is_hydronicus_owned(hass, entity_id):
            return path, entity_id
    return None


@dataclass(frozen=True, slots=True)
class BoundElsewhere:
    """An output entity that another Plant already binds."""

    entity_id: str
    path: str
    other_plant: str


def output_bound_elsewhere(
    hass: HomeAssistant, plant: Plant, entry_id: str | None = None
) -> BoundElsewhere | None:
    """Return the first output of ``plant`` that another Plant's config entry binds."""
    paths = entity_paths(plant)
    outputs = plant.outputs()
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == entry_id:
            continue
        try:
            other = plant_from_entry(entry)
        except PlantFileError:
            continue
        shared = [entity for entity in outputs if entity in other.outputs()]
        if shared:
            return BoundElsewhere(shared[0], paths[shared[0]], entry.title)
    return None
