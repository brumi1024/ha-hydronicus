"""Explicit operator actions for Hydronicus."""

from __future__ import annotations

from typing import cast

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HydronicConfigEntry
from .entity_device import plant_device_info
from .entity_registration import async_add_plant_entities
from .runtime import HydronicRuntime

# The runtime serializes the shutdown sequence under its own operation lock.
PARALLEL_UPDATES = 0


class SafeShutdownButton(ButtonEntity):
    """Release source demand and stop hydraulic equipment in safe order."""

    _attr_translation_key = "safe_shutdown"
    _attr_has_entity_name = True

    def __init__(self, entry: HydronicConfigEntry) -> None:
        """Bind the button to the plant runtime."""
        self._entry = entry
        runtime = cast(HydronicRuntime, entry.runtime_data)
        self._attr_unique_id = f"{runtime.plant_id}_safe_shutdown"
        self._attr_device_info = plant_device_info(runtime)

    @property
    def _runtime(self) -> HydronicRuntime:
        """Resolve the current runtime after a config-entry reload."""
        return cast(HydronicRuntime, self._entry.runtime_data)

    async def async_press(self) -> None:
        """Start or advance the explicit shutdown sequence."""
        hass = cast(HomeAssistant, self.hass)
        await self._runtime.async_safe_shutdown(hass)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Publish one plant-level safe-shutdown action."""
    async_add_plant_entities(
        entry.runtime_data, "button", async_add_entities, [SafeShutdownButton(entry)]
    )
