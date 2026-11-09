"""The Plant mode select, and the source's heating supply select."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HydronicusConfigEntry
from .core.model import HeatingSupply, Mode
from .entity import (
    HydronicusEntity,
    async_add_plant_entities,
    plant_device,
    plant_unique_id,
    source_device,
)
from .runtime import PlantRuntime

PARALLEL_UPDATES = 0
# The option that lets the Plant's changeover choose heat or cool.
AUTO = "auto"


class PlantModeSelect(HydronicusEntity, SelectEntity):
    """The mode the Plant runs in; cool is offered only when a loop cools."""

    _attr_translation_key = "mode"

    def __init__(self, entry: HydronicusConfigEntry) -> None:
        runtime = entry.runtime_data
        super().__init__(
            runtime, plant_unique_id(runtime.plant.id, "mode"), plant_device(runtime.plant)
        )
        # Cool stays offered while it is chosen, as when the configuration is not valid.
        cools = runtime.requested_mode is Mode.COOL or any(
            loop.cools for loop in runtime.plant.all_loops
        )
        self._attr_options = [
            mode.value
            for mode in (Mode.OFF, Mode.HEAT, Mode.COOL)
            if cools or mode is not Mode.COOL
        ]
        if runtime.plant.changeover is not None:
            self._attr_options.append(AUTO)

    @property
    def current_option(self) -> str:
        if self.runtime.auto_mode:
            return AUTO
        return self.runtime.requested_mode.value

    async def async_select_option(self, option: str) -> None:
        self.runtime.set_mode(None if option == AUTO else Mode(option))


class HeatingSupplySelect(HydronicusEntity, SelectEntity):
    """Who owns the heating supply temperature, among the strategies the source offers.

    A change made elsewhere, such as the weather curve switched on the source's
    own controller, shows here as the new choice. The runtime persists the
    choice with the Plant's state.
    """

    _attr_translation_key = "heating_supply"

    def __init__(self, runtime: PlantRuntime, supplies: tuple[HeatingSupply, ...]) -> None:
        super().__init__(
            runtime, plant_unique_id(runtime.plant.id, "heating_supply"), source_device(runtime)
        )
        self._attr_options = [supply.value for supply in supplies]

    @property
    def available(self) -> bool:
        return self.runtime.heating_supply is not None

    @property
    def current_option(self) -> str | None:
        result = self.runtime.heating_supply
        return None if result is None else result.strategy.value

    async def async_select_option(self, option: str) -> None:
        self.runtime.command_supply(strategy=HeatingSupply(option))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    entities: list[tuple[str | None, SelectEntity]] = [(None, PlantModeSelect(entry))]
    source = runtime.plant.source
    if source is not None and len(source.heating_supplies) > 1:
        entities.append((None, HeatingSupplySelect(runtime, source.heating_supplies)))
    async_add_plant_entities(runtime, "select", async_add_entities, entities)
