"""Enable the custom integration and provide mocked actuators for adapter tests."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from tests.integration.helpers import Actuators


@pytest.fixture(autouse=True)
def enable_hydronic_custom_integration(enable_custom_integrations: None) -> None:
    """Allow Home Assistant's loader to discover this custom integration."""


@pytest.fixture
def actuators(hass: HomeAssistant) -> Actuators:
    """Switch, valve, and select services that record every call and follow it."""
    return Actuators(hass)
