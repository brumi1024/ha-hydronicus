"""Deletion-closed ownership of Plant graph objects by rooms.

Every graph object belongs either to the Plant or to exactly one room, and a
room is one Comfort Zone. A zone owns itself, a Delivery Route belongs to the
room of its zone, and circuits and valves listed in ``room_objects`` are private
to a room. Everything else, including pumps, sources, and the source selector,
belongs to the Plant.

References only point toward the Plant, never into another room, so removing
one room's closure always leaves a graph that validates and compiles.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from .model import PlantConfiguration


class OwnershipError(ValueError):
    """An ownership assignment breaks a deletion-closed ownership rule."""

    def __init__(self, message: str, object_ids: tuple[str, ...]) -> None:
        self.object_ids = object_ids
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PlantOwnership:
    """Private circuits and valves, each mapped to the zone of its room."""

    room_objects: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class RoomClosure:
    """Everything that is removed together with one room."""

    zone_id: str
    route_ids: frozenset[str]
    circuit_ids: frozenset[str]
    valve_ids: frozenset[str]


def owner_of(
    configuration: PlantConfiguration, ownership: PlantOwnership, object_id: str
) -> str | None:
    """Return the zone id of the room owning an object, or ``None`` for the Plant."""
    if any(zone.id == object_id for zone in configuration.zones):
        return object_id
    for route in configuration.routes:
        if route.id == object_id:
            return route.zone_id
    return ownership.room_objects.get(object_id)


def validate_ownership(configuration: PlantConfiguration, ownership: PlantOwnership) -> None:
    """Raise ``OwnershipError`` unless ownership follows every deletion-closed rule."""
    zone_ids = {zone.id for zone in configuration.zones}
    circuit_ids = {circuit.id for circuit in configuration.circuits}
    valve_ids = {valve.id for valve in configuration.valves}
    room_objects = ownership.room_objects

    # R1: only circuits and valves are private, and each to an existing zone.
    for object_id, zone_id in room_objects.items():
        if object_id not in circuit_ids | valve_ids:
            raise OwnershipError(
                f"Only circuits and valves can belong to a room, not {object_id}.", (object_id,)
            )
        if zone_id not in zone_ids:
            raise OwnershipError(
                f"Private object {object_id} belongs to {zone_id}, which is not a zone.",
                (object_id, zone_id),
            )

    for circuit in configuration.circuits:
        circuit_owner = room_objects.get(circuit.id)
        for valve_id in circuit.valve_ids:
            valve_owner = room_objects.get(valve_id)
            if valve_owner is None or valve_owner == circuit_owner:
                continue
            # R3: a Plant circuit uses only Plant valves.
            if circuit_owner is None:
                raise OwnershipError(
                    f"Plant circuit {circuit.id} uses valve {valve_id}, which is private to "
                    f"room {valve_owner}.",
                    (circuit.id, valve_id),
                )
            # R4: a room circuit uses only its own room's valves or Plant valves.
            raise OwnershipError(
                f"Circuit {circuit.id} of room {circuit_owner} uses valve {valve_id}, which is "
                f"private to room {valve_owner}.",
                (circuit.id, valve_id),
            )

    # R5: a route targets a circuit of its own room or of the Plant.
    for route in configuration.routes:
        circuit_owner = room_objects.get(route.circuit_id)
        if circuit_owner is not None and circuit_owner != route.zone_id:
            raise OwnershipError(
                f"Route {route.id} from zone {route.zone_id} targets circuit {route.circuit_id}, "
                f"which is private to room {circuit_owner}.",
                (route.id, route.circuit_id),
            )

    # R6: every private object is used by its own room.
    for circuit in configuration.circuits:
        circuit_owner = room_objects.get(circuit.id)
        if circuit_owner is not None and not any(
            route.circuit_id == circuit.id and route.zone_id == circuit_owner
            for route in configuration.routes
        ):
            raise OwnershipError(
                f"Circuit {circuit.id} is private to room {circuit_owner} but has no route "
                "from it.",
                (circuit.id,),
            )
    for valve_id in sorted(valve_ids):
        valve_owner = room_objects.get(valve_id)
        if valve_owner is not None and not any(
            valve_id in circuit.valve_ids and room_objects.get(circuit.id) == valve_owner
            for circuit in configuration.circuits
        ):
            raise OwnershipError(
                f"Valve {valve_id} is private to room {valve_owner} but no circuit of that room "
                "uses it.",
                (valve_id,),
            )


def derive_ownership(configuration: PlantConfiguration) -> PlantOwnership:
    """Make everything private that only one room uses.

    A circuit is private to zone Z when every route targeting it comes from Z,
    and a valve is private to Z when every circuit using it is private to Z.
    """
    room_objects: dict[str, str] = {}
    for circuit in configuration.circuits:
        route_zones = {
            route.zone_id for route in configuration.routes if route.circuit_id == circuit.id
        }
        if len(route_zones) == 1:
            room_objects[circuit.id] = next(iter(route_zones))
    for valve in configuration.valves:
        users = [circuit.id for circuit in configuration.circuits if valve.id in circuit.valve_ids]
        user_rooms = {room_objects.get(circuit_id) for circuit_id in users}
        if len(user_rooms) == 1 and (room := next(iter(user_rooms))) is not None:
            room_objects[valve.id] = room
    return PlantOwnership(room_objects=room_objects)


def room_closure(
    configuration: PlantConfiguration, ownership: PlantOwnership, zone_id: str
) -> RoomClosure:
    """Return the objects removed together with one room."""
    if not any(zone.id == zone_id for zone in configuration.zones):
        raise OwnershipError(f"Zone {zone_id} is not part of the Plant.", (zone_id,))
    private_ids = {
        object_id for object_id, owner in ownership.room_objects.items() if owner == zone_id
    }
    return RoomClosure(
        zone_id=zone_id,
        route_ids=frozenset(route.id for route in configuration.routes if route.zone_id == zone_id),
        circuit_ids=frozenset(
            circuit.id for circuit in configuration.circuits if circuit.id in private_ids
        ),
        valve_ids=frozenset(valve.id for valve in configuration.valves if valve.id in private_ids),
    )


def without_room(
    configuration: PlantConfiguration, ownership: PlantOwnership, zone_id: str
) -> tuple[PlantConfiguration, PlantOwnership]:
    """Remove one room's closure, keeping the order of everything that remains.

    With valid ownership nothing outside the closure references it, so the
    remaining graph still validates and compiles.
    """
    closure = room_closure(configuration, ownership, zone_id)
    remaining = replace(
        configuration,
        zones=tuple(zone for zone in configuration.zones if zone.id != zone_id),
        valves=tuple(valve for valve in configuration.valves if valve.id not in closure.valve_ids),
        circuits=tuple(
            circuit for circuit in configuration.circuits if circuit.id not in closure.circuit_ids
        ),
        routes=tuple(route for route in configuration.routes if route.id not in closure.route_ids),
    )
    return remaining, PlantOwnership(
        room_objects={
            object_id: owner
            for object_id, owner in ownership.room_objects.items()
            if owner != zone_id
        }
    )
