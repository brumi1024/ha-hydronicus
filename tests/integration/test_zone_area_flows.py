"""Zones are set up from Home Assistant areas: guided setup, the zone forms, and devices."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import CONF_NAME, DOMAIN, SUBENTRY_TYPE_ZONE
from custom_components.hydronicus.entry_configuration import zone_draft
from tests.integration.flow_forms import form_fields, form_value, frontend_submission
from tests.integration.plant_fixtures import (
    MANIFOLD_PUMP_ENTITY,
    MANIFOLD_PUMP_ID,
    manifold_topology,
    manifold_zones,
    plant_data,
    plant_entry,
    zone_subentry,
)

PUMP = "switch.manifold_pump"
GROUND, UPSTAIRS = manifold_zones(("Ground floor", "Upstairs"))


def _temperature(hass, entity_id: str, value: float = 20.0) -> None:
    hass.states.async_set(
        entity_id, str(value), {"device_class": "temperature", "unit_of_measurement": "°C"}
    )


def _humidity(hass, entity_id: str, value: float = 50.0) -> None:
    hass.states.async_set(
        entity_id, str(value), {"device_class": "humidity", "unit_of_measurement": "%"}
    )


@pytest.fixture
def home(hass) -> dict[str, str]:
    """Kitchen and hall downstairs, a bedroom upstairs, a bare study, and a loft that loops.

    The kitchen and the hall name both sensors, the bedroom names only a
    temperature sensor, the study names none, and the loft names a sensor that
    Hydronicus provides, which no zone may follow.
    """
    floors = fr.async_get(hass)
    ground = floors.async_create("Ground floor")
    upstairs = floors.async_create("Upstairs")
    areas = ar.async_get(hass)
    for room in ("kitchen", "hall", "bedroom"):
        _temperature(hass, f"sensor.{room}_temperature")
    for room in ("kitchen", "hall"):
        _humidity(hass, f"sensor.{room}_humidity")
    _temperature(hass, "sensor.study_probe", 19.0)
    own = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, "own-loft", suggested_object_id="loft_combined"
    )
    _temperature(hass, own.entity_id)
    for entity_id in ("switch.kitchen_valve", "switch.hall_valve", "switch.study_valve", PUMP):
        hass.states.async_set(entity_id, "off")
    return {
        "kitchen": areas.async_create(
            "Kitchen",
            floor_id=ground.floor_id,
            temperature_entity_id="sensor.kitchen_temperature",
            humidity_entity_id="sensor.kitchen_humidity",
        ).id,
        "hall": areas.async_create(
            "Hall",
            floor_id=ground.floor_id,
            temperature_entity_id="sensor.hall_temperature",
            humidity_entity_id="sensor.hall_humidity",
        ).id,
        "bedroom": areas.async_create(
            "Bedroom",
            floor_id=upstairs.floor_id,
            temperature_entity_id="sensor.bedroom_temperature",
        ).id,
        "study": areas.async_create("Study").id,
        "loft": areas.async_create(
            "Loft", floor_id=upstairs.floor_id, temperature_entity_id=own.entity_id
        ).id,
    }


# --------------------------------------------------------------------------
# Guided setup
# --------------------------------------------------------------------------


async def _submit(hass, result: Mapping[str, Any], user_input: Mapping[str, Any]) -> dict:
    return await hass.config_entries.flow.async_configure(result["flow_id"], dict(user_input))


async def _zoning_menu(hass) -> dict:
    """Advance guided setup past the Plant form."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await _submit(hass, result, {"next_step_id": "guided"})
    return await _submit(hass, result, {CONF_NAME: "Home plant", "pump_entity": PUMP})


async def _answer(hass, answer: str) -> dict:
    return await _submit(hass, await _zoning_menu(hass), {"next_step_id": answer})


async def _created(hass, result: dict) -> config_entries.ConfigEntry:
    """Confirm the review when it asks, and return the loaded Plant."""
    assert result["step_id"] == "review", result.get("errors")
    result = await _submit(hass, result, {"confirm": True} if form_fields(result) else {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return result["result"]


def _zones(entry: config_entries.ConfigEntry) -> dict[str, dict[str, Any]]:
    return {zone[CONF_NAME]: zone for zone in entry.data["topology"]["zones"]}


def _zone_device(hass, entry: config_entries.ConfigEntry, zone_id: str) -> dr.DeviceEntry:
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, f"{entry.data['plant_id']}:zone:{zone_id}"), entry.entry_id
    )
    assert device is not None
    return device


async def test_guided_setup_asks_how_the_home_is_zoned(hass, home) -> None:
    result = await _zoning_menu(hass)

    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "zoning"
    assert result["menu_options"] == ["zoning_whole_home", "zoning_per_area", "zoning_grouped"]


async def test_whole_home_is_one_zone_over_every_area_with_a_temperature_sensor(hass, home) -> None:
    result = await _answer(hass, "zoning_whole_home")

    assert result["step_id"] == "zone"
    assert "add_another" not in form_fields(result)
    assert form_value(result, CONF_NAME) == "Home"
    # The study names no sensor, and the loft names one that Hydronicus provides.
    assert form_value(result, "areas") == ["bedroom", "hall", "kitchen"]
    entry = await _created(
        hass,
        await _submit(
            hass, result, {**frontend_submission(result), "valves": ["switch.kitchen_valve"]}
        ),
    )

    (zone,) = entry.data["topology"]["zones"]
    assert zone[CONF_NAME] == "Home"
    assert zone["areas"] == [{"area_id": "bedroom"}, {"area_id": "hall"}, {"area_id": "kitchen"}]
    assert zone["temperature_sensor_metadata"] == []
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.plant.zones[zone["id"]].temperature_sensors == (
        "sensor.bedroom_temperature",
        "sensor.hall_temperature",
        "sensor.kitchen_temperature",
    )
    # A device has one area, so a zone over three areas leaves its device unassigned.
    assert _zone_device(hass, entry, zone["id"]).area_id is None


async def test_per_area_setup_opens_one_prefilled_zone_form_per_area(hass, home) -> None:
    result = await _answer(hass, "zoning_per_area")

    assert result["step_id"] == "zoning_per_area"
    assert form_value(result, "areas") == ["bedroom", "hall", "kitchen"]
    result = await _submit(hass, result, {"areas": []})
    assert result["errors"] == {"areas": "areas_required"}

    result = await _submit(hass, result, {"areas": ["kitchen", "study"]})
    assert result["step_id"] == "zone"
    assert "add_another" not in form_fields(result)
    assert form_value(result, CONF_NAME) == "Kitchen"
    assert form_value(result, "areas") == ["kitchen"]
    assert result["description_placeholders"]["progress"] == "\n\nZone 1 of 2: Kitchen."
    result = await _submit(
        hass, result, {**frontend_submission(result), "valves": ["switch.kitchen_valve"]}
    )

    assert result["step_id"] == "zone"
    assert form_value(result, CONF_NAME) == "Study"
    assert form_value(result, "areas") == ["study"]
    assert result["description_placeholders"]["progress"] == "\n\nZone 2 of 2: Study."
    study = {**frontend_submission(result), "valves": ["switch.study_valve"]}
    result = await _submit(hass, result, study)
    # The study names no temperature sensor, so the zone needs one of its own.
    assert result["errors"] == {"areas": "no_temperature_source"}
    assert form_value(result, "areas") == ["study"]
    result = await _submit(hass, result, {**study, "temperature_sensors": ["sensor.study_probe"]})

    assert result["step_id"] == "review"
    assert (
        "Area Study of zone Study has no temperature sensor"
        in (result["description_placeholders"]["warnings"])
    )
    entry = await _created(hass, result)
    zones = _zones(entry)
    assert zones["Kitchen"]["areas"] == [{"area_id": "kitchen"}]
    assert zones["Study"]["areas"] == [{"area_id": "study"}]
    assert [record["entity_id"] for record in zones["Study"]["temperature_sensor_metadata"]] == [
        "sensor.study_probe"
    ]
    # A zone over exactly one area suggests that area for its device.
    assert _zone_device(hass, entry, zones["Kitchen"]["id"]).area_id == "kitchen"
    assert _zone_device(hass, entry, zones["Study"]["id"]).area_id == "study"


async def test_grouped_setup_names_zones_after_their_floor_and_reviews_shared_areas(
    hass, home
) -> None:
    result = await _answer(hass, "zoning_grouped")

    assert result["step_id"] == "zone"
    assert form_value(result, "add_another") is False
    assert form_value(result, "areas") is None
    assert result["description_placeholders"]["progress"] == ""
    result = await _submit(
        hass,
        result,
        {"areas": ["kitchen", "hall"], "valves": ["switch.kitchen_valve"], "add_another": True},
    )

    assert result["step_id"] == "zone"
    assert result["description_placeholders"]["zones"] == (
        "\n\nZones added so far:\n- Ground floor: Kitchen and Hall"
    )
    mixed = {"areas": ["hall", "bedroom"], "valves": ["switch.hall_valve"]}
    result = await _submit(hass, result, mixed)
    # Areas on two floors give no name, so the form asks for one.
    assert result["errors"] == {CONF_NAME: "zone_name_required"}
    result = await _submit(hass, result, {**mixed, CONF_NAME: "Stairwell"})

    assert result["step_id"] == "review"
    # The review names the areas each zone covers.
    assert result["description_placeholders"]["zones"] == (
        "- Ground floor: Kitchen and Hall\n- Stairwell: Hall and Bedroom"
    )
    assert (
        "Area Hall is covered by zones Ground floor and Stairwell"
        in (result["description_placeholders"]["warnings"])
    )
    zones = _zones(await _created(hass, result))
    assert zones["Ground floor"]["areas"] == [{"area_id": "kitchen"}, {"area_id": "hall"}]
    assert zones["Stairwell"]["areas"] == [{"area_id": "hall"}, {"area_id": "bedroom"}]


async def test_guided_review_confirms_a_cooled_area_without_humidity(hass, home) -> None:
    result = await _answer(hass, "zoning_grouped")
    result = await _submit(
        hass,
        result,
        {
            CONF_NAME: "Bedroom",
            "areas": ["bedroom"],
            "valves": ["switch.kitchen_valve"],
            # The area counts as the humidity source, although it names no humidity sensor.
            "cooling": {"cooling_enabled": True, "supply_temperature_sensor": "sensor.supply"},
        },
    )

    assert result["step_id"] == "review"
    assert (
        "Area Bedroom of zone Bedroom has no humidity sensor"
        in (result["description_placeholders"]["warnings"])
    )
    assert "confirm" in form_fields(result)


# --------------------------------------------------------------------------
# The zone form of a Plant
# --------------------------------------------------------------------------


def _pump_only_entry() -> MockConfigEntry:
    pump = {
        "id": MANIFOLD_PUMP_ID,
        "name": "Manifold pump",
        "entity_id": MANIFOLD_PUMP_ENTITY,
        "overrun_seconds": 0.0,
    }
    return plant_entry(plant_data({"pumps": [pump]}))


async def _setup(hass, entry: MockConfigEntry) -> MockConfigEntry:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _configure(hass, result: Mapping[str, Any], user_input: Mapping[str, Any]) -> dict:
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], dict(user_input)
    )
    await hass.async_block_till_done()
    return result


async def _confirmed(hass, result: dict) -> dict:
    if result["type"] == FlowResultType.FORM and result["step_id"] == "review":
        result = await _configure(hass, result, {"confirm": True})
    return result


async def _start_zone(hass, entry: MockConfigEntry) -> dict:
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_ZONE), context={"source": config_entries.SOURCE_USER}
    )


async def _menu(hass, entry: MockConfigEntry, zone_id: str, option: str) -> dict:
    result = await entry.start_subentry_reconfigure_flow(
        hass, zone_subentry(entry, zone_id).subentry_id
    )
    return await _configure(hass, result, {"next_step_id": option})


def _stored_zone(entry: MockConfigEntry, zone_id: str) -> dict[str, Any]:
    return zone_draft(entry.data, zone_id).zone


async def test_the_zone_form_asks_for_areas_after_the_name(hass, home) -> None:
    entry = await _setup(hass, _pump_only_entry())

    result = await _start_zone(hass, entry)

    fields = form_fields(result)
    assert list(fields) == [
        CONF_NAME,
        "areas",
        "temperature_sensors",
        "external_climate_entity",
        "valves",
        "cooling",
        "cooling.cooling_enabled",
        "cooling.humidity_sensors",
        "cooling.supply_temperature_sensor",
        "cooling.surface_temperature_sensor",
        "cooling.condensation_margin",
    ]
    # A checkbox list shows its label as a heading, which Home Assistant's area
    # selector shows only on its empty add field, below the chosen areas.
    assert fields["areas"]["selector"]["select"] == {
        "options": [
            {"value": "bedroom", "label": "Bedroom"},
            {"value": "hall", "label": "Hall"},
            {"value": "kitchen", "label": "Kitchen"},
            {"value": "loft", "label": "Loft"},
            {"value": "study", "label": "Study"},
        ],
        "multiple": True,
        "mode": "list",
        "custom_value": False,
        "sort": False,
    }
    # The name may stay empty when areas give it.
    assert fields[CONF_NAME]["required"] is False


@pytest.mark.parametrize(
    ("areas", "name"),
    [
        pytest.param(["kitchen"], "Kitchen", id="one area"),
        pytest.param(["study"], "Study", id="one area on no floor"),
        pytest.param(["kitchen", "hall"], "Ground floor", id="areas on one floor"),
    ],
)
async def test_an_empty_zone_name_comes_from_its_areas(hass, home, areas, name) -> None:
    entry = await _setup(hass, _pump_only_entry())

    result = await _confirmed(
        hass,
        await _configure(
            hass,
            await _start_zone(hass, entry),
            {
                CONF_NAME: " ",
                "areas": areas,
                "temperature_sensors": ["sensor.study_probe"],
                "valves": ["switch.kitchen_valve"],
            },
        ),
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == name
    (zone,) = entry.data["topology"]["zones"]
    assert zone[CONF_NAME] == name
    assert zone["areas"] == [{"area_id": area} for area in areas]


@pytest.mark.parametrize(
    "areas",
    [
        pytest.param(["hall", "bedroom"], id="areas on two floors"),
        pytest.param(["kitchen", "study"], id="an area on no floor"),
        pytest.param([], id="no areas"),
    ],
)
async def test_the_zone_form_asks_for_a_name_the_areas_cannot_give(hass, home, areas) -> None:
    entry = await _setup(hass, _pump_only_entry())
    user_input = {
        "areas": areas,
        "temperature_sensors": ["sensor.study_probe"],
        "valves": ["switch.kitchen_valve"],
    }

    result = await _configure(hass, await _start_zone(hass, entry), user_input)

    assert result["errors"] == {CONF_NAME: "zone_name_required"}


def test_the_zone_name_error_names_its_field() -> None:
    """Home Assistant shows a field error above its field, which for the first field looks
    like an error of the whole form, so the message names the field it belongs to."""
    strings = json.loads(
        (Path(__file__).parents[2] / "custom_components/hydronicus/strings.json").read_text()
    )
    for errors in (strings["config"]["error"], strings["config_subentries"]["zone"]["error"]):
        assert errors["zone_name_required"].startswith("Enter a Zone name.")


@pytest.mark.parametrize(
    "user_input",
    [
        pytest.param({"areas": ["study"]}, id="an area without a temperature sensor"),
        pytest.param({"areas": ["loft"]}, id="an area naming a Hydronicus sensor"),
        pytest.param({"areas": [], "temperature_sensors": []}, id="no areas and no sensors"),
    ],
)
async def test_a_hydronicus_thermostat_needs_a_resolved_temperature_sensor(
    hass, home, user_input
) -> None:
    entry = await _setup(hass, _pump_only_entry())

    result = await _configure(
        hass,
        await _start_zone(hass, entry),
        {CONF_NAME: "Upstairs", "valves": ["switch.kitchen_valve"], **user_input},
    )

    assert result["errors"] == {"areas": "no_temperature_source"}
    assert entry.data["topology"].get("zones", []) == []


@pytest.mark.parametrize(
    "user_input",
    [
        pytest.param({"temperature_sensors": ["sensor.study_probe"]}, id="an extra sensor"),
        pytest.param({"external_climate_entity": "climate.study"}, id="an existing thermostat"),
    ],
)
async def test_an_area_without_a_sensor_is_fine_with_another_temperature_source(
    hass, home, user_input
) -> None:
    hass.states.async_set("climate.study", "heat")
    entry = await _setup(hass, _pump_only_entry())

    result = await _confirmed(
        hass,
        await _configure(
            hass,
            await _start_zone(hass, entry),
            {"areas": ["study"], "valves": ["switch.study_valve"], **user_input},
        ),
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data["topology"]["zones"][0]["areas"] == [{"area_id": "study"}]


async def test_adding_a_zone_reviews_a_cooled_area_without_humidity(hass, home) -> None:
    entry = await _setup(hass, _pump_only_entry())

    result = await _configure(
        hass,
        await _start_zone(hass, entry),
        {
            "areas": ["bedroom"],
            "valves": ["switch.kitchen_valve"],
            "cooling": {"cooling_enabled": True, "supply_temperature_sensor": "sensor.supply"},
        },
    )

    assert result["step_id"] == "review"
    assert (
        "Area Bedroom of zone Bedroom has no humidity sensor"
        in (result["description_placeholders"]["warnings"])
    )
    result = await _configure(hass, result, {"confirm": True})
    assert result["type"] == FlowResultType.CREATE_ENTRY


# --------------------------------------------------------------------------
# Editing a zone
# --------------------------------------------------------------------------


def _area_topology(areas: list[dict[str, Any]], *, sensors: bool = True) -> dict[str, Any]:
    """Return two zones where Ground floor covers ``areas``."""
    topology = manifold_topology(("Ground floor", "Upstairs"))
    ground = topology["zones"][0]
    ground["areas"] = areas
    if not sensors:
        ground["temperature_sensor_metadata"] = []
    return topology


def _area_issue_keys(hass) -> set[str]:
    return {
        issue.translation_key
        for (domain, _issue_id), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key and issue.translation_key.startswith("zone_")
    }


async def test_the_zone_step_edits_areas_and_removes_a_missing_one(hass, home) -> None:
    _temperature(hass, GROUND.temperature_sensor)
    _temperature(hass, UPSTAIRS.temperature_sensor)
    topology = _area_topology(
        [{"area_id": "attic"}, {"area_id": "kitchen", "weight": 2.0}], sensors=False
    )
    entry = await _setup(hass, plant_entry(plant_data(topology)))
    assert "zone_area_missing" in _area_issue_keys(hass)

    result = await _menu(hass, entry, GROUND.zone_id, "zone")
    assert list(form_fields(result)) == [
        CONF_NAME,
        "areas",
        "temperature_sensors",
        "external_climate_entity",
    ]
    # The missing area stays visible by name, so the user can see and remove it.
    assert form_value(result, "areas") == ["attic", "kitchen"]
    assert {"value": "attic", "label": "Attic (no longer exists)"} in (
        form_fields(result)["areas"]["selector"]["select"]["options"]
    )
    assert result["description_placeholders"]["missing_areas"] == (
        "\n\nArea Attic no longer exists in Home Assistant, so the zone gets no reading "
        "from it. Clear it under Areas, or create an area named Attic to bring it back."
    )
    result = await _confirmed(hass, await _configure(hass, result, frontend_submission(result)))
    assert result["reason"] == "reconfigure_successful"
    assert _stored_zone(entry, GROUND.zone_id)["areas"] == [
        {"area_id": "attic"},
        {"area_id": "kitchen", "weight": 2.0},
    ]

    result = await _menu(hass, entry, GROUND.zone_id, "zone")
    result = await _confirmed(
        hass,
        await _configure(
            hass, result, {**frontend_submission(result), "areas": ["kitchen", "hall"]}
        ),
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    # A kept area keeps its settings, and a new area starts from the defaults.
    assert _stored_zone(entry, GROUND.zone_id)["areas"] == [
        {"area_id": "kitchen", "weight": 2.0},
        {"area_id": "hall"},
    ]
    assert "zone_area_missing" not in _area_issue_keys(hass)
    result = await _menu(hass, entry, GROUND.zone_id, "zone")
    assert result["description_placeholders"]["missing_areas"] == ""
    assert "attic" not in [
        option["value"] for option in form_fields(result)["areas"]["selector"]["select"]["options"]
    ]


async def test_a_cleared_zone_name_stays_cleared_when_the_form_returns(hass, home) -> None:
    """The frontend leaves out a field the user cleared, so a returned form must not refill it."""
    _temperature(hass, UPSTAIRS.temperature_sensor)
    entry = await _setup(
        hass, plant_entry(plant_data(_area_topology([{"area_id": "kitchen"}], sensors=False)))
    )

    result = await _menu(hass, entry, GROUND.zone_id, "zone")
    assert form_value(result, CONF_NAME) == "Ground floor"
    submission = {**frontend_submission(result), "areas": ["hall", "bedroom"]}
    del submission[CONF_NAME]
    result = await _configure(hass, result, submission)

    assert result["errors"] == {CONF_NAME: "zone_name_required"}
    assert form_value(result, CONF_NAME) is None
    assert form_value(result, "areas") == ["hall", "bedroom"]


async def test_the_zone_step_needs_a_temperature_source_for_a_hydronicus_thermostat(
    hass, home
) -> None:
    _temperature(hass, UPSTAIRS.temperature_sensor)
    entry = await _setup(
        hass, plant_entry(plant_data(_area_topology([{"area_id": "kitchen"}], sensors=False)))
    )

    result = await _menu(hass, entry, GROUND.zone_id, "zone")
    result = await _configure(hass, result, {**frontend_submission(result), "areas": ["study"]})

    assert result["errors"] == {"areas": "no_temperature_source"}


async def test_the_sensors_step_edits_areas_and_their_settings(hass, home) -> None:
    _temperature(hass, GROUND.temperature_sensor)
    _temperature(hass, UPSTAIRS.temperature_sensor)
    entry = await _setup(
        hass, plant_entry(plant_data(_area_topology([{"area_id": "kitchen", "required": True}])))
    )

    result = await _menu(hass, entry, GROUND.zone_id, "sensors")
    assert list(form_fields(result)) == [
        "areas",
        "humidity_sensors",
        "temperature_aggregation",
        "configure_sensor_metadata",
    ]
    assert form_value(result, "areas") == ["kitchen"]
    result = await _configure(
        hass,
        result,
        {
            **frontend_submission(result),
            "areas": ["kitchen", "hall"],
            "configure_sensor_metadata": True,
        },
    )
    # One form per explicit sensor, then one per area.
    assert result["step_id"] == "sensor_metadata"
    assert result["description_placeholders"] == {"sensor": GROUND.temperature_sensor}
    result = await _configure(hass, result, frontend_submission(result))
    assert result["step_id"] == "area_metadata"
    assert result["description_placeholders"] == {
        "area": "Kitchen",
        "temperature_sensor": "sensor.kitchen_temperature",
        "humidity_sensor": "sensor.kitchen_humidity",
    }
    assert list(form_fields(result)) == [
        "required",
        "weight",
        "max_age_seconds",
        "designated_reference",
    ]
    assert form_value(result, "required") is True
    result = await _configure(hass, result, {**frontend_submission(result), "required": False})
    assert result["step_id"] == "area_metadata"
    assert result["description_placeholders"]["area"] == "Hall"
    assert form_value(result, "weight") == 1.0
    result = await _configure(
        hass,
        result,
        {**frontend_submission(result), "weight": 2.0, "designated_reference": True},
    )
    assert result["step_id"] == "sensor_policy"
    result = await _configure(hass, result, {"temperature_aggregation": "designated_reference"})

    assert result["reason"] == "reconfigure_successful"
    zone = _stored_zone(entry, GROUND.zone_id)
    assert zone["temperature_aggregation"] == "designated_reference"
    # Settings at their defaults are left out, as a plant file writes them.
    assert zone["areas"] == [
        {"area_id": "kitchen"},
        {"area_id": "hall", "weight": 2.0, "designated_reference": True},
    ]
    await hass.async_block_till_done()
    reference = next(
        record
        for record in entry.runtime_data.plant.zones[GROUND.zone_id].temperature_sensor_metadata
        if record.designated_reference
    )
    assert (reference.entity_id, reference.area_id) == ("sensor.hall_temperature", "hall")


async def test_the_sensors_step_names_a_missing_area_in_its_settings(hass, home) -> None:
    _temperature(hass, GROUND.temperature_sensor)
    _temperature(hass, UPSTAIRS.temperature_sensor)
    entry = await _setup(hass, plant_entry(plant_data(_area_topology([{"area_id": "attic"}]))))

    result = await _menu(hass, entry, GROUND.zone_id, "sensors")
    assert "Area Attic no longer exists" in result["description_placeholders"]["missing_areas"]
    result = await _configure(
        hass, result, {**frontend_submission(result), "configure_sensor_metadata": True}
    )
    result = await _configure(hass, result, frontend_submission(result))

    assert result["step_id"] == "area_metadata"
    assert result["description_placeholders"] == {
        "area": "Attic",
        "temperature_sensor": "None",
        "humidity_sensor": "None",
    }


async def test_the_sensors_step_needs_a_temperature_source_for_a_hydronicus_thermostat(
    hass, home
) -> None:
    _temperature(hass, UPSTAIRS.temperature_sensor)
    entry = await _setup(
        hass, plant_entry(plant_data(_area_topology([{"area_id": "kitchen"}], sensors=False)))
    )

    result = await _menu(hass, entry, GROUND.zone_id, "sensors")
    result = await _configure(hass, result, {**frontend_submission(result), "areas": []})

    assert result["errors"] == {"areas": "no_temperature_source"}


# --------------------------------------------------------------------------
# Device placement
# --------------------------------------------------------------------------


async def test_a_zone_device_takes_the_area_only_of_a_zone_over_one_existing_area(
    hass, home
) -> None:
    names = ("One area", "Two areas", "Missing area", "No areas")
    topology = manifold_topology(names)
    for zone, areas in zip(
        topology["zones"], (["kitchen"], ["kitchen", "hall"], ["attic"], []), strict=True
    ):
        zone["areas"] = [{"area_id": area_id} for area_id in areas]
    for zone in manifold_zones(names):
        _temperature(hass, zone.temperature_sensor)
    area_count = len(ar.async_get(hass).areas)

    entry = await _setup(hass, plant_entry(plant_data(topology)))

    placed = {
        name: _zone_device(hass, entry, zone.zone_id).area_id
        for name, zone in zip(names, manifold_zones(names), strict=True)
    }
    assert placed == {
        "One area": "kitchen",
        "Two areas": None,
        "Missing area": None,
        "No areas": None,
    }
    # Suggesting a missing area would have created it.
    assert len(ar.async_get(hass).areas) == area_count


async def test_a_placed_zone_device_keeps_entity_ids_without_the_area_name(hass, home) -> None:
    # Home Assistant puts the area name in front of new entity IDs, so a zone
    # named after its area would otherwise get climate.kitchen_kitchen.
    topology = manifold_topology(("Kitchen",))
    topology["zones"][0]["areas"] = [{"area_id": "kitchen"}]
    (kitchen,) = manifold_zones(("Kitchen",))
    _temperature(hass, kitchen.temperature_sensor)

    entry = await _setup(hass, plant_entry(plant_data(topology)))

    device = _zone_device(hass, entry, kitchen.zone_id)
    assert device.area_id == "kitchen"
    entity_ids = {
        registered.entity_id
        for registered in er.async_entries_for_device(er.async_get(hass), device.id)
    }
    assert "climate.kitchen" in entity_ids
    assert "sensor.kitchen_combined_temperature" in entity_ids
    assert not any("kitchen_kitchen" in entity_id for entity_id in entity_ids)

    # The area is placed only when the device is created, so a device the user
    # took out of the area stays out after a reload.
    dr.async_get(hass).async_update_device(device.id, area_id=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _zone_device(hass, entry, kitchen.zone_id).area_id is None
