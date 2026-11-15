"""Resets of what Hydronicus learned: a zone's recovery times and the room trim."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HydronicusConfigEntry
from .core.model import DigitalThermostat, LearningMode, Zone
from .entity import (
    HydronicusEntity,
    ZoneEntity,
    async_add_plant_entities,
    plant_unique_id,
    room_trim_offered,
    source_device,
)
from .runtime import PlantRuntime

PARALLEL_UPDATES = 0


class ResetLearningButton(ZoneEntity, ButtonEntity):
    """Discard only this zone's recorded recovery evidence."""

    _attr_translation_key = "reset_learning"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, runtime: PlantRuntime, zone: Zone) -> None:
        super().__init__(runtime, zone, "reset_learning")

    async def async_press(self) -> None:
        self.runtime.reset_learning(self._zone)


class ResetRoomTrimButton(HydronicusEntity, ButtonEntity):
    """Forget the room trim's learned part, so it starts again from the curve."""

    _attr_translation_key = "reset_room_trim"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, runtime: PlantRuntime) -> None:
        super().__init__(
            runtime, plant_unique_id(runtime.plant.id, "reset_room_trim"), source_device(runtime)
        )

    async def async_press(self) -> None:
        self.runtime.reset_room_trim()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    entities: list[tuple[str | None, ButtonEntity]] = [
        (zone.slug, ResetLearningButton(runtime, zone))
        for zone in runtime.plant.zones
        if isinstance(zone.thermostat, DigitalThermostat)
        and zone.thermostat.learning is not LearningMode.OFF
    ]
    if room_trim_offered(runtime, learning=True):
        entities.append((None, ResetRoomTrimButton(runtime)))
    async_add_plant_entities(runtime, "button", async_add_entities, entities)
