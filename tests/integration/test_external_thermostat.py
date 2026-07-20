"""Integration coverage for external climate thermostat ownership."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from homeassistant.helpers import issue_registry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import CONF_DRY_RUN, CONF_NAME, CONF_PLANT_ID, DOMAIN
from custom_components.hydronicus.diagnostics import async_get_config_entry_diagnostics
from custom_components.hydronicus.websocket import _filter_snapshot_for_user

PLANT_ID = "00000000-0000-4000-8000-000000000101"
ZONE_ID = "00000000-0000-4000-8000-000000000102"
VALVE_ID = "00000000-0000-4000-8000-000000000103"
PUMP_ID = "00000000-0000-4000-8000-000000000104"
CIRCUIT_ID = "00000000-0000-4000-8000-000000000105"
ROUTE_ID = "00000000-0000-4000-8000-000000000106"
EXTERNAL_ENTITY = "climate.external_room"


def _entry(*, internal: bool = False) -> MockConfigEntry:
    """Build one synthetic Plant with a switchable thermostat owner."""
    thermostat = (
        {
            "kind": "hydronicus",
            "initial_target_temperature": 21.0,
            "preset_targets": {"comfort": 22.0},
            "initial_preset": "none",
        }
        if internal
        else {"kind": "external_climate", "entity_id": EXTERNAL_ENTITY}
    )
    zone: dict[str, object] = {
        "id": ZONE_ID,
        "name": "External room" if not internal else "Internal room",
        "thermostat": thermostat,
        "temperature_sensor_metadata": (
            [{"entity_id": "sensor.internal_room"}] if internal else []
        ),
    }
    return MockConfigEntry(
        domain=DOMAIN,
        title="External thermostat plant",
        data={
            CONF_NAME: "External thermostat plant",
            CONF_PLANT_ID: PLANT_ID,
            CONF_DRY_RUN: True,
            "topology": {
                "zones": [zone],
                "valves": [{"id": VALVE_ID, "name": "Valve", "entity_id": "switch.external_valve"}],
                "pumps": [{"id": PUMP_ID, "name": "Pump", "entity_id": "switch.external_pump"}],
                "circuits": [
                    {
                        "id": CIRCUIT_ID,
                        "name": "Circuit",
                        "valve_ids": [VALVE_ID],
                        "pump_id": PUMP_ID,
                    }
                ],
                "routes": [{"id": ROUTE_ID, "zone_id": ZONE_ID, "circuit_id": CIRCUIT_ID}],
            },
        },
    )


async def test_external_state_changes_drive_demand_without_external_service_calls(hass) -> None:
    """External hvac_action is authoritative and its owner remains read-only."""
    hass.states.async_set("switch.external_valve", "off")
    hass.states.async_set("switch.external_pump", "off")
    hass.states.async_set(
        EXTERNAL_ENTITY,
        "heat",
        {"hvac_action": "heating", "temperature": 22.0, "current_temperature": 19.0},
    )
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    assert hass.states.get("climate.external_thermostat_plant_external_room") is None
    assert (
        hass.states.get("binary_sensor.external_thermostat_plant_external_room_demand").state
        == "on"
    )
    assert runtime.evaluation.diagnostics.zone_decisions[ZONE_ID].explanation.startswith(
        "External thermostat accepted authoritative heating"
    )
    first_evaluation_count = runtime.evaluation_count

    with patch.object(type(hass.services), "async_call", new=AsyncMock()) as service_call:
        hass.states.async_set(EXTERNAL_ENTITY, "heat", {"hvac_action": "idle"})
        await hass.async_block_till_done()
        assert runtime.evaluation_count > first_evaluation_count
        assert (
            hass.states.get("binary_sensor.external_thermostat_plant_external_room_demand").state
            == "off"
        )
        assert all(
            call.args[1:3] != ("climate", "set_temperature")
            and call.args[1:3] != ("climate", "set_preset_mode")
            and call.args[1:3] != ("climate", "set_hvac_mode")
            for call in service_call.call_args_list
        )

    hass.states.async_set(EXTERNAL_ENTITY, "unavailable", {"hvac_action": "heating"})
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.external_thermostat_plant_external_room_demand").state
        == "off"
    )
    assert "unavailable" in runtime.evaluation.diagnostics.zone_decisions[ZONE_ID].explanation

    serialized = runtime.serialized_presentation(hass)
    assert EXTERNAL_ENTITY not in serialized
    diagnostics = json.dumps(await async_get_config_entry_diagnostics(hass, entry), sort_keys=True)
    assert EXTERNAL_ENTITY not in diagnostics


async def test_missing_external_binding_creates_thermostat_repair(hass) -> None:
    """A missing external climate reference is actionable and fail-closed."""
    hass.states.async_set("switch.external_valve", "off")
    hass.states.async_set("switch.external_pump", "off")
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.external_thermostat_plant_external_room_demand").state
        == "off"
    )
    issues = issue_registry.async_get(hass).issues
    assert any(
        issue.domain == DOMAIN and issue.translation_key == "missing_thermostat_binding"
        for issue in issues.values()
    )


async def test_external_zone_visibility_uses_hydronicus_demand_acl(hass) -> None:
    """External Zones remain visible through their Hydronicus demand entity ACL."""
    hass.states.async_set("switch.external_valve", "off")
    hass.states.async_set("switch.external_pump", "off")
    hass.states.async_set(EXTERNAL_ENTITY, "heat", {"hvac_action": "idle"})
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    class _Permissions:
        def check_entity(self, entity_id: str, _permission: str) -> bool:
            return entity_id.endswith("external_room_demand")

    user = type("User", (), {"permissions": _Permissions()})()
    filtered = _filter_snapshot_for_user(
        entry.runtime_data.presentation_snapshot(hass),
        entry.runtime_data,
        hass,
        user,
    )
    assert [zone["id"] for zone in filtered["zones"]] == [ZONE_ID]
    assert filtered["zones"][0]["thermostat"]["control_entity_id"] is None
    assert EXTERNAL_ENTITY not in json.dumps(filtered, sort_keys=True)


async def test_switching_thermostat_kind_does_not_leave_a_duplicate_climate_entity(hass) -> None:
    """Changing ownership removes the old climate entity before re-adding it."""
    hass.states.async_set("sensor.internal_room", "18")
    hass.states.async_set("switch.external_valve", "off")
    hass.states.async_set("switch.external_pump", "off")
    entry = _entry(internal=True)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    climate_entity_id = "climate.external_thermostat_plant_internal_room"
    assert hass.states.get(climate_entity_id) is not None

    updated_data = dict(entry.data)
    updated_topology = dict(updated_data["topology"])
    updated_zone = dict(updated_topology["zones"][0])
    updated_zone["name"] = "External room"
    updated_zone["thermostat"] = {"kind": "external_climate", "entity_id": EXTERNAL_ENTITY}
    updated_zone["temperature_sensor_metadata"] = []
    updated_topology["zones"] = [updated_zone]
    updated_data["topology"] = updated_topology
    hass.states.async_set(EXTERNAL_ENTITY, "heat", {"hvac_action": "idle"})
    hass.config_entries.async_update_entry(entry, data=updated_data)
    await hass.async_block_till_done()

    assert entry.runtime_data.plant.zones[ZONE_ID].thermostat.kind.value == "external_climate"
    state = hass.states.get(climate_entity_id)
    assert state is None or state.state == "unavailable"
    assert not [
        current
        for current in hass.states.async_all("climate")
        if current.entity_id == climate_entity_id and current.state != "unavailable"
    ]


async def test_internal_thermostat_restores_mutable_state_without_changing_plant_mode(hass) -> None:
    """RestoreEntity returns target, preset, and Zone mode after a reload."""
    hass.states.async_set("sensor.internal_room", "18")
    hass.states.async_set("switch.external_valve", "off")
    hass.states.async_set("switch.external_pump", "off")
    entry = _entry(internal=True)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    climate_entity_id = "climate.external_thermostat_plant_internal_room"

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": climate_entity_id, "hvac_mode": "heat"},
        blocking=True,
    )
    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": climate_entity_id, "preset_mode": "comfort"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(climate_entity_id).attributes["temperature"] == 22.0
    assert hass.states.get(climate_entity_id).attributes["preset_mode"] == "comfort"
    assert hass.states.get(climate_entity_id).state == "heat"
    assert hass.states.get("select.external_thermostat_plant_requested_mode").state == "auto"

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restored = hass.states.get(climate_entity_id)
    assert restored.attributes["temperature"] == 22.0
    assert restored.attributes["preset_mode"] == "comfort"
    assert restored.state == "heat"
    assert hass.states.get("select.external_thermostat_plant_requested_mode").state == "auto"
