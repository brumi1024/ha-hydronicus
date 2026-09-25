"""Builders for version 4 Plant config entries with zone and source subentries.

Tests describe a Plant by its stored topology. These builders derive zone
ownership, give every zone a zone handle and every source a source handle, and
create a ``MockConfigEntry`` whose subentries match, with deterministic subentry
ids so tests can name them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_NAME,
    CONF_PLANT_ID,
    CONF_SUBENTRY_OBJECTS,
    CONF_TOPOLOGY,
    CONF_ZONE_OBJECTS,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SUBENTRY_TYPE_SOURCE,
    SUBENTRY_TYPE_ZONE,
)
from custom_components.hydronicus.core.legacy.configuration import (
    plant_configuration_from_entry_data,
)
from custom_components.hydronicus.core.legacy.ownership import derive_ownership
from custom_components.hydronicus.entry_configuration import (
    authorize_outputs,
    new_plant_data,
    subentries_for,
)

PLANT_ID = "00000000-0000-4000-8000-000000000001"


def subentry_id_for(object_id: str) -> str:
    """Return the deterministic subentry id these builders give an object's handle."""
    return f"handle-{object_id}"


def with_zone_handles(data: Mapping[str, Any], *, source_handles: bool = True) -> dict[str, Any]:
    """Add derived zone ownership and handles to stored data that has none.

    Everything else, including Dry run and output authorization, stays as given,
    so a live test Plant stays live.
    """
    updated = deepcopy(dict(data))
    topology = updated.get(CONF_TOPOLOGY, {})
    if CONF_ZONE_OBJECTS not in updated:
        configuration = plant_configuration_from_entry_data(updated)
        updated[CONF_ZONE_OBJECTS] = dict(derive_ownership(configuration).zone_objects)
    if CONF_SUBENTRY_OBJECTS not in updated or not updated[CONF_SUBENTRY_OBJECTS]:
        handles = {str(zone["id"]): SUBENTRY_TYPE_ZONE for zone in topology.get("zones", [])}
        if source_handles:
            handles.update(
                {str(source["id"]): SUBENTRY_TYPE_SOURCE for source in topology.get("sources", [])}
            )
        updated[CONF_SUBENTRY_OBJECTS] = handles
    return updated


def plant_data(
    topology: Mapping[str, Any],
    *,
    name: str = "Hydronic plant",
    plant_id: str = PLANT_ID,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Return validated version 4 data with derived ownership, authorized when live."""
    configuration = plant_configuration_from_entry_data(
        {CONF_PLANT_ID: plant_id, CONF_TOPOLOGY: topology}
    )
    data = new_plant_data(
        name=name,
        plant_id=plant_id,
        topology=topology,
        ownership=derive_ownership(configuration),
    )
    return data if dry_run else authorize_outputs(data)


def subentries_data(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return ``MockConfigEntry`` subentries for every handle of stored data."""
    return [
        {**handle, "subentry_id": subentry_id_for(handle["unique_id"])}
        for handle in subentries_for(data)
    ]


def plant_entry(
    data: Mapping[str, Any],
    *,
    title: str | None = None,
    source_handles: bool = True,
    **kwargs: Any,
) -> MockConfigEntry:
    """Return a version 4 entry for stored data, adding zone handles when it has none."""
    stored = with_zone_handles(data, source_handles=source_handles)
    return MockConfigEntry(
        domain=DOMAIN,
        title=title if title is not None else str(stored.get(CONF_NAME, "Hydronic plant")),
        data=stored,
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        subentries_data=subentries_data(stored),
        **kwargs,
    )


@dataclass(frozen=True, slots=True)
class ZoneIds:
    """The stored ids of one zone built by ``manifold_topology``."""

    zone_id: str
    circuit_id: str
    valve_id: str
    route_id: str
    temperature_sensor: str
    valve_entity: str


def _uuid(group: int, index: int) -> str:
    return f"00000000-0000-4000-8000-{group:04d}{index:08d}"


def manifold_zones(names: Sequence[str]) -> list[ZoneIds]:
    """Return deterministic ids and entities for zones on one manifold."""
    zones = []
    for index, name in enumerate(names, 1):
        slug = name.lower().replace(" ", "_")
        zones.append(
            ZoneIds(
                zone_id=_uuid(1, index),
                circuit_id=_uuid(2, index),
                valve_id=_uuid(3, index),
                route_id=_uuid(4, index),
                temperature_sensor=f"sensor.{slug}_temperature",
                valve_entity=f"switch.{slug}_valve",
            )
        )
    return zones


MANIFOLD_PUMP_ID = _uuid(5, 1)
MANIFOLD_PUMP_ENTITY = "switch.manifold_pump"


def manifold_topology(
    names: Sequence[str] = ("Living room", "Bedroom"),
    *,
    sources: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Return zones that each own a loop and valve, sharing one Plant pump."""
    zones = manifold_zones(names)
    return {
        "zones": [
            {
                "id": zone.zone_id,
                "name": name,
                "thermostat": {"kind": "hydronicus", "initial_target_temperature": 21.0},
                "temperature_sensor_metadata": [{"entity_id": zone.temperature_sensor}],
            }
            for name, zone in zip(names, zones, strict=True)
        ],
        "valves": [
            {
                "id": zone.valve_id,
                "name": f"{name} loop valve",
                "entity_id": zone.valve_entity,
                "opening_time_seconds": 0.0,
            }
            for name, zone in zip(names, zones, strict=True)
        ],
        "pumps": [
            {
                "id": MANIFOLD_PUMP_ID,
                "name": "Manifold pump",
                "entity_id": MANIFOLD_PUMP_ENTITY,
                "overrun_seconds": 0.0,
            }
        ],
        "circuits": [
            {
                "id": zone.circuit_id,
                "name": f"{name} loop",
                "valve_ids": [zone.valve_id],
                "pump_id": MANIFOLD_PUMP_ID,
            }
            for name, zone in zip(names, zones, strict=True)
        ],
        "routes": [
            {"id": zone.route_id, "zone_id": zone.zone_id, "circuit_id": zone.circuit_id}
            for zone in zones
        ],
        "sources": [deepcopy(dict(source)) for source in sources],
    }


def manifold_entry(
    names: Sequence[str] = ("Living room", "Bedroom"),
    *,
    dry_run: bool = True,
    sources: Iterable[Mapping[str, Any]] = (),
    **kwargs: Any,
) -> MockConfigEntry:
    """Return a version 4 manifold entry with one zone subentry per zone."""
    data = plant_data(manifold_topology(names, sources=sources), dry_run=dry_run)
    return plant_entry(data, **kwargs)


def zone_subentry(entry: MockConfigEntry, zone_id: str) -> Any:
    """Return the zone subentry of one zone."""
    return next(
        subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_ZONE and subentry.unique_id == zone_id
    )


def is_dry_run(entry: MockConfigEntry) -> bool:
    """Return the stored Dry run setting of an entry."""
    return bool(entry.data.get(CONF_DRY_RUN, True))
