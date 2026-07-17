"""Validation and compilation of an explicitly configured plant topology."""

from __future__ import annotations

from collections.abc import Iterable

from .model import CompiledPlant, PlantConfiguration


class TopologyValidationError(ValueError):
    """Raised when a topology cannot safely be evaluated."""


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def compile_topology(configuration: PlantConfiguration) -> CompiledPlant:
    """Validate and compile a plant configuration without reading runtime state."""
    if not configuration.id:
        raise TopologyValidationError("Plant id must not be empty.")

    zone_ids = [zone.id for zone in configuration.zones]
    circuit_ids = [circuit.id for circuit in configuration.circuits]
    route_ids = [route.id for route in configuration.routes]
    for object_name, ids in (("zone", zone_ids), ("circuit", circuit_ids)):
        if not ids:
            continue
        if not all(ids):
            raise TopologyValidationError(f"Every {object_name} requires a non-empty id.")
        if duplicates := _duplicates(ids):
            raise TopologyValidationError(
                f"Duplicate {object_name} ids: {', '.join(sorted(duplicates))}."
            )
    if not all(route_ids):
        raise TopologyValidationError("Every route requires a non-empty id.")
    if duplicates := _duplicates(route_ids):
        raise TopologyValidationError(f"Duplicate route ids: {', '.join(sorted(duplicates))}.")

    zones = {zone.id: zone for zone in configuration.zones}
    circuits = {circuit.id: circuit for circuit in configuration.circuits}
    referenced_zones: set[str] = set()
    referenced_circuits: set[str] = set()
    for route in configuration.routes:
        if route.zone_id not in zones:
            raise TopologyValidationError(
                f"Route {route.id} references unknown zone {route.zone_id}."
            )
        if route.circuit_id not in circuits:
            raise TopologyValidationError(
                f"Route {route.id} references unknown circuit {route.circuit_id}."
            )
        if not route.enabled:
            continue
        referenced_zones.add(route.zone_id)
        referenced_circuits.add(route.circuit_id)

    orphaned_zones = sorted(set(zones) - referenced_zones)
    orphaned_circuits = sorted(set(circuits) - referenced_circuits)
    if orphaned_zones or orphaned_circuits:
        details: list[str] = []
        if orphaned_zones:
            details.append(f"orphaned zones: {', '.join(orphaned_zones)}")
        if orphaned_circuits:
            details.append(f"orphaned circuits: {', '.join(orphaned_circuits)}")
        raise TopologyValidationError("; ".join(details) + ".")

    summary = tuple(
        (
            f"Circuit {circuit.name} opens valve {circuit.valve_id} before requesting pump "
            f"{circuit.pump_id}."
        )
        for circuit in configuration.circuits
    )
    return CompiledPlant(
        id=configuration.id,
        zones=zones,
        circuits=circuits,
        routes=tuple(route for route in configuration.routes if route.enabled),
        logic_summary=summary,
    )
