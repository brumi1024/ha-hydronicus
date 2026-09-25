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
