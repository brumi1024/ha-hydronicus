"""Every translation key the integration uses exists, with the placeholders it gets."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from custom_components.hydronicus.areas import (
    AreaResolution,
    ZoneAreaProblem,
    ZoneAreaProblemKind,
)
from custom_components.hydronicus.core.plant_file import read_plant_file
from custom_components.hydronicus.flows.documents import NEW
from custom_components.hydronicus.flows.forms import pick_schema
from custom_components.hydronicus.issues import (
    FIXABLE,
    Issue,
    IssueKind,
    invalid_plant,
    missing_area_sensor,
    missing_binding,
    output_not_responding,
    outputs_awaiting_confirmation,
    zone_area_issue,
)
from custom_components.hydronicus.sensor import STATUSES
from tests.integration.helpers import REFERENCE_PLANT, SOURCE_REQUEST

COMPONENT = Path(__file__).parents[2] / "custom_components" / "hydronicus"
STRINGS = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
ICONS = json.loads((COMPONENT / "icons.json").read_text(encoding="utf-8"))
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
ENTITY_KEYS = {
    "binary_sensor": {"heating_demand", "cooling_demand", "loop_flowing", "source_requested"},
    "select": {"mode"},
    "sensor": {"status", "combined_temperature", "dew_point"},
    "switch": {"control"},
}


def placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER.findall(text))


def test_the_english_translation_is_a_copy_of_strings() -> None:
    assert (COMPONENT / "translations" / "en.json").read_bytes() == (
        COMPONENT / "strings.json"
    ).read_bytes()


def test_every_entity_translation_key_has_a_name_and_an_icon() -> None:
    assert {domain: set(keys) for domain, keys in STRINGS["entity"].items()} == ENTITY_KEYS
    assert {domain: set(keys) for domain, keys in ICONS["entity"].items()} == ENTITY_KEYS
    assert (
        STRINGS["entity"]["sensor"]["status"]["state"].keys()
        == ICONS["entity"]["sensor"]["status"]["state"].keys()
        == set(STATUSES)
    )


def _issues() -> list[Issue]:
    plant = read_plant_file(REFERENCE_PLANT)
    areas = AreaResolution()
    return [
        invalid_plant("Home", "pumps.heat_pump.min_flow_loops: needs a loop"),
        output_not_responding(plant, SOURCE_REQUEST),
        outputs_awaiting_confirmation(plant, ["switch.a", "switch.b"]),
        missing_binding(plant, "switch.a", "pumps.floor.switch"),
        missing_area_sensor(plant, "Kitchen", "sensor.kitchen"),
        *(
            zone_area_issue(plant, ZoneAreaProblem(kind, "basement", "workshop"), areas)
            for kind in ZoneAreaProblemKind
        ),
    ]


@pytest.mark.parametrize("issue", _issues(), ids=lambda issue: issue.kind.value)
def test_every_issue_has_a_translation_with_the_placeholders_it_gets(issue: Issue) -> None:
    translation: dict[str, Any] = STRINGS["issues"][issue.kind.value]
    texts = [translation["title"], translation.get("description", "")]
    for step in translation.get("fix_flow", {}).get("step", {}).values():
        texts.extend((step["title"], step.get("description", "")))
        texts.extend(step.get("data_description", {}).values())
    texts.extend(translation.get("fix_flow", {}).get("abort", {}).values())
    used = set().union(*(placeholders(text) for text in texts))
    assert used <= set(issue.placeholders)


def test_every_issue_kind_is_translated() -> None:
    assert set(STRINGS["issues"]) == {kind.value for kind in IssueKind}


def test_a_fixable_issue_has_a_fix_flow_and_an_informational_one_a_description() -> None:
    """Hassfest refuses an issue translation with both a description and a fix flow."""
    for kind in IssueKind:
        translation = STRINGS["issues"][kind.value]
        if kind in FIXABLE:
            assert set(translation) == {"title", "fix_flow"}, kind
        else:
            assert set(translation) == {"title", "description"}, kind


def test_the_zone_subentry_names_its_type_and_its_flows() -> None:
    zone = STRINGS["config_subentries"]["zone"]
    assert zone["entry_type"] == "Zone"
    assert set(zone["initiate_flow"]) == {"user", "reconfigure"}


def test_every_flow_error_is_translated_in_each_flow_that_raises_it() -> None:
    config_errors = set(STRINGS["config"]["error"])
    zone_errors = set(STRINGS["config_subentries"]["zone"]["error"])
    assert {
        "name_required",
        "mode_needs_request",
        "option_not_offered",
        "pump_required",
        "pump_in_use",
        "zones_required",
        "min_flow_loops_required",
        "zone_name_required",
        "areas_required",
        "invalid_value",
        "invalid_plant",
        "invalid_plant_file",
        "different_plant",
        "own_entity",
        "output_bound_elsewhere",
    } == config_errors
    assert {
        "zone_name_required",
        "pump_required",
        "invalid_value",
        "invalid_plant",
        "own_entity",
        "output_bound_elsewhere",
    } == zone_errors
    assert set(STRINGS["exceptions"]) == {
        "invalid_plant",
        "plant_not_found",
        "invalid_target_temperature",
        "unsupported_hvac_mode",
    }
    assert set(STRINGS["services"]) == {"export_plant"}


def test_every_form_field_has_a_label() -> None:
    """Each step that shows fields labels them, sections included."""
    flows = [
        STRINGS["config"]["step"],
        STRINGS["config_subentries"]["zone"]["step"],
        STRINGS["options"]["step"],
    ]
    flows.extend(
        issue["fix_flow"]["step"] for issue in STRINGS["issues"].values() if "fix_flow" in issue
    )
    for steps in flows:
        for step_id, step in steps.items():
            assert "title" in step, step_id
            for field in step.get("data_description", {}):
                assert field in step.get("data", {}), (step_id, field)
            for name, section in step.get("sections", {}).items():
                assert "name" in section, (step_id, name)
                for field in section.get("data_description", {}):
                    assert field in section["data"], (step_id, name, field)


def test_no_translation_uses_an_em_dash() -> None:
    assert "\u2014" not in (COMPONENT / "strings.json").read_text(encoding="utf-8")


def test_a_config_or_options_menu_title_takes_no_placeholder() -> None:
    """The frontend localizes the title of a config or options flow menu without placeholders.

    Home Assistant's frontend passes ``description_placeholders`` to a menu's
    description, and to a subentry flow menu's title, but not to the title of a
    config flow or options flow menu, which then shows a translation error.
    """
    for flow in (STRINGS["config"]["step"], STRINGS["options"]["step"]):
        for step_id, step in flow.items():
            if "menu_options" in step:
                assert not placeholders(step["title"]), step_id


# hassfest's rule for a translation key, which selector option keys must follow.
_TRANSLATION_KEY = re.compile(r"^(?!.+[_-]{2})(?![_-])[a-z0-9-_]+(?<![_-])$")


def test_every_selector_option_key_is_a_valid_translation_key() -> None:
    for name, selector in STRINGS["selector"].items():
        for option in selector["options"]:
            assert _TRANSLATION_KEY.match(option), (name, option)


def test_the_add_option_of_each_pick_form_is_translated() -> None:
    selectors = STRINGS["selector"]
    assert selectors["pump_pick"]["options"][NEW] == "Add a pump"
    assert selectors["plant_loop_pick"]["options"][NEW] == "Add a plant loop"
    assert selectors["loop_pick"]["options"][NEW] == "Add a loop"
    for key in ("pump_pick", "plant_loop_pick", "loop_pick"):
        (field,) = pick_schema(key, "pump", {"floor": "Floor"}).schema.values()
        config = field.serialize()["selector"]["select"]
        assert config["translation_key"] == key
        assert config["options"][-1] == {"value": NEW, "label": selectors[key]["options"][NEW]}


def test_every_menu_says_what_it_is_for() -> None:
    flows = [
        STRINGS["config"]["step"],
        STRINGS["config_subentries"]["zone"]["step"],
        STRINGS["options"]["step"],
    ]
    for steps in flows:
        for step_id, step in steps.items():
            if "menu_options" in step:
                assert step.get("description"), step_id


def test_the_zone_loop_forms_say_that_empty_valves_and_pump_add_no_loop() -> None:
    subentry_loop = STRINGS["config_subentries"]["zone"]["step"]["loop"]["description"]
    guided_loop = STRINGS["config"]["step"]["zone_loop"]["description"]
    assert "Leave Valves and Pump empty" in subentry_loop
    assert "Leave Valves and Pump empty" in guided_loop
