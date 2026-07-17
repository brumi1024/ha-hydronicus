"""Expose the pure core package without importing Home Assistant adapters."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

CORE_PATH = Path(__file__).parents[2] / "custom_components" / "hydronic_climate" / "core"
core_package = ModuleType("hydronic_climate_core")
core_package.__path__ = [str(CORE_PATH)]
sys.modules.setdefault("hydronic_climate_core", core_package)
