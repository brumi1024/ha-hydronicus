"""Compose config-entry and subentry data into one effective plant topology."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from .const import (
    ACTUATOR_KIND_VALVE,
    CONF_ACTUATOR_KIND,
    CONF_CIRCUIT_IDS,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_OPENING_TIME,
    SUBENTRY_TYPE_ACTUATOR,
)
from .core.configuration import StoredTopologyError, plant_configuration_from_entry_data
from .core.model import PlantConfiguration, Valve


@dataclass(frozen=True, slots=True)
class EffectivePlantConfiguration:
    """A fully composed plant and its Home Assistant subentry ownership map."""

    configuration: PlantConfiguration
    actuator_subentry_ids: Mapping[str, str]


def _required(data: Mapping[str, Any], key: str) -> Any:
    try:
        return data[key]
    except KeyError as error:
        raise StoredTopologyError(
            f"Actuator subentry is missing required field {key!r}."
        ) from error


def _uuid(data: Mapping[str, Any], key: str) -> str:
    value = str(_required(data, key))
    try:
        return str(UUID(value))
    except ValueError as error:
        raise StoredTopologyError(
            f"Actuator subentry field {key!r} must be a UUID."
        ) from error


def _circuit_ids(data: Mapping[str, Any]) -> tuple[str, ...]:
    value = _required(data, CONF_CIRCUIT_IDS)
    if not isinstance(value, list) or not value:
        raise StoredTopologyError("Actuator subentry requires at least one circuit id.")
    try:
        return tuple(str(UUID(str(item))) for item in value)
    except ValueError as error:
        raise StoredTopologyError(
            "Actuator subentry circuit ids must be UUIDs."
        ) from error


def effective_plant_configuration(
    entry: Any,
    *,
    proposed_actuators: Sequence[Mapping[str, Any]] = (),
    excluded_subentry_id: str | None = None,
) -> EffectivePlantConfiguration:
    """Build an atomic effective topology from embedded data and actuator subentries."""
    base = plant_configuration_from_entry_data(entry.data)
    actuator_records: list[tuple[str | None, Mapping[str, Any]]] = []
    for subentry in getattr(entry, "subentries", {}).values():
        if (
            subentry.subentry_type == SUBENTRY_TYPE_ACTUATOR
            and subentry.subentry_id != excluded_subentry_id
        ):
            actuator_records.append((subentry.subentry_id, subentry.data))
    actuator_records.extend((None, data) for data in proposed_actuators)

    valves = list(base.valves)
    circuits = list(base.circuits)
    known_circuit_ids = {circuit.id for circuit in circuits}
    actuator_subentry_ids: dict[str, str] = {}
    for subentry_id, data in actuator_records:
        kind = str(_required(data, CONF_ACTUATOR_KIND))
        if kind != ACTUATOR_KIND_VALVE:
            raise StoredTopologyError(f"Unsupported actuator subentry kind {kind!r}.")
        actuator_id = _uuid(data, "id")
        selected_circuit_ids = _circuit_ids(data)
        unknown_circuit_ids = sorted(set(selected_circuit_ids) - known_circuit_ids)
        if unknown_circuit_ids:
            raise StoredTopologyError(
                "Actuator subentry references unknown circuits: "
                + ", ".join(unknown_circuit_ids)
                + "."
            )
        try:
            opening_time_seconds = float(_required(data, CONF_OPENING_TIME))
        except (TypeError, ValueError) as error:
            raise StoredTopologyError(
                "Actuator subentry opening time must be numeric."
            ) from error
        valves.append(
            Valve(
                id=actuator_id,
                name=str(_required(data, CONF_NAME)),
                entity_id=str(_required(data, CONF_ENTITY_ID)),
                opening_time_seconds=opening_time_seconds,
            )
        )
        selected = set(selected_circuit_ids)
        circuits = [
            replace(circuit, valve_ids=(*circuit.valve_ids, actuator_id))
            if circuit.id in selected
            else circuit
            for circuit in circuits
        ]
        if subentry_id is not None:
            actuator_subentry_ids[actuator_id] = subentry_id

    return EffectivePlantConfiguration(
        configuration=replace(base, valves=tuple(valves), circuits=tuple(circuits)),
        actuator_subentry_ids=actuator_subentry_ids,
    )
