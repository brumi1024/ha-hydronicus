"""Fix flows for the Repairs that Hydronicus can lead to a fix.

Outputs awaiting confirmation are armed in the fix flow itself, for the unarmed
outputs only. The other fix flows explain the problem and then open the flow
that fixes it through ``next_flow``, which Home Assistant 2026.9 supports for a
config flow, an options flow, and a config subentry flow: an invalid Plant and a
Plant-level missing binding open the entry's reconfigure flow, and a zone's area
problem or missing binding opens that zone's reconfigure flow. Opening another
flow aborts the fix flow, so the Repair stays until the next evaluation finds
the problem gone.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import FlowType, RepairsFlow, RepairsFlowResult
from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, OPTION_ARMED_OUTPUTS, SUBENTRY_TYPE_ZONE
from .core.plant_file import PlantFileError
from .flows.forms import arm_schema, output_labels
from .issues import DATA_ENTRY_ID, DATA_KIND, DATA_ZONE, IssueKind
from .storage import armed_outputs, plant_from_entry, zone_subentry_ids


class _IssueFlow(RepairsFlow):
    """A fix flow of one Plant's issue."""

    def __init__(self, entry_id: str, zone: str | None) -> None:
        self._entry_id = entry_id
        self._zone = zone

    def _entry(self) -> ConfigEntry | None:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        return entry if entry is not None and entry.domain == DOMAIN else None

    def _placeholders(self) -> dict[str, str]:
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, self.issue_id)
        return dict(issue.translation_placeholders or {}) if issue is not None else {}


class ArmOutputsFlow(_IssueFlow):
    """Confirm the outputs that are not armed yet."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        return await self.async_step_arm()

    async def async_step_arm(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        entry = self._entry()
        if entry is None:
            return self.async_abort(reason="plant_not_found")
        try:
            plant = plant_from_entry(entry)
        except PlantFileError:
            return self.async_abort(reason="plant_not_found")
        armed = armed_outputs(entry)
        labels = {
            entity: label for entity, label in output_labels(plant).items() if entity not in armed
        }
        if user_input is not None:
            chosen = set(user_input.get("outputs") or [])
            if not chosen:
                # Nothing confirmed: the Repair stays.
                return self.async_abort(reason="nothing_armed")
            outputs = list(plant.outputs())
            self.hass.config_entries.async_update_entry(
                entry,
                options={
                    **entry.options,
                    OPTION_ARMED_OUTPUTS: [
                        entity for entity in outputs if entity in armed or entity in chosen
                    ],
                },
            )
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="arm",
            data_schema=arm_schema(labels),
            description_placeholders=self._placeholders(),
        )


class OpenFlow(_IssueFlow):
    """Explain the problem, then open the reconfigure flow of the Plant or of its zone."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        placeholders = self._placeholders()
        if user_input is None:
            return self.async_show_form(
                step_id="confirm", data_schema=vol.Schema({}), description_placeholders=placeholders
            )
        entry = self._entry()
        if entry is None:
            return self.async_abort(reason="plant_not_found")
        if self._zone is None:
            result = await self.hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
            )
            return self.async_abort(
                reason="reconfigure_opened",
                description_placeholders=placeholders,
                next_flow=(FlowType.CONFIG_FLOW, result["flow_id"]),
            )
        subentry_id = zone_subentry_ids(entry).get(self._zone)
        if subentry_id is None:
            return self.async_abort(reason="zone_not_found", description_placeholders=placeholders)
        zone_flow = await self.hass.config_entries.subentries.async_init(
            (entry.entry_id, SUBENTRY_TYPE_ZONE),
            context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry_id},
        )
        return self.async_abort(
            reason="zone_opened",
            description_placeholders=placeholders,
            next_flow=(FlowType.CONFIG_SUBENTRIES_FLOW, zone_flow["flow_id"]),
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str | int | float | None] | None
) -> RepairsFlow:
    """Create the fix flow of a Hydronicus Repair from its issue data."""
    data = data or {}
    entry_id = str(data.get(DATA_ENTRY_ID, ""))
    zone = data.get(DATA_ZONE)
    zone_slug = zone if isinstance(zone, str) else None
    if data.get(DATA_KIND) == IssueKind.OUTPUTS_AWAITING_CONFIRMATION:
        return ArmOutputsFlow(entry_id, None)
    return OpenFlow(entry_id, zone_slug)
