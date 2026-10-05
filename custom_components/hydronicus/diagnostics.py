"""Diagnostics of one Plant (contract K5).

They hold the configuration as its plant file, the last observations, the
desired state, the reconciler state, the flow counters, and the recent Dry run
proposals. A Plant
holds no secret, and its names and entity IDs are what makes a report
readable, so nothing is redacted; the troubleshooting guide says so.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import HydronicusConfigEntry
from .core.model import Desired
from .core.plant_file import export_plant
from .core.reconcile import target_to_dict
from .core.step import Observations, SwitchState, value_of
from .storage import stored_document
from .view import pump_operation, source_operation


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
            entity: {
                "value": value_of(state),
                "since": state.since,
                "moving": isinstance(state, SwitchState) and state.moving,
            }
            for entity, state in observations.outputs.items()
        },
        "readiness": _plain(dict(observations.readiness)),
        "sensors": _plain(dict(observations.sensors)),
        "areas": _plain(dict(observations.areas)),
        "thermostats": _plain(dict(observations.thermostats)),
        "schedules": _plain(dict(observations.schedules)),
        "recovery": _plain(dict(observations.recovery)),
    }


def _desired(desired: Desired) -> dict[str, Any]:
    return {
        "mode": desired.mode.value,
        "source_request": desired.source_request,
        "outputs": {entity: target_to_dict(target) for entity, target in desired.outputs.items()},
        "reasons": dict(desired.reasons),
        "demands": _plain(dict(desired.demands)),
        "comfort": _plain(dict(desired.comfort)),
        "blocking_sensors": _plain(dict(desired.blocking_sensors)),
        "blocking_condensation_inputs": _plain(dict(desired.blocking_condensation_inputs)),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HydronicusConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    view = runtime.view
    now = dt_util.utcnow().timestamp()
    return {
        # A configuration that is not valid has no Plant to export, only what is stored.
        "plant": export_plant(runtime.plant) if runtime.problem is None else stored_document(entry),
        "options": dict(entry.options),
        "requested_mode": runtime.requested_mode.value,
        "status": "degraded"
        if runtime.evaluation_error
        else None
        if view is None
        else view.status(),
        "evaluated_at": None if view is None else view.at,
        "evaluation_error": runtime.evaluation_error,
        "blocking_reason": runtime.evaluation_error
        or (None if view is None else view.blocking_reason()),
        "next_evaluation_at": runtime.next_evaluation_at,
        "learning": _plain(runtime.learning.diagnostics(now)),
        "forecast": None if runtime.forecast is None else runtime.forecast.diagnostics(now),
        "sensor_health": {} if view is None else view.sensor_health(now),
        "pending_commands": {
            entity: {
                "target": target_to_dict(attempt.target),
                "age_seconds": round(max(0.0, now - attempt.sent_at), 1),
                "attempts": attempt.count,
            }
            for entity, attempt in sorted(runtime.reconcile_state.attempts.items())
        },
        "pump_operation": {}
        if view is None
        else {
            pump.slug: pump_operation(
                runtime.plant,
                pump,
                view.observations,
                view.at,
                source_winding=view.source_winding and view.live,
            ).attributes()
            for pump in runtime.plant.pumps
        },
        "source_operation": None
        if view is None
        else source_operation(runtime.plant, view.observations).attributes(),
        "observed_flow": {}
        if view is None
        else {
            str(loop.ref): view.loop_operation(loop, observed=True).attributes()
            for loop in runtime.plant.all_loops
        },
        "observations": None if view is None else _observations(view.observations),
        "desired": None if view is None else _desired(view.desired),
        "state": runtime.state.to_dict(),
        "reconcile": runtime.reconcile_state.to_dict(),
        "unusable_inputs": runtime.unusable.to_dict(),
        "flow": runtime.flow.to_dict(),
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
