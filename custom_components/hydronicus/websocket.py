"""The websocket commands a dashboard card uses to read a Plant's view.

``hydronicus/plant_view`` returns the view of one Plant once, and
``hydronicus/plant_view/subscribe`` sends it now and again after every
evaluation, until the client unsubscribes or the Plant unloads, which ends the
subscription with a last event whose ``unloaded`` is true. Both only read.
"""

from __future__ import annotations

from typing import Any, Final

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .presentation import plant_view
from .runtime import PlantRuntime

ATTR_ENTRY_ID: Final = "entry_id"


def _runtime(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> PlantRuntime | None:
    entry = hass.config_entries.async_get_entry(msg[ATTR_ENTRY_ID])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "No loaded Hydronicus Plant")
        return None
    runtime: PlantRuntime = entry.runtime_data
    return runtime


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/plant_view", vol.Required(ATTR_ENTRY_ID): str}
)
@callback
def _plant_view(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if (runtime := _runtime(hass, connection, msg)) is not None:
        connection.send_result(msg["id"], plant_view(runtime))


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/plant_view/subscribe", vol.Required(ATTR_ENTRY_ID): str}
)
@callback
def _subscribe_plant_view(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    runtime = _runtime(hass, connection, msg)
    if runtime is None:
        return
    subscribed = True

    @callback
    def send() -> None:
        if subscribed:
            connection.send_event(msg["id"], plant_view(runtime))

    remove = runtime.async_add_listener(send)

    @callback
    def unsubscribe() -> None:
        nonlocal subscribed
        if subscribed:
            subscribed = False
            remove()

    @callback
    def unloaded() -> None:
        if subscribed:
            connection.send_event(msg["id"], {"unloaded": True})
            unsubscribe()

    runtime.entry.async_on_unload(unloaded)
    connection.subscriptions[msg["id"]] = unsubscribe
    connection.send_result(msg["id"])
    send()


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    """Register the websocket commands."""
    websocket_api.async_register_command(hass, _plant_view)
    websocket_api.async_register_command(hass, _subscribe_plant_view)
