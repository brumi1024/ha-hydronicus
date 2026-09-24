"""Home Assistant Repairs for unresolved topology bindings."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.components.repairs.const import FlowType
from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .core.entity_bindings import BindingCategory, EntityBinding

if TYPE_CHECKING:
    from .runtime import HydronicRuntime

REPAIR_ISSUE_PREFIX = "unresolved_entity"
ISSUE_DATA_ENTRY_ID = "entry_id"
ISSUE_DATA_SUBENTRY_ID = "subentry_id"

_TRANSLATION_KEYS = {
    BindingCategory.SENSOR: "missing_sensor_binding",
    BindingCategory.FEEDBACK: "missing_feedback_binding",
    BindingCategory.ACTUATOR: "missing_actuator_binding",
    BindingCategory.THERMOSTAT: "missing_thermostat_binding",
}
_FIXABLE_SUFFIX = "_fixable"


def _plant_issue_prefix(plant_id: str) -> str:
    """Build the opaque issue-ID prefix for one plant."""
    digest = hashlib.sha256(plant_id.encode("utf-8")).hexdigest()[:16]
    return f"{REPAIR_ISSUE_PREFIX}_{digest}_"


def _issue_id(plant_id: str, binding: EntityBinding) -> str:
    """Build an opaque, stable issue ID without storing the entity reference."""
    stable_key = "|".join((plant_id, binding.object_id, binding.object_type, binding.binding_key))
    digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:24]
    return f"{_plant_issue_prefix(plant_id)}{binding.category.value}_{digest}"


def _plant_entry(hass: HomeAssistant, plant_id: str) -> ConfigEntry[HydronicRuntime] | None:
    """Return the config entry whose runtime reports bindings for one plant."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime: HydronicRuntime | None = getattr(entry, "runtime_data", None)
        if runtime is not None and runtime.plant_id == plant_id:
            return entry
    return None


def _owning_subentry_id(entry: ConfigEntry[HydronicRuntime], binding: EntityBinding) -> str | None:
    """Return the config subentry that owns the object carrying one binding."""
    runtime = entry.runtime_data
    owners = {
        "zone": runtime.zone_subentry_ids,
        "valve": runtime.actuator_subentry_ids,
        "circuit": runtime.circuit_subentry_ids,
        "source": runtime.source_subentry_ids,
    }.get(binding.object_type)
    if owners is not None:
        return owners.get(binding.object_id)
    # Pumps, and every object created with the plant, are owned by the parent entry.
    return None


def async_sync_repairs(
    hass: HomeAssistant, plant_id: str, unresolved_bindings: Iterable[EntityBinding]
) -> None:
    """Create current binding repairs and remove recovered or obsolete repairs."""
    current = tuple(unresolved_bindings)
    current_issue_ids = {_issue_id(plant_id, binding) for binding in current}
    registry = ir.async_get(hass)
    for domain, issue_id in tuple(registry.issues):
        if domain != DOMAIN or not issue_id.startswith(_plant_issue_prefix(plant_id)):
            continue
        if issue_id not in current_issue_ids:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
    if not current:
        return

    entry = _plant_entry(hass, plant_id)
    for binding in current:
        data: dict[str, str | int | float | None] = {
            "object_id": binding.object_id,
            "binding_key": binding.binding_key,
            "binding_category": binding.category.value,
        }
        translation_key = _TRANSLATION_KEYS[binding.category]
        subentry_id = _owning_subentry_id(entry, binding) if entry is not None else None
        if entry is not None and subentry_id is not None:
            data[ISSUE_DATA_ENTRY_ID] = entry.entry_id
            data[ISSUE_DATA_SUBENTRY_ID] = subentry_id
            translation_key += _FIXABLE_SUFFIX
        ir.async_create_issue(
            hass,
            DOMAIN,
            _issue_id(plant_id, binding),
            data=data,
            is_fixable=subentry_id is not None,
            is_persistent=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=translation_key,
            translation_placeholders={
                "object_type": binding.object_type,
                "object_name": binding.object_name,
                "binding_label": binding.label,
            },
        )


class SubentryReconfigureRepairFlow(RepairsFlow):
    """Explain an unresolved binding, then open its owning subentry's reconfigure flow."""

    def __init__(self, entry_id: str, subentry_id: str) -> None:
        """Remember which subentry owns the unresolved binding."""
        self._entry_id = entry_id
        self._subentry_id = subentry_id

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> RepairsFlowResult:
        """Start with the confirmation step."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Hand off to the subentry reconfigure flow once the user confirms."""
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, self.issue_id)
        placeholders = issue.translation_placeholders if issue is not None else None
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                data_schema=vol.Schema({}),
                description_placeholders=placeholders,
            )

        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        subentry = entry.subentries.get(self._subentry_id) if entry is not None else None
        if entry is None or subentry is None:
            return self.async_abort(reason="subentry_not_found")
        result = await self.hass.config_entries.subentries.async_init(
            (entry.entry_id, subentry.subentry_type),
            context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id},
        )
        # Abort rather than create an entry: the issue stays until the binding
        # actually resolves, and the runtime removes it on its next synchronization.
        return self.async_abort(
            reason="reconfigure_subentry",
            description_placeholders=placeholders,
            next_flow=(FlowType.CONFIG_SUBENTRIES_FLOW, result["flow_id"]),
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for a subentry-owned unresolved binding."""
    data = data or {}
    return SubentryReconfigureRepairFlow(
        str(data.get(ISSUE_DATA_ENTRY_ID, "")),
        str(data.get(ISSUE_DATA_SUBENTRY_ID, "")),
    )
