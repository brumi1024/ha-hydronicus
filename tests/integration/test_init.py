"""Tests for integration setup and unload."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus import async_setup_entry
from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_NAME,
    CONF_OUTPUT_AUTHORIZATION,
    CONF_PLANT_ID,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
)
from custom_components.hydronicus.runtime import HydronicRuntime


async def test_setup_unload_and_reload_entry(hass) -> None:
    """The integration should load, unload, and reload an empty plant cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: "00000000-0000-4000-8000-000000000001",
            CONF_DRY_RUN: True,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data is not None
    assert entry.runtime_data.dry_run is True

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not hasattr(entry, "runtime_data")

    assert await hass.config_entries.async_reload(entry.entry_id)


async def test_config_entry_migrates_from_pre_release_1_1_to_version_2(hass) -> None:
    """The pre-release 1.1 entry contract is upgraded before runtime setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        version=1,
        minor_version=1,
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: "00000000-0000-4000-8000-000000000001",
            CONF_DRY_RUN: True,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)

    assert entry.version == 2
    assert entry.minor_version == 0
    assert entry.data[CONF_DRY_RUN] is True


async def test_setup_returns_unauthorized_active_entry_to_dry_run(hass) -> None:
    """A stored active version 2 entry must still carry exact output authorization."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: "00000000-0000-4000-8000-000000000001",
            CONF_DRY_RUN: False,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)

    assert entry.data[CONF_DRY_RUN] is True
    assert CONF_OUTPUT_AUTHORIZATION not in entry.data
    assert entry.runtime_data.dry_run is True


async def test_setup_failure_stops_partial_runtime_and_clears_entry(hass, monkeypatch) -> None:
    """A failed setup must not leave listeners, tasks, or runtime data behind."""
    stopped: list[HydronicRuntime] = []
    original_stop = HydronicRuntime.async_stop

    async def record_stop(runtime: HydronicRuntime) -> None:
        stopped.append(runtime)
        await original_stop(runtime)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: "00000000-0000-4000-8000-000000000001",
            CONF_DRY_RUN: True,
        },
    )
    entry.add_to_hass(hass)
    monkeypatch.setattr(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(side_effect=RuntimeError("platform boom")),
    )
    monkeypatch.setattr(HydronicRuntime, "async_stop", record_stop)

    with pytest.raises(RuntimeError, match="platform boom"):
        await async_setup_entry(hass, entry)

    assert len(stopped) == 1
    assert stopped[0]._hass is None
    assert stopped[0]._entry is None
    assert not stopped[0]._tasks
    assert not hasattr(entry, "runtime_data")


async def test_configured_zone_climate_unloads_with_entry(hass) -> None:
    """Configured climate entities must disappear with their parent entry."""
    hass.states.async_set("sensor.test_zone_temperature", "18.0")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: "00000000-0000-4000-8000-000000000001",
            CONF_DRY_RUN: True,
            "topology": {
                "zones": [
                    {
                        "id": "00000000-0000-4000-8000-000000000002",
                        "name": "Test zone",
                        "thermostat": {
                            "kind": "hydronicus",
                            "initial_target_temperature": 21.0,
                            "preset_targets": {"comfort": 22.0, "eco": 19.0},
                        },
                        "temperature_sensor_metadata": [
                            {"entity_id": "sensor.test_zone_temperature"}
                        ],
                    }
                ],
                "valves": [
                    {
                        "id": "00000000-0000-4000-8000-000000000003",
                        "name": "Test valve",
                        "entity_id": "switch.test_valve",
                    }
                ],
                "pumps": [
                    {
                        "id": "00000000-0000-4000-8000-000000000004",
                        "name": "Test pump",
                        "entity_id": "switch.test_pump",
                    }
                ],
                "circuits": [
                    {
                        "id": "00000000-0000-4000-8000-000000000005",
                        "name": "Test circuit",
                        "valve_ids": ["00000000-0000-4000-8000-000000000003"],
                        "pump_id": "00000000-0000-4000-8000-000000000004",
                    }
                ],
                "routes": [
                    {
                        "id": "00000000-0000-4000-8000-000000000006",
                        "zone_id": "00000000-0000-4000-8000-000000000002",
                        "circuit_id": "00000000-0000-4000-8000-000000000005",
                    }
                ],
            },
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    registry = dr.async_get(hass)
    assert registry.async_get_device({(DOMAIN, "00000000-0000-4000-8000-000000000001")})
    climate_entity_id = "climate.hydronic_plant_test_zone"
    assert hass.states.get(climate_entity_id) is not None
    assert hass.states.get("sensor.hydronic_plant_test_zone_aggregate_temperature").state == "18.0"
    assert hass.states.get("binary_sensor.hydronic_plant_test_zone_blocked").state == "off"
    assert hass.states.get("sensor.hydronic_plant_test_zone_blocked_reason").state == "none"
    assert hass.states.get(climate_entity_id).attributes["preset_modes"] == [
        "comfort",
        "eco",
    ]

    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": climate_entity_id, "preset_mode": "comfort"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(climate_entity_id).attributes["preset_mode"] == "comfort"
    assert hass.states.get(climate_entity_id).attributes["temperature"] == 22.0

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": climate_entity_id, "temperature": 18.5},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(climate_entity_id).attributes["preset_mode"] == "none"
    assert hass.states.get(climate_entity_id).attributes["temperature"] == 18.5

    hass.states.async_set("sensor.test_zone_temperature", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.hydronic_plant_test_zone_blocked").state == "on"
    assert hass.states.get("binary_sensor.hydronic_plant_test_zone_demand").state == "off"
    assert hass.states.get("sensor.hydronic_plant_test_zone_blocked_reason").state.startswith(
        "Blocked:"
    )

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert hass.states.get(climate_entity_id).state == "unavailable"


async def test_unload_waits_for_inflight_refresh_before_detaching_runtime(
    hass, monkeypatch
) -> None:
    """An unload must serialize with a live refresh before clearing runtime state."""
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked_refresh(self, active_hass):
        entered.set()
        await release.wait()

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: "00000000-0000-4000-8000-000000000001",
            CONF_DRY_RUN: True,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    runtime = entry.runtime_data
    monkeypatch.setattr(
        "custom_components.hydronicus.runtime.HydronicRuntime._async_refresh_locked",
        blocked_refresh,
    )

    refresh_task = asyncio.create_task(runtime.async_refresh(hass))
    await entered.wait()

    unload_task = asyncio.create_task(hass.config_entries.async_unload(entry.entry_id))
    await asyncio.sleep(0)
    assert not unload_task.done()
    assert not refresh_task.done()

    release.set()
    assert await unload_task
    await refresh_task
    assert not hasattr(entry, "runtime_data")
