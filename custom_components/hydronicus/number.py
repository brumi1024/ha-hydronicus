"""The setbacks of each scheduled zone, the heating supply settings, and the DHW target."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HydronicusConfigEntry
from .core.model import (
    MAX_CURVE_OFFSET,
    MAX_SETBACK,
    CurveNumber,
    Dhw,
    HeatingSupply,
    Mode,
    SupplyControl,
    Zone,
)
from .entity import (
    HydronicusEntity,
    ZoneEntity,
    async_add_plant_entities,
    plant_unique_id,
    source_device,
)
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


class HeatingCurveOffset(HydronicusEntity, NumberEntity):
    """The owner's parallel shift of the heating curve, which any user may set.

    The runtime persists it with the Plant's state, like the setbacks.
    """

    _attr_translation_key = "heating_curve_offset"
    _attr_device_class = NumberDeviceClass.TEMPERATURE_DELTA
    _attr_native_unit_of_measurement = UnitOfTemperature.KELVIN
    _attr_native_min_value = -MAX_CURVE_OFFSET
    _attr_native_max_value = MAX_CURVE_OFFSET
    _attr_native_step = 0.5
    _attr_mode = NumberMode.SLIDER

    def __init__(self, runtime: PlantRuntime) -> None:
        super().__init__(
            runtime,
            plant_unique_id(runtime.plant.id, "heating_curve_offset"),
            source_device(runtime),
        )

    @property
    def available(self) -> bool:
        # It shifts Hydronicus's curve, so it applies only while heating uses it.
        result = self.runtime.heating_supply
        return result is None or result.strategy is HeatingSupply.CURVE

    @property
    def native_value(self) -> float | None:
        return self.runtime.heating_curve_offset()

    async def async_set_native_value(self, value: float) -> None:
        self.runtime.set_curve_offset(value)


class HeatingSupplyTemperature(HydronicusEntity, NumberEntity):
    """The fixed heating supply temperature, available while heating uses it.

    A change made elsewhere to the supply number while heating uses a fixed
    temperature or Hydronicus's curve shows here as the new value.
    """

    _attr_translation_key = "heating_supply_temperature"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(self, runtime: PlantRuntime, supply: SupplyControl) -> None:
        super().__init__(
            runtime,
            plant_unique_id(runtime.plant.id, "heating_supply_temperature"),
            source_device(runtime),
        )
        self._attr_native_min_value = supply.minimum
        self._attr_native_max_value = supply.maximum
        self._attr_native_step = supply.step or 0.5

    @property
    def available(self) -> bool:
        result = self.runtime.heating_supply
        return result is not None and result.strategy is HeatingSupply.FIXED

    @property
    def native_value(self) -> float | None:
        result = self.runtime.heating_supply
        return None if result is None else result.fixed

    async def async_set_native_value(self, value: float) -> None:
        self.runtime.command_supply(fixed=value)


class WeatherCurveNumber(HydronicusEntity, NumberEntity):
    """The source's own weather curve number that Hydronicus owns.

    A change made on the source's own controller is adopted and shows here.
    """

    _attr_translation_key = "weather_curve_number"
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1.0

    def __init__(self, runtime: PlantRuntime, number: CurveNumber) -> None:
        super().__init__(
            runtime,
            plant_unique_id(runtime.plant.id, "weather_curve_number"),
            source_device(runtime),
        )
        self._attr_native_min_value = number.minimum
        self._attr_native_max_value = number.maximum

    @property
    def available(self) -> bool:
        result = self.runtime.heating_supply
        return result is not None and result.state.curve_number is not None

    @property
    def native_value(self) -> float | None:
        result = self.runtime.heating_supply
        return None if result is None else result.state.curve_number

    async def async_set_native_value(self, value: float) -> None:
        self.runtime.command_supply(curve_number=value)


class DhwTarget(HydronicusEntity, NumberEntity):
    """The owned DHW target within its hard limits; a boost shows in its attributes."""

    _attr_translation_key = "dhw_target"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(self, runtime: PlantRuntime, dhw: Dhw) -> None:
        super().__init__(
            runtime, plant_unique_id(runtime.plant.id, "dhw_target"), source_device(runtime)
        )
        self._attr_native_min_value = dhw.minimum
        self._attr_native_max_value = dhw.maximum
        self._attr_native_step = dhw.step or 0.5

    @property
    def available(self) -> bool:
        dhw = self.runtime.dhw
        return dhw is not None and dhw.target is not None

    @property
    def native_value(self) -> float | None:
        dhw = self.runtime.dhw
        return None if dhw is None else dhw.target

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dhw = self.runtime.dhw
        boosted = dhw is not None and dhw.boost_until is not None
        return {
            "boost": dhw.boost if boosted and dhw is not None else None,
            "boost_until": dt_util.utc_from_timestamp(dhw.boost_until).isoformat()
            if boosted and dhw is not None and dhw.boost_until is not None
            else None,
        }

    async def async_set_native_value(self, value: float) -> None:
        self.runtime.command_dhw(target=value)


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
    source = runtime.plant.source
    if runtime.heating_curve_offset() is not None:
        entities.append((None, HeatingCurveOffset(runtime)))
    if source is not None and source.supply is not None:
        entities.append((None, HeatingSupplyTemperature(runtime, source.supply)))
    if source is not None and source.curve_number is not None:
        entities.append((None, WeatherCurveNumber(runtime, source.curve_number)))
    if source is not None and source.dhw is not None and source.dhw.setpoint is not None:
        entities.append((None, DhwTarget(runtime, source.dhw)))
    async_add_plant_entities(runtime, "number", async_add_entities, entities)
