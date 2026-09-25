"""Zone subentries own their zone, routes, and private loops and valves."""

from __future__ import annotations

from types import MappingProxyType

from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.core.legacy.model import ThermostatHvacMode
from custom_components.hydronicus.entry_configuration import output_authorization
from custom_components.hydronicus.runtime import HydronicRuntime
from tests.integration.plant_fixtures import (
    MANIFOLD_PUMP_ENTITY,
    MANIFOLD_PUMP_ID,
    PLANT_ID,
    manifold_entry,
    manifold_zones,
    zone_subentry,
)

LIVING, BEDROOM = manifold_zones(("Living room", "Bedroom"))


def _set_states(hass) -> None:
    for zone in (LIVING, BEDROOM):
        hass.states.async_set(zone.temperature_sensor, "18.0")
        hass.states.async_set(zone.valve_entity, "off")
    hass.states.async_set(MANIFOLD_PUMP_ENTITY, "off")


def _entity(hass, domain: str, unique_id: str) -> er.RegistryEntry | None:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    return registry.async_get(entity_id) if entity_id is not None else None


def _device(hass, entry, kind: str, object_id: str) -> dr.DeviceEntry | None:
    return dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, f"{PLANT_ID}:{kind}:{object_id}"), entry.entry_id
    )


def _owned_registrations(hass, entry) -> dict[str, str | None]:
    """Map each object-scoped entity unique ID and device to its owning subentry."""
    owners: dict[str, str | None] = {}
    for registry_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        owners[f"entity:{registry_entry.unique_id}"] = registry_entry.config_subentry_id
    for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id):
        (identifier,) = device.identifiers
        owners[f"device:{identifier[1]}"] = device.config_subentry_id
    return owners


async def test_deleting_an_active_zone_reaches_dry_run_before_the_graph_changes(hass) -> None:
    """Deleting a zone of a live Plant completes safe shutdown against the old graph first."""
    calls: list[tuple[str, str]] = []

    async def record_switch(call) -> None:
        entity_id = call.data["entity_id"]
        calls.append((call.service, entity_id))
        hass.states.async_set(entity_id, "on" if call.service == "turn_on" else "off")

    hass.services.async_register("switch", "turn_on", record_switch)
    hass.services.async_register("switch", "turn_off", record_switch)
    _set_states(hass)
    entry = manifold_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    runtime = entry.runtime_data
    assert await runtime.async_set_dry_run(
        False, hass=hass, authorization=output_authorization(entry.data)
    )
    await runtime.async_set_zone_hvac_mode(BEDROOM.zone_id, ThermostatHvacMode.HEAT, hass=hass)
    await hass.async_block_till_done()
    assert BEDROOM.valve_id in runtime.active_equipment_ids()
    calls.clear()

    assert hass.config_entries.async_remove_subentry(
        entry, zone_subentry(entry, BEDROOM.zone_id).subentry_id
    )
    await hass.async_block_till_done()

    assert entry.data["dry_run"] is True
    assert "output_authorization" not in entry.data
    # The shutdown ran against the old graph, so it still reached the removed valve.
    assert calls == [
        ("turn_off", MANIFOLD_PUMP_ENTITY),
        ("turn_off", BEDROOM.valve_entity),
    ]
    plant = entry.runtime_data.plant
    assert BEDROOM.zone_id not in plant.zones
    assert BEDROOM.circuit_id not in plant.circuits
    assert BEDROOM.valve_id not in plant.valves
    assert set(plant.zones) == {LIVING.zone_id}


async def test_failed_shutdown_retains_the_parent_graph_after_zone_removal(
    hass, monkeypatch
) -> None:
    """A failed safety transition cannot delete the graph the active runtime uses."""
    _set_states(hass)
    entry = manifold_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    runtime = entry.runtime_data
    active_data = dict(entry.data)
    active_data["dry_run"] = False
    hass.config_entries.async_update_entry(entry, data=active_data)
    runtime.dry_run = False
    runtime.executor.dry_run = False
    attempts: list[HydronicRuntime] = []

    async def fail_transition(active_runtime: HydronicRuntime, _hass) -> bool:
        attempts.append(active_runtime)
        return False

    monkeypatch.setattr(HydronicRuntime, "async_prepare_configuration_change", fail_transition)

    assert hass.config_entries.async_remove_subentry(
        entry, zone_subentry(entry, BEDROOM.zone_id).subentry_id
    )
    await hass.async_block_till_done()

    assert attempts == [runtime]
    topology = entry.data["topology"]
    assert BEDROOM.zone_id in {zone["id"] for zone in topology["zones"]}
    assert BEDROOM.valve_id in {valve["id"] for valve in topology["valves"]}
    assert BEDROOM.valve_id in runtime.plant.valves
    assert entry.data["dry_run"] is False


async def test_deleting_a_zone_removes_its_entities_and_devices_and_the_plant_loads(
    hass,
) -> None:
    """A zone takes exactly its closure with it, and the rest of the Plant keeps working."""
    _set_states(hass)
    entry = manifold_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    bedroom_demand = f"{PLANT_ID}_{BEDROOM.zone_id}_demand"
    bedroom_valve = f"{PLANT_ID}_valve_{BEDROOM.valve_id}_requested"
    assert _entity(hass, "binary_sensor", bedroom_demand) is not None
    assert _entity(hass, "binary_sensor", bedroom_valve) is not None
    assert _device(hass, entry, "valve", BEDROOM.valve_id) is not None

    assert hass.config_entries.async_remove_subentry(
        entry, zone_subentry(entry, BEDROOM.zone_id).subentry_id
    )
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert _entity(hass, "binary_sensor", bedroom_demand) is None
    assert _entity(hass, "binary_sensor", bedroom_valve) is None
    assert _device(hass, entry, "zone", BEDROOM.zone_id) is None
    assert _device(hass, entry, "valve", BEDROOM.valve_id) is None
    assert _entity(hass, "binary_sensor", f"{PLANT_ID}_{LIVING.zone_id}_demand") is not None
    assert _entity(hass, "binary_sensor", f"{PLANT_ID}_pump_{MANIFOLD_PUMP_ID}_requested")
    assert entry.data["zone_objects"] == {
        LIVING.circuit_id: LIVING.zone_id,
        LIVING.valve_id: LIVING.zone_id,
    }
    assert entry.data["subentry_objects"] == {LIVING.zone_id: "zone"}
    assert [warning.code for warning in entry.runtime_data.plant.warnings] == []

    # With the last zone gone the pump is unused Plant equipment, which only warns.
    assert hass.config_entries.async_remove_subentry(
        entry, zone_subentry(entry, LIVING.zone_id).subentry_id
    )
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    plant = entry.runtime_data.plant
    assert plant.zones == {}
    assert set(plant.pumps) == {MANIFOLD_PUMP_ID}
    assert [(warning.code, warning.equipment_id) for warning in plant.warnings] == [
        ("unused_equipment", MANIFOLD_PUMP_ID)
    ]


async def test_devices_show_the_ui_names_of_their_kinds(hass) -> None:
    """A zone device reads as a Zone; the model is not part of any identifier or entity ID."""
    _set_states(hass)
    entry = manifold_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    zone = _device(hass, entry, "zone", LIVING.zone_id)
    assert zone is not None
    assert zone.model == "Hydronicus Zone"
    valve = _device(hass, entry, "valve", LIVING.valve_id)
    assert valve is not None
    assert valve.model == "Hydronicus Valve"
    pump = _device(hass, entry, "pump", MANIFOLD_PUMP_ID)
    assert pump is not None
    assert pump.model == "Hydronicus Pump"
    assert _entity(hass, "climate", f"{PLANT_ID}_{LIVING.zone_id}_climate") is not None


async def test_reload_reconstructs_zones_and_their_entity_ownership(hass) -> None:
    """Zone entities and devices belong to their zone, Plant equipment to the parent."""
    _set_states(hass)
    entry = manifold_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    living = zone_subentry(entry, LIVING.zone_id).subentry_id
    bedroom = zone_subentry(entry, BEDROOM.zone_id).subentry_id
    runtime = entry.runtime_data
    assert runtime.object_subentry_ids == {
        LIVING.zone_id: living,
        LIVING.circuit_id: living,
        LIVING.valve_id: living,
        BEDROOM.zone_id: bedroom,
        BEDROOM.circuit_id: bedroom,
        BEDROOM.valve_id: bedroom,
    }
    assert runtime.subentry_id_for(MANIFOLD_PUMP_ID) is None

    before = _owned_registrations(hass, entry)
    for zone, subentry_id in ((LIVING, living), (BEDROOM, bedroom)):
        assert before[f"entity:{PLANT_ID}_{zone.zone_id}_climate"] == subentry_id
        assert before[f"entity:{PLANT_ID}_valve_{zone.valve_id}_requested"] == subentry_id
        assert before[f"device:{PLANT_ID}:zone:{zone.zone_id}"] == subentry_id
        assert before[f"device:{PLANT_ID}:valve:{zone.valve_id}"] == subentry_id
    assert before[f"entity:{PLANT_ID}_pump_{MANIFOLD_PUMP_ID}_requested"] is None
    assert before[f"device:{PLANT_ID}:pump:{MANIFOLD_PUMP_ID}"] is None
    assert before[f"device:{PLANT_ID}"] is None
    assert before[f"entity:{PLANT_ID}_dry_run"] is None

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data is not runtime
    assert entry.runtime_data.object_subentry_ids == runtime.object_subentry_ids
    assert _owned_registrations(hass, entry) == before


async def test_a_handle_without_a_parent_record_fails_the_reload_it_triggers(hass, caplog) -> None:
    """A stored mismatch fails setup with a readable reason instead of in a background task."""
    _set_states(hass)
    entry = manifold_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    stray = "00000000-0000-4000-8000-00000000abcd"

    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data=MappingProxyType({"id": stray}),
            subentry_type="zone",
            title="Stray",
            unique_id=stray,
        ),
    )
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert "no matching parent ownership record" in caplog.text
    assert "Task exception was never retrieved" not in caplog.text


async def test_initial_setup_creates_one_zone_that_owns_its_loop_and_valve(hass) -> None:
    """Guided setup creates version 4 data: one zone, its loop and valve, a Plant pump."""
    hass.states.async_set("sensor.study_temperature", "18.0")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "guided"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "Study plant", "pump_entity": "switch.study_pump"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "zoning_grouped"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Study",
            "temperature_sensors": ["sensor.study_temperature"],
            "valves": ["switch.study_valve"],
        },
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert (entry.version, entry.minor_version) == (4, 0)
    topology = entry.data["topology"]
    (zone,) = topology["zones"]
    (circuit,) = topology["circuits"]
    (valve,) = topology["valves"]
    (pump,) = topology["pumps"]
    assert entry.data["subentry_objects"] == {zone["id"]: "zone"}
    assert entry.data["zone_objects"] == {circuit["id"]: zone["id"], valve["id"]: zone["id"]}
    (handle,) = entry.subentries.values()
    assert (handle.subentry_type, handle.unique_id, handle.title) == ("zone", zone["id"], "Study")
    assert dict(handle.data) == {"id": zone["id"]}
    runtime = entry.runtime_data
    assert runtime.subentry_id_for(valve["id"]) == handle.subentry_id
    assert runtime.subentry_id_for(pump["id"]) is None
    assert hass.states.get("climate.study") is not None
