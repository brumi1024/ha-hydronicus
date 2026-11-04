"""The Plant view a dashboard card reads: one versioned, JSON-ready document per evaluation.

It answers three questions without the card enumerating any entity: what the
Plant does, why, and whether each delivery path is healthy. It only reads the
runtime and its last ``PlantView``; nothing here commands equipment.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from .core.model import Loop, OutputTarget, Pump, Zone
from .core.reconcile import target_to_dict
from .core.step import value_of
from .view import PlantView, pump_operation, source_operation

if TYPE_CHECKING:
    from .runtime import PlantRuntime

# Raise it whenever a key changes meaning or disappears; adding a key keeps it.
VIEW_VERSION: Final = 1


def _time(at: float | None) -> str | None:
    return None if at is None else datetime.fromtimestamp(at, UTC).isoformat()


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _target(target: OutputTarget | None) -> dict[str, Any] | None:
    return None if target is None else target_to_dict(target)


def plant_view(runtime: PlantRuntime) -> dict[str, Any]:
    """The whole Plant as a card shows it; ``evaluated`` is false before the first evaluation."""
    plant, view = runtime.plant, runtime.view
    document: dict[str, Any] = {
        "version": VIEW_VERSION,
        "entry_id": runtime.entry.entry_id,
        "plant": {"id": plant.id, "name": plant.name},
        "evaluated": view is not None,
        "evaluation_error": runtime.evaluation_error,
        "control": runtime.control,
        "live": runtime.state.live,
        "requested_mode": "auto" if runtime.auto_mode else runtime.requested_mode.value,
        "away": None if runtime.away is None else {"until": _time(runtime.away.until)},
        "repairs": sorted(f"{issue.kind.value}:{issue.key}" for issue in runtime.issues),
    }
    if view is None:
        return document
    desired = view.desired
    document |= {
        "evaluated_at": _time(view.at),
        "status": "degraded" if runtime.evaluation_error is not None else view.status(),
        "running_mode": desired.mode.value,
        "blocking_reason": view.blocking_reason(),
        "frost_protection": list(desired.frost_protection),
        "sensor_fallback": list(desired.sensor_fallback),
        "exercising": desired.exercise,
        "zones": [_zone(view, zone) for zone in plant.zones],
        "loops": [_loop(runtime, view, loop) for loop in plant.all_loops],
        "pumps": [_pump(runtime, view, pump) for pump in plant.pumps],
        "source": _source(runtime, view),
        "paths": _paths(view),
        "holds": view.holds(),
        "proposed": {
            entity: value_of(state)
            for entity, state in sorted(runtime.reconcile_state.dry_run.items())
        }
        if not runtime.state.live
        else {},
    }
    return document


def _zone(view: PlantView, zone: Zone) -> dict[str, Any]:
    desired = view.desired
    demand = desired.demands.get(zone.slug)
    comfort = desired.comfort.get(zone.slug)
    readings = view.readings(zone.slug)
    return {
        "slug": zone.slug,
        "name": zone.title,
        "temperature": _round(readings.temperature),
        "humidity": _round(readings.humidity),
        "dew_point": _round(readings.dew_point),
        "target": None if comfort is None else comfort.target,
        "schedule_status": None if comfort is None else comfort.schedule_status,
        "demand": None
        if demand is None
        else {"mode": demand.mode.value, "on": demand.on, "reason": demand.reason},
        "action": view.zone_action(zone.slug),
        "blocked": view.blocked_zones().get(zone.slug),
        "not_responding": _time(view.not_responding.get(zone.slug)),
        "loops": [str(loop.ref) for loop in view.plant.zone_loops(zone.slug)],
    }


def _loop(runtime: PlantRuntime, view: PlantView, loop: Loop) -> dict[str, Any]:
    desired = view.desired
    observed = view.observations.outputs
    return {
        "ref": str(loop.ref),
        "name": loop.title,
        "zone": loop.zone,
        "pump": loop.pump,
        "modes": sorted(mode.value for mode in loop.modes),
        "flowing": view.loop_operation(loop).attributes(),
        "observed_flow": view.loop_operation(loop, observed=True).attributes(),
        "reason": desired.reasons.get(str(loop.ref)),
        "valves": [
            {
                "entity": valve.entity,
                "armed": valve.entity in runtime.armed,
                "observed": None
                if (state := observed.get(valve.entity)) is None
                else value_of(state),
                "target": _target(desired.outputs.get(valve.entity)),
                "reason": desired.reasons.get(valve.entity),
            }
            for valve in loop.valves
        ],
        "holds": view.holds(*view.loop_hold_targets(loop)),
    }


def _pump(runtime: PlantRuntime, view: PlantView, pump: Pump) -> dict[str, Any]:
    desired = view.desired
    observed = None if pump.switch is None else view.observations.outputs.get(pump.switch)
    return {
        "slug": pump.slug,
        "name": pump.title,
        "switch": pump.switch,
        "driven_by_source": pump.driven_by_source,
        "armed": pump.switch is not None and pump.switch in runtime.armed,
        "observed": None if observed is None else value_of(observed),
        "target": None if pump.switch is None else _target(desired.outputs.get(pump.switch)),
        "operation": pump_operation(
            view.plant,
            pump,
            view.observations,
            view.at,
            source_winding=view.source_winding and view.live,
        ).attributes(),
        "reason": None if pump.switch is None else desired.reasons.get(pump.switch),
        "holds": view.holds(pump.switch or "source"),
    }


def _source(runtime: PlantRuntime, view: PlantView) -> dict[str, Any] | None:
    source = view.plant.source
    if source is None:
        return None
    desired = view.desired
    observed = view.observations.outputs.get(source.request)
    curve = desired.heating_curve
    supply = None if source.supply is None else desired.outputs.get(source.supply.entity)
    return {
        "name": source.title,
        "request": source.request,
        "armed": source.request in runtime.armed,
        "requested": desired.source_request,
        "observed": None if observed is None else value_of(observed),
        "reason": desired.reasons.get("source"),
        "operation": source_operation(view.plant, view.observations).attributes(),
        "fault": desired.source_fault,
        "handover": desired.source_handover,
        "inhibited": desired.source_inhibited,
        "supply_target": _target(supply),
        "supply_reason": desired.reasons.get("source_supply"),
        "heating_curve": None
        if curve is None
        else {
            "outdoor": _round(curve.outdoor),
            "fallback": curve.fallback,
            "warm_weather": curve.warm_weather,
            "offset": curve.offset,
            "room_shift": _round(curve.room_shift),
        },
        "dhw": None
        if desired.dhw is None
        else {
            "on": desired.dhw.on,
            "target": desired.dhw.target,
            "reason": desired.dhw_reason,
            "boost_until": _time(desired.dhw.boost_until),
            "disinfect_running": desired.dhw.disinfect_started is not None,
            "last_disinfection": _time(desired.dhw.disinfect_done),
        },
        "holds": view.holds("source"),
    }


def _paths(view: PlantView) -> list[dict[str, Any]]:
    """Each zone's delivery sequence, zone to loop to valves to pump to source, in order.

    A step is ``ok`` once it is observed done, so a card can show where a path
    waits: valves opening, a pump not confirmed, or a source not yet requested.
    """
    desired = view.desired
    plant = view.plant
    paths: list[dict[str, Any]] = []
    for zone in plant.zones:
        demand = desired.demands.get(zone.slug)
        for loop in plant.zone_loops(zone.slug):
            pump = plant.pump(loop.pump)
            serves = demand is not None and demand.on and demand.mode in loop.modes
            flowing = view.loop_flowing(loop)
            valves_open = all(
                value_of(state) is True
                for valve in loop.valves
                if (state := view.seen.outputs.get(valve.entity)) is not None
            )
            pump_on = (
                pump_operation(
                    plant, pump, view.seen, view.at, source_winding=view.source_winding
                ).active
                is True
            )
            paths.append(
                {
                    "zone": zone.slug,
                    "loop": str(loop.ref),
                    "wanted": serves and desired.mode in loop.modes,
                    "steps": [
                        {
                            "kind": "zone",
                            "ok": serves,
                            "reason": None if demand is None else demand.reason,
                        },
                        {
                            "kind": "valves",
                            "ok": valves_open,
                            "entities": [valve.entity for valve in loop.valves],
                        },
                        {"kind": "pump", "ok": pump_on, "entity": pump.switch or "source"},
                        {
                            "kind": "source",
                            "ok": plant.source is None or desired.source_request,
                            "entity": None if plant.source is None else plant.source.request,
                        },
                    ],
                    "flowing": flowing,
                    "reason": desired.reasons.get(str(loop.ref)),
                }
            )
    return paths
