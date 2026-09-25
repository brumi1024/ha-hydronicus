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
from custom_components.hydronicus.issues import (
    Issue,
    IssueKind,
    invalid_plant,
    missing_area_sensor,
    missing_binding,
    output_not_responding,
    outputs_awaiting_confirmation,
    zone_area_issue,
)
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
    assert STRINGS["entity"]["sensor"]["status"]["state"].keys() == {
        "off",
        "idle",
        "heating",
        "cooling",
        "changing_over",
        "degraded",
    }


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
    used = placeholders(translation["title"]) | placeholders(translation["description"])
    assert used <= set(issue.placeholders)


def test_every_issue_kind_is_translated() -> None:
    assert set(STRINGS["issues"]) == {kind.value for kind in IssueKind}


def test_the_config_flow_errors_and_the_exceptions_are_translated() -> None:
    assert set(STRINGS["config"]["error"]) == {
        "invalid_plant_file",
        "own_entity",
        "output_bound_elsewhere",
    }
    assert set(STRINGS["exceptions"]) == {
        "invalid_plant",
        "plant_not_found",
        "invalid_target_temperature",
    }
    assert set(STRINGS["services"]) == {"export_plant"}
