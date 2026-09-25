"""Config flow for Hydronicus."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SUBENTRY_TYPE_ROOM,
    SUBENTRY_TYPE_SOURCE,
)
from .flows.common import OwnEntityPickerMixin
from .flows.plant import PlantSettingsOptionsFlow
from .flows.room import RoomSubentryFlowHandler
from .flows.setup import SetupSteps
from .flows.source import SourceSubentryFlowHandler


class HydronicClimateConfigFlow(  # type: ignore[call-arg]
    OwnEntityPickerMixin, SetupSteps, config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle creation of a hydronic plant config entry."""

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> PlantSettingsOptionsFlow:
        """Return Plant settings, which the Plant entry's Configure button opens."""
        return PlantSettingsOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return the handle types of a Plant: rooms and sources."""
        return {
            SUBENTRY_TYPE_ROOM: RoomSubentryFlowHandler,
            SUBENTRY_TYPE_SOURCE: SourceSubentryFlowHandler,
        }
