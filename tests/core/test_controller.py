"""Tests for the deterministic shadow-mode heating sequence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hydronic_climate_core.controller import evaluate
from hydronic_climate_core.model import (
    Circuit,
    DeliveryRoute,
    PlantConfiguration,
    PlantSnapshot,
    PumpState,
    RuntimeState,
    TemperatureObservation,
    ValveState,
    Zone,
)
from hydronic_climate_core.topology import compile_topology

NOW = datetime(2026, 7, 17, tzinfo=UTC)


def _plant() -> PlantConfiguration:
    return PlantConfiguration(
        id="plant",
        zones=(Zone("living", "Living", 21.0, "temperature.living"),),
        circuits=(
            Circuit(
                "floor",
                "Floor",
                "valve.floor",
                "pump.floor",
                valve_opening_time_seconds=30,
                pump_overrun_seconds=120,
            ),
        ),
        routes=(DeliveryRoute("living-floor", "living", "floor"),),
    )


def _snapshot(temperature: float) -> PlantSnapshot:
    return PlantSnapshot({"temperature.living": TemperatureObservation(temperature, NOW)})


def test_shadow_sequence_waits_for_valve_before_requesting_pump() -> None:
    plant = compile_topology(_plant())

    opening = evaluate(plant, _snapshot(20.0), RuntimeState(), NOW)
    ready = evaluate(plant, _snapshot(20.0), opening.next_runtime, NOW + timedelta(seconds=30))

    assert opening.next_runtime.valves["valve.floor"].state is ValveState.OPENING
    assert opening.control_plan.commands[0].action == "open"
    assert "pump.floor" not in {command.actuator_id for command in opening.control_plan.commands}
    assert ready.next_runtime.valves["valve.floor"].state is ValveState.OPEN
    assert ready.next_runtime.pumps["pump.floor"].state is PumpState.RUNNING
    assert [(command.actuator_id, command.action) for command in ready.control_plan.commands] == [
        ("pump.floor", "turn_on")
    ]


def test_removing_demand_overruns_pump_before_closing_valve() -> None:
    plant = compile_topology(_plant())
    opening = evaluate(plant, _snapshot(20.0), RuntimeState(), NOW)
    running = evaluate(plant, _snapshot(20.0), opening.next_runtime, NOW + timedelta(seconds=30))

    overrun = evaluate(plant, _snapshot(22.0), running.next_runtime, NOW + timedelta(seconds=31))
    stopped = evaluate(plant, _snapshot(22.0), overrun.next_runtime, NOW + timedelta(seconds=151))

    assert overrun.next_runtime.pumps["pump.floor"].state is PumpState.OVERRUN
    assert overrun.next_runtime.valves["valve.floor"].state is ValveState.OPEN
    assert [command.action for command in overrun.control_plan.commands] == []
    assert stopped.next_runtime.pumps["pump.floor"].state is PumpState.OFF
    assert stopped.next_runtime.valves["valve.floor"].state is ValveState.CLOSED
    assert {(command.actuator_id, command.action) for command in stopped.control_plan.commands} == {
        ("pump.floor", "turn_off"),
        ("valve.floor", "close"),
    }


def test_shared_pump_remains_running_when_one_consumer_releases_demand() -> None:
    plant = compile_topology(
        PlantConfiguration(
            id="plant",
            zones=(
                Zone("living", "Living", 21.0, "temperature.living"),
                Zone("office", "Office", 21.0, "temperature.office"),
            ),
            circuits=(
                Circuit(
                    "floor",
                    "Floor",
                    "valve.floor",
                    "pump.shared",
                    valve_opening_time_seconds=1,
                ),
                Circuit(
                    "office",
                    "Office",
                    "valve.office",
                    "pump.shared",
                    valve_opening_time_seconds=1,
                ),
            ),
            routes=(
                DeliveryRoute("living-floor", "living", "floor"),
                DeliveryRoute("office-circuit", "office", "office"),
            ),
        )
    )
    cool_both = PlantSnapshot(
        {
            "temperature.living": TemperatureObservation(20.0, NOW),
            "temperature.office": TemperatureObservation(20.0, NOW),
        }
    )
    only_office = PlantSnapshot(
        {
            "temperature.living": TemperatureObservation(22.0, NOW),
            "temperature.office": TemperatureObservation(20.0, NOW),
        }
    )
    opening = evaluate(plant, cool_both, RuntimeState(), NOW)
    running = evaluate(plant, cool_both, opening.next_runtime, NOW + timedelta(seconds=1))
    released = evaluate(plant, only_office, running.next_runtime, NOW + timedelta(seconds=2))

    assert released.next_runtime.pumps["pump.shared"].state is PumpState.RUNNING
    assert released.control_plan.pump_consumers["pump.shared"] == frozenset({"office"})
    assert all(command.actuator_id != "pump.shared" for command in released.control_plan.commands)


def test_unchanged_running_snapshot_produces_no_new_commands() -> None:
    plant = compile_topology(_plant())
    opening = evaluate(plant, _snapshot(20.0), RuntimeState(), NOW)
    running = evaluate(plant, _snapshot(20.0), opening.next_runtime, NOW + timedelta(seconds=30))

    unchanged = evaluate(plant, _snapshot(20.0), running.next_runtime, NOW + timedelta(seconds=31))

    assert unchanged.control_plan.commands == ()
