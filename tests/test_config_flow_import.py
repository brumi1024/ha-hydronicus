"""Regression tests for config flow dependency imports."""

from __future__ import annotations

import ast
from pathlib import Path

COMPONENT_DIR = Path(__file__).parents[1] / "custom_components" / "hydronicus"
FLOW_MODULES = (COMPONENT_DIR / "config_flow.py", *sorted((COMPONENT_DIR / "flows").glob("*.py")))


def test_selector_is_imported_from_homeassistant_helpers() -> None:
    """The config flows must use Home Assistant's public selector module."""
    imports = {
        (node.module, imported.name)
        for path in FLOW_MODULES
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.ImportFrom)
        for imported in node.names
    }

    assert ("homeassistant.helpers", "selector") in imports
    assert ("homeassistant", "selector") not in imports
