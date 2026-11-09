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
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .core.plant_file import PlantFileError, dump_yaml, export_plant
from .runtime import PlantRuntime
from .storage import plant_from_entry

SERVICE_EXPORT_PLANT: Final = "export_plant"
SERVICE_BOOST_DHW: Final = "boost_dhw"
SERVICE_END_DHW_BOOST: Final = "end_dhw_boost"
SERVICE_SET_AWAY: Final = "set_away"
SERVICE_END_AWAY: Final = "end_away"
ATTR_UNTIL: Final = "until"
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
_SET_AWAY_SCHEMA: Final = vol.Schema(
    {vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string, vol.Optional(ATTR_UNTIL): cv.datetime}
)
_END_AWAY_SCHEMA: Final = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})


async def _async_set_away(call: ServiceCall) -> None:
    """Hold every digital thermostat at its away level, until a return time if given."""
    until = call.data.get(ATTR_UNTIL)
    if until is not None:
        until = dt_util.as_utc(until if until.tzinfo else dt_util.as_local(until))
        if until.timestamp() <= dt_util.utcnow().timestamp():
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="away_until_past"
            )
    _runtime(call).set_away(None if until is None else until.timestamp())


async def _async_end_away(call: ServiceCall) -> None:
    """End the away now."""
    _runtime(call).end_away()


def _runtime(call: ServiceCall) -> PlantRuntime:
    """The loaded Plant the call names."""
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = call.hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="plant_not_found",
            translation_placeholders={"config_entry_id": entry_id},
        )
    runtime: PlantRuntime = entry.runtime_data
    return runtime


def _dhw_runtime(call: ServiceCall) -> PlantRuntime:
    """The loaded Plant the call names, which must have a DHW setpoint."""
    runtime = _runtime(call)
    source = runtime.plant.source
    if source is None or source.dhw is None or source.dhw.setpoint is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_dhw_setpoint",
            translation_placeholders={"plant": runtime.entry.title},
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
    hass.services.async_register(DOMAIN, SERVICE_SET_AWAY, _async_set_away, _SET_AWAY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_END_AWAY, _async_end_away, _END_AWAY_SCHEMA)
