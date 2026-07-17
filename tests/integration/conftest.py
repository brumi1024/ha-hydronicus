"""Enable the custom integration for adapter integration tests."""

import pytest


@pytest.fixture(autouse=True)
def enable_hydronic_custom_integration(enable_custom_integrations) -> None:
    """Allow Home Assistant's loader to discover this custom integration."""
