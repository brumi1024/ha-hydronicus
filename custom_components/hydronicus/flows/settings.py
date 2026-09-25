"""Plant settings, the options flow: arm outputs and show the plant file.

Arming lists every output with its role and stores the checked ones as armed
(contract K6); Control equipment stays as it is. The plant file is the export
that imports as the same Plant.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow

from ..const import OPTION_ARMED_OUTPUTS
from ..core.plant_file import PlantFileError, write_plant_file
from ..storage import armed_outputs, plant_from_entry
from . import forms


class PlantSettingsFlow(OptionsFlow):
    """Arm the Plant's outputs, or show its plant file."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["arm", "plant_file"])

    async def async_step_arm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm the outputs Hydronicus may command; unchecking one disarms it."""
        entry = self.config_entry
        try:
            plant = plant_from_entry(entry)
        except PlantFileError as error:
            return self.async_abort(
                reason="invalid_plant", description_placeholders={"error": str(error)}
            )
        labels = forms.output_labels(plant)
        if user_input is not None:
            chosen = set(user_input.get("outputs") or [])
            return self.async_create_entry(
                data={
                    **entry.options,
                    OPTION_ARMED_OUTPUTS: [entity for entity in labels if entity in chosen],
                }
            )
        return self.async_show_form(
            step_id="arm",
            data_schema=forms.arm_schema(labels, armed_outputs(entry)),
            description_placeholders={"plant": entry.title},
        )

    async def async_step_plant_file(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the plant file, which imports as the same Plant with the same entity IDs."""
        entry = self.config_entry
        if user_input is not None:
            return self.async_create_entry(data=dict(entry.options))
        try:
            text = write_plant_file(plant_from_entry(entry))
        except PlantFileError as error:
            return self.async_abort(
                reason="invalid_plant", description_placeholders={"error": str(error)}
            )
        return self.async_show_form(
            step_id="plant_file",
            data_schema=vol.Schema({}),
            description_placeholders={"plant": entry.title, "plant_file": text},
        )
