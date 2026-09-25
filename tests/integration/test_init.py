"""Tests for integration setup and unload."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus import async_setup_entry, async_unload_entry
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
from tests.integration.plant_fixtures import (
    manifold_entry,
    manifold_zones,
    plant_entry,
    subentry_id_for,
)


async def test_setup_unload_and_reload_entry(hass) -> None:
    """The integration should load, unload, and reload an empty plant cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
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


def test_config_entry_version_is_4_0() -> None:
    assert (CONFIG_ENTRY_VERSION, CONFIG_ENTRY_MINOR_VERSION) == (4, 0)


@pytest.mark.parametrize(("version", "minor_version"), [(1, 1), (2, 0), (3, 0)])
async def test_an_entry_from_an_earlier_development_version_is_refused(
    hass, caplog: pytest.LogCaptureFixture, version: int, minor_version: int
) -> None:
    """Earlier storage versions are not migrated, and the log says to set the Plant up again."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Old plant",
        version=version,
        minor_version=minor_version,
        data={
            CONF_NAME: "Old plant",
            CONF_PLANT_ID: "00000000-0000-4000-8000-000000000001",
            CONF_DRY_RUN: True,
        },
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.MIGRATION_ERROR
    assert (entry.version, entry.minor_version) == (version, minor_version)
    assert not hasattr(entry, "runtime_data")
    errors = [
        record.getMessage()
        for record in caplog.records
        if record.levelname == "ERROR" and record.name == "custom_components.hydronicus"
    ]
    assert len(errors) == 1
    assert "Old plant" in errors[0]
    assert "earlier development version" in errors[0]
    assert "remove it and set the Plant up again" in errors[0]


async def test_setup_rejects_an_unsupported_subentry_type(hass) -> None:
    """A handle of a type Hydronicus does not know, such as ``room``, is an invalid graph."""
    entry = manifold_entry()
    bedroom = manifold_zones(["Living room", "Bedroom"])[1].zone_id
    corrupt = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        data=dict(entry.data),
        subentries_data=[
            *(
                subentry.as_dict()
                for subentry in entry.subentries.values()
                if subentry.unique_id != bedroom
            ),
            {**entry.subentries[subentry_id_for(bedroom)].as_dict(), "subentry_type": "room"},
        ],
    )
    corrupt.add_to_hass(hass)

    with pytest.raises(ConfigEntryError) as error:
        await async_setup_entry(hass, corrupt)

    assert error.value.translation_key == "invalid_stored_graph"
    placeholders = error.value.translation_placeholders
    assert "Unsupported config subentry type 'room'" in placeholders["error"]


async def test_setup_returns_unauthorized_active_entry_to_dry_run(hass) -> None:
    """A stored active entry must still carry exact output authorization."""
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
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
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
    entry = plant_entry(
        {
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
        title="Hydronic plant",
        source_handles=False,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    registry = dr.async_get(hass)
    assert registry.async_get_device_by_identifier(
        (DOMAIN, "00000000-0000-4000-8000-000000000001"), entry.entry_id
    )
    climate_entity_id = "climate.test_zone"
    assert hass.states.get(climate_entity_id) is not None
    assert hass.states.get("sensor.test_zone_temperature").state == "18.0"
    assert hass.states.get("binary_sensor.test_zone_blocked").state == "off"
    assert hass.states.get("sensor.test_zone_blocked_reason").state == "none"
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
    assert hass.states.get("binary_sensor.test_zone_blocked").state == "on"
    assert hass.states.get("binary_sensor.test_zone_heating_demand").state == "off"
    assert hass.states.get("sensor.test_zone_blocked_reason").state.startswith("Blocked:")

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
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
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


async def test_unload_entry_leaves_runtime_data_cleanup_to_home_assistant(hass) -> None:
    """The integration stops the runtime, and Home Assistant clears runtime data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
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

    assert await async_unload_entry(hass, entry)

    assert entry.runtime_data is runtime
    assert runtime._stopping is True
    assert runtime._hass is None


@pytest.mark.parametrize(
    "topology",
    [
        pytest.param(
            {"zones": [{"id": "00000000-0000-4000-8000-000000000002", "legacy": True}]},
            id="undecodable",
        ),
        pytest.param(
            {
                "routes": [
                    {
                        "id": "00000000-0000-4000-8000-000000000006",
                        "zone_id": "00000000-0000-4000-8000-000000000002",
                        "circuit_id": "00000000-0000-4000-8000-000000000005",
                    }
                ]
            },
            id="uncompilable",
        ),
    ],
)
async def test_setup_with_invalid_stored_graph_raises_translated_config_entry_error(
    hass, topology: dict[str, object]
) -> None:
    """A stored graph that cannot be decoded or compiled fails setup with a translation."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        title="Hydronic plant",
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: "00000000-0000-4000-8000-000000000001",
            CONF_DRY_RUN: True,
            "topology": topology,
        },
    )
    entry.add_to_hass(hass)

    with pytest.raises(ConfigEntryError) as error:
        await async_setup_entry(hass, entry)
    assert error.value.translation_domain == DOMAIN
    assert error.value.translation_key == "invalid_stored_graph"
    assert error.value.translation_placeholders["plant"] == "Hydronic plant"
    assert error.value.translation_placeholders["error"]
    assert not hasattr(entry, "runtime_data")

    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == "invalid_stored_graph"


async def test_setup_removes_the_closure_of_a_zone_deleted_while_unloaded(hass) -> None:
    """A zone whose zone handle disappeared was deleted, so setup removes its closure."""
    living, bedroom = manifold_zones(("Living room", "Bedroom"))
    entry = manifold_entry(dry_run=False)
    entry.add_to_hass(hass)
    assert hass.config_entries.async_remove_subentry(entry, subentry_id_for(bedroom.zone_id))

    assert await hass.config_entries.async_setup(entry.entry_id)

    assert [zone["id"] for zone in entry.data["topology"]["zones"]] == [living.zone_id]
    assert [circuit["id"] for circuit in entry.data["topology"]["circuits"]] == [living.circuit_id]
    assert [valve["id"] for valve in entry.data["topology"]["valves"]] == [living.valve_id]
    assert entry.data[CONF_DRY_RUN] is True
    assert CONF_OUTPUT_AUTHORIZATION not in entry.data
    assert set(entry.runtime_data.plant.zones) == {living.zone_id}
