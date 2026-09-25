"""Source subentry flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers import selector

from ..const import (
    CONF_NAME,
    CONF_SOURCE_AVAILABILITY_ENTITY,
    CONF_SOURCE_DEMAND_ENTITY,
    CONF_SOURCE_HYSTERESIS,
    CONF_SOURCE_MAXIMUM_AGE,
    CONF_SOURCE_MINIMUM_TEMPERATURE,
    CONF_SOURCE_PRIORITY,
    CONF_SOURCE_TEMPERATURE_ENTITY,
    CONF_SOURCE_TYPE,
    DEFAULT_SOURCE_HYSTERESIS,
    DEFAULT_SOURCE_MAXIMUM_AGE,
    DEFAULT_SOURCE_PRIORITY,
    SOURCE_KIND_BUFFER,
    SOURCE_KIND_EXTERNAL,
    SUBENTRY_TYPE_SOURCE,
)
from ..core.configuration import (
    BufferTemperatureRequiredError,
)
from ..entry_configuration import (
    data_with_source,
    subentry_draft,
)
from .common import (
    OwnEntityPickerMixin,
    SubentryReviewMixin,
    effective_topology_error,
    max_age_selector,
    name_selector,
    number,
    optional_entity,
    own_entity_errors,
    sensor_selector,
    shared_outputs,
    sharing_to_confirm,
    temperature_delta_selector,
    warning_text,
    whole_number_selector,
    with_submitted_values,
)


def _source_data(user_input: Mapping[str, Any], source_id: str) -> dict[str, Any]:
    """Normalize one source subentry into stable persisted configuration."""
    return {
        "id": source_id,
        CONF_NAME: str(user_input[CONF_NAME]).strip(),
        CONF_SOURCE_TYPE: str(user_input.get(CONF_SOURCE_TYPE, SOURCE_KIND_EXTERNAL)),
        # The schema admits only whole numbers; the priority has always been stored as int.
        CONF_SOURCE_PRIORITY: int(user_input.get(CONF_SOURCE_PRIORITY, DEFAULT_SOURCE_PRIORITY)),
        CONF_SOURCE_AVAILABILITY_ENTITY: user_input.get(CONF_SOURCE_AVAILABILITY_ENTITY),
        CONF_SOURCE_DEMAND_ENTITY: user_input.get(CONF_SOURCE_DEMAND_ENTITY),
        CONF_SOURCE_TEMPERATURE_ENTITY: user_input.get(CONF_SOURCE_TEMPERATURE_ENTITY),
        CONF_SOURCE_MINIMUM_TEMPERATURE: user_input.get(CONF_SOURCE_MINIMUM_TEMPERATURE, 0.0),
        CONF_SOURCE_MAXIMUM_AGE: user_input.get(
            CONF_SOURCE_MAXIMUM_AGE, DEFAULT_SOURCE_MAXIMUM_AGE
        ),
        CONF_SOURCE_HYSTERESIS: user_input.get(CONF_SOURCE_HYSTERESIS, DEFAULT_SOURCE_HYSTERESIS),
    }


def _source_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    """Build the generic and temperature-qualified source editor."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)
            ): name_selector(),
            vol.Required(
                CONF_SOURCE_TYPE,
                default=defaults.get(CONF_SOURCE_TYPE, SOURCE_KIND_EXTERNAL),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[SOURCE_KIND_EXTERNAL, SOURCE_KIND_BUFFER],
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key=CONF_SOURCE_TYPE,
                )
            ),
            vol.Required(
                CONF_SOURCE_PRIORITY,
                default=defaults.get(CONF_SOURCE_PRIORITY, DEFAULT_SOURCE_PRIORITY),
            ): whole_number_selector(minimum=0),
            # vol.Maybe keeps accepting an explicit None, which clears a binding.
            optional_entity(CONF_SOURCE_AVAILABILITY_ENTITY, defaults): vol.Maybe(
                selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["binary_sensor", "input_boolean", "sensor"]
                    )
                )
            ),
            optional_entity(CONF_SOURCE_TEMPERATURE_ENTITY, defaults): vol.Maybe(
                sensor_selector(SensorDeviceClass.TEMPERATURE)
            ),
            optional_entity(CONF_SOURCE_DEMAND_ENTITY, defaults): vol.Maybe(
                selector.EntitySelector(selector.EntitySelectorConfig(domain=["switch", "valve"]))
            ),
            vol.Required(
                CONF_SOURCE_MINIMUM_TEMPERATURE,
                default=defaults.get(CONF_SOURCE_MINIMUM_TEMPERATURE, 0.0),
            ): number(step=0.1, unit=UnitOfTemperature.CELSIUS),
            vol.Required(
                CONF_SOURCE_MAXIMUM_AGE,
                default=defaults.get(CONF_SOURCE_MAXIMUM_AGE, DEFAULT_SOURCE_MAXIMUM_AGE),
            ): max_age_selector(),
            vol.Required(
                CONF_SOURCE_HYSTERESIS,
                default=defaults.get(CONF_SOURCE_HYSTERESIS, DEFAULT_SOURCE_HYSTERESIS),
            ): temperature_delta_selector(),
        }
    )


def _source_validation_errors(
    entry: config_entries.ConfigEntry,
    data: Mapping[str, Any],
    *,
    excluded_subentry_id: str | None = None,
) -> dict[str, str]:
    """Return flow errors after compiling the complete source topology."""
    if not data[CONF_NAME]:
        return {"base": "name_required"}
    error = effective_topology_error(
        entry,
        proposed_sources=(data,),
        excluded_subentry_id=excluded_subentry_id,
    )
    if error is None:
        return {}
    if isinstance(error, BufferTemperatureRequiredError) and error.source_id == data["id"]:
        return {CONF_SOURCE_TEMPERATURE_ENTITY: "buffer_temperature_required"}
    return {"base": "invalid_source"}


class SourceSubentryFlowHandler(
    SubentryReviewMixin, OwnEntityPickerMixin, config_entries.ConfigSubentryFlow
):
    """Add a source used by the read-only source recommendation."""

    _subentry_type = SUBENTRY_TYPE_SOURCE

    def _review_text(self, entry: config_entries.ConfigEntry, data: Mapping[str, Any]) -> str:
        """List the outputs other Plants bind when the source newly shares one, else nothing."""
        sharing = shared_outputs(self.hass, entry.entry_id, data_with_source(entry.data, data))
        if not sharing_to_confirm(sharing, shared_outputs(self.hass, entry.entry_id, entry.data)):
            return ""
        return warning_text(None, [shared.message for shared in sharing])

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Create one source configuration without any actuator binding."""
        entry = self._get_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _source_data(user_input, str(uuid4()))
            errors = own_entity_errors(self.hass, user_input)
            if not errors:
                errors = _source_validation_errors(entry, data)
            if not errors and (
                result := await self._async_save_draft(
                    data,
                    reconfigure=False,
                    warnings=self._review_text(entry, data),
                    errors=errors,
                    user_input=user_input,
                )
            ):
                return result
        return self.async_show_form(
            step_id="user",
            data_schema=with_submitted_values(self, _source_schema(), user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Update a source while preserving its stable UUID."""
        entry = self._get_entry()
        subentry = self._handle_subentry()
        defaults = subentry_draft(entry, subentry)
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _source_data(user_input, defaults["id"])
            errors = own_entity_errors(self.hass, user_input)
            if not errors:
                errors = _source_validation_errors(
                    entry, data, excluded_subentry_id=subentry.subentry_id
                )
            if not errors and (
                result := await self._async_save_draft(
                    data,
                    reconfigure=True,
                    warnings=self._review_text(entry, data),
                    errors=errors,
                    user_input=user_input,
                )
            ):
                return result
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=with_submitted_values(self, _source_schema(defaults), user_input),
            errors=errors,
        )
