"""Hypothesis strategies for valid Plant configurations of many shapes.

The strategies draw stored version 4 topology records, the form persisted in a
config entry, and decode them with the real decoder, so tests can use either the
stored records or the typed configuration. Every drawn Plant compiles.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid5

from hydronicus_core.configuration import plant_configuration_from_entry_data
from hydronicus_core.model import PlantConfiguration
from hypothesis import strategies as st

PLANT_ID = "00000000-0000-4000-8000-00000000a000"
_NAMESPACE = UUID(PLANT_ID)

# Names repeat and carry characters a slug must replace, on purpose.
_NAMES = ("Living room", "Bedroom", "Bedroom", "2nd floor", "Kid's room", "Bad", "Ärkély")


def object_id(kind: str, index: int) -> str:
    """Return the deterministic UUID of one generated object."""
    return str(uuid5(_NAMESPACE, f"{kind}:{index}"))


_AREAS = ("living_room", "kitchen", "hall", "bedroom")


def _area_settings() -> st.SearchStrategy[dict[str, Any]]:
    """Draw area settings, each left out or set to a value other than its default."""
    return st.fixed_dictionaries(
        {},
        optional={
            "required": st.just(True),
            "weight": st.sampled_from((0.5, 2.0)),
            "max_age_seconds": st.sampled_from((600.0, 3600.0)),
        },
    )


def _names(draw: st.DrawFn, count: int) -> list[str]:
    return [draw(st.sampled_from(_NAMES)) for _ in range(count)]


def _indices(maximum: int, *, min_size: int, max_size: int) -> st.SearchStrategy[list[int]]:
    """Draw distinct indices below maximum, in drawn order."""
    return st.lists(
        st.integers(min_value=0, max_value=maximum - 1),
        min_size=min_size,
        max_size=min(max_size, maximum),
        unique=True,
    )


@st.composite
def stored_plants(draw: st.DrawFn, *, min_zones: int = 0, max_zones: int = 4) -> dict[str, Any]:
    """Draw config entry data holding a valid stored topology.

    Zones route to one or more circuits, so circuits are private to one zone or
    shared by several. Circuits draw their valves and pump from small pools, so
    valves and pumps are shared by several circuits or by none. Some circuits
    have only disabled routes or no route at all, which leaves them and possibly
    their equipment unused.
    """
    zone_count = draw(st.integers(min_value=min_zones, max_value=max_zones))
    circuit_count = draw(st.integers(min_value=1 if zone_count else 0, max_value=5))
    valve_count = draw(st.integers(min_value=1 if circuit_count else 0, max_value=6))
    pump_count = draw(st.integers(min_value=1 if circuit_count else 0, max_value=3))

    zones: list[dict[str, Any]] = []
    for index, name in enumerate(_names(draw, zone_count)):
        external = draw(st.booleans())
        # Areas repeat across zones, since several zones may cover one area.
        areas = [
            {"area_id": area_id, **draw(_area_settings())}
            for area_id in draw(st.lists(st.sampled_from(_AREAS), unique=True, max_size=3))
        ]
        # A Hydronicus thermostat needs a temperature sensor or an area.
        temperature = not (external or areas) or draw(st.booleans())
        zone: dict[str, Any] = {"id": object_id("zone", index), "name": name}
        zone["thermostat"] = (
            {"kind": "external_climate", "entity_id": f"climate.zone_{index}"}
            if external
            else {"kind": "hydronicus"}
        )
        if areas:
            zone["areas"] = areas
        if temperature:
            zone["temperature_sensor_metadata"] = [{"entity_id": f"sensor.zone_{index}_temp"}]
        if draw(st.booleans()):
            zone["humidity_sensor_metadata"] = [{"entity_id": f"sensor.zone_{index}_humidity"}]
        zones.append(zone)

    valves = [
        {"id": object_id("valve", index), "name": name, "entity_id": f"switch.valve_{index}"}
        for index, name in enumerate(_names(draw, valve_count))
    ]
    pumps = [
        {"id": object_id("pump", index), "name": name, "entity_id": f"switch.pump_{index}"}
        for index, name in enumerate(_names(draw, pump_count))
    ]
    circuits = [
        {
            "id": object_id("circuit", index),
            "name": name,
            "valve_ids": [
                object_id("valve", valve)
                for valve in draw(_indices(valve_count, min_size=1, max_size=3))
            ],
            "pump_id": object_id("pump", draw(st.integers(0, pump_count - 1))),
        }
        for index, name in enumerate(_names(draw, circuit_count))
    ]

    routes: list[dict[str, Any]] = []
    served: dict[int, set[int]] = {circuit: set() for circuit in range(circuit_count)}
    for zone_index in range(zone_count):
        enabled = draw(_indices(circuit_count, min_size=1, max_size=3))
        remaining = [circuit for circuit in range(circuit_count) if circuit not in enabled]
        disabled = (
            draw(st.lists(st.sampled_from(remaining), unique=True, max_size=1))
            if (remaining)
            else []
        )
        for circuit_index in enabled:
            served[circuit_index].add(zone_index)
        for circuit_index, is_enabled in (
            *((circuit, True) for circuit in enabled),
            *((circuit, False) for circuit in disabled),
        ):
            route = {
                "id": object_id("route", len(routes)),
                "zone_id": object_id("zone", zone_index),
                "circuit_id": object_id("circuit", circuit_index),
            }
            if not is_enabled:
                route["enabled"] = False
            routes.append(route)

    # Cooling needs temperature and humidity observations in every served zone,
    # and an area counts as both.
    for circuit_index, circuit in enumerate(circuits):
        observed = all(
            "areas" in zones[zone]
            or (
                "temperature_sensor_metadata" in zones[zone]
                and "humidity_sensor_metadata" in zones[zone]
            )
            for zone in served[circuit_index]
        )
        if observed and draw(st.booleans()):
            circuit["cooling_enabled"] = True
            circuit["supply_temperature_sensor"] = f"sensor.circuit_{circuit_index}_supply"

    topology: dict[str, Any] = {
        "zones": zones,
        "valves": valves,
        "pumps": pumps,
        "circuits": circuits,
        "routes": routes,
    }
    source_count = draw(st.integers(min_value=0, max_value=2))
    if source_count:
        topology["sources"] = [
            {
                "id": object_id("source", index),
                "name": name,
                "priority": index,
                **(
                    {"source_demand_entity": f"switch.source_{index}"}
                    if draw(st.booleans())
                    else {}
                ),
            }
            for index, name in enumerate(_names(draw, source_count))
        ]
        if draw(st.booleans()):
            topology["source_selector"] = {
                "id": object_id("source_selector", 0),
                "name": "Source selector",
                "entity_id": "select.source_selector",
            }
    return {"plant_id": PLANT_ID, "topology": topology}


def plant_configurations(
    *, min_zones: int = 0, max_zones: int = 4
) -> st.SearchStrategy[PlantConfiguration]:
    """Draw decoded configurations of valid stored Plants."""
    return stored_plants(min_zones=min_zones, max_zones=max_zones).map(
        plant_configuration_from_entry_data
    )
