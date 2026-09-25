"""Tests for deletion-closed Plant ownership."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hydronicus_core.model import (
    Circuit,
    DeliveryRoute,
    PlantConfiguration,
    Pump,
    Source,
    SourceSelectionActuator,
    TemperatureSensorMetadata,
    Valve,
    Zone,
)
from hydronicus_core.ownership import (
    OwnershipError,
    PlantOwnership,
    RoomClosure,
    derive_ownership,
    owner_of,
    room_closure,
    validate_ownership,
    without_room,
)
from hydronicus_core.topology import compile_topology
from hypothesis import given, settings

from tests.core.strategies import plant_configurations


def _zone(zone_id: str) -> Zone:
    return Zone(zone_id, zone_id, 21.0, (TemperatureSensorMetadata(f"sensor.{zone_id}"),))


def _manifold() -> PlantConfiguration:
    """Two rooms with private loops and valves, one shared loop, and one pump."""
    return PlantConfiguration(
        id="plant",
        zones=(_zone("living"), _zone("bedroom")),
        valves=(
            Valve("living-valve", "Living valve", "switch.living_valve"),
            Valve("bedroom-valve", "Bedroom valve", "switch.bedroom_valve"),
            Valve("shared-valve", "Shared valve", "switch.shared_valve"),
            Valve("spare-valve", "Spare valve", "switch.spare_valve"),
        ),
        pumps=(Pump("pump", "Pump", "switch.pump"),),
        circuits=(
            Circuit("living-loop", "Living loop", ("living-valve", "shared-valve"), "pump"),
            Circuit("bedroom-loop", "Bedroom loop", ("bedroom-valve",), "pump"),
            Circuit("shared-loop", "Shared loop", ("shared-valve",), "pump"),
            Circuit("spare-loop", "Spare loop", ("spare-valve",), "pump"),
        ),
        routes=(
            DeliveryRoute("living-route", "living", "living-loop"),
            DeliveryRoute("bedroom-route", "bedroom", "bedroom-loop"),
            DeliveryRoute("living-shared", "living", "shared-loop"),
            DeliveryRoute("bedroom-shared", "bedroom", "shared-loop", enabled=False),
        ),
        sources=(Source("source", "Boiler"),),
        source_selector=SourceSelectionActuator("selector", "Selector"),
    )


MANIFOLD_OWNERSHIP = PlantOwnership(
    room_objects={
        "living-loop": "living",
        "living-valve": "living",
        "bedroom-loop": "bedroom",
        "bedroom-valve": "bedroom",
    }
)


def _rejects(configuration: PlantConfiguration, room_objects: dict[str, str]) -> tuple[str, ...]:
    with pytest.raises(OwnershipError) as caught:
        validate_ownership(configuration, PlantOwnership(room_objects))
    for object_id in caught.value.object_ids:
        assert object_id in str(caught.value)
    return caught.value.object_ids


def test_derive_ownership_makes_single_room_objects_private() -> None:
    """Circuits routed from one zone, and valves used only by them, are private."""
    assert derive_ownership(_manifold()) == MANIFOLD_OWNERSHIP


def test_derive_ownership_counts_disabled_routes() -> None:
    """A circuit whose routes all come from one zone is private, enabled or not."""
    configuration = replace(
        _manifold(),
        routes=tuple(route for route in _manifold().routes if route.id != "living-shared"),
    )

    assert derive_ownership(configuration).room_objects["shared-loop"] == "bedroom"
    assert "shared-valve" not in derive_ownership(configuration).room_objects


def test_derive_ownership_keeps_unrouted_and_unused_equipment_on_the_plant() -> None:
    """Nothing without a route or a user belongs to a room."""
    ownership = derive_ownership(_manifold())

    assert "spare-loop" not in ownership.room_objects
    assert "spare-valve" not in ownership.room_objects


def test_validate_ownership_accepts_the_derived_manifold() -> None:
    validate_ownership(_manifold(), MANIFOLD_OWNERSHIP)
    validate_ownership(_manifold(), PlantOwnership({}))


def test_r1_room_objects_must_map_circuits_or_valves_to_zones() -> None:
    manifold = _manifold()

    assert _rejects(manifold, {"pump": "living"}) == ("pump",)
    assert _rejects(manifold, {"living": "living"}) == ("living",)
    assert _rejects(manifold, {"missing": "living"}) == ("missing",)
    assert _rejects(manifold, {"living-loop": "pump", "living-valve": "living"}) == (
        "living-loop",
        "pump",
    )


def test_r3_plant_circuit_uses_only_plant_valves() -> None:
    assert _rejects(_manifold(), {"shared-valve": "living"}) == ("living-loop", "shared-valve")


def test_r4_room_circuit_uses_only_its_own_or_plant_valves() -> None:
    room_objects = dict(MANIFOLD_OWNERSHIP.room_objects, **{"shared-valve": "bedroom"})
    room_objects["shared-loop"] = "bedroom"

    assert _rejects(_manifold(), room_objects) == ("living-loop", "shared-valve")


def test_r5_route_targets_its_own_room_or_a_plant_circuit() -> None:
    room_objects = dict(MANIFOLD_OWNERSHIP.room_objects, **{"shared-loop": "living"})

    assert _rejects(_manifold(), room_objects) == ("bedroom-shared", "shared-loop")


def test_r6_private_objects_must_be_used_by_their_room() -> None:
    loose = replace(
        _manifold(), valves=(*_manifold().valves, Valve("loose-valve", "Loose", "switch.loose"))
    )

    assert _rejects(_manifold(), {"spare-loop": "living"}) == ("spare-loop",)
    assert _rejects(loose, {**MANIFOLD_OWNERSHIP.room_objects, "loose-valve": "living"}) == (
        "loose-valve",
    )


def test_owner_of_names_the_owning_zone_or_the_plant() -> None:
    manifold = _manifold()
    owners = {
        object_id: owner_of(manifold, MANIFOLD_OWNERSHIP, object_id)
        for object_id in (
            "living",
            "living-route",
            "living-shared",
            "living-loop",
            "living-valve",
            "bedroom-shared",
            "shared-loop",
            "shared-valve",
            "pump",
            "source",
            "selector",
        )
    }

    assert owners == {
        "living": "living",
        "living-route": "living",
        "living-shared": "living",
        "living-loop": "living",
        "living-valve": "living",
        "bedroom-shared": "bedroom",
        "shared-loop": None,
        "shared-valve": None,
        "pump": None,
        "source": None,
        "selector": None,
    }


def test_room_closure_holds_the_zone_its_routes_and_its_private_objects() -> None:
    assert room_closure(_manifold(), MANIFOLD_OWNERSHIP, "living") == RoomClosure(
        zone_id="living",
        route_ids=frozenset({"living-route", "living-shared"}),
        circuit_ids=frozenset({"living-loop"}),
        valve_ids=frozenset({"living-valve"}),
    )


def test_room_closure_rejects_an_unknown_zone() -> None:
    with pytest.raises(OwnershipError) as caught:
        room_closure(_manifold(), MANIFOLD_OWNERSHIP, "attic")

    assert caught.value.object_ids == ("attic",)


def test_without_room_removes_exactly_the_room_closure() -> None:
    configuration, ownership = without_room(_manifold(), MANIFOLD_OWNERSHIP, "living")

    assert [zone.id for zone in configuration.zones] == ["bedroom"]
    assert [valve.id for valve in configuration.valves] == [
        "bedroom-valve",
        "shared-valve",
        "spare-valve",
    ]
    assert [circuit.id for circuit in configuration.circuits] == [
        "bedroom-loop",
        "shared-loop",
        "spare-loop",
    ]
    assert [route.id for route in configuration.routes] == ["bedroom-route", "bedroom-shared"]
    assert configuration.pumps == _manifold().pumps
    assert configuration.sources == _manifold().sources
    assert configuration.source_selector == _manifold().source_selector
    assert ownership == PlantOwnership({"bedroom-loop": "bedroom", "bedroom-valve": "bedroom"})
    validate_ownership(configuration, ownership)
    compile_topology(configuration)


def test_without_every_room_leaves_plant_equipment_that_compiles() -> None:
    configuration, ownership = _manifold(), MANIFOLD_OWNERSHIP
    for zone_id in ("living", "bedroom"):
        configuration, ownership = without_room(configuration, ownership, zone_id)

    compiled = compile_topology(configuration)
    assert configuration.zones == ()
    assert ownership == PlantOwnership({})
    assert {warning.equipment_id for warning in compiled.warnings} >= {
        "shared-loop",
        "shared-valve",
        "pump",
    }


@settings(max_examples=200)
@given(plant_configurations())
def test_derived_ownership_always_validates(configuration: PlantConfiguration) -> None:
    """Migration can derive ownership for every Plant that compiles."""
    validate_ownership(configuration, derive_ownership(configuration))


@settings(max_examples=200)
@given(plant_configurations(min_zones=1))
def test_removing_any_room_leaves_a_valid_plant(configuration: PlantConfiguration) -> None:
    """Ownership is deletion-closed: every room can be removed on its own."""
    ownership = derive_ownership(configuration)
    for zone in configuration.zones:
        closure = room_closure(configuration, ownership, zone.id)
        remaining, remaining_ownership = without_room(configuration, ownership, zone.id)

        validate_ownership(remaining, remaining_ownership)
        compile_topology(remaining)
        kept_ids = {
            item.id
            for item in (
                *remaining.zones,
                *remaining.valves,
                *remaining.circuits,
                *remaining.routes,
            )
        }
        removed_ids = {zone.id} | closure.route_ids | closure.circuit_ids | closure.valve_ids
        assert kept_ids.isdisjoint(removed_ids)
        assert len(kept_ids) + len(removed_ids) == sum(
            len(collection)
            for collection in (
                configuration.zones,
                configuration.valves,
                configuration.circuits,
                configuration.routes,
            )
        )
