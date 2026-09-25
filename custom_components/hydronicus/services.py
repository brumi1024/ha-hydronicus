"""Hydronicus actions, and the plant file of a stored Plant that they return."""

from __future__ import annotations

from typing import Final

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN
from .core.plant_file import PlantFileError, dump_yaml, export_plant
from .storage import plant_from_entry

SERVICE_EXPORT_PLANT: Final = "export_plant"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_DOCUMENT: Final = "document"
ATTR_YAML: Final = "yaml"

_EXPORT_PLANT_SCHEMA: Final = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})


async def _async_export_plant(call: ServiceCall) -> ServiceResponse:
    """Return the format 2 plant file of one Plant, which imports as the same Plant."""
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = call.hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="plant_not_found",
            translation_placeholders={"config_entry_id": entry_id},
        )
    try:
        document = export_plant(plant_from_entry(entry))
    except PlantFileError as error:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_plant",
            translation_placeholders={"plant": entry.title, "error": str(error)},
        ) from error
    return {ATTR_DOCUMENT: document, ATTR_YAML: dump_yaml(document)}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Hydronicus actions."""
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_EXPORT_PLANT,
        _async_export_plant,
        schema=_EXPORT_PLANT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
