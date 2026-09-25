"""The user documentation stays true to the plant file format and the UI strings.

Every ``yaml`` example in the plant file reference must import, the trial kit's
plant files must import, and every bold UI label in the user documents must be a
label that ``strings.json`` or Home Assistant itself shows.

The user documents still describe the v0.1 plant file and flows until phase R6
of docs/redesign-plan.md rewrites them, so the checks of their content are
expected to fail until then; they are strict, so R6 must remove the marker.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from custom_components.hydronicus.core.plant_file import (
    PlantFileError,
    parse_plant,
    read_plant_file,
    write_plant_file,
)

REPOSITORY_ROOT = Path(__file__).parents[1]
PLANT_FILE_REFERENCE = REPOSITORY_ROOT / "docs" / "plant-file.md"
TRIAL_KIT = REPOSITORY_ROOT / "docs" / "examples" / "trial"
STRINGS = REPOSITORY_ROOT / "custom_components" / "hydronicus" / "strings.json"
PLANT_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
# Documents whose bold text names a UI label, and nothing else.
LABEL_DOCUMENTS = (
    "README.md",
    "docs/configuration.md",
    "docs/how-it-works.md",
    "docs/plant-file.md",
    "docs/troubleshooting.md",
    "docs/upgrade-and-rollback.md",
)
# Labels that Home Assistant, HACS, or the Lovelace card show rather than strings.json.
EXTERNAL_LABELS = frozenset(
    {
        "Actions",
        "Add integration",
        "Area",
        "Area settings",
        "Areas, labels & zones",
        "Configure",
        "Custom repositories",
        "Devices & services",
        "Diagnostic",
        "Download diagnostics",
        "Hydronicus",
        "Humidity sensor",
        "Hydronicus Plant",
        "Integration",
        "Integrations",
        "Logs",
        "Reconfigure",
        "Settings",
        "States",
        "Submit",
        "System",
        "Tools",
    }
)
_YAML_BLOCK = re.compile(r"^```yaml\n(.*?)^```", re.MULTILINE | re.DOTALL)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
# The user documents describe the v0.1 Plant until R6 rewrites them.
UNTIL_R6 = pytest.mark.xfail(
    strict=True, reason="R6 rewrites the user documentation for the redesigned Plant"
)


def _yaml_examples() -> list[tuple[str, str]]:
    text = PLANT_FILE_REFERENCE.read_text(encoding="utf-8")
    blocks = _YAML_BLOCK.findall(text)
    return [(f"example_{index}", block) for index, block in enumerate(blocks, start=1)]


def _string_values(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for value in node.values():
            yield from _string_values(value)
    elif isinstance(node, str):
        yield node


def test_plant_file_reference_has_examples() -> None:
    """The reference shows the format through several complete examples."""
    assert len(_yaml_examples()) >= 5


@UNTIL_R6
@pytest.mark.parametrize(
    ("name", "block"), _yaml_examples(), ids=[name for name, _ in _yaml_examples()]
)
def test_plant_file_reference_example_imports(name: str, block: str) -> None:
    """Every YAML example in the plant file reference is a complete, valid plant file."""
    plant = parse_plant(yaml.safe_load(block), new_id=lambda: PLANT_ID)
    assert read_plant_file(write_plant_file(plant)) == plant


@pytest.mark.parametrize("name", ["plant.yaml", "plant-areas.yaml"])
def test_trial_plant_files_import(name: str) -> None:
    """The trial kit's plant files are valid format 2 plant files."""
    plant = read_plant_file((TRIAL_KIT / name).read_text(encoding="utf-8"))

    assert plant.name == "Trial plant"
    assert [zone.title for zone in plant.zones] == ["Living room", "Bedroom"]


@UNTIL_R6
@pytest.mark.parametrize(
    ("document", "path"),
    [
        pytest.param(
            {"hydronicus": 1, "name": "Flat", "zones": {"Living room": {}}},
            "zones.Living room",
            id="invalid_slug",
        ),
        pytest.param(
            {
                "hydronicus": 1,
                "name": "Flat",
                "pumps": {"pump": "switch.pump"},
                "zones": {
                    "bedroom": {
                        "temperature_sensors": ["sensor.bedroom_temperature"],
                        "loops": {
                            "bedroom_loop": {"valves": ["switch.bedroom_valve"], "pump": "pumps"}
                        },
                    }
                },
            },
            "zones.bedroom.loops.bedroom_loop.pump",
            id="unknown_pump",
        ),
    ],
)
def test_plant_file_reference_error_paths(document: dict[str, Any], path: str) -> None:
    """The error paths the reference quotes are the ones import reports."""
    with pytest.raises(PlantFileError) as raised:
        parse_plant(document, new_id=lambda: PLANT_ID)

    assert raised.value.path == path
    assert f"`{path}`" in PLANT_FILE_REFERENCE.read_text(encoding="utf-8")


@UNTIL_R6
def test_bold_ui_labels_match_strings() -> None:
    """Every bold label in the user documents is shown by Hydronicus or Home Assistant."""
    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    labels = set(_string_values(strings)) | EXTERNAL_LABELS
    unknown: list[str] = []
    for document in LABEL_DOCUMENTS:
        text = (REPOSITORY_ROOT / document).read_text(encoding="utf-8")
        for match in _BOLD.finditer(text):
            unknown.extend(
                f"{document}: {part!r}"
                for part in match.group(1).split(" > ")
                if part not in labels
            )
    assert unknown == []
