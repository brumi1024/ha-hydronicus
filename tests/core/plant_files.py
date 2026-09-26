"""Paths of the format 2 plant files that the core tests share."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parents[1] / "fixtures"
# The reference plant of docs/redesign-plan.md, contract K1, verbatim.
REFERENCE_PLANT = FIXTURES / "reference_plant.yaml"
# The trial kit of docs/examples/trial, converted to format 2.
TRIAL_PLANTS = {
    FIXTURES / "trial_plant.yaml": Path(__file__).parents[2] / "docs/examples/trial/plant.yaml",
    FIXTURES / "trial_plant_areas.yaml": (
        Path(__file__).parents[2] / "docs/examples/trial/plant-areas.yaml"
    ),
}
