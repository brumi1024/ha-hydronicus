"""Zones follow the sensors that their Home Assistant areas name."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from homeassistant.components.repairs import DOMAIN as REPAIRS_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.hydronicus.areas import resolve_area_sensors
from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.diagnostics import async_get_config_entry_diagnostics
from custom_components.hydronicus.websocket import WS_SUBSCRIBE_PLANT, ws_subscribe_plant
from tests.integration.flow_forms import form_fields
from tests.integration.plant_fixtures import (
    PLANT_ID,
    manifold_topology,
    manifold_zones,
    plant_data,
    plant_entry,
    subentry_id_for,
)
from tests.integration.test_websocket import _Connection, _User

GROUND, UPSTAIRS = manifold_zones(("Ground floor", "Upstairs"))


def _temperature(hass, entity_id: str, value: float) -> None:
    hass.states.async_set(
        entity_id, str(value), {"device_class": "temperature", "unit_of_measurement": "°C"}
    )


def _humidity(hass, entity_id: str, value: float) -> None:
    hass.states.async_set(
        entity_id, str(value), {"device_class": "humidity", "unit_of_measurement": "%"}
    )


def _area(hass, name: str, *, temperature: str | None = None, humidity: str | None = None):
    return ar.async_get(hass).async_create(
        name, temperature_entity_id=temperature, humidity_entity_id=humidity
    )


def _topology(ground_areas: list[Any], *, ground_sensors: bool = False) -> dict[str, Any]:
    """Return two zones where Ground floor covers areas and Upstairs has its own sensor."""
    topology = manifold_topology(("Ground floor", "Upstairs"))
    ground = topology["zones"][0]
    ground["areas"] = [
        area if isinstance(area, Mapping) else {"area_id": area} for area in ground_areas
    ]
    if not ground_sensors:
        del ground["temperature_sensor_metadata"]
    return topology


async def _loaded(hass, topology: Mapping[str, Any], *, dry_run: bool = True) -> MockConfigEntry:
    entry = plant_entry(plant_data(topology, dry_run=dry_run))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


_AREA_ISSUES = frozenset(
    {
        "zone_area_missing",
        "zone_without_temperature_source",
        "zone_area_self_feed",
        "missing_area_sensor_binding",
    }
)


def _area_issues(hass) -> dict[str, ir.IssueEntry]:
    return {
        issue.translation_key: issue
        for (domain, _issue_id), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key in _AREA_ISSUES
    }


def _combined_temperature(hass, zone_id: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"00000000-0000-4000-8000-000000000001_{zone_id}_aggregate_temperature"
    )
    assert entity_id is not None
    return hass.states.get(entity_id)


@pytest.fixture
def home(hass):
    """Kitchen and hall with both sensors, and a study without any."""
    _temperature(hass, "sensor.kitchen_temperature", 20.0)
    _humidity(hass, "sensor.kitchen_humidity", 45.0)
    _temperature(hass, "sensor.hall_temperature", 22.0)
    _humidity(hass, "sensor.hall_humidity", 50.0)
    _temperature(hass, "sensor.spare_temperature", 18.0)
    _temperature(hass, UPSTAIRS.temperature_sensor, 21.0)
    return {
        "kitchen": _area(
            hass,
            "Kitchen",
            temperature="sensor.kitchen_temperature",
            humidity="sensor.kitchen_humidity",
        ),
        "hall": _area(
            hass, "Hall", temperature="sensor.hall_temperature", humidity="sensor.hall_humidity"
        ),
        "study": _area(hass, "Study"),
    }


async def test_a_zone_follows_the_sensors_of_its_areas(hass, home) -> None:
    entry = await _loaded(hass, _topology(["kitchen", {"area_id": "hall", "weight": 3.0}]))

    zone = entry.runtime_data.plant.zones[GROUND.zone_id]
    assert zone.temperature_sensors == ("sensor.kitchen_temperature", "sensor.hall_temperature")
    assert zone.humidity_sensors == ("sensor.kitchen_humidity", "sensor.hall_humidity")
    assert entry.runtime_data.zone_current_temperature(GROUND.zone_id) == pytest.approx(21.0)

    state = _combined_temperature(hass, GROUND.zone_id)
    assert float(state.state) == pytest.approx(21.0)
    assert state.attributes["areas"] == [
        {
            "area_id": "kitchen",
            "temperature_entity_id": "sensor.kitchen_temperature",
            "humidity_entity_id": "sensor.kitchen_humidity",
        },
        {
            "area_id": "hall",
            "temperature_entity_id": "sensor.hall_temperature",
            "humidity_entity_id": "sensor.hall_humidity",
        },
    ]
    assert sorted(state.attributes["usable_sensor_ids"]) == [
        "sensor.hall_temperature",
        "sensor.kitchen_temperature",
    ]
    # A zone without areas keeps its attributes as they were.
    assert "areas" not in _combined_temperature(hass, UPSTAIRS.zone_id).attributes
    assert not _area_issues(hass)


async def test_changing_a_covered_area_sensor_reloads_the_plant(hass, home) -> None:
    calls = async_mock_service(hass, "switch", "turn_on") + async_mock_service(
        hass, "switch", "turn_off"
    )
    entry = await _loaded(hass, _topology(["kitchen"]))
    runtime = entry.runtime_data

    ar.async_get(hass).async_update("kitchen", temperature_entity_id="sensor.spare_temperature")
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not runtime
    zone = entry.runtime_data.plant.zones[GROUND.zone_id]
    assert zone.temperature_sensors == ("sensor.spare_temperature",)
    assert entry.runtime_data.zone_current_temperature(GROUND.zone_id) == 18.0
    # A Dry run Plant stays silent across the reload.
    assert calls == []


async def test_a_live_plant_stays_live_across_an_area_reload(hass, home) -> None:
    for entity_id in (GROUND.valve_entity, UPSTAIRS.valve_entity, "switch.manifold_pump"):
        hass.states.async_set(entity_id, "off")
    entry = await _loaded(hass, _topology(["kitchen"]), dry_run=False)
    assert entry.runtime_data.dry_run is False
    runtime = entry.runtime_data

    ar.async_get(hass).async_update("kitchen", temperature_entity_id="sensor.spare_temperature")
    await hass.async_block_till_done()

    # An area change edits no output, so the output authorization still holds.
    assert entry.runtime_data is not runtime
    assert entry.runtime_data.dry_run is False
    assert entry.data["dry_run"] is False


async def test_changes_that_do_not_reach_the_followed_sensors_do_not_reload(hass, home) -> None:
    entry = await _loaded(hass, _topology(["kitchen"]))
    runtime = entry.runtime_data
    registry = ar.async_get(hass)

    registry.async_update("kitchen", name="Cooking")  # renamed, same sensors
    registry.async_update("hall", temperature_entity_id="sensor.spare_temperature")  # not covered
    _area(hass, "Garage")
    await hass.async_block_till_done()

    assert entry.runtime_data is runtime


async def test_several_area_changes_coalesce_into_one_reload(hass, home, monkeypatch) -> None:
    entry = await _loaded(hass, _topology(["kitchen", "hall"]))
    reloads: list[str] = []
    reload = hass.config_entries.async_reload

    async def counted(entry_id: str) -> bool:
        reloads.append(entry_id)
        return await reload(entry_id)

    monkeypatch.setattr(hass.config_entries, "async_reload", counted)
    registry = ar.async_get(hass)
    registry.async_update("kitchen", temperature_entity_id="sensor.spare_temperature")
    registry.async_update("hall", temperature_entity_id=None)
    registry.async_update("kitchen", humidity_entity_id=None)
    await hass.async_block_till_done()

    assert reloads == [entry.entry_id]
    zone = entry.runtime_data.plant.zones[GROUND.zone_id]
    assert zone.temperature_sensors == ("sensor.spare_temperature",)
    assert zone.humidity_sensors == ("sensor.hall_humidity",)


async def test_a_removed_area_raises_a_repair_and_the_plant_keeps_loading(hass, home) -> None:
    await async_setup_component(hass, REPAIRS_DOMAIN, {})
    entry = await _loaded(hass, _topology(["kitchen", "hall"]))

    ar.async_get(hass).async_delete("kitchen")
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.plant.zones[GROUND.zone_id].temperature_sensors == (
        "sensor.hall_temperature",
    )
    issue = _area_issues(hass)["zone_area_missing"]
    assert issue.is_fixable is True
    assert issue.translation_placeholders["zone"] == "Ground floor"
    # Home Assistant forgets a removed area, but the repair keeps its last name.
    assert issue.translation_placeholders["area"] == "Kitchen"
    assert issue.data["subentry_id"] == subentry_id_for(GROUND.zone_id)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    zones = diagnostics["compiled_topology"]["relationships"]["zones"]
    ground = next(zone for zone in zones if zone["area_count"])
    assert (ground["area_count"], ground["missing_area_count"]) == (2, 1)
    assert ground["area_temperature_sensor_count"] == 1

    # The fix flow opens the zone.
    manager = hass.data[REPAIRS_DOMAIN]["flow_manager"]
    flow = await manager.async_init(DOMAIN, data={"issue_id": _issue_id(hass, "zone_area_missing")})
    assert flow["step_id"] == "confirm"
    flow = await manager.async_configure(flow["flow_id"], {})
    assert flow["type"] == FlowResultType.ABORT
    assert flow["reason"] == "reconfigure_subentry"
    assert flow["next_flow"][1] in {
        progress["flow_id"] for progress in hass.config_entries.subentries.async_progress()
    }

    # An area created again with the same ID resolves the problem.
    _area(hass, "Kitchen", temperature="sensor.kitchen_temperature")
    await hass.async_block_till_done()
    assert "zone_area_missing" not in _area_issues(hass)
    assert "sensor.kitchen_temperature" in (
        entry.runtime_data.plant.zones[GROUND.zone_id].temperature_sensors
    )


def _issue_id(hass, translation_key: str) -> str:
    return next(
        issue_id
        for (domain, issue_id), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == translation_key
    )


async def test_a_zone_whose_areas_name_no_temperature_sensor_is_blocked(hass, home) -> None:
    entry = await _loaded(hass, _topology(["study"]))

    runtime = entry.runtime_data
    assert runtime.zone_is_blocked(GROUND.zone_id)
    assert runtime.zone_blocked_reason(GROUND.zone_id) == (
        "Blocked: no usable temperature sensors remain."
    )
    issue = _area_issues(hass)["zone_without_temperature_source"]
    assert issue.translation_placeholders["areas"] == "area Study"
    assert issue.is_fixable is True

    ar.async_get(hass).async_update("study", temperature_entity_id="sensor.spare_temperature")
    await hass.async_block_till_done()

    assert "zone_without_temperature_source" not in _area_issues(hass)
    assert not entry.runtime_data.zone_is_blocked(GROUND.zone_id)


async def test_an_area_that_names_a_hydronicus_sensor_is_ignored(hass, home) -> None:
    entry = await _loaded(hass, _topology(["study"]))
    upstairs = _combined_temperature(hass, UPSTAIRS.zone_id)

    # The study names the combined temperature of another zone.
    ar.async_get(hass).async_update("study", temperature_entity_id=upstairs.entity_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.plant.zones[GROUND.zone_id].temperature_sensors == ()
    assert entry.runtime_data.area_resolution.self_provided == {"study": (upstairs.entity_id,)}
    issues = _area_issues(hass)
    self_feed = issues["zone_area_self_feed"]
    assert self_feed.is_fixable is False
    assert self_feed.translation_placeholders["entity_ids"] == upstairs.entity_id
    assert self_feed.translation_placeholders["area"] == "Study"
    assert "zone_without_temperature_source" in issues

    ar.async_get(hass).async_update("study", temperature_entity_id="sensor.spare_temperature")
    await hass.async_block_till_done()
    assert not {"zone_area_self_feed", "zone_without_temperature_source"} & set(_area_issues(hass))


async def test_home_assistant_does_not_follow_a_sensor_rename_into_the_area(hass, home) -> None:
    """Renaming a named sensor leaves the area naming the old ID, which a repair reports."""
    registry = er.async_get(hass)
    den = registry.async_get_or_create("sensor", "test", "den", suggested_object_id="den")
    _temperature(hass, den.entity_id, 20.0)
    _area(hass, "Den", temperature=den.entity_id)
    entry = await _loaded(hass, _topology(["den", "hall"]))
    runtime = entry.runtime_data

    registry.async_update_entity(den.entity_id, new_entity_id="sensor.den_air")
    hass.states.async_remove(den.entity_id)
    _temperature(hass, "sensor.den_air", 20.0)
    await hass.async_block_till_done()

    assert ar.async_get(hass).async_get_area("den").temperature_entity_id == den.entity_id
    # Nothing the Plant follows changed, so it did not reload.
    assert entry.runtime_data is runtime
    issue = _area_issues(hass)["missing_area_sensor_binding"]
    assert issue.is_fixable is False
    assert issue.translation_placeholders["area"] == "Den"
    assert issue.translation_placeholders["object_name"] == "Ground floor"
    # The den sensor is optional, so the hall keeps the zone heating.
    assert not runtime.zone_is_blocked(GROUND.zone_id)


async def test_resolution_reads_missing_areas_and_absent_sensors(hass, home) -> None:
    resolution = resolve_area_sensors(hass, ["study", "attic", "kitchen", "study"])

    assert resolution.missing_area_ids == ("attic",)
    assert list(resolution.area_sensors) == ["study", "kitchen"]
    assert resolution.area_sensors["study"].temperature_entity_id is None
    assert resolution.named_entity_ids() == {
        "sensor.kitchen_temperature",
        "sensor.kitchen_humidity",
    }
    assert resolution.name("attic") == "attic"
    assert resolution.name("kitchen") == "Kitchen"


# The plant file review


_DOCUMENT: dict[str, Any] = {
    "hydronicus": 1,
    "name": "Home",
    "pumps": {"ground_pump": "switch.ground_pump", "upstairs_pump": "switch.upstairs_pump"},
    "zones": {
        "ground_floor": {
            "areas": ["kitchen", "study"],
            "loops": {"ground_loop": {"valves": ["switch.ground_valve"], "pump": "ground_pump"}},
        },
        "upstairs": {
            "areas": ["study"],
            "loops": {
                "upstairs_loop": {"valves": ["switch.upstairs_valve"], "pump": "upstairs_pump"}
            },
        },
    },
}


async def _import(hass, document: Mapping[str, Any]) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "import_plant"}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"document": deepcopy(dict(document))}
    )


async def test_the_import_review_lists_area_warnings_without_confirmation(hass, home) -> None:
    result = await _import(hass, _DOCUMENT)

    assert result["step_id"] == "import_review"
    warnings = result["description_placeholders"]["warnings"]
    assert "Area Study of zone Ground floor has no temperature sensor" in warnings
    assert "Area Study is covered by zones Ground floor and Upstairs" in warnings
    assert form_fields(result) == {}


async def test_the_import_review_confirms_a_missing_area(hass, home) -> None:
    document = deepcopy(_DOCUMENT)
    document["zones"]["upstairs"]["areas"] = ["attic"]

    result = await _import(hass, document)

    assert (
        "Zone Upstairs covers area attic, which does not exist"
        in (result["description_placeholders"]["warnings"])
    )
    assert "confirm" in form_fields(result)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"confirm": False})
    assert result["errors"] == {"base": "confirm_required"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"confirm": True})
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_the_import_review_confirms_a_cooled_area_without_humidity(hass, home) -> None:
    document = deepcopy(_DOCUMENT)
    document["zones"]["upstairs"]["areas"] = ["hall"]
    document["zones"]["ground_floor"]["loops"]["ground_loop"] |= {
        "cooling_enabled": True,
        "supply_temperature_sensor": "sensor.supply",
    }

    result = await _import(hass, document)

    warnings = result["description_placeholders"]["warnings"]
    assert "Area Study of zone Ground floor has no humidity sensor" in warnings
    assert "Area Kitchen" not in warnings
    assert "confirm" in form_fields(result)


async def test_the_plant_file_review_confirms_only_new_missing_areas(hass, home) -> None:
    topology = _topology(["attic"])
    entry = await _loaded(hass, topology)

    async def review(document: Mapping[str, Any]) -> dict[str, Any]:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "edit_plant"}
        )
        return await hass.config_entries.options.async_configure(
            result["flow_id"], {"document": document}
        )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "export_plant"}
    )
    exported = _exported_document(result)
    ground = next(zone for zone in exported["zones"].values() if zone["id"] == GROUND.zone_id)

    ground["name"] = "Downstairs"  # the attic was already missing
    result = await review(exported)
    assert result["step_id"] == "edit_plant_review"
    assert "covers area attic" in result["description_placeholders"]["warnings"]
    assert "confirm" not in form_fields(result)

    ground["areas"] = ["attic", "cellar"]
    result = await review(exported)
    assert "confirm" in form_fields(result)


def _exported_document(result: Mapping[str, Any]) -> dict[str, Any]:
    import yaml

    text = result["description_placeholders"]["document"]
    return yaml.safe_load(text.removeprefix("```yaml\n").removesuffix("```"))


# The zone card


def _zone_snapshot(hass, entry: MockConfigEntry, zone_id: str) -> dict[str, Any]:
    snapshot = entry.runtime_data.presentation_snapshot(hass)
    return next(zone for zone in snapshot["zones"] if zone["id"] == zone_id)


async def test_the_zone_snapshot_lists_each_area_in_zone_order(hass, home) -> None:
    entry = await _loaded(hass, _topology(["hall", "study", "kitchen", "attic"]))

    assert _zone_snapshot(hass, entry, GROUND.zone_id)["areas"] == [
        {
            "id": "hall",
            "name": "Hall",
            "missing": False,
            "temperature": 22.0,
            "humidity": 50.0,
            "temperature_entity_id": "sensor.hall_temperature",
            "humidity_entity_id": "sensor.hall_humidity",
        },
        # An area that names no sensor, and an area that does not exist, read nothing.
        {
            "id": "study",
            "name": "Study",
            "missing": False,
            "temperature": None,
            "humidity": None,
            "temperature_entity_id": None,
            "humidity_entity_id": None,
        },
        {
            "id": "kitchen",
            "name": "Kitchen",
            "missing": False,
            "temperature": 20.0,
            "humidity": 45.0,
            "temperature_entity_id": "sensor.kitchen_temperature",
            "humidity_entity_id": "sensor.kitchen_humidity",
        },
        {
            "id": "attic",
            "name": "attic",
            "missing": True,
            "temperature": None,
            "humidity": None,
            "temperature_entity_id": None,
            "humidity_entity_id": None,
        },
    ]
    assert _zone_snapshot(hass, entry, UPSTAIRS.zone_id)["areas"] == []


async def test_an_unusable_area_reading_is_null_and_keeps_its_sensor(hass, home) -> None:
    entry = await _loaded(hass, _topology(["kitchen", "hall"]))

    hass.states.async_set("sensor.hall_temperature", "unavailable")
    hass.states.async_set("sensor.kitchen_humidity", "unknown")
    await hass.async_block_till_done()

    kitchen, hall = _zone_snapshot(hass, entry, GROUND.zone_id)["areas"]
    assert (kitchen["temperature"], kitchen["humidity"]) == (20.0, None)
    assert kitchen["humidity_entity_id"] == "sensor.kitchen_humidity"
    assert (hall["temperature"], hall["humidity"]) == (None, 50.0)
    assert hall["temperature_entity_id"] == "sensor.hall_temperature"


async def test_an_area_reading_is_calibrated_like_the_zone_uses_it(hass, home) -> None:
    topology = _topology(["kitchen", "hall"], ground_sensors=True)
    topology["zones"][0]["temperature_sensor_metadata"] = [
        {"entity_id": "sensor.kitchen_temperature", "calibration_offset": -0.5}
    ]
    entry = await _loaded(hass, topology)

    kitchen, hall = _zone_snapshot(hass, entry, GROUND.zone_id)["areas"]
    assert kitchen["temperature"] == 19.5
    assert hall["temperature"] == 22.0


async def test_an_area_reading_change_is_published_when_the_zone_value_holds(hass, home) -> None:
    """Subscribers hear of a new area reading even when the zone's own value holds."""
    topology = _topology(["kitchen", "hall"])
    topology["zones"][0]["temperature_aggregation"] = "minimum"
    entry = await _loaded(hass, topology)
    runtime = entry.runtime_data
    published: list[None] = []
    runtime.async_add_listener(lambda: published.append(None))
    runtime._notify_listeners_if_changed()
    published.clear()

    hall = runtime.snapshot.temperatures["sensor.hall_temperature"]
    runtime.snapshot = replace(
        runtime.snapshot,
        temperatures={
            **runtime.snapshot.temperatures,
            "sensor.hall_temperature": replace(hall, value=23.0),
        },
    )
    runtime._notify_listeners_if_changed()

    assert published == [None]
    assert runtime.zone_current_temperature(GROUND.zone_id) == 20.0
    assert _zone_snapshot(hass, entry, GROUND.zone_id)["areas"][1]["temperature"] == 23.0


async def test_the_stream_hides_area_sensors_the_user_may_not_read(hass, home) -> None:
    """A readable zone keeps its area readings, but only readable sensors are named."""
    entry = await _loaded(hass, _topology(["kitchen", "hall"]))
    entities = entry.runtime_data.presentation_entities(hass)
    readable = {
        entities[f"zone:{GROUND.zone_id}"],
        "sensor.kitchen_temperature",
        "sensor.hall_humidity",
    }

    class _Permissions:
        def check_entity(self, entity_id: str, _permission: str) -> bool:
            return entity_id in readable

    connection = _Connection(_User(_Permissions()))
    await ws_subscribe_plant.__wrapped__(  # type: ignore[attr-defined]
        hass,
        connection,
        {"id": 1, "type": WS_SUBSCRIBE_PLANT, "plant_id": PLANT_ID},
    )

    (zone,) = connection.results[0][1]["snapshot"]["zones"]
    assert [
        (
            area["temperature"],
            area["humidity"],
            area["temperature_entity_id"],
            area["humidity_entity_id"],
        )
        for area in zone["areas"]
    ] == [
        (20.0, 45.0, "sensor.kitchen_temperature", None),
        (22.0, 50.0, None, "sensor.hall_humidity"),
    ]


# Area repairs and the Plant header


_ISSUE_STRINGS = json.loads(
    (Path(__file__).parents[2] / "custom_components/hydronicus/strings.json").read_text()
)["issues"]


def _rendered(issue: ir.IssueEntry, part: str = "description") -> str:
    """Render one issue text the way the frontend does, failing on a missing placeholder."""
    strings = _ISSUE_STRINGS[issue.translation_key]
    text = strings[part] if part in strings else strings["fix_flow"]["step"]["confirm"][part]
    return text.format_map(issue.translation_placeholders)


async def _plant_with_every_area_problem(hass) -> MockConfigEntry:
    """Give Ground floor a missing and a self-feeding area, and Upstairs a lost area sensor."""
    registry = er.async_get(hass)
    den = registry.async_get_or_create("sensor", "test", "den", suggested_object_id="den")
    _temperature(hass, den.entity_id, 20.0)
    _area(hass, "Den", temperature=den.entity_id)
    topology = _topology(["study", "attic"])
    topology["zones"][1]["areas"] = [{"area_id": "den"}]
    entry = await _loaded(hass, topology)
    upstairs = _combined_temperature(hass, UPSTAIRS.zone_id)
    ar.async_get(hass).async_update("study", temperature_entity_id=upstairs.entity_id)
    await hass.async_block_till_done()
    hass.states.async_remove(den.entity_id)
    await hass.async_block_till_done()
    await entry.runtime_data.async_refresh(hass)
    return entry


async def test_every_area_repair_title_names_its_plant_and_zone(hass, home) -> None:
    await _plant_with_every_area_problem(hass)

    issues = _area_issues(hass)
    assert set(issues) == _AREA_ISSUES
    titles = {key: _rendered(issue, "title") for key, issue in issues.items()}
    # A list of repairs cuts a long title short, so the Plant and zone come first.
    for key, title in titles.items():
        assert title.startswith("Hydronic plant, zone "), key
    assert titles["zone_area_missing"] == ("Hydronic plant, zone Ground floor: missing area attic")
    assert titles["zone_without_temperature_source"] == (
        "Hydronic plant, zone Ground floor: no temperature sensor"
    )
    assert titles["zone_area_self_feed"] == (
        "Hydronic plant, zone Ground floor: area Study names a Hydronicus sensor"
    )
    assert titles["missing_area_sensor_binding"] == (
        "Hydronic plant, zone Upstairs: missing temperature sensor of area Den"
    )


async def test_a_zone_without_temperature_source_reads_well_with_one_area(hass, home) -> None:
    await _loaded(hass, _topology(["study"]))

    issue = _area_issues(hass)["zone_without_temperature_source"]
    for text in (_rendered(issue), _rendered(issue, "description")):
        assert "covers area Study, but" in text
        assert "these areas" not in text


async def test_a_zone_without_temperature_source_lists_several_areas(hass, home) -> None:
    _area(hass, "Porch")
    await _loaded(hass, _topology(["study", "porch"]))

    issue = _area_issues(hass)["zone_without_temperature_source"]
    assert "covers areas Study and Porch, but" in _rendered(issue)


async def test_a_missing_area_repair_advises_a_name_that_recreates_its_id(hass, home) -> None:
    """Home Assistant makes a new area's ID from its name, so the advice names the area."""
    await async_setup_component(hass, REPAIRS_DOMAIN, {})
    kids = _area(hass, "Kids room", temperature="sensor.spare_temperature")
    entry = await _loaded(hass, _topology(["kitchen", kids.id, "attic_2"]))

    ar.async_get(hass).async_delete(kids.id)
    await hass.async_block_till_done()

    issues = [
        issue
        for issue in ir.async_get(hass).issues.values()
        if issue.translation_key == "zone_area_missing"
    ]
    by_area = {issue.translation_placeholders["area_id"]: issue for issue in issues}
    # The area's last known name, and a name made from an ID never seen.
    assert by_area["kids_room"].translation_placeholders["area"] == "Kids room"
    assert by_area["kids_room"].translation_placeholders["recreate_name"] == "Kids room"
    assert by_area["attic_2"].translation_placeholders["area"] == "attic_2"
    assert by_area["attic_2"].translation_placeholders["recreate_name"] == "Attic 2"
    text = _rendered(by_area["kids_room"])
    assert "create an area named Kids room again" in text
    assert "with this ID" not in text

    # Following the advice resolves the repair.
    _area(hass, "Kids room", temperature="sensor.spare_temperature")
    await hass.async_block_till_done()
    assert {
        issue.translation_placeholders["area_id"]
        for issue in ir.async_get(hass).issues.values()
        if issue.translation_key == "zone_area_missing"
    } == {"attic_2"}
    assert entry.state is ConfigEntryState.LOADED


async def test_area_repairs_put_the_plant_header_in_need_of_attention(hass, home) -> None:
    for entity_id in (GROUND.valve_entity, UPSTAIRS.valve_entity, "switch.manifold_pump"):
        hass.states.async_set(entity_id, "off")
    entry = await _loaded(hass, _topology(["kitchen", "hall"]))
    assert entry.runtime_data.presentation_snapshot(hass)["plant"]["health"] == "healthy"

    ar.async_get(hass).async_delete("hall")
    await hass.async_block_till_done()

    snapshot = entry.runtime_data.presentation_snapshot(hass)
    assert snapshot["plant"]["health"] == "degraded"
    (alert,) = [alert for alert in snapshot["alerts"] if alert["code"] == "zone_area_missing"]
    assert alert["severity"] == "error"
    assert alert["scope"] == GROUND.zone_id
    assert alert["name"] == "Ground floor"
    assert alert["message"] == (
        "Area Hall no longer exists in Home Assistant, so the zone gets no reading from it."
    )

    _area(hass, "Hall", temperature="sensor.hall_temperature")
    await hass.async_block_till_done()
    snapshot = entry.runtime_data.presentation_snapshot(hass)
    assert snapshot["plant"]["health"] == "healthy"
    assert not [alert for alert in snapshot["alerts"] if alert["code"].startswith("zone_area")]


async def test_every_area_problem_raises_an_alert(hass, home) -> None:
    entry = await _plant_with_every_area_problem(hass)

    snapshot = entry.runtime_data.presentation_snapshot(hass)
    alerts = {(alert["code"], alert["scope"]): alert for alert in snapshot["alerts"]}
    assert alerts[("zone_area_missing", GROUND.zone_id)]["severity"] == "error"
    assert alerts[("zone_without_temperature_source", GROUND.zone_id)]["severity"] == "error"
    self_feed = alerts[("zone_area_self_feed", GROUND.zone_id)]
    assert self_feed["severity"] == "warning"
    assert self_feed["message"] == (
        "Area Study names a sensor that Hydronicus provides, so the zone ignores it."
    )
    # The lost area sensor is an unresolved binding, which already marks the Plant.
    assert snapshot["plant"]["health"] == "unavailable"
    assert ("binding_unavailable", "plant") in alerts


async def test_a_missing_area_on_the_zone_card_is_flagged_with_its_last_name(hass, home) -> None:
    entry = await _loaded(hass, _topology(["hall", "kitchen", "attic"]))

    ar.async_get(hass).async_delete("kitchen")
    await hass.async_block_till_done()

    areas = _zone_snapshot(hass, entry, GROUND.zone_id)["areas"]
    assert [(area["id"], area["name"], area["missing"]) for area in areas] == [
        ("hall", "Hall", False),
        ("kitchen", "Kitchen", True),
        ("attic", "attic", True),
    ]
