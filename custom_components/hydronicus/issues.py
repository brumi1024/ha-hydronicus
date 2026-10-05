"""The Repairs the runtime raises for one Plant.

A failed evaluation, output faults, missing bindings, unconfirmed outputs, zone
area problems, required sensors that block their zone, and condensation inputs
that block cooling are Repairs, not entities (contract K7). The runtime computes
the current set after every evaluation and ``async_sync_issues`` creates the new
ones and deletes the resolved ones.

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
from .core.model import Loop, OutputRole, Plant
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
    CONDENSATION_INPUT_UNUSABLE = "condensation_input_unusable"


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
# How long an input stays unusable before its Repair is raised, in seconds, so
# that a restart or a short spell of unavailability raises nothing.
UNUSABLE_REPAIR_AFTER: Final = 600.0

_ROLE_NAMES = {
    OutputRole.SOURCE_REQUEST: "source request",
    OutputRole.SOURCE_MODE: "source mode select",
    OutputRole.SOURCE_SETPOINT: "source supply temperature",
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


def condensation_inputs_unusable(plant: Plant, reported: Iterable[tuple[str, str]]) -> list[Issue]:
    """One Repair for each unusable condensation input, naming every loop it blocks.

    ``reported`` holds the loop and the entity of each input that
    ``UnusableInputs`` reports, from ``Desired.blocking_condensation_inputs``.
    """
    loops: dict[str, set[str]] = {}
    for loop, entity in reported:
        loops.setdefault(entity, set()).add(loop)
    issues = []
    for entity, refs in loops.items():
        blocked = [loop for loop in plant.all_loops if str(loop.ref) in refs]
        noun = "loop" if len(blocked) == 1 else "loops"
        issues.append(
            Issue(
                IssueKind.CONDENSATION_INPUT_UNUSABLE,
                entity,
                {
                    "plant": plant.name,
                    "entity_id": entity,
                    "input": _input_name(plant, entity),
                    "loops": f"{noun} {listed([_loop_name(plant, loop) for loop in blocked])}",
                },
            )
        )
    return issues


def _input_name(plant: Plant, entity: str) -> str:
    """What a condensation input is: a switch, or a supply or surface temperature sensor."""
    if any(entity == pump.supply_temperature for pump in plant.pumps):
        return "supply temperature sensor"
    if any(entity == loop.surface_temperature for loop in plant.all_loops):
        return "surface temperature sensor"
    return "condensation switch"


def _loop_name(plant: Plant, loop: Loop) -> str:
    return loop.title if loop.zone is None else f"{plant.zone(loop.zone).title} / {loop.title}"


class UnusableInputs:
    """When each unusable input began to block what needs it, which delays its Repair.

    A required sensor blocks its zone, keyed by the zone's slug, and a
    condensation input blocks the cooling of a loop, keyed by ``str(LoopRef)``;
    each is kept under the kind of its Repair. The runtime updates it after
    every evaluation and persists it, so a restart neither raises a Repair early
    nor starts the delay over.
    """

    def __init__(self, since: Mapping[tuple[IssueKind, str, str], float] | None = None) -> None:
        # By kind, what the input blocks, and the input's entity ID.
        self._since: dict[tuple[IssueKind, str, str], float] = dict(since or {})

    def update(self, unusable: Mapping[IssueKind, Mapping[str, Iterable[str]]], now: float) -> None:
        """Keep the blocks that go on, start the new ones now, and drop the ended ones."""
        self._since = {
            (kind, blocked, entity): self._since.get((kind, blocked, entity), now)
            for kind, inputs in unusable.items()
            for blocked, entities in inputs.items()
            for entity in entities
        }

    def reported(self, kind: IssueKind, now: float) -> list[tuple[str, str]]:
        """The blocked object and input of each block of ``kind`` that has lasted long enough."""
        return [
            (blocked, entity)
            for (of, blocked, entity), since in self._since.items()
            if of is kind and now >= since + UNUSABLE_REPAIR_AFTER
        ]

    def next_report(self, now: float) -> float | None:
        """Just after the next block that still waits becomes a Repair, if any does."""
        waiting = [
            since + UNUSABLE_REPAIR_AFTER + TICK
            for since in self._since.values()
            if now < since + UNUSABLE_REPAIR_AFTER
        ]
        return min(waiting, default=None)

    def to_dict(self) -> dict[str, dict[str, dict[str, float]]]:
        data: dict[str, dict[str, dict[str, float]]] = {}
        for (kind, blocked, entity), since in self._since.items():
            data.setdefault(kind.value, {}).setdefault(blocked, {})[entity] = since
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> UnusableInputs:
        return cls(
            {
                (IssueKind(kind), blocked, entity): float(since)
                for kind, inputs in data.items()
                for blocked, entities in inputs.items()
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
