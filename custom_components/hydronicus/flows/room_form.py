"""Room basics: the form that describes a room, and the records it drafts.

The room subentry flow and guided setup both use it. A room is one zone with
its thermostat and sensors, its routes to shared loops, and at most one private
loop created from the valves chosen here. Further private loops come from the
room flow's loop steps.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from copy import deepcopy
from typing import Any
from uuid import UUID, uuid4

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from ..const import (
    CONF_CALIBRATION_OFFSET,
    CONF_CIRCUIT_IDS,
    CONF_CONDENSATION_MARGIN,
    CONF_COOLING_ENABLED,
    CONF_DESIGNATED_REFERENCE,
    CONF_ENTITY_ID,
    CONF_EXTERNAL_CLIMATE_ENTITY,
    CONF_MAX_AGE,
    CONF_NAME,
    CONF_OPENING_TIME,
    CONF_PUMP_ID,
    CONF_REQUIRED,
    CONF_ROUTES,
    CONF_SUPPLY_TEMPERATURE_MAX_AGE,
    CONF_SUPPLY_TEMPERATURE_SENSOR,
    CONF_SURFACE_TEMPERATURE_MAX_AGE,
    CONF_SURFACE_TEMPERATURE_SENSOR,
    CONF_TEMPERATURE_SENSOR_METADATA,
    CONF_TEMPERATURE_SENSORS,
    CONF_THERMOSTAT,
    CONF_THERMOSTAT_KIND,
    CONF_VALVE_IDS,
    CONF_VALVES,
    CONF_WEIGHT,
    DEFAULT_CONDENSATION_MARGIN,
    DEFAULT_REFERENCE_MAX_AGE,
    DEFAULT_SENSOR_MAX_AGE,
    DEFAULT_SENSOR_WEIGHT,
    DEFAULT_VALVE_OPENING_TIME,
    THERMOSTAT_KIND_EXTERNAL_CLIMATE,
    THERMOSTAT_KIND_HYDRONICUS,
)
from ..entry_configuration import EffectivePlant, RoomDraft
from .common import (
    is_hydronicus_owned,
    name_selector,
    own_entity_errors,
    sensor_selector,
    topology_select,
    zone_data,
)

CONF_PUMP = "pump"
CONF_SHARED_LOOPS = "shared_loops"


# Entity fields of the room forms that the shared own-entity check does not cover yet.
def valve_entity_selector() -> selector.EntitySelector:
    """Return the picker for the switches and valves of a loop."""
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["switch", "valve"], multiple=True)
    )


def _suggested(key: str, defaults: Mapping[str, Any], *, required: bool = False) -> vol.Marker:
    """Build a field that suggests a stored value, which the user can still clear."""
    marker = vol.Required if required else vol.Optional
    value = defaults.get(key)
    if value in (None, "", []):
        return marker(key)
    return marker(key, description={"suggested_value": value})


def room_form_schema(
    *,
    pumps: Sequence[selector.SelectOptionDict],
    shared_loops: Sequence[selector.SelectOptionDict],
    defaults: Mapping[str, Any] | None = None,
    include_valves: bool = True,
) -> vol.Schema:
    """Build the room basics form.

    ``defaults`` holds form values, as ``room_form_defaults`` returns them. The
    pump is asked for only when the Plant has two or more pumps, and shared
    loops only when the Plant has any.
    """
    defaults = defaults or {}
    schema: dict[Any, Any] = {
        vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)): name_selector(),
        _suggested(CONF_TEMPERATURE_SENSORS, defaults): sensor_selector(
            SensorDeviceClass.TEMPERATURE, multiple=True
        ),
        _suggested(CONF_EXTERNAL_CLIMATE_ENTITY, defaults): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="climate")
        ),
    }
    if include_valves:
        schema[_suggested(CONF_VALVES, defaults)] = valve_entity_selector()
        if len(pumps) >= 2:
            schema[_suggested(CONF_PUMP, defaults)] = topology_select(list(pumps), multiple=False)
    if shared_loops:
        schema[_suggested(CONF_SHARED_LOOPS, defaults)] = topology_select(
            list(shared_loops), multiple=True
        )
    return vol.Schema(schema)


def room_form_defaults(draft: RoomDraft) -> dict[str, Any]:
    """Return the room basics form values of a stored room."""
    thermostat = draft.zone.get(CONF_THERMOSTAT, {})
    private_loops = {_canonical(circuit["id"]) for circuit in draft.circuits}
    defaults: dict[str, Any] = {
        CONF_NAME: draft.zone.get(CONF_NAME, ""),
        CONF_TEMPERATURE_SENSORS: sensor_entity_ids(
            draft.zone.get(CONF_TEMPERATURE_SENSOR_METADATA)
        ),
        # A room routes only to its own loops and to Plant-owned loops.
        CONF_SHARED_LOOPS: [
            _canonical(route["circuit_id"])
            for route in draft.routes
            if _canonical(route["circuit_id"]) not in private_loops
        ],
    }
    if isinstance(thermostat, Mapping) and thermostat.get("kind") == (
        THERMOSTAT_KIND_EXTERNAL_CLIMATE
    ):
        defaults[CONF_EXTERNAL_CLIMATE_ENTITY] = thermostat.get(CONF_ENTITY_ID)
    return defaults


def pump_options(plant: EffectivePlant) -> list[selector.SelectOptionDict]:
    """Return every Plant pump as a select option."""
    return [
        selector.SelectOptionDict(value=pump.id, label=pump.name)
        for pump in plant.configuration.pumps
    ]


def shared_loop_options(plant: EffectivePlant) -> list[selector.SelectOptionDict]:
    """Return every Plant-owned loop, which any room may route to."""
    return [
        selector.SelectOptionDict(value=circuit.id, label=circuit.name)
        for circuit in plant.configuration.circuits
        if circuit.id not in plant.ownership.room_objects
    ]


def room_form_errors(
    hass: HomeAssistant, user_input: Mapping[str, Any], plant: EffectivePlant
) -> tuple[dict[str, str], dict[str, str]]:
    """Return the form errors of submitted room basics, and their placeholders.

    Both are empty when the form is valid. Errors that depend on the whole graph,
    such as an entity another valve already uses, come from applying the draft.
    """
    errors: dict[str, str] = {}
    if not str(user_input.get(CONF_NAME, "")).strip():
        errors[CONF_NAME] = "name_required"
    # vol.Required accepts an empty list, which a lazily loaded frontend picker
    # can submit, so required selections are checked explicitly.
    external = user_input.get(CONF_EXTERNAL_CLIMATE_ENTITY)
    if not external and not user_input.get(CONF_TEMPERATURE_SENSORS):
        errors[CONF_TEMPERATURE_SENSORS] = "temperature_sensors_required"
    if not user_input.get(CONF_VALVES) and not user_input.get(CONF_SHARED_LOOPS):
        errors["base"] = "delivery_required"
    elif user_input.get(CONF_VALVES) and _pump_id(user_input, plant) is None:
        errors[CONF_PUMP if len(plant.configuration.pumps) >= 2 else "base"] = "pump_required"
    errors.update(own_entity_errors(hass, user_input))
    if external and is_hydronicus_owned(hass, str(external)):
        errors["base"] = "thermostat_loop"
    return errors, {}


def room_draft_from_form(
    user_input: Mapping[str, Any], *, plant: EffectivePlant, existing: RoomDraft | None
) -> RoomDraft:
    """Draft a room from valid room basics.

    A new room gets a new zone id. An existing room keeps its zone, its private
    loops and valves, its thermostat settings unless the thermostat kind changes,
    and the route ids and route flags of the shared loops it keeps. ``valves``
    creates the room's first private loop, so it is ignored for a room that
    already has one.
    """
    name = str(user_input[CONF_NAME]).strip()
    sensors = [str(entity_id) for entity_id in user_input.get(CONF_TEMPERATURE_SENSORS) or ()]
    external = user_input.get(CONF_EXTERNAL_CLIMATE_ENTITY) or None
    if existing is None:
        zone = _new_zone(str(uuid4()), name, sensors, external)
        circuits: list[dict[str, Any]] = []
        valves: list[dict[str, Any]] = []
        kept_routes: list[dict[str, Any]] = []
        previous_shared: dict[str, dict[str, Any]] = {}
    else:
        zone = _updated_zone(existing.zone, name, sensors, external)
        circuits = deepcopy(existing.circuits)
        valves = deepcopy(existing.valves)
        private = {_canonical(circuit["id"]) for circuit in circuits}
        kept_routes = [
            deepcopy(route)
            for route in existing.routes
            if _canonical(route["circuit_id"]) in private
        ]
        previous_shared = {
            _canonical(route["circuit_id"]): route
            for route in existing.routes
            if _canonical(route["circuit_id"]) not in private
        }
    zone_id = str(zone["id"])
    routes = kept_routes
    valve_entities = [str(entity_id) for entity_id in user_input.get(CONF_VALVES) or ()]
    if valve_entities and not circuits:
        pump_id = _pump_id(user_input, plant)
        if pump_id is None:
            raise ValueError("A room loop needs a pump.")
        circuit, loop_valves = new_private_loop(
            f"{name} loop", valve_entities, pump_id=pump_id, taken_names=()
        )
        circuits.append(circuit)
        valves.extend(loop_valves)
        routes.insert(0, new_route(zone_id, circuit["id"]))
    for loop_id in dict.fromkeys(str(value) for value in user_input.get(CONF_SHARED_LOOPS) or ()):
        previous = previous_shared.get(_canonical(loop_id))
        routes.append(deepcopy(previous) if previous is not None else new_route(zone_id, loop_id))
    return RoomDraft(zone=zone, circuits=circuits, valves=valves, routes=routes)


def new_route(zone_id: str, circuit_id: str) -> dict[str, Any]:
    """Return a new Delivery Route record."""
    return {"id": str(uuid4()), "zone_id": zone_id, "circuit_id": circuit_id}


def new_private_loop(
    name: str,
    valve_entities: Sequence[str],
    *,
    pump_id: str,
    taken_names: Collection[str],
    opening_time: float = DEFAULT_VALVE_OPENING_TIME,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a new loop record and one new valve record per entity."""
    loop_id = str(uuid4())
    valves = new_valves(name, valve_entities, taken_names=taken_names, opening_time=opening_time)
    circuit = {
        "id": loop_id,
        CONF_NAME: name,
        CONF_VALVE_IDS: [valve["id"] for valve in valves],
        CONF_PUMP_ID: pump_id,
        CONF_COOLING_ENABLED: False,
        CONF_SUPPLY_TEMPERATURE_SENSOR: None,
        CONF_SURFACE_TEMPERATURE_SENSOR: None,
        CONF_CONDENSATION_MARGIN: DEFAULT_CONDENSATION_MARGIN,
        CONF_SUPPLY_TEMPERATURE_MAX_AGE: DEFAULT_REFERENCE_MAX_AGE,
        CONF_SURFACE_TEMPERATURE_MAX_AGE: DEFAULT_REFERENCE_MAX_AGE,
    }
    return circuit, valves


def new_valves(
    loop_name: str,
    valve_entities: Iterable[str],
    *,
    taken_names: Collection[str],
    opening_time: float = DEFAULT_VALVE_OPENING_TIME,
    first_position: int = 1,
) -> list[dict[str, Any]]:
    """Return new valve records named ``<loop> valve``, ``<loop> valve 2``, and so on.

    A name another valve already has is skipped, so names stay unique in a room.
    """
    taken = set(taken_names)
    valves = []
    position = first_position
    for entity_id in valve_entities:
        name = valve_name(loop_name, position)
        while name in taken:
            position += 1
            name = valve_name(loop_name, position)
        taken.add(name)
        position += 1
        valves.append(
            {
                "id": str(uuid4()),
                CONF_NAME: name,
                CONF_ENTITY_ID: entity_id,
                CONF_OPENING_TIME: opening_time,
            }
        )
    return valves


def valve_name(loop_name: str, position: int) -> str:
    """Return the plant file shorthand name of a loop's valve at one position."""
    return f"{loop_name} valve" if position == 1 else f"{loop_name} valve {position}"


def sensor_entity_ids(metadata: Any) -> list[str]:
    """Return the entity IDs of stored sensor metadata records."""
    if not isinstance(metadata, list):
        return []
    return [
        str(record[CONF_ENTITY_ID])
        for record in metadata
        if isinstance(record, Mapping) and record.get(CONF_ENTITY_ID)
    ]


def sensor_metadata_for(metadata: Any, entity_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Keep the metadata of retained sensors and give new sensors default metadata."""
    stored = {
        str(record[CONF_ENTITY_ID]): dict(record)
        for record in metadata or ()
        if isinstance(record, Mapping) and record.get(CONF_ENTITY_ID)
    }
    return [stored.get(entity_id, default_sensor_metadata(entity_id)) for entity_id in entity_ids]


def default_sensor_metadata(entity_id: str) -> dict[str, Any]:
    """Return the metadata a newly chosen sensor starts with."""
    return {
        CONF_ENTITY_ID: entity_id,
        CONF_REQUIRED: True,
        CONF_WEIGHT: DEFAULT_SENSOR_WEIGHT,
        CONF_CALIBRATION_OFFSET: 0.0,
        CONF_MAX_AGE: DEFAULT_SENSOR_MAX_AGE,
        CONF_DESIGNATED_REFERENCE: False,
    }


def _new_zone(
    zone_id: str, name: str, sensors: Sequence[str], external: str | None
) -> dict[str, Any]:
    """Return a new zone record with default thermostat settings."""
    zone = zone_data(
        {
            CONF_NAME: name,
            CONF_TEMPERATURE_SENSORS: list(sensors),
            CONF_CIRCUIT_IDS: [],
            CONF_THERMOSTAT_KIND: (
                THERMOSTAT_KIND_EXTERNAL_CLIMATE if external else THERMOSTAT_KIND_HYDRONICUS
            ),
            **({CONF_EXTERNAL_CLIMATE_ENTITY: external} if external else {}),
        },
        zone_id,
    )
    # A stored zone record holds no relationships; routes are stored separately.
    zone.pop(CONF_CIRCUIT_IDS, None)
    zone.pop(CONF_ROUTES, None)
    return zone


def _updated_zone(
    stored: Mapping[str, Any], name: str, sensors: Sequence[str], external: str | None
) -> dict[str, Any]:
    """Apply room basics to a stored zone record.

    Switching to an external thermostat drops the Hydronicus thermostat settings,
    and switching back starts from defaults.
    """
    zone = deepcopy(dict(stored))
    zone[CONF_NAME] = name
    zone[CONF_TEMPERATURE_SENSOR_METADATA] = sensor_metadata_for(
        zone.get(CONF_TEMPERATURE_SENSOR_METADATA), sensors
    )
    thermostat = zone.get(CONF_THERMOSTAT)
    was_hydronicus = (
        isinstance(thermostat, Mapping) and thermostat.get("kind") == THERMOSTAT_KIND_HYDRONICUS
    )
    if external:
        zone[CONF_THERMOSTAT] = {"kind": THERMOSTAT_KIND_EXTERNAL_CLIMATE, CONF_ENTITY_ID: external}
    elif not was_hydronicus:
        zone[CONF_THERMOSTAT] = _new_zone(str(zone["id"]), name, sensors, None)[CONF_THERMOSTAT]
    return zone


def _pump_id(user_input: Mapping[str, Any], plant: EffectivePlant) -> str | None:
    """Return the chosen pump, or the Plant's only pump, which is implied."""
    pump_ids = {pump.id for pump in plant.configuration.pumps}
    if (chosen := user_input.get(CONF_PUMP)) and _canonical(str(chosen)) in pump_ids:
        return _canonical(str(chosen))
    if len(pump_ids) == 1:
        return next(iter(pump_ids))
    return None


def _canonical(object_id: Any) -> str:
    """Return a stored id in the canonical UUID form the core decoder uses."""
    try:
        return str(UUID(str(object_id)))
    except ValueError:
        return str(object_id)
