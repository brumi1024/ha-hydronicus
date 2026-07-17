"""Tests for config flow setup of Hydronic Climate."""

from __future__ import annotations

from homeassistant.data_entry_flow import FlowResultType

from custom_components.hydronic_climate.const import DOMAIN


async def test_user_config_flow_creates_entry(hass) -> None:
    """A user flow should create an empty plant in shadow mode."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Hydronic plant"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hydronic plant"
    assert result["data"]["shadow_mode"] is True
