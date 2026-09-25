"""The room subentry flow adds and edits rooms with their private loops and valves."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import DOMAIN, SUBENTRY_TYPE_ROOM
from custom_components.hydronicus.core.model import ThermostatHvacMode
from custom_components.hydronicus.entry_configuration import (
    effective_plant,
    output_authorization,
    room_draft,
)
from custom_components.hydronicus.flows import room_form
from custom_components.hydronicus.runtime import HydronicRuntime
from tests.integration.flow_forms import form_fields, form_value, frontend_submission
from tests.integration.plant_fixtures import (
    MANIFOLD_PUMP_ENTITY,
    MANIFOLD_PUMP_ID,
    manifold_entry,
    manifold_rooms,
    manifold_topology,
    plant_data,
    plant_entry,
    room_subentry,
)

LIVING, BEDROOM = manifold_rooms(("Living room", "Bedroom"))
SECOND_PUMP_ID = "00000000-0000-4000-8000-000500000002"
SECOND_PUMP_ENTITY = "switch.second_pump"
SHARED_LOOP_ID = "00000000-0000-4000-8000-000600000001"
SHARED_VALVE_ID = "00000000-0000-4000-8000-000600000002"
SHARED_VALVE_ENTITY = "switch.shared_manifold_valve"
OTHER_PLANT_ID = "00000000-0000-4000-8000-00000000f001"
LIVING_INPUT = {
    "name": "Living room",
    "temperature_sensors": [LIVING.temperature_sensor],
    "valves": [LIVING.valve_entity],
}
BEDROOM_INPUT = {
    "name": "Bedroom",
    "temperature_sensors": [BEDROOM.temperature_sensor],
    "valves": [BEDROOM.valve_entity],
}


def _pump(pump_id: str = MANIFOLD_PUMP_ID, entity_id: str = MANIFOLD_PUMP_ENTITY) -> dict:
    name = "Manifold pump" if pump_id == MANIFOLD_PUMP_ID else "Second pump"
    return {"id": pump_id, "name": name, "entity_id": entity_id, "overrun_seconds": 0.0}


def _pump_only_entry(*, pumps: int = 1, **kwargs: Any) -> MockConfigEntry:
    """Return a Plant with pumps and nothing else, the start of a room-by-room setup."""
    topology = {"pumps": [_pump(), _pump(SECOND_PUMP_ID, SECOND_PUMP_ENTITY)][:pumps]}
    return plant_entry(plant_data(topology), **kwargs)


def _with_shared_loop(topology: dict) -> dict:
    """Add a Plant-owned loop with a Plant-owned valve that no room uses yet."""
    topology.setdefault("valves", []).append(
        {
            "id": SHARED_VALVE_ID,
            "name": "Shared valve",
            "entity_id": SHARED_VALVE_ENTITY,
            "opening_time_seconds": 0.0,
        }
    )
    topology.setdefault("circuits", []).append(
        {
            "id": SHARED_LOOP_ID,
            "name": "Shared loop",
            "valve_ids": [SHARED_VALVE_ID],
            "pump_id": MANIFOLD_PUMP_ID,
        }
    )
    return topology


def _set_states(hass) -> None:
    for room in (LIVING, BEDROOM):
        hass.states.async_set(room.temperature_sensor, "20.0")
        hass.states.async_set(room.valve_entity, "off")
    for entity_id in (
        MANIFOLD_PUMP_ENTITY,
        SECOND_PUMP_ENTITY,
        SHARED_VALVE_ENTITY,
        "switch.living_room_valve_2",
        "switch.living_room_extra_valve",
        "binary_sensor.living_room_valve_ready",
    ):
        hass.states.async_set(entity_id, "off")
    for entity_id in (
        "sensor.living_room_temperature_2",
        "sensor.living_room_supply",
        "sensor.living_room_valve_position",
    ):
        hass.states.async_set(entity_id, "20.0")
    hass.states.async_set("sensor.living_room_humidity", "50.0")
    hass.states.async_set("climate.living_room_thermostat", "heat")


async def _setup(hass, entry: MockConfigEntry) -> MockConfigEntry:
    _set_states(hass)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _start_room(hass, entry: MockConfigEntry) -> dict:
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_ROOM), context={"source": config_entries.SOURCE_USER}
    )


async def _configure(hass, result: Mapping[str, Any], user_input: Mapping[str, Any]) -> dict:
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], dict(user_input)
    )
    await hass.async_block_till_done()
    return result


async def _confirmed(hass, result: dict) -> dict:
    """Confirm a review step when one is shown."""
    if result["type"] == FlowResultType.FORM and result["step_id"] == "review":
        result = await _configure(hass, result, {"confirm": True})
    return result


async def _add_room(hass, entry: MockConfigEntry, user_input: Mapping[str, Any]) -> dict:
    result = await _start_room(hass, entry)
    assert result["step_id"] == "user"
    return await _confirmed(hass, await _configure(hass, result, user_input))


async def _menu(hass, entry: MockConfigEntry, zone_id: str, option: str | None = None) -> dict:
    result = await entry.start_subentry_reconfigure_flow(
        hass, room_subentry(entry, zone_id).subentry_id
    )
    assert result["type"] == FlowResultType.MENU
    if option is None:
        return result
    return await _configure(hass, result, {"next_step_id": option})


def _warning_codes(entry: MockConfigEntry) -> set[str]:
    return {warning.code for warning in effective_plant(entry).compiled.warnings}


def _zone_id(entry: MockConfigEntry, name: str) -> str:
    return next(zone["id"] for zone in entry.data["topology"]["zones"] if zone["name"] == name)


def _ids(entry: MockConfigEntry, zone_id: str) -> dict[str, Any]:
    """Return the stored ids of one room, by collection."""
    draft = room_draft(entry.data, zone_id)
    return {
        "zone": draft.zone["id"],
        "circuits": [circuit["id"] for circuit in draft.circuits],
        "valves": {valve["entity_id"]: valve["id"] for valve in draft.valves},
        "routes": [route["id"] for route in draft.routes],
    }


def _own_entity(hass, domain: str, object_id: str) -> str:
    """Register an entity that Hydronicus provides, which no form may bind."""
    registry_entry = er.async_get(hass).async_get_or_create(
        domain, DOMAIN, f"own-{object_id}", suggested_object_id=object_id
    )
    hass.states.async_set(registry_entry.entity_id, "20.0")
    return registry_entry.entity_id


# --------------------------------------------------------------------------
# Adding rooms
# --------------------------------------------------------------------------


async def test_rooms_on_one_pump_get_independent_private_loops(hass) -> None:
    """The Evidence scenario: each room gets its own loop and valve on the shared pump."""
    entry = await _setup(hass, _pump_only_entry())

    result = await _add_room(hass, entry, LIVING_INPUT)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    result = await _start_room(hass, entry)
    result = await _configure(hass, result, BEDROOM_INPUT)
    # The second loop on the pump is the only warning, and it is reviewed.
    assert result["step_id"] == "review"
    assert "Pump Manifold pump is shared" in result["description_placeholders"]["warnings"]
    result = await _configure(hass, result, {"confirm": True})
    assert result["type"] == FlowResultType.CREATE_ENTRY

    topology = entry.data["topology"]
    zones = {zone["id"]: zone["name"] for zone in topology["zones"]}
    circuits = {circuit["id"]: circuit for circuit in topology["circuits"]}
    valves = {valve["id"]: valve for valve in topology["valves"]}
    delivery = {
        zones[route["zone_id"]]: [
            (circuits[route["circuit_id"]]["name"], valves[valve_id]["name"])
            for valve_id in circuits[route["circuit_id"]]["valve_ids"]
        ]
        for route in topology["routes"]
    }
    assert delivery == {
        "Living room": [("Living room loop", "Living room loop valve")],
        "Bedroom": [("Bedroom loop", "Bedroom loop valve")],
    }
    assert {valve["name"]: valve["entity_id"] for valve in valves.values()} == {
        "Living room loop valve": LIVING.valve_entity,
        "Bedroom loop valve": BEDROOM.valve_entity,
    }
    assert {circuit["pump_id"] for circuit in circuits.values()} == {MANIFOLD_PUMP_ID}
    owners = entry.data["room_objects"]
    for zone_id in zones:
        draft = room_draft(entry.data, zone_id)
        assert {owners[circuit["id"]] for circuit in draft.circuits} == {zone_id}
        assert {owners[valve["id"]] for valve in draft.valves} == {zone_id}
    assert _warning_codes(entry) == {"shared_pump_limits_independent_control"}
    assert {
        subentry.unique_id: subentry.title
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_ROOM
    } == zones
    assert entry.data["dry_run"] is True
    assert entry.state is ConfigEntryState.LOADED
    assert set(entry.runtime_data.plant.zones) == set(zones)


@pytest.mark.parametrize("order", [("Living room", "Bedroom"), ("Bedroom", "Living room")])
async def test_deleting_each_room_leaves_a_plant_that_loads(hass, order) -> None:
    """Removing rooms in turn leaves a loading Plant, with only unused equipment at the end."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(hass, entry, LIVING_INPUT)
    await _add_room(hass, entry, BEDROOM_INPUT)
    zone_ids = {name: _zone_id(entry, name) for name in order}

    first, second = order
    assert hass.config_entries.async_remove_subentry(
        entry, room_subentry(entry, zone_ids[first]).subentry_id
    )
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert _warning_codes(entry) == set()
    assert [zone["name"] for zone in entry.data["topology"]["zones"]] == [second]
    assert [circuit["name"] for circuit in entry.data["topology"]["circuits"]] == [f"{second} loop"]

    assert hass.config_entries.async_remove_subentry(
        entry, room_subentry(entry, zone_ids[second]).subentry_id
    )
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert _warning_codes(entry) == {"unused_equipment"}
    topology = entry.data["topology"]
    assert (topology["zones"], topology["circuits"], topology["valves"], topology["routes"]) == (
        [],
        [],
        [],
        [],
    )
    assert [pump["id"] for pump in topology["pumps"]] == [MANIFOLD_PUMP_ID]
    assert entry.data["room_objects"] == {}


async def test_adding_a_room_needs_a_pump(hass) -> None:
    """Without a pump no loop can run, so the room flow explains that first."""
    entry = await _setup(hass, plant_entry(plant_data({})))

    result = await _start_room(hass, entry)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_pumps"


async def test_the_pump_is_asked_for_only_when_there_is_a_choice(hass) -> None:
    """One pump is implied; with two pumps the form asks, and requires an answer."""
    single = await _setup(hass, _pump_only_entry())
    result = await _start_room(hass, single)
    assert "pump" not in form_fields(result)
    assert "shared_loops" not in form_fields(result)

    entry = _pump_only_entry(pumps=2)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    result = await _start_room(hass, entry)
    assert "pump" in form_fields(result)

    result = await _configure(hass, result, LIVING_INPUT)
    assert result["errors"] == {"pump": "pump_required"}
    # A rejected form keeps what the user submitted.
    assert form_value(result, "valves") == [LIVING.valve_entity]
    result = await _configure(hass, result, {**LIVING_INPUT, "pump": SECOND_PUMP_ID})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    (circuit,) = entry.data["topology"]["circuits"]
    assert circuit["pump_id"] == SECOND_PUMP_ID


async def test_a_room_can_use_a_shared_loop_without_private_valves(hass) -> None:
    """Shared loops are offered when they exist, and are enough to deliver heat."""
    topology = _with_shared_loop({"pumps": [_pump()]})
    entry = await _setup(hass, plant_entry(plant_data(topology)))
    result = await _start_room(hass, entry)
    options = form_fields(result)["shared_loops"]["selector"]["select"]["options"]
    assert options == [{"value": SHARED_LOOP_ID, "label": "Shared loop"}]

    result = await _configure(
        hass,
        result,
        {
            "name": "Living room",
            "temperature_sensors": [LIVING.temperature_sensor],
            "shared_loops": [SHARED_LOOP_ID],
        },
    )
    result = await _confirmed(hass, result)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    zone_id = _zone_id(entry, "Living room")
    draft = room_draft(entry.data, zone_id)
    assert (draft.circuits, draft.valves) == ([], [])
    assert [route["circuit_id"] for route in draft.routes] == [SHARED_LOOP_ID]
    assert entry.data["room_objects"] == {}
    assert _warning_codes(entry) == set()


async def test_empty_required_selections_are_reported_on_their_fields(hass) -> None:
    """A lazily loaded picker can submit an empty list, which the flow rejects by field."""
    entry = await _setup(hass, _pump_only_entry())
    result = await _start_room(hass, entry)

    result = await _configure(hass, result, {"name": " ", "temperature_sensors": [], "valves": []})

    assert result["errors"] == {
        "name": "name_required",
        "temperature_sensors": "temperature_sensors_required",
        "base": "delivery_required",
    }
    assert entry.data["topology"]["zones"] == []


async def test_an_external_thermostat_room_needs_no_temperature_sensor(hass) -> None:
    """An existing climate entity owns demand, so temperature sensors become optional."""
    entry = await _setup(hass, _pump_only_entry())

    result = await _add_room(
        hass,
        entry,
        {
            "name": "Living room",
            "external_climate_entity": "climate.living_room_thermostat",
            "valves": [LIVING.valve_entity],
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    (zone,) = entry.data["topology"]["zones"]
    assert zone["thermostat"] == {
        "kind": "external_climate",
        "entity_id": "climate.living_room_thermostat",
    }
    assert zone["temperature_sensor_metadata"] == []


async def test_a_valve_entity_bound_elsewhere_in_the_plant_is_rejected(hass) -> None:
    """One entity cannot drive two actuators of a Plant, so the valves field says so."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(hass, entry, LIVING_INPUT)
    data = dict(entry.data)
    result = await _start_room(hass, entry)

    for entity_id in (LIVING.valve_entity, MANIFOLD_PUMP_ENTITY):
        result = await _configure(hass, result, {**BEDROOM_INPUT, "valves": [entity_id]})
        assert result["errors"] == {"valves": "actuator_entity_in_use"}
        assert form_value(result, "valves") == [entity_id]

    assert dict(entry.data) == data


async def test_room_forms_hide_hydronicus_entities(hass) -> None:
    """Pickers leave out Hydronicus entities, which would feed the Plant back into itself."""
    entry = await _setup(hass, _pump_only_entry())
    own_switch = _own_entity(hass, "switch", "own_valve")
    own_sensor = _own_entity(hass, "sensor", "own_temperature")

    result = await _start_room(hass, entry)
    fields = form_fields(result)

    assert own_switch in fields["valves"]["selector"]["entity"]["exclude_entities"]
    assert own_sensor in fields["temperature_sensors"]["selector"]["entity"]["exclude_entities"]
    assert own_sensor in fields["external_climate_entity"]["selector"]["entity"]["exclude_entities"]


async def test_a_new_room_whose_id_is_taken_aborts_without_saving(hass, monkeypatch) -> None:
    """A zone id that already names a subentry aborts before the graph changes."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(hass, entry, LIVING_INPUT)
    data = dict(entry.data)
    taken = iter([_zone_id(entry, "Living room")])
    real_uuid4 = room_form.uuid4
    monkeypatch.setattr(room_form, "uuid4", lambda: next(taken, None) or real_uuid4())

    result = await _start_room(hass, entry)
    result = await _configure(hass, result, BEDROOM_INPUT)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert dict(entry.data) == data


# --------------------------------------------------------------------------
# Output sharing with other Plants, review, and Dry run
# --------------------------------------------------------------------------


def _other_plant_binding_living_valve(hass) -> MockConfigEntry:
    """Store another Plant that already binds the Living room valve entity."""
    other = plant_entry(
        plant_data(manifold_topology(("Living room",)), plant_id=OTHER_PLANT_ID),
        title="Plant 1",
    )
    other.add_to_hass(hass)
    return other


async def test_a_valve_bound_by_another_plant_is_a_reviewed_warning(hass) -> None:
    """Dry run Plants may share outputs, so sharing is confirmed rather than refused."""
    _other_plant_binding_living_valve(hass)
    entry = await _setup(hass, _pump_only_entry(title="Plant 2"))

    result = await _start_room(hass, entry)
    result = await _configure(hass, result, LIVING_INPUT)

    assert result["step_id"] == "review"
    assert not result.get("errors")
    warnings = result["description_placeholders"]["warnings"]
    assert LIVING.valve_entity in warnings
    assert "Plant 1" in warnings
    assert entry.data["topology"]["zones"] == []
    result = await _configure(hass, result, {"confirm": False})
    assert result["errors"] == {"base": "confirm_required"}
    result = await _configure(hass, result, {"confirm": True})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert [valve["entity_id"] for valve in entry.data["topology"]["valves"]] == [
        LIVING.valve_entity
    ]


async def test_moving_a_loop_valve_onto_another_plants_output_is_reviewed(hass) -> None:
    """The reconfigure twin: a loop edit that binds another Plant's valve is reviewed."""
    _other_plant_binding_living_valve(hass)
    entry = await _setup(hass, _pump_only_entry(title="Plant 2"))
    await _add_room(hass, entry, {**LIVING_INPUT, "valves": ["switch.living_room_extra_valve"]})
    zone_id = _zone_id(entry, "Living room")

    result = await _menu(hass, entry, zone_id, "edit_loop")
    result = await _configure(hass, result, {"loop": _ids(entry, zone_id)["circuits"][0]})
    submission = frontend_submission(result)
    result = await _configure(hass, result, {**submission, "valves": [LIVING.valve_entity]})

    assert result["step_id"] == "review"
    assert "Plant 1" in result["description_placeholders"]["warnings"]
    result = await _configure(hass, result, {"confirm": True})
    assert result["reason"] == "reconfigure_successful"
    assert [valve["entity_id"] for valve in entry.data["topology"]["valves"]] == [
        LIVING.valve_entity
    ]


async def test_a_live_plant_reaches_dry_run_before_a_room_is_saved(hass, monkeypatch) -> None:
    """When the safe shutdown cannot finish, nothing is stored and the user can retry."""
    entry = await _setup(hass, manifold_entry(("Living room",), dry_run=False))
    assert entry.runtime_data.dry_run is False
    data = dict(entry.data)
    zone_id = LIVING.zone_id

    async def shutdown_pending(self, dry_run, **kwargs) -> bool:
        return False

    monkeypatch.setattr(HydronicRuntime, "async_set_dry_run", shutdown_pending)

    # A change without warnings is saved straight from its form.
    result = await _menu(hass, entry, zone_id, "thermostat")
    result = await _configure(hass, result, frontend_submission(result))
    assert result["step_id"] == "thermostat"
    assert result["errors"] == {"base": "dry_run_shutdown_in_progress"}

    # A reviewed change retries from the review.
    result = await _start_room(hass, entry)
    result = await _configure(hass, result, BEDROOM_INPUT)
    assert result["step_id"] == "review"
    result = await _configure(hass, result, {"confirm": True})
    assert result["step_id"] == "review"
    assert result["errors"] == {"base": "dry_run_shutdown_in_progress"}
    assert dict(entry.data) == data

    monkeypatch.undo()
    result = await _configure(hass, result, {"confirm": True})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data["dry_run"] is True
    assert "output_authorization" not in entry.data


# --------------------------------------------------------------------------
# Reconfiguring rooms
# --------------------------------------------------------------------------


async def test_the_reconfigure_menu_offers_what_the_room_has(hass) -> None:
    """Thermostat settings need a Hydronicus thermostat; loop editing needs a private loop."""
    topology = _with_shared_loop({"pumps": [_pump()]})
    entry = await _setup(hass, plant_entry(plant_data(topology)))
    await _add_room(hass, entry, LIVING_INPUT)
    await _add_room(
        hass,
        entry,
        {
            "name": "Bedroom",
            "external_climate_entity": "climate.living_room_thermostat",
            "shared_loops": [SHARED_LOOP_ID],
        },
    )

    living = await _menu(hass, entry, _zone_id(entry, "Living room"))
    bedroom = await _menu(hass, entry, _zone_id(entry, "Bedroom"))

    assert living["menu_options"] == ["room", "thermostat", "sensors", "add_loop", "edit_loop"]
    assert bedroom["menu_options"] == ["room", "sensors", "add_loop"]


async def test_room_step_keeps_ids_and_switches_the_thermostat(hass) -> None:
    """Editing the room keeps every id; the thermostat kind switch drops or resets settings."""
    topology = _with_shared_loop({"pumps": [_pump()]})
    entry = await _setup(hass, plant_entry(plant_data(topology)))
    await _add_room(hass, entry, {**LIVING_INPUT, "shared_loops": [SHARED_LOOP_ID]})
    zone_id = _zone_id(entry, "Living room")
    before = _ids(entry, zone_id)

    result = await _menu(hass, entry, zone_id, "room")
    assert result["step_id"] == "room"
    assert set(form_fields(result)) == {
        "name",
        "temperature_sensors",
        "external_climate_entity",
        "shared_loops",
    }
    assert form_value(result, "shared_loops") == [SHARED_LOOP_ID]
    result = await _configure(
        hass,
        result,
        {
            **frontend_submission(result),
            "name": "Lounge",
            "external_climate_entity": "climate.living_room_thermostat",
        },
    )
    result = await _confirmed(hass, result)
    assert result["reason"] == "reconfigure_successful"
    assert _ids(entry, zone_id) == before
    zone = room_draft(entry.data, zone_id).zone
    assert zone["name"] == "Lounge"
    assert zone["thermostat"] == {
        "kind": "external_climate",
        "entity_id": "climate.living_room_thermostat",
    }
    assert room_subentry(entry, zone_id).title == "Lounge"

    result = await _menu(hass, entry, zone_id, "room")
    submission = frontend_submission(result)
    submission.pop("external_climate_entity")
    result = await _confirmed(
        hass, await _configure(hass, result, {**submission, "shared_loops": []})
    )
    assert result["reason"] == "reconfigure_successful"
    after = _ids(entry, zone_id)
    assert after == {**before, "routes": before["routes"][:1]}
    thermostat = room_draft(entry.data, zone_id).zone["thermostat"]
    assert thermostat["kind"] == "hydronicus"
    assert thermostat["heating_start_delta"] == 0.3


async def test_a_room_without_private_loops_keeps_a_shared_loop(hass) -> None:
    """Dropping the last shared loop of a room without private loops leaves no delivery."""
    topology = _with_shared_loop({"pumps": [_pump()]})
    entry = await _setup(hass, plant_entry(plant_data(topology)))
    await _add_room(
        hass,
        entry,
        {
            "name": "Living room",
            "temperature_sensors": [LIVING.temperature_sensor],
            "shared_loops": [SHARED_LOOP_ID],
        },
    )
    zone_id = _zone_id(entry, "Living room")

    result = await _menu(hass, entry, zone_id, "room")
    result = await _configure(hass, result, {**frontend_submission(result), "shared_loops": []})

    assert result["errors"] == {"base": "delivery_required"}


async def test_thermostat_step_keeps_ids(hass) -> None:
    """Thermostat settings change only the thermostat record."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(hass, entry, LIVING_INPUT)
    zone_id = _zone_id(entry, "Living room")
    before = _ids(entry, zone_id)

    result = await _menu(hass, entry, zone_id, "thermostat")
    assert "cooling.cooling_start_delta" in form_fields(result)
    submission = frontend_submission(result)
    submission["cooling"]["cooling_start_delta"] = 0.8
    result = await _configure(
        hass, result, {**submission, "heating_start_delta": 0.5, "comfort": 22.0}
    )

    assert result["reason"] == "reconfigure_successful"
    assert _ids(entry, zone_id) == before
    thermostat = room_draft(entry.data, zone_id).zone["thermostat"]
    assert thermostat["heating_start_delta"] == 0.5
    assert thermostat["cooling_start_delta"] == 0.8
    assert thermostat["preset_targets"] == {"comfort": 22.0}
    assert thermostat["initial_target_temperature"] == 21.0


async def test_sensors_step_edits_metadata_and_policy_and_keeps_ids(hass) -> None:
    """The sensor editor and policy steps keep ids and store typed metadata."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(
        hass,
        entry,
        {
            **LIVING_INPUT,
            "temperature_sensors": [LIVING.temperature_sensor, "sensor.living_room_temperature_2"],
        },
    )
    zone_id = _zone_id(entry, "Living room")
    before = _ids(entry, zone_id)

    result = await _menu(hass, entry, zone_id, "sensors")
    assert set(form_fields(result)) == {
        "temperature_aggregation",
        "humidity_sensors",
        "configure_sensor_metadata",
    }
    result = await _configure(
        hass,
        result,
        {"temperature_aggregation": "weighted_mean", "humidity_sensors": []},
    )
    assert result["errors"] == {"base": "sensor_metadata_required"}
    result = await _configure(
        hass,
        result,
        {
            "temperature_aggregation": "mean",
            "humidity_sensors": ["sensor.living_room_humidity"],
            "configure_sensor_metadata": True,
        },
    )
    assert result["step_id"] == "sensor_metadata"
    assert result["description_placeholders"] == {"sensor": LIVING.temperature_sensor}
    result = await _configure(hass, result, {**frontend_submission(result), "weight": 3.0})
    assert result["description_placeholders"] == {"sensor": "sensor.living_room_temperature_2"}
    result = await _configure(hass, result, frontend_submission(result))
    assert result["step_id"] == "sensor_policy"
    result = await _configure(hass, result, {"temperature_aggregation": "weighted_mean"})

    assert result["reason"] == "reconfigure_successful"
    assert _ids(entry, zone_id) == before
    zone = room_draft(entry.data, zone_id).zone
    assert zone["temperature_aggregation"] == "weighted_mean"
    assert [record["weight"] for record in zone["temperature_sensor_metadata"]] == [3.0, 1.0]
    assert [record["entity_id"] for record in zone["humidity_sensor_metadata"]] == [
        "sensor.living_room_humidity"
    ]


async def test_sensor_policy_errors_point_at_the_fixable_form(hass) -> None:
    """A designated reference needs exactly one sensor, and a sensor appears once."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(
        hass,
        entry,
        {
            **LIVING_INPUT,
            "temperature_sensors": [LIVING.temperature_sensor, "sensor.living_room_temperature_2"],
        },
    )
    zone_id = _zone_id(entry, "Living room")
    data = dict(entry.data)

    result = await _menu(hass, entry, zone_id, "sensors")
    result = await _configure(
        hass, result, {**frontend_submission(result), "configure_sensor_metadata": True}
    )
    result = await _configure(hass, result, frontend_submission(result))
    result = await _configure(hass, result, frontend_submission(result))
    result = await _configure(hass, result, {"temperature_aggregation": "designated_reference"})
    assert result["step_id"] == "sensor_policy"
    assert result["errors"] == {"base": "designated_reference_count"}

    result = await _menu(hass, entry, zone_id, "sensors")
    result = await _configure(
        hass, result, {**frontend_submission(result), "configure_sensor_metadata": True}
    )
    result = await _configure(hass, result, frontend_submission(result))
    result = await _configure(
        hass,
        result,
        {**frontend_submission(result), "sensor_entity": LIVING.temperature_sensor},
    )
    result = await _configure(hass, result, {"temperature_aggregation": "mean"})
    assert result["step_id"] == "sensor_policy"
    assert result["errors"] == {"base": "invalid_room"}
    assert "duplicate" in result["description_placeholders"]["error"]
    assert dict(entry.data) == data


async def test_loop_edits_keep_valve_identity_by_entity_id(hass) -> None:
    """A retained entity keeps its valve; a new one adds a valve; a dropped one is removed."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(hass, entry, LIVING_INPUT)
    zone_id = _zone_id(entry, "Living room")
    before = _ids(entry, zone_id)
    (loop_id,) = before["circuits"]

    result = await _menu(hass, entry, zone_id, "edit_loop")
    assert result["step_id"] == "edit_loop"
    result = await _configure(hass, result, {"loop": loop_id})
    assert result["step_id"] == "loop"
    assert form_value(result, "valves") == [LIVING.valve_entity]
    assert form_value(result, "name") == "Living room loop"
    assert "shared_valves" not in form_fields(result)
    result = await _configure(
        hass,
        result,
        {
            **frontend_submission(result),
            "valves": [LIVING.valve_entity, "switch.living_room_valve_2"],
            "valve_opening_time_seconds": 45.0,
        },
    )
    assert result["reason"] == "reconfigure_successful"
    after = _ids(entry, zone_id)
    assert after["zone"] == before["zone"]
    assert after["circuits"] == before["circuits"]
    assert after["routes"] == before["routes"]
    assert after["valves"][LIVING.valve_entity] == before["valves"][LIVING.valve_entity]
    draft = room_draft(entry.data, zone_id)
    assert [(valve["name"], valve["opening_time_seconds"]) for valve in draft.valves] == [
        ("Living room loop valve", 45.0),
        ("Living room loop valve 2", 45.0),
    ]
    added_valve_id = after["valves"]["switch.living_room_valve_2"]

    result = await _menu(hass, entry, zone_id, "edit_loop")
    result = await _configure(hass, result, {"loop": loop_id})
    assert form_value(result, "valve_opening_time_seconds") == 45.0
    result = await _configure(
        hass, result, {**frontend_submission(result), "valves": ["switch.living_room_valve_2"]}
    )
    assert result["reason"] == "reconfigure_successful"
    final = _ids(entry, zone_id)
    assert final["valves"] == {"switch.living_room_valve_2": added_valve_id}
    assert final["circuits"] == before["circuits"]
    assert final["routes"] == before["routes"]
    assert entry.data["room_objects"] == {loop_id: zone_id, added_valve_id: zone_id}


async def test_loops_can_be_added_share_room_valves_and_be_removed(hass) -> None:
    """A second private loop may reuse a room valve; removing a loop keeps valves still used."""
    topology = _with_shared_loop({"pumps": [_pump()]})
    entry = await _setup(hass, plant_entry(plant_data(topology)))
    await _add_room(hass, entry, LIVING_INPUT)
    zone_id = _zone_id(entry, "Living room")
    before = _ids(entry, zone_id)

    result = await _menu(hass, entry, zone_id, "add_loop")
    assert result["step_id"] == "loop"
    assert "remove_loop" not in form_fields(result)
    assert form_value(result, "pump") == MANIFOLD_PUMP_ID
    options = form_fields(result)["shared_valves"]["selector"]["select"]["options"]
    assert options == [{"value": SHARED_VALVE_ID, "label": "Shared valve"}]
    result = await _configure(
        hass,
        result,
        {
            "name": "Ceiling loop",
            "valves": [LIVING.valve_entity],
            "shared_valves": [SHARED_VALVE_ID],
            "pump": MANIFOLD_PUMP_ID,
            "valve_opening_time_seconds": 30.0,
        },
    )
    result = await _confirmed(hass, result)
    assert result["reason"] == "reconfigure_successful"
    added = _ids(entry, zone_id)
    assert added["circuits"][0] == before["circuits"][0]
    assert added["routes"][0] == before["routes"][0]
    assert len(added["circuits"]) == len(added["routes"]) == 2
    # The room's valve is shared by its two loops, so it keeps one identity.
    assert added["valves"] == before["valves"]
    ceiling = room_draft(entry.data, zone_id).circuits[1]
    assert ceiling["valve_ids"] == [before["valves"][LIVING.valve_entity], SHARED_VALVE_ID]

    result = await _menu(hass, entry, zone_id, "edit_loop")
    result = await _configure(hass, result, {"loop": before["circuits"][0]})
    assert form_value(result, "remove_loop") is False
    result = await _configure(hass, result, {**frontend_submission(result), "remove_loop": True})
    result = await _confirmed(hass, result)
    assert result["reason"] == "reconfigure_successful"
    remaining = _ids(entry, zone_id)
    assert remaining["circuits"] == [added["circuits"][1]]
    assert remaining["routes"] == [added["routes"][1]]
    assert remaining["valves"] == before["valves"]

    result = await _menu(hass, entry, zone_id, "edit_loop")
    result = await _configure(hass, result, {"loop": added["circuits"][1]})
    result = await _configure(hass, result, {**frontend_submission(result), "remove_loop": True})
    assert result["errors"] == {"base": "delivery_required"}


async def test_loop_form_reports_required_fields(hass) -> None:
    """A loop needs a name, at least one valve, and a pump."""
    entry = await _setup(hass, _pump_only_entry(pumps=2))
    await _add_room(hass, entry, {**LIVING_INPUT, "pump": MANIFOLD_PUMP_ID})
    zone_id = _zone_id(entry, "Living room")

    result = await _menu(hass, entry, zone_id, "add_loop")
    result = await _configure(
        hass,
        result,
        {"name": " ", "valves": [], "valve_opening_time_seconds": 30.0},
    )

    assert result["errors"] == {
        "name": "name_required",
        "valves": "valves_required",
        "pump": "pump_required",
    }


async def test_valve_details_set_feedback_per_private_valve(hass) -> None:
    """Valve feedback is edited once per private valve of the loop, keeping ids."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(hass, entry, LIVING_INPUT)
    zone_id = _zone_id(entry, "Living room")
    before = _ids(entry, zone_id)

    result = await _menu(hass, entry, zone_id, "edit_loop")
    result = await _configure(hass, result, {"loop": before["circuits"][0]})
    result = await _configure(
        hass, result, {**frontend_submission(result), "configure_valve_feedback": True}
    )
    assert result["step_id"] == "valve_details"
    assert result["description_placeholders"] == {
        "valve": "Living room loop valve",
        "entity": LIVING.valve_entity,
    }
    result = await _configure(
        hass,
        result,
        {
            "readiness_entity_id": "binary_sensor.living_room_valve_ready",
            "position_feedback_entity": "sensor.living_room_valve_position",
            "position_feedback_max_age_seconds": 60.0,
        },
    )

    assert result["reason"] == "reconfigure_successful"
    assert _ids(entry, zone_id) == before
    (valve,) = room_draft(entry.data, zone_id).valves
    assert valve["readiness_entity_id"] == "binary_sensor.living_room_valve_ready"
    assert valve["position_feedback_entity"] == "sensor.living_room_valve_position"
    assert valve["position_feedback_max_age_seconds"] == 60.0


# --------------------------------------------------------------------------
# Cooling errors map to the field the user can fix
# --------------------------------------------------------------------------


async def test_loop_cooling_errors_point_at_the_loop_form(hass) -> None:
    """Cooling needs a reference, and humidity in every room the loop serves."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(hass, entry, LIVING_INPUT)
    zone_id = _zone_id(entry, "Living room")
    loop_id = _ids(entry, zone_id)["circuits"][0]

    result = await _menu(hass, entry, zone_id, "edit_loop")
    result = await _configure(hass, result, {"loop": loop_id})
    submission = frontend_submission(result)
    submission["cooling"]["cooling_enabled"] = True
    result = await _configure(hass, result, submission)
    assert result["step_id"] == "loop"
    assert result["errors"] == {"base": "cooling_reference_required"}

    submission["cooling"]["supply_temperature_sensor"] = "sensor.living_room_supply"
    result = await _configure(hass, result, submission)
    assert result["errors"] == {"base": "cooling_requires_zone_observations"}


async def _cooling_room(hass) -> tuple[MockConfigEntry, str]:
    """Return a Plant whose external-thermostat room has a cooling loop."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(
        hass,
        entry,
        {
            **LIVING_INPUT,
            "external_climate_entity": "climate.living_room_thermostat",
        },
    )
    zone_id = _zone_id(entry, "Living room")
    result = await _menu(hass, entry, zone_id, "sensors")
    result = await _configure(
        hass,
        result,
        {**frontend_submission(result), "humidity_sensors": ["sensor.living_room_humidity"]},
    )
    assert result["reason"] == "reconfigure_successful"
    result = await _menu(hass, entry, zone_id, "edit_loop")
    result = await _configure(hass, result, {"loop": _ids(entry, zone_id)["circuits"][0]})
    submission = frontend_submission(result)
    submission["cooling"].update(
        {"cooling_enabled": True, "supply_temperature_sensor": "sensor.living_room_supply"}
    )
    result = await _configure(hass, result, submission)
    assert result["reason"] == "reconfigure_successful"
    return entry, zone_id


async def test_room_cooling_errors_point_at_the_sensor_fields(hass) -> None:
    """A cooling room keeps a temperature and a humidity sensor, even with its own thermostat."""
    entry, zone_id = await _cooling_room(hass)
    data = dict(entry.data)

    result = await _menu(hass, entry, zone_id, "room")
    result = await _configure(
        hass, result, {**frontend_submission(result), "temperature_sensors": []}
    )
    assert result["errors"] == {"temperature_sensors": "temperature_required_for_cooling"}

    result = await _menu(hass, entry, zone_id, "sensors")
    result = await _configure(hass, result, {**frontend_submission(result), "humidity_sensors": []})
    assert result["errors"] == {"humidity_sensors": "humidity_required_for_cooling"}
    assert dict(entry.data) == data


# --------------------------------------------------------------------------
# Stored Hydronicus entities are rejected on submit
# --------------------------------------------------------------------------


async def test_stored_hydronicus_entities_are_rejected_on_submit(hass) -> None:
    """A stored binding stays visible in its picker, so the backend rejects it on submit."""
    _set_states(hass)
    own_valve = _own_entity(hass, "switch", "own_valve")
    own_sensor = _own_entity(hass, "sensor", "own_temperature")
    own_climate = _own_entity(hass, "climate", "own_thermostat")
    own_ready = _own_entity(hass, "binary_sensor", "own_ready")
    topology = {
        "pumps": [_pump()],
        "zones": [
            {
                "id": LIVING.zone_id,
                "name": "Living room",
                "thermostat": {"kind": "hydronicus", "initial_target_temperature": 21.0},
                "temperature_sensor_metadata": [{"entity_id": own_sensor}],
            },
            {
                "id": BEDROOM.zone_id,
                "name": "Bedroom",
                "thermostat": {"kind": "external_climate", "entity_id": own_climate},
                "temperature_sensor_metadata": [],
            },
        ],
        "valves": [
            {
                "id": LIVING.valve_id,
                "name": "Living room loop valve",
                "entity_id": LIVING.valve_entity,
                "readiness_entity_id": own_ready,
            },
            {"id": BEDROOM.valve_id, "name": "Bedroom loop valve", "entity_id": own_valve},
        ],
        "circuits": [
            {
                "id": LIVING.circuit_id,
                "name": "Living room loop",
                "valve_ids": [LIVING.valve_id],
                "pump_id": MANIFOLD_PUMP_ID,
                "supply_temperature_sensor": own_sensor,
            },
            {
                "id": BEDROOM.circuit_id,
                "name": "Bedroom loop",
                "valve_ids": [BEDROOM.valve_id],
                "pump_id": MANIFOLD_PUMP_ID,
            },
        ],
        "routes": [
            {"id": LIVING.route_id, "zone_id": LIVING.zone_id, "circuit_id": LIVING.circuit_id},
            {"id": BEDROOM.route_id, "zone_id": BEDROOM.zone_id, "circuit_id": BEDROOM.circuit_id},
        ],
    }
    entry = plant_entry(plant_data(topology))
    entry.add_to_hass(hass)
    data = dict(entry.data)

    result = await _menu(hass, entry, LIVING.zone_id, "room")
    result = await _configure(hass, result, frontend_submission(result))
    assert result["errors"] == {"temperature_sensors": "own_entity"}

    result = await _menu(hass, entry, BEDROOM.zone_id, "room")
    result = await _configure(hass, result, frontend_submission(result))
    assert result["errors"] == {"base": "thermostat_loop"}

    result = await _menu(hass, entry, BEDROOM.zone_id, "edit_loop")
    result = await _configure(hass, result, {"loop": BEDROOM.circuit_id})
    result = await _configure(hass, result, frontend_submission(result))
    assert result["errors"] == {"valves": "own_entity"}

    result = await _menu(hass, entry, LIVING.zone_id, "edit_loop")
    result = await _configure(hass, result, {"loop": LIVING.circuit_id})
    submission = frontend_submission(result)
    result = await _configure(hass, result, submission)
    # A field inside a collapsed section is reported on the form.
    assert result["errors"] == {"base": "own_entity"}
    submission["cooling"].pop("supply_temperature_sensor")
    result = await _configure(hass, result, {**submission, "configure_valve_feedback": True})
    assert result["step_id"] == "valve_details"
    result = await _configure(hass, result, frontend_submission(result))
    assert result["step_id"] == "valve_details"
    assert result["errors"] == {"readiness_entity_id": "own_entity"}
    assert dict(entry.data) == data


# --------------------------------------------------------------------------
# Repairs hand off to the room's reconfigure flow
# --------------------------------------------------------------------------


async def test_a_binding_repair_is_fixed_through_the_room_flow(hass) -> None:
    """A repair opens the room's reconfigure flow, whose loop step replaces the valve."""
    entry = manifold_entry(("Living room",))
    entry.add_to_hass(hass)
    hass.states.async_set(LIVING.temperature_sensor, "20.0")
    hass.states.async_set(MANIFOLD_PUMP_ENTITY, "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert [
        issue for (domain, _), issue in ir.async_get(hass).issues.items() if domain == DOMAIN
    ], "the valve entity is missing, so its binding is unresolved"

    # This is the hand-off the fix flow makes.
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_ROOM),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": room_subentry(entry, LIVING.zone_id).subentry_id,
        },
    )
    assert result["type"] == FlowResultType.MENU
    result = await _configure(hass, result, {"next_step_id": "edit_loop"})
    result = await _configure(hass, result, {"loop": LIVING.circuit_id})
    hass.states.async_set("switch.living_room_valve_2", "off")
    result = await _configure(
        hass, result, {**frontend_submission(result), "valves": ["switch.living_room_valve_2"]}
    )

    assert result["reason"] == "reconfigure_successful"
    plant = entry.runtime_data.plant
    (valve,) = plant.valves.values()
    assert valve.entity_id == "switch.living_room_valve_2"
    assert [
        issue for (domain, _), issue in ir.async_get(hass).issues.items() if domain == DOMAIN
    ] == []


async def test_only_warnings_a_change_introduces_are_reviewed(hass) -> None:
    """A warning the Plant already had does not ask for confirmation again."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(hass, entry, LIVING_INPUT)
    result = await _configure(hass, await _start_room(hass, entry), BEDROOM_INPUT)
    assert result["step_id"] == "review"
    result = await _configure(hass, result, {"confirm": True})
    assert "shared_pump_limits_independent_control" in _warning_codes(entry)
    zone_id = _zone_id(entry, "Bedroom")

    result = await _menu(hass, entry, zone_id, "room")
    result = await _configure(hass, result, {**frontend_submission(result), "name": "Guest room"})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert room_subentry(entry, zone_id).title == "Guest room"


# --------------------------------------------------------------------------
# Edits that meet a graph another flow changed
# --------------------------------------------------------------------------

KITCHEN_INPUT = {
    "name": "Kitchen",
    "temperature_sensors": ["sensor.kitchen_temperature"],
    "valves": ["switch.kitchen_valve"],
}


async def _live_heating_manifold(hass, gate: asyncio.Event) -> MockConfigEntry:
    """Return a live manifold heating Bedroom, whose switches answer once ``gate`` opens."""

    async def slow_switch(call) -> None:
        await gate.wait()
        hass.states.async_set(call.data["entity_id"], "on" if call.service == "turn_on" else "off")

    hass.services.async_register("switch", "turn_on", slow_switch)
    hass.services.async_register("switch", "turn_off", slow_switch)
    hass.states.async_set("sensor.kitchen_temperature", "18.0")
    hass.states.async_set("switch.kitchen_valve", "off")
    entry = await _setup(hass, manifold_entry())
    hass.states.async_set(BEDROOM.temperature_sensor, "18.0")
    runtime = entry.runtime_data
    gate.set()
    assert await runtime.async_set_dry_run(
        False, hass=hass, authorization=output_authorization(entry.data)
    )
    await runtime.async_set_zone_hvac_mode(BEDROOM.zone_id, ThermostatHvacMode.HEAT, hass=hass)
    await hass.async_block_till_done()
    assert runtime.active_equipment_ids()
    gate.clear()
    return entry


async def test_concurrent_edits_of_a_live_plant_keep_each_others_changes(hass) -> None:
    """Two saves that both wait for the safe shutdown each apply to the graph the other stored."""
    gate = asyncio.Event()
    entry = await _live_heating_manifold(hass, gate)
    room = await _start_room(hass, entry)
    # The room save waits in the slow safe shutdown.
    room_task = hass.async_create_task(
        hass.config_entries.subentries.async_configure(room["flow_id"], KITCHEN_INPUT)
    )
    pump = await entry.start_reconfigure_flow(hass)
    pump = await hass.config_entries.flow.async_configure(
        pump["flow_id"], {"next_step_id": "edit_pump"}
    )
    pump = await hass.config_entries.flow.async_configure(
        pump["flow_id"], {"pump": MANIFOLD_PUMP_ID}
    )
    assert pump["step_id"] == "pump"
    # The pump save waits for the runtime lock the shutdown holds.
    pump_task = hass.async_create_task(
        hass.config_entries.flow.async_configure(
            pump["flow_id"],
            {"name": "Renamed pump", "entity_id": MANIFOLD_PUMP_ENTITY, "overrun_seconds": 0.0},
        )
    )
    for _ in range(5):
        await asyncio.sleep(0)
    gate.set()
    room_result = await room_task
    pump_result = await pump_task
    await hass.async_block_till_done()

    assert room_result["type"] == FlowResultType.CREATE_ENTRY
    assert pump_result["reason"] == "reconfigure_successful"
    topology = entry.data["topology"]
    assert [zone["name"] for zone in topology["zones"]] == ["Living room", "Bedroom", "Kitchen"]
    assert [pump["name"] for pump in topology["pumps"]] == ["Renamed pump"]
    kitchen = room_subentry(entry, _zone_id(entry, "Kitchen"))
    assert effective_plant(entry).object_subentry_ids[kitchen.unique_id] == kitchen.subentry_id
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.dry_run is True
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_a_review_confirmed_after_the_graph_changed_shows_the_conflict(hass) -> None:
    """A room whose valve another room took meanwhile returns to its form with the error."""
    hass.states.async_set("sensor.kitchen_temperature", "18.0")
    hass.states.async_set("switch.kitchen_valve", "off")
    entry = await _setup(hass, manifold_entry(("Living room",)))
    flows = []
    for name in ("Kitchen", "Pantry"):
        result = await _start_room(hass, entry)
        result = await _configure(hass, result, {**KITCHEN_INPUT, "name": name})
        # The second room on the pump is a new shared pump warning in both flows.
        assert result["step_id"] == "review"
        flows.append(result)
    first = await _configure(hass, flows[0], {"confirm": True})
    assert first["type"] == FlowResultType.CREATE_ENTRY
    data = dict(entry.data)

    second = await _configure(hass, flows[1], {"confirm": True})

    assert second["type"] == FlowResultType.FORM
    assert second["step_id"] == "user"
    assert second["errors"] == {"valves": "actuator_entity_in_use"}
    assert form_value(second, "name") == "Pantry"
    assert dict(entry.data) == data
    assert [subentry.title for subentry in entry.subentries.values()] == [
        "Living room",
        "Kitchen",
    ]


async def test_editing_a_room_that_was_deleted_meanwhile_aborts(hass) -> None:
    """A room removed while its reconfigure flow is open ends that flow instead of raising."""
    entry = await _setup(hass, manifold_entry())
    menu = await _menu(hass, entry, BEDROOM.zone_id)
    form = await _menu(hass, entry, BEDROOM.zone_id, "room")
    assert hass.config_entries.async_remove_subentry(
        entry, room_subentry(entry, BEDROOM.zone_id).subentry_id
    )
    await hass.async_block_till_done()

    chosen = await _configure(hass, menu, {"next_step_id": "thermostat"})
    saved = await _configure(hass, form, {**frontend_submission(form), "name": "Guest room"})

    for result in (chosen, saved):
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "subentry_removed"
    assert [zone["name"] for zone in entry.data["topology"]["zones"]] == ["Living room"]
    assert entry.state is ConfigEntryState.LOADED


async def test_valve_details_keep_room_edits_made_meanwhile(hass) -> None:
    """A loop saved after its valve feedback steps applies to the room as it is now."""
    entry = await _setup(hass, _pump_only_entry())
    await _add_room(hass, entry, LIVING_INPUT)
    zone_id = _zone_id(entry, "Living room")
    circuit_id = _ids(entry, zone_id)["circuits"][0]
    loop = await _menu(hass, entry, zone_id, "edit_loop")
    loop = await _configure(hass, loop, {"loop": circuit_id})
    details = await _configure(
        hass, loop, {**frontend_submission(loop), "configure_valve_feedback": True}
    )
    assert details["step_id"] == "valve_details"
    rename = await _menu(hass, entry, zone_id, "room")
    rename = await _configure(hass, rename, {**frontend_submission(rename), "name": "Lounge"})
    assert rename["reason"] == "reconfigure_successful"

    result = await _configure(
        hass,
        details,
        {
            "readiness_entity_id": "binary_sensor.living_room_valve_ready",
            "position_feedback_max_age_seconds": 60.0,
        },
    )

    assert result["reason"] == "reconfigure_successful"
    draft = room_draft(entry.data, zone_id)
    assert draft.zone["name"] == "Lounge"
    assert room_subentry(entry, zone_id).title == "Lounge"
    (valve,) = draft.valves
    assert valve["readiness_entity_id"] == "binary_sensor.living_room_valve_ready"
