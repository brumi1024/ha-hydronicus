"""The documentation stays true to the plant file format, the code, and the UI strings.

Every example plant file imports, the full example names every key the plant
file reads, every bold UI label is a label that ``strings.json`` or Home
Assistant itself shows, and every relative link resolves.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from custom_components.hydronicus.core import plant_file
from custom_components.hydronicus.core.plant_file import (
    parse_plant,
    read_plant_file,
    write_plant_file,
)

REPOSITORY_ROOT = Path(__file__).parents[1]
DOCS = REPOSITORY_ROOT / "docs"
EXAMPLES = DOCS / "examples"
FULL_EXAMPLE = EXAMPLES / "full-plant.yaml"
STRINGS = REPOSITORY_ROOT / "custom_components" / "hydronicus" / "strings.json"
PLANT_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

# The documents a reader sees.
DOCUMENTS = (
    "README.md",
    "CONTRIBUTING.md",
    "CONTEXT.md",
    "AGENTS.md",
    "docs/architecture.md",
    "adapters/README.md",
    "adapters/midea-shelly-modbus/README.md",
    ".github/pull_request_template.md",
)
# Labels that Home Assistant or HACS show rather than strings.json.
EXTERNAL_LABELS = frozenset(
    {
        "Add integration",
        "Custom repositories",
        "Devices & services",
        "Hydronicus",
        "Integration",
        "Settings",
    }
)
# Keys the plant file reads outside a ``_KEYS`` tuple.
EXTRA_KEYS = frozenset({"heat_target", "cool_target"})
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^#{1,6} (.+)$", re.MULTILINE)
_CODE_BLOCK = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)


def _text(document: str | Path) -> str:
    return (REPOSITORY_ROOT / document).read_text(encoding="utf-8")


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


@pytest.mark.parametrize("path", sorted(EXAMPLES.rglob("*.yaml")), ids=str)
def test_example_plant_files_import(path: Path) -> None:
    """Every example plant file imports and round-trips; the trial package is not one."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if "hydronicus" not in document:
        assert path.name == "package.yaml"
        return
    plant = parse_plant(document, new_id=lambda: PLANT_ID)
    assert read_plant_file(write_plant_file(plant)) == plant


def test_the_full_example_uses_every_key() -> None:
    """The full example names every key the plant file reads."""
    text = FULL_EXAMPLE.read_text(encoding="utf-8")
    keys = {
        key
        for name in dir(plant_file)
        if name.endswith("_KEYS")
        for key in getattr(plant_file, name)
    } | EXTRA_KEYS
    assert keys > {"min_flow_loops", "readiness", "max_age"}
    assert sorted(key for key in keys if not re.search(rf"\b{key}:", text)) == []


# UI labels, links, and wording


def test_bold_ui_labels_match_strings() -> None:
    """Every bold README label that is not a lead-in is shown by Hydronicus or Home Assistant."""
    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    labels = set(_string_values(strings)) | EXTERNAL_LABELS
    unknown: list[str] = []
    for document in ("README.md",):
        for match in _BOLD.finditer(_text(document)):
            label = match.group(1)
            if label.endswith(".") or label[0].islower():
                continue
            unknown.extend(
                f"{document}: {part!r}" for part in label.split(" > ") if part not in labels
            )
    assert unknown == []


def test_every_document_is_checked() -> None:
    """Every page under docs/ is one of the checked documents."""
    pages = {str(path.relative_to(REPOSITORY_ROOT)) for path in DOCS.glob("*.md")}
    assert sorted(pages - set(DOCUMENTS)) == []


@pytest.mark.parametrize("document", DOCUMENTS)
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
            anchor
            and linked.is_file()
            and anchor not in _anchors(linked.read_text(encoding="utf-8"))
        ):
            broken.append(target)
    assert broken == []


@pytest.mark.parametrize("document", DOCUMENTS)
def test_documents_use_no_em_dash(document: str) -> None:
    assert "\N{EM DASH}" not in _text(document)
