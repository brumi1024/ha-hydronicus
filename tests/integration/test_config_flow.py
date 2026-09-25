"""Tests for creating a Plant: guided setup, plant file import, and the Plant settings entry."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import voluptuous as vol
import yaml
from homeassistant.config_entries import ConfigEntry
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.config_flow import HydronicClimateConfigFlow
from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_DRY_RUN_CONFIRMATION,
    CONF_NAME,
    CONF_PLANT_ID,
    DEFAULT_CONDENSATION_MARGIN,
    DOMAIN,
)
from custom_components.hydronicus.flows.plant import PlantSettingsOptionsFlow
from custom_components.hydronicus.plant_file import plant_file
from tests.core.test_plant_document import NEGATIVE_FIXTURES
from tests.integration.flow_forms import form_fields, form_value

FIXTURES = Path(__file__).parents[1] / "fixtures" / "plant_files"
VALID_FIXTURES = sorted(path.name for path in FIXTURES.glob("*.yaml"))
FILE_PLANT_ID = "00000000-0000-4000-8000-0000000000f1"
PUMP = "switch.manifold_pump"
ROOMS = (
    ("Living room", "sensor.living_temperature", "switch.living_valve"),
    ("Bedroom", "sensor.bedroom_temperature", "switch.bedroom_valve"),
    ("Office", "sensor.office_temperature", "switch.office_valve"),
)


def _fixture(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _own_entity(hass, domain: str, object_id: str) -> str:
    """Register an entity that Hydronicus provides, which no form may bind."""
    registry_entry = er.async_get(hass).async_get_or_create(
        domain, DOMAIN, f"own-{object_id}", suggested_object_id=object_id
    )
    hass.states.async_set(registry_entry.entity_id, "20.0")
    return registry_entry.entity_id


def _room(name: str, sensor: str, valve: str, *, add_another: bool = False) -> dict[str, Any]:
    return {
        CONF_NAME: name,
        "temperature_sensors": [sensor],
        "valves": [valve],
        "add_another": add_another,
    }


async def _submit(hass, result: Mapping[str, Any], user_input: Mapping[str, Any]):
    return await hass.config_entries.flow.async_configure(result["flow_id"], dict(user_input))


async def _start(hass, option: str):
    """Open the setup menu and choose one way to create a Plant."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    return await _submit(hass, result, {"next_step_id": option})


async def _first_room(hass, *, name: str = "Hydronic plant", pump: str = PUMP):
    """Advance guided setup to its first room form."""
    result = await _start(hass, "guided")
    result = await _submit(hass, result, {CONF_NAME: name, "pump_entity": pump})
    assert result["step_id"] == "room", result.get("errors")
    return result


async def _import(hass, document: Any):
    """Submit a plant file to the import form."""
    result = await _start(hass, "import_plant")
    assert result["step_id"] == "import_plant"
    return await _submit(hass, result, {"document": document})


async def _create_by_import(hass, document: Any) -> ConfigEntry:
    """Import a plant file, confirming any warnings, and return the loaded entry."""
    result = await _import(hass, document)
    assert result["step_id"] == "import_review", result.get("description_placeholders")
    user_input = {"confirm": True} if "confirm" in form_fields(result) else {}
    result = await _submit(hass, result, user_input)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return result["result"]


def _unordered(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return Plant data with its topology collections sorted by id.

    A plant file lists objects by slug, so an export can reorder stored records.
    """
    result = deepcopy(dict(data))
    topology = result["topology"]
    for collection, records in topology.items():
        if isinstance(records, list):
            topology[collection] = sorted(records, key=lambda record: str(record["id"]))
    return result


def _handles(entry: ConfigEntry) -> list[tuple[str, str, str, dict[str, Any]]]:
    return sorted(
        (subentry.subentry_type, str(subentry.unique_id), subentry.title, dict(subentry.data))
        for subentry in entry.subentries.values()
    )


# --------------------------------------------------------------------------
# The setup menu
# --------------------------------------------------------------------------


async def test_setup_starts_with_a_menu_of_guided_setup_and_import(hass) -> None:
    """A new Plant is either set up step by step or imported from a plant file."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "user"
    assert list(result["menu_options"]) == ["guided", "import_plant"]


# --------------------------------------------------------------------------
# Guided setup
# --------------------------------------------------------------------------


async def test_guided_setup_creates_a_three_room_manifold_in_six_screens(hass) -> None:
    """Menu, Plant form, one form per room, and the review: six screens in total."""
    screens = []

    async def show(result):
        if result["type"] in (FlowResultType.FORM, FlowResultType.MENU):
            screens.append(result["step_id"])
        return result

    result = await show(
        await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    )
    result = await show(await _submit(hass, result, {"next_step_id": "guided"}))
    result = await show(
        await _submit(
            hass,
            result,
            {CONF_NAME: "Manifold", "pump_entity": PUMP, "pump_options": {"overrun_seconds": 90}},
        )
    )
    for index, (name, sensor, valve) in enumerate(ROOMS):
        result = await show(
            await _submit(
                hass, result, _room(name, sensor, valve, add_another=index < len(ROOMS) - 1)
            )
        )
    assert result["step_id"] == "review"
    placeholders = result["description_placeholders"]
    assert placeholders["rooms"] == "- Living room\n- Bedroom\n- Office"
    assert "Bedroom is heated by Bedroom loop." in placeholders["logic"]
    # Three rooms on one pump carry the shared pump warning, which needs confirming.
    assert "shared by loops" in placeholders["warnings"]
    result = await _submit(hass, result, {"confirm": True})
    await hass.async_block_till_done()

    assert screens == ["user", "guided", "room", "room", "room", "review"]
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry: ConfigEntry = result["result"]
    assert (entry.version, entry.minor_version) == (3, 0)
    assert entry.title == "Manifold"
    data = entry.data
    assert data[CONF_DRY_RUN] is True
    assert "output_authorization" not in data
    assert entry.unique_id == data[CONF_PLANT_ID]
    topology = data["topology"]
    (pump,) = topology["pumps"]
    assert pump == {
        "id": pump["id"],
        CONF_NAME: "Circulation pump",
        "entity_id": PUMP,
        "overrun_seconds": 90.0,
    }
    zones = {zone["id"]: zone for zone in topology["zones"]}
    circuits = {circuit["id"]: circuit for circuit in topology["circuits"]}
    valves = {valve["id"]: valve for valve in topology["valves"]}
    assert [zone[CONF_NAME] for zone in topology["zones"]] == [name for name, _, _ in ROOMS]
    assert len(topology["routes"]) == 3
    for route in topology["routes"]:
        zone = zones[route["zone_id"]]
        circuit = circuits[route["circuit_id"]]
        (valve_id,) = circuit["valve_ids"]
        name, sensor, valve = next(room for room in ROOMS if room[0] == zone[CONF_NAME])
        assert circuit[CONF_NAME] == f"{name} loop"
        assert circuit["pump_id"] == pump["id"]
        assert valves[valve_id]["entity_id"] == valve
        assert valves[valve_id][CONF_NAME] == f"{name} loop valve"
        assert zone["temperature_sensor_metadata"][0]["entity_id"] == sensor
        # The room owns its loop and valve; the pump belongs to the Plant.
        assert data["room_objects"][circuit["id"]] == zone["id"]
        assert data["room_objects"][valve_id] == zone["id"]
    assert data["subentry_objects"] == dict.fromkeys(zones, "room")
    assert _handles(entry) == sorted(
        ("room", zone_id, zone[CONF_NAME], {"id": zone_id}) for zone_id, zone in zones.items()
    )
    runtime = entry.runtime_data
    assert runtime.dry_run is True
    assert runtime.subentry_id_for(pump["id"]) is None
    assert hass.states.get("climate.manifold_bedroom") is not None


async def test_guided_setup_without_warnings_needs_no_confirmation(hass) -> None:
    """One room on its own pump has nothing to confirm, and the pump overrun has a default."""
    result = await _first_room(hass)
    assert "overrun_seconds" not in form_fields(result)
    result = await _submit(hass, result, _room("Study", "sensor.study", "switch.study_valve"))

    assert result["step_id"] == "review"
    assert result["description_placeholders"]["warnings"] == "- None"
    assert form_fields(result) == {}
    result = await _submit(hass, result, {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["topology"]["pumps"][0]["overrun_seconds"] == 120.0


async def test_guided_forms_ask_only_for_what_setup_needs(hass) -> None:
    """The Plant form collapses the pump overrun; room forms have no pump or shared loops."""
    result = await _start(hass, "guided")
    fields = form_fields(result)
    assert set(fields) == {CONF_NAME, "pump_entity", "pump_options", "pump_options.overrun_seconds"}
    assert "text" in fields[CONF_NAME]["selector"]
    assert fields["pump_entity"]["selector"]["entity"]["domain"] == ["switch"]
    assert fields["pump_options"]["expanded"] is False
    assert fields["pump_options.overrun_seconds"]["selector"]["number"]["unit_of_measurement"] == (
        "s"
    )
    assert "dry_run" not in fields

    result = await _submit(hass, result, {CONF_NAME: "Hydronic plant", "pump_entity": PUMP})
    fields = form_fields(result)
    assert set(fields) == {
        CONF_NAME,
        "temperature_sensors",
        "external_climate_entity",
        "valves",
        "cooling",
        "cooling.cooling_enabled",
        "cooling.humidity_sensors",
        "cooling.supply_temperature_sensor",
        "cooling.surface_temperature_sensor",
        "cooling.condensation_margin",
        "add_another",
    }
    assert fields["temperature_sensors"]["selector"]["entity"]["device_class"] == ["temperature"]
    assert fields["valves"]["selector"]["entity"]["domain"] == ["switch", "valve"]
    assert form_value(result, "add_another") is False
    # Cooling is optional and collapsed, and starts off.
    assert fields["cooling"]["expanded"] is False
    assert form_value(result, "cooling.cooling_enabled") is False
    assert fields["cooling.humidity_sensors"]["selector"]["entity"]["device_class"] == ["humidity"]
    assert fields["cooling.humidity_sensors"]["selector"]["entity"]["multiple"] is True
    # The margin has the default and bounds of the loop form's Cooling section.
    margin = fields["cooling.condensation_margin"]
    assert margin["default"] == DEFAULT_CONDENSATION_MARGIN
    assert margin["selector"]["number"]["min"] == 0
    assert margin["selector"]["number"]["unit_of_measurement"] == "°C"


async def test_guided_room_form_lists_rooms_only_once_one_exists(hass) -> None:
    """The first room form lists no rooms; later ones list the rooms added so far."""
    result = await _first_room(hass)
    assert result["description_placeholders"]["rooms"] == ""

    name, sensor, valve = ROOMS[0]
    result = await _submit(hass, result, _room(name, sensor, valve, add_another=True))

    assert result["step_id"] == "room"
    assert result["description_placeholders"]["rooms"] == ("\n\nRooms added so far:\n- Living room")


COOLING_ROOM = {
    CONF_NAME: "Living room",
    "temperature_sensors": ["sensor.living_temperature"],
    "valves": ["switch.living_valve"],
    "cooling": {
        "cooling_enabled": True,
        "humidity_sensors": ["sensor.living_humidity"],
        "surface_temperature_sensor": "sensor.living_floor_temperature",
        "condensation_margin": 3.0,
    },
}


async def test_guided_setup_creates_a_cooling_room(hass) -> None:
    """The room form's Cooling section cools the private loop and stores the humidity sensors."""
    result = await _first_room(hass)
    result = await _submit(hass, result, COOLING_ROOM)

    assert result["step_id"] == "review"
    assert (
        "Living room is heated and cooled by Living room loop."
        in (result["description_placeholders"]["logic"])
    )
    result = await _submit(hass, result, {"confirm": True} if form_fields(result) else {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    topology = result["result"].data["topology"]
    (zone,) = topology["zones"]
    (circuit,) = topology["circuits"]
    assert [sensor["entity_id"] for sensor in zone["humidity_sensor_metadata"]] == [
        "sensor.living_humidity"
    ]
    assert circuit["cooling_enabled"] is True
    assert circuit["surface_temperature_sensor"] == "sensor.living_floor_temperature"
    assert circuit["supply_temperature_sensor"] is None
    assert circuit["condensation_margin"] == 3.0


async def test_guided_room_without_cooling_keeps_a_heating_only_loop(hass) -> None:
    """Leaving the section closed stores the loop with cooling off and the default margin."""
    result = await _first_room(hass)
    name, sensor, valve = ROOMS[0]
    result = await _submit(hass, result, _room(name, sensor, valve))
    result = await _submit(hass, result, {"confirm": True} if form_fields(result) else {})

    topology = result["result"].data["topology"]
    (zone,) = topology["zones"]
    (circuit,) = topology["circuits"]
    assert zone["humidity_sensor_metadata"] == []
    assert circuit["cooling_enabled"] is False
    assert circuit["condensation_margin"] == DEFAULT_CONDENSATION_MARGIN


@pytest.mark.parametrize(
    ("change", "errors"),
    [
        pytest.param(
            {"cooling": {"cooling_enabled": True, "humidity_sensors": ["sensor.h"]}},
            {"base": "cooling_reference_required"},
            id="no condensation reference",
        ),
        pytest.param(
            {"cooling": {"cooling_enabled": True, "supply_temperature_sensor": "sensor.supply"}},
            {"base": "humidity_required_for_cooling"},
            id="no humidity sensors",
        ),
        pytest.param(
            {"temperature_sensors": [], "external_climate_entity": "climate.living"},
            {"temperature_sensors": "temperature_required_for_cooling"},
            id="no temperature sensors",
        ),
    ],
)
async def test_guided_cooling_room_is_validated(hass, change, errors) -> None:
    """A cooling room needs a condensation reference, humidity, and temperature sensors."""
    result = await _first_room(hass)
    result = await _submit(hass, result, {**COOLING_ROOM, **change})

    assert result["step_id"] == "room"
    assert result["errors"] == errors
    # The rejected form keeps what the user entered in the section.
    assert form_value(result, "cooling.cooling_enabled") is True


async def test_guided_plant_form_rejects_a_blank_name_and_keeps_the_input(hass) -> None:
    """A rejected Plant form is shown again with the submitted values."""
    result = await _start(hass, "guided")
    result = await _submit(hass, result, {CONF_NAME: "  ", "pump_entity": PUMP})

    assert result["step_id"] == "guided"
    assert result["errors"] == {CONF_NAME: "name_required"}
    assert form_value(result, "pump_entity") == PUMP


async def test_guided_plant_form_rejects_a_hydronicus_pump(hass) -> None:
    """A Hydronicus entity would feed the Plant back into itself."""
    result = await _start(hass, "guided")
    # The picker hides Hydronicus entities, so this one appears after the form is shown.
    own_switch = _own_entity(hass, "switch", "own_pump")
    result = await _submit(hass, result, {CONF_NAME: "Plant", "pump_entity": own_switch})

    assert result["step_id"] == "guided"
    assert result["errors"] == {"pump_entity": "own_entity"}


async def test_room_rejects_an_empty_temperature_sensor_selection(hass) -> None:
    """An empty list, as a lazily loaded picker can submit, stays on the room form."""
    result = await _first_room(hass)
    room = {**_room("Study", "sensor.study", "switch.study_valve"), "temperature_sensors": []}
    result = await _submit(hass, result, room)

    assert result["step_id"] == "room"
    assert result["errors"] == {"temperature_sensors": "temperature_sensors_required"}
    assert form_value(result, CONF_NAME) == "Study"
    assert form_value(result, "valves") == ["switch.study_valve"]

    result = await _submit(hass, result, _room("Study", "sensor.study", "switch.study_valve"))
    assert result["step_id"] == "review"


async def test_room_with_an_external_thermostat_needs_no_sensors(hass) -> None:
    """An existing climate entity supplies the temperature, so sensors stay optional."""
    result = await _first_room(hass)
    result = await _submit(
        hass,
        result,
        {
            CONF_NAME: "Office",
            "temperature_sensors": [],
            "external_climate_entity": "climate.office",
            "valves": ["switch.office_valve"],
        },
    )
    assert result["step_id"] == "review"
    result = await _submit(hass, result, {})

    (zone,) = result["data"]["topology"]["zones"]
    assert zone["thermostat"] == {"kind": "external_climate", "entity_id": "climate.office"}


async def test_room_rejects_blank_names_and_missing_valves(hass) -> None:
    """A room needs a name and at least one valve."""
    result = await _first_room(hass)
    result = await _submit(
        hass, result, {CONF_NAME: " ", "temperature_sensors": ["sensor.study"], "valves": []}
    )

    assert result["step_id"] == "room"
    assert result["errors"] == {CONF_NAME: "name_required", "base": "delivery_required"}


async def test_room_rejects_hydronicus_entities(hass) -> None:
    """Sensors and valves of this integration are refused, and so is its own thermostat."""
    result = await _first_room(hass)
    thermostat = await _first_room(hass, name="Second plant")
    # The pickers hide Hydronicus entities, so these appear after the forms are shown.
    own_sensor = _own_entity(hass, "sensor", "own_temperature")
    own_valve = _own_entity(hass, "switch", "own_valve")
    own_climate = _own_entity(hass, "climate", "own_thermostat")

    result = await _submit(hass, result, _room("Study", own_sensor, own_valve))
    assert result["errors"] == {"temperature_sensors": "own_entity", "valves": "own_entity"}

    result = await _submit(
        hass,
        thermostat,
        {
            CONF_NAME: "Study",
            "external_climate_entity": own_climate,
            "valves": ["switch.study_valve"],
        },
    )
    assert result["errors"] == {"base": "thermostat_loop"}


async def test_room_rejects_the_pump_entity_as_a_valve(hass) -> None:
    """One entity controls one valve or pump; the room form points at its valves."""
    result = await _first_room(hass)
    result = await _submit(hass, result, _room("Study", "sensor.study", PUMP))

    assert result["step_id"] == "room"
    assert result["errors"] == {"valves": "actuator_entity_in_use"}
    assert form_value(result, "valves") == [PUMP]


async def test_room_rejects_a_valve_another_room_already_uses(hass) -> None:
    """A valve entity of an earlier room is refused on the later room's form."""
    result = await _first_room(hass)
    result = await _submit(
        hass, result, _room("Study", "sensor.study", "switch.valve", add_another=True)
    )
    assert result["step_id"] == "room"
    assert not result.get("errors")

    result = await _submit(hass, result, _room("Hall", "sensor.hall", "switch.valve"))
    assert result["step_id"] == "room"
    assert result["errors"] == {"valves": "actuator_entity_in_use"}


async def test_review_requires_confirming_a_pump_another_plant_binds(hass) -> None:
    """Sharing an output with another Plant is a blocking warning."""
    await _create_by_import(hass, _fixture("manifold.yaml"))

    result = await _first_room(hass, name="Second plant")
    result = await _submit(hass, result, _room("Study", "sensor.study", "switch.study_valve"))

    assert result["step_id"] == "review"
    warnings = result["description_placeholders"]["warnings"]
    assert PUMP in warnings
    assert "Manifold" in warnings
    assert "switch.study_valve" not in warnings
    result = await _submit(hass, result, {"confirm": False})
    assert result["errors"] == {"base": "confirm_required"}
    result = await _submit(hass, result, {"confirm": True})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DRY_RUN] is True


# --------------------------------------------------------------------------
# Plant file import
# --------------------------------------------------------------------------


async def test_import_creates_the_plant_with_room_and_source_subentries(hass) -> None:
    """An imported Plant has a room handle per room and a source handle per source."""
    document = {**_fixture("sources.yaml"), "id": FILE_PLANT_ID}
    result = await _import(hass, document)

    assert result["step_id"] == "import_review"
    placeholders = result["description_placeholders"]
    assert placeholders["name"] == "Sources"
    assert placeholders["rooms"] == "- Living room"
    assert "Living room is heated by Living loop." in placeholders["logic"]
    result = await _submit(
        hass, result, {"confirm": True} if "confirm" in form_fields(result) else {}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry: ConfigEntry = result["result"]
    assert entry.title == "Sources"
    assert entry.unique_id == FILE_PLANT_ID
    assert entry.data[CONF_PLANT_ID] == FILE_PLANT_ID
    assert entry.data[CONF_DRY_RUN] is True
    assert "output_authorization" not in entry.data
    handles = _handles(entry)
    assert [(kind, title) for kind, _, title, _ in handles] == [
        ("room", "Living room"),
        ("source", "Buffer"),
        ("source", "Heat pump"),
    ]
    assert entry.runtime_data.dry_run is True


@pytest.mark.parametrize("fixture", VALID_FIXTURES)
async def test_import_equals_importing_its_own_export(hass, fixture: str) -> None:
    """A plant file and its export create the same data and the same subentries."""
    first = await _create_by_import(hass, _fixture(fixture))
    data, handles = deepcopy(dict(first.data)), _handles(first)
    export = plant_file(first.data)
    assert await hass.config_entries.async_remove(first.entry_id)

    second = await _create_by_import(hass, export)

    assert _unordered(second.data) == _unordered(data)
    assert _handles(second) == handles
    assert second.unique_id == data[CONF_PLANT_ID]


async def test_import_accepts_yaml_text(hass) -> None:
    """The object selector may submit the plant file as YAML text."""
    text = (FIXTURES / "single_room.yaml").read_text(encoding="utf-8")
    result = await _import(hass, text)

    assert result["step_id"] == "import_review"


EMPTY_DOCUMENT_ERROR = (
    "The plant file is empty or not valid YAML. The editor marks the line with the problem."
)


async def test_import_editor_starts_empty(hass) -> None:
    """The plant file editor has no default, so it opens empty rather than with ``''``."""
    result = await _start(hass, "import_plant")

    (key,) = result["data_schema"].schema
    assert isinstance(key, vol.Optional)
    assert key.default is vol.UNDEFINED
    assert form_value(result, "document") is None


@pytest.mark.parametrize(
    "user_input",
    [{}, {"document": ""}, {"document": None}, {"document": "  \n"}],
    ids=["missing", "empty_text", "none", "blank_text"],
)
async def test_import_without_a_document_explains_the_editor(hass, user_input) -> None:
    """A missing or unparseable document reaches the flow, which explains it at the top."""
    result = await _start(hass, "import_plant")
    result = await _submit(hass, result, user_input)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "import_plant"
    assert result["errors"] == {"base": "invalid_document"}
    assert result["description_placeholders"] == {
        "path": "the top level",
        "error": EMPTY_DOCUMENT_ERROR,
    }


async def test_import_of_a_configured_plant_aborts(hass) -> None:
    """A plant file whose id matches an existing Plant cannot be imported again."""
    document = {**_fixture("manifold.yaml"), "id": FILE_PLANT_ID}
    await _create_by_import(hass, document)

    result = await _import(hass, document)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.parametrize(("fixture", "path"), sorted(NEGATIVE_FIXTURES.items()))
async def test_invalid_plant_file_shows_its_path(hass, fixture: str, path: str) -> None:
    """Every rejected plant file names the key to fix, and the form keeps the file."""
    document = _fixture(f"invalid/{fixture}")
    result = await _import(hass, document)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "import_plant"
    assert result["errors"] == {"base": "invalid_document"}
    assert result["description_placeholders"]["path"] == (path or "the top level")
    assert result["description_placeholders"]["error"]
    assert form_value(result, "document") == document
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_import_explains_typed_cooling_and_reference_errors(hass) -> None:
    """Cooling and reference errors point at the room or loop that can fix them."""
    for fixture, path, error in (
        ("cooling_reference.yaml", "rooms.living_room.loops.living_loop", "reference"),
        ("cooling_observation.yaml", "rooms.living_room.humidity_sensors", "humidity"),
        ("designated_reference.yaml", "rooms.living_room.temperature_sensors", "designated"),
    ):
        result = await _import(hass, _fixture(f"invalid/{fixture}"))
        assert result["errors"] == {"base": "invalid_document"}
        assert result["description_placeholders"]["path"] == path
        assert error in result["description_placeholders"]["error"].lower()


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("hydronicus: [1\n", id="yaml-syntax"),
        pytest.param(None, id="empty"),
        pytest.param(["not", "a", "mapping"], id="list"),
    ],
)
async def test_unreadable_plant_file_is_a_top_level_error(hass, document: Any) -> None:
    """Broken YAML and a file that is not a mapping are reported, not raised."""
    result = await _import(hass, document)

    assert result["errors"] == {"base": "invalid_document"}
    assert result["description_placeholders"]["path"] == "the top level"


async def test_import_refuses_a_hydronicus_entity(hass) -> None:
    """A Hydronicus entity bound in the file is reported with its path."""
    own_sensor = _own_entity(hass, "sensor", "own_temperature")
    document = _fixture("single_room.yaml")
    room = next(iter(document["rooms"].values()))
    room["temperature_sensors"] = [own_sensor]
    slug = next(iter(document["rooms"]))

    result = await _import(hass, document)

    assert result["errors"] == {"base": "document_own_entity"}
    assert result["description_placeholders"] == {
        "path": f"rooms.{slug}.temperature_sensors.0",
        "entity_id": own_sensor,
    }


_SHARED_ID = "00000000-0000-4000-8000-0000000000c1"


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param(("rooms", "living_room"), ("sources", "heat_pump"), id="room-and-source"),
        pytest.param(("pumps", "pump"), ("sources", "buffer"), id="pump-and-source"),
    ],
)
async def test_import_refuses_one_id_for_two_objects(
    hass, first: tuple[str, str], second: tuple[str, str]
) -> None:
    """Every object id names one object, so handles and registrations never collide."""
    document = _fixture("sources.yaml")
    for kind, slug in (first, second):
        record = document[kind][slug]
        document[kind][slug] = {
            **(record if isinstance(record, dict) else {"entity_id": record}),
            "id": _SHARED_ID,
        }

    result = await _import(hass, document)

    assert result["step_id"] == "import_plant"
    assert result["errors"] == {"base": "invalid_document"}
    assert _SHARED_ID in result["description_placeholders"]["error"]
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_import_review_confirms_only_blocking_warnings(hass) -> None:
    """An unused pump never blocks an import; a shared pump needs confirming."""
    document = _fixture("single_room.yaml")
    document["pumps"]["spare_pump"] = "switch.spare_pump"
    result = await _import(hass, document)

    assert result["step_id"] == "import_review"
    assert "Spare pump" in result["description_placeholders"]["warnings"]
    assert form_fields(result) == {}

    result = await _import(hass, _fixture("manifold.yaml"))
    assert "confirm" in form_fields(result)
    result = await _submit(hass, result, {"confirm": False})
    assert result["step_id"] == "import_review"
    assert result["errors"] == {"base": "confirm_required"}


async def test_imported_cooling_plant_persists_and_reloads(hass) -> None:
    """Cooling loops and sensor relationships survive import and a reload."""
    entry = await _create_by_import(hass, _fixture("cooling.yaml"))

    circuit = next(iter(entry.runtime_data.plant.circuits.values()))
    assert circuit.cooling_enabled is True
    assert circuit.supply_temperature_sensor == "sensor.living_supply"
    route_ids = tuple(route.id for route in entry.runtime_data.plant.routes)
    assert await hass.config_entries.async_reload(entry.entry_id)
    assert entry.runtime_data.plant.circuits[circuit.id].cooling_enabled is True
    assert tuple(route.id for route in entry.runtime_data.plant.routes) == route_ids


# --------------------------------------------------------------------------
# Plant settings entry points kept in this module
# --------------------------------------------------------------------------


async def test_plant_settings_cannot_disable_dry_run_without_loaded_runtime(hass) -> None:
    """Leaving Dry run requires a live runtime to own activation safety."""
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

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "dry_run"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dry_run"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_DRY_RUN: False}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dry_run_confirmation"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_DRY_RUN_CONFIRMATION: True}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dry_run"
    assert result["errors"] == {"base": "dry_run_runtime_unavailable"}
    assert entry.data[CONF_DRY_RUN] is True


async def test_plant_settings_can_enable_dry_run_without_loaded_runtime(hass) -> None:
    """Re-enabling Dry run is a safe persisted fallback when runtime is unloaded."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hydronic plant",
        data={
            CONF_NAME: "Hydronic plant",
            CONF_PLANT_ID: "00000000-0000-4000-8000-000000000001",
            CONF_DRY_RUN: False,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "dry_run"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_DRY_RUN: True}
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "settings_saved"
    assert entry.data[CONF_DRY_RUN] is True


def test_parent_flow_steps_return_config_flow_results() -> None:
    """Parent and Plant settings steps use the specific ConfigFlowResult type, not FlowResult."""
    steps = [
        getattr(flow, name)
        for flow in (HydronicClimateConfigFlow, PlantSettingsOptionsFlow)
        for name in dir(flow)
        if name.startswith("async_step_") and name not in {"async_step_ignore"}
    ]
    own = [step for step in steps if step.__module__.startswith("custom_components.hydronicus.")]

    assert own
    assert {step.__annotations__["return"] for step in own} == {"config_entries.ConfigFlowResult"}
