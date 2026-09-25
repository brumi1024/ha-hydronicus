"""Hydronicus actions, and the plant file of a stored Plant that they return."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

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
from homeassistant.util.yaml import dump

from .const import CONF_NAME, CONF_PLANT_ID, DOMAIN
from .core.plant_document import export_plant_document
from .entry_configuration import plant_ownership, topology_copy

SERVICE_EXPORT_PLANT: Final = "export_plant"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_DOCUMENT: Final = "document"

_EXPORT_PLANT_SCHEMA: Final = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})


def plant_file(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical plant file of stored Plant data.

    Raise ``ValueError`` when the stored graph does not decode or breaks
    ownership, because such a Plant has no faithful plant file.
    """
    return export_plant_document(
        name=str(data.get(CONF_NAME, "")),
        plant_id=str(data.get(CONF_PLANT_ID, "")),
        topology=topology_copy(data),
        ownership=plant_ownership(data),
    )


def plant_file_yaml(document: Mapping[str, Any]) -> str:
    """Render a plant file as YAML, keeping the canonical key order."""
    return str(dump(dict(document)))


async def _async_export_plant(call: ServiceCall) -> ServiceResponse:
    """Return the plant file of one Plant."""
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = call.hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="plant_not_found",
            translation_placeholders={"config_entry_id": entry_id},
        )
    try:
        document = plant_file(entry.data)
    except ValueError as error:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_stored_graph",
            translation_placeholders={"plant": entry.title, "error": str(error)},
        ) from error
    return {ATTR_DOCUMENT: document}


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
