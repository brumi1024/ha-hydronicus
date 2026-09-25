"""Tests for the plant file format: import, export, and canonical round trips."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import pytest
import yaml
from hydronicus_core.configuration import plant_configuration_from_entry_data
from hydronicus_core.ownership import PlantOwnership, derive_ownership, validate_ownership
from hydronicus_core.plant_document import (
    PLANT_FILE_FORMAT,
    ImportedPlant,
    PlantDocumentError,
    export_plant_document,
    import_plant_document,
)
from hypothesis import given, settings

from tests.core.strategies import stored_plants

FIXTURES = Path(__file__).parents[1] / "fixtures" / "plant_files"
PLANT_ID = "00000000-0000-4000-8000-0000000000aa"
OTHER_PLANT_ID = "00000000-0000-4000-8000-0000000000bb"
NAMESPACE = UUID(PLANT_ID)


def _load(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _derived(kind: str, slug: str) -> str:
    return str(uuid5(NAMESPACE, f"{kind}:{slug}"))


def _by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {record["id"]: record for record in records}


def _minimal(**zone: Any) -> dict[str, Any]:
    """Return a one-zone document, with zone keys replaced by the arguments."""
    bedroom: dict[str, Any] = {
        "temperature_sensors": ["sensor.bedroom_temperature"],
        "loops": {"bedroom_loop": {"valves": ["switch.bedroom_valve"], "pump": "pump"}},
    }
    bedroom.update(zone)
    return {
        "hydronicus": 1,
        "name": "Home",
        "pumps": {"pump": "switch.pump"},
        "zones": {"bedroom": bedroom},
    }


def _error_path(document: Mapping[str, Any], plant_id: str = PLANT_ID) -> str:
    with pytest.raises(PlantDocumentError) as caught:
        import_plant_document(document, plant_id=plant_id)
    return caught.value.path


def _reexport(imported: ImportedPlant) -> dict[str, Any]:
    return export_plant_document(
        name=imported.name,
        plant_id=imported.plant_id,
        topology=imported.topology,
        ownership=imported.ownership,
    )


# Positive fixtures


POSITIVE_FIXTURES = (
    "single_zone.yaml",
    "manifold.yaml",
    "two_pumps.yaml",
    "shared_loop.yaml",
    "private_loops_shared_valve.yaml",
    "external_thermostat.yaml",
    "cooling.yaml",
    "sources.yaml",
    "shorthand.yaml",
)


@pytest.mark.parametrize("fixture", POSITIVE_FIXTURES)
def test_fixture_imports_and_reexports_canonically(fixture: str) -> None:
    imported = import_plant_document(_load(fixture), plant_id=PLANT_ID)

    configuration = plant_configuration_from_entry_data(
        {"plant_id": imported.plant_id, "topology": imported.topology}
    )
    validate_ownership(configuration, imported.ownership)
    assert imported.compiled.id == PLANT_ID
    canonical = _reexport(imported)
    again = import_plant_document(copy.deepcopy(canonical), plant_id=OTHER_PLANT_ID)
    assert again.plant_id == PLANT_ID
    assert _collections(again.topology) == _collections(imported.topology)
    assert again.ownership == imported.ownership
    assert _reexport(again) == canonical


def test_manifold_shares_one_pump_across_three_private_loops() -> None:
    imported = import_plant_document(_load("manifold.yaml"), plant_id=PLANT_ID)

    pump_id = _derived("pump", "manifold_pump")
    assert [pump["id"] for pump in imported.topology["pumps"]] == [pump_id]
    assert {circuit["pump_id"] for circuit in imported.topology["circuits"]} == {pump_id}
    assert imported.ownership.zone_objects == {
        _derived("circuit", "living_loop"): _derived("zone", "living_room"),
        _derived("valve", "living_loop_valve"): _derived("zone", "living_room"),
        _derived("circuit", "bedroom_loop"): _derived("zone", "bedroom"),
        _derived("valve", "bedroom_loop_valve"): _derived("zone", "bedroom"),
        _derived("circuit", "office_loop"): _derived("zone", "office"),
        _derived("valve", "office_loop_valve"): _derived("zone", "office"),
    }
    assert {warning.code for warning in imported.compiled.warnings} == {
        "shared_pump_limits_independent_control"
    }


def test_two_pumps_keep_stored_pump_fields() -> None:
    imported = import_plant_document(_load("two_pumps.yaml"), plant_id=PLANT_ID)

    assert imported.topology["pumps"] == [
        {
            "id": _derived("pump", "ground_pump"),
            "name": "Ground pump",
            "entity_id": "switch.ground_pump",
            "overrun_seconds": 60,
        },
        {
            "id": _derived("pump", "upper_pump"),
            "name": "Upper pump",
            "entity_id": "switch.upper_pump",
            "power_feedback_entity": "sensor.upper_pump_power",
        },
    ]


def test_shared_loop_and_shared_valve_serve_two_zones() -> None:
    imported = import_plant_document(_load("shared_loop.yaml"), plant_id=PLANT_ID)

    hall_loop = _derived("circuit", "hall_loop")
    hall_valve = _derived("valve", "hall_valve")
    assert hall_loop not in imported.ownership.zone_objects
    assert hall_valve not in imported.ownership.zone_objects
    circuits = _by_id(imported.topology["circuits"])
    assert circuits[_derived("circuit", "bedroom_loop")]["valve_ids"] == [
        _derived("valve", "bedroom_loop_valve"),
        hall_valve,
    ]
    assert imported.topology["routes"] == [
        {
            "id": _derived("route", "living_room:hall_loop"),
            "zone_id": _derived("zone", "living_room"),
            "circuit_id": hall_loop,
        },
        {
            "id": _derived("route", "bedroom:hall_loop"),
            "zone_id": _derived("zone", "bedroom"),
            "circuit_id": hall_loop,
            "enabled": False,
        },
        {
            "id": _derived("route", "bedroom:bedroom_loop"),
            "zone_id": _derived("zone", "bedroom"),
            "circuit_id": _derived("circuit", "bedroom_loop"),
        },
    ]


def test_zone_with_two_private_loops_sharing_a_private_valve() -> None:
    imported = import_plant_document(_load("private_loops_shared_valve.yaml"), plant_id=PLANT_ID)

    hall = _derived("zone", "hall")
    shared_valve = _derived("valve", "hall_zone_valve")
    assert imported.ownership.zone_objects[shared_valve] == hall
    circuits = _by_id(imported.topology["circuits"])
    for loop in ("north_loop", "south_loop"):
        assert circuits[_derived("circuit", loop)]["valve_ids"][0] == shared_valve
        assert imported.ownership.zone_objects[_derived("circuit", loop)] == hall


def test_external_thermostat_short_and_long_forms() -> None:
    imported = import_plant_document(_load("external_thermostat.yaml"), plant_id=PLANT_ID)

    bedroom, study = imported.topology["zones"]
    assert bedroom == {
        "id": _derived("zone", "bedroom"),
        "name": "Bedroom",
        "thermostat": {"kind": "external_climate", "entity_id": "climate.bedroom"},
    }
    assert study["thermostat"] == {"kind": "external_climate", "entity_id": "climate.study"}
    assert study["temperature_sensor_metadata"] == [{"entity_id": "sensor.study_temperature"}]


def test_cooling_loop_keeps_stored_fields_and_sensor_records() -> None:
    imported = import_plant_document(_load("cooling.yaml"), plant_id=PLANT_ID)

    (zone,) = imported.topology["zones"]
    assert zone["thermostat"] == {
        "kind": "hydronicus",
        "initial_target_temperature": 22,
        "cooling_start_delta": 0.5,
    }
    assert zone["temperature_sensor_metadata"] == [
        {"entity_id": "sensor.living_temperature", "weight": 2},
        {"entity_id": "sensor.living_temperature_2"},
    ]
    assert zone["humidity_sensor_metadata"] == [{"entity_id": "sensor.living_humidity"}]
    (circuit,) = imported.topology["circuits"]
    assert circuit == {
        "id": _derived("circuit", "living_loop"),
        "name": "Living loop",
        "valve_ids": [_derived("valve", "living_loop_valve")],
        "pump_id": _derived("pump", "pump"),
        "cooling_enabled": True,
        "supply_temperature_sensor": "sensor.living_supply",
        "condensation_margin": 3,
    }


def test_sources_and_source_selector() -> None:
    imported = import_plant_document(_load("sources.yaml"), plant_id=PLANT_ID)

    assert imported.topology["sources"] == [
        {
            "id": _derived("source", "heat_pump"),
            "name": "Heat pump",
            "source_demand_entity": "switch.heat_pump_demand",
            "priority": 1,
        },
        {
            "id": _derived("source", "buffer"),
            "name": "Buffer",
            "source_type": "temperature_qualified_buffer",
            "temperature_entity": "sensor.buffer_temperature",
            "minimum_temperature": 35,
            "priority": 2,
        },
    ]
    assert imported.topology["source_selector"] == {
        "id": _derived("source_selector", "source_selector"),
        "name": "Source selector",
        "entity_id": "select.heat_source",
        "minimum_dwell_seconds": 600,
    }
    assert imported.ownership.zone_objects.keys().isdisjoint(
        {_derived("source", "heat_pump"), _derived("source", "buffer")}
    )


def test_every_shorthand_form_expands_to_stored_records() -> None:
    imported = import_plant_document(_load("shorthand.yaml"), plant_id=PLANT_ID)
    living = _derived("zone", "living_room")

    assert imported.topology["zones"] == [
        {
            "id": living,
            "name": "Living room",
            "thermostat": {"kind": "external_climate", "entity_id": "climate.living"},
            "temperature_sensor_metadata": [{"entity_id": "sensor.living_temperature"}],
            "humidity_sensor_metadata": [{"entity_id": "sensor.living_humidity"}],
        }
    ]
    assert imported.topology["pumps"] == [
        {"id": _derived("pump", "main_pump"), "name": "Main pump", "entity_id": "switch.main_pump"}
    ]
    valves = {valve["name"]: valve for valve in imported.topology["valves"]}
    assert valves == {
        "Shared valve": {
            "id": _derived("valve", "shared_valve"),
            "name": "Shared valve",
            "entity_id": "switch.shared_valve",
        },
        "Shared loop valve": {
            "id": _derived("valve", "shared_loop_valve"),
            "name": "Shared loop valve",
            "entity_id": "switch.shared_extra",
        },
        "Living valve": {
            "id": _derived("valve", "living_valve"),
            "name": "Living valve",
            "entity_id": "switch.living_valve",
        },
        "Living loop valve": {
            "id": _derived("valve", "living_loop_valve"),
            "name": "Living loop valve",
            "entity_id": "switch.living_first",
        },
        "Living loop valve 2": {
            "id": _derived("valve", "living_loop_valve_2"),
            "name": "Living loop valve 2",
            "entity_id": "switch.living_second",
        },
    }
    circuits = _by_id(imported.topology["circuits"])
    assert circuits[_derived("circuit", "living_loop")]["valve_ids"] == [
        _derived("valve", "living_valve"),
        _derived("valve", "living_loop_valve"),
        _derived("valve", "shared_valve"),
        _derived("valve", "living_loop_valve_2"),
    ]
    # A shorthand valve belongs to the owner of its loop.
    assert imported.ownership.zone_objects == {
        _derived("circuit", "living_loop"): living,
        _derived("valve", "living_valve"): living,
        _derived("valve", "living_loop_valve"): living,
        _derived("valve", "living_loop_valve_2"): living,
    }
    assert {route["circuit_id"] for route in imported.topology["routes"]} == {
        _derived("circuit", "living_loop"),
        _derived("circuit", "shared_loop"),
    }


def test_shorthand_valve_slug_collides_with_an_explicit_valve() -> None:
    document = _minimal(valves={"bedroom_loop_valve": "switch.other"})
    document["zones"]["bedroom"]["loops"]["bedroom_loop"]["valves"] = [
        "bedroom_loop_valve",
        "switch.bedroom_valve",
    ]
    # The explicit valve comes second in document order.
    assert _error_path(document) == "zones.bedroom.valves.bedroom_loop_valve"


# Plant-level rules


def test_format_version_constant() -> None:
    assert PLANT_FILE_FORMAT == 1


def test_zones_section_holds_the_zones() -> None:
    imported = import_plant_document(_minimal(), plant_id=PLANT_ID)

    bedroom = _derived("zone", "bedroom")
    assert [zone["id"] for zone in imported.topology["zones"]] == [bedroom]
    assert imported.ownership.zone_objects[_derived("circuit", "bedroom_loop")] == bedroom
    assert imported.entity_paths["sensor.bedroom_temperature"] == (
        "zones.bedroom.temperature_sensors.0"
    )
    assert list(_reexport(imported)) == ["hydronicus", "id", "name", "pumps", "zones"]


def test_rooms_is_an_unknown_key() -> None:
    document = _minimal()
    document["rooms"] = document.pop("zones")

    with pytest.raises(PlantDocumentError, match="Unknown key 'rooms'") as caught:
        import_plant_document(document, plant_id=PLANT_ID)

    assert caught.value.path == "rooms"


def test_file_id_wins_over_the_plant_id_argument() -> None:
    document = _minimal()
    document["id"] = OTHER_PLANT_ID.upper()

    imported = import_plant_document(document, plant_id=PLANT_ID)

    assert imported.plant_id == OTHER_PLANT_ID
    other_namespace = UUID(OTHER_PLANT_ID)
    assert imported.topology["zones"][0]["id"] == str(uuid5(other_namespace, "zone:bedroom"))


def test_plant_id_argument_is_the_fallback() -> None:
    imported = import_plant_document(_minimal(), plant_id=PLANT_ID)

    assert imported.plant_id == PLANT_ID
    assert imported.name == "Home"


@pytest.mark.parametrize(
    ("change", "path"),
    [
        ({"hydronicus": 2}, "hydronicus"),
        ({"hydronicus": True}, "hydronicus"),
        ({"hydronicus": "1"}, "hydronicus"),
        ({"id": "not-a-uuid"}, "id"),
        ({"id": 5}, "id"),
        ({"name": ""}, "name"),
        ({"name": 5}, "name"),
        ({"dry_run": True}, "dry_run"),
        ({"output_authorization": {}}, "output_authorization"),
        ({"requested_mode": "heat"}, "requested_mode"),
        ({"pumps": None}, "pumps"),
        ({"zones": []}, "zones"),
        ({"source_selector": "select.x"}, "source_selector"),
    ],
)
def test_plant_level_shape_errors(change: dict[str, Any], path: str) -> None:
    document = _minimal()
    document.update(change)
    assert _error_path(document) == path


def test_missing_name_points_at_name() -> None:
    document = _minimal()
    del document["name"]
    assert _error_path(document) == "name"


def test_document_must_be_a_mapping() -> None:
    with pytest.raises(PlantDocumentError) as caught:
        import_plant_document(["hydronicus"], plant_id=PLANT_ID)  # type: ignore[arg-type]
    assert caught.value.path == ""


def test_invalid_plant_id_argument_is_a_whole_plant_error() -> None:
    assert _error_path(_minimal(), plant_id="plant") == ""


def test_error_carries_path_and_message() -> None:
    error = PlantDocumentError("zones.bedroom", "Broken.")
    assert error.path == "zones.bedroom"
    assert str(error) == "Broken."
    assert isinstance(error, ValueError)


# Object rules


def test_explicit_ids_and_names_are_kept() -> None:
    zone_id = "00000000-0000-4000-8000-000000000001"
    route_id = "00000000-0000-4000-8000-000000000002"
    document = _minimal(id=zone_id, name="Master bedroom")
    document["zones"]["bedroom"]["loops"]["bedroom_loop"]["route_id"] = route_id

    imported = import_plant_document(document, plant_id=PLANT_ID)

    assert imported.topology["zones"][0]["id"] == zone_id
    assert imported.topology["zones"][0]["name"] == "Master bedroom"
    assert imported.topology["routes"][0]["id"] == route_id
    assert imported.topology["valves"][0]["name"] == "Bedroom loop valve"


def test_missing_names_come_from_slugs() -> None:
    document = _minimal()
    document["zones"] = {"guest_bedroom_2": document["zones"]["bedroom"]}

    imported = import_plant_document(document, plant_id=PLANT_ID)

    assert imported.topology["zones"][0]["name"] == "Guest bedroom 2"


def test_derived_ids_use_the_kind_and_slug() -> None:
    imported = import_plant_document(_load("single_zone.yaml"), plant_id=PLANT_ID)

    assert imported.topology["zones"][0]["id"] == _derived("zone", "living_room")
    assert imported.topology["valves"][0]["id"] == _derived("valve", "living_loop_valve")
    assert imported.topology["pumps"][0]["id"] == _derived("pump", "pump")
    assert imported.topology["circuits"][0]["id"] == _derived("circuit", "living_loop")
    assert imported.topology["routes"][0]["id"] == _derived("route", "living_room:living_loop")


def test_private_loop_route_enabled_flag() -> None:
    document = _minimal()
    document["zones"]["bedroom"]["shared_loops"] = ["hall_loop"]
    document["zones"]["bedroom"]["loops"]["bedroom_loop"]["route_enabled"] = False
    document["loops"] = {"hall_loop": {"valves": ["switch.hall"], "pump": "pump"}}

    imported = import_plant_document(document, plant_id=PLANT_ID)

    routes = {route["circuit_id"]: route for route in imported.topology["routes"]}
    assert routes[_derived("circuit", "bedroom_loop")]["enabled"] is False
    assert "enabled" not in routes[_derived("circuit", "hall_loop")]


def test_route_enabled_true_is_the_default() -> None:
    document = _minimal()
    document["zones"]["bedroom"]["loops"]["bedroom_loop"]["route_enabled"] = True
    imported = import_plant_document(document, plant_id=PLANT_ID)
    assert "enabled" not in imported.topology["routes"][0]


def test_shared_loop_mapping_accepts_route_id() -> None:
    route_id = "00000000-0000-4000-8000-000000000003"
    document = _minimal(shared_loops=[{"loop": "hall_loop", "route_id": route_id}])
    document["loops"] = {"hall_loop": {"valves": ["switch.hall"], "pump": "pump"}}

    imported = import_plant_document(document, plant_id=PLANT_ID)

    assert imported.topology["routes"][1]["id"] == route_id


def test_zone_loop_uses_own_and_plant_valves() -> None:
    document = _minimal(valves={"bedroom_valve": "switch.bedroom_valve"})
    document["valves"] = {"hall_valve": "switch.hall_valve"}
    document["zones"]["bedroom"]["loops"]["bedroom_loop"]["valves"] = [
        "bedroom_valve",
        "hall_valve",
    ]

    imported = import_plant_document(document, plant_id=PLANT_ID)

    assert _derived("valve", "hall_valve") not in imported.ownership.zone_objects
    assert imported.ownership.zone_objects[_derived("valve", "bedroom_valve")] == _derived(
        "zone", "bedroom"
    )


def test_unused_plant_equipment_is_a_warning() -> None:
    document = _minimal()
    document["pumps"]["spare_pump"] = "switch.spare_pump"
    document["valves"] = {"spare_valve": "switch.spare_valve"}

    imported = import_plant_document(document, plant_id=PLANT_ID)

    assert {warning.code for warning in imported.compiled.warnings} == {"unused_equipment"}


def test_hydronicus_thermostat_mapping_defaults_its_kind() -> None:
    imported = import_plant_document(
        _minimal(thermostat={"initial_target_temperature": 20}), plant_id=PLANT_ID
    )
    assert imported.topology["zones"][0]["thermostat"] == {
        "kind": "hydronicus",
        "initial_target_temperature": 20,
    }


def test_zone_without_thermostat_gets_a_hydronicus_thermostat() -> None:
    imported = import_plant_document(_minimal(), plant_id=PLANT_ID)
    assert imported.topology["zones"][0]["thermostat"] == {"kind": "hydronicus"}


def test_stored_leaf_fields_pass_through() -> None:
    document = _minimal(temperature_aggregation="median")
    document["pumps"]["pump"] = {
        "entity_id": "switch.pump",
        "overrun_seconds": 30,
        "fault_feedback_entity": "binary_sensor.pump_fault",
        "fault_feedback_max_age_seconds": 60,
    }
    document["valves"] = {
        "hall_valve": {
            "entity_id": "switch.hall_valve",
            "opening_time_seconds": 90,
            "readiness_entity_id": "binary_sensor.hall_ready",
            "position_feedback_entity": "sensor.hall_position",
            "position_feedback_max_age_seconds": 120,
        }
    }

    imported = import_plant_document(document, plant_id=PLANT_ID)

    assert imported.topology["zones"][0]["temperature_aggregation"] == "median"
    assert imported.topology["pumps"][0]["fault_feedback_max_age_seconds"] == 60
    hall = _by_id(imported.topology["valves"])[_derived("valve", "hall_valve")]
    assert hall["readiness_entity_id"] == "binary_sensor.hall_ready"
    assert hall["position_feedback_max_age_seconds"] == 120


def test_null_optional_entity_fields_round_trip() -> None:
    document = _minimal()
    document["zones"]["bedroom"]["loops"]["bedroom_loop"]["surface_temperature_sensor"] = None

    imported = import_plant_document(document, plant_id=PLANT_ID)

    assert imported.topology["circuits"][0]["surface_temperature_sensor"] is None
    assert None not in imported.entity_paths
    exported = _reexport(imported)
    loop = exported["zones"]["bedroom"]["loops"]["bedroom_loop"]
    assert loop["surface_temperature_sensor"] is None
    assert _reexport(import_plant_document(exported, plant_id=PLANT_ID)) == exported


def test_entity_paths_name_the_first_binding_of_every_entity() -> None:
    document = _load("shorthand.yaml")
    document["zones"]["living_room"]["temperature_sensors"] = [
        {"entity_id": "sensor.living_temperature"},
        "sensor.living_temperature_2",
    ]
    document["pumps"]["main_pump"] = {
        "entity_id": "switch.main_pump",
        "power_feedback_entity": "sensor.living_temperature_2",
    }
    document["sources"] = {"boiler": {"source_demand_entity": "switch.boiler"}}
    document["source_selector"] = {"entity_id": "select.source"}

    imported = import_plant_document(document, plant_id=PLANT_ID)

    assert imported.entity_paths == {
        "switch.main_pump": "pumps.main_pump.entity_id",
        "sensor.living_temperature_2": "pumps.main_pump.power_feedback_entity",
        "switch.shared_valve": "valves.shared_valve",
        "switch.shared_extra": "loops.shared_loop.valves.1",
        "climate.living": "zones.living_room.thermostat",
        "sensor.living_temperature": "zones.living_room.temperature_sensors.0.entity_id",
        "sensor.living_humidity": "zones.living_room.humidity_sensors.0",
        "switch.living_valve": "zones.living_room.valves.living_valve",
        "switch.living_first": "zones.living_room.loops.living_loop.valves.1",
        "switch.living_second": "zones.living_room.loops.living_loop.valves.3",
        "switch.boiler": "sources.boiler.source_demand_entity",
        "select.source": "source_selector.entity_id",
    }


def test_entity_paths_cover_long_form_thermostat_and_loop_sensors() -> None:
    imported = import_plant_document(_load("cooling.yaml"), plant_id=PLANT_ID)
    assert imported.entity_paths["sensor.living_supply"] == (
        "zones.living_room.loops.living_loop.supply_temperature_sensor"
    )
    external = import_plant_document(_load("external_thermostat.yaml"), plant_id=PLANT_ID)
    assert external.entity_paths["climate.study"] == "zones.study.thermostat.entity_id"


# Shape and reference errors


@pytest.mark.parametrize(
    ("zone", "path"),
    [
        ({"thermostat": "sensor.bedroom"}, "zones.bedroom.thermostat"),
        ({"thermostat": {"kind": "gas"}}, "zones.bedroom.thermostat.kind"),
        (
            {"thermostat": {"kind": "hydronicus", "entity_id": "x"}},
            "zones.bedroom.thermostat.entity_id",
        ),
        ({"thermostat": {"flavour": 1}}, "zones.bedroom.thermostat.flavour"),
        ({"thermostat": 5}, "zones.bedroom.thermostat"),
        ({"temperature_sensors": "sensor.x"}, "zones.bedroom.temperature_sensors"),
        ({"temperature_sensors": [5]}, "zones.bedroom.temperature_sensors.0"),
        ({"temperature_sensors": [""]}, "zones.bedroom.temperature_sensors.0"),
        (
            {"temperature_sensors": [{"entity_id": "sensor.x", "offset": 1}]},
            "zones.bedroom.temperature_sensors.0.offset",
        ),
        (
            {"temperature_sensors": [{"weight": 1}]},
            "zones.bedroom.temperature_sensors.0.entity_id",
        ),
        ({"temperature_sensors": []}, "zones.bedroom.temperature_sensors"),
        ({"humidity_sensors": [None]}, "zones.bedroom.humidity_sensors.0"),
        ({"valves": ["switch.x"]}, "zones.bedroom.valves"),
        ({"loops": {}}, "zones.bedroom"),
        ({"loops": {"bedroom_loop": "switch.x"}}, "zones.bedroom.loops.bedroom_loop"),
        (
            {"loops": {"bedroom_loop": {"valves": ["switch.x"]}}},
            "zones.bedroom.loops.bedroom_loop.pump",
        ),
        (
            {"loops": {"bedroom_loop": {"pump": "pump"}}},
            "zones.bedroom.loops.bedroom_loop.valves",
        ),
        (
            {"loops": {"bedroom_loop": {"valves": [], "pump": "pump"}}},
            "zones.bedroom.loops.bedroom_loop.valves",
        ),
        (
            {"loops": {"bedroom_loop": {"valves": [5], "pump": "pump"}}},
            "zones.bedroom.loops.bedroom_loop.valves.0",
        ),
        (
            {"loops": {"bedroom_loop": {"valves": ["switch.x"], "pump": 5}}},
            "zones.bedroom.loops.bedroom_loop.pump",
        ),
        (
            {"loops": {"bedroom_loop": {"valves": ["nope"], "pump": "pump"}}},
            "zones.bedroom.loops.bedroom_loop.valves.0",
        ),
        (
            {
                "valves": {"bedroom_valve": "switch.v"},
                "loops": {"bedroom_loop": {"valves": ["bedroom_valve"] * 2, "pump": "pump"}},
            },
            "zones.bedroom.loops.bedroom_loop.valves.1",
        ),
        (
            {"loops": {"bedroom_loop": {"valves": ["switch.x"], "pump": "pump", "valve_ids": []}}},
            "zones.bedroom.loops.bedroom_loop.valve_ids",
        ),
        (
            {"loops": {"bedroom_loop": {"valves": ["switch.x"], "pump": "pump", "route_id": "r"}}},
            "zones.bedroom.loops.bedroom_loop.route_id",
        ),
        (
            {
                "loops": {
                    "bedroom_loop": {"valves": ["switch.x"], "pump": "pump", "route_enabled": 1}
                }
            },
            "zones.bedroom.loops.bedroom_loop.route_enabled",
        ),
        (
            {
                "loops": {
                    "bedroom_loop": {
                        "valves": ["switch.x"],
                        "pump": "pump",
                        "route_enabled": False,
                    }
                }
            },
            "zones.bedroom",
        ),
        ({"shared_loops": "hall_loop"}, "zones.bedroom.shared_loops"),
        ({"shared_loops": ["nope"]}, "zones.bedroom.shared_loops.0"),
        ({"shared_loops": [5]}, "zones.bedroom.shared_loops.0"),
        ({"shared_loops": ["bedroom_loop"]}, "zones.bedroom.shared_loops.0"),
        ({"shared_loops": ["hall_loop", "hall_loop"]}, "zones.bedroom.shared_loops.1"),
        ({"shared_loops": [{"route_id": "x"}]}, "zones.bedroom.shared_loops.0.loop"),
        ({"shared_loops": [{"loop": "hall_loop", "x": 1}]}, "zones.bedroom.shared_loops.0.x"),
        ({"id": "nope"}, "zones.bedroom.id"),
        ({"name": ""}, "zones.bedroom.name"),
        ({"temperature_aggregation": "loudest"}, "zones.bedroom"),
    ],
)
def test_zone_shape_and_reference_errors(zone: dict[str, Any], path: str) -> None:
    document = _minimal(**zone)
    document["loops"] = {"hall_loop": {"valves": ["switch.hall"], "pump": "pump"}}
    assert _error_path(document) == path


def test_zone_must_be_a_mapping() -> None:
    document = _minimal()
    document["zones"]["bedroom"] = None
    assert _error_path(document) == "zones.bedroom"


def test_shared_loops_rejects_another_zones_private_loop() -> None:
    document = _minimal(shared_loops=["living_loop"])
    document["zones"]["living_room"] = {
        "temperature_sensors": ["sensor.living"],
        "loops": {"living_loop": {"valves": ["switch.living"], "pump": "pump"}},
    }
    assert _error_path(document) == "zones.bedroom.shared_loops.0"


@pytest.mark.parametrize(
    ("pumps", "path"),
    [
        ({"pump": 5}, "pumps.pump"),
        ({"pump": ""}, "pumps.pump"),
        ({"pump": {"overrun_seconds": 3}}, "pumps.pump.entity_id"),
        ({"pump": {"entity_id": 5}}, "pumps.pump.entity_id"),
        (
            {"pump": {"entity_id": "switch.p", "pump_overrun_seconds": 3}},
            "pumps.pump.pump_overrun_seconds",
        ),
        ({"pump": {"entity_id": "switch.p", "overrun_seconds": -1}}, "pumps.pump"),
        ({"pump": {"entity_id": "switch.p", "name": 5}}, "pumps.pump.name"),
        ({"pump": {"entity_id": "switch.p", "id": "x"}}, "pumps.pump.id"),
        ({"pump": "switch.pump", "2nd_pump": "switch.p2"}, "pumps.2nd_pump"),
        ({"pump": "switch.pump", 5: "switch.p2"}, "pumps.5"),
    ],
)
def test_pump_errors(pumps: dict[Any, Any], path: str) -> None:
    document = _minimal()
    document["pumps"] = pumps
    assert _error_path(document) == path


def test_unknown_stored_field_points_at_the_key() -> None:
    document = _minimal()
    document["pumps"] = {"pump": {"entity_id": "switch.p", "overrun": 3}}
    assert _error_path(document) == "pumps.pump.overrun"


@pytest.mark.parametrize(
    ("valves", "path"),
    [
        ({"hall_valve": 5}, "valves.hall_valve"),
        (
            {"hall_valve": {"entity_id": "switch.v", "opening_time_seconds": "slow"}},
            "valves.hall_valve",
        ),
        ({"hall_valve": {"entity_id": "switch.v", "colour": "red"}}, "valves.hall_valve.colour"),
    ],
)
def test_plant_valve_errors(valves: dict[str, Any], path: str) -> None:
    document = _minimal()
    document["valves"] = valves
    assert _error_path(document) == path


@pytest.mark.parametrize(
    ("loops", "path"),
    [
        (
            {"hall_loop": {"valves": ["switch.h"], "pump": "pump", "route_id": "x"}},
            "loops.hall_loop.route_id",
        ),
        (
            {"hall_loop": {"valves": ["switch.h"], "pump": "pump", "cooling_enabled": "yes"}},
            "loops.hall_loop",
        ),
        ({"hall_loop": {"valves": ["switch.h"], "pump": "pump", "id": 5}}, "loops.hall_loop.id"),
    ],
)
def test_plant_loop_errors(loops: dict[str, Any], path: str) -> None:
    document = _minimal()
    document["loops"] = loops
    assert _error_path(document) == path


@pytest.mark.parametrize(
    ("change", "path"),
    [
        ({"sources": {"boiler": "switch.boiler"}}, "sources.boiler"),
        ({"sources": {"boiler": {"source_type": "coal"}}}, "sources.boiler"),
        ({"sources": {"boiler": {"demand_entity": "switch.b"}}}, "sources.boiler.demand_entity"),
        (
            {"sources": {"boiler": {"source_demand_entity": 5}}},
            "sources.boiler.source_demand_entity",
        ),
        (
            {"source_selector": {"entity_id": "select.s", "break_seconds": 3}},
            "source_selector.break_seconds",
        ),
        ({"source_selector": {"shadow_only": "no"}}, "source_selector"),
        ({"source_selector": {"id": "x"}}, "source_selector.id"),
    ],
)
def test_source_errors(change: dict[str, Any], path: str) -> None:
    document = _minimal()
    document.update(change)
    assert _error_path(document) == path


def test_loops_share_one_namespace() -> None:
    document = _minimal()
    document["loops"] = {"bedroom_loop": {"valves": ["switch.hall"], "pump": "pump"}}
    assert _error_path(document) == "loops.bedroom_loop"


def test_zones_and_pumps_have_separate_namespaces() -> None:
    document = _minimal()
    document["pumps"] = {"bedroom": "switch.pump"}
    document["zones"]["bedroom"]["loops"]["bedroom_loop"]["pump"] = "bedroom"
    document["sources"] = {"bedroom": {}}
    imported = import_plant_document(document, plant_id=PLANT_ID)
    assert imported.topology["pumps"][0]["id"] == _derived("pump", "bedroom")
    assert imported.topology["sources"][0]["id"] == _derived("source", "bedroom")


def test_duplicate_ids_point_at_the_second_object() -> None:
    same = "00000000-0000-4000-8000-000000000009"
    document = _minimal(id=same)
    document["pumps"]["pump"] = {"entity_id": "switch.pump", "id": same}
    assert _error_path(document) == "zones.bedroom.id"


def test_duplicate_route_id_points_at_the_route() -> None:
    same = "00000000-0000-4000-8000-000000000009"
    document = _minimal(id=same)
    document["zones"]["bedroom"]["loops"]["bedroom_loop"]["route_id"] = same
    assert _error_path(document) == "zones.bedroom.loops.bedroom_loop.route_id"


# Negative fixtures, one per error class


NEGATIVE_FIXTURES = {
    "unknown_key.yaml": "zones.bedroom.colour",
    "invalid_slug.yaml": "zones.Bedroom",
    "duplicate_slug.yaml": "zones.bedroom.valves.bedroom_valve",
    "unknown_reference.yaml": "zones.bedroom.loops.bedroom_loop.pump",
    "other_zone_private_valve.yaml": "zones.bedroom.loops.bedroom_loop.valves.1",
    "plant_loop_private_valve.yaml": "loops.hall_loop.valves.1",
    "compile_failure.yaml": "",
    "missing_format_version.yaml": "hydronicus",
    "duplicate_actuator_binding.yaml": "zones.bedroom.loops.bedroom_loop.valves.0",
    "cooling_reference.yaml": "zones.living_room.loops.living_loop",
    "cooling_observation.yaml": "zones.living_room.humidity_sensors",
    "designated_reference.yaml": "zones.living_room.temperature_sensors",
    "buffer_temperature.yaml": "sources.buffer",
    "ownership.yaml": "zones.bedroom.valves.spare_valve",
}


@pytest.mark.parametrize(("fixture", "path"), sorted(NEGATIVE_FIXTURES.items()))
def test_negative_fixture_points_at_its_error_path(fixture: str, path: str) -> None:
    assert _error_path(_load(f"invalid/{fixture}")) == path


def test_every_negative_fixture_is_covered() -> None:
    on_disk = {path.name for path in (FIXTURES / "invalid").glob("*.yaml")}
    assert on_disk == set(NEGATIVE_FIXTURES)


def test_compile_failure_keeps_the_core_message() -> None:
    with pytest.raises(PlantDocumentError, match="target temperature must be between"):
        import_plant_document(_load("invalid/compile_failure.yaml"), plant_id=PLANT_ID)


def test_cooling_observation_temperature_path() -> None:
    document = _load("invalid/cooling_observation.yaml")
    zone = document["zones"]["living_room"]
    zone["thermostat"] = "climate.living"
    del zone["temperature_sensors"]
    zone["humidity_sensors"] = ["sensor.living_humidity"]
    assert _error_path(document) == "zones.living_room.temperature_sensors"


# Export


def _stored_manifold() -> tuple[dict[str, Any], PlantOwnership]:
    imported = import_plant_document(_load("shared_loop.yaml"), plant_id=PLANT_ID)
    return imported.topology, imported.ownership


def test_export_writes_the_canonical_form() -> None:
    topology, ownership = _stored_manifold()

    document = export_plant_document(
        name="Shared manifold", plant_id=PLANT_ID, topology=topology, ownership=ownership
    )

    assert list(document) == ["hydronicus", "id", "name", "pumps", "valves", "loops", "zones"]
    assert document["hydronicus"] == PLANT_FILE_FORMAT
    assert document["id"] == PLANT_ID
    assert document["pumps"] == {
        "pump": {"id": _derived("pump", "pump"), "name": "Pump", "entity_id": "switch.pump"}
    }
    assert document["valves"] == {
        "hall_valve": {
            "id": _derived("valve", "hall_valve"),
            "name": "Hall valve",
            "entity_id": "switch.hall_valve",
            "opening_time_seconds": 120,
        }
    }
    assert document["loops"] == {
        "hall_loop": {
            "id": _derived("circuit", "hall_loop"),
            "name": "Hall loop",
            "valves": ["hall_valve"],
            "pump": "pump",
        }
    }
    assert list(document["zones"]) == ["bedroom", "living_room"]
    assert document["zones"]["bedroom"] == {
        "id": _derived("zone", "bedroom"),
        "name": "Bedroom",
        "thermostat": {"kind": "hydronicus"},
        "temperature_sensors": [{"entity_id": "sensor.bedroom_temperature"}],
        "valves": {
            "bedroom_loop_valve": {
                "id": _derived("valve", "bedroom_loop_valve"),
                "name": "Bedroom loop valve",
                "entity_id": "switch.bedroom_valve",
            }
        },
        "loops": {
            "bedroom_loop": {
                "id": _derived("circuit", "bedroom_loop"),
                "name": "Bedroom loop",
                "valves": ["bedroom_loop_valve", "hall_valve"],
                "pump": "pump",
                "route_id": _derived("route", "bedroom:bedroom_loop"),
            }
        },
        "shared_loops": [
            {
                "loop": "hall_loop",
                "route_id": _derived("route", "bedroom:hall_loop"),
                "route_enabled": False,
            }
        ],
    }
    assert document["zones"]["living_room"]["shared_loops"] == [
        {"loop": "hall_loop", "route_id": _derived("route", "living_room:hall_loop")}
    ]


def test_export_orders_keys_like_the_stored_decoder() -> None:
    imported = import_plant_document(_load("cooling.yaml"), plant_id=PLANT_ID)
    zone = imported.topology["zones"][0]
    # Stored records may hold their keys in any order.
    zone["thermostat"] = dict(reversed(zone["thermostat"].items()))
    zone["temperature_sensor_metadata"][0] = {
        "weight": 2,
        "designated_reference": False,
        "entity_id": "sensor.living_temperature",
    }
    imported.topology["zones"][0] = dict(reversed(zone.items()))

    document = _reexport(imported)

    exported = document["zones"]["living_room"]
    assert list(exported) == [
        "id",
        "name",
        "thermostat",
        "temperature_sensors",
        "humidity_sensors",
        "valves",
        "loops",
    ]
    assert list(exported["thermostat"]) == [
        "kind",
        "initial_target_temperature",
        "cooling_start_delta",
    ]
    assert list(exported["temperature_sensors"][0]) == [
        "entity_id",
        "designated_reference",
        "weight",
    ]
    assert list(exported["loops"]["living_loop"]) == [
        "id",
        "name",
        "valves",
        "pump",
        "cooling_enabled",
        "supply_temperature_sensor",
        "condensation_margin",
        "route_id",
    ]


def test_export_writes_sources_and_selector() -> None:
    imported = import_plant_document(_load("sources.yaml"), plant_id=PLANT_ID)

    document = _reexport(imported)

    assert list(document)[-2:] == ["sources", "source_selector"]
    assert list(document["sources"]) == ["buffer", "heat_pump"]
    assert list(document["sources"]["buffer"]) == [
        "id",
        "name",
        "source_type",
        "temperature_entity",
        "minimum_temperature",
        "priority",
    ]
    assert document["source_selector"] == {
        "id": _derived("source_selector", "source_selector"),
        "name": "Source selector",
        "entity_id": "select.heat_source",
        "minimum_dwell_seconds": 600,
    }


def test_export_does_not_alias_stored_values() -> None:
    imported = import_plant_document(
        _minimal(thermostat={"preset_targets": {"eco": 18}}), plant_id=PLANT_ID
    )
    document = _reexport(imported)
    document["zones"]["bedroom"]["thermostat"]["preset_targets"]["eco"] = 5
    assert imported.topology["zones"][0]["thermostat"]["preset_targets"] == {"eco": 18}


def _named(names: list[tuple[str, str]]) -> dict[str, Any]:
    """Return stored data with one pump per (name, id) and nothing else."""
    return {
        "pumps": [
            {"id": object_id, "name": name, "entity_id": f"switch.pump_{index}"}
            for index, (name, object_id) in enumerate(names)
        ]
    }


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Main Pump", "main_pump"),
        ("Kid's  room -- 2", "kid_s_room_2"),
        ("2nd floor", "pump_2nd_floor"),
        ("Ärkély", "arkely"),
        ("Straße", "strasse"),
        ("  !!  ", "pump"),
        ("Кухня", "pump"),
        ("_under_", "under"),
    ],
)
def test_export_slugs_from_names(name: str, slug: str) -> None:
    pump_id = "00000000-0000-4000-8000-000000000001"
    document = export_plant_document(
        name="P",
        plant_id=PLANT_ID,
        topology=_named([(name, pump_id)]),
        ownership=PlantOwnership({}),
    )
    assert list(document["pumps"]) == [slug]


def test_export_suffixes_duplicate_slugs_in_name_and_id_order() -> None:
    first = "00000000-0000-4000-8000-000000000001"
    second = "00000000-0000-4000-8000-000000000002"
    third = "00000000-0000-4000-8000-000000000003"
    topology = _named(
        [("Pump", third), ("pump", first), ("Pump", second), ("Pump 2", first[:-1] + "4")]
    )

    document = export_plant_document(
        name="P", plant_id=PLANT_ID, topology=topology, ownership=PlantOwnership({})
    )

    slugs = {slug: pump["id"] for slug, pump in document["pumps"].items()}
    # (name, id) order: ("Pump", second), ("Pump", third), ("Pump 2", ...), ("pump", first).
    assert slugs == {
        "pump": second,
        "pump_2": third,
        "pump_2_2": first[:-1] + "4",
        "pump_3": first,
    }
    assert list(document["pumps"]) == sorted(slugs)


def test_export_uses_the_plant_file_kind_for_prefixes() -> None:
    imported = import_plant_document(_minimal(name="1st bedroom"), plant_id=PLANT_ID)
    imported.topology["circuits"][0]["name"] = "1st loop"
    imported.topology["valves"][0]["name"] = "1st valve"
    document = _reexport(imported)
    zone = document["zones"]["zone_1st_bedroom"]
    assert list(zone["loops"]) == ["loop_1st_loop"]
    assert list(zone["valves"]) == ["valve_1st_valve"]


def test_export_omits_empty_collections_and_keeps_empty_sensor_lists() -> None:
    imported = import_plant_document(
        _minimal(thermostat="climate.bedroom", temperature_sensors=[]), plant_id=PLANT_ID
    )
    document = _reexport(imported)
    assert "sources" not in document
    assert "source_selector" not in document
    assert "shared_loops" not in document["zones"]["bedroom"]
    assert document["zones"]["bedroom"]["temperature_sensors"] == []


def test_export_rejects_invalid_ownership() -> None:
    topology, ownership = _stored_manifold()
    broken = PlantOwnership(
        {**ownership.zone_objects, _derived("valve", "hall_valve"): _derived("zone", "bedroom")}
    )
    with pytest.raises(ValueError, match="private"):
        export_plant_document(name="P", plant_id=PLANT_ID, topology=topology, ownership=broken)


def test_export_keeps_unknown_stored_keys_so_import_rejects_them() -> None:
    topology, ownership = _stored_manifold()
    topology["pumps"][0]["legacy"] = 1
    document = export_plant_document(
        name="P", plant_id=PLANT_ID, topology=topology, ownership=ownership
    )
    assert list(document["pumps"]["pump"])[-1] == "legacy"
    assert _error_path(document) == "pumps.pump.legacy"


# Properties


def _exported(data: dict[str, Any], ownership: PlantOwnership) -> dict[str, Any]:
    return export_plant_document(
        name="Plant", plant_id=data["plant_id"], topology=data["topology"], ownership=ownership
    )


def _collections(topology: Mapping[str, Any]) -> dict[str, Any]:
    """Return every stored collection keyed by id, with absent lists as empty."""
    return {
        key: _by_id(list(topology.get(key, [])))
        for key in ("zones", "valves", "pumps", "circuits", "routes", "sources")
    } | {"source_selector": topology.get("source_selector")}


@settings(max_examples=300, deadline=None)
@given(stored_plants())
def test_export_then_import_reproduces_topology_and_ownership(data: dict[str, Any]) -> None:
    ownership = derive_ownership(plant_configuration_from_entry_data(data))

    imported = import_plant_document(_exported(data, ownership), plant_id=OTHER_PLANT_ID)

    assert imported.plant_id == data["plant_id"]
    assert _collections(imported.topology) == _collections(data["topology"])
    assert imported.ownership == ownership


@settings(max_examples=300, deadline=None)
@given(stored_plants())
def test_import_then_export_of_a_canonical_file_is_the_identity(data: dict[str, Any]) -> None:
    ownership = derive_ownership(plant_configuration_from_entry_data(data))
    canonical = _exported(data, ownership)

    imported = import_plant_document(copy.deepcopy(canonical), plant_id=OTHER_PLANT_ID)

    assert _reexport(imported) == canonical
    # The canonical file is also plain YAML data.
    assert yaml.safe_load(yaml.safe_dump(canonical, sort_keys=False)) == canonical
