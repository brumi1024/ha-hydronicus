"""Home Assistant Repairs for unresolved topology bindings and zone areas.

A binding of a zone-owned object or a source with a handle opens that zone or
source, and a pump binding opens Plant settings. Other Plant equipment (shared
valves and loops, Plant-owned sources, and the source selector) is edited only
through the plant file, so its repair explains that instead of offering a fix.
A sensor that a zone follows through an area is chosen in the area settings, so
its repair points there.
"""

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

from .areas import AreaResolution, ZoneAreaProblem, ZoneAreaProblemKind, listed
from .const import DOMAIN
from .core.entity_bindings import BindingCategory, EntityBinding

if TYPE_CHECKING:
    from .runtime import HydronicRuntime

REPAIR_ISSUE_PREFIX = "unresolved_entity"
AREA_ISSUE_PREFIX = "zone_area"
ISSUE_DATA_ENTRY_ID = "entry_id"
ISSUE_DATA_SUBENTRY_ID = "subentry_id"

_TRANSLATION_KEYS = {
    BindingCategory.SENSOR: "missing_sensor_binding",
    BindingCategory.FEEDBACK: "missing_feedback_binding",
    BindingCategory.ACTUATOR: "missing_actuator_binding",
    BindingCategory.THERMOSTAT: "missing_thermostat_binding",
}
_AREA_TRANSLATION_KEYS = {
    ZoneAreaProblemKind.AREA_MISSING: "zone_area_missing",
    ZoneAreaProblemKind.NO_TEMPERATURE_SOURCE: "zone_without_temperature_source",
    ZoneAreaProblemKind.SELF_FEED: "zone_area_self_feed",
}
_FIXABLE_SUFFIX = "_fixable"
_PLANT_SETTINGS_SUFFIX = "_plant_settings"
_SUBENTRY_OBJECT_TYPES = frozenset({"zone", "valve", "circuit", "source"})
# Plant equipment that Plant settings edit directly. Shared valves and loops,
# Plant-owned sources, and the source selector are edited through the plant file.
_PLANT_SETTINGS_OBJECT_TYPES = frozenset({"pump"})
# How a repair names the entity behind an actuator binding, by its domain.
_ACTUATOR_NOUNS = {"switch": "switch", "valve": "valve entity", "input_boolean": "toggle helper"}


def _plant_issue_prefix(plant_id: str, prefix: str = REPAIR_ISSUE_PREFIX) -> str:
    """Build the opaque issue-ID prefix for one plant."""
    digest = hashlib.sha256(plant_id.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}_"


def _delete_stale_issues(hass: HomeAssistant, prefix: str, current_issue_ids: set[str]) -> None:
    """Remove this Plant's issues with a prefix that the current state no longer shows."""
    registry = ir.async_get(hass)
    for domain, issue_id in tuple(registry.issues):
        if domain == DOMAIN and issue_id.startswith(prefix) and issue_id not in current_issue_ids:
            ir.async_delete_issue(hass, DOMAIN, issue_id)


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
    """Return the zone or source subentry whose reconfigure flow can fix one binding.

    A zone and its private loops and valves open that zone, and a source with a
    handle opens its source. Pumps, shared loops and valves, Plant-owned
    sources, and the source selector belong to the Plant and return ``None``.
    """
    if binding.object_type not in _SUBENTRY_OBJECT_TYPES:
        return None
    return entry.runtime_data.subentry_id_for(binding.object_id)


def _binding_phrase(binding: EntityBinding) -> str:
    """Name a binding the way users know it, without its entity ID.

    An actuator is the entity bound to its object, such as ``switch bound to
    Study loop valve``; any other binding is a role of its object, such as
    ``temperature sensor of Study`` or ``readiness feedback of Study loop valve``.
    """
    if binding.category is BindingCategory.THERMOSTAT:
        return f"thermostat bound to {binding.object_name}"
    if binding.category is BindingCategory.ACTUATOR:
        domain = binding.entity_id.partition(".")[0]
        return f"{_ACTUATOR_NOUNS.get(domain, 'entity')} bound to {binding.object_name}"
    role = binding.label.removeprefix(f"{binding.object_type} ")
    return f"{role} of {binding.object_name}"


def async_sync_repairs(
    hass: HomeAssistant,
    plant_id: str,
    unresolved_bindings: Iterable[EntityBinding],
    *,
    plant_name: str,
) -> None:
    """Create current binding repairs and remove recovered or obsolete repairs."""
    current = tuple(unresolved_bindings)
    current_issue_ids = {_issue_id(plant_id, binding) for binding in current}
    _delete_stale_issues(hass, _plant_issue_prefix(plant_id), current_issue_ids)
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
        placeholders = {
            "plant": plant_name,
            "object_name": binding.object_name,
            "binding": _binding_phrase(binding),
        }
        subentry_id = _owning_subentry_id(entry, binding) if entry is not None else None
        fixable = False
        if binding.area_id is not None:
            # The area settings, not the zone, choose this sensor.
            translation_key = "missing_area_sensor_binding"
            placeholders["area"] = (
                entry.runtime_data.area_resolution.name(binding.area_id)
                if entry is not None
                else binding.area_id
            )
        elif entry is not None and subentry_id is not None:
            data[ISSUE_DATA_ENTRY_ID] = entry.entry_id
            data[ISSUE_DATA_SUBENTRY_ID] = subentry_id
            placeholders["owner"] = entry.subentries[subentry_id].title
            translation_key += _FIXABLE_SUFFIX
            fixable = True
        elif entry is not None and binding.object_type in _PLANT_SETTINGS_OBJECT_TYPES:
            data[ISSUE_DATA_ENTRY_ID] = entry.entry_id
            translation_key += _PLANT_SETTINGS_SUFFIX
            fixable = True
        ir.async_create_issue(
            hass,
            DOMAIN,
            _issue_id(plant_id, binding),
            data=data,
            is_fixable=fixable,
            is_persistent=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=translation_key,
            translation_placeholders=placeholders,
        )


def _area_issue_id(plant_id: str, problem: ZoneAreaProblem) -> str:
    """Build a stable issue ID for one area problem of one zone."""
    stable_key = "|".join((plant_id, problem.kind.value, problem.zone_id, problem.area_id or ""))
    digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:24]
    return f"{_plant_issue_prefix(plant_id, AREA_ISSUE_PREFIX)}{digest}"


def async_sync_area_repairs(
    hass: HomeAssistant,
    plant_id: str,
    problems: Iterable[ZoneAreaProblem],
    *,
    plant_name: str,
    areas: AreaResolution,
) -> None:
    """Create a repair for each current zone area problem and remove the resolved ones.

    A missing area, and a zone left without a temperature sensor, open the
    zone. A sensor Hydronicus provides is replaced in the area settings, so its
    repair has no fix flow.
    """
    current = tuple(problems)
    current_issue_ids = {_area_issue_id(plant_id, problem) for problem in current}
    _delete_stale_issues(hass, _plant_issue_prefix(plant_id, AREA_ISSUE_PREFIX), current_issue_ids)
    if not current:
        return
    entry = _plant_entry(hass, plant_id)
    for problem in current:
        zone = entry.runtime_data.plant.zones.get(problem.zone_id) if entry is not None else None
        placeholders = {
            "plant": plant_name,
            "zone": zone.name if zone is not None else problem.zone_id,
            "area": areas.name(problem.area_id) if problem.area_id is not None else "",
            "areas": listed([areas.name(area.area_id) for area in zone.areas])
            if zone is not None and zone.areas
            else "",
            "entity_ids": ", ".join(problem.entity_ids),
        }
        data: dict[str, str | int | float | None] = {
            "zone_id": problem.zone_id,
            "area_id": problem.area_id,
        }
        subentry_id = entry.runtime_data.subentry_id_for(problem.zone_id) if entry else None
        self_feed = problem.kind is ZoneAreaProblemKind.SELF_FEED
        fixable = not self_feed and subentry_id is not None
        if fixable and entry is not None and subentry_id is not None:
            data[ISSUE_DATA_ENTRY_ID] = entry.entry_id
            data[ISSUE_DATA_SUBENTRY_ID] = subentry_id
            placeholders["owner"] = entry.subentries[subentry_id].title
        ir.async_create_issue(
            hass,
            DOMAIN,
            _area_issue_id(plant_id, problem),
            data=data,
            is_fixable=fixable,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING if self_feed else ir.IssueSeverity.ERROR,
            translation_key=_AREA_TRANSLATION_KEYS[problem.kind],
            translation_placeholders=placeholders,
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


class PlantSettingsRepairFlow(RepairsFlow):
    """Explain an unresolved Plant equipment binding, then open Plant settings.

    It shares its abort reasons with the zone and source hand-off, so every
    fixable issue translates both flows: ``reconfigure_subentry`` reports the
    hand-off, and ``subentry_not_found`` a Plant that no longer exists.
    """

    def __init__(self, entry_id: str) -> None:
        """Remember which Plant owns the unresolved binding."""
        self._entry_id = entry_id

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> RepairsFlowResult:
        """Start with the confirmation step."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Hand off to the Plant settings flow once the user confirms."""
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, self.issue_id)
        placeholders = issue.translation_placeholders if issue is not None else None
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                data_schema=vol.Schema({}),
                description_placeholders=placeholders,
            )

        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or entry.domain != DOMAIN:
            return self.async_abort(reason="subentry_not_found")
        # Plant settings are the options flow of the Plant entry.
        result = await self.hass.config_entries.options.async_init(entry.entry_id)
        # Abort rather than create an entry: the issue stays until the binding
        # actually resolves, and the runtime removes it on its next synchronization.
        return self.async_abort(
            reason="reconfigure_subentry",
            description_placeholders=placeholders,
            next_flow=(FlowType.OPTIONS_FLOW, result["flow_id"]),
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow of a zone, source, or Plant settings binding."""
    data = data or {}
    entry_id = str(data.get(ISSUE_DATA_ENTRY_ID, ""))
    if ISSUE_DATA_SUBENTRY_ID not in data:
        return PlantSettingsRepairFlow(entry_id)
    return SubentryReconfigureRepairFlow(entry_id, str(data[ISSUE_DATA_SUBENTRY_ID]))
