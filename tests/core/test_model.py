"""Tests for the frozen cross-milestone controller contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from hydronicus_core.model import (
    ActuatorAction,
    ActuatorCommand,
    Circuit,
    CompiledPlant,
    DeliveryRoute,
    InterlockStatus,
    PlantMode,
    PlantSnapshot,
    RuntimeState,
    SafetyInterlockResult,
    SourceRecommendation,
    Valve,
    ValveRuntime,
    ValveState,
)


def test_actuator_commands_retain_explicit_actions() -> None:
    """Typed actions remain unchanged at the executor contract."""
    command = ActuatorCommand("valve", ActuatorAction.OPEN, "needs heat")

    assert command.action is ActuatorAction.OPEN


def test_wave_one_extensions_are_optional_for_heating_callers() -> None:
    """Existing heating evaluations can omit cooling and source observations."""
    snapshot = PlantSnapshot(temperatures={})
    runtime = RuntimeState()
    interlock = SafetyInterlockResult("dew-point", InterlockStatus.PERMITTED, "safe")
    recommendation = SourceRecommendation("buffer", "Buffer is eligible", ("buffer",))

    assert snapshot.humidities == {}
    assert runtime.plant_mode is PlantMode.IDLE
    assert interlock.permits is True
    assert recommendation.source_id == "buffer"


def test_valve_readiness_is_explicit_and_immutable() -> None:
    """Canonical readiness configuration and runtime state remain immutable."""
    valve = Valve(
        "valve",
        "Valve",
        "switch.valve",
        readiness_entity_id="binary_sensor.valve_ready",
    )
    assert valve.readiness_entity_id == "binary_sensor.valve_ready"
    assert ValveRuntime(ValveState.OPEN, datetime(2026, 7, 17, tzinfo=UTC), True).is_ready is True
    assert ValveRuntime(ValveState.OPEN, None, False).is_ready is False


def test_a_zone_can_cool_only_through_an_enabled_route_to_a_cooling_circuit() -> None:
    """Cool modes and cooling entities share one notion of a room that can cool."""
    plant = CompiledPlant(
        id="plant",
        zones={},
        valves={},
        pumps={},
        circuits={
            "floor": Circuit("floor", "Floor", ("valve",), "pump"),
            "ceiling": Circuit("ceiling", "Ceiling", ("valve",), "pump", cooling_enabled=True),
        },
        routes=(
            DeliveryRoute("heating", "heated", "floor"),
            DeliveryRoute("cooling", "cooled", "ceiling"),
            DeliveryRoute("mixed-floor", "mixed", "floor"),
            DeliveryRoute("mixed-ceiling", "mixed", "ceiling"),
            DeliveryRoute("disabled", "disabled", "ceiling", enabled=False),
        ),
        logic_summary=(),
    )

    assert plant.zone_can_cool("cooled") is True
    assert plant.zone_can_cool("mixed") is True
    assert plant.zone_can_cool("heated") is False
    assert plant.zone_can_cool("disabled") is False
    assert plant.zone_can_cool("unknown") is False
