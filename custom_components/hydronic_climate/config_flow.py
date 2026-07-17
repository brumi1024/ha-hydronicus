"""Config flow for Hydronic Climate."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries

from .const import CONF_NAME, CONF_PLANT_ID, CONF_SHADOW_MODE, DEFAULT_PLANT_NAME, DOMAIN


class HydronicClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle creation of a hydronic plant config entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if not name:
                errors["base"] = "name_required"
            else:
                plant_id = str(uuid4())
                await self.async_set_unique_id(plant_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_NAME: name,
                        CONF_PLANT_ID: plant_id,
                        CONF_SHADOW_MODE: True,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_PLANT_NAME): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
