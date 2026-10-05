"""The digital thermostat of a zone (decision 9).

It owns the zone's target, preset, and mode, restores them across restarts, and
reports as its action what the equipment does for the zone. The exact Celsius
target is persisted beside the restored state, because the display unit may
round it.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any, Final

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
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
from .core.comfort import ComfortTarget, comfort_target
from .core.model import DigitalThermostat, LearningMode, Mode, Preset, Zone
from .core.step import DigitalThermostatState
from .entity import ZoneEntity, async_add_plant_entities
from .runtime import PlantRuntime

# The runtime evaluates thermostat changes itself.
PARALLEL_UPDATES = 0

MIN_TARGET: Final = 5.0
MAX_TARGET: Final = 35.0
_LAST_ACTIVE_HVAC_MODE: Final = "last_active_hvac_mode"
_LEGACY_TARGET_CELSIUS: Final = "target_temperature_celsius"
_HEAT_TARGET_CELSIUS: Final = "heat_target_temperature_celsius"
_COOL_TARGET_CELSIUS: Final = "cool_target_temperature_celsius"
_BASE_FEATURES: Final = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)


class ZoneClimate(ZoneEntity, ClimateEntity, RestoreEntity):
    """A Hydronicus-owned digital thermostat for one zone."""

    # No name: the thermostat is the zone device's main feature and takes its name.
    _attr_name = None
    _attr_translation_key = "zone"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_TARGET
    _attr_max_temp = MAX_TARGET
    _attr_target_temperature_step = 0.5
    _unrecorded_attributes = frozenset({"reason", "schedule_status", "learning_reason"})

    def __init__(self, runtime: PlantRuntime, zone: Zone, config: DigitalThermostat) -> None:
        super().__init__(runtime, zone, "climate")
        self._config = config
        modes = runtime.plant.zone_modes(zone.slug)
        self._attr_hvac_modes = [HVACMode.OFF]
        self._attr_hvac_modes.extend(
            HVACMode(mode.value) for mode in (Mode.HEAT, Mode.COOL) if mode in modes
        )
        self._attr_supported_features = _BASE_FEATURES
        if config.presets or config.cool_presets or config.schedule is not None:
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
        self._has_humidity = bool(zone.humidity or zone.areas)
        self._targets = {Mode.HEAT: config.target, Mode.COOL: config.cool_target}
        # The mode turn_on restores, kept beside the zone mode in the restore state.
        self._last_active = HVACMode.COOL if modes == {Mode.COOL} else HVACMode.HEAT
        self._thermostat = DigitalThermostatState(
            Mode.OFF, self._targets[Mode(self._last_active.value)]
        )

    async def async_added_to_hass(self) -> None:
        """Restore the target, preset, and mode, then hand them to the runtime."""
        await super().async_added_to_hass()
        extra: dict[str, Any] = {}
        if (extra_data := await self.async_get_last_extra_data()) is not None:
            extra = extra_data.as_dict()
            self._remember_active(extra.get(_LAST_ACTIVE_HVAC_MODE))
        for mode, key in ((Mode.HEAT, _HEAT_TARGET_CELSIUS), (Mode.COOL, _COOL_TARGET_CELSIUS)):
            if (target := _usable_target(extra.get(key))) is not None:
                self._targets[mode] = target
        last_state = await self.async_get_last_state()
        if last_state is not None:
            preset = str(last_state.attributes.get("preset_mode", PRESET_NONE)).lower()
            mode = Mode.OFF
            with suppress(ValueError):
                if HVACMode(last_state.state) in self.hvac_modes:
                    mode = Mode(last_state.state)
            self._remember_active(mode.value)
            active = Mode(self._last_active.value)
            key = _COOL_TARGET_CELSIUS if active is Mode.COOL else _HEAT_TARGET_CELSIUS
            target = _usable_target(extra.get(key))
            # Version 0.3.0 stored one exact manual target, even under a preset.
            # Import it only for the last active mode, behind any newer value.
            if target is None:
                target = _usable_target(extra.get(_LEGACY_TARGET_CELSIUS))
            # Only a manual displayed target can restore a target when precise
            # extra data is absent. A preset or schedule may display a setback.
            if target is None and preset == PRESET_NONE:
                with suppress(KeyError, TypeError, ValueError):
                    target = _usable_target(
                        TemperatureConverter.convert(
                            float(last_state.attributes[ATTR_TEMPERATURE]),
                            self.hass.config.units.temperature_unit,
                            UnitOfTemperature.CELSIUS,
                        )
                    )
            if target is not None:
                self._targets[active] = target
            self._thermostat = DigitalThermostatState(
                mode,
                self._targets[active],
                Preset(preset)
                if preset in (self.preset_modes or ()) and preset != PRESET_NONE
                else None,
            )
        else:
            self._thermostat = DigitalThermostatState(
                Mode.OFF, self._targets[Mode(self._last_active.value)]
            )
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
                _HEAT_TARGET_CELSIUS: self._targets[Mode.HEAT],
                _COOL_TARGET_CELSIUS: self._targets[Mode.COOL],
            }
        )

    @property
    def current_temperature(self) -> float | None:
        return self._readings.temperature

    @property
    def current_humidity(self) -> float | None:
        return self._readings.humidity if self._has_humidity else None

    @property
    def target_temperature(self) -> float:
        return self._comfort.target

    @property
    def _comfort(self) -> ComfortTarget:
        view = self.runtime.view
        # A queued user change has not been evaluated yet. Keep its immediate
        # display, and retain the last active mode's presets while switched off.
        if (
            view is not None
            and view.observations.thermostats.get(self._zone) == self._thermostat
            and (
                self._thermostat.hvac_mode is not Mode.OFF
                or self._thermostat.preset is Preset.SCHEDULE
            )
            and (proposal := view.desired.comfort.get(self._zone)) is not None
        ):
            return proposal
        schedule = self._config.schedule
        observed = (
            None
            if view is None or schedule is None
            else view.observations.schedules.get(schedule.entity)
        )
        now = 0.0 if view is None else view.at
        mode = self._thermostat.hvac_mode
        previous = self.runtime.state.demands.get(self._zone)
        if mode is Mode.OFF and self._thermostat.preset is not Preset.SCHEDULE:
            mode = Mode(self._last_active.value)
        return comfort_target(
            self._config,
            mode,
            self._thermostat.target,
            self._thermostat.preset,
            self.current_temperature,
            observed,
            now,
            lambda deadline: deadline <= now,
            None if previous is None or previous.mode is not mode else previous.early_start_event,
        )

    @property
    def preset_modes(self) -> list[str]:
        modes = [preset.value for preset in self._config.presets_for(Mode(self._last_active.value))]
        if self._config.schedule is not None:
            modes.append(Preset.SCHEDULE.value)
        if self.supported_features & ClimateEntityFeature.PRESET_MODE:
            modes.append(PRESET_NONE)
        return modes

    @property
    def preset_mode(self) -> str | None:
        if not self.preset_modes:
            return None
        preset = self._thermostat.preset
        return PRESET_NONE if preset is None else preset.value

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode(self._thermostat.hvac_mode.value)

    @property
    def hvac_action(self) -> HVACAction | None:
        """What the equipment does for the zone; the demand sensors show what it asks for."""
        view = self.runtime.view
        if view is None:
            return None
        action = HVACAction(view.zone_action(self._zone))
        # Frost protection heats a zone whose thermostat is off.
        if self._thermostat.hvac_mode is Mode.OFF and action is HVACAction.IDLE:
            return HVACAction.OFF
        return action

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Why the zone demands or not, as its demand sensors show it."""
        view = self.runtime.view
        demand = None if view is None else view.desired.demands.get(self._zone)
        comfort = self._comfort
        recovery = (
            view.observations.recovery.get(self._zone)
            if view is not None
            and view.observations.thermostats.get(self._zone) == self._thermostat
            else None
        )
        return {
            "reason": None if demand is None else demand.reason,
            "heat_target": self._targets[Mode.HEAT],
            "cool_target": self._targets[Mode.COOL],
            "planned_target": self._thermostat.target,
            "effective_target": comfort.target,
            "early_start": comfort.early_start,
            "schedule_status": comfort.schedule_status,
            "recovery_method": comfort.recovery_method,
            "planned_recovery_seconds": comfort.recovery_seconds,
            "learning_mode": self._config.learning.value,
            "learning_reason": "disabled"
            if self._config.learning is LearningMode.OFF
            else "no recovery estimate"
            if recovery is None
            else recovery.reason,
            "learning_episode_count": 0 if recovery is None else recovery.episode_count,
            "learning_confidence": False if recovery is None else recovery.confidence,
            "estimated_recovery_seconds": None if recovery is None else recovery.seconds,
        }

    @callback
    def _set(self, thermostat: DigitalThermostatState) -> None:
        self._thermostat = thermostat
        self.runtime.set_thermostat(self._zone, thermostat)
        self._published = None
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a manual target in Celsius, which leaves any preset, and the mode it names."""
        # Home Assistant has already refused a target outside min_temp and max_temp.
        temperature = kwargs.get(ATTR_TEMPERATURE)
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        target = None if temperature is None else float(temperature)
        if hvac_mode is not None and hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_hvac_mode",
                translation_placeholders={
                    "mode": str(hvac_mode),
                    "modes": ", ".join(self.hvac_modes),
                },
            )
        thermostat = self._thermostat
        mode = thermostat.hvac_mode
        if hvac_mode is not None:
            self._remember_active(hvac_mode)
            mode = Mode(HVACMode(hvac_mode).value)
        if target is not None:
            self._targets[Mode(self._last_active.value)] = target
            self._set(DigitalThermostatState(mode, target))
        elif mode is not thermostat.hvac_mode:
            self._set_mode(mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        preset = None if preset_mode == PRESET_NONE else Preset(preset_mode)
        self._set(
            DigitalThermostatState(self._thermostat.hvac_mode, self._thermostat.target, preset)
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Change only this zone's thermostat mode."""
        self._remember_active(hvac_mode)
        self._set_mode(Mode(hvac_mode.value))

    @callback
    def _set_mode(self, mode: Mode) -> None:
        preset = self._thermostat.preset
        if preset is not None and preset.value not in self.preset_modes:
            preset = None
        self._set(
            DigitalThermostatState(mode, self._targets[Mode(self._last_active.value)], preset)
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
