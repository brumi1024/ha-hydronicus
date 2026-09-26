"""Paths of the format 2 plant files that the core tests share.

These are the same files docs/examples ships and docs/plant-file.md links to,
so the tests run exactly what a user would import.
"""

from __future__ import annotations

from pathlib import Path

DOCS_EXAMPLES = Path(__file__).parents[2] / "docs" / "examples"
# The reference plant, the same Plant as docs/examples/reference-plant.yaml.
REFERENCE_PLANT = DOCS_EXAMPLES / "reference-plant.yaml"
# The trial kit's plant file, without Home Assistant areas.
TRIAL_PLANT = DOCS_EXAMPLES / "trial" / "plant.yaml"
