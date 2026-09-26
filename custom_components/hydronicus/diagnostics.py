"""Diagnostics of one Plant (contract K5).

They hold the configuration as its plant file, the last observations, the
desired state, the reconciler state, and the recent Dry run proposals. A Plant
holds no secret, and its names and entity IDs are what makes a report
readable, so nothing is redacted; the troubleshooting guide says so.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from homeassistant.core import HomeAssistant

from . import HydronicusConfigEntry
from .core.model import Desired
from .core.plant_file import export_plant
from .core.reconcile import target_to_dict
from .core.step import Observations, value_of
from .storage import stored_document


def _plain(value: Any) -> Any:
    """Turn dataclasses, enums, mappings, and sets into JSON-friendly values."""
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted(_plain(item) for item in value)
    return value


def _observations(observations: Observations) -> dict[str, Any]:
    return {
        "mode": observations.mode.value,
        "control": observations.control,
        "armed": sorted(observations.armed),
        "outputs": {
            entity: {"value": value_of(state), "since": state.since}
            for entity, state in observations.outputs.items()
        },
        "readiness": _plain(dict(observations.readiness)),
        "sensors": _plain(dict(observations.sensors)),
        "areas": _plain(dict(observations.areas)),
        "thermostats": _plain(dict(observations.thermostats)),
    }


def _desired(desired: Desired) -> dict[str, Any]:
    return {
        "mode": desired.mode.value,
        "source_request": desired.source_request,
        "outputs": {entity: target_to_dict(target) for entity, target in desired.outputs.items()},
        "reasons": dict(desired.reasons),
        "demands": _plain(dict(desired.demands)),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HydronicusConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    view = runtime.view
    return {
        # A configuration that is not valid has no Plant to export, only what is stored.
        "plant": export_plant(runtime.plant) if runtime.problem is None else stored_document(entry),
        "options": dict(entry.options),
        "requested_mode": runtime.requested_mode.value,
        "status": None if view is None else view.status(),
        "evaluated_at": None if view is None else view.at,
        "observations": None if view is None else _observations(view.observations),
        "desired": None if view is None else _desired(view.desired),
        "state": runtime.state.to_dict(),
        "reconcile": runtime.reconcile_state.to_dict(),
        "repairs": [] if view is None else sorted(view.reconciled.repairs),
        "retry_at": None if view is None else view.reconciled.retry_at,
        "proposals": [
            {
                "at": proposal.at,
                "entity": proposal.entity,
                "target": target_to_dict(proposal.target),
            }
            for proposal in runtime.proposals
        ],
        "missing": {} if view is None else dict(view.missing),
        "configuration_problem": runtime.problem,
        "stopping": None
        if view is None or view.stopping is None
        else {
            "plant": export_plant(view.stopping.plant),
            "outputs": sorted(view.stopping.outputs),
            "not_off": view.stopping_outputs(),
        },
        "issues": [issue.kind.value for issue in runtime.issues],
    }
