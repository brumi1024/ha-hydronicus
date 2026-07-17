"""Tests for integration setup and unload."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronic_climate.const import (
    CONF_NAME,
    CONF_PLANT_ID,
    CONF_SHADOW_MODE,
    DOMAIN,
)


async def test_setup_unload_and_reload_entry(hass) -> None:
    """The integration should load, unload, and reload an empty plant cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: "plant-1",
            CONF_SHADOW_MODE: True,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data is not None
    assert entry.runtime_data.shadow_mode is True

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.runtime_data is None

    assert await hass.config_entries.async_reload(entry.entry_id)
