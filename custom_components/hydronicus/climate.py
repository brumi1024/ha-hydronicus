"""Shadow-mode climate entities for configured comfort zones."""

from __future__ import annotations

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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import HydronicConfigEntry
from .const import DEFAULT_TARGET_TEMPERATURE, DOMAIN
from .core.model import (
    MAX_ZONE_TARGET_TEMPERATURE,
    MIN_ZONE_TARGET_TEMPERATURE,
    HydronicusThermostatConfig,
    ThermostatHvacMode,
    ZoneRuntime,
)
from .runtime import HydronicRuntime


class ZoneClimate(ClimateEntity, RestoreEntity):
    """A Hydronicus-owned digital thermostat for one Zone."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
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
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.plant_id)}, name=runtime.name
        )
        if any(
            route.zone_id == zone_id and runtime.plant.circuits[route.circuit_id].cooling_enabled
            for route in runtime.plant.routes
        ):
            self._attr_hvac_modes = [
                HVACMode.OFF,
                HVACMode.HEAT,
                HVACMode.COOL,
                HVACMode.HEAT_COOL,
            ]
        if self._configured_preset_modes:
            self._attr_supported_features = (
                ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
            )

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
        last_state = await self.async_get_last_state()
        if last_state is not None:
            target = DEFAULT_TARGET_TEMPERATURE
            preset = PRESET_NONE
            try:
                restored_target = float(last_state.attributes.get(ATTR_TEMPERATURE))
                if MIN_ZONE_TARGET_TEMPERATURE <= restored_target <= MAX_ZONE_TARGET_TEMPERATURE:
                    target = restored_target
            except TypeError, ValueError:
                pass
            restored_preset = str(last_state.attributes.get("preset_mode", PRESET_NONE)).lower()
            if restored_preset == PRESET_NONE or restored_preset in self._configured_preset_modes:
                preset = restored_preset
            try:
                restored_mode = ThermostatHvacMode(last_state.state)
                if HVACMode(restored_mode.value) in self.hvac_modes:
                    mode = restored_mode
            except ValueError:
                pass
        await self._runtime.async_restore_zone_thermostat(
            self._zone_id,
            target_temperature=target,
            preset=preset,
            hvac_mode=mode,
            hass=self.hass,
        )
        self.async_on_remove(self._runtime.async_add_listener(self.async_write_ha_state))

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
        """Change only this Zone's thermostat mode."""
        try:
            thermostat_mode = ThermostatHvacMode(hvac_mode.value)
        except ValueError as error:
            raise ValueError(f"Unsupported HVAC mode {hvac_mode!r}.") from error
        await self._runtime.async_set_zone_hvac_mode(self._zone_id, thermostat_mode, hass=self.hass)


async def async_setup_entry(
    hass: HomeAssistant, entry: HydronicConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add one climate entity for every configured comfort zone."""
    runtime = entry.runtime_data
    parent_entities: list[ZoneClimate] = []
    subentry_entities: dict[str, list[ZoneClimate]] = {}
    for zone in runtime.plant.zones.values():
        if not isinstance(zone.thermostat, HydronicusThermostatConfig):
            continue
        entity = ZoneClimate(entry, zone.id, zone.name)
        if subentry_id := runtime.zone_subentry_ids.get(zone.id):
            subentry_entities.setdefault(subentry_id, []).append(entity)
        else:
            parent_entities.append(entity)
    async_add_entities(parent_entities)
    for subentry_id, entities in subentry_entities.items():
        async_add_entities(entities, config_subentry_id=subentry_id)
