"""Tests for deletion-closed Plant ownership."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hydronicus_core.legacy.model import (
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
from hydronicus_core.legacy.ownership import (
    OwnershipError,
    PlantOwnership,
    ZoneClosure,
    derive_ownership,
    owner_of,
    validate_ownership,
    without_zone,
    zone_closure,
)
from hydronicus_core.legacy.topology import compile_topology
from hypothesis import given, settings

from tests.core.legacy.strategies import plant_configurations


def _zone(zone_id: str) -> Zone:
    return Zone(zone_id, zone_id, 21.0, (TemperatureSensorMetadata(f"sensor.{zone_id}"),))


def _manifold() -> PlantConfiguration:
    """Two zones with private loops and valves, one shared loop, and one pump."""
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
    zone_objects={
        "living-loop": "living",
        "living-valve": "living",
        "bedroom-loop": "bedroom",
        "bedroom-valve": "bedroom",
    }
)


def _rejects(configuration: PlantConfiguration, zone_objects: dict[str, str]) -> tuple[str, ...]:
    with pytest.raises(OwnershipError) as caught:
        validate_ownership(configuration, PlantOwnership(zone_objects))
    for object_id in caught.value.object_ids:
        assert object_id in str(caught.value)
    return caught.value.object_ids


def test_derive_ownership_makes_single_zone_objects_private() -> None:
    """Circuits routed from one zone, and valves used only by them, are private."""
    assert derive_ownership(_manifold()) == MANIFOLD_OWNERSHIP


def test_derive_ownership_counts_disabled_routes() -> None:
    """A circuit whose routes all come from one zone is private, enabled or not."""
    configuration = replace(
        _manifold(),
        routes=tuple(route for route in _manifold().routes if route.id != "living-shared"),
    )

    assert derive_ownership(configuration).zone_objects["shared-loop"] == "bedroom"
    assert "shared-valve" not in derive_ownership(configuration).zone_objects


def test_derive_ownership_keeps_unrouted_and_unused_equipment_on_the_plant() -> None:
    """Nothing without a route or a user belongs to a zone."""
    ownership = derive_ownership(_manifold())

    assert "spare-loop" not in ownership.zone_objects
    assert "spare-valve" not in ownership.zone_objects


def test_validate_ownership_accepts_the_derived_manifold() -> None:
    validate_ownership(_manifold(), MANIFOLD_OWNERSHIP)
    validate_ownership(_manifold(), PlantOwnership({}))


def test_r1_zone_objects_must_map_circuits_or_valves_to_zones() -> None:
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


def test_r4_zone_circuit_uses_only_its_own_or_plant_valves() -> None:
    zone_objects = dict(MANIFOLD_OWNERSHIP.zone_objects, **{"shared-valve": "bedroom"})
    zone_objects["shared-loop"] = "bedroom"

    assert _rejects(_manifold(), zone_objects) == ("living-loop", "shared-valve")


def test_r5_route_targets_its_own_zone_or_a_plant_circuit() -> None:
    zone_objects = dict(MANIFOLD_OWNERSHIP.zone_objects, **{"shared-loop": "living"})

    assert _rejects(_manifold(), zone_objects) == ("bedroom-shared", "shared-loop")


def test_r6_private_objects_must_be_used_by_their_zone() -> None:
    loose = replace(
        _manifold(), valves=(*_manifold().valves, Valve("loose-valve", "Loose", "switch.loose"))
    )

    assert _rejects(_manifold(), {"spare-loop": "living"}) == ("spare-loop",)
    assert _rejects(loose, {**MANIFOLD_OWNERSHIP.zone_objects, "loose-valve": "living"}) == (
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


def test_zone_closure_holds_the_zone_its_routes_and_its_private_objects() -> None:
    assert zone_closure(_manifold(), MANIFOLD_OWNERSHIP, "living") == ZoneClosure(
        zone_id="living",
        route_ids=frozenset({"living-route", "living-shared"}),
        circuit_ids=frozenset({"living-loop"}),
        valve_ids=frozenset({"living-valve"}),
    )


def test_zone_closure_rejects_an_unknown_zone() -> None:
    with pytest.raises(OwnershipError) as caught:
        zone_closure(_manifold(), MANIFOLD_OWNERSHIP, "attic")

    assert caught.value.object_ids == ("attic",)


def test_without_zone_removes_exactly_the_zone_closure() -> None:
    configuration, ownership = without_zone(_manifold(), MANIFOLD_OWNERSHIP, "living")

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


def test_without_every_zone_leaves_plant_equipment_that_compiles() -> None:
    configuration, ownership = _manifold(), MANIFOLD_OWNERSHIP
    for zone_id in ("living", "bedroom"):
        configuration, ownership = without_zone(configuration, ownership, zone_id)

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
    """Ownership can be derived for every Plant that compiles."""
    validate_ownership(configuration, derive_ownership(configuration))


@settings(max_examples=200)
@given(plant_configurations(min_zones=1))
def test_removing_any_zone_leaves_a_valid_plant(configuration: PlantConfiguration) -> None:
    """Ownership is deletion-closed: every zone can be removed on its own."""
    ownership = derive_ownership(configuration)
    for zone in configuration.zones:
        closure = zone_closure(configuration, ownership, zone.id)
        remaining, remaining_ownership = without_zone(configuration, ownership, zone.id)

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
