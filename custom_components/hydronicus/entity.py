"""The entity contract's shared parts: unique IDs, devices, and publication (contract K7).

Unique IDs derive from the Plant ID and object slugs (decision 1), so a Plant
rebuilt from its plant file gets the same unique IDs, and Home Assistant gives
it the same entity IDs. Zone entities belong to their zone's subentry and its
device, and Plant, plant loop, and source entities to the Plant entry.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .core.model import LoopRef, Plant, Zone
from .storage import zone_subentry_ids

if TYPE_CHECKING:
    from .runtime import PlantRuntime

_MANUFACTURER = "Hydronicus"


def plant_unique_id(plant_id: str, suffix: str) -> str:
    return f"{plant_id}_{suffix}"


def zone_unique_id(plant_id: str, zone: str, suffix: str) -> str:
    return f"{plant_id}_zone_{zone}_{suffix}"


def loop_unique_id(plant_id: str, ref: LoopRef, suffix: str) -> str:
    # A loop reference is ``zone.loop`` or a plant loop's slug; slugs have no dot.
    return f"{plant_id}_loop_{ref}_{suffix}"


def plant_device(plant: Plant) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, plant.id)},
        name=plant.name,
        manufacturer=_MANUFACTURER,
        model="Hydronicus Plant",
    )


def zone_device(runtime: PlantRuntime, zone: Zone) -> DeviceInfo:
    """The device of a zone, named after the zone alone, under the Plant device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{runtime.plant.id}:zone:{zone.slug}")},
        name=zone.title,
        manufacturer=_MANUFACTURER,
        model="Hydronicus Zone",
        via_device_id=runtime.plant_device_id,
    )


def source_device(runtime: PlantRuntime) -> DeviceInfo:
    plant = runtime.plant
    assert plant.source is not None
    return DeviceInfo(
        identifiers={(DOMAIN, f"{plant.id}:source")},
        name=plant.source.title,
        manufacturer=_MANUFACTURER,
        model="Hydronicus Source",
        via_device_id=runtime.plant_device_id,
    )


class HydronicusEntity(Entity):
    """An entity that publishes what the Plant's runtime last evaluated."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime: PlantRuntime, unique_id: str, device: DeviceInfo) -> None:
        self.runtime = runtime
        self._attr_unique_id = unique_id
        self._attr_device_info = device
        self._published: tuple[Any, ...] | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.runtime.async_add_listener(self._handle_runtime_update))

    @callback
    def _handle_runtime_update(self) -> None:
        """Write the state only when it changed."""
        snapshot = (
            self.available,
            self.state,
            self.state_attributes,
            self.extra_state_attributes,
        )
        if snapshot != self._published:
            self._published = snapshot
            self.async_write_ha_state()


@callback
def async_add_plant_entities(
    runtime: PlantRuntime,
    domain: str,
    async_add_entities: AddConfigEntryEntitiesCallback,
    entities: Iterable[tuple[str | None, Entity]],
) -> None:
    """Add a platform's entities, each zone's to its subentry, and record them as provided.

    ``entities`` pairs each entity with its zone's slug, or None for the Plant.
    """
    subentries = zone_subentry_ids(runtime.entry)
    plant_entities: list[Entity] = []
    zone_entities: dict[str, list[Entity]] = {}
    provided: set[str] = set()
    for zone, entity in entities:
        assert entity.unique_id is not None
        provided.add(entity.unique_id)
        if zone is None or zone not in subentries:
            plant_entities.append(entity)
        else:
            zone_entities.setdefault(subentries[zone], []).append(entity)
    runtime.provided[domain] = frozenset(provided)
    async_add_entities(plant_entities)
    for subentry_id, owned in zone_entities.items():
        async_add_entities(owned, config_subentry_id=subentry_id)


@callback
def async_remove_unprovided_entities(
    hass: HomeAssistant, entry: ConfigEntry, runtime: PlantRuntime
) -> None:
    """Remove this Plant's registry entries that no platform provides any more.

    Which entities exist depends on the Plant: cooling entities only for zones
    that cool, and the source entity only with a source. Only platforms that
    recorded their entities in this setup are cleaned.
    """
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.platform != DOMAIN:
            continue
        provided = runtime.provided.get(registry_entry.domain)
        if provided is not None and registry_entry.unique_id not in provided:
            registry.async_remove(registry_entry.entity_id)
