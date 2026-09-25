"""Plant settings steps of the parent reconfigure flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import selector

from ..const import (
    CONF_DRY_RUN,
    CONF_DRY_RUN_CONFIRMATION,
)
from ..entry_configuration import (
    authorization_output_lines,
    invalidate_output_authorization,
    output_authorization,
)
from .common import (
    ConfigFlowBase,
    dry_run_confirmation_schema,
)


def _dry_run_reconfigure_schema(default: bool) -> vol.Schema:
    """Return the Plant Dry run reconfigure schema."""
    return vol.Schema(
        {
            vol.Required(CONF_DRY_RUN, default=default): selector.BooleanSelector(),
        }
    )


class PlantSettingsSteps(ConfigFlowBase):
    """Change Plant settings through Home Assistant reconfiguration."""

    _requested_dry_run: bool
    _shown_authorization: dict[str, Any]

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Change the Plant Dry run setting through Home Assistant reconfiguration."""
        entry = self._get_reconfigure_entry()
        # A Plant held in Dry run by an output conflict is stored live but is
        # not live, so the form offers its effective setting. Leaving Dry run then
        # takes the confirmed, conflict-checked path; choosing Dry run stores it.
        runtime = getattr(entry, "runtime_data", None)
        current_dry_run = (
            bool(runtime.dry_run)
            if runtime is not None
            else bool(entry.data.get(CONF_DRY_RUN, True))
        )
        if user_input is not None:
            requested_dry_run = bool(user_input[CONF_DRY_RUN])
            if requested_dry_run is False and current_dry_run:
                self._requested_dry_run = False
                return await self.async_step_dry_run_confirmation()
            return await self._async_apply_dry_run(entry, requested_dry_run)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_dry_run_reconfigure_schema(current_dry_run),
        )

    async def async_step_dry_run_confirmation(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm the exact heating outputs before leaving Dry run."""
        entry = self._get_reconfigure_entry()
        if user_input is None:
            return self._dry_run_confirmation_form(entry)
        if not user_input.get(CONF_DRY_RUN_CONFIRMATION, False):
            return self._dry_run_confirmation_form(
                entry, errors={"base": "dry_run_confirmation_required"}
            )
        try:
            # Authorize exactly the outputs the form showed, never a later graph.
            return await self._async_apply_dry_run(
                entry, self._requested_dry_run, authorization=self._shown_authorization
            )
        except ServiceValidationError as error:
            if error.translation_key == "output_authorization_mismatch":
                return self._dry_run_confirmation_form(entry, errors={"base": "outputs_changed"})
            if error.translation_key == "output_conflict":
                placeholders = dict(error.translation_placeholders or {})
                placeholders.pop("plant", None)
                return self._dry_run_confirmation_form(
                    entry, errors={"base": "output_conflict"}, placeholders=placeholders
                )
            raise

    def _dry_run_confirmation_form(
        self,
        entry: config_entries.ConfigEntry,
        *,
        errors: dict[str, str] | None = None,
        placeholders: Mapping[str, str] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Show the current outputs and remember exactly what the user confirms."""
        data = entry.data
        self._shown_authorization = output_authorization(data)
        return self.async_show_form(
            step_id="dry_run_confirmation",
            data_schema=dry_run_confirmation_schema(),
            errors=errors,
            description_placeholders={
                "outputs": authorization_output_lines(data),
                **(placeholders or {}),
            },
        )

    async def _async_apply_dry_run(
        self,
        entry: config_entries.ConfigEntry,
        dry_run: bool,
        *,
        authorization: Mapping[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Apply Dry run, completing any active heating shutdown first."""
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None:
            if not await runtime.async_set_dry_run(
                dry_run,
                hass=self.hass,
                authorization=authorization,
            ):
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=_dry_run_reconfigure_schema(dry_run),
                    errors={"base": "dry_run_shutdown_in_progress"},
                )
        else:
            if not dry_run:
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=_dry_run_reconfigure_schema(
                        bool(entry.data.get(CONF_DRY_RUN, True))
                    ),
                    errors={"base": "dry_run_runtime_unavailable"},
                )
            data = invalidate_output_authorization(entry.data)
            self.hass.config_entries.async_update_entry(entry, data=data)
        return self.async_abort(reason="reconfigure_successful")
