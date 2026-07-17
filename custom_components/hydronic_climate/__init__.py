"""Hydronic Climate integration setup."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .runtime import HydronicRuntime

type HydronicConfigEntry = ConfigEntry[HydronicRuntime]


async def async_setup_entry(hass: HomeAssistant, entry: HydronicConfigEntry) -> bool:
    """Set up a hydronic plant from a config entry."""
    runtime = HydronicRuntime.from_entry(entry)
    entry.runtime_data = runtime
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HydronicConfigEntry) -> bool:
    """Unload a hydronic plant without issuing equipment commands."""
    entry.runtime_data = None
    return True
