"""Zones that cover Home Assistant areas: stored declarations and resolved sensors."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from hydronicus_core.legacy.configuration import (
    DesignatedReferenceError,
    StoredTopologyError,
    plant_configuration_from_entry_data,
)
from hydronicus_core.legacy.controller import aggregate_temperature, evaluate
from hydronicus_core.legacy.entity_bindings import configured_entity_bindings
from hydronicus_core.legacy.model import (
    AreaSensors,
    HydronicusThermostatState,
    NumericObservation,
    PlantSnapshot,
    RuntimeState,
    TemperatureAggregation,
    TemperatureSensorMetadata,
    ThermostatHvacMode,
    ZoneArea,
    ZoneDecisionStatus,
)
from hydronicus_core.legacy.topology import (
    CoolingObservationError,
    TopologyValidationError,
    compile_topology,
)
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.core.legacy.strategies import stored_plants

PLANT_ID = "00000000-0000-4000-8000-000000000001"
ZONE_ID = "00000000-0000-4000-8000-000000000002"
VALVE_ID = "00000000-0000-4000-8000-000000000003"
PUMP_ID = "00000000-0000-4000-8000-000000000004"
CIRCUIT_ID = "00000000-0000-4000-8000-000000000005"
ROUTE_ID = "00000000-0000-4000-8000-000000000006"
NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


def _data(*, cooling: bool = False, **zone_fields: Any) -> dict[str, Any]:
    """Return stored data for one zone on one loop, with zone fields replaced."""
    zone: dict[str, Any] = {
        "id": ZONE_ID,
        "name": "Ground floor",
        "thermostat": {"kind": "hydronicus"},
    }
    zone.update(zone_fields)
    circuit: dict[str, Any] = {
        "id": CIRCUIT_ID,
        "name": "Ground floor loop",
        "valve_ids": [VALVE_ID],
        "pump_id": PUMP_ID,
    }
    if cooling:
        circuit |= {"cooling_enabled": True, "supply_temperature_sensor": "sensor.supply"}
    return {
        "plant_id": PLANT_ID,
        "topology": {
            "zones": [zone],
            "valves": [{"id": VALVE_ID, "name": "Valve", "entity_id": "switch.valve"}],
            "pumps": [{"id": PUMP_ID, "name": "Pump", "entity_id": "switch.pump"}],
            "circuits": [circuit],
            "routes": [{"id": ROUTE_ID, "zone_id": ZONE_ID, "circuit_id": CIRCUIT_ID}],
        },
    }


def _zone(data: dict[str, Any], **area_sensors: AreaSensors) -> Any:
    return plant_configuration_from_entry_data(data, area_sensors=area_sensors).zones[0]


# K1: stored declarations


def test_areas_decode_with_their_defaults() -> None:
    zone = _zone(
        _data(
            areas=[
                {"area_id": "kitchen"},
                {
                    "area_id": "hall",
                    "required": True,
                    "weight": 0.5,
                    "designated_reference": True,
                    "max_age_seconds": 600,
                },
            ]
        )
    )

    assert zone.areas == (
        ZoneArea("kitchen"),
        ZoneArea("hall", required=True, weight=0.5, designated_reference=True, max_age_seconds=600),
    )
    assert ZoneArea("x") == ZoneArea(
        "x", required=False, weight=1.0, designated_reference=False, max_age_seconds=1800.0
    )


def test_a_zone_without_areas_has_no_areas() -> None:
    zone = _zone(_data(temperature_sensor_metadata=[{"entity_id": "sensor.t"}]))

    assert zone.areas == ()
    assert zone.temperature_sensor_metadata[0].area_id is None


def test_an_area_is_a_temperature_source_of_a_hydronicus_thermostat() -> None:
    for sensors in ({}, {"temperature_sensor_metadata": []}):
        zone = _zone(_data(areas=[{"area_id": "kitchen"}], **sensors))
        assert zone.temperature_sensor_metadata == ()


def test_a_hydronicus_thermostat_needs_a_sensor_or_an_area() -> None:
    for fields in ({}, {"areas": []}, {"areas": [], "temperature_sensor_metadata": []}):
        with pytest.raises(StoredTopologyError, match="temperature_sensor_metadata"):
            plant_configuration_from_entry_data(_data(**fields))


@pytest.mark.parametrize(
    ("areas", "message"),
    [
        ("kitchen", "areas.*list of objects"),
        (["kitchen"], "areas.*list of objects"),
        ([{"required": True}], "area_id"),
        ([{"area_id": ""}], "area_id"),
        ([{"area_id": 3}], "area_id"),
        ([{"area_id": "kitchen"}, {"area_id": "kitchen"}], "duplicate area 'kitchen'"),
        ([{"area_id": "kitchen", "entity_id": "sensor.t"}], "unknown fields: entity_id"),
        ([{"area_id": "kitchen", "required": "yes"}], "required.*boolean"),
        ([{"area_id": "kitchen", "designated_reference": 1}], "designated_reference.*boolean"),
        ([{"area_id": "kitchen", "weight": 0}], "weight.*positive"),
        ([{"area_id": "kitchen", "max_age_seconds": -1}], "max_age_seconds.*positive"),
    ],
)
def test_malformed_areas_are_rejected(areas: Any, message: str) -> None:
    with pytest.raises(StoredTopologyError, match=message):
        plant_configuration_from_entry_data(_data(areas=areas))


def test_one_sensor_or_area_may_be_the_designated_reference() -> None:
    data = _data(
        temperature_sensor_metadata=[{"entity_id": "sensor.t", "designated_reference": True}],
        areas=[{"area_id": "kitchen", "designated_reference": True}],
    )

    with pytest.raises(DesignatedReferenceError, match="multiple designated") as caught:
        plant_configuration_from_entry_data(data)
    assert caught.value.zone_id == ZONE_ID


def test_designated_reference_aggregation_accepts_a_designated_area() -> None:
    data = _data(
        temperature_aggregation="designated_reference",
        temperature_sensor_metadata=[{"entity_id": "sensor.t"}],
        areas=[{"area_id": "kitchen", "designated_reference": True}],
    )

    # The area resolves to nothing: the zone keeps no designated record and
    # still compiles, so the aggregation blocks at runtime instead.
    unresolved = plant_configuration_from_entry_data(data)
    compile_topology(unresolved)
    assert not any(sensor.designated_reference for sensor in unresolved.zones[0].sensor_metadata)

    resolved = _zone(data, kitchen=AreaSensors("sensor.kitchen_t"))
    assert [
        sensor.entity_id for sensor in resolved.sensor_metadata if sensor.designated_reference
    ] == ["sensor.kitchen_t"]


def test_designated_reference_aggregation_still_needs_one_declaration() -> None:
    data = _data(
        temperature_aggregation="designated_reference",
        areas=[{"area_id": "kitchen"}],
    )

    with pytest.raises(DesignatedReferenceError, match="exactly one"):
        plant_configuration_from_entry_data(data)


# K2: resolution and merging


def test_resolved_areas_follow_the_explicit_sensors_in_area_order() -> None:
    zone = _zone(
        _data(
            temperature_sensor_metadata=[{"entity_id": "sensor.floor_probe"}],
            humidity_sensor_metadata=[{"entity_id": "sensor.bathroom_humidity"}],
            areas=[
                {"area_id": "kitchen", "weight": 0.5, "max_age_seconds": 900},
                {"area_id": "hall", "required": True, "designated_reference": True},
            ],
        ),
        hall=AreaSensors("sensor.hall_t", "sensor.hall_h"),
        kitchen=AreaSensors("sensor.kitchen_t", "sensor.kitchen_h"),
    )

    assert zone.temperature_sensor_metadata == (
        TemperatureSensorMetadata("sensor.floor_probe"),
        TemperatureSensorMetadata(
            "sensor.kitchen_t", required=False, weight=0.5, max_age_seconds=900, area_id="kitchen"
        ),
        TemperatureSensorMetadata(
            "sensor.hall_t", required=True, designated_reference=True, area_id="hall"
        ),
    )
    # An area's humidity sensor is always required, with the area's maximum age.
    assert zone.humidity_sensor_metadata == (
        TemperatureSensorMetadata("sensor.bathroom_humidity"),
        TemperatureSensorMetadata("sensor.kitchen_h", max_age_seconds=900, area_id="kitchen"),
        TemperatureSensorMetadata("sensor.hall_h", area_id="hall"),
    )


def test_an_unresolved_area_or_measurement_contributes_nothing() -> None:
    zone = _zone(
        _data(areas=[{"area_id": "kitchen"}, {"area_id": "hall"}, {"area_id": "missing"}]),
        kitchen=AreaSensors(temperature_entity_id="sensor.kitchen_t"),
        hall=AreaSensors(humidity_entity_id="sensor.hall_h"),
    )

    assert zone.temperature_sensors == ("sensor.kitchen_t",)
    assert zone.humidity_sensors == ("sensor.hall_h",)


def test_an_explicit_sensor_and_an_area_on_one_entity_count_once() -> None:
    zone = _zone(
        _data(
            temperature_sensor_metadata=[
                {"entity_id": "sensor.kitchen_t", "required": True, "calibration_offset": -0.5}
            ],
            humidity_sensor_metadata=[{"entity_id": "sensor.kitchen_h", "required": False}],
            areas=[{"area_id": "kitchen", "weight": 3, "designated_reference": True}],
        ),
        kitchen=AreaSensors("sensor.kitchen_t", "sensor.kitchen_h"),
    )

    # The explicit sensor's settings win, and the area's reference mark is kept.
    assert zone.temperature_sensor_metadata == (
        TemperatureSensorMetadata(
            "sensor.kitchen_t", required=True, calibration_offset=-0.5, designated_reference=True
        ),
    )
    assert zone.humidity_sensor_metadata == (
        TemperatureSensorMetadata("sensor.kitchen_h", required=False),
    )


def test_two_areas_on_one_entity_count_once_with_the_first_area() -> None:
    zone = _zone(
        _data(
            temperature_aggregation="designated_reference",
            areas=[{"area_id": "kitchen"}, {"area_id": "dining", "designated_reference": True}],
        ),
        kitchen=AreaSensors("sensor.shared_t", "sensor.shared_h"),
        dining=AreaSensors("sensor.shared_t", "sensor.shared_h"),
    )

    assert zone.temperature_sensor_metadata == (
        TemperatureSensorMetadata(
            "sensor.shared_t", required=False, designated_reference=True, area_id="kitchen"
        ),
    )
    assert zone.humidity_sensor_metadata == (
        TemperatureSensorMetadata("sensor.shared_h", area_id="kitchen"),
    )


def test_resolution_is_ignored_for_areas_no_zone_covers() -> None:
    zone = _zone(
        _data(temperature_sensor_metadata=[{"entity_id": "sensor.t"}]),
        kitchen=AreaSensors("sensor.kitchen_t", "sensor.kitchen_h"),
    )

    assert zone.temperature_sensors == ("sensor.t",)
    assert zone.humidity_sensors == ()


# Structural rules count an area as a source


def test_a_zone_whose_areas_resolve_nothing_compiles() -> None:
    configuration = plant_configuration_from_entry_data(
        _data(cooling=True, areas=[{"area_id": "kitchen"}])
    )

    compiled = compile_topology(configuration)
    assert compiled.zones[ZONE_ID].areas == (ZoneArea("kitchen"),)


def test_cooling_still_needs_a_temperature_and_a_humidity_source() -> None:
    with pytest.raises(CoolingObservationError) as caught:
        compile_topology(
            plant_configuration_from_entry_data(
                _data(cooling=True, temperature_sensor_metadata=[{"entity_id": "sensor.t"}])
            )
        )
    assert caught.value.observation == "humidity"

    external = _data(
        cooling=True,
        thermostat={"kind": "external_climate", "entity_id": "climate.zone"},
        humidity_sensor_metadata=[{"entity_id": "sensor.h"}],
    )
    with pytest.raises(CoolingObservationError) as caught:
        compile_topology(plant_configuration_from_entry_data(external))
    assert caught.value.observation == "temperature"


@pytest.mark.parametrize(
    ("areas", "message"),
    [
        ((ZoneArea("kitchen"), ZoneArea("kitchen")), "areas must not contain duplicates"),
        ((ZoneArea(""),), "areas must be non-empty area ids"),
        ((ZoneArea("kitchen", weight=0),), "area kitchen weight"),
        ((ZoneArea("kitchen", max_age_seconds=float("inf")),), "area kitchen maximum age"),
        ((ZoneArea("kitchen", required=1),), "area kitchen settings"),  # type: ignore[arg-type]
    ],
)
def test_topology_rejects_malformed_area_declarations(
    areas: tuple[ZoneArea, ...], message: str
) -> None:
    configuration = plant_configuration_from_entry_data(_data(areas=[{"area_id": "hall"}]))
    zone = configuration.zones[0]
    object.__setattr__(zone, "areas", areas)

    with pytest.raises(TopologyValidationError, match=message):
        compile_topology(configuration)


def test_topology_requires_a_temperature_source_of_a_hydronicus_thermostat() -> None:
    configuration = plant_configuration_from_entry_data(_data(areas=[{"area_id": "hall"}]))
    object.__setattr__(configuration.zones[0], "areas", ())

    with pytest.raises(TopologyValidationError, match="temperature sensor or area"):
        compile_topology(configuration)


def test_topology_designated_reference_aggregation_counts_a_designated_area() -> None:
    configuration = plant_configuration_from_entry_data(
        _data(
            temperature_aggregation="designated_reference",
            areas=[{"area_id": "hall", "designated_reference": True}],
        )
    )
    compile_topology(configuration)
    object.__setattr__(configuration.zones[0], "areas", (ZoneArea("hall"),))

    with pytest.raises(TopologyValidationError, match="exactly one"):
        compile_topology(configuration)


# The controller aggregates resolved records like explicit ones


def _snapshot(**temperatures: float) -> PlantSnapshot:
    return PlantSnapshot(
        temperatures={
            entity_id: NumericObservation(value, NOW) for entity_id, value in temperatures.items()
        },
        thermostats={
            ZONE_ID: HydronicusThermostatState(
                target_temperature=21.0, hvac_mode=ThermostatHvacMode.HEAT
            )
        },
    )


def test_resolved_area_sensors_are_aggregated_with_their_settings() -> None:
    zone = _zone(
        _data(
            temperature_aggregation="weighted_mean",
            areas=[{"area_id": "kitchen", "weight": 3}, {"area_id": "hall"}],
        ),
        kitchen=AreaSensors("sensor.kitchen_t"),
        hall=AreaSensors("sensor.hall_t"),
    )

    result = aggregate_temperature(
        zone, _snapshot(**{"sensor.kitchen_t": 20.0, "sensor.hall_t": 24.0}), now=NOW
    )
    assert result.value == pytest.approx(21.0)

    # An area temperature sensor is optional by default, so one flat battery
    # does not stop the other areas from heating.
    result = aggregate_temperature(zone, _snapshot(**{"sensor.hall_t": 19.0}), now=NOW)
    assert result.value == 19.0
    assert result.excluded_optional_sensor_ids == ("sensor.kitchen_t",)
    assert zone.aggregation is TemperatureAggregation.WEIGHTED_MEAN


def test_a_zone_left_without_a_reading_is_blocked() -> None:
    configuration = plant_configuration_from_entry_data(_data(areas=[{"area_id": "kitchen"}]))
    plant = compile_topology(configuration)

    evaluation = evaluate(plant, _snapshot(), RuntimeState(), NOW)

    decision = evaluation.diagnostics.zone_decisions[ZONE_ID]
    assert decision.status is ZoneDecisionStatus.SENSOR_BLOCKED
    assert decision.demand is False
    assert decision.explanation == "Blocked: no usable temperature sensors remain."


def test_area_sensors_are_bindings_of_their_area() -> None:
    configuration = plant_configuration_from_entry_data(
        _data(
            temperature_sensor_metadata=[{"entity_id": "sensor.probe"}],
            areas=[{"area_id": "kitchen"}],
        ),
        area_sensors={"kitchen": AreaSensors("sensor.kitchen_t", "sensor.kitchen_h")},
    )
    bindings = {
        binding.entity_id: binding
        for binding in configured_entity_bindings(compile_topology(configuration))
        if binding.object_type == "zone"
    }

    assert bindings["sensor.probe"].area_id is None
    assert bindings["sensor.probe"].binding_key == "temperature_sensor_0"
    assert (bindings["sensor.kitchen_t"].area_id, bindings["sensor.kitchen_t"].binding_key) == (
        "kitchen",
        "area_temperature_sensor_kitchen",
    )
    assert bindings["sensor.kitchen_t"].label == "area temperature sensor"
    assert bindings["sensor.kitchen_t"].required is False
    assert (bindings["sensor.kitchen_h"].area_id, bindings["sensor.kitchen_h"].binding_key) == (
        "kitchen",
        "area_humidity_sensor_kitchen",
    )


def test_resolution_does_not_change_the_stored_data() -> None:
    data = _data(areas=[{"area_id": "kitchen"}])
    before = deepcopy(data)

    plant_configuration_from_entry_data(data, area_sensors={"kitchen": AreaSensors("sensor.k")})

    assert data == before


# Resolution never breaks a Plant


def _bound_entity_ids(value: Any) -> set[str]:
    """Return every string in stored data that looks like an entity ID."""
    if isinstance(value, dict):
        return {entity for item in value.values() for entity in _bound_entity_ids(item)}
    if isinstance(value, list):
        return {entity for item in value for entity in _bound_entity_ids(item)}
    return {value} if isinstance(value, str) and "." in value else set()


@settings(max_examples=200, deadline=None)
@given(data=st.data(), stored=stored_plants(min_zones=1))
def test_any_resolution_of_the_covered_areas_compiles(data: st.DataObject, stored: Any) -> None:
    """Whatever the areas name, even entities the Plant binds elsewhere, the Plant compiles."""
    compile_topology(plant_configuration_from_entry_data(stored))
    candidates = sorted(_bound_entity_ids(stored["topology"]) | {"sensor.area_a", "sensor.area_b"})
    entity = st.one_of(st.none(), st.sampled_from(candidates))
    area_sensors = data.draw(
        st.dictionaries(
            st.sampled_from(("living_room", "kitchen", "hall", "bedroom")),
            st.builds(AreaSensors, entity, entity),
        )
    )

    configuration = plant_configuration_from_entry_data(stored, area_sensors=area_sensors)

    compiled = compile_topology(configuration)
    for zone in compiled.zones.values():
        for records in (zone.temperature_sensor_metadata, zone.humidity_sensor_metadata):
            entity_ids = [record.entity_id for record in records]
            assert len(entity_ids) == len(set(entity_ids))
        assert sum(record.designated_reference for record in zone.temperature_sensor_metadata) <= 1
