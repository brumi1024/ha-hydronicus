"""The setbacks of each scheduled zone, which a dashboard changes like a target."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HydronicusConfigEntry
from .core.model import MAX_SETBACK, Mode, Zone
from .entity import ZoneEntity, async_add_plant_entities
from .runtime import PlantRuntime

# The runtime evaluates setback changes itself.
PARALLEL_UPDATES = 0


class ZoneSetback(ZoneEntity, NumberEntity):
    """How far a scheduled zone's target moves outside its comfort periods, in one mode.

    The runtime persists the value with the Plant's state, so it needs no restore
    of its own and the first evaluation after a restart already uses it.
    """

    _attr_device_class = NumberDeviceClass.TEMPERATURE_DELTA
    _attr_native_unit_of_measurement = UnitOfTemperature.KELVIN
    _attr_native_min_value = 0.0
    _attr_native_max_value = MAX_SETBACK
    _attr_native_step = 0.5
    _attr_mode = NumberMode.SLIDER

    def __init__(self, runtime: PlantRuntime, zone: Zone, mode: Mode) -> None:
        key = f"{mode.value}_setback"
        super().__init__(runtime, zone, key)
        self._attr_translation_key = key
        self._mode = mode

    @property
    def native_value(self) -> float | None:
        setbacks = self.runtime.zone_setbacks(self._zone)
        if setbacks is None:
            return None
        return setbacks.heat if self._mode is Mode.HEAT else setbacks.cool

    async def async_set_native_value(self, value: float) -> None:
        self.runtime.set_setback(self._zone, self._mode, value)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    entities: list[tuple[str | None, Entity]] = []
    for zone in runtime.plant.zones:
        if zone.slug not in runtime.scheduled_zones():
            continue
        modes = runtime.plant.zone_modes(zone.slug)
        entities.extend(
            (zone.slug, ZoneSetback(runtime, zone, mode))
            for mode in (Mode.HEAT, Mode.COOL)
            if mode in modes
        )
    async_add_plant_entities(runtime, "number", async_add_entities, entities)
