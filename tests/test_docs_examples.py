"""The user documentation stays true to the plant file format and the UI strings.

Every ``yaml`` example in the plant file reference must import, the trial kit's
plant file must import, and every bold UI label in the user documents must be a
label that ``strings.json`` or Home Assistant itself shows.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from custom_components.hydronicus.core.ownership import PlantOwnership
from custom_components.hydronicus.core.plant_document import (
    PlantDocumentError,
    export_plant_document,
    import_plant_document,
)

REPOSITORY_ROOT = Path(__file__).parents[1]
PLANT_FILE_REFERENCE = REPOSITORY_ROOT / "docs" / "plant-file.md"
TRIAL_PLANT = REPOSITORY_ROOT / "docs" / "examples" / "trial" / "plant.yaml"
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
        "Configure",
        "Custom repositories",
        "Devices & services",
        "Download diagnostics",
        "Hydronicus",
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


def _yaml_examples() -> list[tuple[str, str]]:
    text = PLANT_FILE_REFERENCE.read_text(encoding="utf-8")
    blocks = _YAML_BLOCK.findall(text)
    return [(f"example_{index}", block) for index, block in enumerate(blocks, start=1)]


def _by_id(topology: dict[str, Any]) -> dict[str, Any]:
    """Key every stored collection by object id, since export orders them by slug."""
    return {
        key: {record["id"]: record for record in value} if isinstance(value, list) else value
        for key, value in topology.items()
    }


def _string_values(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for value in node.values():
            yield from _string_values(value)
    elif isinstance(node, str):
        yield node


def test_plant_file_reference_has_examples() -> None:
    """The reference shows the format through several complete examples."""
    assert len(_yaml_examples()) >= 5


@pytest.mark.parametrize(
    ("name", "block"), _yaml_examples(), ids=[name for name, _ in _yaml_examples()]
)
def test_plant_file_reference_example_imports(name: str, block: str) -> None:
    """Every YAML example in the plant file reference is a complete, valid plant file."""
    document = yaml.safe_load(block)
    imported = import_plant_document(document, plant_id=PLANT_ID)

    exported = export_plant_document(
        name=imported.name,
        plant_id=imported.plant_id,
        topology=imported.topology,
        ownership=imported.ownership,
    )
    again = import_plant_document(exported, plant_id=PLANT_ID)
    assert _by_id(again.topology) == _by_id(imported.topology)
    assert again.ownership == imported.ownership


def test_trial_plant_file_imports() -> None:
    """The trial kit's plant file is valid."""
    document = yaml.safe_load(TRIAL_PLANT.read_text(encoding="utf-8"))
    imported = import_plant_document(document, plant_id=PLANT_ID)

    assert imported.name == "Trial plant"
    assert {zone["name"] for zone in imported.topology["zones"]} == {"Living room", "Bedroom"}


@pytest.mark.parametrize(
    ("document", "path"),
    [
        pytest.param(
            {"hydronicus": 1, "name": "Flat", "rooms": {"Living room": {}}},
            "rooms.Living room",
            id="invalid_slug",
        ),
        pytest.param(
            {
                "hydronicus": 1,
                "name": "Flat",
                "pumps": {"pump": "switch.pump"},
                "rooms": {
                    "bedroom": {
                        "temperature_sensors": ["sensor.bedroom_temperature"],
                        "loops": {
                            "bedroom_loop": {"valves": ["switch.bedroom_valve"], "pump": "pumps"}
                        },
                    }
                },
            },
            "rooms.bedroom.loops.bedroom_loop.pump",
            id="unknown_pump",
        ),
    ],
)
def test_plant_file_reference_error_paths(document: dict[str, Any], path: str) -> None:
    """The error paths the reference quotes are the ones import reports."""
    with pytest.raises(PlantDocumentError) as raised:
        import_plant_document(document, plant_id=PLANT_ID)

    assert raised.value.path == path
    assert f"`{path}`" in PLANT_FILE_REFERENCE.read_text(encoding="utf-8")


def test_export_slugs_match_the_reference() -> None:
    """Export slugs fold accents, prefix leading digits, and number duplicates as documented."""
    pump = {"id": "00000000-0000-4000-8000-000000000010", "name": "2nd floor pump"}
    valves = [
        {"id": f"00000000-0000-4000-8000-00000000002{index}", "name": name}
        for index, name in enumerate(("Ärkély valve", "Ärkély valve", "!!!"))
    ]
    circuit = {
        "id": "00000000-0000-4000-8000-000000000030",
        "name": "Ärkély loop",
        "valve_ids": [valve["id"] for valve in valves],
        "pump_id": pump["id"],
    }
    zone = {
        "id": "00000000-0000-4000-8000-000000000040",
        "name": "Ärkély",
        "thermostat": {"kind": "external_climate", "entity_id": "climate.arkely"},
    }
    topology = {
        "zones": [zone],
        "valves": [
            {**valve, "entity_id": f"switch.valve_{index}"} for index, valve in enumerate(valves)
        ],
        "pumps": [{**pump, "entity_id": "switch.pump"}],
        "circuits": [circuit],
        "routes": [
            {
                "id": "00000000-0000-4000-8000-000000000050",
                "zone_id": zone["id"],
                "circuit_id": circuit["id"],
            }
        ],
    }
    document = export_plant_document(
        name="Plant",
        plant_id=PLANT_ID,
        topology=topology,
        ownership=PlantOwnership(room_objects={}),
    )

    assert list(document["pumps"]) == ["pump_2nd_floor_pump"]
    assert list(document["valves"]) == ["arkely_valve", "arkely_valve_2", "valve"]
    assert list(document["loops"]) == ["arkely_loop"]
    assert list(document["rooms"]) == ["arkely"]
    reference = PLANT_FILE_REFERENCE.read_text(encoding="utf-8")
    for slug in ("arkely", "pump_2nd_floor_pump", "arkely_valve_2"):
        assert f"`{slug}`" in reference


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
