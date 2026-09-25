"""Shadow-mode climate entities for configured comfort zones."""

from __future__ import annotations

from contextlib import suppress
from typing import Any, cast

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoredExtraData, RestoreEntity
from homeassistant.util.unit_conversion import TemperatureConverter

from . import HydronicConfigEntry
from .const import DEFAULT_TARGET_TEMPERATURE
from .core.model import (
    MAX_ZONE_TARGET_TEMPERATURE,
    MIN_ZONE_TARGET_TEMPERATURE,
    HydronicusThermostatConfig,
    ThermostatHvacMode,
    ZoneRuntime,
)
from .core.topology import thermostat_hvac_modes
from .entity_device import topology_device_info
from .entity_registration import async_add_plant_entities
from .runtime import HydronicRuntime

# The runtime serializes thermostat changes under its own operation lock.
PARALLEL_UPDATES = 0

_LAST_ACTIVE_HVAC_MODE = "last_active_hvac_mode"
# The display unit may round the setpoint (whole degrees Fahrenheit), so the exact
# Celsius target is persisted beside it and preferred on restore.
_TARGET_TEMPERATURE_CELSIUS = "target_temperature_celsius"
_BASE_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)


class ZoneClimate(ClimateEntity, RestoreEntity):
    """A Hydronicus-owned digital thermostat for one Zone."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = _BASE_FEATURES
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_ZONE_TARGET_TEMPERATURE
    _attr_max_temp = MAX_ZONE_TARGET_TEMPERATURE
    _attr_target_temperature_step = 0.5

    def __init__(self, entry: HydronicConfigEntry, zone_id: str, name: str) -> None:
        """Bind the entity to one zone in the runtime topology."""
        self._entry = entry
        runtime = entry.runtime_data
        self._zone_id = zone_id
        self._attr_unique_id = f"{runtime.plant_id}_{zone_id}_climate"
        # No name or translation key: the thermostat is the Zone device's main
        # feature and takes the device name, as before.
        self._attr_device_info = topology_device_info(runtime, "zone", zone_id, name)
        self._attr_hvac_modes = [
            HVACMode(mode.value) for mode in thermostat_hvac_modes(runtime.plant, zone_id)
        ]
        if self._configured_preset_modes:
            self._attr_supported_features = _BASE_FEATURES | ClimateEntityFeature.PRESET_MODE
        self._has_humidity_sensors = bool(runtime.plant.zones[zone_id].humidity_sensors)
        # The mode turn_on restores; kept beside the zone mode in restore state.
        self._last_active_hvac_mode = HVACMode.HEAT

    @property
    def _runtime(self) -> HydronicRuntime:
        """Resolve the current runtime after a config-entry reload."""
        return cast(HydronicRuntime, self._entry.runtime_data)

    async def async_added_to_hass(self) -> None:
        """Restore mutable thermostat state, then subscribe to evaluations."""
        await super().async_added_to_hass()
        zone = self._runtime.plant.zones[self._zone_id]
        assert isinstance(zone.thermostat, HydronicusThermostatConfig)
        target = zone.thermostat.initial_target_temperature
        preset = zone.thermostat.initial_preset
        mode = ThermostatHvacMode.OFF
        extra: dict[str, Any] = {}
        if (extra_data := await self.async_get_last_extra_data()) is not None:
            extra = extra_data.as_dict()
            self._remember_active_mode(extra.get(_LAST_ACTIVE_HVAC_MODE))
        last_state = await self.async_get_last_state()
        if last_state is not None:
            target = DEFAULT_TARGET_TEMPERATURE
            preset = PRESET_NONE
            restored_target = _usable_target(extra.get(_TARGET_TEMPERATURE_CELSIUS))
            if restored_target is None:
                # Data from older versions only has the attribute in the display unit.
                with suppress(TypeError, ValueError):
                    restored_target = _usable_target(
                        TemperatureConverter.convert(
                            float(last_state.attributes.get(ATTR_TEMPERATURE)),
                            self.hass.config.units.temperature_unit,
                            UnitOfTemperature.CELSIUS,
                        )
                    )
            if restored_target is not None:
                target = restored_target
            restored_preset = str(last_state.attributes.get("preset_mode", PRESET_NONE)).lower()
            if restored_preset == PRESET_NONE or restored_preset in self._configured_preset_modes:
                preset = restored_preset
            try:
                restored_mode = ThermostatHvacMode(last_state.state)
                if HVACMode(restored_mode.value) in self.hvac_modes:
                    mode = restored_mode
            except ValueError:
                pass
            self._remember_active_mode(mode.value)
        await self._runtime.async_restore_zone_thermostat(
            self._zone_id,
            target_temperature=target,
            preset=preset,
            hvac_mode=mode,
            hass=self.hass,
        )
        self.async_on_remove(self._runtime.async_add_listener(self._async_handle_runtime_update))

    @callback
    def _async_handle_runtime_update(self) -> None:
        """Track the last active mode, whoever set it, then publish the new state."""
        self._remember_active_mode(self._runtime.zone_hvac_modes[self._zone_id].value)
        self.async_write_ha_state()

    def _remember_active_mode(self, value: object) -> None:
        """Remember a mode this thermostat supports as the one turn_on restores."""
        try:
            mode = HVACMode(str(value))
        except ValueError:
            return
        if mode is not HVACMode.OFF and mode in self.hvac_modes:
            self._last_active_hvac_mode = mode

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        """Persist the mode turn_on restores and the exact Celsius setpoint."""
        return RestoredExtraData(
            {
                _LAST_ACTIVE_HVAC_MODE: self._last_active_hvac_mode.value,
                _TARGET_TEMPERATURE_CELSIUS: self._runtime.zone_target_temperatures.get(
                    self._zone_id
                ),
            }
        )

    @property
    def current_humidity(self) -> float | None:
        """Return the zone humidity aggregate the cooling interlock evaluated."""
        if not self._has_humidity_sensors:
            return None
        decision = self._runtime.cooling_zone_decision(self._zone_id)
        if decision is None or decision.humidity_aggregation is None:
            return None
        return decision.humidity_aggregation.value

    @property
    def current_temperature(self) -> float | None:
        """Return the current aggregate zone temperature."""
        return self._runtime.zone_current_temperature(self._zone_id)

    @property
    def target_temperature(self) -> float:
        """Return the current persisted or in-session zone target."""
        return self._runtime.zone_target_temperatures[self._zone_id]

    @property
    def _configured_preset_modes(self) -> list[str]:
        """Return configured standard presets in a stable Home Assistant order."""
        zone = self._runtime.plant.zones[self._zone_id]
        return [
            preset
            for preset in (PRESET_COMFORT, PRESET_ECO, PRESET_AWAY)
            if preset in zone.preset_targets
        ]

    @property
    def preset_modes(self) -> list[str]:
        """Expose only presets that have a configured target temperature."""
        return self._configured_preset_modes

    @property
    def preset_mode(self) -> str:
        """Return the persisted active preset or the standard manual value."""
        return cast(str, self._runtime.zone_preset_modes.get(self._zone_id, PRESET_NONE))

    @property
    def hvac_mode(self) -> HVACMode:
        """Expose this thermostat's runtime mode, independent of the Plant constraint."""
        return HVACMode(self._runtime.zone_hvac_modes[self._zone_id].value)

    @property
    def hvac_action(self) -> HVACAction | None:
        """Expose active or idle shadow heating demand."""
        if self._runtime.evaluation is None:
            return None
        if self.hvac_mode is HVACMode.OFF:
            return HVACAction.OFF
        if self._runtime.runtime_state.cooling_zone_demands.get(self._zone_id, False):
            return HVACAction.COOLING
        if self._runtime.runtime_state.zone_runtime.get(self._zone_id, ZoneRuntime()).demand:
            return HVACAction.HEATING
        return HVACAction.IDLE

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Persist a new target and immediately recalculate shadow demand."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self._runtime.async_set_zone_target_temperature(
            self._zone_id, float(temperature), hass=self.hass
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Persist the selected preset and recalculate shadow demand immediately."""
        await self._runtime.async_set_zone_preset_mode(self._zone_id, preset_mode, hass=self.hass)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Change only this Zone's thermostat mode.

        The climate base class has already rejected modes outside hvac_modes with
        a translated error, and every exposed mode is a thermostat mode.
        """
        self._remember_active_mode(hvac_mode)
        await self._runtime.async_set_zone_hvac_mode(
            self._zone_id, ThermostatHvacMode(hvac_mode.value), hass=self.hass
        )

    async def async_turn_on(self) -> None:
        """Restore the last active mode instead of guessing heat_cool."""
        await self.async_set_hvac_mode(self._last_active_hvac_mode)

    async def async_turn_off(self) -> None:
        """Turn only this Zone's thermostat off."""
        await self.async_set_hvac_mode(HVACMode.OFF)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one climate entity for every configured comfort zone."""
    runtime = entry.runtime_data
    parent_entities: list[ZoneClimate] = []
    subentry_entities: dict[str, list[ZoneClimate]] = {}
    for zone in runtime.plant.zones.values():
        if not isinstance(zone.thermostat, HydronicusThermostatConfig):
            continue
        entity = ZoneClimate(entry, zone.id, zone.name)
        if subentry_id := runtime.subentry_id_for(zone.id):
            subentry_entities.setdefault(subentry_id, []).append(entity)
        else:
            parent_entities.append(entity)
    async_add_plant_entities(
        runtime, "climate", async_add_entities, parent_entities, subentry_entities
    )


def _usable_target(value: object) -> float | None:
    """Return a restored Celsius setpoint inside the thermostat range, or None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not MIN_ZONE_TARGET_TEMPERATURE <= value <= MAX_ZONE_TARGET_TEMPERATURE:
        return None
    return float(value)
