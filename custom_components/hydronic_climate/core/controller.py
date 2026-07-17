"""Deterministic shadow-mode controller for the initial hydronic vertical slice."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from .model import (
    ActuatorCommand,
    CompiledPlant,
    ControllerDiagnostics,
    ControlPlan,
    Evaluation,
    PlantSnapshot,
    PumpRuntime,
    PumpState,
    RuntimeState,
    ValveRuntime,
    ValveState,
)


def _zone_demand(
    *,
    previous: bool,
    temperature: float | None,
    target: float,
    start_delta: float,
    stop_delta: float,
) -> tuple[bool, str]:
    """Apply heating hysteresis to one zone without side effects."""
    if temperature is None:
        return False, "Blocked: the required temperature sensor has no usable reading."
    if temperature <= target - start_delta:
        return True, f"Heating requested: {temperature:.1f} is below {target - start_delta:.1f}."
    if temperature >= target + stop_delta:
        return False, f"Satisfied: {temperature:.1f} is at or above {target + stop_delta:.1f}."
    if previous:
        return True, "Heating remains requested inside the hysteresis band."
    return False, "Heating remains idle inside the hysteresis band."


def _elapsed(now: datetime, changed_at: datetime | None) -> timedelta:
    """Return a conservative zero duration for state restored without a timestamp."""
    return now - changed_at if changed_at is not None else timedelta(0)


def evaluate(
    plant: CompiledPlant,
    snapshot: PlantSnapshot,
    runtime: RuntimeState,
    now: datetime,
) -> Evaluation:
    """Return the next shadow runtime state and idempotent desired control plan."""
    zone_demands: dict[str, bool] = {}
    zone_reasons: dict[str, str] = {}
    for zone in plant.zones.values():
        observation = snapshot.temperatures.get(zone.temperature_sensor)
        temperature = observation.value if observation is not None else None
        demand, reason = _zone_demand(
            previous=runtime.zone_demands.get(zone.id, False),
            temperature=temperature,
            target=zone.target_temperature,
            start_delta=zone.heating_start_delta,
            stop_delta=zone.heating_stop_delta,
        )
        zone_demands[zone.id] = demand
        zone_reasons[zone.id] = reason

    requested_circuits = {
        route.circuit_id for route in plant.routes if zone_demands.get(route.zone_id, False)
    }
    valve_consumers: dict[str, set[str]] = defaultdict(set)
    for circuit_id in requested_circuits:
        circuit = plant.circuits[circuit_id]
        valve_consumers[circuit.valve_id].add(circuit_id)

    valves: dict[str, ValveRuntime] = dict(runtime.valves)
    valve_ready: set[str] = set()
    commands: list[ActuatorCommand] = []
    actuator_reasons: dict[str, str] = {}
    for circuit in plant.circuits.values():
        consumers = valve_consumers.get(circuit.valve_id, set())
        previous = valves.get(circuit.valve_id, ValveRuntime())
        if consumers:
            if previous.state is ValveState.CLOSED:
                valves[circuit.valve_id] = ValveRuntime(ValveState.OPENING, now)
                commands.append(
                    ActuatorCommand(
                        circuit.valve_id,
                        "open",
                        "A requesting circuit needs this valve.",
                    )
                )
                actuator_reasons[circuit.valve_id] = "Opening for active circuit consumers."
            elif previous.state is ValveState.OPENING and _elapsed(
                now, previous.changed_at
            ) >= timedelta(seconds=circuit.valve_opening_time_seconds):
                valves[circuit.valve_id] = ValveRuntime(ValveState.OPEN, previous.changed_at)
                actuator_reasons[circuit.valve_id] = "Open-delay elapsed; valve is virtually ready."
            else:
                valves[circuit.valve_id] = previous
                actuator_reasons[circuit.valve_id] = "Held open for active circuit consumers."
        else:
            valves[circuit.valve_id] = previous
        if valves[circuit.valve_id].state is ValveState.OPEN:
            valve_ready.add(circuit.valve_id)

    ready_circuits = {
        circuit_id
        for circuit_id in requested_circuits
        if plant.circuits[circuit_id].valve_id in valve_ready
    }
    pump_consumers: dict[str, set[str]] = defaultdict(set)
    for circuit_id in ready_circuits:
        pump_consumers[plant.circuits[circuit_id].pump_id].add(circuit_id)

    pumps: dict[str, PumpRuntime] = dict(runtime.pumps)
    for circuit in plant.circuits.values():
        pump_id = circuit.pump_id
        consumers = pump_consumers.get(pump_id, set())
        previous = pumps.get(pump_id, PumpRuntime())
        if consumers:
            if previous.state is not PumpState.RUNNING:
                pumps[pump_id] = PumpRuntime(PumpState.RUNNING, now)
                commands.append(
                    ActuatorCommand(pump_id, "turn_on", "A ready circuit needs this pump.")
                )
            else:
                pumps[pump_id] = previous
            actuator_reasons[pump_id] = "Running for ready circuit consumers."
            continue
        if previous.state is PumpState.RUNNING:
            pumps[pump_id] = PumpRuntime(PumpState.OVERRUN, now)
            actuator_reasons[pump_id] = "Overrunning after the final ready circuit released demand."
            continue
        if previous.state is PumpState.OVERRUN and _elapsed(now, previous.changed_at) < timedelta(
            seconds=circuit.pump_overrun_seconds
        ):
            pumps[pump_id] = previous
            actuator_reasons[pump_id] = "Overrun is still protecting the hydraulic circuit."
            continue
        if previous.state is PumpState.OVERRUN:
            pumps[pump_id] = PumpRuntime(PumpState.OFF, now)
            commands.append(ActuatorCommand(pump_id, "turn_off", "Pump overrun has completed."))
        else:
            pumps[pump_id] = previous
        actuator_reasons[pump_id] = "Idle because no ready circuit requires this pump."

    overrun_pumps = {pump_id for pump_id, pump in pumps.items() if pump.state is PumpState.OVERRUN}
    for circuit in plant.circuits.values():
        valve_id = circuit.valve_id
        valve = valves.get(valve_id, ValveRuntime())
        if valve_consumers.get(valve_id) or circuit.pump_id in overrun_pumps:
            continue
        if valve.state is not ValveState.CLOSED:
            valves[valve_id] = ValveRuntime(ValveState.CLOSED, now)
            commands.append(
                ActuatorCommand(
                    valve_id,
                    "close",
                    "No active consumer remains after pump overrun.",
                )
            )
            actuator_reasons[valve_id] = "Closing because its consumer set is empty."

    circuit_reasons = {
        circuit.id: (
            "Ready: valve is open and the circuit has demand."
            if circuit.id in ready_circuits
            else "Waiting for valve readiness."
            if circuit.id in requested_circuits
            else "Idle: no eligible zone currently requests this circuit."
        )
        for circuit in plant.circuits.values()
    }
    return Evaluation(
        next_runtime=RuntimeState(zone_demands=zone_demands, valves=valves, pumps=pumps),
        control_plan=ControlPlan(
            commands=tuple(commands),
            valve_consumers={key: frozenset(value) for key, value in valve_consumers.items()},
            pump_consumers={key: frozenset(value) for key, value in pump_consumers.items()},
        ),
        diagnostics=ControllerDiagnostics(zone_reasons, circuit_reasons, actuator_reasons),
    )
