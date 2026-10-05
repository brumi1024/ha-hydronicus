"""Where a form shows a plant file problem, by the problem's path."""

from __future__ import annotations

import pytest

from custom_components.hydronicus.flows.forms import (
    LOOP_FIELDS,
    MODE_FIELDS,
    ZONE_FIELDS,
    problem_field,
)


@pytest.mark.parametrize(
    ("path", "prefix", "fields", "target"),
    [
        ("zones.study", "zones.study", ZONE_FIELDS, "temperature"),
        ("zones.study.humidity", "zones.study", ZONE_FIELDS, "humidity"),
        ("zones.study.areas.1", "zones.study", ZONE_FIELDS, "areas"),
        ("zones.study.loops.radiator.modes", "zones.study", ZONE_FIELDS, "base"),
        ("zones.studio.humidity", "zones.study", ZONE_FIELDS, "base"),
        (
            "zones.study.loops.radiator.valves.0",
            "zones.study.loops.radiator",
            LOOP_FIELDS,
            "valves",
        ),
        ("loops.shared.runs.with_zones.0", "loops.shared", LOOP_FIELDS, "with_zones"),
        ("zones.study.windows.1", "zones.study", ZONE_FIELDS, "windows"),
        ("zones.study.max_humidity", "zones.study", ZONE_FIELDS, "max_humidity"),
        ("loops.shared.surface_minimum", "loops.shared", LOOP_FIELDS, "surface_minimum"),
        ("source.mode.cool", "", MODE_FIELDS, "cool"),
        ("source.mode", "", MODE_FIELDS, "heat"),
        ("pumps.pump.driven_by", "", MODE_FIELDS, "base"),
        ("", "", MODE_FIELDS, "base"),
    ],
)
def test_a_problem_shows_on_the_field_its_path_belongs_to(
    path: str, prefix: str, fields: dict[str, str], target: str
) -> None:
    assert problem_field(path, prefix, fields) == target


def test_advanced_controls_survive_form_roundtrips_and_unshown_sections() -> None:
    from custom_components.hydronicus.core.plant_file import export_plant, parse_plant
    from custom_components.hydronicus.flows import documents
    from tests.core.test_plant_file import predictive_document

    document = export_plant(parse_plant(predictive_document()))
    values = documents.plant_values(document)
    edited = documents.with_plant(document, values)
    edited = documents.with_mode(edited, values["mode_select"], "Heat", "Cool")
    assert edited["source"]["supply"] == document["source"]["supply"]
    assert edited["source"]["running_sensor"] == document["source"]["running_sensor"]
    for slug in document["pumps"]:
        edited, _ = documents.with_pump(edited, slug, documents.pump_values(document, slug))
    edited, _ = documents.with_zone(
        edited, "basement", documents.zone_values(document, "basement"), "Basement"
    )
    assert parse_plant(edited) == parse_plant(document)
    for key in ("supply", "running_sensor", "weather"):
        values.pop(key)
    preserved = documents.with_plant(document, values)
    assert preserved["source"]["supply"] == document["source"]["supply"]
    assert preserved["weather"] == document["weather"]
    zone_values = documents.zone_values(document, "basement")
    for key in ("comfort", "presets", "cool_presets", "schedule", "learning"):
        zone_values.pop(key)
    preserved, _ = documents.with_zone(document, "basement", zone_values, "Basement")
    assert (
        preserved["zones"]["basement"]["thermostat"] == document["zones"]["basement"]["thermostat"]
    )


def test_optional_policy_sections_can_be_removed_explicitly() -> None:
    from custom_components.hydronicus.flows import documents
    from tests.core.test_plant_file import advanced_document

    document = advanced_document()
    values = documents.plant_values(document)
    values["supply"] = {}
    assert "supply" not in documents.with_plant(document, values)["source"]
    values = documents.zone_values(document, "basement")
    values["schedule"] = {}
    values["cool_presets"] = {}
    edited, _ = documents.with_zone(document, "basement", values, "Basement")
    digital = edited["zones"]["basement"]["thermostat"]["digital"]
    assert "schedule" not in digital
    assert "cool_presets" not in digital
    assert digital["target"] == 20 and digital["cool_target"] == 25


async def test_new_sections_accept_saved_values_and_have_complete_labels(hass) -> None:
    import json
    from pathlib import Path

    from homeassistant.data_entry_flow import section

    from custom_components.hydronicus.flows import documents, forms
    from tests.core.test_plant_file import predictive_document

    strings = json.loads(
        (Path(__file__).parents[1] / "custom_components/hydronicus/strings.json").read_text()
    )
    document = predictive_document()
    for schema, values, labels in (
        (
            forms.plant_schema(hass, documents.plant_values(document)),
            documents.plant_values(document),
            strings["config"]["step"]["plant"],
        ),
        (
            forms.pump_schema(
                hass,
                documents.pump_values(document, "heat_pump"),
                loops=documents.loop_refs(document, "heat_pump"),
            ),
            documents.pump_values(document, "heat_pump"),
            strings["config"]["step"]["pump"],
        ),
        (
            forms.zone_schema(hass, documents.zone_values(document, "basement")),
            documents.zone_values(document, "basement"),
            strings["config"]["step"]["zone"],
        ),
    ):
        submitted = {key: value for key, value in values.items() if value is not None}
        schema(submitted)
        for key, validator in schema.schema.items():
            name = str(key)
            if isinstance(validator, section):
                assert {str(field) for field in validator.schema.schema} <= set(
                    labels["sections"][name]["data"]
                )
            else:
                assert name in labels["data"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("source.supply.entity", "supply"),
        ("source.supply.outdoor_warm", "supply"),
        ("source.running_sensor", "running_sensor"),
        ("weather.entity", "weather"),
        ("weather.outdoor_sensor", "weather"),
        ("weather.max_age", "weather"),
    ],
)
def test_source_settings_problems_map_to_their_form(path: str, expected: str) -> None:
    from custom_components.hydronicus.flows.forms import PLANT_FIELDS

    assert problem_field(path, "", PLANT_FIELDS) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("target", "comfort"),
        ("cool_target", "comfort"),
        ("presets.eco", "presets"),
        ("cool_presets.eco", "cool_presets"),
        ("schedule.max_early_start", "schedule"),
        ("learning", "learning"),
        ("weather_aware", "learning"),
    ],
)
def test_zone_policy_problems_map_to_their_section(path: str, expected: str) -> None:
    assert (
        problem_field(f"zones.room.thermostat.digital.{path}", "zones.room", ZONE_FIELDS)
        == expected
    )


def test_learning_can_be_disabled_and_weather_removed_without_a_source() -> None:
    from custom_components.hydronicus.core.model import LearningMode
    from custom_components.hydronicus.core.plant_file import parse_plant
    from custom_components.hydronicus.flows import documents

    document = {
        "hydronicus": 2,
        "name": "Rooms",
        "weather": {"entity": "weather.home", "outdoor_sensor": "sensor.outdoor"},
        "zones": {
            "room": {
                "temperature": ["sensor.room"],
                "thermostat": {"digital": {"learning": "observe"}},
            }
        },
    }
    values = documents.plant_values(document)
    values["weather"] = {}
    edited = documents.with_plant(document, values)
    assert "weather" not in edited and "source" not in edited
    values = documents.zone_values(edited, "room")
    values["learning"] = {"mode": "off", "weather_aware": False}
    edited, _ = documents.with_zone(edited, "room", values, "Room")
    assert parse_plant(edited).zone("room").thermostat.learning is LearningMode.OFF
