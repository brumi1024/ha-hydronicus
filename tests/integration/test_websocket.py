"""Lifecycle and permission tests for Hydronicus Plant WebSocket commands."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest
from homeassistant.exceptions import Unauthorized
from homeassistant.setup import async_setup_component
from homeassistant.util.hass_dict import HassKey
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import CONF_DRY_RUN, CONF_NAME, CONF_PLANT_ID, DOMAIN
from custom_components.hydronicus.presentation import PRESENTATION_SCHEMA_VERSION
from custom_components.hydronicus.websocket import (
    DATA_SUBSCRIPTIONS,
    WS_LIST_PLANTS,
    WS_SUBSCRIBE_PLANT,
    PlantSubscriptions,
    _filter_snapshot_for_user,
    _readable_entity_ids,
    ws_list_plants,
    ws_subscribe_plant,
)

PLANT_ID = "00000000-0000-4000-8000-000000000101"
ZONE_A = "00000000-0000-4000-8000-000000000102"
ZONE_B = "00000000-0000-4000-8000-000000000103"
VALVE_ID = "00000000-0000-4000-8000-000000000104"
PUMP_ID = "00000000-0000-4000-8000-000000000105"
CIRCUIT_ID = "00000000-0000-4000-8000-000000000106"
ROUTE_A = "00000000-0000-4000-8000-000000000107"
ROUTE_B = "00000000-0000-4000-8000-000000000108"


@dataclass
class _User:
    permissions: object | None = None


class _Connection:
    """Small ActiveConnection seam for command and cleanup tests."""

    def __init__(self, user: object) -> None:
        self.user = user
        self.results: list[tuple[int, object]] = []
        self.events: list[tuple[int, object]] = []
        self.errors: list[tuple[int, str, str]] = []
        self.subscriptions: dict[int, object] = {}

    def send_result(self, msg_id: int, result: object) -> None:
        self.results.append((msg_id, result))

    def send_event(self, msg_id: int, event: object) -> None:
        self.events.append((msg_id, event))

    def send_error(self, msg_id: int, code: str, message: str) -> None:
        self.errors.append((msg_id, code, message))


def _entry() -> MockConfigEntry:
    """Create one two-zone Plant with synthetic bindings."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="WebSocket Plant",
        data={
            CONF_NAME: "WebSocket Plant",
            CONF_PLANT_ID: PLANT_ID,
            CONF_DRY_RUN: True,
            "topology": {
                "zones": [
                    {
                        "id": ZONE_A,
                        "name": "Zone A",
                        "thermostat": {"kind": "hydronicus", "initial_target_temperature": 21.0},
                        "temperature_sensor_metadata": [{"entity_id": "sensor.ws_zone_a"}],
                    },
                    {
                        "id": ZONE_B,
                        "name": "Zone B",
                        "thermostat": {"kind": "hydronicus", "initial_target_temperature": 21.0},
                        "temperature_sensor_metadata": [{"entity_id": "sensor.ws_zone_b"}],
                    },
                ],
                "valves": [{"id": VALVE_ID, "name": "Valve", "entity_id": "switch.ws_valve"}],
                "pumps": [{"id": PUMP_ID, "name": "Pump", "entity_id": "switch.ws_pump"}],
                "circuits": [
                    {
                        "id": CIRCUIT_ID,
                        "name": "Circuit",
                        "valve_ids": [VALVE_ID],
                        "pump_id": PUMP_ID,
                    }
                ],
                "routes": [
                    {"id": ROUTE_A, "zone_id": ZONE_A, "circuit_id": CIRCUIT_ID},
                    {"id": ROUTE_B, "zone_id": ZONE_B, "circuit_id": CIRCUIT_ID},
                ],
            },
        },
    )


async def test_list_and_subscribe_are_permission_filtered_and_reconnect_on_reload(hass) -> None:
    """Plant discovery and snapshots follow visible Hydronicus-owned entities."""
    hass.states.async_set("sensor.ws_zone_a", "18")
    hass.states.async_set("sensor.ws_zone_b", "19")
    hass.states.async_set("switch.ws_valve", "off")
    hass.states.async_set("switch.ws_pump", "off")
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    all_connection = _Connection(_User())
    await ws_list_plants.__wrapped__(  # type: ignore[attr-defined]
        hass, all_connection, {"id": 1, "type": WS_LIST_PLANTS}
    )
    assert all_connection.results[0][1]["plants"][0]["id"] == PLANT_ID

    class _Permissions:
        def check_entity(self, entity_id: str, _permission: str) -> bool:
            return entity_id.endswith("zone_a_demand") or entity_id.endswith("safe_shutdown")

    filtered_connection = _Connection(_User(_Permissions()))
    await ws_subscribe_plant.__wrapped__(  # type: ignore[attr-defined]
        hass,
        filtered_connection,
        {"id": 2, "type": WS_SUBSCRIBE_PLANT, "plant_id": PLANT_ID},
    )
    initial = filtered_connection.results[0][1]["snapshot"]
    assert [zone["id"] for zone in initial["zones"]] == [ZONE_A]
    assert initial["zones"][0]["thermostat"]["control_entity_id"] is None
    assert initial["controls"]["requested_mode"] is None
    assert filtered_connection.subscriptions
    assert filtered_connection.events == [(2, {"snapshot": initial})]

    old_runtime = entry.runtime_data
    assert await hass.config_entries.async_reload(entry.entry_id)
    assert entry.runtime_data is not old_runtime
    assert any("snapshot" in event for _msg_id, event in filtered_connection.events)

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert filtered_connection.events[-1][1]["status"] == "unavailable"
    filtered_connection.subscriptions.pop(2)()
    assert not filtered_connection.subscriptions


async def test_connection_close_can_iterate_multiple_plant_subscriptions(hass) -> None:
    """Subscription cleanup must not mutate Core's map while Core iterates it."""
    hass.states.async_set("sensor.ws_zone_a", "18")
    hass.states.async_set("sensor.ws_zone_b", "19")
    hass.states.async_set("switch.ws_valve", "off")
    hass.states.async_set("switch.ws_pump", "off")
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    connection = _Connection(_User())

    for message_id in (2, 3):
        await ws_subscribe_plant.__wrapped__(  # type: ignore[attr-defined]
            hass,
            connection,
            {"id": message_id, "type": WS_SUBSCRIBE_PLANT, "plant_id": PLANT_ID},
        )

    for unsubscribe in connection.subscriptions.values():
        unsubscribe()
    connection.subscriptions.clear()

    assert connection.subscriptions == {}


async def test_permission_filter_hides_zone_equipment_but_keeps_plant_source_state(hass) -> None:
    """Zone equipment follows topology ACLs while shared source state stays Plant-wide."""
    hass.states.async_set("sensor.ws_zone_a", "18")
    hass.states.async_set("sensor.ws_zone_b", "19")
    hass.states.async_set("switch.ws_valve", "off")
    hass.states.async_set("switch.ws_pump", "off")
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    runtime = entry.runtime_data

    class _Permissions:
        def check_entity(self, entity_id: str, _permission: str) -> bool:
            return entity_id.endswith("zone_a_demand")

    snapshot = runtime.presentation_snapshot(hass)
    hidden_actuator_id = "00000000-0000-4000-8000-000000000199"
    snapshot["actuators"].append({"id": hidden_actuator_id, "active_consumers": []})
    snapshot["execution"]["boundary"]["forced_shadow_actuators"] = [
        VALVE_ID,
        hidden_actuator_id,
    ]
    snapshot["execution"]["operations"]["proposed"] = [
        {"actuator_id": VALVE_ID},
        {"actuator_id": hidden_actuator_id},
        {"actuator_id": "source:plant"},
    ]
    snapshot["sources"] = [{"id": "shared-source", "name": "Shared source"}]
    entities = runtime.presentation_entities(hass)
    allowed = _readable_entity_ids(_User(_Permissions()), entities)

    filtered = _filter_snapshot_for_user(snapshot, entities, allowed)

    assert filtered["execution"]["boundary"]["forced_shadow_actuators"] == [VALVE_ID]
    assert [
        operation["actuator_id"] for operation in filtered["execution"]["operations"]["proposed"]
    ] == [VALVE_ID, "source:plant"]
    assert filtered["sources"] == [{"id": "shared-source", "name": "Shared source"}]


async def test_subscribe_missing_plant_returns_defined_error(hass) -> None:
    """An unloaded or unknown Plant never leaks topology or raises a 500."""
    connection = _Connection(_User())
    await ws_subscribe_plant.__wrapped__(  # type: ignore[attr-defined]
        hass,
        connection,
        {"id": 1, "type": WS_SUBSCRIBE_PLANT, "plant_id": "missing"},
    )
    assert connection.errors[0][1] == "plant_not_found"


def _seed_states(hass) -> None:
    hass.states.async_set("sensor.ws_zone_a", "18")
    hass.states.async_set("sensor.ws_zone_b", "19")
    hass.states.async_set("switch.ws_valve", "off")
    hass.states.async_set("switch.ws_pump", "off")


async def _subscribe(hass, connection: _Connection, msg_id: int = 5) -> None:
    await ws_subscribe_plant.__wrapped__(  # type: ignore[attr-defined]
        hass,
        connection,
        {"id": msg_id, "type": WS_SUBSCRIBE_PLANT, "plant_id": PLANT_ID},
    )


async def test_subscription_to_a_plant_that_is_not_loaded_binds_when_it_loads(hass) -> None:
    """A stream opened while Home Assistant starts binds once the Plant is loaded."""
    _seed_states(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    entry = _entry()
    entry.add_to_hass(hass)
    connection = _Connection(_User())

    await _subscribe(hass, connection)

    assert connection.errors == []
    assert connection.results == [
        (
            5,
            {
                "schema_version": PRESENTATION_SCHEMA_VERSION,
                "snapshot": None,
                "status": "unavailable",
            },
        )
    ]
    assert connection.events == [(5, {"status": "unavailable", "plant_id": PLANT_ID})]

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    snapshots = [event["snapshot"] for _msg_id, event in connection.events if "snapshot" in event]
    assert snapshots
    assert snapshots[-1]["plant"]["id"] == PLANT_ID


async def test_loaded_state_signal_binds_streams_without_the_setup_hook(hass) -> None:
    """Binding follows the config entry state, not only the explicit setup hook."""
    _seed_states(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    entry = _entry()
    entry.add_to_hass(hass)
    connection = _Connection(_User())
    await _subscribe(hass, connection)

    with patch("custom_components.hydronicus.register_runtime"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert any("snapshot" in event for _msg_id, event in connection.events)
    subscription = hass.data[DATA_SUBSCRIPTIONS].for_plant(PLANT_ID)[0]
    assert subscription.runtime is entry.runtime_data


async def test_unknown_plant_is_not_found_even_when_other_plants_exist(hass) -> None:
    """Only a Plant without any config entry is terminally missing."""
    _seed_states(hass)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    connection = _Connection(_User())

    await ws_subscribe_plant.__wrapped__(  # type: ignore[attr-defined]
        hass,
        connection,
        {"id": 1, "type": WS_SUBSCRIBE_PLANT, "plant_id": "00000000-0000-4000-8000-00000000ffff"},
    )

    assert connection.errors[0][1] == "plant_not_found"
    assert connection.subscriptions == {}


async def test_pending_subscription_requires_a_readable_plant_entity(hass) -> None:
    """A stream for an unloaded Plant still follows entity permissions."""
    _seed_states(hass)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert await hass.config_entries.async_unload(entry.entry_id)

    class _DenyAll:
        def check_entity(self, _entity_id: str, _permission: str) -> bool:
            return False

    class _ZoneA:
        def check_entity(self, entity_id: str, _permission: str) -> bool:
            return entity_id.endswith("zone_a_demand")

    with pytest.raises(Unauthorized):
        await _subscribe(hass, _Connection(_User(_DenyAll())))

    allowed = _Connection(_User(_ZoneA()))
    await _subscribe(hass, allowed)
    assert allowed.events == [(5, {"status": "unavailable", "plant_id": PLANT_ID})]


async def test_revoked_access_sends_a_status_event_before_closing(hass) -> None:
    """A client learns why its stream stopped instead of waiting forever."""
    _seed_states(hass)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    class _Revocable:
        allowed = True

        def check_entity(self, _entity_id: str, _permission: str) -> bool:
            return self.allowed

    permissions = _Revocable()
    connection = _Connection(_User(permissions))
    await _subscribe(hass, connection)
    assert connection.subscriptions

    permissions.allowed = False
    hass.data[DATA_SUBSCRIPTIONS].for_plant(PLANT_ID)[0].publish()

    assert connection.events[-1] == (5, {"status": "unauthorized", "plant_id": PLANT_ID})
    assert connection.subscriptions == {}
    assert hass.data[DATA_SUBSCRIPTIONS].for_plant(PLANT_ID) == ()


async def test_removing_the_plant_ends_its_streams_as_not_found(hass) -> None:
    """A deleted Plant ends the stream with a terminal status."""
    _seed_states(hass)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    connection = _Connection(_User())
    await _subscribe(hass, connection)

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    statuses = [event.get("status") for _msg_id, event in connection.events]
    assert statuses[-2:] == ["unavailable", "plant_not_found"]
    assert connection.subscriptions == {}


async def test_plant_registry_uses_typed_keys_and_loaded_entries(hass) -> None:
    """X4: no string hass.data keys, and discovery follows loaded entries."""
    _seed_states(hass)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    assert DOMAIN not in hass.data
    assert isinstance(DATA_SUBSCRIPTIONS, HassKey)
    assert isinstance(hass.data[DATA_SUBSCRIPTIONS], PlantSubscriptions)

    async def _listed() -> list[str]:
        connection = _Connection(_User())
        await ws_list_plants.__wrapped__(  # type: ignore[attr-defined]
            hass, connection, {"id": 1, "type": WS_LIST_PLANTS}
        )
        return [plant["id"] for plant in connection.results[0][1]["plants"]]

    assert await _listed() == [PLANT_ID]
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await _listed() == []
