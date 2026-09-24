"""Integration coverage for unresolved binding Repairs and degraded operation."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.components.repairs import DOMAIN as REPAIRS_DOMAIN
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.config_flow import SECTION_COOLING
from custom_components.hydronicus.const import (
    CONF_CIRCUIT_IDS,
    CONF_DRY_RUN,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_OPENING_TIME,
    CONF_PLANT_ID,
    CONF_PUMP_ID,
    CONF_SUPPLY_TEMPERATURE_SENSOR,
    CONF_VALVE_IDS,
    CONF_ZONE_IDS,
    DOMAIN,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_CIRCUIT,
)
from custom_components.hydronicus.core.model import ThermostatHvacMode

PLANT_ID = "00000000-0000-4000-8000-000000000001"
ZONE_A = "00000000-0000-4000-8000-000000000002"
ZONE_B = "00000000-0000-4000-8000-000000000003"
VALVE_A = "00000000-0000-4000-8000-000000000004"
VALVE_B = "00000000-0000-4000-8000-000000000005"
PUMP_A = "00000000-0000-4000-8000-000000000006"
PUMP_B = "00000000-0000-4000-8000-000000000007"
CIRCUIT_A = "00000000-0000-4000-8000-000000000008"
CIRCUIT_B = "00000000-0000-4000-8000-000000000009"
ROUTE_A = "00000000-0000-4000-8000-000000000010"
ROUTE_B = "00000000-0000-4000-8000-000000000011"

MISSING_SENSOR = "sensor.zone_a_temperature"
MISSING_VALVE = "switch.zone_a_valve"
MISSING_READINESS = "binary_sensor.zone_a_valve_ready"
MISSING_SUBENTRY_VALVE = "switch.repairs_subentry_valve"
RESTORED_SUBENTRY_VALVE = "switch.repairs_replacement_valve"
PARENT_OWNED_TRANSLATION_KEYS = {
    "missing_sensor_binding",
    "missing_feedback_binding",
    "missing_actuator_binding",
}


def _entry() -> MockConfigEntry:
    """Build two independent synthetic paths, one intentionally unresolved."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Synthetic plant",
        data={
            CONF_NAME: "Synthetic plant",
            CONF_PLANT_ID: PLANT_ID,
            CONF_DRY_RUN: True,
            "topology": {
                "zones": [
                    {
                        "id": ZONE_A,
                        "name": "Zone A",
                        "thermostat": {"kind": "hydronicus", "initial_target_temperature": 21.0},
                        "temperature_sensor_metadata": [{"entity_id": MISSING_SENSOR}],
                    },
                    {
                        "id": ZONE_B,
                        "name": "Zone B",
                        "thermostat": {"kind": "hydronicus", "initial_target_temperature": 21.0},
                        "temperature_sensor_metadata": [{"entity_id": "sensor.zone_b_temperature"}],
                    },
                ],
                "valves": [
                    {
                        "id": VALVE_A,
                        "name": "Zone A valve",
                        "entity_id": MISSING_VALVE,
                        "readiness_entity_id": MISSING_READINESS,
                    },
                    {
                        "id": VALVE_B,
                        "name": "Zone B valve",
                        "entity_id": "switch.zone_b_valve",
                    },
                ],
                "pumps": [
                    {
                        "id": PUMP_A,
                        "name": "Zone A pump",
                        "entity_id": "switch.zone_a_pump",
                    },
                    {
                        "id": PUMP_B,
                        "name": "Zone B pump",
                        "entity_id": "switch.zone_b_pump",
                    },
                ],
                "circuits": [
                    {
                        "id": CIRCUIT_A,
                        "name": "Zone A circuit",
                        "valve_ids": [VALVE_A],
                        "pump_id": PUMP_A,
                    },
                    {
                        "id": CIRCUIT_B,
                        "name": "Zone B circuit",
                        "valve_ids": [VALVE_B],
                        "pump_id": PUMP_B,
                    },
                ],
                "routes": [
                    {"id": ROUTE_A, "zone_id": ZONE_A, "circuit_id": CIRCUIT_A},
                    {"id": ROUTE_B, "zone_id": ZONE_B, "circuit_id": CIRCUIT_B},
                ],
            },
        },
    )


def _issues(hass):
    """Return active Hydronicus Repairs entries."""
    return {
        issue_id: issue
        for (domain, issue_id), issue in issue_registry.async_get(hass).issues.items()
        if domain == DOMAIN and issue.active
    }


def _register_synthetic_reference(hass, entity_id: str) -> None:
    """Keep a missing synthetic reference in the registry for rename coverage."""
    domain, object_id = entity_id.split(".", 1)
    er.async_get(hass).async_get_or_create(
        domain,
        "synthetic",
        f"repairs:{object_id}",
        suggested_object_id=object_id,
    )


async def test_setup_reload_and_restoration_create_and_remove_repairs(hass) -> None:
    """Missing bindings alert distinctly while the healthy path keeps evaluating."""
    for entity_id in (MISSING_SENSOR, MISSING_VALVE, MISSING_READINESS):
        _register_synthetic_reference(hass, entity_id)
    hass.states.async_set("sensor.zone_b_temperature", "18.0")
    hass.states.async_set("switch.zone_b_valve", "off")
    hass.states.async_set("switch.zone_b_pump", "off")
    hass.states.async_set("switch.zone_a_pump", "off")
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await entry.runtime_data.async_set_zone_hvac_mode(ZONE_A, ThermostatHvacMode.HEAT, hass=hass)
    await entry.runtime_data.async_set_zone_hvac_mode(ZONE_B, ThermostatHvacMode.HEAT, hass=hass)

    repairs = _issues(hass)
    translation_keys = {issue.translation_key for issue in repairs.values()}
    assert translation_keys == PARENT_OWNED_TRANSLATION_KEYS
    for issue in repairs.values():
        assert issue.is_fixable is False
        assert MISSING_SENSOR not in str(issue.translation_placeholders)
        assert MISSING_VALVE not in str(issue.translation_placeholders)
        assert MISSING_READINESS not in str(issue.translation_placeholders)
        assert issue.data is not None
        assert "entity_id" not in issue.data

    runtime = entry.runtime_data
    assert {
        zone_id: state.demand for zone_id, state in runtime.runtime_state.zone_runtime.items()
    } == {ZONE_A: False, ZONE_B: True}
    assert all(
        command.actuator_id not in {VALVE_A, PUMP_A}
        for command in runtime.evaluation.control_plan.commands
    )

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert {issue.translation_key for issue in _issues(hass).values()} == translation_keys

    hass.states.async_set(MISSING_SENSOR, "18.0")
    hass.states.async_set(MISSING_VALVE, "off")
    hass.states.async_set(MISSING_READINESS, "off")
    await hass.async_block_till_done()

    assert _issues(hass) == {}
    assert entry.runtime_data.unresolved_bindings == ()


async def test_unload_removes_repairs_for_removed_plant(hass) -> None:
    """Removing a configured plant does not leave its Repairs behind."""
    for entity_id in (MISSING_SENSOR, MISSING_VALVE, MISSING_READINESS):
        _register_synthetic_reference(hass, entity_id)
    hass.states.async_set("sensor.zone_b_temperature", "18.0")
    hass.states.async_set("switch.zone_b_valve", "off")
    hass.states.async_set("switch.zone_b_pump", "off")
    hass.states.async_set("switch.zone_a_pump", "off")
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _issues(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert _issues(hass) == {}


async def test_reconfigure_replaces_an_unresolved_binding_and_removes_its_repair(hass) -> None:
    """A valid reconfiguration removes the old binding repair after reload."""
    hass.states.async_set("sensor.zone_b_temperature", "18.0")
    hass.states.async_set("switch.zone_b_valve", "off")
    hass.states.async_set("switch.zone_b_pump", "off")
    hass.states.async_set("switch.zone_a_pump", "off")
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert any(
        issue.translation_key == "missing_actuator_binding" for issue in _issues(hass).values()
    )

    updated_data = dict(entry.data)
    updated_data["topology"] = dict(entry.data["topology"])
    updated_data["topology"]["valves"] = [dict(valve) for valve in entry.data["topology"]["valves"]]
    updated_data["topology"]["valves"][0]["entity_id"] = "switch.reconfigured_zone_a_valve"
    hass.states.async_set("switch.reconfigured_zone_a_valve", "off")
    hass.config_entries.async_update_entry(entry, data=updated_data)
    await hass.async_block_till_done()

    assert entry.runtime_data.plant.valves[VALVE_A].entity_id == "switch.reconfigured_zone_a_valve"
    assert all(
        issue.translation_key != "missing_actuator_binding" for issue in _issues(hass).values()
    )
    assert any(
        issue.translation_key == "missing_sensor_binding" for issue in _issues(hass).values()
    )


def _set_healthy_parent_states(hass) -> None:
    """Resolve every parent-owned binding so only subentry repairs remain."""
    for entity_id in (
        MISSING_SENSOR,
        MISSING_VALVE,
        MISSING_READINESS,
        "sensor.zone_b_temperature",
        "switch.zone_b_valve",
        "switch.zone_b_pump",
        "switch.zone_a_pump",
    ):
        hass.states.async_set(entity_id, "18.0" if entity_id.startswith("sensor.") else "off")


async def _setup_with_unresolved_subentry_valve(hass) -> tuple[MockConfigEntry, str, str]:
    """Add a valve through its subentry flow while its actuator entity is missing."""
    _set_healthy_parent_states(hass)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _issues(hass) == {}

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_ACTUATOR),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Return valve",
            CONF_ENTITY_ID: MISSING_SUBENTRY_VALVE,
            CONF_OPENING_TIME: 45.0,
            CONF_CIRCUIT_IDS: [CIRCUIT_B],
        },
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    subentry = next(iter(entry.subentries.values()))

    repairs = _issues(hass)
    assert len(repairs) == 1
    issue_id, issue = next(iter(repairs.items()))
    assert issue.translation_key == "missing_actuator_binding_fixable"
    assert issue.is_fixable is True
    assert issue.data == {
        "object_id": subentry.data["id"],
        "binding_key": "actuator",
        "binding_category": "actuator",
        "entry_id": entry.entry_id,
        "subentry_id": subentry.subentry_id,
    }
    assert MISSING_SUBENTRY_VALVE not in str(issue.translation_placeholders)
    return entry, subentry.subentry_id, issue_id


async def test_parent_owned_binding_repairs_are_not_fixable(hass) -> None:
    """Objects created with the plant have no subentry reconfigure flow to open."""
    hass.states.async_set("sensor.zone_b_temperature", "18.0")
    hass.states.async_set("switch.zone_b_valve", "off")
    hass.states.async_set("switch.zone_b_pump", "off")
    hass.states.async_set("switch.zone_a_pump", "off")
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    repairs = _issues(hass)
    assert {issue.translation_key for issue in repairs.values()} == PARENT_OWNED_TRANSLATION_KEYS
    for issue in repairs.values():
        assert issue.is_fixable is False
        assert issue.data is not None
        assert "subentry_id" not in issue.data


async def test_subentry_binding_repair_opens_owning_subentry_reconfigure_flow(
    hass, hass_client
) -> None:
    """The fix flow hands off to the owning subentry, and the repair clears once restored."""
    assert await async_setup_component(hass, REPAIRS_DOMAIN, {})
    entry, subentry_id, issue_id = await _setup_with_unresolved_subentry_valve(hass)
    valve_id = entry.subentries[subentry_id].data["id"]
    client = await hass_client()

    response = await client.post(
        "/api/repairs/issues/fix", json={"handler": DOMAIN, "issue_id": issue_id}
    )
    assert response.status == 200
    result = await response.json()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"]["object_name"] == "Return valve"

    response = await client.post(f"/api/repairs/issues/fix/{result['flow_id']}", json={})
    assert response.status == 200
    result = await response.json()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_subentry"
    assert result["description_placeholders"]["object_name"] == "Return valve"
    assert result["result"]["entry_id"] == entry.entry_id
    flow_type, next_flow_id = result["next_flow"]
    assert flow_type == "config_subentries_flow"

    subentry_flow = hass.config_entries.subentries.async_get(next_flow_id)
    assert subentry_flow["handler"] == (entry.entry_id, SUBENTRY_TYPE_ACTUATOR)
    assert subentry_flow["context"]["source"] == config_entries.SOURCE_RECONFIGURE
    assert subentry_flow["context"]["subentry_id"] == subentry_id
    assert subentry_flow["step_id"] == "reconfigure"
    # Handing off does not claim the repair is fixed while the binding is still missing.
    assert issue_id in _issues(hass)

    hass.states.async_set(RESTORED_SUBENTRY_VALVE, "off")
    result = await hass.config_entries.subentries.async_configure(
        next_flow_id,
        user_input={
            CONF_NAME: "Return valve",
            CONF_ENTITY_ID: RESTORED_SUBENTRY_VALVE,
            CONF_OPENING_TIME: 45.0,
            CONF_CIRCUIT_IDS: [CIRCUIT_B],
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.runtime_data.plant.valves[valve_id].entity_id == RESTORED_SUBENTRY_VALVE
    assert _issues(hass) == {}


async def test_subentry_binding_repair_clears_when_the_entity_returns(hass) -> None:
    """A fixable repair still clears automatically when its entity comes back."""
    _, _, issue_id = await _setup_with_unresolved_subentry_valve(hass)
    assert issue_id in _issues(hass)

    hass.states.async_set(MISSING_SUBENTRY_VALVE, "off")
    await hass.async_block_till_done()

    assert _issues(hass) == {}


async def test_fix_flow_aborts_when_the_owning_subentry_is_gone(hass) -> None:
    """A fix flow opened before its subentry was removed aborts without a hand-off."""
    assert await async_setup_component(hass, REPAIRS_DOMAIN, {})
    entry, subentry_id, issue_id = await _setup_with_unresolved_subentry_valve(hass)
    manager = hass.data[REPAIRS_DOMAIN]["flow_manager"]

    result = await manager.async_init(DOMAIN, data={"issue_id": issue_id})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"

    assert hass.config_entries.async_remove_subentry(entry, subentry_id)
    await hass.async_block_till_done()
    assert _issues(hass) == {}

    result = await manager.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "subentry_not_found"
    assert "next_flow" not in result
    assert hass.config_entries.subentries.async_progress() == []


async def test_circuit_subentry_sensor_repair_opens_circuit_reconfigure_flow(hass) -> None:
    """Circuit-owned reference sensors hand off to the owning circuit subentry."""
    assert await async_setup_component(hass, REPAIRS_DOMAIN, {})
    _set_healthy_parent_states(hass)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_CIRCUIT),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Secondary loop",
            CONF_ZONE_IDS: [ZONE_B],
            CONF_VALVE_IDS: [VALVE_B],
            CONF_PUMP_ID: PUMP_B,
            SECTION_COOLING: {CONF_SUPPLY_TEMPERATURE_SENSOR: "sensor.repairs_missing_supply"},
        },
    )
    if result["type"] == FlowResultType.FORM and result["step_id"] == "review":
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], user_input={"confirm": True}
        )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    subentry = next(iter(entry.subentries.values()))

    repairs = _issues(hass)
    assert len(repairs) == 1
    issue_id, issue = next(iter(repairs.items()))
    assert issue.translation_key == "missing_sensor_binding_fixable"
    assert issue.is_fixable is True
    assert issue.data is not None
    assert issue.data["subentry_id"] == subentry.subentry_id

    manager = hass.data[REPAIRS_DOMAIN]["flow_manager"]
    result = await manager.async_init(DOMAIN, data={"issue_id": issue_id})
    result = await manager.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.ABORT
    subentry_flow = hass.config_entries.subentries.async_get(result["next_flow"][1])
    assert subentry_flow["handler"] == (entry.entry_id, SUBENTRY_TYPE_CIRCUIT)
    assert subentry_flow["context"]["subentry_id"] == subentry.subentry_id
    assert subentry_flow["step_id"] == "reconfigure"
