"""Thermostat ownership behavior at the pure evaluator seam."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from custom_components.hydronicus.core.controller import evaluate
from custom_components.hydronicus.core.model import (
    Circuit,
    DeliveryRoute,
    ExternalClimateThermostatConfig,
    ExternalClimateThermostatState,
    ExternalHvacAction,
    HydronicusThermostatConfig,
    HydronicusThermostatState,
    PlantConfiguration,
    PlantSnapshot,
    Pump,
    RuntimeState,
    TemperatureObservation,
    TemperatureSensorMetadata,
    ThermostatHvacMode,
    Valve,
    Zone,
    ZoneDecisionStatus,
    ZoneRuntime,
)
from custom_components.hydronicus.core.topology import compile_topology

NOW = datetime(2026, 7, 20, 12, tzinfo=UTC)


def _plant(*, external: bool, cooling: bool = False):
    thermostat = (
        ExternalClimateThermostatConfig("climate.external")
        if external
        else HydronicusThermostatConfig()
    )
    zone = Zone(
        "zone",
        "Zone",
        temperature_sensor_metadata=(
            (TemperatureSensorMetadata("sensor.zone"),) if not external or cooling else ()
        ),
        humidity_sensor_metadata=(
            (TemperatureSensorMetadata("sensor.humidity"),) if cooling else ()
        ),
        thermostat=thermostat,
    )
    return compile_topology(
        PlantConfiguration(
            id="plant",
            zones=(zone,),
            valves=(Valve("valve", "Valve", "switch.valve", 0),),
            pumps=(Pump("pump", "Pump", "switch.pump", 0),),
            circuits=(
                Circuit(
                    "circuit",
                    "Circuit",
                    ("valve",),
                    "pump",
                    cooling_enabled=cooling,
                    supply_temperature_sensor="sensor.supply" if cooling else None,
                ),
            ),
            routes=(DeliveryRoute("route", "zone", "circuit"),),
        )
    )


def _external_snapshot(
    action: ExternalHvacAction | None,
    *,
    available: bool = True,
    mode: ThermostatHvacMode | None = ThermostatHvacMode.HEAT_COOL,
    cooling_safety: bool = False,
) -> PlantSnapshot:
    return PlantSnapshot(
        temperatures=({"sensor.zone": TemperatureObservation(25.0, NOW)} if cooling_safety else {}),
        humidities=(
            {"sensor.humidity": TemperatureObservation(50.0, NOW)} if cooling_safety else {}
        ),
        supply_temperatures=(
            {"sensor.supply": TemperatureObservation(18.0, NOW)} if cooling_safety else {}
        ),
        thermostats={
            "zone": ExternalClimateThermostatState(
                available=available,
                hvac_action=action,
                hvac_mode=mode,
                explanation="Normalized external thermostat state.",
            )
        },
    )


def test_internal_off_mode_never_requests_demand() -> None:
    """The digital thermostat owns off independently from the Plant mode."""
    plant = _plant(external=False)
    snapshot = PlantSnapshot(
        temperatures={"sensor.zone": TemperatureObservation(10.0, NOW)},
        thermostats={"zone": HydronicusThermostatState(21.0, "none", ThermostatHvacMode.OFF)},
    )

    result = evaluate(plant, snapshot, RuntimeState(), NOW)

    assert result.next_runtime.zone_runtime["zone"].demand is False
    assert result.control_plan.commands == ()


@pytest.mark.parametrize("action", [ExternalHvacAction.HEATING, ExternalHvacAction.PREHEATING])
def test_external_heating_actions_request_heat_without_temperature_attributes(
    action: ExternalHvacAction,
) -> None:
    """The authoritative action does not depend on diagnostic climate attributes."""
    result = evaluate(
        _plant(external=True),
        _external_snapshot(action),
        RuntimeState(),
        NOW,
    )

    assert result.next_runtime.zone_runtime["zone"].demand is True
    assert result.diagnostics.zone_decisions["zone"].status is ZoneDecisionStatus.REQUESTED


def test_external_idle_releases_without_internal_duration_hold() -> None:
    """An external release is immediate even if prior internal-style timing exists."""
    runtime = RuntimeState(zone_runtime={"zone": ZoneRuntime(True, NOW - timedelta(seconds=1))})

    result = evaluate(
        _plant(external=True),
        _external_snapshot(ExternalHvacAction.IDLE),
        runtime,
        NOW,
    )

    assert result.next_runtime.zone_runtime["zone"].demand is False
    assert result.diagnostics.zone_decisions["zone"].deadline is None


def test_external_cooling_still_requires_explicit_safety_observations() -> None:
    """Climate current_temperature never substitutes for cooling safety sensors."""
    plant = _plant(external=True, cooling=True)

    blocked = evaluate(
        plant,
        _external_snapshot(ExternalHvacAction.COOLING),
        RuntimeState(),
        NOW,
    )
    permitted = evaluate(
        plant,
        _external_snapshot(ExternalHvacAction.COOLING, cooling_safety=True),
        RuntimeState(),
        NOW,
    )

    assert blocked.next_runtime.cooling_zone_demands["zone"] is False
    assert blocked.diagnostics.cooling_zone_decisions["zone"].status is (
        ZoneDecisionStatus.SENSOR_BLOCKED
    )
    assert permitted.next_runtime.cooling_zone_demands["zone"] is True


@given(
    available=st.booleans(),
    mode=st.sampled_from([ThermostatHvacMode.OFF, ThermostatHvacMode.COOL]),
)
def test_invalid_external_heating_input_never_produces_actuator_demand(
    available: bool, mode: ThermostatHvacMode | None
) -> None:
    """Unavailable or mode-contradictory external input always fails closed."""
    snapshot = _external_snapshot(
        ExternalHvacAction.HEATING if available else None,
        available=available,
        mode=mode,
    )

    result = evaluate(_plant(external=True), snapshot, RuntimeState(), NOW)

    assert result.next_runtime.zone_runtime["zone"].demand is False
    assert result.control_plan.valve_consumers == {}
    assert result.control_plan.pump_consumers == {}
    assert result.control_plan.commands == ()
