"""The Repairs the runtime raises for one Plant.

A failed evaluation, output faults, missing bindings, unconfirmed outputs, zone
area problems, and required sensors that block their zone are Repairs, not
entities (contract K7). The runtime computes the current set after every
evaluation and ``async_sync_issues`` creates the new ones and deletes the
resolved ones.

The kinds in ``FIXABLE`` have a fix flow in ``repairs``, which their issue data
leads to: the Plant's entry, and for a zone's problem its subentry. The others
are fixed outside Hydronicus, at the device or in the area settings.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .areas import AreaResolution, ZoneAreaProblem, listed
from .const import DOMAIN
from .core.model import OutputRole, Plant
from .core.plant_file import describe_path
from .core.step import TICK


class IssueKind(StrEnum):
    """The translation key of each Repair."""

    INVALID_PLANT = "invalid_plant"
    EVALUATION_FAILED = "evaluation_failed"
    OUTPUT_NOT_RESPONDING = "output_not_responding"
    OUTPUTS_AWAITING_CONFIRMATION = "outputs_awaiting_confirmation"
    MISSING_BINDING = "missing_binding"
    MISSING_AREA_SENSOR = "missing_area_sensor"
    ZONE_AREA_MISSING = "zone_area_missing"
    ZONE_WITHOUT_TEMPERATURE_SOURCE = "zone_without_temperature_source"
    ZONE_AREA_SELF_FEED = "zone_area_self_feed"
    ZONE_SENSOR_UNUSABLE = "zone_sensor_unusable"


# Kinds with a fix flow; hassfest wants their translations to carry the fix flow
# instead of a description.
FIXABLE = frozenset(
    {
        IssueKind.INVALID_PLANT,
        IssueKind.OUTPUTS_AWAITING_CONFIRMATION,
        IssueKind.MISSING_BINDING,
        IssueKind.ZONE_AREA_MISSING,
        IssueKind.ZONE_WITHOUT_TEMPERATURE_SOURCE,
    }
)
# The issue data a fix flow reads.
DATA_KIND = "kind"
DATA_ENTRY_ID = "entry_id"
DATA_ZONE = "zone"
DATA_PATH = "path"

_WARNINGS = frozenset(
    {
        IssueKind.OUTPUTS_AWAITING_CONFIRMATION,
        IssueKind.ZONE_AREA_SELF_FEED,
    }
)
# How long a required sensor blocks its zone before its Repair is raised, in
# seconds, so that a restart or a short spell of unavailability raises nothing.
SENSOR_REPAIR_AFTER: Final = 600.0

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
    # The zone whose reconfigure flow fixes it, if any.
    zone: str | None = None
    # The plant file path whose form fixes it, if any.
    path: str | None = None

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
        data: dict[str, str | int | float | None] = {
            DATA_KIND: issue.kind.value,
            DATA_ENTRY_ID: entry_id,
        }
        if issue.zone is not None:
            data[DATA_ZONE] = issue.zone
        if issue.path is not None:
            data[DATA_PATH] = issue.path
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            data=data,
            is_fixable=issue.kind in FIXABLE,
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


def evaluation_failed(plant_name: str, error: str) -> Issue:
    return Issue(IssueKind.EVALUATION_FAILED, "", {"plant": plant_name, "error": error})


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


def missing_binding(plant: Plant, document: Mapping[str, Any], entity_id: str, path: str) -> Issue:
    """A bound entity that does not exist; a zone's binding is fixed in that zone.

    ``document`` is the Plant's plant file, which names the objects the path passes through.
    """
    keys = path.split(".")
    return Issue(
        IssueKind.MISSING_BINDING,
        entity_id,
        {
            "plant": plant.name,
            "entity_id": entity_id,
            "path": describe_path(document, path),
        },
        zone=keys[1] if keys[0] == "zones" and len(keys) > 1 else None,
        path=path,
    )


def missing_area_sensor(plant: Plant, area: str, entity_id: str) -> Issue:
    return Issue(
        IssueKind.MISSING_AREA_SENSOR,
        f"{area}|{entity_id}",
        {"plant": plant.name, "area": area, "entity_id": entity_id},
    )


def zone_sensor_unusable(plant: Plant, zone: str, entity_id: str) -> Issue:
    return Issue(
        IssueKind.ZONE_SENSOR_UNUSABLE,
        f"{zone}|{entity_id}",
        {"plant": plant.name, "zone": plant.zone(zone).title, "entity_id": entity_id},
    )


class BlockingSensors:
    """When each required sensor began to block its zone, which delays its Repair.

    The runtime updates it from ``Desired.blocking_sensors`` after every
    evaluation and persists it, so a restart neither raises the Repair early
    nor starts the delay over.
    """

    def __init__(self, since: Mapping[tuple[str, str], float] | None = None) -> None:
        # By zone slug and sensor entity ID.
        self._since: dict[tuple[str, str], float] = dict(since or {})

    def update(self, blocking: Mapping[str, Iterable[str]], now: float) -> None:
        """Keep the blocks that go on, start the new ones now, and drop the ended ones."""
        self._since = {
            (zone, entity): self._since.get((zone, entity), now)
            for zone, entities in blocking.items()
            for entity in entities
        }

    def reported(self, now: float) -> list[tuple[str, str]]:
        """The zone and sensor of each block that has lasted ``SENSOR_REPAIR_AFTER``."""
        return [key for key, since in self._since.items() if now >= since + SENSOR_REPAIR_AFTER]

    def next_report(self, now: float) -> float | None:
        """Just after the next block that still waits becomes a Repair, if any does."""
        waiting = [
            since + SENSOR_REPAIR_AFTER + TICK
            for since in self._since.values()
            if now < since + SENSOR_REPAIR_AFTER
        ]
        return min(waiting, default=None)

    def to_dict(self) -> dict[str, dict[str, float]]:
        data: dict[str, dict[str, float]] = {}
        for (zone, entity), since in self._since.items():
            data.setdefault(zone, {})[entity] = since
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BlockingSensors:
        return cls(
            {
                (zone, entity): float(since)
                for zone, entities in data.items()
                for entity, since in entities.items()
            }
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
        zone=problem.zone,
    )
