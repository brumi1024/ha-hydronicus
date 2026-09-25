"""Config flow for Hydronicus."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_CIRCUIT,
    SUBENTRY_TYPE_SOURCE,
    SUBENTRY_TYPE_ZONE,
)
from .flows.common import OwnEntityPickerMixin
from .flows.legacy import (
    ActuatorSubentryFlowHandler,
    CircuitSubentryFlowHandler,
    ZoneSubentryFlowHandler,
)
from .flows.plant import PlantSettingsSteps
from .flows.setup import SetupSteps
from .flows.source import SourceSubentryFlowHandler


class HydronicClimateConfigFlow(  # type: ignore[call-arg]
    OwnEntityPickerMixin, SetupSteps, PlantSettingsSteps, config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle creation of a hydronic plant config entry."""

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return dynamic object types supported by this plant."""
        return {
            SUBENTRY_TYPE_ACTUATOR: ActuatorSubentryFlowHandler,
            SUBENTRY_TYPE_CIRCUIT: CircuitSubentryFlowHandler,
            SUBENTRY_TYPE_ZONE: ZoneSubentryFlowHandler,
            SUBENTRY_TYPE_SOURCE: SourceSubentryFlowHandler,
        }
