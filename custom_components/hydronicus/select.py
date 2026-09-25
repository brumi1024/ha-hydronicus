"""The Plant mode select: off, heat, or cool (decision 7)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HydronicusConfigEntry
from .core.model import Mode
from .entity import HydronicusEntity, async_add_plant_entities, plant_device, plant_unique_id

PARALLEL_UPDATES = 0


class PlantModeSelect(HydronicusEntity, SelectEntity):
    """The mode the Plant runs in; cool is offered only when a loop cools."""

    _attr_translation_key = "mode"

    def __init__(self, entry: HydronicusConfigEntry) -> None:
        runtime = entry.runtime_data
        super().__init__(
            runtime, plant_unique_id(runtime.plant.id, "mode"), plant_device(runtime.plant)
        )
        cools = any(loop.cools for loop in runtime.plant.all_loops)
        self._attr_options = [
            mode.value
            for mode in (Mode.OFF, Mode.HEAT, Mode.COOL)
            if cools or mode is not Mode.COOL
        ]

    @property
    def current_option(self) -> str:
        return self.runtime.requested_mode.value

    async def async_select_option(self, option: str) -> None:
        self.runtime.set_mode(Mode(option))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_plant_entities(
        entry.runtime_data, "select", async_add_entities, [(None, PlantModeSelect(entry))]
    )
