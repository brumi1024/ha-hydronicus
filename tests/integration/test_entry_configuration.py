"""Tests for parent-owned graph persistence and output authorization."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.config_flow import _async_persist_subentry_graph
from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_OUTPUT_AUTHORIZATION,
    CONF_SUBENTRY_OBJECTS,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SUBENTRY_TYPE_ZONE,
)
from custom_components.hydronicus.entry_configuration import (
    authorize_outputs,
    entry_data_with_subentry_draft,
    output_authorization,
    output_authorization_is_valid,
)

PLANT_ID = "00000000-0000-4000-8000-000000000001"
ZONE_ID = "00000000-0000-4000-8000-000000000002"
VALVE_ID = "00000000-0000-4000-8000-000000000003"
PUMP_ID = "00000000-0000-4000-8000-000000000004"
CIRCUIT_ID = "00000000-0000-4000-8000-000000000005"
ROUTE_ID = "00000000-0000-4000-8000-000000000006"
SOURCE_ID = "00000000-0000-4000-8000-000000000007"
ADDED_ZONE_ID = "00000000-0000-4000-8000-000000000008"
ADDED_ROUTE_ID = "00000000-0000-4000-8000-000000000009"


def _base_data() -> dict[str, object]:
    """Return one complete canonical parent graph."""
    return {
        "name": "Synthetic plant",
        "plant_id": PLANT_ID,
        "dry_run": True,
        "topology": {
            "zones": [
                {
                    "id": ZONE_ID,
                    "name": "Living room",
                    "thermostat": {
                        "kind": "hydronicus",
                        "initial_target_temperature": 21.0,
                    },
                    "temperature_sensor_metadata": [{"entity_id": "sensor.living_temperature"}],
                }
            ],
            "valves": [
                {
                    "id": VALVE_ID,
                    "name": "Floor valve",
                    "entity_id": "switch.floor_valve",
                }
            ],
            "pumps": [
                {
                    "id": PUMP_ID,
                    "name": "Floor pump",
                    "entity_id": "switch.floor_pump",
                }
            ],
            "circuits": [
                {
                    "id": CIRCUIT_ID,
                    "name": "Floor circuit",
                    "valve_ids": [VALVE_ID],
                    "pump_id": PUMP_ID,
                }
            ],
            "routes": [
                {
                    "id": ROUTE_ID,
                    "zone_id": ZONE_ID,
                    "circuit_id": CIRCUIT_ID,
                }
            ],
            "sources": [
                {
                    "id": SOURCE_ID,
                    "name": "Boiler",
                    "source_type": "external",
                    "source_demand_entity": "switch.boiler_demand",
                }
            ],
        },
        CONF_SUBENTRY_OBJECTS: {},
    }


def _added_zone_draft() -> dict[str, object]:
    """Return a complete UI draft for one additional Zone."""
    return {
        "id": ADDED_ZONE_ID,
        "name": "Office",
        "thermostat": {
            "kind": "hydronicus",
            "initial_target_temperature": 20.0,
        },
        "temperature_sensor_metadata": [{"entity_id": "sensor.office_temperature"}],
        "temperature_aggregation": "mean",
        "circuit_ids": [CIRCUIT_ID],
        "routes": [{"id": ADDED_ROUTE_ID, "circuit_id": CIRCUIT_ID}],
    }


def test_output_authorization_is_bound_to_the_exact_graph_and_outputs() -> None:
    """Any physical binding change invalidates the stored activation grant."""
    data = _base_data()
    authorization = output_authorization(data)

    assert authorization["outputs"] == [
        {"kind": "pump", "id": PUMP_ID, "entity_id": "switch.floor_pump"},
        {
            "kind": "source_demand",
            "id": SOURCE_ID,
            "entity_id": "switch.boiler_demand",
        },
        {"kind": "valve", "id": VALVE_ID, "entity_id": "switch.floor_valve"},
    ]

    active = authorize_outputs(data)
    assert active[CONF_DRY_RUN] is False
    assert output_authorization_is_valid(active)

    changed = deepcopy(active)
    changed["topology"]["valves"][0]["entity_id"] = "switch.other_valve"
    assert not output_authorization_is_valid(changed)


def test_graph_mutation_returns_to_dry_run_and_invalidates_authorization() -> None:
    """A valid graph edit cannot inherit authorization for the prior outputs."""
    active = authorize_outputs(_base_data())
    entry = SimpleNamespace(data=active, subentries={})

    updated = entry_data_with_subentry_draft(
        entry,
        SUBENTRY_TYPE_ZONE,
        _added_zone_draft(),
    )

    assert active[CONF_DRY_RUN] is False
    assert CONF_OUTPUT_AUTHORIZATION in active
    assert updated[CONF_DRY_RUN] is True
    assert CONF_OUTPUT_AUTHORIZATION not in updated
    assert updated[CONF_SUBENTRY_OBJECTS] == {ADDED_ZONE_ID: SUBENTRY_TYPE_ZONE}
    assert {zone["id"] for zone in updated["topology"]["zones"]} == {
        ZONE_ID,
        ADDED_ZONE_ID,
    }


async def test_active_graph_mutation_aborts_when_safe_shutdown_cannot_finish(hass) -> None:
    """A failed transition to Dry run leaves the parent graph byte-for-byte unchanged."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Synthetic plant",
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        data=authorize_outputs(_base_data()),
    )
    entry.add_to_hass(hass)
    runtime = SimpleNamespace(async_set_dry_run=AsyncMock(return_value=False))
    entry.runtime_data = runtime
    original = deepcopy(dict(entry.data))

    persisted = await _async_persist_subentry_graph(
        SimpleNamespace(hass=hass),
        entry,
        SUBENTRY_TYPE_ZONE,
        _added_zone_draft(),
    )

    assert persisted is False
    runtime.async_set_dry_run.assert_awaited_once_with(True, hass=hass)
    assert dict(entry.data) == original
