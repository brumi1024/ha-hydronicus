"""The digital thermostat of a zone (decision 9).

It owns the zone's target, preset, and mode, restores them across restarts, and
reports the zone's demand as its action. The exact Celsius target is persisted
beside the restored state, because the display unit may round it.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any, Final

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoredExtraData, RestoreEntity
from homeassistant.util.unit_conversion import TemperatureConverter

from . import HydronicusConfigEntry
from .const import DOMAIN
from .core.model import DigitalThermostat, Mode, Preset, Zone
from .core.step import DigitalThermostatState
from .entity import HydronicusEntity, async_add_plant_entities, zone_device, zone_unique_id
from .runtime import PlantRuntime, ZoneReadings

# The runtime evaluates thermostat changes itself.
PARALLEL_UPDATES = 0

MIN_TARGET: Final = 5.0
MAX_TARGET: Final = 35.0
_LAST_ACTIVE_HVAC_MODE: Final = "last_active_hvac_mode"
_TARGET_TEMPERATURE_CELSIUS: Final = "target_temperature_celsius"
_BASE_FEATURES: Final = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)


class ZoneClimate(HydronicusEntity, ClimateEntity, RestoreEntity):
    """A Hydronicus-owned digital thermostat for one zone."""

    # No name: the thermostat is the zone device's main feature and takes its name.
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_TARGET
    _attr_max_temp = MAX_TARGET
    _attr_target_temperature_step = 0.5

    def __init__(self, runtime: PlantRuntime, zone: Zone, config: DigitalThermostat) -> None:
        super().__init__(
            runtime,
            zone_unique_id(runtime.plant.id, zone.slug, "climate"),
            zone_device(runtime, zone),
        )
        self._zone = zone.slug
        self._config = config
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        if zone.cools:
            self._attr_hvac_modes.append(HVACMode.COOL)
        self._attr_preset_modes = [preset.value for preset, _ in config.presets]
        self._attr_supported_features = _BASE_FEATURES
        if self._attr_preset_modes:
            self._attr_preset_modes.append(PRESET_NONE)
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
        self._has_humidity = bool(zone.humidity or zone.areas)
        self._thermostat = DigitalThermostatState(Mode.OFF, config.target)
        # The mode turn_on restores, kept beside the zone mode in the restore state.
        self._last_active = HVACMode.HEAT

    async def async_added_to_hass(self) -> None:
        """Restore the target, preset, and mode, then hand them to the runtime."""
        await super().async_added_to_hass()
        extra: dict[str, Any] = {}
        if (extra_data := await self.async_get_last_extra_data()) is not None:
            extra = extra_data.as_dict()
            self._remember_active(extra.get(_LAST_ACTIVE_HVAC_MODE))
        last_state = await self.async_get_last_state()
        if last_state is not None:
            target = _usable_target(extra.get(_TARGET_TEMPERATURE_CELSIUS))
            if target is None:
                with suppress(KeyError, TypeError, ValueError):
                    target = _usable_target(
                        TemperatureConverter.convert(
                            float(last_state.attributes[ATTR_TEMPERATURE]),
                            self.hass.config.units.temperature_unit,
                            UnitOfTemperature.CELSIUS,
                        )
                    )
            preset = str(last_state.attributes.get("preset_mode", PRESET_NONE)).lower()
            mode = Mode.OFF
            with suppress(ValueError):
                if HVACMode(last_state.state) in self.hvac_modes:
                    mode = Mode(last_state.state)
            self._thermostat = DigitalThermostatState(
                mode,
                self._config.target if target is None else target,
                Preset(preset)
                if preset in (self._attr_preset_modes or ()) and preset != PRESET_NONE
                else None,
            )
            self._remember_active(mode.value)
        self.runtime.restore_thermostat(self._zone, self._thermostat)

    def _remember_active(self, value: object) -> None:
        with suppress(ValueError):
            mode = HVACMode(str(value))
            if mode is not HVACMode.OFF and mode in self.hvac_modes:
                self._last_active = mode

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        return RestoredExtraData(
            {
                _LAST_ACTIVE_HVAC_MODE: self._last_active.value,
                _TARGET_TEMPERATURE_CELSIUS: self._thermostat.target,
            }
        )

    @property
    def _readings(self) -> ZoneReadings:
        return self.runtime.zone_readings.get(self._zone, ZoneReadings())

    @property
    def current_temperature(self) -> float | None:
        return self._readings.temperature

    @property
    def current_humidity(self) -> float | None:
        return self._readings.humidity if self._has_humidity else None

    @property
    def target_temperature(self) -> float:
        thermostat = self._thermostat
        if thermostat.preset is not None:
            return self._config.preset_targets.get(thermostat.preset, thermostat.target)
        return thermostat.target

    @property
    def preset_mode(self) -> str | None:
        if not self._attr_preset_modes:
            return None
        preset = self._thermostat.preset
        return PRESET_NONE if preset is None else preset.value

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode(self._thermostat.hvac_mode.value)

    @property
    def hvac_action(self) -> HVACAction | None:
        desired = self.runtime.desired
        if desired is None:
            return None
        if self._thermostat.hvac_mode is Mode.OFF:
            return HVACAction.OFF
        demand = desired.demands.get(self._zone)
        if demand is None or not demand.on:
            return HVACAction.IDLE
        return HVACAction.HEATING if demand.mode is Mode.HEAT else HVACAction.COOLING

    @callback
    def _set(self, thermostat: DigitalThermostatState) -> None:
        self._thermostat = thermostat
        self.runtime.set_thermostat(self._zone, thermostat)
        self._published = None
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a manual target in Celsius, which leaves any preset."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        target = _usable_target(float(temperature))
        if target is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_target_temperature",
                translation_placeholders={
                    "temperature": str(temperature),
                    "minimum": str(MIN_TARGET),
                    "maximum": str(MAX_TARGET),
                },
            )
        self._set(DigitalThermostatState(self._thermostat.hvac_mode, target))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        preset = None if preset_mode == PRESET_NONE else Preset(preset_mode)
        self._set(
            DigitalThermostatState(self._thermostat.hvac_mode, self._thermostat.target, preset)
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Change only this zone's thermostat mode."""
        self._remember_active(hvac_mode)
        thermostat = self._thermostat
        self._set(
            DigitalThermostatState(Mode(hvac_mode.value), thermostat.target, thermostat.preset)
        )

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(self._last_active)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    entities: list[tuple[str | None, Entity]] = [
        (zone.slug, ZoneClimate(runtime, zone, zone.thermostat))
        for zone in runtime.plant.zones
        if isinstance(zone.thermostat, DigitalThermostat)
    ]
    async_add_plant_entities(runtime, "climate", async_add_entities, entities)


def _usable_target(value: object) -> float | None:
    """Return a Celsius target inside the thermostat range, or None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not MIN_TARGET <= value <= MAX_TARGET:
        return None
    return float(value)
