"""Tests for the pure topology compiler."""

from __future__ import annotations

import math

import pytest
from hydronicus_core.model import (
    Circuit,
    DeliveryRoute,
    ExternalClimateThermostatConfig,
    PlantConfiguration,
    Pump,
    Source,
    TemperatureAggregation,
    TemperatureSensorMetadata,
    Valve,
    Zone,
)
from hydronicus_core.topology import (
    CoolingObservationError,
    CoolingReferenceError,
    DuplicateActuatorBindingError,
    TopologyValidationError,
    compile_topology,
)


def _metadata(*entity_ids: str) -> tuple[TemperatureSensorMetadata, ...]:
    return tuple(TemperatureSensorMetadata(entity_id) for entity_id in entity_ids)


def test_compile_topology_produces_summary() -> None:
    """A valid topology should compile into a deterministic summary."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                id="zone-1",
                name="Living room",
                target_temperature=21.5,
                temperature_sensor_metadata=_metadata("sensor.living_room_temperature"),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(
            Circuit(
                id="circuit-1",
                name="Floor loop",
                valve_ids=("valve-1",),
                pump_id="pump-1",
            ),
        ),
        routes=(DeliveryRoute(id="route-1", zone_id="zone-1", circuit_id="circuit-1"),),
    )

    compiled = compile_topology(plant)

    assert compiled.id == "plant-1"
    assert compiled.logic_summary == (
        "Floor loop opens Floor valve, then starts Floor pump.",
        "Living room is heated by Floor loop.",
    )


def test_compile_topology_explains_multi_route_and_shared_equipment() -> None:
    """The preview should make shared hydraulic ownership understandable."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "living",
                "Living room",
                21.0,
                _metadata(
                    "sensor.living_temperature",
                ),
            ),
            Zone(
                "office",
                "Office",
                20.0,
                _metadata(
                    "sensor.office_temperature",
                ),
            ),
        ),
        valves=(Valve("shared", "Shared valve", "switch.shared_valve"),),
        pumps=(Pump("pump", "Shared pump", "switch.shared_pump"),),
        circuits=(
            Circuit("floor", "Floor loop", ("shared",), "pump"),
            Circuit("ceiling", "Ceiling loop", ("shared",), "pump"),
        ),
        routes=(
            DeliveryRoute("living-floor", "living", "floor"),
            DeliveryRoute("living-ceiling", "living", "ceiling"),
            DeliveryRoute("office-floor", "office", "floor"),
        ),
    )

    compiled = compile_topology(plant)

    assert compiled.logic_summary == (
        "Floor loop opens Shared valve, then starts Shared pump.",
        "Ceiling loop opens Shared valve, then starts Shared pump.",
        "Living room is heated by Floor loop and Ceiling loop.",
        "Office is heated by Floor loop.",
        "Valve Shared valve is shared by loops Floor loop, Ceiling loop.",
        "Pump Shared pump is shared by loops Floor loop, Ceiling loop.",
    )
    # Warnings name the loops in configuration order, like the summary, and keep ids sorted.
    assert [(warning.circuit_ids, warning.message) for warning in compiled.warnings] == [
        (
            ("ceiling", "floor"),
            "Valve Shared valve is shared by loops Floor loop, Ceiling loop; separate room "
            "thermostats cannot independently control loops coupled by the same physical valve.",
        ),
        (
            ("ceiling", "floor"),
            "Pump Shared pump is shared by loops Floor loop, Ceiling loop; separate room "
            "thermostats cannot independently control heating and cooling through the same pump.",
        ),
    ]


def test_compile_topology_emits_stable_non_fatal_shared_valve_warning() -> None:
    """Shared-valve coupling is diagnostic, not a topology rejection."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "living",
                "Living room",
                21.0,
                _metadata(
                    "sensor.living_temperature",
                ),
            ),
            Zone(
                "office",
                "Office",
                20.0,
                _metadata(
                    "sensor.office_temperature",
                ),
            ),
        ),
        valves=(Valve("shared", "Shared valve", "switch.shared_valve"),),
        pumps=(
            Pump("floor-pump", "Floor pump", "switch.floor_pump"),
            Pump("ceiling-pump", "Ceiling pump", "switch.ceiling_pump"),
        ),
        circuits=(
            Circuit("floor", "Floor loop", ("shared",), "floor-pump"),
            Circuit("ceiling", "Ceiling loop", ("shared",), "ceiling-pump"),
        ),
        routes=(
            DeliveryRoute("living-floor", "living", "floor"),
            DeliveryRoute("office-ceiling", "office", "ceiling"),
        ),
    )

    compiled = compile_topology(plant)

    assert len(compiled.warnings) == 1
    warning = compiled.warnings[0]
    assert warning.code == "shared_valve_limits_independent_control"
    assert warning.valve_id == "shared"
    assert warning.circuit_ids == ("ceiling", "floor")
    assert warning.zone_ids == ("living", "office")
    assert "cannot independently control" in warning.message


def test_compile_topology_validates_first_class_sensor_metadata() -> None:
    """Reference selection, age, and calibration metadata are topology inputs."""
    base = dict(
        id="plant-1",
        valves=(Valve("valve", "Valve", "switch.valve"),),
        pumps=(Pump("pump", "Pump", "switch.pump"),),
        circuits=(Circuit("circuit", "Circuit", ("valve",), "pump"),),
        routes=(DeliveryRoute("route", "zone", "circuit"),),
    )
    multiple_reference = PlantConfiguration(
        **base,
        zones=(
            Zone(
                "zone",
                "Zone",
                21.0,
                temperature_sensor_metadata=(
                    TemperatureSensorMetadata("sensor.a", designated_reference=True),
                    TemperatureSensorMetadata("sensor.b", designated_reference=True),
                ),
                aggregation=TemperatureAggregation.DESIGNATED_REFERENCE,
            ),
        ),
    )

    with pytest.raises(TopologyValidationError, match="multiple designated reference"):
        compile_topology(multiple_reference)

    invalid_age = PlantConfiguration(
        **base,
        zones=(
            Zone(
                "zone",
                "Zone",
                21.0,
                temperature_sensor_metadata=(
                    TemperatureSensorMetadata("sensor.a", max_age_seconds=0),
                ),
            ),
        ),
    )
    with pytest.raises(TopologyValidationError, match="maximum age must be positive"):
        compile_topology(invalid_age)


def test_compile_topology_rejects_duplicate_delivery_route_relationships() -> None:
    """A zone-to-circuit relationship must have one stable route identity."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                _metadata(
                    "sensor.living_temperature",
                ),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(
            DeliveryRoute("route-1", "zone-1", "circuit-1"),
            DeliveryRoute("route-2", "zone-1", "circuit-1", enabled=False),
        ),
    )

    with pytest.raises(
        TopologyValidationError,
        match="Duplicate delivery routes: zone-1 -> circuit-1",
    ):
        compile_topology(plant)


def test_compile_topology_rejects_orphans() -> None:
    """A topology with unreferenced objects should fail closed."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                id="zone-1",
                name="Living room",
                target_temperature=21.5,
                temperature_sensor_metadata=_metadata("sensor.living_room_temperature"),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(
            Circuit(
                id="circuit-1",
                name="Floor loop",
                valve_ids=("valve-1",),
                pump_id="pump-1",
            ),
        ),
        routes=tuple(),
    )

    with pytest.raises(TopologyValidationError, match="orphaned zones"):
        compile_topology(plant)


def test_compile_topology_rejects_unknown_actuator_relationships() -> None:
    """Circuit relationships must resolve to topology-owned actuator ids."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                _metadata(
                    "sensor.living_temperature",
                ),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("missing-valve",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(TopologyValidationError, match="unknown valves: missing-valve"):
        compile_topology(plant)


def test_compile_topology_rejects_unknown_pump_relationship() -> None:
    """A circuit pump relationship must resolve to a topology-owned pump id."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                _metadata(
                    "sensor.living_temperature",
                ),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "missing-pump"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(TopologyValidationError, match="unknown pump missing-pump"):
        compile_topology(plant)


def _unused(compiled) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Return unused-equipment warnings as equipment id -> (kind, circuit ids)."""
    return {
        str(warning.equipment_id): (str(warning.equipment_kind), warning.circuit_ids)
        for warning in compiled.warnings
        if warning.code == "unused_equipment"
    }


def test_unused_valve_and_pump_compile_with_warnings() -> None:
    """Plant equipment that no route reaches is reported, not rejected."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(Zone("zone-1", "Living room", 21.5, _metadata("sensor.living_temperature")),),
        valves=(
            Valve("valve-1", "Floor valve", "switch.floor_valve"),
            Valve("valve-2", "Unused valve", "switch.unused_valve"),
        ),
        pumps=(
            Pump("pump-1", "Floor pump", "switch.floor_pump"),
            Pump("pump-2", "Unused pump", "switch.unused_pump"),
        ),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    compiled = compile_topology(plant)

    assert _unused(compiled) == {"valve-2": ("valve", ()), "pump-2": ("pump", ())}
    warning = next(w for w in compiled.warnings if w.equipment_id == "valve-2")
    assert warning.valve_id == "valve-2"
    assert warning.zone_ids == ()
    assert warning.message == (
        "Valve Unused valve is not reached by any room, so Hydronicus never requests it."
    )
    assert set(compiled.valves) == {"valve-1", "valve-2"}
    assert set(compiled.pumps) == {"pump-1", "pump-2"}


def test_unrouted_circuit_and_its_equipment_are_unused() -> None:
    """A circuit without an enabled route leaves its valves and pump unreached."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(Zone("zone-1", "Living room", 21.5, _metadata("sensor.living_temperature")),),
        valves=(
            Valve("valve-1", "Floor valve", "switch.floor_valve"),
            Valve("valve-2", "Spare valve", "switch.spare_valve"),
            Valve("valve-3", "Disabled valve", "switch.disabled_valve"),
        ),
        pumps=(
            Pump("pump-1", "Floor pump", "switch.floor_pump"),
            Pump("pump-2", "Spare pump", "switch.spare_pump"),
        ),
        circuits=(
            Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),
            Circuit("circuit-2", "Spare loop", ("valve-2", "valve-1"), "pump-2"),
            Circuit("circuit-3", "Disabled loop", ("valve-3",), "pump-1"),
        ),
        routes=(
            DeliveryRoute("route-1", "zone-1", "circuit-1"),
            DeliveryRoute("route-3", "zone-1", "circuit-3", enabled=False),
        ),
    )

    compiled = compile_topology(plant)

    assert _unused(compiled) == {
        "circuit-2": ("circuit", ("circuit-2",)),
        "circuit-3": ("circuit", ("circuit-3",)),
        "valve-2": ("valve", ("circuit-2",)),
        "valve-3": ("valve", ("circuit-3",)),
        "pump-2": ("pump", ("circuit-2",)),
    }
    assert [route.id for route in compiled.routes] == ["route-1"]
    assert (
        "Spare loop opens Spare valve and Floor valve, then starts Spare pump."
        in compiled.logic_summary
    )
    loop_warning = next(w for w in compiled.warnings if w.equipment_id == "circuit-3")
    assert loop_warning.message == (
        "Loop Disabled loop is not reached by any room, so Hydronicus never requests it."
    )


def test_zone_without_enabled_route_is_still_rejected() -> None:
    """Only equipment may be unused; a zone must be able to request heat."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(Zone("zone-1", "Living room", 21.5, _metadata("sensor.living_temperature")),),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1", enabled=False),),
    )

    with pytest.raises(TopologyValidationError, match="orphaned zones: zone-1.$"):
        compile_topology(plant)


def test_plant_without_zones_compiles() -> None:
    """An empty Plant, or one holding only equipment, is valid and requests nothing."""
    empty = compile_topology(
        PlantConfiguration(id="plant-1", zones=(), valves=(), pumps=(), circuits=(), routes=())
    )
    equipment_only = compile_topology(
        PlantConfiguration(
            id="plant-1",
            zones=(),
            valves=(),
            pumps=(Pump("pump-1", "Manifold pump", "switch.manifold_pump"),),
            circuits=(),
            routes=(),
        )
    )

    assert empty.warnings == ()
    assert _unused(equipment_only) == {"pump-1": ("pump", ())}


def test_compile_topology_rejects_duplicate_actuator_ids() -> None:
    """Actuator relationship ids must be globally unambiguous within their type."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                _metadata(
                    "sensor.living_temperature",
                ),
            ),
        ),
        valves=(
            Valve("valve-1", "First valve", "switch.first_valve"),
            Valve("valve-1", "Second valve", "switch.second_valve"),
        ),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(TopologyValidationError, match="Duplicate valve ids: valve-1"):
        compile_topology(plant)


def test_compile_topology_rejects_duplicate_pump_ids() -> None:
    """Pump relationship ids must be globally unambiguous."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                _metadata(
                    "sensor.living_temperature",
                ),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(
            Pump("pump-1", "First pump", "switch.first_pump"),
            Pump("pump-1", "Second pump", "switch.second_pump"),
        ),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(TopologyValidationError, match="Duplicate pump ids: pump-1"):
        compile_topology(plant)


def test_compile_topology_rejects_circuit_without_valves() -> None:
    """A circuit without a valve cannot be sequenced safely."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                _metadata(
                    "sensor.living_temperature",
                ),
            ),
        ),
        valves=(),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", (), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(
        TopologyValidationError, match="Circuit circuit-1 requires at least one valve"
    ):
        compile_topology(plant)


@pytest.mark.parametrize("target_temperature", [math.inf, -math.inf, math.nan])
def test_compile_topology_rejects_non_finite_zone_target(
    target_temperature: float,
) -> None:
    """Zone demand thresholds must remain finite and deterministic."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                target_temperature,
                ("sensor.living_temperature",),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(
        TopologyValidationError,
        match="Zone zone-1 target temperature must be finite",
    ):
        compile_topology(plant)


@pytest.mark.parametrize("target_temperature", [4.9, 35.1])
def test_compile_topology_rejects_out_of_range_zone_target(
    target_temperature: float,
) -> None:
    """Stored targets must stay within the climate entity's public range."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                target_temperature,
                ("sensor.living_temperature",),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(
        TopologyValidationError,
        match="Zone zone-1 target temperature must be between 5 and 35",
    ):
        compile_topology(plant)


def test_compile_topology_rejects_duplicate_zone_temperature_sensors() -> None:
    """One physical reading must not receive accidental double aggregation weight."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                _metadata("sensor.living_temperature", "sensor.living_temperature"),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(
        TopologyValidationError,
        match="Zone zone-1 temperature sensors must not contain duplicates",
    ):
        compile_topology(plant)


def test_compile_topology_rejects_zone_without_temperature_sensors() -> None:
    """Every zone needs at least one observation before demand can be evaluated."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(Zone("zone-1", "Living room", 21.5, _metadata()),),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(
        TopologyValidationError,
        match="Zone zone-1 requires at least one temperature sensor",
    ):
        compile_topology(plant)


def test_compile_topology_rejects_blank_temperature_sensor_id() -> None:
    """Every configured observation must identify a real Home Assistant entity."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                _metadata(
                    "",
                ),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(
        TopologyValidationError,
        match="Zone zone-1 temperature sensors must be non-empty entity ids",
    ):
        compile_topology(plant)


@pytest.mark.parametrize("opening_time", [-1.0, math.inf, math.nan])
def test_compile_topology_rejects_unsafe_valve_timing(opening_time: float) -> None:
    """Valve readiness timing must be finite and non-negative."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                _metadata(
                    "sensor.living_temperature",
                ),
            ),
        ),
        valves=(
            Valve(
                "valve-1",
                "Floor valve",
                "switch.floor_valve",
                opening_time_seconds=opening_time,
            ),
        ),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(
        TopologyValidationError, match="Valve valve-1 opening time must be finite and non-negative"
    ):
        compile_topology(plant)


@pytest.mark.parametrize("overrun", [-1.0, math.inf, math.nan])
def test_compile_topology_rejects_unsafe_pump_timing(overrun: float) -> None:
    """Pump overrun timing must be finite and non-negative."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                _metadata(
                    "sensor.living_temperature",
                ),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(
            Pump(
                "pump-1",
                "Floor pump",
                "switch.floor_pump",
                overrun_seconds=overrun,
            ),
        ),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(
        TopologyValidationError, match="Pump pump-1 overrun must be finite and non-negative"
    ):
        compile_topology(plant)


def test_compile_topology_rejects_duplicate_physical_actuator_bindings() -> None:
    """One physical HA entity must compile to one actuator state machine."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                _metadata(
                    "sensor.living_temperature",
                ),
            ),
        ),
        valves=(
            Valve("valve-1", "First valve", "switch.shared_valve"),
            Valve("valve-2", "Second valve", "switch.shared_valve"),
        ),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(
        TopologyValidationError,
        match="Duplicate actuator entity bindings: switch.shared_valve",
    ):
        compile_topology(plant)


def test_compile_topology_rejects_unknown_temperature_aggregation() -> None:
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                ("sensor.living_temperature",),
                aggregation="trimmed_mean",
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(
        TopologyValidationError,
        match="Zone zone-1 temperature aggregation must be a supported policy",
    ):
        compile_topology(plant)


def test_compile_topology_rejects_invalid_temperature_sensor_weights() -> None:
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                "zone-1",
                "Living room",
                21.5,
                (TemperatureSensorMetadata("sensor.living_temperature", weight=0),),
            ),
        ),
        valves=(Valve("valve-1", "Floor valve", "switch.floor_valve"),),
        pumps=(Pump("pump-1", "Floor pump", "switch.floor_pump"),),
        circuits=(Circuit("circuit-1", "Floor loop", ("valve-1",), "pump-1"),),
        routes=(DeliveryRoute("route-1", "zone-1", "circuit-1"),),
    )

    with pytest.raises(
        TopologyValidationError,
        match="Zone zone-1 temperature sensor weights must be positive and finite",
    ):
        compile_topology(plant)


def _metadata_plant(
    zone: Zone, *, routes: tuple[DeliveryRoute, ...] | None = None
) -> PlantConfiguration:
    """Build the smallest topology needed for metadata validation tests."""
    return PlantConfiguration(
        id="metadata-plant",
        zones=(zone,),
        valves=(Valve("valve", "Valve", "switch.valve"),),
        pumps=(Pump("pump", "Pump", "switch.pump"),),
        circuits=(Circuit("circuit", "Circuit", ("valve",), "pump"),),
        routes=routes or (DeliveryRoute("route", zone.id, "circuit"),),
    )


@pytest.mark.parametrize(
    ("zone_kwargs", "message"),
    [
        (
            {"heating_start_delta": -1},
            "heating hysteresis deltas",
        ),
        (
            {"minimum_active_duration_seconds": -1},
            "minimum active duration",
        ),
        (
            {"minimum_idle_duration_seconds": math.inf},
            "minimum idle duration",
        ),
        (
            {
                "temperature_sensor_metadata": (
                    TemperatureSensorMetadata("sensor", calibration_offset=math.inf),
                )
            },
            "calibration offset",
        ),
        (
            {
                "temperature_sensor_metadata": (
                    TemperatureSensorMetadata("sensor", designated_reference=1),
                )
            },
            "reference status",
        ),
    ],
)
def test_compile_topology_rejects_unsafe_zone_metadata(
    zone_kwargs: dict[str, object], message: str
) -> None:
    fields = dict(zone_kwargs)
    metadata = fields.pop("temperature_sensor_metadata", _metadata("sensor"))
    zone = Zone(
        "zone",
        "Zone",
        21.0,
        temperature_sensor_metadata=metadata,
        **fields,
    )

    with pytest.raises(TopologyValidationError, match=message):
        compile_topology(_metadata_plant(zone))


def test_compile_topology_requires_reference_for_designated_policy() -> None:
    zone = Zone(
        "zone",
        "Zone",
        21.0,
        temperature_sensor_metadata=(TemperatureSensorMetadata("sensor"),),
        aggregation=TemperatureAggregation.DESIGNATED_REFERENCE,
    )

    with pytest.raises(TopologyValidationError, match="requires exactly one"):
        compile_topology(_metadata_plant(zone))


@pytest.mark.parametrize(
    ("preset_targets", "message"),
    [
        ({"holiday": 20.0}, "unsupported preset target"),
        ({"none": 20.0}, "unsupported preset target"),
        ({"comfort": math.nan}, "preset target comfort must be finite"),
        ({"comfort": 4.9}, "preset target comfort must be between 5 and 35"),
        ({"eco": 35.1}, "preset target eco must be between 5 and 35"),
    ],
)
def test_compile_topology_validates_preset_targets(
    preset_targets: dict[str, float], message: str
) -> None:
    zone = Zone("zone", "Zone", 21.0, _metadata("sensor"), preset_targets=preset_targets)

    with pytest.raises(TopologyValidationError, match=message):
        compile_topology(_metadata_plant(zone))


def test_compile_topology_rejects_blank_bindings_and_unknown_routes() -> None:
    blank_binding = PlantConfiguration(
        id="plant",
        zones=(
            Zone(
                "zone",
                "Zone",
                21.0,
                _metadata(
                    "sensor",
                ),
            ),
        ),
        valves=(Valve("valve", "Valve", " "),),
        pumps=(Pump("pump", "Pump", "switch.pump"),),
        circuits=(Circuit("circuit", "Circuit", ("valve",), "pump"),),
        routes=(DeliveryRoute("route", "zone", "circuit"),),
    )
    with pytest.raises(TopologyValidationError, match="non-empty entity binding"):
        compile_topology(blank_binding)

    unknown_zone = _metadata_plant(
        Zone(
            "zone",
            "Zone",
            21.0,
            _metadata(
                "sensor",
            ),
        ),
        routes=(DeliveryRoute("route", "missing", "circuit"),),
    )
    with pytest.raises(TopologyValidationError, match="unknown zone missing"):
        compile_topology(unknown_zone)

    unknown_circuit = _metadata_plant(
        Zone(
            "zone",
            "Zone",
            21.0,
            _metadata(
                "sensor",
            ),
        ),
        routes=(DeliveryRoute("route", "zone", "missing"),),
    )
    with pytest.raises(TopologyValidationError, match="unknown circuit missing"):
        compile_topology(unknown_circuit)


def test_compile_topology_accepts_a_disabled_route_when_other_routes_cover_the_graph() -> None:
    plant = PlantConfiguration(
        id="plant",
        zones=(
            Zone(
                "living",
                "Living",
                21.0,
                _metadata(
                    "sensor.living",
                ),
            ),
            Zone(
                "office",
                "Office",
                21.0,
                _metadata(
                    "sensor.office",
                ),
            ),
        ),
        valves=(
            Valve("valve", "Valve", "switch.valve"),
            Valve("valve-two", "Valve two", "switch.valve_two"),
        ),
        pumps=(
            Pump("pump", "Pump", "switch.pump"),
            Pump("pump-two", "Pump two", "switch.pump_two"),
        ),
        circuits=(
            Circuit("circuit", "Circuit", ("valve",), "pump"),
            Circuit("circuit-two", "Circuit two", ("valve-two",), "pump-two"),
        ),
        routes=(
            DeliveryRoute("living-route", "living", "circuit"),
            DeliveryRoute("office-route", "office", "circuit-two"),
            DeliveryRoute("disabled-route", "living", "circuit-two", enabled=False),
        ),
    )

    compiled = compile_topology(plant)

    assert compiled.routes == (
        DeliveryRoute("living-route", "living", "circuit"),
        DeliveryRoute("office-route", "office", "circuit-two"),
    )


def test_compile_topology_accepts_cooling_references_and_metadata() -> None:
    """Cooling compatibility is explicit and non-cooling circuits remain unchanged."""
    zone = Zone(
        "zone",
        "Zone",
        24.0,
        temperature_sensor_metadata=(TemperatureSensorMetadata("sensor.temperature"),),
        humidity_sensor_metadata=(TemperatureSensorMetadata("sensor.humidity"),),
    )
    plant = PlantConfiguration(
        id="cooling",
        zones=(zone,),
        valves=(Valve("valve", "Valve", "switch.valve"),),
        pumps=(Pump("pump", "Pump", "switch.pump"),),
        circuits=(
            Circuit(
                "circuit",
                "Circuit",
                ("valve",),
                "pump",
                cooling_enabled=True,
                surface_temperature_sensor="sensor.surface",
            ),
        ),
        routes=(DeliveryRoute("route", "zone", "circuit"),),
    )

    compiled = compile_topology(plant)

    assert compiled.circuits["circuit"].cooling_enabled is True
    assert "Zone is heated and cooled by Circuit." in compiled.logic_summary


def test_compile_topology_names_the_cooling_loops_of_a_room() -> None:
    """A room served by heating-only and cooling loops says which loops also cool it."""
    zone = Zone(
        "zone",
        "Living",
        22.0,
        temperature_sensor_metadata=(TemperatureSensorMetadata("sensor.temperature"),),
        humidity_sensor_metadata=(TemperatureSensorMetadata("sensor.humidity"),),
    )
    plant = PlantConfiguration(
        id="mixed",
        zones=(zone,),
        valves=(
            Valve("floor-valve", "Floor valve", "switch.floor_valve"),
            Valve("ceiling-valve", "Ceiling valve", "switch.ceiling_valve"),
        ),
        pumps=(Pump("pump", "Circulation pump", "switch.pump"),),
        circuits=(
            Circuit("floor", "Floor loop", ("floor-valve",), "pump"),
            Circuit(
                "ceiling",
                "Ceiling loop",
                ("ceiling-valve",),
                "pump",
                cooling_enabled=True,
                supply_temperature_sensor="sensor.supply",
            ),
        ),
        routes=(
            DeliveryRoute("floor-route", "zone", "floor"),
            DeliveryRoute("ceiling-route", "zone", "ceiling"),
        ),
    )

    compiled = compile_topology(plant)

    assert compiled.logic_summary[:3] == (
        "Floor loop opens Floor valve, then starts Circulation pump.",
        "Ceiling loop opens Ceiling valve, then starts Circulation pump.",
        "Living is heated by Floor loop and Ceiling loop, and cooled by Ceiling loop.",
    )


def test_compile_topology_warns_for_shared_pumps_and_sources() -> None:
    """Mode-coupled pump and source paths remain valid but explain their limits."""
    plant = PlantConfiguration(
        id="coupled-modes",
        zones=(
            Zone(
                "heating-zone",
                "Heating",
                21.0,
                _metadata(
                    "sensor.heating",
                ),
            ),
            Zone(
                "cooling-zone",
                "Cooling",
                24.0,
                temperature_sensor_metadata=(TemperatureSensorMetadata("sensor.cooling"),),
                humidity_sensor_metadata=(TemperatureSensorMetadata("sensor.humidity"),),
            ),
        ),
        valves=(
            Valve("heating-valve", "Heating valve", "switch.heating_valve"),
            Valve("cooling-valve", "Cooling valve", "switch.cooling_valve"),
        ),
        pumps=(Pump("shared-pump", "Shared pump", "switch.shared_pump"),),
        circuits=(
            Circuit("heating", "Heating circuit", ("heating-valve",), "shared-pump"),
            Circuit(
                "cooling",
                "Cooling circuit",
                ("cooling-valve",),
                "shared-pump",
                cooling_enabled=True,
                supply_temperature_sensor="sensor.supply",
            ),
        ),
        routes=(
            DeliveryRoute("heating-route", "heating-zone", "heating"),
            DeliveryRoute("cooling-route", "cooling-zone", "cooling"),
        ),
        sources=(Source("source", "Plant source"),),
    )

    compiled = compile_topology(plant)

    assert [
        (warning.code, warning.equipment_kind, warning.equipment_id)
        for warning in compiled.warnings
    ] == [
        ("shared_pump_limits_independent_control", "pump", "shared-pump"),
        ("shared_source_limits_independent_control", "source", "source"),
    ]
    assert all("independently" in warning.message for warning in compiled.warnings)
    assert compiled.warnings[1].message == (
        "Source Plant source is shared by the Plant; separate room thermostats cannot "
        "independently change heating and cooling source mode."
    )


@pytest.mark.parametrize(
    ("circuit_kwargs", "message"),
    [
        ({"cooling_enabled": True}, "supply or surface"),
        (
            {
                "cooling_enabled": True,
                "supply_temperature_sensor": "sensor.supply",
                "condensation_margin": -1,
            },
            "condensation margin",
        ),
        (
            {
                "cooling_enabled": True,
                "supply_temperature_sensor": "sensor.supply",
                "supply_temperature_max_age_seconds": 0,
            },
            "supply reference maximum age",
        ),
    ],
)
def test_compile_topology_rejects_unsafe_cooling_circuits(
    circuit_kwargs: dict[str, object], message: str
) -> None:
    """Cooling circuits cannot bypass reference or freshness configuration."""
    zone = Zone(
        "zone",
        "Zone",
        24.0,
        temperature_sensor_metadata=(TemperatureSensorMetadata("sensor.temperature"),),
        humidity_sensor_metadata=(TemperatureSensorMetadata("sensor.humidity"),),
    )
    circuit = Circuit("circuit", "Circuit", ("valve",), "pump", **circuit_kwargs)
    plant = PlantConfiguration(
        id="cooling",
        zones=(zone,),
        valves=(Valve("valve", "Valve", "switch.valve"),),
        pumps=(Pump("pump", "Pump", "switch.pump"),),
        circuits=(circuit,),
        routes=(DeliveryRoute("route", "zone", "circuit"),),
    )

    with pytest.raises(TopologyValidationError, match=message):
        compile_topology(plant)


def test_compile_topology_rejects_cooling_without_humidity_observation() -> None:
    """A cooling-enabled route cannot run without zone humidity topology."""
    plant = _metadata_plant(
        Zone(
            "zone",
            "Zone",
            24.0,
            _metadata(
                "sensor.temperature",
            ),
        ),
    )
    plant = PlantConfiguration(
        id=plant.id,
        zones=plant.zones,
        valves=plant.valves,
        pumps=plant.pumps,
        circuits=(
            Circuit(
                "circuit",
                "Circuit",
                ("valve",),
                "pump",
                cooling_enabled=True,
                supply_temperature_sensor="sensor.supply",
            ),
        ),
        routes=plant.routes,
    )

    with pytest.raises(TopologyValidationError, match="humidity observations"):
        compile_topology(plant)


def test_compile_topology_rejects_empty_valve_readiness_entity() -> None:
    """A configured feedback binding must remain an explicit non-empty entity ID."""
    plant = _metadata_plant(
        Zone(
            "zone",
            "Zone",
            21.0,
            _metadata(
                "sensor.temperature",
            ),
        )
    )
    plant = PlantConfiguration(
        id=plant.id,
        zones=plant.zones,
        valves=(Valve("valve", "Valve", "switch.valve", readiness_entity_id=" "),),
        pumps=plant.pumps,
        circuits=plant.circuits,
        routes=plant.routes,
    )

    with pytest.raises(TopologyValidationError, match="readiness feedback entity"):
        compile_topology(plant)


def _cooling_plant(zone: Zone, **circuit_kwargs: object) -> PlantConfiguration:
    return PlantConfiguration(
        id="cooling",
        zones=(zone,),
        valves=(Valve("valve", "Valve", "switch.valve"),),
        pumps=(Pump("pump", "Pump", "switch.pump"),),
        circuits=(Circuit("circuit", "Circuit", ("valve",), "pump", **circuit_kwargs),),
        routes=(DeliveryRoute("route", "zone", "circuit"),),
    )


def test_cooling_observation_errors_name_the_circuit_zone_and_observation() -> None:
    """Flows map a missing cooling observation to one form field without parsing text."""
    cooling: dict[str, object] = {
        "cooling_enabled": True,
        "supply_temperature_sensor": "sensor.supply",
    }
    no_humidity = Zone("zone", "Zone", 24.0, _metadata("sensor.temperature"))

    with pytest.raises(CoolingObservationError) as humidity:
        compile_topology(_cooling_plant(no_humidity, **cooling))
    assert (humidity.value.circuit_id, humidity.value.zone_id) == ("circuit", "zone")
    assert humidity.value.observation == "humidity"
    assert isinstance(humidity.value, TopologyValidationError)
    assert "requires humidity observations for zone zone" in str(humidity.value)

    no_temperature = Zone(
        "zone",
        "Zone",
        humidity_sensor_metadata=_metadata("sensor.humidity"),
        thermostat=ExternalClimateThermostatConfig("climate.zone"),
    )
    with pytest.raises(CoolingObservationError) as temperature:
        compile_topology(_cooling_plant(no_temperature, **cooling))
    assert temperature.value.observation == "temperature"


def test_cooling_reference_error_names_the_circuit() -> None:
    zone = Zone(
        "zone",
        "Zone",
        24.0,
        _metadata("sensor.temperature"),
        humidity_sensor_metadata=_metadata("sensor.humidity"),
    )

    with pytest.raises(CoolingReferenceError, match="supply or surface") as error:
        compile_topology(_cooling_plant(zone, cooling_enabled=True))
    assert error.value.circuit_id == "circuit"


def test_duplicate_binding_error_names_the_entities() -> None:
    zone = Zone("zone", "Zone", 21.0, _metadata("sensor.temperature"))
    duplicate = PlantConfiguration(
        id="plant",
        zones=(zone,),
        valves=(Valve("valve", "Valve", "switch.shared"),),
        pumps=(Pump("pump", "Pump", "switch.shared"),),
        circuits=(Circuit("circuit", "Circuit", ("valve",), "pump"),),
        routes=(DeliveryRoute("route", "zone", "circuit"),),
    )
    with pytest.raises(DuplicateActuatorBindingError) as binding:
        compile_topology(duplicate)
    assert binding.value.entity_ids == ("switch.shared",)
