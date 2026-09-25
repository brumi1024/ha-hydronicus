"""Diagnostics of one Plant (contract K5).

They hold the configuration as its plant file, the last observations, the
desired state, the reconciler state, and the recent Dry run proposals, with
names and IDs redacted by ``async_redact_data``.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Final

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import HydronicusConfigEntry
from .core.plant_file import export_plant
from .core.reconcile import target_to_dict
from .core.step import value_of

TO_REDACT: Final = {"id", "name", "title"}


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


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HydronicusConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    observations, desired, reconciled = runtime.observations, runtime.desired, runtime.reconciled
    data: dict[str, Any] = {
        "plant": export_plant(runtime.plant),
        "options": dict(entry.options),
        "requested_mode": runtime.requested_mode.value,
        "status": runtime.status(),
        "evaluated_at": runtime.evaluated_at,
        "observations": None
        if observations is None
        else {
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
        },
        "desired": None
        if desired is None
        else {
            "mode": desired.mode.value,
            "source_request": desired.source_request,
            "outputs": {
                entity: target_to_dict(target) for entity, target in desired.outputs.items()
            },
            "reasons": dict(desired.reasons),
            "demands": _plain(dict(desired.demands)),
        },
        "state": runtime.state.to_dict(),
        "reconcile": runtime.reconcile_state.to_dict(),
        "repairs": [] if reconciled is None else sorted(reconciled.repairs),
        "retry_at": None if reconciled is None else reconciled.retry_at,
        "proposals": [
            {
                "at": proposal.at,
                "entity": proposal.entity,
                "target": target_to_dict(proposal.target),
            }
            for proposal in runtime.proposals
        ],
        "missing": dict(runtime.missing),
        "issues": [issue.kind.value for issue in runtime.issues],
    }
    return async_redact_data(data, TO_REDACT)
