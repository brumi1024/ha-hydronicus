"""Create a Plant by pasting its plant file.

The plant file, format 2, is read and validated by ``core.plant_file`` and
stored as the entry data plus one ``zone`` subentry per zone. A new Plant starts
with nothing armed and Control equipment off (contract K6). The guided setup,
the zone subentry flows, reconfigure, and Plant settings build on this flow.
"""

from __future__ import annotations

from typing import Any, Final

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .bindings import output_bound_elsewhere, own_entity
from .const import CONFIG_ENTRY_MINOR_VERSION, CONFIG_ENTRY_VERSION, DOMAIN
from .core.plant_file import PlantFileError, read_plant_file
from .storage import new_entry, new_options

CONF_PLANT_FILE: Final = "plant_file"


class HydronicusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Plant from a plant file."""

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the plant file and create the Plant it describes."""
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        text = ""
        if user_input is not None:
            text = str(user_input.get(CONF_PLANT_FILE, ""))
            try:
                plant = read_plant_file(text)
            except PlantFileError as error:
                errors["base"] = "invalid_plant_file"
                placeholders["error"] = str(error)
            else:
                await self.async_set_unique_id(plant.id)
                self._abort_if_unique_id_configured()
                if (own := own_entity(self.hass, plant)) is not None:
                    errors["base"] = "own_entity"
                    placeholders["error"] = f"{own[0]}: {own[1]}"
                elif (shared := output_bound_elsewhere(self.hass, plant)) is not None:
                    errors["base"] = "output_bound_elsewhere"
                    placeholders["error"] = (
                        f"{shared.path}: {shared.entity_id} ({shared.other_plant})"
                    )
                else:
                    data, subentries = new_entry(plant)
                    return self.async_create_entry(
                        title=plant.name, data=data, options=new_options(), subentries=subentries
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PLANT_FILE, default=text): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    )
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )
