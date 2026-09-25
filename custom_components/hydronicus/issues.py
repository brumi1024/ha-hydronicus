"""The Repairs the runtime raises for one Plant.

Output faults, missing bindings, unconfirmed outputs, and zone area problems
are Repairs, not entities (contract K7). The runtime computes the current set
after every evaluation and ``async_sync_issues`` creates the new ones and
deletes the resolved ones. None of them has a fix flow yet; the guided flows
that fix them arrive with the Plant settings and zone flows.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .areas import AreaResolution, ZoneAreaProblem, listed
from .const import DOMAIN
from .core.model import OutputRole, Plant


class IssueKind(StrEnum):
    """The translation key of each Repair."""

    INVALID_PLANT = "invalid_plant"
    OUTPUT_NOT_RESPONDING = "output_not_responding"
    OUTPUTS_AWAITING_CONFIRMATION = "outputs_awaiting_confirmation"
    MISSING_BINDING = "missing_binding"
    MISSING_AREA_SENSOR = "missing_area_sensor"
    ZONE_AREA_MISSING = "zone_area_missing"
    ZONE_WITHOUT_TEMPERATURE_SOURCE = "zone_without_temperature_source"
    ZONE_AREA_SELF_FEED = "zone_area_self_feed"


_WARNINGS = frozenset(
    {
        IssueKind.OUTPUTS_AWAITING_CONFIRMATION,
        IssueKind.ZONE_AREA_SELF_FEED,
    }
)
_ROLE_NAMES = {
    OutputRole.SOURCE_REQUEST: "source request",
    OutputRole.SOURCE_MODE: "source mode select",
    OutputRole.PUMP: "pump",
    OutputRole.VALVE: "valve",
}


@dataclass(frozen=True, slots=True)
class Issue:
    """One Repair: its kind, what it is about, and its message placeholders."""

    kind: IssueKind
    key: str
    placeholders: Mapping[str, str] = field(default_factory=dict)

    def issue_id(self, entry_id: str) -> str:
        digest = hashlib.sha256(f"{self.kind}|{self.key}".encode()).hexdigest()[:16]
        return f"{_prefix(entry_id)}{self.kind}_{digest}"


def _prefix(entry_id: str) -> str:
    return f"{entry_id}_"


@callback
def async_sync_issues(hass: HomeAssistant, entry_id: str, issues: Iterable[Issue]) -> None:
    """Create the current Repairs of a Plant and delete the ones that resolved."""
    current = {issue.issue_id(entry_id): issue for issue in issues}
    registry = ir.async_get(hass)
    prefix = _prefix(entry_id)
    for domain, issue_id in tuple(registry.issues):
        if domain == DOMAIN and issue_id.startswith(prefix) and issue_id not in current:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
    for issue_id, issue in current.items():
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING
            if issue.kind in _WARNINGS
            else ir.IssueSeverity.ERROR,
            translation_key=issue.kind.value,
            translation_placeholders=dict(issue.placeholders),
        )


@callback
def async_delete_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Delete every Repair of a Plant."""
    async_sync_issues(hass, entry_id, ())


def invalid_plant(plant_name: str, error: str) -> Issue:
    return Issue(IssueKind.INVALID_PLANT, "", {"plant": plant_name, "error": error})


def output_not_responding(plant: Plant, entity_id: str) -> Issue:
    role = _ROLE_NAMES[plant.outputs()[entity_id]]
    return Issue(
        IssueKind.OUTPUT_NOT_RESPONDING,
        entity_id,
        {"plant": plant.name, "entity_id": entity_id, "role": role},
    )


def outputs_awaiting_confirmation(plant: Plant, entity_ids: Iterable[str]) -> Issue:
    return Issue(
        IssueKind.OUTPUTS_AWAITING_CONFIRMATION,
        "",
        {"plant": plant.name, "entity_ids": ", ".join(sorted(entity_ids))},
    )


def missing_binding(plant: Plant, entity_id: str, path: str) -> Issue:
    return Issue(
        IssueKind.MISSING_BINDING,
        entity_id,
        {"plant": plant.name, "entity_id": entity_id, "path": path},
    )


def missing_area_sensor(plant: Plant, area: str, entity_id: str) -> Issue:
    return Issue(
        IssueKind.MISSING_AREA_SENSOR,
        f"{area}|{entity_id}",
        {"plant": plant.name, "area": area, "entity_id": entity_id},
    )


def zone_area_issue(plant: Plant, problem: ZoneAreaProblem, areas: AreaResolution) -> Issue:
    zone = plant.zone(problem.zone)
    area_ids = [area.area for area in zone.areas]
    noun = "area" if len(area_ids) == 1 else "areas"
    return Issue(
        IssueKind(problem.kind.value),
        f"{problem.zone}|{problem.area_id or ''}",
        {
            "plant": plant.name,
            "zone": zone.title,
            "area": areas.name(problem.area_id) if problem.area_id else "",
            "area_id": problem.area_id or "",
            "recreate_name": areas.recreate_name(problem.area_id) if problem.area_id else "",
            "areas": f"{noun} {listed([areas.name(area_id) for area_id in area_ids])}"
            if area_ids
            else "",
            "entity_ids": ", ".join(problem.entity_ids),
        },
    )
