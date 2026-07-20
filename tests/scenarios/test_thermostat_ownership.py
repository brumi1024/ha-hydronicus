"""Named operating scenarios for the thermostat ownership boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hydronicus_core.controller import evaluate
from hydronicus_core.executor import ActuatorExecutor
from hydronicus_core.model import (
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
    PumpRuntime,
    PumpState,
    RuntimeState,
    TemperatureObservation,
    TemperatureSensorMetadata,
    ThermostatHvacMode,
    Valve,
    ValveRuntime,
    ValveState,
    Zone,
    ZoneDecisionStatus,
)
from hydronicus_core.topology import compile_topology

NOW = datetime(2026, 7, 20, 12, tzinfo=UTC)


def _internal_plant(*, cooling: bool = False):
    """Build a one-zone Hydronicus-owned Plant for scenario timelines."""
    zone = Zone(
        "zone",
        "Zone",
        temperature_sensor_metadata=(TemperatureSensorMetadata("sensor.zone"),),
        humidity_sensor_metadata=(TemperatureSensorMetadata("sensor.humidity"),) if cooling else (),
        thermostat=HydronicusThermostatConfig(),
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


def _external_plant(*, cooling: bool = False):
    """Build a one-zone Plant whose demand comes from an external climate."""
    zone = Zone(
        "zone",
        "Zone",
        temperature_sensor_metadata=(TemperatureSensorMetadata("sensor.zone"),) if cooling else (),
        humidity_sensor_metadata=(TemperatureSensorMetadata("sensor.humidity"),) if cooling else (),
        thermostat=ExternalClimateThermostatConfig("climate.external"),
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


def _snapshot(
    *,
    thermostat: HydronicusThermostatState | ExternalClimateThermostatState,
    temperature: float = 18.0,
    humidity: float | None = None,
    supply: float | None = None,
) -> PlantSnapshot:
    """Create a timestamped synthetic snapshot for one scenario step."""
    return PlantSnapshot(
        temperatures={
            "sensor.zone": TemperatureObservation(temperature, NOW),
            **(
                {"sensor.humidity": TemperatureObservation(humidity, NOW)}
                if humidity is not None
                else {}
            ),
        },
        supply_temperatures=(
            {"sensor.supply": TemperatureObservation(supply, NOW)} if supply is not None else {}
        ),
        humidities=(
            {"sensor.humidity": TemperatureObservation(humidity, NOW)}
            if humidity is not None
            else {}
        ),
        thermostats={"zone": thermostat},
    )


def test_internal_zone_off_heat_demand_satisfied_off() -> None:
    """The internal thermostat owns the complete off-to-demand timeline."""
    plant = _internal_plant()
    runtime = RuntimeState()

    off = evaluate(
        plant,
        _snapshot(thermostat=HydronicusThermostatState(hvac_mode=ThermostatHvacMode.OFF)),
        runtime,
        NOW,
    )
    assert off.next_runtime.zone_runtime["zone"].demand is False

    heating = evaluate(
        plant,
        _snapshot(thermostat=HydronicusThermostatState(hvac_mode=ThermostatHvacMode.HEAT)),
        off.next_runtime,
        NOW + timedelta(seconds=1),
    )
    assert heating.next_runtime.zone_runtime["zone"].demand is True

    satisfied = evaluate(
        plant,
        _snapshot(
            thermostat=HydronicusThermostatState(hvac_mode=ThermostatHvacMode.HEAT),
            temperature=22.0,
        ),
        heating.next_runtime,
        NOW + timedelta(seconds=2),
    )
    assert satisfied.next_runtime.zone_runtime["zone"].demand is False

    released = evaluate(
        plant,
        _snapshot(thermostat=HydronicusThermostatState(hvac_mode=ThermostatHvacMode.OFF)),
        satisfied.next_runtime,
        NOW + timedelta(seconds=3),
    )
    assert released.next_runtime.zone_runtime["zone"].demand is False


def test_external_zone_idle_heating_idle() -> None:
    """An external thermostat's authoritative action changes demand immediately."""
    plant = _external_plant()
    runtime = RuntimeState()
    idle = evaluate(
        plant,
        _snapshot(
            thermostat=ExternalClimateThermostatState(
                available=True, hvac_action=ExternalHvacAction.IDLE
            )
        ),
        runtime,
        NOW,
    )
    heating = evaluate(
        plant,
        _snapshot(
            thermostat=ExternalClimateThermostatState(
                available=True, hvac_action=ExternalHvacAction.HEATING
            )
        ),
        idle.next_runtime,
        NOW + timedelta(seconds=1),
    )
    assert heating.next_runtime.zone_runtime["zone"].demand is True
    released = evaluate(
        plant,
        _snapshot(
            thermostat=ExternalClimateThermostatState(
                available=True, hvac_action=ExternalHvacAction.IDLE
            )
        ),
        heating.next_runtime,
        NOW + timedelta(seconds=2),
    )
    assert released.next_runtime.zone_runtime["zone"].demand is False
    assert released.diagnostics.zone_decisions["zone"].deadline is None


def test_external_unavailable_releases_active_demand() -> None:
    """A climate entity becoming unavailable cannot retain a hydraulic request."""
    plant = _external_plant()
    active = evaluate(
        plant,
        _snapshot(
            thermostat=ExternalClimateThermostatState(
                available=True, hvac_action=ExternalHvacAction.HEATING
            )
        ),
        RuntimeState(),
        NOW,
    )
    unavailable = evaluate(
        plant,
        _snapshot(
            thermostat=ExternalClimateThermostatState(
                available=False, hvac_action=ExternalHvacAction.HEATING
            )
        ),
        active.next_runtime,
        NOW + timedelta(seconds=1),
    )
    assert unavailable.next_runtime.zone_runtime["zone"].demand is False
    assert unavailable.diagnostics.zone_decisions["zone"].status is (
        ZoneDecisionStatus.SENSOR_BLOCKED
    )


def test_external_cooling_requires_zone_and_circuit_safety_observations() -> None:
    """Cooling action is blocked until configured observations are fresh and usable."""
    plant = _external_plant(cooling=True)
    thermostat = ExternalClimateThermostatState(
        available=True,
        hvac_action=ExternalHvacAction.COOLING,
        hvac_mode=ThermostatHvacMode.COOL,
    )
    blocked = evaluate(
        plant,
        _snapshot(thermostat=thermostat, humidity=50.0),
        RuntimeState(),
        NOW,
    )
    assert blocked.next_runtime.cooling_zone_demands["zone"] is False
    assert blocked.diagnostics.cooling_zone_decisions["zone"].status is (
        ZoneDecisionStatus.SENSOR_BLOCKED
    )

    permitted = evaluate(
        plant,
        _snapshot(thermostat=thermostat, humidity=50.0, supply=18.0),
        RuntimeState(),
        NOW,
    )
    assert permitted.next_runtime.cooling_zone_demands["zone"] is True


def test_mixed_thermostats_share_one_pump_without_dual_zone_demand() -> None:
    """Internal and external Zones can share a pump while retaining one owner each."""
    internal = Zone(
        "internal",
        "Internal",
        temperature_sensor_metadata=(TemperatureSensorMetadata("sensor.internal"),),
        thermostat=HydronicusThermostatConfig(),
    )
    external = Zone(
        "external",
        "External",
        thermostat=ExternalClimateThermostatConfig("climate.external"),
    )
    plant = compile_topology(
        PlantConfiguration(
            id="mixed",
            zones=(internal, external),
            valves=(
                Valve("internal-valve", "Internal valve", "switch.internal", 0),
                Valve("external-valve", "External valve", "switch.external", 0),
            ),
            pumps=(Pump("pump", "Shared pump", "switch.pump", 0),),
            circuits=(
                Circuit("internal-circuit", "Internal circuit", ("internal-valve",), "pump"),
                Circuit("external-circuit", "External circuit", ("external-valve",), "pump"),
            ),
            routes=(
                DeliveryRoute("internal-route", "internal", "internal-circuit"),
                DeliveryRoute("external-route", "external", "external-circuit"),
            ),
        )
    )
    result = evaluate(
        plant,
        PlantSnapshot(
            temperatures={"sensor.internal": TemperatureObservation(18.0, NOW)},
            thermostats={
                "internal": HydronicusThermostatState(hvac_mode=ThermostatHvacMode.HEAT),
                "external": ExternalClimateThermostatState(
                    available=True, hvac_action=ExternalHvacAction.HEATING
                ),
            },
        ),
        RuntimeState(
            valves={
                "internal-valve": ValveRuntime(ValveState.OPEN, NOW, True),
                "external-valve": ValveRuntime(ValveState.OPEN, NOW, True),
            },
            pumps={"pump": PumpRuntime(PumpState.OFF, NOW)},
        ),
        NOW,
    )
    assert result.next_runtime.zone_runtime["internal"].demand is True
    assert result.next_runtime.zone_runtime["external"].demand is True
    assert result.control_plan.pump_consumers == {
        "pump": frozenset({"internal-circuit", "external-circuit"})
    }
    assert not (
        result.next_runtime.cooling_zone_demands.get("internal", False)
        and result.next_runtime.zone_runtime["internal"].demand
    )


def test_dry_run_executor_keeps_synthetic_plan_across_re_evaluation() -> None:
    """A repeated Dry run evaluation remains proposed and never dispatches equipment."""
    plant = _external_plant()
    evaluation = evaluate(
        plant,
        _snapshot(
            thermostat=ExternalClimateThermostatState(
                available=True, hvac_action=ExternalHvacAction.HEATING
            )
        ),
        RuntimeState(),
        NOW,
    )
    executor = ActuatorExecutor.from_plant(plant, dry_run=True)

    async def _not_called(_operation) -> None:
        raise AssertionError("Dry run attempted an actuator dispatch.")

    import asyncio

    first = asyncio.run(executor.async_execute(evaluation.control_plan, _not_called))
    second_evaluation = evaluate(
        plant,
        _snapshot(
            thermostat=ExternalClimateThermostatState(
                available=True, hvac_action=ExternalHvacAction.HEATING
            )
        ),
        evaluation.next_runtime,
        NOW + timedelta(seconds=1),
    )
    second = asyncio.run(executor.async_execute(second_evaluation.control_plan, _not_called))
    assert first.executed == ()
    assert second.executed == ()
    assert first.proposed
