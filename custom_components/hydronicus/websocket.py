"""Read-only Plant presentation WebSocket commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import voluptuous as vol
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized

from .const import DOMAIN
from .presentation import PRESENTATION_SCHEMA_VERSION, build_plant_summary

WS_LIST_PLANTS = "hydronicus/list_plants"
WS_SUBSCRIBE_PLANT = "hydronicus/subscribe_plant"
DATA_RUNTIMES = "runtimes"
DATA_SUBSCRIPTIONS = "plant_subscriptions"


@dataclass(slots=True)
class PlantSubscription:
    """One connection subscription that can be rebound across runtime reloads."""

    hass: HomeAssistant
    connection: websocket_api.ActiveConnection
    msg_id: int
    plant_id: str
    _remove_runtime_listener: Any = None

    def bind(self, runtime: Any | None) -> None:
        """Bind to the current runtime without changing the stream payload."""
        self.unbind()
        if runtime is not None:
            self._remove_runtime_listener = runtime.async_add_listener(self.publish)

    def send_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Send an already-built snapshot on the subscription event channel."""
        self.connection.send_event(self.msg_id, {"snapshot": snapshot})

    @callback
    def publish(self) -> None:
        """Publish one meaningful runtime update to the subscribed user."""
        runtime = _runtimes(self.hass).get(self.plant_id)
        if runtime is None:
            self.connection.send_event(
                self.msg_id,
                {"status": "unavailable", "plant_id": self.plant_id},
            )
            return
        entities = runtime.presentation_entities(self.hass)
        allowed = _readable_entity_ids(self.connection.user, entities)
        if not _has_read_access(allowed):
            self.revoke()
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

    @callback
    def revoke(self) -> None:
        """Remove this subscription when access is revoked while connected."""
        self.connection.subscriptions.pop(self.msg_id, None)
        self.close()

    @callback
    def close(self) -> None:
        """Detach without mutating Core's subscription map during connection close."""
        self.unbind()
        subscriptions = _subscriptions(self.hass)
        if self in subscriptions:
            subscriptions.remove(self)


async def async_setup(hass: HomeAssistant, _config: Any) -> bool:
    """Register read-only Plant presentation commands once per Home Assistant."""
    data = hass.data.setdefault(DOMAIN, {})
    data.setdefault(DATA_RUNTIMES, {})
    data.setdefault(DATA_SUBSCRIPTIONS, [])
    websocket_api.async_register_command(hass, ws_list_plants)
    websocket_api.async_register_command(hass, ws_subscribe_plant)
    return True


@websocket_api.websocket_command({vol.Required("type"): WS_LIST_PLANTS})
@websocket_api.async_response
async def ws_list_plants(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List only Plants for which the user can read Hydronicus-owned entities."""
    plants = []
    for plant_id, runtime in sorted(_runtimes(hass).items()):
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
    """Send an atomic initial snapshot and meaningful subsequent updates."""
    plant_id = msg["plant_id"]
    runtime = _runtimes(hass).get(plant_id)
    if runtime is None:
        connection.send_error(
            msg["id"], "plant_not_found", "Hydronicus Plant is missing or unloaded."
        )
        return
    entities = runtime.presentation_entities(hass)
    allowed = _readable_entity_ids(connection.user, entities)
    if not _has_read_access(allowed):
        raise Unauthorized()

    existing = connection.subscriptions.pop(msg["id"], None)
    if existing is not None:
        existing()
    subscription = PlantSubscription(hass, connection, msg["id"], plant_id)
    _subscriptions(hass).append(subscription)
    connection.subscriptions[msg["id"]] = subscription.close
    snapshot = _filter_snapshot_for_user(
        runtime.presentation_snapshot(hass, control_entities=entities),
        entities,
        allowed,
    )
    connection.send_result(
        msg["id"],
        {"schema_version": PRESENTATION_SCHEMA_VERSION, "snapshot": snapshot},
    )
    # The HA subscribeMessage helper delivers subsequent send_event payloads
    # to the card callback, while the command result resolves its promise.
    # Publish the same initial snapshot on the event channel as well so cards
    # work with both HA connection implementations.
    subscription.bind(runtime)
    subscription.send_snapshot(snapshot)


def register_runtime(hass: HomeAssistant, runtime: Any) -> None:
    """Publish a runtime and rebind subscriptions after setup or reload."""
    _runtimes(hass)[runtime.plant_id] = runtime
    for subscription in tuple(_subscriptions(hass)):
        if subscription.plant_id == runtime.plant_id:
            subscription.bind(runtime)
            subscription.publish()


def unregister_runtime(hass: HomeAssistant, plant_id: str) -> None:
    """Mark subscriptions unavailable and remove a runtime on unload."""
    _runtimes(hass).pop(plant_id, None)
    for subscription in tuple(_subscriptions(hass)):
        if subscription.plant_id == plant_id:
            subscription.bind(None)
            subscription.publish()


def _runtimes(hass: HomeAssistant) -> dict[str, Any]:
    return cast(dict[str, Any], hass.data.setdefault(DOMAIN, {}).setdefault(DATA_RUNTIMES, {}))


def _subscriptions(hass: HomeAssistant) -> list[PlantSubscription]:
    return cast(
        list[PlantSubscription],
        hass.data.setdefault(DOMAIN, {}).setdefault(DATA_SUBSCRIPTIONS, []),
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
    boundary = dict(execution["boundary"])
    boundary["forced_shadow_actuators"] = [
        actuator_id
        for actuator_id in boundary["forced_shadow_actuators"]
        if actuator_id in visible_actuator_ids
    ]
    execution["boundary"] = boundary
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
