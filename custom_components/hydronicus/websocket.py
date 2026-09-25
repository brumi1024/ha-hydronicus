"""Read-only Plant presentation WebSocket commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    ConfigEntry,
    ConfigEntryChange,
    ConfigEntryState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util.hass_dict import HassKey

from .const import CONF_PLANT_ID, DOMAIN
from .presentation import PRESENTATION_SCHEMA_VERSION, build_plant_summary

if TYPE_CHECKING:
    from .runtime import HydronicRuntime

WS_LIST_PLANTS = "hydronicus/list_plants"
WS_SUBSCRIBE_PLANT = "hydronicus/subscribe_plant"

# Status events on a Plant stream. A card treats the last two as terminal.
STATUS_UNAVAILABLE = "unavailable"
STATUS_UNAUTHORIZED = "unauthorized"
STATUS_PLANT_NOT_FOUND = "plant_not_found"


class PlantSubscriptions:
    """Every open Plant stream, bound to its Plant's runtime while it is loaded."""

    def __init__(self) -> None:
        self._subscriptions: list[PlantSubscription] = []

    def add(self, subscription: PlantSubscription) -> None:
        self._subscriptions.append(subscription)

    def discard(self, subscription: PlantSubscription) -> None:
        if subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

    def for_plant(self, plant_id: str) -> tuple[PlantSubscription, ...]:
        return tuple(item for item in self._subscriptions if item.plant_id == plant_id)

    def __len__(self) -> int:
        return len(self._subscriptions)

    @callback
    def bind_plant(self, plant_id: str, runtime: HydronicRuntime) -> None:
        """Bind every stream of a Plant to its runtime and publish a snapshot."""
        for subscription in self.for_plant(plant_id):
            if subscription.runtime is not runtime:
                subscription.bind(runtime)
                subscription.publish()

    @callback
    def release_plant(self, plant_id: str) -> None:
        """Tell every bound stream of a Plant that it became unavailable."""
        for subscription in self.for_plant(plant_id):
            if subscription.runtime is not None:
                subscription.bind(None)
                subscription.send_status(STATUS_UNAVAILABLE)

    @callback
    def remove_plant(self, plant_id: str) -> None:
        """End every stream of a Plant whose config entry was removed."""
        for subscription in self.for_plant(plant_id):
            subscription.revoke(STATUS_PLANT_NOT_FOUND)


DATA_SUBSCRIPTIONS: HassKey[PlantSubscriptions] = HassKey(f"{DOMAIN}_plant_subscriptions")


@dataclass(slots=True, eq=False)
class PlantSubscription:
    """One connection's Plant stream; it outlives runtime reloads."""

    hass: HomeAssistant
    connection: websocket_api.ActiveConnection
    msg_id: int
    plant_id: str
    runtime: HydronicRuntime | None = None
    _remove_runtime_listener: Callable[[], None] | None = field(default=None, repr=False)

    def bind(self, runtime: HydronicRuntime | None) -> None:
        """Follow one runtime, or none while the Plant is not loaded."""
        self.unbind()
        self.runtime = runtime
        if runtime is not None:
            self._remove_runtime_listener = runtime.async_add_listener(self.publish)

    def send_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Send an already-built snapshot on the subscription event channel."""
        self.connection.send_event(self.msg_id, {"snapshot": snapshot})

    def send_status(self, status: str) -> None:
        """Send a stream status such as unavailable or unauthorized."""
        self.connection.send_event(self.msg_id, {"status": status, "plant_id": self.plant_id})

    @callback
    def publish(self) -> None:
        """Publish one meaningful runtime update to the subscribed user."""
        runtime = self.runtime
        if runtime is None:
            self.send_status(STATUS_UNAVAILABLE)
            return
        entities = runtime.presentation_entities(self.hass)
        allowed = _readable_entity_ids(self.connection.user, entities)
        if not _has_read_access(allowed):
            self.revoke(STATUS_UNAUTHORIZED)
            return
        snapshot = _filter_snapshot_for_user(
            runtime.presentation_snapshot(self.hass, control_entities=entities),
            entities,
            allowed,
        )
        self.send_snapshot(snapshot)

    @callback
    def unbind(self) -> None:
        """Remove the runtime listener without closing the WebSocket stream."""
        if self._remove_runtime_listener is not None:
            self._remove_runtime_listener()
            self._remove_runtime_listener = None
        self.runtime = None

    @callback
    def revoke(self, status: str) -> None:
        """Tell the client why, then end the stream on the server side."""
        self.send_status(status)
        self.connection.subscriptions.pop(self.msg_id, None)
        self.close()

    @callback
    def close(self) -> None:
        """Detach without mutating Core's subscription map during connection close."""
        self.unbind()
        subscriptions = self.hass.data.get(DATA_SUBSCRIPTIONS)
        if subscriptions is not None:
            subscriptions.discard(self)


async def async_setup(hass: HomeAssistant, _config: Any) -> bool:
    """Register read-only Plant presentation commands once per Home Assistant."""
    if DATA_SUBSCRIPTIONS not in hass.data:
        hass.data[DATA_SUBSCRIPTIONS] = PlantSubscriptions()

        @callback
        def _config_entry_changed(change: ConfigEntryChange, entry: ConfigEntry) -> None:
            _async_config_entry_changed(hass, change, entry)

        async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, _config_entry_changed)
    websocket_api.async_register_command(hass, ws_list_plants)
    websocket_api.async_register_command(hass, ws_subscribe_plant)
    return True


@callback
def _async_config_entry_changed(
    hass: HomeAssistant, change: ConfigEntryChange, entry: ConfigEntry
) -> None:
    """Bind streams when a Plant finishes loading, and release them otherwise."""
    if entry.domain != DOMAIN:
        return
    subscriptions = hass.data[DATA_SUBSCRIPTIONS]
    plant_id = _entry_plant_id(entry)
    if change is ConfigEntryChange.REMOVED:
        subscriptions.remove_plant(plant_id)
    elif entry.state is ConfigEntryState.LOADED:
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None:
            subscriptions.bind_plant(runtime.plant_id, runtime)
    else:
        subscriptions.release_plant(plant_id)


@websocket_api.websocket_command({vol.Required("type"): WS_LIST_PLANTS})
@websocket_api.async_response
async def ws_list_plants(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List only Plants for which the user can read Hydronicus-owned entities."""
    plants = []
    for plant_id, runtime in sorted(_loaded_runtimes(hass).items()):
        allowed = _readable_entity_ids(connection.user, runtime.presentation_entities(hass))
        if not _has_read_access(allowed):
            continue
        presentation = build_plant_summary(runtime)
        plants.append(
            {
                "id": plant_id,
                "name": runtime.name,
                "status": presentation["status"],
                "health": presentation["health"],
                "requested_mode": presentation["requested_mode"],
                "active_mode": presentation["active_mode"],
            }
        )
    connection.send_result(
        msg["id"], {"schema_version": PRESENTATION_SCHEMA_VERSION, "plants": plants}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SUBSCRIBE_PLANT,
        vol.Required("plant_id"): vol.Coerce(str),
    }
)
@websocket_api.async_response
async def ws_subscribe_plant(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Stream a Plant: an initial snapshot or status, then meaningful updates.

    A Plant whose config entry exists but is not loaded yet, for example
    while Home Assistant starts or the entry reloads, is accepted. The stream
    reports it unavailable and binds when the Plant finishes loading.
    """
    plant_id = msg["plant_id"]
    runtime = _loaded_runtimes(hass).get(plant_id)
    snapshot: dict[str, Any] | None = None
    if runtime is None:
        entry = _plant_entry(hass, plant_id)
        if entry is None:
            connection.send_error(
                msg["id"], STATUS_PLANT_NOT_FOUND, "Hydronicus Plant does not exist."
            )
            return
        if not _may_read_unloaded_plant(hass, connection.user, entry):
            raise Unauthorized()
    else:
        entities = runtime.presentation_entities(hass)
        allowed = _readable_entity_ids(connection.user, entities)
        if not _has_read_access(allowed):
            raise Unauthorized()
        snapshot = _filter_snapshot_for_user(
            runtime.presentation_snapshot(hass, control_entities=entities),
            entities,
            allowed,
        )

    existing = connection.subscriptions.pop(msg["id"], None)
    if existing is not None:
        existing()
    subscription = PlantSubscription(hass, connection, msg["id"], plant_id)
    hass.data[DATA_SUBSCRIPTIONS].add(subscription)
    connection.subscriptions[msg["id"]] = subscription.close
    result: dict[str, Any] = {"schema_version": PRESENTATION_SCHEMA_VERSION, "snapshot": snapshot}
    if snapshot is None:
        result["status"] = STATUS_UNAVAILABLE
    connection.send_result(msg["id"], result)
    # The HA subscribeMessage helper delivers subsequent send_event payloads
    # to the card callback, while the command result resolves its promise.
    # Publish the initial state on the event channel as well, so the card
    # always learns the stream state from its callback.
    if snapshot is None:
        subscription.send_status(STATUS_UNAVAILABLE)
        return
    subscription.bind(runtime)
    subscription.send_snapshot(snapshot)


def register_runtime(hass: HomeAssistant, runtime: HydronicRuntime) -> None:
    """Bind a Plant's streams to its runtime as soon as setup has started it.

    The config entry state signal binds them as well once the entry is
    loaded; binding is idempotent, so either path alone is sufficient.
    """
    if (subscriptions := hass.data.get(DATA_SUBSCRIPTIONS)) is not None:
        subscriptions.bind_plant(runtime.plant_id, runtime)


def unregister_runtime(hass: HomeAssistant, plant_id: str) -> None:
    """Mark a Plant's streams unavailable before its runtime stops."""
    if (subscriptions := hass.data.get(DATA_SUBSCRIPTIONS)) is not None:
        subscriptions.release_plant(plant_id)


def _entry_plant_id(entry: ConfigEntry) -> str:
    """Return the Plant UUID the same way the runtime derives it."""
    return str(entry.data.get(CONF_PLANT_ID, entry.entry_id))


def _loaded_runtimes(hass: HomeAssistant) -> dict[str, HydronicRuntime]:
    """Map Plant UUIDs to the runtimes of loaded config entries."""
    runtimes: dict[str, HydronicRuntime] = {}
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None:
            runtimes[runtime.plant_id] = runtime
    return runtimes


def _plant_entry(hass: HomeAssistant, plant_id: str) -> ConfigEntry | None:
    """Find the config entry of a Plant, whether or not it is loaded."""
    for entry in hass.config_entries.async_entries(DOMAIN, include_ignore=False):
        if _entry_plant_id(entry) == plant_id:
            return entry
    return None


def _may_read_unloaded_plant(hass: HomeAssistant, user: Any, entry: ConfigEntry) -> bool:
    """Allow a pending stream when the user can read any entity of the Plant.

    A pending stream carries no Plant data. Once the Plant loads, the stream
    applies the exact presentation permission check, and revokes itself with
    an unauthorized status when that check fails.
    """
    permissions = getattr(user, "permissions", None)
    checker = getattr(permissions, "check_entity", None)
    if checker is None or getattr(user, "is_admin", False):
        return True
    registry = er.async_get(hass)
    return any(
        checker(registry_entry.entity_id, POLICY_READ)
        for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
    )


def _readable_entity_ids(user: Any, entities: dict[str, str]) -> frozenset[str] | None:
    """Resolve readable entity IDs once, or None for test and legacy seams."""
    permissions = getattr(user, "permissions", None)
    checker = getattr(permissions, "check_entity", None)
    if checker is None:
        return None
    return frozenset(
        entity_id for entity_id in set(entities.values()) if checker(entity_id, POLICY_READ)
    )


def _has_read_access(allowed: frozenset[str] | None) -> bool:
    """Require one readable Plant entity when Home Assistant exposes ACLs."""
    return allowed is None or bool(allowed)


def _filter_snapshot_for_user(
    snapshot: dict[str, Any],
    entities: dict[str, str],
    allowed: frozenset[str] | None,
) -> dict[str, Any]:
    """Remove Hydronicus-owned zones and controls hidden by entity ACLs."""
    if allowed is None:
        return snapshot
    controls = dict(snapshot["controls"])
    for key, entity_id in tuple(controls.items()):
        if entity_id is not None and entity_id not in allowed:
            controls[key] = None
    zones = []
    for zone in snapshot["zones"]:
        zone_id = zone["id"]
        presentation_entity = entities.get(f"zone:{zone_id}")
        if presentation_entity is None or presentation_entity not in allowed:
            continue
        visible_zone = dict(zone)
        thermostat = dict(visible_zone["thermostat"])
        control_entity = thermostat.get("control_entity_id")
        if control_entity is not None and control_entity not in allowed:
            thermostat["control_entity_id"] = None
        visible_zone["thermostat"] = thermostat
        zones.append(visible_zone)
    visible_zone_ids = {zone["id"] for zone in zones}
    filtered = dict(snapshot)
    filtered["controls"] = controls
    filtered["zones"] = zones
    filtered["delivery_paths"] = [
        path for path in snapshot["delivery_paths"] if path["zone_id"] in visible_zone_ids
    ]
    topology = dict(snapshot["topology"])
    topology["routes"] = [
        route for route in topology["routes"] if route["zone_id"] in visible_zone_ids
    ]
    visible_circuit_ids = {route["circuit_id"] for route in topology["routes"]}
    topology["circuits"] = [
        circuit for circuit in topology["circuits"] if circuit["id"] in visible_circuit_ids
    ]
    visible_route_ids = {route["id"] for route in topology["routes"]}
    topology["circuits"] = [
        {
            **circuit,
            "route_ids": [
                route_id for route_id in circuit["route_ids"] if route_id in visible_route_ids
            ],
        }
        for circuit in topology["circuits"]
    ]
    topology["coupling_groups"] = [
        {
            **group,
            "zone_ids": [zone_id for zone_id in group["zone_ids"] if zone_id in visible_zone_ids],
            "circuit_ids": [
                circuit_id
                for circuit_id in group["circuit_ids"]
                if circuit_id in visible_circuit_ids
            ],
        }
        for group in topology["coupling_groups"]
        if set(group["zone_ids"]) & visible_zone_ids
    ]
    visible_actuator_ids = {
        valve_id for circuit in topology["circuits"] for valve_id in circuit["valve_ids"]
    }
    visible_actuator_ids.update(circuit["pump_id"] for circuit in topology["circuits"])
    plant_actuator_ids = {actuator["id"] for actuator in snapshot["actuators"]}
    filtered["actuators"] = [
        {
            **actuator,
            "active_consumers": [
                consumer
                for consumer in actuator["active_consumers"]
                if consumer["id"] in visible_circuit_ids
            ],
        }
        for actuator in snapshot["actuators"]
        if actuator["id"] in visible_actuator_ids
    ]
    execution = dict(snapshot["execution"])
    execution["operations"] = {
        result: [
            operation
            for operation in operations
            # Sources serve the shared Plant, so source and selector operations
            # remain visible once the user can read any Plant presentation entity.
            if operation["actuator_id"] not in plant_actuator_ids
            or operation["actuator_id"] in visible_actuator_ids
        ]
        for result, operations in execution["operations"].items()
    }
    filtered["execution"] = execution
    topology["active_consumer_sets"] = {
        kind: [
            {
                **entry,
                "consumers": [
                    consumer
                    for consumer in entry["consumers"]
                    if consumer["id"] in visible_circuit_ids
                ],
            }
            for entry in topology["active_consumer_sets"][kind]
            if entry["actuator_id"] in visible_actuator_ids
        ]
        for kind in ("valves", "pumps")
    }
    summary = dict(topology["summary"])
    summary.update(
        {
            "zones": len(visible_zone_ids),
            "circuits": len(topology["circuits"]),
            "routes": len(topology["routes"]),
            "valves": len(
                {valve_id for circuit in topology["circuits"] for valve_id in circuit["valve_ids"]}
            ),
            "pumps": len({circuit["pump_id"] for circuit in topology["circuits"]}),
        }
    )
    topology["summary"] = summary
    filtered["topology"] = topology
    filtered["alerts"] = [
        alert
        for alert in snapshot["alerts"]
        if alert["scope"] == "plant"
        or alert["scope"] in visible_zone_ids
        or alert["scope"] in visible_circuit_ids
        or alert["scope"] in visible_actuator_ids
    ]
    visible_scopes = visible_zone_ids | visible_circuit_ids | visible_actuator_ids
    filtered["explanations"] = [
        step
        for step in snapshot["explanations"]
        if step["scope"] == "plant" or step["scope"] in visible_scopes
    ]
    # Source summaries are Plant-wide. Physical source entity IDs are already
    # excluded by the presentation whitelist and never cross this boundary.
    return filtered
