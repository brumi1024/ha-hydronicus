"""The Hydronicus config flow, with its zone subentry flow and Plant settings.

The flows live in the ``flows`` package; this module is where Home Assistant
finds the config flow.
"""

from __future__ import annotations

from .flows.plant import HydronicusConfigFlow

__all__ = ["HydronicusConfigFlow"]
