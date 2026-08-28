"""Integration tests for generic actuator service execution."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_NAME,
    CONF_PLANT_ID,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
)
from custom_components.hydronicus.core.executor import (
    ActuatorFailureKind,
    ActuatorObservedState,
    ActuatorOperation,
)
from custom_components.hydronicus.core.model import (
    ActuatorAction,
    PlantMode,
    PumpRuntime,
    PumpState,
    RuntimeState,
    SafeShutdownPhase,
    ThermostatHvacMode,
    ValveRuntime,
    ValveState,
)
from custom_components.hydronicus.entry_configuration import authorize_outputs
from custom_components.hydronicus.runtime import HydronicRuntime

PLANT_ID = "00000000-0000-4000-8000-000000000001"
ZONE_ID = "00000000-0000-4000-8000-000000000002"
VALVE_ID = "00000000-0000-4000-8000-000000000003"
PUMP_ID = "00000000-0000-4000-8000-000000000004"
CIRCUIT_ID = "00000000-0000-4000-8000-000000000005"
ROUTE_ID = "00000000-0000-4000-8000-000000000006"
SOURCE_ID = "00000000-0000-4000-8000-000000000007"


@pytest.fixture(autouse=True)
def declare_synthetic_pump_state(hass) -> None:
    """Declare the synthetic pump so tests exercise actuator execution, not repair mode."""
    hass.states.async_set("switch.synthetic_pump", "off")


def _entry(
    *,
    dry_run: bool,
    valve_entity_id: str = "switch.synthetic_valve",
    pump_overrun_seconds: float = 300.0,
    valve_opening_seconds: float = 300.0,
    readiness_entity_id: str | None = None,
    source_demand: bool = False,
) -> MockConfigEntry:
    """Build a completely synthetic plant with one generic valve actuator."""
    data = {
        CONF_NAME: "Synthetic plant",
        CONF_PLANT_ID: PLANT_ID,
        CONF_DRY_RUN: dry_run,
        "topology": {
            "zones": [
                {
                    "id": ZONE_ID,
                    "name": "Synthetic zone",
                    "thermostat": {"kind": "hydronicus", "initial_target_temperature": 21.0},
                    "temperature_sensor_metadata": [{"entity_id": "sensor.synthetic_temperature"}],
                }
            ],
            "valves": [
                {
                    "id": VALVE_ID,
                    "name": "Synthetic valve",
                    "entity_id": valve_entity_id,
                    "opening_time_seconds": valve_opening_seconds,
                }
            ],
            "pumps": [
                {
                    "id": PUMP_ID,
                    "name": "Synthetic pump",
                    "entity_id": "switch.synthetic_pump",
                    "overrun_seconds": pump_overrun_seconds,
                }
            ],
            "circuits": [
                {
                    "id": CIRCUIT_ID,
                    "name": "Synthetic circuit",
                    "valve_ids": [VALVE_ID],
                    "pump_id": PUMP_ID,
                }
            ],
            "routes": [
                {
                    "id": ROUTE_ID,
                    "zone_id": ZONE_ID,
                    "circuit_id": CIRCUIT_ID,
                }
            ],
        },
    }
    if source_demand:
        data["topology"]["sources"] = [
            {
                "id": SOURCE_ID,
                "name": "Synthetic source",
                "source_demand_entity": "switch.synthetic_source",
            }
        ]
    if readiness_entity_id is not None:
        data["topology"]["valves"][0]["readiness_entity_id"] = readiness_entity_id
    if not dry_run:
        data = authorize_outputs(data)
    return MockConfigEntry(
        domain=DOMAIN,
        title="Synthetic plant",
        data=data,
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
    )


def _register_recorder(hass, calls: list[tuple[str, str, str]]) -> None:
    """Register synthetic service endpoints without creating physical entities."""

    async def record(call) -> None:
        calls.append((call.domain, call.service, call.data["entity_id"]))

    for domain, service in (
        ("switch", "turn_on"),
        ("switch", "turn_off"),
        ("valve", "open_valve"),
        ("valve", "close_valve"),
    ):
        hass.services.async_register(domain, service, record)


async def _enable_heating(hass, runtime: HydronicRuntime) -> None:
    """Opt the fresh default-off synthetic thermostat into heating."""
    await runtime.async_set_zone_hvac_mode(ZONE_ID, ThermostatHvacMode.HEAT, hass=hass)
    await hass.async_block_till_done()


async def _start_active_synthetic_plant(
    hass, calls: list[tuple[str, str, str]]
) -> tuple[MockConfigEntry, HydronicRuntime]:
    """Start one intercepted active Plant for lifecycle boundary tests."""
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    hass.states.async_set("switch.synthetic_pump", "off")
    entry = _entry(
        dry_run=False,
        valve_opening_seconds=0.0,
        pump_overrun_seconds=0.0,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)
    hass.states.async_set("switch.synthetic_valve", "on")
    await hass.async_block_till_done()
    hass.states.async_set("switch.synthetic_pump", "on")
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    assert set(runtime.active_equipment_ids()) == {VALVE_ID, PUMP_ID}
    calls.clear()
    return entry, runtime


async def test_selector_dispatch_preserves_the_selected_option(hass) -> None:
    """The HA adapter sends the core's explicit selector target unchanged."""
    calls: list[dict[str, object]] = []

    async def record(call) -> None:
        calls.append(dict(call.data))

    hass.services.async_register("select", "select_option", record)
    runtime = HydronicRuntime.from_entry(_entry(dry_run=False))
    operation = ActuatorOperation(
        actuator_id="source-selector",
        entity_id="select.synthetic_source",
        domain="select",
        service="select_option",
        target_state=ActuatorObservedState.SELECTED,
        target_value="buffer",
        reason="Select the recommended source.",
    )

    await runtime._async_dispatch_actuator(hass, operation)

    assert calls == [{"entity_id": "select.synthetic_source", "option": "buffer"}]


async def test_refresh_waits_for_safe_shutdown_before_mutation(hass, monkeypatch) -> None:
    """A refresh in the safe-shutdown branch should serialize against later mutations."""
    entered = asyncio.Event()
    release = asyncio.Event()
    active = 0

    async def blocked_shutdown(self, active_hass, *, now=None, force_dry_run=None):
        nonlocal active
        active += 1
        entered.set()
        await release.wait()
        active -= 1
        return object()

    monkeypatch.setattr(
        HydronicRuntime,
        "_async_safe_shutdown_locked",
        blocked_shutdown,
    )
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    entry = _entry(dry_run=True)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    runtime = entry.runtime_data
    runtime.runtime_state = replace(
        runtime.runtime_state,
        safe_shutdown_phase=SafeShutdownPhase.SOURCE_RELEASED,
        safe_shutdown_started_at=runtime._now(),
    )

    first = asyncio.create_task(runtime.async_refresh(hass))
    await entered.wait()
    second = asyncio.create_task(
        runtime.async_set_zone_hvac_mode(ZONE_ID, ThermostatHvacMode.HEAT, hass=hass)
    )
    await asyncio.sleep(0)

    assert active == 1
    assert not second.done()

    release.set()
    await asyncio.gather(first, second)

    assert runtime.zone_hvac_modes[ZONE_ID] is ThermostatHvacMode.HEAT


@pytest.mark.parametrize(
    ("entity_id", "initial_state", "expected_domain", "expected_service"),
    [
        ("switch.synthetic_valve", "off", "switch", "turn_on"),
        ("valve.synthetic_valve", "closed", "valve", "open_valve"),
    ],
)
async def test_demand_reaches_the_expected_generic_service_call(
    hass,
    entity_id: str,
    initial_state: str,
    expected_domain: str,
    expected_service: str,
) -> None:
    """A synthetic demand traverses evaluation, runtime, adapter, and service dispatch."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set(entity_id, initial_state)
    entry = _entry(dry_run=False, valve_entity_id=entity_id)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    await _enable_heating(hass, runtime)
    assert runtime.evaluation is not None
    assert runtime.evaluation.control_plan.commands[0].action is ActuatorAction.OPEN
    assert calls == [(expected_domain, expected_service, entity_id)]
    assert all(entity != "switch.synthetic_pump" for _domain, _service, entity in calls)
    assert all(service != "toggle" for _domain, service, _entity in calls)

    await runtime.async_refresh(hass)
    await hass.async_block_till_done()
    assert calls == [(expected_domain, expected_service, entity_id)]


async def test_dry_run_off_executes_heating_and_source_demand_after_pump_feedback(hass) -> None:
    """Direct source demand waits until the commanded pump is observed running."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    hass.states.async_set("switch.synthetic_pump", "off")
    hass.states.async_set("switch.synthetic_source", "off")
    entry = _entry(
        dry_run=False,
        valve_opening_seconds=0.0,
        pump_overrun_seconds=0.0,
        source_demand=True,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)
    assert calls == [
        ("switch", "turn_on", "switch.synthetic_valve"),
        ("switch", "turn_on", "switch.synthetic_pump"),
    ]
    assert all(entity != "switch.synthetic_source" for _domain, _service, entity in calls)

    hass.states.async_set("switch.synthetic_pump", "on")
    await hass.async_block_till_done()
    assert calls[-1] == ("switch", "turn_on", "switch.synthetic_source")
    assert calls.index(("switch", "turn_on", "switch.synthetic_pump")) < calls.index(
        ("switch", "turn_on", "switch.synthetic_source")
    )


async def test_rejected_service_call_is_explained_without_failing_setup(hass) -> None:
    """A service rejection becomes a stable runtime failure report."""

    async def reject(_call) -> None:
        raise HomeAssistantError("synthetic rejection")

    hass.services.async_register("switch", "turn_on", reject)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    entry = _entry(dry_run=False)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)

    report = entry.runtime_data.last_execution
    assert report is not None
    assert len(report.failures) == 1
    assert report.failures[0].kind is ActuatorFailureKind.REJECTED
    assert "synthetic rejection" in report.failures[0].explanation
    assert entry.runtime_data.executor.failure_for(VALVE_ID) == report.failures[0]
    assert entry.runtime_data.runtime_state.valves[VALVE_ID].state is ValveState.INDETERMINATE


async def test_rejected_valve_close_keeps_runtime_conservative(hass) -> None:
    """A failed close does not claim that an observed-open valve is closed."""

    async def reject_close(_call) -> None:
        raise HomeAssistantError("synthetic close rejection")

    hass.services.async_register("switch", "turn_off", reject_close)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    entry = _entry(dry_run=False)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)
    hass.states.async_set("switch.synthetic_valve", "on")
    hass.states.async_set("sensor.synthetic_temperature", "22.0")
    await hass.async_block_till_done()

    failure = entry.runtime_data.executor.failure_for(VALVE_ID)
    assert failure is not None
    assert failure.kind is ActuatorFailureKind.REJECTED
    assert entry.runtime_data.runtime_state.valves[VALVE_ID].state is ValveState.INDETERMINATE
    assert entry.runtime_data.runtime_state.valves[VALVE_ID].is_ready is False


async def test_rejected_pump_start_is_retained_as_failure(hass) -> None:
    """A failed pump start remains visible as an actuator failure."""

    calls: list[str] = []

    async def reject_pump(call) -> None:
        calls.append(call.data["entity_id"])
        if call.data["entity_id"] == "switch.synthetic_pump":
            raise HomeAssistantError("synthetic pump rejection")

    hass.services.async_register("switch", "turn_on", reject_pump)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    hass.states.async_set("switch.synthetic_pump", "off")
    entry = _entry(dry_run=False, valve_opening_seconds=0.0)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)
    hass.states.async_set("switch.synthetic_valve", "on")
    await hass.async_block_till_done()

    assert "switch.synthetic_pump" in calls
    failure = entry.runtime_data.executor.failure_for(PUMP_ID)
    assert failure is not None
    assert failure.operation.target_state is ActuatorObservedState.ON


async def test_delayed_service_success_is_reconciled_without_a_duplicate_command(hass) -> None:
    """A command that outlives its timeout recovers from synthetic feedback."""
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def delayed_open(call) -> None:
        calls.append(call.data["entity_id"])
        started.set()
        await release.wait()
        hass.states.async_set("switch.synthetic_valve", "on")

    hass.services.async_register("switch", "turn_on", delayed_open)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    entry = _entry(dry_run=False)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("custom_components.hydronicus.runtime.ACTUATOR_COMMAND_TIMEOUT_SECONDS", 0.01)
        mode_task = asyncio.create_task(
            entry.runtime_data.async_set_zone_hvac_mode(ZONE_ID, ThermostatHvacMode.HEAT, hass=hass)
        )
        await started.wait()
        await mode_task

    report = entry.runtime_data.last_execution
    assert report is not None
    assert report.failures[0].kind is ActuatorFailureKind.TIMEOUT
    assert calls == ["switch.synthetic_valve"]

    release.set()
    await hass.async_block_till_done()

    assert entry.runtime_data.executor.failure_for(VALVE_ID) is None
    assert entry.runtime_data.executor.actuator_state(VALVE_ID) is ActuatorObservedState.ON
    assert calls == ["switch.synthetic_valve"]


async def test_late_service_completion_triggers_conservative_reconciliation(hass) -> None:
    """A late accepted call is rechecked without treating completion as feedback."""
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def delayed_open(call) -> None:
        calls.append(call.data["entity_id"])
        started.set()
        await release.wait()

    hass.services.async_register("switch", "turn_on", delayed_open)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    entry = _entry(dry_run=False)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("custom_components.hydronicus.runtime.ACTUATOR_COMMAND_TIMEOUT_SECONDS", 0.01)
        mode_task = asyncio.create_task(
            entry.runtime_data.async_set_zone_hvac_mode(ZONE_ID, ThermostatHvacMode.HEAT, hass=hass)
        )
        await asyncio.wait_for(started.wait(), timeout=1.0)
        await mode_task

    failure = entry.runtime_data.executor.failure_for(VALVE_ID)
    assert failure is not None
    assert failure.kind is ActuatorFailureKind.TIMEOUT
    refresh_count = entry.runtime_data.refresh_count

    release.set()
    async with asyncio.timeout(1.0):
        while entry.runtime_data.refresh_count == refresh_count:
            await asyncio.sleep(0)

    assert entry.runtime_data.executor.failure_for(VALVE_ID) == failure
    assert calls == ["switch.synthetic_valve"]
    assert entry.runtime_data.late_actuator_completion_count == 1
    assert entry.runtime_data.late_actuator_error_count == 0


async def test_late_service_error_is_consumed_and_reconciled(hass) -> None:
    """A service that rejects after timeout is consumed and remains indeterminate."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_rejection(_call) -> None:
        started.set()
        await release.wait()
        raise HomeAssistantError("late synthetic rejection")

    hass.services.async_register("switch", "turn_on", delayed_rejection)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    entry = _entry(dry_run=False)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("custom_components.hydronicus.runtime.ACTUATOR_COMMAND_TIMEOUT_SECONDS", 0.01)
        mode_task = asyncio.create_task(
            entry.runtime_data.async_set_zone_hvac_mode(ZONE_ID, ThermostatHvacMode.HEAT, hass=hass)
        )
        await asyncio.wait_for(started.wait(), timeout=1.0)
        await mode_task

    failure = entry.runtime_data.executor.failure_for(VALVE_ID)
    assert failure is not None
    assert failure.kind is ActuatorFailureKind.TIMEOUT

    release.set()
    async with asyncio.timeout(1.0):
        while entry.runtime_data.late_actuator_completion_count == 0:
            await asyncio.sleep(0)

    assert entry.runtime_data.executor.failure_for(VALVE_ID) == failure
    assert entry.runtime_data.late_actuator_completion_count == 1
    assert entry.runtime_data.late_actuator_error_count == 1


async def test_timed_out_open_does_not_block_an_opposite_close_command(hass) -> None:
    """Turning a zone off closes a transitional valve before a late open finishes."""
    open_started = asyncio.Event()
    release_open = asyncio.Event()
    close_called = asyncio.Event()
    calls: list[tuple[str, str]] = []

    async def delayed_open(call) -> None:
        calls.append((call.service, call.data["entity_id"]))
        hass.states.async_set("valve.synthetic_valve", "opening")
        open_started.set()
        await release_open.wait()
        hass.states.async_set("valve.synthetic_valve", "open")

    async def close_valve(call) -> None:
        calls.append((call.service, call.data["entity_id"]))
        hass.states.async_set("valve.synthetic_valve", "closed")
        close_called.set()

    hass.services.async_register("valve", "open_valve", delayed_open)
    hass.services.async_register("valve", "close_valve", close_valve)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("valve.synthetic_valve", "closed")
    entry = _entry(dry_run=False, valve_entity_id="valve.synthetic_valve")
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("custom_components.hydronicus.runtime.ACTUATOR_COMMAND_TIMEOUT_SECONDS", 0.01)
        mode_task = asyncio.create_task(
            entry.runtime_data.async_set_zone_hvac_mode(ZONE_ID, ThermostatHvacMode.HEAT, hass=hass)
        )
        await asyncio.wait_for(open_started.wait(), timeout=1.0)
        await mode_task

    failure = entry.runtime_data.executor.failure_for(VALVE_ID)
    assert failure is not None
    assert failure.kind is ActuatorFailureKind.TIMEOUT

    try:
        await entry.runtime_data.async_set_zone_hvac_mode(
            ZONE_ID,
            ThermostatHvacMode.OFF,
            hass=hass,
        )
        await asyncio.wait_for(close_called.wait(), timeout=0.2)
        assert not release_open.is_set()
    finally:
        release_open.set()
        await hass.async_block_till_done()

    assert calls[:2] == [
        ("open_valve", "valve.synthetic_valve"),
        ("close_valve", "valve.synthetic_valve"),
    ]


async def test_native_valve_open_timeout_cannot_advance_to_pump_start_on_unknown_feedback(
    hass,
) -> None:
    """A failed native valve open stays indeterminate until feedback repairs it."""
    open_started = asyncio.Event()
    release_open = asyncio.Event()
    calls: list[tuple[str, str, str]] = []

    async def delayed_open(call) -> None:
        calls.append((call.domain, call.service, call.data["entity_id"]))
        open_started.set()
        await release_open.wait()

    async def record_switch(call) -> None:
        calls.append((call.domain, call.service, call.data["entity_id"]))

    hass.services.async_register("valve", "open_valve", delayed_open)
    hass.services.async_register("switch", "turn_on", record_switch)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("valve.synthetic_valve", "closed")
    hass.states.async_set("switch.synthetic_pump", "off")
    entry = _entry(
        dry_run=False,
        valve_entity_id="valve.synthetic_valve",
        valve_opening_seconds=0.0,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("custom_components.hydronicus.runtime.ACTUATOR_COMMAND_TIMEOUT_SECONDS", 0.01)
        mode_task = asyncio.create_task(
            entry.runtime_data.async_set_zone_hvac_mode(ZONE_ID, ThermostatHvacMode.HEAT, hass=hass)
        )
        await asyncio.wait_for(open_started.wait(), timeout=1.0)
        await mode_task

    failure = entry.runtime_data.executor.failure_for(VALVE_ID)
    assert failure is not None
    assert failure.kind is ActuatorFailureKind.TIMEOUT

    hass.states.async_set("valve.synthetic_valve", "opening")
    await entry.runtime_data.async_refresh(hass)

    try:
        assert entry.runtime_data.executor.failure_for(VALVE_ID) == failure
        assert not entry.runtime_data.runtime_state.valves[VALVE_ID].is_ready
        assert ("switch", "turn_on", "switch.synthetic_pump") not in calls
    finally:
        release_open.set()
        await hass.async_block_till_done()


async def test_failed_source_release_keeps_safe_shutdown_retryable(hass, monkeypatch) -> None:
    """A failed source-demand release must not advance past the retryable source phase."""
    calls: list[str] = []
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    hass.states.async_set("switch.synthetic_pump", "off")
    hass.states.async_set("switch.synthetic_source", "off")
    entry = _entry(
        dry_run=False,
        source_demand=True,
        valve_opening_seconds=0.0,
        pump_overrun_seconds=0.0,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    started_at = runtime._now()
    runtime.runtime_state = replace(
        runtime.runtime_state,
        plant_mode=PlantMode.HEATING,
        valves={VALVE_ID: ValveRuntime(ValveState.OPEN, started_at, True)},
        pumps={PUMP_ID: PumpRuntime(PumpState.RUNNING, started_at)},
        safe_shutdown_phase=SafeShutdownPhase.IDLE,
    )

    async def fail_source(self, active_hass, operation) -> None:
        calls.append(operation.actuator_id)
        if operation.actuator_id.startswith("source:"):
            raise HomeAssistantError("synthetic source release failed")

    monkeypatch.setattr(HydronicRuntime, "_async_dispatch_actuator", fail_source)

    first = await runtime.async_safe_shutdown(hass, now=started_at)
    second = await runtime.async_safe_shutdown(hass, now=started_at)

    assert first.execution.failures
    assert second.execution.failures
    assert runtime.runtime_state.safe_shutdown_phase is SafeShutdownPhase.IDLE
    assert calls == [f"source:{SOURCE_ID}", f"source:{SOURCE_ID}"]


async def test_periodic_reconciliation_repairs_a_missed_feedback_event_without_churn(hass) -> None:
    """A periodic read advances synthetic feedback even when its event was missed."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    hass.states.async_set("switch.synthetic_pump", "off")
    entry = _entry(dry_run=False, valve_opening_seconds=0.0)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)
    assert calls == [
        ("switch", "turn_on", "switch.synthetic_valve"),
        ("switch", "turn_on", "switch.synthetic_pump"),
    ]

    # Simulate a missed state event by removing the listener before synthetic feedback.
    remove_state_listener = entry.runtime_data._remove_state_listener
    assert remove_state_listener is not None
    remove_state_listener()
    entry.runtime_data._remove_state_listener = None
    hass.states.async_set("switch.synthetic_valve", "on")
    hass.states.async_set("switch.synthetic_pump", "on")
    calls.clear()
    remove_reconciliation_timer = entry.runtime_data._remove_reconciliation_timer
    assert remove_reconciliation_timer is not None
    remove_reconciliation_timer()
    entry.runtime_data._remove_reconciliation_timer = None
    entry.runtime_data._async_handle_reconciliation_timer(datetime.now(UTC))
    await hass.async_block_till_done()

    assert calls == []
    assert entry.runtime_data.runtime_state.valves[VALVE_ID].is_ready is True
    assert entry.runtime_data.runtime_state.pumps[PUMP_ID].state.value == "running"
    remove_reconciliation_timer = entry.runtime_data._remove_reconciliation_timer
    assert remove_reconciliation_timer is not None
    remove_reconciliation_timer()
    entry.runtime_data._remove_reconciliation_timer = None
    entry.runtime_data._async_handle_reconciliation_timer(datetime.now(UTC))
    await hass.async_block_till_done()
    assert calls == []
    await entry.runtime_data.async_stop()


async def test_readiness_feedback_allows_pump_only_after_the_valve_is_ready(hass) -> None:
    """A readiness feedback event advances the synthetic valve-to-pump sequence."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("valve.synthetic_valve", "closed")
    hass.states.async_set("binary_sensor.synthetic_valve_ready", "off")
    hass.states.async_set("switch.synthetic_pump", "off")
    entry = _entry(
        dry_run=False,
        valve_entity_id="valve.synthetic_valve",
        valve_opening_seconds=300.0,
        readiness_entity_id="binary_sensor.synthetic_valve_ready",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)

    assert calls == [("valve", "open_valve", "valve.synthetic_valve")]
    assert all(entity != "switch.synthetic_pump" for _domain, _service, entity in calls)

    hass.states.async_set("binary_sensor.synthetic_valve_ready", "on")
    await hass.async_block_till_done()

    assert calls == [
        ("valve", "open_valve", "valve.synthetic_valve"),
        ("switch", "turn_on", "switch.synthetic_pump"),
    ]
    assert entry.runtime_data.runtime_state.valves[VALVE_ID].is_ready is True


async def test_rejected_native_valve_open_never_becomes_timer_ready(hass) -> None:
    """Unknown native-valve feedback cannot erase a failed open and release the pump."""
    calls: list[tuple[str, str, str]] = []

    async def reject_open(call) -> None:
        calls.append((call.domain, call.service, call.data["entity_id"]))
        raise HomeAssistantError("synthetic native valve rejection")

    async def record(call) -> None:
        calls.append((call.domain, call.service, call.data["entity_id"]))

    hass.services.async_register("valve", "open_valve", reject_open)
    hass.services.async_register("valve", "close_valve", record)
    hass.services.async_register("switch", "turn_on", record)
    hass.services.async_register("switch", "turn_off", record)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("valve.synthetic_valve", "closed")
    hass.states.async_set("switch.synthetic_pump", "off")
    entry = _entry(
        dry_run=False,
        valve_entity_id="valve.synthetic_valve",
        valve_opening_seconds=0.0,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await _enable_heating(hass, entry.runtime_data)
    assert calls == [("valve", "open_valve", "valve.synthetic_valve")]
    assert entry.runtime_data.runtime_state.valves[VALVE_ID].state is ValveState.INDETERMINATE

    hass.states.async_set("valve.synthetic_valve", "unknown")
    await hass.async_block_till_done()

    assert entry.runtime_data.runtime_state.valves[VALVE_ID].state is ValveState.INDETERMINATE
    assert entry.runtime_data.runtime_state.valves[VALVE_ID].is_ready is False
    assert all(
        binding.entity_id != "valve.synthetic_valve"
        for binding in entry.runtime_data.unresolved_bindings
    )
    assert all(entity_id != "switch.synthetic_pump" for _, _, entity_id in calls)


async def test_failed_source_release_keeps_runtime_in_retryable_shutdown_phase(hass) -> None:
    """Runtime state cannot advance beyond source release after a rejected command."""
    attempts: list[str] = []

    async def reject_source(call) -> None:
        attempts.append(call.data["entity_id"])
        raise HomeAssistantError("synthetic source release rejection")

    hass.services.async_register("switch", "turn_off", reject_source)
    entry = _entry(
        dry_run=False,
        pump_overrun_seconds=10.0,
        valve_opening_seconds=0.0,
        source_demand=True,
    )
    runtime = HydronicRuntime.from_entry(entry)
    started_at = datetime(2026, 7, 18, tzinfo=UTC)
    runtime.runtime_state = RuntimeState(
        valves={VALVE_ID: ValveRuntime(ValveState.OPEN, started_at, True)},
        pumps={PUMP_ID: PumpRuntime(PumpState.RUNNING, started_at)},
        selected_source_id=SOURCE_ID,
    )

    first = await runtime.async_safe_shutdown(hass, now=started_at)

    assert attempts == ["switch.synthetic_source"]
    assert len(first.execution.failures) == 1
    assert runtime.runtime_state.safe_shutdown_phase is SafeShutdownPhase.IDLE
    assert runtime.runtime_state.selected_source_id == SOURCE_ID

    async def accept_source(call) -> None:
        attempts.append(call.data["entity_id"])

    hass.services.async_register("switch", "turn_off", accept_source)
    second = await runtime.async_safe_shutdown(hass, now=started_at)

    assert attempts == ["switch.synthetic_source", "switch.synthetic_source"]
    assert second.execution.failures == ()
    assert runtime.runtime_state.safe_shutdown_phase is SafeShutdownPhase.PUMP_OVERRUN
    await runtime.async_stop()


async def test_dry_run_keeps_the_desired_plan_without_service_calls(hass) -> None:
    """Dry run preserves the command and explanation while issuing no call."""
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    entry = _entry(dry_run=True)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)

    runtime = entry.runtime_data
    assert runtime.evaluation is not None
    assert runtime.evaluation.control_plan.commands[0].action is ActuatorAction.OPEN
    assert runtime.evaluation.diagnostics.actuator_reasons[VALVE_ID].startswith("Opening")
    assert runtime.last_execution is not None
    assert [operation.actuator_id for operation in runtime.last_execution.proposed] == [VALVE_ID]
    assert "valve" in runtime.last_execution.proposed[0].reason
    summary = runtime.execution_summary()
    assert summary["dry_run"] is True
    assert summary["proposed"]
    assert summary["executed"] == []
    assert runtime.active_equipment_ids() == ()


async def test_reconfigure_can_leave_dry_run_after_one_confirmation(hass) -> None:
    """The normal config-entry reconfigure path changes the Plant boundary."""
    hass.states.async_set("sensor.synthetic_temperature", "22.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    entry = _entry(dry_run=True)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry.runtime_data

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_DRY_RUN: False}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "dry_run_confirmation"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"dry_run_confirmation": True}
    )
    assert result["type"] == "abort"
    await hass.async_block_till_done()
    assert entry.data[CONF_DRY_RUN] is False
    assert entry.runtime_data is runtime
    assert entry.runtime_data.dry_run is False


async def test_returning_to_dry_run_completes_ordered_shutdown_before_persisting(hass) -> None:
    """Dry run is persisted only after active heating has released pump then valve."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    hass.states.async_set("switch.synthetic_pump", "off")
    entry = _entry(
        dry_run=False,
        valve_opening_seconds=0.0,
        pump_overrun_seconds=0.0,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)
    hass.states.async_set("switch.synthetic_valve", "on")
    await hass.async_block_till_done()
    hass.states.async_set("switch.synthetic_pump", "on")
    await hass.async_block_till_done()
    calls.clear()

    assert await entry.runtime_data.async_set_dry_run(True, hass=hass)
    assert calls == [
        ("switch", "turn_off", "switch.synthetic_pump"),
        ("switch", "turn_off", "switch.synthetic_valve"),
    ]
    assert entry.runtime_data.runtime_state.safe_shutdown_phase.value == "idle"
    assert {
        zone_id: state.demand
        for zone_id, state in entry.runtime_data.runtime_state.zone_runtime.items()
    } == {ZONE_ID: True}
    assert entry.runtime_data.runtime_state.cooling_zone_demands == {ZONE_ID: False}
    assert entry.data[CONF_DRY_RUN] is True
    assert entry.runtime_data.dry_run is True


async def test_reload_reconstructs_unknown_state_when_feedback_is_not_trustworthy(hass) -> None:
    """Reload does not restore a prior command as an observed physical state."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    entry = _entry(dry_run=False)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)
    assert entry.runtime_data.executor.actuator_state(VALVE_ID) is ActuatorObservedState.OFF
    assert entry.runtime_data.executor.requested_state(VALVE_ID) is ActuatorObservedState.ON

    hass.states.async_set("sensor.synthetic_temperature", "22.0")
    hass.states.async_set("switch.synthetic_valve", "unknown")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert isinstance(entry.runtime_data, HydronicRuntime)
    assert entry.runtime_data.executor.actuator_state(VALVE_ID) is ActuatorObservedState.UNKNOWN


@pytest.mark.parametrize("action", ["reload", "unload", "remove"])
async def test_active_reload_unload_and_removal_issue_no_implicit_equipment_commands(
    hass, caplog, action: str
) -> None:
    """Lifecycle teardown is command-free and warns about the hardware safety boundary."""
    calls: list[tuple[str, str, str]] = []
    entry, _runtime = await _start_active_synthetic_plant(hass, calls)

    if action == "reload":
        assert await hass.config_entries.async_reload(entry.entry_id)
    elif action == "unload":
        assert await hass.config_entries.async_unload(entry.entry_id)
    else:
        result = await hass.config_entries.async_remove(entry.entry_id)
        assert result == {"require_restart": False}

    assert calls == []
    assert "without issuing equipment commands" in caplog.text
    assert "independent safeguards" in caplog.text


async def test_home_assistant_stop_detaches_active_runtime_without_commands(hass, caplog) -> None:
    """Host shutdown never starts an overrun sequence it cannot remain alive to finish."""
    calls: list[tuple[str, str, str]] = []
    _entry, runtime = await _start_active_synthetic_plant(hass, calls)

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    assert calls == []
    assert runtime._hass is None
    assert runtime._entry is None
    assert not runtime._tasks
    assert "no equipment commands are issued during Home Assistant shutdown" in caplog.text
    assert "independent safeguards" in caplog.text
    assert "Unable to remove unknown job listener" not in caplog.text


async def test_home_assistant_stop_cancels_a_timed_out_actuator_service(hass, caplog) -> None:
    """Host shutdown consumes and cancels a shielded service task after its timeout."""
    open_started = asyncio.Event()
    service_cancelled = asyncio.Event()
    release_open = asyncio.Event()
    calls: list[tuple[str, str, str]] = []

    async def delayed_open(call) -> None:
        calls.append((call.domain, call.service, call.data["entity_id"]))
        open_started.set()
        try:
            await release_open.wait()
        except asyncio.CancelledError:
            service_cancelled.set()
            raise

    hass.services.async_register("valve", "open_valve", delayed_open)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("valve.synthetic_valve", "closed")
    entry = _entry(dry_run=False, valve_entity_id="valve.synthetic_valve")
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "custom_components.hydronicus.runtime.ACTUATOR_COMMAND_TIMEOUT_SECONDS",
            0.01,
        )
        mode_task = asyncio.create_task(
            runtime.async_set_zone_hvac_mode(
                ZONE_ID,
                ThermostatHvacMode.HEAT,
                hass=hass,
            )
        )
        await asyncio.wait_for(open_started.wait(), timeout=1.0)
        await mode_task

    failure = runtime.executor.failure_for(VALVE_ID)
    assert failure is not None
    assert failure.kind is ActuatorFailureKind.TIMEOUT
    assert any(not task.done() for task in runtime._tasks)

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    assert service_cancelled.is_set()
    assert calls == [("valve", "open_valve", "valve.synthetic_valve")]
    assert runtime._hass is None
    assert runtime._entry is None
    assert not runtime._tasks
    assert runtime.late_actuator_completion_count == 0
    assert "no equipment commands are issued during Home Assistant shutdown" in caplog.text


async def test_reload_during_valve_opening_does_not_start_pump_early(hass) -> None:
    """A switch that is on after restart remains timer-gated because it has no position feedback."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    hass.states.async_set("switch.synthetic_pump", "off")
    entry = _entry(dry_run=False, valve_opening_seconds=300.0)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)
    assert calls == [("switch", "turn_on", "switch.synthetic_valve")]

    hass.states.async_set("switch.synthetic_valve", "on")
    await hass.async_block_till_done()
    calls.clear()

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    assert runtime.runtime_state.valves[VALVE_ID].state.value == "opening"
    assert runtime.runtime_state.valves[VALVE_ID].is_ready is False
    assert runtime.runtime_state.pumps[PUMP_ID].state.value == "off"
    assert all(entity != "switch.synthetic_pump" for _domain, _service, entity in calls)


async def test_reload_during_pump_starting_does_not_assume_running_feedback(hass) -> None:
    """A pending start is reasserted only because synthetic feedback still says off."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    hass.states.async_set("switch.synthetic_pump", "off")
    entry = _entry(dry_run=False, valve_opening_seconds=0.0)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)
    assert hass.states.get("climate.synthetic_plant_synthetic_zone").state == "heat"
    hass.states.async_set("switch.synthetic_valve", "on")
    await hass.async_block_till_done()
    calls.clear()

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert calls == [("switch", "turn_on", "switch.synthetic_pump")]
    assert entry.runtime_data.runtime_state.pumps[PUMP_ID].state.value == "starting"
    assert entry.runtime_data.executor.actuator_state(PUMP_ID) is ActuatorObservedState.OFF


async def test_reload_during_pump_running_keeps_observed_running_state_without_churn(hass) -> None:
    """Observed synthetic pump feedback is enough to reconstruct running state."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "on")
    hass.states.async_set("switch.synthetic_pump", "on")
    entry = _entry(dry_run=False, valve_opening_seconds=0.0)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)
    calls.clear()

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert calls == []
    assert entry.runtime_data.runtime_state.pumps[PUMP_ID].state.value == "running"


async def test_reload_during_shutdown_preserves_pump_overrun_before_valve_close(hass) -> None:
    """Restarting during shutdown never closes a valve while observed pump is on."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "22.0")
    hass.states.async_set("switch.synthetic_valve", "on")
    hass.states.async_set("switch.synthetic_pump", "on")
    entry = _entry(dry_run=False, pump_overrun_seconds=60.0)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    started_at = runtime.runtime_state.pumps[PUMP_ID].changed_at
    assert started_at is not None
    shutdown = await runtime.async_safe_shutdown(hass, now=started_at)
    assert shutdown.plan.phase.value == "pump_overrun"
    calls.clear()

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert calls == []
    assert entry.runtime_data.runtime_state.pumps[PUMP_ID].state.value == "overrun"
    assert all(service != "close_valve" for _domain, service, _entity in calls)


async def test_reload_during_pump_overrun_keeps_valve_protected(hass) -> None:
    """Observed open and running equipment reconstructs overrun before valve closure."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "22.0")
    hass.states.async_set("valve.synthetic_valve", "open")
    hass.states.async_set("switch.synthetic_pump", "on")
    entry = _entry(
        dry_run=False,
        valve_entity_id="valve.synthetic_valve",
        valve_opening_seconds=300.0,
        pump_overrun_seconds=60.0,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert calls == []
    assert entry.runtime_data.runtime_state.valves[VALVE_ID].is_ready is True
    assert entry.runtime_data.runtime_state.pumps[PUMP_ID].state.value == "overrun"

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    assert runtime.runtime_state.pumps[PUMP_ID].state.value == "overrun"
    assert runtime.runtime_state.valves[VALVE_ID].is_ready is True
    assert all(service != "close_valve" for _domain, service, _entity in calls)


async def test_reload_reconciles_observed_active_actuators_before_idle_shutdown(hass) -> None:
    """Observed active equipment is reconciled into the virtual state before shutdown."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "22.0")
    hass.states.async_set("switch.synthetic_valve", "on")
    hass.states.async_set("switch.synthetic_pump", "on")
    entry = _entry(dry_run=False, pump_overrun_seconds=0.0)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ("switch", "turn_off", "switch.synthetic_pump") in calls
    assert ("switch", "turn_off", "switch.synthetic_valve") in calls


async def test_safe_shutdown_is_ordered_and_idempotent_with_intercepted_services(hass) -> None:
    """Synthetic shutdown releases source, waits overrun, then stops pumps and valves."""
    calls: list[tuple[str, str, str]] = []
    _register_recorder(hass, calls)
    hass.states.async_set("sensor.synthetic_temperature", "18.0")
    hass.states.async_set("switch.synthetic_valve", "off")
    hass.states.async_set("switch.synthetic_pump", "off")
    hass.states.async_set("switch.synthetic_source", "on")
    entry = _entry(
        dry_run=False,
        pump_overrun_seconds=10.0,
        valve_opening_seconds=0.0,
        source_demand=True,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _enable_heating(hass, entry.runtime_data)
    runtime = entry.runtime_data
    hass.states.async_set("switch.synthetic_pump", "on")
    await runtime.async_refresh(hass)
    await hass.async_block_till_done()
    started_at = runtime.runtime_state.pumps[PUMP_ID].changed_at
    assert started_at is not None
    calls.clear()

    first = await runtime.async_safe_shutdown(hass, now=started_at)
    assert first.plan.phase.value == "pump_overrun"
    assert first.plan.next_deadline == started_at + timedelta(seconds=10)
    assert first.next_runtime.safe_shutdown_phase.value == "pump_overrun"
    assert first.next_runtime.pumps[PUMP_ID].state.value == "overrun"
    assert calls[-1] == ("switch", "turn_off", "switch.synthetic_source")
    second = await runtime.async_safe_shutdown(hass, now=started_at + timedelta(seconds=5))
    assert second.plan.phase.value == "pump_overrun"
    assert calls == [("switch", "turn_off", "switch.synthetic_source")]
    third = await runtime.async_safe_shutdown(hass, now=started_at + timedelta(seconds=10))
    assert third.plan.phase.value == "pumps_stopped"
    assert third.plan.next_deadline is None
    assert third.next_runtime.pumps[PUMP_ID].state.value == "off"
    assert third.next_runtime.valves[VALVE_ID].state.value == "open"
    assert calls[-1] == ("switch", "turn_off", "switch.synthetic_pump")
    fourth = await runtime.async_safe_shutdown(hass, now=started_at + timedelta(seconds=11))
    assert fourth.plan.phase.value == "valves_closed"
    assert fourth.next_runtime.valves[VALVE_ID].state.value == "closed"
    assert calls[-1] == ("switch", "turn_off", "switch.synthetic_valve")
    fifth = await runtime.async_safe_shutdown(hass, now=started_at + timedelta(seconds=12))
    assert fifth.execution.executed == ()
