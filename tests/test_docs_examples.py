"""The user documentation stays true to the plant file format, the code, and the UI strings.

Every plant file example in the documentation imports, the error paths and
messages the plant file reference quotes are the ones import reports, the
reference plant example matches the fixture the tests run, every bold UI label
is a label that ``strings.json`` or Home Assistant itself shows, and every
relative link resolves.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from custom_components.hydronicus.core import plant_file
from custom_components.hydronicus.core.plant_file import (
    PlantFileError,
    describe_path,
    parse_plant,
    read_plant_file,
    write_plant_file,
)
from custom_components.hydronicus.issues import IssueKind
from custom_components.hydronicus.sensor import STATUSES

REPOSITORY_ROOT = Path(__file__).parents[1]
DOCS = REPOSITORY_ROOT / "docs"
PLANT_FILE_REFERENCE = DOCS / "plant-file.md"
REFERENCE_EXAMPLE = DOCS / "examples" / "reference-plant.yaml"
TRIAL_KIT = DOCS / "examples" / "trial"
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures"
PACKAGE = REPOSITORY_ROOT / "custom_components" / "hydronicus"
STRINGS = PACKAGE / "strings.json"
PLANT_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

# The documents a user reads; the plans of earlier versions are history.
USER_DOCUMENTS = (
    "README.md",
    "CONTRIBUTING.md",
    "docs/configuration.md",
    "docs/development.md",
    "docs/entities.md",
    "docs/how-it-works.md",
    "docs/plant-file.md",
    "docs/safety.md",
    "docs/troubleshooting.md",
    "docs/upgrade-and-rollback.md",
)
HISTORICAL_PLANS = (
    "implementation-plan.md",
    "setup-redesign-plan.md",
    "zones-and-areas-plan.md",
    "ha-modernization-plan.md",
    "home-server-staging.md",
)
# Labels that Home Assistant or HACS show rather than strings.json.
EXTERNAL_LABELS = frozenset(
    {
        "Actions",
        "Add integration",
        "Area",
        "Area settings",
        "Areas, labels & zones",
        "Configure",
        "Custom repositories",
        "Delete",
        "Devices & services",
        "Download diagnostics",
        "Humidity sensor",
        "Hydronicus",
        "Integration",
        "Logs",
        "Reconfigure",
        "Repairs",
        "Settings",
        "Submit",
        "System",
        "Temperature sensor",
        "Tools",
    }
)
# Pick options that the flows label in code; the documents quote them in backticks.
CODE_LABELS = ("Add a pump", "Add a plant loop", "Add a loop")
# Words of the replaced model that no current document uses; the upgrade guide
# names them to map an old plant file onto the new one.
STALE_TERMS = (
    "Delivery Route",
    "Hydraulic Circuit",
    "Route Arbitration",
    "Any Demand",
    "source selector",
    "source_selector",
    "shared valve",
    "Lovelace",
    "--hydronicus-",
    "theming",
    "websocket",
    "presentation",
    "Dry run off",
    "npm",
)
_YAML_BLOCK = re.compile(r"^```yaml\n(.*?)^```", re.MULTILINE | re.DOTALL)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^#{1,6} (.+)$", re.MULTILINE)
_CODE_BLOCK = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
_TABLE_ROW = re.compile(r"^\| `([^`]+)` \| ([^|]+) \| ([^|]+) \|$", re.MULTILINE)


def _text(document: str | Path) -> str:
    return (REPOSITORY_ROOT / document).read_text(encoding="utf-8")


def _plant_file_blocks() -> list[tuple[str, str]]:
    """Every YAML block of the user documents that is a plant file, with an ID."""
    blocks = []
    for document in USER_DOCUMENTS:
        for index, block in enumerate(_YAML_BLOCK.findall(_text(document)), start=1):
            parsed = yaml.safe_load(block)
            if isinstance(parsed, dict) and "hydronicus" in parsed:
                blocks.append((f"{document}#{index}", block))
    return blocks


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _string_values(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for value in node.values():
            yield from _string_values(value)
    elif isinstance(node, str):
        yield node


def _anchor(heading: str) -> str:
    """Return the anchor GitHub gives a heading."""
    text = re.sub(r"[`*_]", "", heading).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for heading in _HEADING.findall(_CODE_BLOCK.sub("", text)):
        anchor = _anchor(heading)
        count = counts.get(anchor, 0)
        counts[anchor] = count + 1
        anchors.add(anchor if count == 0 else f"{anchor}-{count}")
    return anchors


# Plant file examples


def test_plant_file_reference_has_examples() -> None:
    """The reference shows the format through several complete examples."""
    blocks = _YAML_BLOCK.findall(_text(PLANT_FILE_REFERENCE))
    assert len(blocks) >= 5
    assert all("hydronicus" in yaml.safe_load(block) for block in blocks)


@pytest.mark.parametrize(
    ("name", "block"), _plant_file_blocks(), ids=[name for name, _ in _plant_file_blocks()]
)
def test_plant_file_examples_import(name: str, block: str) -> None:
    """Every plant file in the documentation is complete and valid, and round-trips."""
    plant = parse_plant(yaml.safe_load(block), new_id=lambda: PLANT_ID)
    assert read_plant_file(write_plant_file(plant)) == plant


@pytest.mark.parametrize("path", sorted((DOCS / "examples").rglob("*.yaml")), ids=str)
def test_example_plant_files_import(path: Path) -> None:
    """Every plant file in the examples imports; the trial package is not one."""
    document = _load(path)
    if "hydronicus" not in document:
        assert path.name == "package.yaml"
        return
    parse_plant(document, new_id=lambda: PLANT_ID)


@pytest.mark.parametrize(
    ("example", "fixture"),
    [
        (REFERENCE_EXAMPLE, FIXTURES / "reference_plant.yaml"),
        (TRIAL_KIT / "plant.yaml", FIXTURES / "trial_plant.yaml"),
        (TRIAL_KIT / "plant-areas.yaml", FIXTURES / "trial_plant_areas.yaml"),
    ],
    ids=lambda path: path.name,
)
def test_examples_match_the_tested_fixtures(example: Path, fixture: Path) -> None:
    """The documented examples describe exactly the Plants the tests run."""
    assert _load(example) == _load(fixture)


def test_the_reference_is_the_main_example() -> None:
    """The plant file reference shows the reference plant in full."""
    blocks = [yaml.safe_load(block) for block in _YAML_BLOCK.findall(_text(PLANT_FILE_REFERENCE))]
    assert _load(REFERENCE_EXAMPLE) in blocks


def test_the_reference_documents_every_key() -> None:
    """Every key the plant file reads is named in the reference."""
    text = _text(PLANT_FILE_REFERENCE)
    keys = {
        key
        for name in dir(plant_file)
        if name.endswith("_KEYS")
        for key in getattr(plant_file, name)
    }
    assert keys > {"min_flow_loops", "readiness", "proportional_band"}
    assert sorted(key for key in keys if f"`{key}`" not in text) == []


# Errors


def _reference() -> dict[str, Any]:
    return copy.deepcopy(_load(REFERENCE_EXAMPLE))


def _set(*keys: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def change(document: dict[str, Any]) -> None:
        node = document
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value

    return change


def _drop(*keys: str) -> Callable[[dict[str, Any]], None]:
    def change(document: dict[str, Any]) -> None:
        node = document
        for key in keys[:-1]:
            node = node[key]
        del node[keys[-1]]

    return change


def _rename_zone(document: dict[str, Any]) -> None:
    zones = document["zones"]
    zones["Living room"] = zones.pop("living_area")


def _misspell_pump(document: dict[str, Any]) -> None:
    loop = document["zones"]["living_area"]["loops"]["floor"]
    loop["pumps"] = loop.pop("pump")


def _cooling_zone_without_humidity(document: dict[str, Any]) -> None:
    zone = document["zones"]["living_area"]
    del zone["areas"]
    zone["temperature"] = ["sensor.living_area_temperature"]


_FLOOR = ("zones", "living_area", "loops", "floor")
# Each change of the reference plant makes one of the documented errors.
ERROR_CASES: dict[str, Callable[[dict[str, Any]], None]] = {
    "format_1": _set("hydronicus", value=1),
    "invalid_slug": _rename_zone,
    "unknown_key": _misspell_pump,
    "unknown_pump": _set(*_FLOOR, "pump", value="underfloor"),
    "cooling_without_reference": _set(*_FLOOR, "modes", value=["heat", "cool"]),
    "missing_min_flow_loops": _drop("pumps", "heat_pump", "min_flow_loops"),
    "min_flow_loop_of_another_pump": _set(
        "pumps", "heat_pump", "min_flow_loops", value=["living_area.floor"]
    ),
    "source_driven_without_source": _drop("source"),
    "switch_and_driven_by": _set("pumps", "floor", "driven_by", value="source"),
    "wrong_domain": _set("pumps", "floor", "switch", value="light.underfloor_heating_pump"),
    "output_bound_twice": _set(
        "zones",
        "bedroom_area",
        "loops",
        "ceiling",
        "valves",
        value=["switch.home_basement_ceiling_heating_valve"],
    ),
    "digital_without_temperature": _drop("zones", "bedroom_area", "areas"),
    "cooling_without_humidity": _cooling_zone_without_humidity,
    "missing_runs": _drop("loops", "towel_dryer", "runs"),
    "setpoint_strategy": _set("source", "strategy", value="setpoint"),
}


def _error(case: str) -> tuple[str, str, str]:
    document = _reference()
    ERROR_CASES[case](document)
    with pytest.raises(PlantFileError) as raised:
        parse_plant(document, new_id=lambda: PLANT_ID)
    error = raised.value
    return error.path, describe_path(document, error.path), error.message


def _documented_errors() -> dict[str, tuple[str, str]]:
    text = _text(PLANT_FILE_REFERENCE)
    section = text[text.index("## Errors") :]
    return {
        path: (words.strip(), message.strip())
        for path, words, message in _TABLE_ROW.findall(section)
    }


@pytest.mark.parametrize("case", ERROR_CASES)
def test_documented_errors_are_the_real_ones(case: str) -> None:
    """The reference quotes each error with the path, words, and message import reports."""
    path, words, message = _error(case)

    assert _documented_errors().get(path) == (words, message)


def test_every_documented_error_is_checked() -> None:
    """No row of the error table goes unchecked."""
    assert set(_documented_errors()) == {_error(case)[0] for case in ERROR_CASES}


# UI labels, entities, and Repairs


def test_bold_ui_labels_match_strings() -> None:
    """Every bold label in the user documents is shown by Hydronicus or Home Assistant."""
    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    labels = set(_string_values(strings)) | EXTERNAL_LABELS
    unknown: list[str] = []
    for document in USER_DOCUMENTS:
        for match in _BOLD.finditer(_text(document)):
            unknown.extend(
                f"{document}: {part!r}"
                for part in match.group(1).split(" > ")
                if part not in labels
            )
    assert unknown == []


def test_labels_built_in_code_exist() -> None:
    """The pick options the documents quote are the ones the flows offer."""
    flows = "".join(path.read_text(encoding="utf-8") for path in (PACKAGE / "flows").glob("*.py"))
    configuration = _text("docs/configuration.md")
    for label in CODE_LABELS:
        assert f'"{label}"' in flows
        assert f"`{label}`" in configuration


def test_every_entity_is_documented() -> None:
    """The entity reference names every entity and status the Plant publishes."""
    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    text = _text("docs/entities.md")
    names = [
        entity["name"]
        for platform in strings["entity"].values()
        for entity in platform.values()
        if "{" not in entity["name"]
    ]
    assert [name for name in names if f"**{name}**" not in text] == []
    for document in ("docs/entities.md", "docs/troubleshooting.md"):
        assert [state for state in STATUSES if f"`{state}`" not in _text(document)] == []


def test_every_repair_is_documented() -> None:
    """Troubleshooting lists every Repair by the key diagnostics show."""
    text = _text("docs/troubleshooting.md")
    assert [kind.value for kind in IssueKind if f"`{kind.value}`" not in text] == []


# Links and wording


@pytest.mark.parametrize("document", USER_DOCUMENTS)
def test_relative_links_resolve(document: str) -> None:
    """Every relative link points at a file that exists, and at a heading it has."""
    source = REPOSITORY_ROOT / document
    broken: list[str] = []
    for target in _LINK.findall(_CODE_BLOCK.sub("", source.read_text(encoding="utf-8"))):
        if re.match(r"[a-z]+:", target):
            continue
        path, _, anchor = target.partition("#")
        linked = (source.parent / path).resolve() if path else source
        if not linked.exists() or (
            anchor and anchor not in _anchors(linked.read_text(encoding="utf-8"))
        ):
            broken.append(target)
    assert broken == []


@pytest.mark.parametrize("document", USER_DOCUMENTS)
def test_current_documents_use_current_words(document: str) -> None:
    """No current document uses an em dash or a term the redesign replaced, or links to history."""
    text = _text(document)
    assert "\N{EM DASH}" not in text
    assert [plan for plan in HISTORICAL_PLANS if f"{plan})" in text] == []
    if document != "docs/upgrade-and-rollback.md":
        assert [term for term in STALE_TERMS if term.lower() in text.lower()] == []
