"""Tests for the runtime state container against a real Home Assistant instance."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import mock

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.hydronicus import runtime as runtime_module
from custom_components.hydronicus.const import CONF_DRY_RUN, CONF_PLANT_ID, DOMAIN
from custom_components.hydronicus.core.model import (
    RuntimeState,
    SafeShutdownPhase,
    ThermostatHvacMode,
)
from custom_components.hydronicus.runtime import HydronicRuntime
from tests.integration.plant_fixtures import subentries_data, with_room_handles

NOW = datetime(2026, 7, 17, tzinfo=UTC)
PLANT_UUID = "00000000-0000-4000-8000-000000000001"
ZONE_UUID = "00000000-0000-4000-8000-000000000002"
VALVE_UUID = "00000000-0000-4000-8000-000000000003"
PUMP_UUID = "00000000-0000-4000-8000-000000000004"
CIRCUIT_UUID = "00000000-0000-4000-8000-000000000005"
ROUTE_UUID = "00000000-0000-4000-8000-000000000006"
TEMPERATURE_SENSOR = "sensor.test_temperature"


def _set_temperature(hass: HomeAssistant, value: str, *, at: datetime = NOW) -> None:
    """Report one zone temperature at a controlled Home Assistant timestamp."""
    hass.states.async_set(TEMPERATURE_SENSOR, value, timestamp=at.timestamp())


def _prepare_states(hass: HomeAssistant, temperature: str) -> None:
    """Expose every configured entity, with actuators not yet observed on or off.

    The bindings resolve, so no Repairs issue degrades an actuator, while the
    unknown actuator states leave the virtual transition timers in control.
    """
    hass.states.async_set("switch.test_valve", "unknown", timestamp=NOW.timestamp())
    hass.states.async_set("switch.test_pump", "unknown", timestamp=NOW.timestamp())
    _set_temperature(hass, temperature)


def _version_3(data: dict[str, object]) -> SimpleNamespace:
    """Return a version 3 entry whose stored Plant has its room handles."""
    data = with_room_handles(data)
    return SimpleNamespace(
        data=data,
        subentries={item["subentry_id"]: SimpleNamespace(**item) for item in subentries_data(data)},
    )


def _configured_entry(
    *,
    zone_overrides: dict[str, object] | None = None,
    pump_overrun_seconds: float = 120.0,
) -> SimpleNamespace:
    zone = {
        "id": ZONE_UUID,
        "name": "Test zone",
        "thermostat": {"kind": "hydronicus", "initial_target_temperature": 21.0},
        "temperature_sensor_metadata": [{"entity_id": TEMPERATURE_SENSOR}],
    }
    if zone_overrides:
        zone.update(zone_overrides)
    return _version_3(
        data={
            "name": "Hydronic plant",
            "plant_id": PLANT_UUID,
            "dry_run": True,
            "topology": {
                "zones": [zone],
                "circuits": [
                    {
                        "id": CIRCUIT_UUID,
                        "name": "Test circuit",
                        "valve_ids": [VALVE_UUID],
                        "pump_id": PUMP_UUID,
                    }
                ],
                "valves": [
                    {
                        "id": VALVE_UUID,
                        "name": "Test valve",
                        "entity_id": "switch.test_valve",
                        "opening_time_seconds": 30.0,
                    }
                ],
                "pumps": [
                    {
                        "id": PUMP_UUID,
                        "name": "Test pump",
                        "entity_id": "switch.test_pump",
                        "overrun_seconds": pump_overrun_seconds,
                    }
                ],
                "routes": [
                    {
                        "id": ROUTE_UUID,
                        "zone_id": ZONE_UUID,
                        "circuit_id": CIRCUIT_UUID,
                    }
                ],
            },
        }
    )


def test_defaults_to_dry_run() -> None:
    runtime = HydronicRuntime.from_entry(SimpleNamespace(data={CONF_PLANT_ID: PLANT_UUID}))

    assert runtime.plant_id == PLANT_UUID
    assert runtime.name == "Hydronic plant"
    assert runtime.dry_run is True


def test_reads_explicit_dry_run() -> None:
    runtime = HydronicRuntime.from_entry(
        SimpleNamespace(data={CONF_PLANT_ID: PLANT_UUID, CONF_DRY_RUN: False})
    )

    assert runtime.dry_run is False


def test_zone_aggregation_requires_a_controller_evaluation() -> None:
    """The adapter must not reimplement aggregation before the core evaluates."""
    runtime = HydronicRuntime.from_entry(_configured_entry())
    runtime.snapshot = SimpleNamespace(temperatures={})

    assert runtime.zone_aggregation(ZONE_UUID) is None


async def test_shutdown_timer_advances_shutdown_instead_of_evaluating_demand(
    hass: HomeAssistant,
) -> None:
    """A shutdown deadline never routes back through normal demand evaluation."""
    runtime = HydronicRuntime.from_entry(_configured_entry())
    runtime._hass = hass
    runtime.runtime_state = RuntimeState(safe_shutdown_phase=SafeShutdownPhase.PUMP_OVERRUN)

    with mock.patch.object(
        HydronicRuntime,
        "async_safe_shutdown",
        new_callable=mock.AsyncMock,
    ) as safe_shutdown:
        runtime._async_handle_transition_timer(NOW)
        await hass.async_block_till_done()

    safe_shutdown.assert_awaited_once_with(hass)


async def test_timers_advance_valve_readiness_and_pump_overrun(hass: HomeAssistant) -> None:
    runtime = HydronicRuntime.from_entry(_configured_entry())
    runtime.zone_hvac_modes[ZONE_UUID] = ThermostatHvacMode.HEAT
    _prepare_states(hass, "20.0")
    scheduled: list[tuple[float, object, mock.Mock]] = []

    def schedule(_hass, delay: float, action):
        cancel = mock.Mock()
        scheduled.append((delay, action, cancel))
        return cancel

    with (
        mock.patch.object(
            runtime_module, "async_track_state_change_event", return_value=mock.Mock()
        ),
        mock.patch.object(runtime_module, "async_call_later", side_effect=schedule),
        mock.patch.object(runtime_module, "datetime") as clock,
    ):
        clock.now.return_value = NOW
        await runtime.async_start(hass)

        assert scheduled[0][0] == 30.0
        assert runtime.runtime_state.valves[VALVE_UUID].state.value == "opening"
        assert [
            (command.actuator_id, command.action)
            for command in runtime.evaluation.control_plan.commands
        ] == [(VALVE_UUID, "open")]

        clock.now.return_value = NOW + timedelta(seconds=30)
        scheduled[0][1](clock.now.return_value)
        await hass.async_block_till_done()

        assert runtime.runtime_state.valves[VALVE_UUID].state.value == "open"
        assert runtime.runtime_state.pumps[PUMP_UUID].state.value == "running"
        assert [
            (command.actuator_id, command.action)
            for command in runtime.evaluation.control_plan.commands
        ] == [(PUMP_UUID, "turn_on")]

        clock.now.return_value = NOW + timedelta(seconds=31)
        _set_temperature(hass, "22.0", at=clock.now.return_value)
        await runtime.async_refresh(hass)

        overrun_timer = next(item for item in scheduled if item[0] == 120.0)
        assert runtime.runtime_state.pumps[PUMP_UUID].state.value == "overrun"
        assert runtime.evaluation.control_plan.commands == ()

        clock.now.return_value = NOW + timedelta(seconds=151)
        overrun_timer[1](clock.now.return_value)
        await hass.async_block_till_done()

        assert runtime.runtime_state.pumps[PUMP_UUID].state.value == "off"
        assert runtime.runtime_state.valves[VALVE_UUID].state.value == "closed"
        assert [
            (command.actuator_id, command.action)
            for command in runtime.evaluation.control_plan.commands
        ] == [(PUMP_UUID, "turn_off"), (VALVE_UUID, "close")]

        await runtime.async_stop()


async def test_due_now_transition_runs_as_a_tracked_home_assistant_task(
    hass: HomeAssistant,
) -> None:
    """Zero overrun advances without relying on an untracked timer callback."""
    runtime = HydronicRuntime.from_entry(_configured_entry(pump_overrun_seconds=0))
    runtime.zone_hvac_modes[ZONE_UUID] = ThermostatHvacMode.HEAT
    _prepare_states(hass, "20.0")
    scheduled: list[tuple[float, object]] = []

    def schedule(_hass, delay: float, action):
        scheduled.append((delay, action))
        return mock.Mock()

    with (
        mock.patch.object(
            runtime_module, "async_track_state_change_event", return_value=mock.Mock()
        ),
        mock.patch.object(runtime_module, "async_call_later", side_effect=schedule),
        mock.patch.object(runtime_module, "datetime") as clock,
    ):
        clock.now.return_value = NOW
        await runtime.async_start(hass)

        clock.now.return_value = NOW + timedelta(seconds=30)
        scheduled[0][1](clock.now.return_value)
        await hass.async_block_till_done()

        clock.now.return_value = NOW + timedelta(seconds=31)
        _set_temperature(hass, "22.0", at=clock.now.return_value)
        assert not runtime._tasks
        await runtime.async_refresh(hass)

        assert len(runtime._tasks) == 1
        await hass.async_block_till_done()

        scheduled_delays = [delay for delay, _action in scheduled]
        assert scheduled_delays[0] == 30.0
        assert 0 not in scheduled_delays
        assert runtime.runtime_state.pumps[PUMP_UUID].state.value == "off"
        assert runtime.runtime_state.valves[VALVE_UUID].state.value == "closed"

        await runtime.async_stop()


async def test_battery_observation_uses_last_reported_timestamp(hass: HomeAssistant) -> None:
    """An unchanged report should be newer than its last value update."""
    runtime = HydronicRuntime.from_entry(_configured_entry())
    _set_temperature(hass, "20.0", at=NOW - timedelta(hours=12))
    _set_temperature(hass, "20.0", at=NOW)
    state = hass.states.get(TEMPERATURE_SENSOR)
    assert state.last_updated == NOW - timedelta(hours=12)

    with mock.patch.object(runtime_module, "async_call_later", return_value=mock.Mock()):
        await runtime.async_refresh(hass)

    assert runtime.snapshot.temperatures[TEMPERATURE_SENSOR].observed_at == NOW


async def test_sensor_staleness_deadline_is_scheduled_without_state_change(
    hass: HomeAssistant,
) -> None:
    """The runtime wakes at freshness expiry even when no sensor event arrives."""
    runtime = HydronicRuntime.from_entry(
        _configured_entry(
            zone_overrides={
                "temperature_sensor_metadata": [
                    {
                        "entity_id": TEMPERATURE_SENSOR,
                        "max_age_seconds": 60.0,
                    }
                ]
            }
        )
    )
    _prepare_states(hass, "22.0")
    scheduled: list[float] = []

    def schedule(_hass, delay: float, _action):
        scheduled.append(delay)
        return mock.Mock()

    with (
        mock.patch.object(runtime_module, "async_call_later", side_effect=schedule),
        mock.patch.object(runtime_module, "datetime") as clock,
    ):
        clock.now.return_value = NOW
        await runtime.async_start(hass)
        await runtime.async_stop()

    assert 60.0 in scheduled
    assert 30.0 in scheduled


async def test_stop_cancels_state_and_timer_listeners(hass: HomeAssistant) -> None:
    runtime = HydronicRuntime.from_entry(_configured_entry())
    _prepare_states(hass, "20.0")
    cancel_state = mock.Mock()
    cancel_timer = mock.Mock()

    with (
        mock.patch.object(
            runtime_module, "async_track_state_change_event", return_value=cancel_state
        ),
        mock.patch.object(runtime_module, "async_call_later", return_value=cancel_timer),
        mock.patch.object(runtime_module, "datetime") as clock,
    ):
        clock.now.return_value = NOW
        stop_listeners = hass.bus.async_listeners().get(EVENT_HOMEASSISTANT_STOP, 0)
        await runtime.async_start(hass)
        assert hass.bus.async_listeners()[EVENT_HOMEASSISTANT_STOP] == stop_listeners + 1
        await runtime.async_stop()

    cancel_state.assert_called_once_with()
    assert cancel_timer.call_count == 2
    assert hass.bus.async_listeners().get(EVENT_HOMEASSISTANT_STOP, 0) == stop_listeners


async def test_stop_cancels_in_flight_runtime_work() -> None:
    """Unload cancels tracked work rather than leaving a delayed command alive."""
    runtime = HydronicRuntime.from_entry(_configured_entry())
    task = asyncio.create_task(asyncio.sleep(60))
    runtime._tasks.add(task)

    await runtime.async_stop()

    assert task.cancelled()


async def test_homeassistant_stop_event_cancels_all_runtime_resources(
    hass: HomeAssistant,
) -> None:
    """The Home Assistant stop event cancels listeners, timers, and work."""
    runtime = HydronicRuntime.from_entry(_configured_entry())
    _prepare_states(hass, "20.0")
    cancel_state = mock.Mock()
    cancel_timer = mock.Mock()

    with (
        mock.patch.object(
            runtime_module, "async_track_state_change_event", return_value=cancel_state
        ),
        mock.patch.object(runtime_module, "async_call_later", return_value=cancel_timer),
        mock.patch.object(runtime_module, "datetime") as clock,
    ):
        clock.now.return_value = NOW
        await runtime.async_start(hass)
        task = asyncio.create_task(asyncio.sleep(60))
        runtime._tasks.add(task)

        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
        await hass.async_block_till_done()

    cancel_state.assert_called_once_with()
    assert cancel_timer.call_count == 2
    assert task.cancelled()
    assert runtime._hass is None
    assert runtime._stopping is True
    assert runtime._remove_stop_listener is None


async def test_homeassistant_stop_handler_does_not_remove_its_consumed_listener(
    hass: HomeAssistant,
) -> None:
    """Core removes a one-shot listener before invoking it, so it is not removed twice."""
    runtime = HydronicRuntime.from_entry(_configured_entry())
    cancel_stop_listener = mock.Mock()
    runtime._hass = hass
    runtime._remove_stop_listener = cancel_stop_listener

    await runtime._async_handle_homeassistant_stop(Event(EVENT_HOMEASSISTANT_STOP))

    cancel_stop_listener.assert_not_called()
    assert runtime._hass is None


def _assert_translated(error: HomeAssistantError, key: str) -> None:
    assert error.translation_domain == DOMAIN
    assert error.translation_key == key
    assert error.translation_placeholders


async def test_operations_before_start_raise_translated_runtime_errors() -> None:
    """Operator actions against a detached runtime use Home Assistant's error type."""
    runtime = HydronicRuntime.from_entry(_configured_entry())

    with pytest.raises(HomeAssistantError) as error:
        await runtime.async_set_requested_mode("heating")
    assert not isinstance(error.value, ServiceValidationError)
    _assert_translated(error.value, "runtime_not_started")

    with pytest.raises(HomeAssistantError) as error:
        await runtime.async_safe_shutdown()
    _assert_translated(error.value, "runtime_not_started")

    with pytest.raises(HomeAssistantError) as error:
        await runtime.async_set_zone_hvac_mode(ZONE_UUID, "heat")
    _assert_translated(error.value, "runtime_not_started")


@pytest.mark.parametrize(
    ("call", "key"),
    [
        (lambda runtime: runtime.async_set_requested_mode("turbo"), "unsupported_plant_mode"),
        (
            lambda runtime: runtime.async_set_zone_target_temperature(ZONE_UUID, 99.0),
            "invalid_target_temperature",
        ),
        (
            lambda runtime: runtime.async_set_zone_target_temperature(ZONE_UUID, "warm"),
            "invalid_target_temperature",
        ),
        (
            lambda runtime: runtime.async_set_zone_target_temperature("missing", 20.0),
            "unknown_zone",
        ),
        (
            lambda runtime: runtime.async_set_zone_preset_mode(ZONE_UUID, "party"),
            "unsupported_preset_mode",
        ),
        (
            lambda runtime: runtime.async_set_zone_preset_mode(ZONE_UUID, "eco"),
            "preset_not_configured",
        ),
        (
            lambda runtime: runtime.async_set_zone_preset_mode("missing", "eco"),
            "unknown_zone",
        ),
        (
            lambda runtime: runtime.async_set_zone_hvac_mode(ZONE_UUID, "fan_only"),
            "unsupported_hvac_mode",
        ),
        (
            lambda runtime: runtime.async_set_zone_hvac_mode("missing", "heat"),
            "unknown_zone",
        ),
    ],
)
async def test_invalid_operator_input_raises_translated_validation_errors(call, key: str) -> None:
    """Invalid operator input is a ServiceValidationError with a translation key."""
    runtime = HydronicRuntime.from_entry(_configured_entry())

    with pytest.raises(ServiceValidationError) as error:
        await call(runtime)

    _assert_translated(error.value, key)


async def test_selector_operation_without_option_raises_translated_error(
    hass: HomeAssistant,
) -> None:
    """A malformed selector operation is a runtime failure, not operator input."""
    runtime = HydronicRuntime.from_entry(_configured_entry())
    operation = SimpleNamespace(
        service="select_option", target_value=None, entity_id="select.source"
    )

    with pytest.raises(HomeAssistantError) as error:
        await runtime._async_dispatch_actuator(hass, operation)

    assert not isinstance(error.value, ServiceValidationError)
    _assert_translated(error.value, "selector_option_missing")
