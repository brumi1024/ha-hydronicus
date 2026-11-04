"""The Plant view over the websocket: one read, and a subscription that follows evaluations."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.hydronicus.presentation import VIEW_VERSION
from tests.integration.helpers import (
    REFERENCE_PLANT,
    async_advance,
    async_call,
    async_import,
    reference_world,
)


async def _home(hass: HomeAssistant) -> str:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    return entry.entry_id


async def test_a_read_returns_the_whole_plant_without_naming_an_entity(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, freezer: FrozenDateTimeFactory
) -> None:
    entry_id = await _home(hass)
    await async_advance(hass, freezer, 5)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "hydronicus/plant_view", "entry_id": entry_id})
    response = await client.receive_json()
    assert response["success"]
    view = response["result"]
    assert view["version"] == VIEW_VERSION
    assert view["plant"]["name"] == "Home"
    assert view["evaluated"] is True and view["live"] is False
    assert [zone["slug"] for zone in view["zones"]] == ["basement", "bedroom_area", "living_area"]
    assert {loop["ref"] for loop in view["loops"]} >= {"living_area.floor", "towel_dryer"}
    assert view["source"]["request"] == "switch.heat_pump_heat_request"
    assert all(len(path["steps"]) == 4 for path in view["paths"])
    assert "proposed" in view


async def test_an_unknown_plant_is_an_error(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    await _home(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "hydronicus/plant_view", "entry_id": "nope"})
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_found"


async def test_a_subscription_sends_each_evaluation_and_ends_at_unload(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, freezer: FrozenDateTimeFactory
) -> None:
    entry_id = await _home(hass)
    await async_advance(hass, freezer, 5)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "hydronicus/plant_view/subscribe", "entry_id": entry_id}
    )
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["type"] == "event" and first["event"]["requested_mode"] == "off"
    await async_call(hass, "select", "select_option", entity_id="select.home_mode", option="heat")
    await async_advance(hass, freezer, 5)
    events = []
    while True:
        event = await client.receive_json()
        events.append(event["event"])
        if event["event"].get("requested_mode") == "heat":
            break
    assert await hass.config_entries.async_unload(entry_id)
    await hass.async_block_till_done()
    while (event := await client.receive_json())["event"].get("unloaded") is not True:
        pass
    assert event["event"] == {"unloaded": True}
