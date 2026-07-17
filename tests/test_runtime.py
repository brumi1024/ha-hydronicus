"""Tests for the runtime state container."""

from __future__ import annotations

import sys
import types
import unittest
from importlib import import_module
from types import SimpleNamespace

homeassistant = types.ModuleType("homeassistant")
homeassistant_config_entries = types.ModuleType("homeassistant.config_entries")
homeassistant_core = types.ModuleType("homeassistant.core")


class _ConfigEntry:
    runtime_data: object | None = None


class _HomeAssistant:
    pass


homeassistant_config_entries.ConfigEntry = _ConfigEntry
homeassistant_core.HomeAssistant = _HomeAssistant
sys.modules.setdefault("homeassistant", homeassistant)
sys.modules.setdefault("homeassistant.config_entries", homeassistant_config_entries)
sys.modules.setdefault("homeassistant.core", homeassistant_core)

CONF_SHADOW_MODE = import_module("custom_components.hydronic_climate.const").CONF_SHADOW_MODE
HydronicRuntime = import_module("custom_components.hydronic_climate.runtime").HydronicRuntime


class RuntimeTests(unittest.TestCase):
    """Verify runtime data construction."""

    def test_defaults_to_shadow_mode(self) -> None:
        runtime = HydronicRuntime.from_entry(SimpleNamespace(data={}))

        self.assertEqual(runtime.plant_id, "plant")
        self.assertEqual(runtime.name, "Hydronic plant")
        self.assertTrue(runtime.shadow_mode)

    def test_reads_explicit_shadow_mode(self) -> None:
        runtime = HydronicRuntime.from_entry(SimpleNamespace(data={CONF_SHADOW_MODE: False}))

        self.assertFalse(runtime.shadow_mode)


if __name__ == "__main__":
    unittest.main()
