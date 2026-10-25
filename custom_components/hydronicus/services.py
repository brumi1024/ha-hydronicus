"""Hydronicus actions, and the plant file of a stored Plant that they return."""

from __future__ import annotations

from typing import Final

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
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
from .runtime import PlantRuntime
from .storage import plant_from_entry

SERVICE_EXPORT_PLANT: Final = "export_plant"
SERVICE_BOOST_DHW: Final = "boost_dhw"
SERVICE_END_DHW_BOOST: Final = "end_dhw_boost"
ATTR_TEMPERATURE: Final = "temperature"
ATTR_DURATION: Final = "duration"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_DOCUMENT: Final = "document"
ATTR_YAML: Final = "yaml"

_EXPORT_PLANT_SCHEMA: Final = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})
_BOOST_DHW_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_TEMPERATURE): vol.Coerce(float),
        vol.Optional(ATTR_DURATION): cv.positive_time_period,
    }
)
_END_DHW_BOOST_SCHEMA: Final = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})


def _dhw_runtime(call: ServiceCall) -> PlantRuntime:
    """The loaded Plant the call names, which must have a DHW setpoint."""
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = call.hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="plant_not_found",
            translation_placeholders={"config_entry_id": entry_id},
        )
    runtime: PlantRuntime = entry.runtime_data
    source = runtime.plant.source
    if source is None or source.dhw is None or source.dhw.setpoint is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_dhw_setpoint",
            translation_placeholders={"plant": entry.title},
        )
    return runtime


async def _async_boost_dhw(call: ServiceCall) -> None:
    """Raise the DHW target for a bounded time; it is restored when the boost ends."""
    duration = call.data.get(ATTR_DURATION)
    _dhw_runtime(call).command_dhw(
        boost=call.data[ATTR_TEMPERATURE],
        boost_for=None if duration is None else duration.total_seconds(),
    )


async def _async_end_dhw_boost(call: ServiceCall) -> None:
    """End a DHW boost now and restore the owned target."""
    _dhw_runtime(call).command_dhw(end_boost=True)


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
    hass.services.async_register(DOMAIN, SERVICE_BOOST_DHW, _async_boost_dhw, _BOOST_DHW_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_END_DHW_BOOST, _async_end_dhw_boost, _END_DHW_BOOST_SCHEMA
    )
