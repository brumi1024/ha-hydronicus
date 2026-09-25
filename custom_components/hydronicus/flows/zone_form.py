"""Zone basics: the form that describes a zone, and the records it drafts.

The zone subentry flow and guided setup both use it. A zone has its thermostat
and sensors, its routes to shared loops, and at most one private loop created
from the valves chosen here. Further private loops come from the
zone flow's loop steps.

The zone, thermostat, sensor, and loop fields that only the zone flow's focused
steps show live here too, next to the records they describe.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from copy import deepcopy
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from ..const import (
    CONF_AWAY_TARGET,
    CONF_CALIBRATION_OFFSET,
    CONF_CIRCUIT_IDS,
    CONF_COMFORT_TARGET,
    CONF_CONDENSATION_MARGIN,
    CONF_CONFIGURE_SENSOR_METADATA,
    CONF_COOLING_ENABLED,
    CONF_COOLING_START_DELTA,
    CONF_COOLING_STOP_DELTA,
    CONF_DESIGNATED_REFERENCE,
    CONF_ECO_TARGET,
    CONF_ENTITY_ID,
    CONF_EXTERNAL_CLIMATE_ENTITY,
    CONF_HEATING_START_DELTA,
    CONF_HEATING_STOP_DELTA,
    CONF_HUMIDITY_SENSOR_METADATA,
    CONF_HUMIDITY_SENSORS,
    CONF_INITIAL_PRESET,
    CONF_INITIAL_TARGET_TEMPERATURE,
    CONF_MAX_AGE,
    CONF_MINIMUM_ACTIVE_DURATION,
    CONF_MINIMUM_IDLE_DURATION,
    CONF_NAME,
    CONF_OPENING_TIME,
    CONF_POSITION_FEEDBACK_ENTITY,
    CONF_POSITION_FEEDBACK_MAX_AGE,
    CONF_PRESET_TARGETS,
    CONF_PUMP_ID,
    CONF_REQUIRED,
    CONF_ROUTES,
    CONF_SENSOR_ENTITY,
    CONF_SUPPLY_TEMPERATURE_MAX_AGE,
    CONF_SUPPLY_TEMPERATURE_SENSOR,
    CONF_SURFACE_TEMPERATURE_MAX_AGE,
    CONF_SURFACE_TEMPERATURE_SENSOR,
    CONF_TEMPERATURE_AGGREGATION,
    CONF_TEMPERATURE_SENSOR_METADATA,
    CONF_TEMPERATURE_SENSORS,
    CONF_THERMOSTAT,
    CONF_THERMOSTAT_KIND,
    CONF_VALVE_IDS,
    CONF_VALVE_READINESS_ENTITY,
    CONF_VALVES,
    CONF_WEIGHT,
    DEFAULT_CONDENSATION_MARGIN,
    DEFAULT_COOLING_START_DELTA,
    DEFAULT_COOLING_STOP_DELTA,
    DEFAULT_HEATING_START_DELTA,
    DEFAULT_HEATING_STOP_DELTA,
    DEFAULT_MINIMUM_ACTIVE_DURATION,
    DEFAULT_MINIMUM_IDLE_DURATION,
    DEFAULT_REFERENCE_MAX_AGE,
    DEFAULT_SENSOR_MAX_AGE,
    DEFAULT_SENSOR_WEIGHT,
    DEFAULT_TARGET_TEMPERATURE,
    DEFAULT_TEMPERATURE_AGGREGATION,
    DEFAULT_VALVE_OPENING_TIME,
    THERMOSTAT_KIND_EXTERNAL_CLIMATE,
    THERMOSTAT_KIND_HYDRONICUS,
)
from ..core.configuration import DesignatedReferenceError
from ..core.model import (
    MAX_ZONE_TARGET_TEMPERATURE,
    MIN_ZONE_TARGET_TEMPERATURE,
    TemperatureAggregation,
)
from ..core.topology import (
    CoolingObservationError,
    CoolingReferenceError,
    DuplicateActuatorBindingError,
)
from ..entry_configuration import EffectivePlant, ZoneDraft, canonical_id
from .common import (
    DEFAULT_FEEDBACK_MAX_AGE,
    SECTION_COOLING,
    collapsed_section,
    flatten_sections,
    is_hydronicus_owned,
    max_age_selector,
    name_selector,
    number,
    optional_entity,
    own_entity_errors,
    positive,
    seconds_selector,
    sensor_selector,
    temperature_delta_selector,
    topology_select,
)

CONF_PUMP = "pump"
CONF_SHARED_LOOPS = "shared_loops"


# Entity fields of the zone forms that the shared own-entity check does not cover yet.
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


def _zone_cooling_fields() -> dict[Any, Any]:
    """Return the Cooling section of a new zone: its humidity and its loop's cooling."""
    return {
        vol.Optional(CONF_COOLING_ENABLED, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_HUMIDITY_SENSORS): sensor_selector(
            SensorDeviceClass.HUMIDITY, multiple=True
        ),
        vol.Optional(CONF_SUPPLY_TEMPERATURE_SENSOR): sensor_selector(
            SensorDeviceClass.TEMPERATURE
        ),
        vol.Optional(CONF_SURFACE_TEMPERATURE_SENSOR): sensor_selector(
            SensorDeviceClass.TEMPERATURE
        ),
        vol.Optional(
            CONF_CONDENSATION_MARGIN, default=DEFAULT_CONDENSATION_MARGIN
        ): temperature_delta_selector(),
    }


def _cooling_input(user_input: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the submitted Cooling section of a new zone, or an empty mapping."""
    section_input = user_input.get(SECTION_COOLING)
    return section_input if isinstance(section_input, Mapping) else {}


def zone_form_schema(
    *,
    pumps: Sequence[selector.SelectOptionDict],
    shared_loops: Sequence[selector.SelectOptionDict],
    defaults: Mapping[str, Any] | None = None,
    include_valves: bool = True,
) -> vol.Schema:
    """Build the zone basics form.

    ``defaults`` holds form values, as ``zone_form_defaults`` returns them. The
    pump is asked for only when the Plant has two or more pumps, and shared
    loops only when the Plant has any. A form that creates the zone's private
    loop from its valves also has a collapsed Cooling section, because cooling
    applies to that loop.
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
    if include_valves:
        schema[vol.Optional(SECTION_COOLING)] = collapsed_section(_zone_cooling_fields())
    return vol.Schema(schema)


def zone_form_defaults(draft: ZoneDraft) -> dict[str, Any]:
    """Return the zone basics form values of a stored zone."""
    thermostat = draft.zone.get(CONF_THERMOSTAT, {})
    private_loops = {canonical_id(circuit["id"]) for circuit in draft.circuits}
    defaults: dict[str, Any] = {
        CONF_NAME: draft.zone.get(CONF_NAME, ""),
        CONF_TEMPERATURE_SENSORS: sensor_entity_ids(
            draft.zone.get(CONF_TEMPERATURE_SENSOR_METADATA)
        ),
        # A zone routes only to its own loops and to Plant-owned loops.
        CONF_SHARED_LOOPS: [
            canonical_id(route["circuit_id"])
            for route in draft.routes
            if canonical_id(route["circuit_id"]) not in private_loops
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
    """Return every Plant-owned loop, which any zone may route to."""
    return [
        selector.SelectOptionDict(value=circuit.id, label=circuit.name)
        for circuit in plant.configuration.circuits
        if circuit.id not in plant.ownership.zone_objects
    ]


def zone_form_errors(
    hass: HomeAssistant, user_input: Mapping[str, Any], plant: EffectivePlant
) -> tuple[dict[str, str], dict[str, str]]:
    """Return the form errors of submitted zone basics, and their placeholders.

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
    # Cooling from the zone form applies to the zone's own loop, so it needs Loop
    # valves: a shared loop is Plant equipment that only the plant file edits. The
    # other checks mirror what the graph requires of a cooling loop, made here so
    # that each error names what fixes it. Fields inside the collapsed section are
    # reported on the form.
    cooling = _cooling_input(user_input)
    cooling_on = bool(cooling.get(CONF_COOLING_ENABLED))
    if cooling_on and not user_input.get(CONF_TEMPERATURE_SENSORS):
        errors.setdefault(CONF_TEMPERATURE_SENSORS, "temperature_required_for_cooling")
    if cooling_on and "base" not in errors:
        if not user_input.get(CONF_VALVES):
            errors["base"] = "cooling_requires_zone_loop"
        elif not (
            cooling.get(CONF_SUPPLY_TEMPERATURE_SENSOR)
            or cooling.get(CONF_SURFACE_TEMPERATURE_SENSOR)
        ):
            errors["base"] = "cooling_reference_required"
        elif not cooling.get(CONF_HUMIDITY_SENSORS):
            errors["base"] = "humidity_required_for_cooling"
    errors.update(own_entity_errors(hass, user_input))
    if external and is_hydronicus_owned(hass, str(external)):
        errors["base"] = "thermostat_loop"
    return errors, {}


def zone_draft_from_form(
    user_input: Mapping[str, Any], *, plant: EffectivePlant, existing: ZoneDraft | None
) -> ZoneDraft:
    """Draft a zone from valid zone basics.

    A new zone gets a new zone id. An existing zone keeps its id, its private
    loops and valves, its thermostat settings unless the thermostat kind changes,
    and the route ids and route flags of the shared loops it keeps. ``valves``
    creates the zone's first private loop, so it is ignored for a zone that
    already has one. The Cooling section of a new zone gives the zone its
    humidity sensors and the private loop its cooling settings.
    """
    name = str(user_input[CONF_NAME]).strip()
    sensors = [str(entity_id) for entity_id in user_input.get(CONF_TEMPERATURE_SENSORS) or ()]
    external = user_input.get(CONF_EXTERNAL_CLIMATE_ENTITY) or None
    cooling = _cooling_input(user_input)
    if existing is None:
        humidity = [str(entity_id) for entity_id in cooling.get(CONF_HUMIDITY_SENSORS) or ()]
        zone = _new_zone(str(uuid4()), name, sensors, external, humidity)
        circuits: list[dict[str, Any]] = []
        valves: list[dict[str, Any]] = []
        kept_routes: list[dict[str, Any]] = []
        previous_shared: dict[str, dict[str, Any]] = {}
    else:
        zone = _updated_zone(existing.zone, name, sensors, external)
        circuits = deepcopy(existing.circuits)
        valves = deepcopy(existing.valves)
        private = {canonical_id(circuit["id"]) for circuit in circuits}
        kept_routes = [
            deepcopy(route)
            for route in existing.routes
            if canonical_id(route["circuit_id"]) in private
        ]
        previous_shared = {
            canonical_id(route["circuit_id"]): route
            for route in existing.routes
            if canonical_id(route["circuit_id"]) not in private
        }
    zone_id = str(zone["id"])
    routes = kept_routes
    valve_entities = [str(entity_id) for entity_id in user_input.get(CONF_VALVES) or ()]
    if valve_entities and not circuits:
        pump_id = _pump_id(user_input, plant)
        if pump_id is None:
            raise ValueError("A zone loop needs a pump.")
        circuit, loop_valves = new_private_loop(
            f"{name} loop", valve_entities, pump_id=pump_id, taken_names=(), cooling=cooling
        )
        circuits.append(circuit)
        valves.extend(loop_valves)
        routes.insert(0, new_route(zone_id, circuit["id"]))
    for loop_id in dict.fromkeys(str(value) for value in user_input.get(CONF_SHARED_LOOPS) or ()):
        previous = previous_shared.get(canonical_id(loop_id))
        routes.append(deepcopy(previous) if previous is not None else new_route(zone_id, loop_id))
    return ZoneDraft(zone=zone, circuits=circuits, valves=valves, routes=routes)


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
    cooling: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a new loop record and one new valve record per entity.

    ``cooling`` holds the zone form's Cooling section; without it the loop only heats.
    """
    cooling = cooling or {}
    loop_id = str(uuid4())
    valves = new_valves(name, valve_entities, taken_names=taken_names, opening_time=opening_time)
    circuit = {
        "id": loop_id,
        CONF_NAME: name,
        CONF_VALVE_IDS: [valve["id"] for valve in valves],
        CONF_PUMP_ID: pump_id,
        CONF_COOLING_ENABLED: bool(cooling.get(CONF_COOLING_ENABLED, False)),
        CONF_SUPPLY_TEMPERATURE_SENSOR: cooling.get(CONF_SUPPLY_TEMPERATURE_SENSOR) or None,
        CONF_SURFACE_TEMPERATURE_SENSOR: cooling.get(CONF_SURFACE_TEMPERATURE_SENSOR) or None,
        CONF_CONDENSATION_MARGIN: cooling.get(
            CONF_CONDENSATION_MARGIN, DEFAULT_CONDENSATION_MARGIN
        ),
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

    A name another valve already has is skipped, so names stay unique in a zone.
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
    zone_id: str,
    name: str,
    sensors: Sequence[str],
    external: str | None,
    humidity_sensors: Sequence[str] = (),
) -> dict[str, Any]:
    """Return a new zone record with default thermostat settings."""
    zone = zone_data(
        {
            CONF_NAME: name,
            CONF_TEMPERATURE_SENSORS: list(sensors),
            CONF_HUMIDITY_SENSORS: list(humidity_sensors),
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
    """Apply zone basics to a stored zone record.

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
    if (chosen := user_input.get(CONF_PUMP)) and canonical_id(str(chosen)) in pump_ids:
        return canonical_id(str(chosen))
    if len(pump_ids) == 1:
        return next(iter(pump_ids))
    return None


def graph_errors(
    error: Exception, draft: ZoneDraft, fields: frozenset[str]
) -> tuple[dict[str, str], dict[str, str]]:
    """Map a rejected zone edit to the field of the shown form that can fix it.

    A field error for a field the form does not show is reported on the form.
    """
    zone_id = canonical_id(draft.zone["id"])
    circuit_ids = {canonical_id(circuit["id"]) for circuit in draft.circuits}
    valve_entities = {str(valve.get(CONF_ENTITY_ID)) for valve in draft.valves}

    def on(field: str, key: str) -> tuple[dict[str, str], dict[str, str]]:
        return {field if field in fields else "base": key}, {}

    if isinstance(error, DuplicateActuatorBindingError) and valve_entities & set(error.entity_ids):
        return on(CONF_VALVES, "actuator_entity_in_use")
    if isinstance(error, CoolingReferenceError) and error.circuit_id in circuit_ids:
        return {"base": "cooling_reference_required"}, {}
    if isinstance(error, CoolingObservationError) and error.zone_id == zone_id:
        if SECTION_COOLING in fields and error.circuit_id in circuit_ids:
            return {"base": "cooling_requires_zone_observations"}, {}
        if error.observation == "humidity":
            return on(CONF_HUMIDITY_SENSORS, "humidity_required_for_cooling")
        return on(CONF_TEMPERATURE_SENSORS, "temperature_required_for_cooling")
    if isinstance(error, DesignatedReferenceError) and error.zone_id == zone_id:
        return {"base": "designated_reference_count"}, {}
    return {"base": "invalid_zone"}, {"error": str(error)}


# --------------------------------------------------------------------------
# Zone, thermostat, sensor, and loop fields of the zone flow steps
# --------------------------------------------------------------------------


def routes_with_retained_fields(
    existing_routes: Sequence[Mapping[str, Any]] | None,
    *,
    relationship_key: str,
    relationship_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Create relationship records while preserving retained route metadata."""
    routes_by_relationship = {
        str(route[relationship_key]): route for route in existing_routes or []
    }
    return [
        {
            "id": str(routes_by_relationship.get(relationship_id, {}).get("id", uuid4())),
            relationship_key: relationship_id,
            **(
                {"enabled": routes_by_relationship[relationship_id]["enabled"]}
                if relationship_id in routes_by_relationship
                and "enabled" in routes_by_relationship[relationship_id]
                else {}
            ),
        }
        for relationship_id in relationship_ids
    ]


def cooling_reference_fields(defaults: Mapping[str, Any]) -> dict[Any, Any]:
    """Return the cooling fields of the loop form."""
    return {
        vol.Optional(
            CONF_COOLING_ENABLED, default=defaults.get(CONF_COOLING_ENABLED, False)
        ): selector.BooleanSelector(),
        optional_entity(CONF_SUPPLY_TEMPERATURE_SENSOR, defaults): sensor_selector(
            SensorDeviceClass.TEMPERATURE
        ),
        optional_entity(CONF_SURFACE_TEMPERATURE_SENSOR, defaults): sensor_selector(
            SensorDeviceClass.TEMPERATURE
        ),
        vol.Optional(
            CONF_CONDENSATION_MARGIN,
            default=defaults.get(CONF_CONDENSATION_MARGIN, DEFAULT_CONDENSATION_MARGIN),
        ): temperature_delta_selector(),
        vol.Optional(
            CONF_SUPPLY_TEMPERATURE_MAX_AGE,
            default=defaults.get(CONF_SUPPLY_TEMPERATURE_MAX_AGE, DEFAULT_REFERENCE_MAX_AGE),
        ): max_age_selector(),
        vol.Optional(
            CONF_SURFACE_TEMPERATURE_MAX_AGE,
            default=defaults.get(CONF_SURFACE_TEMPERATURE_MAX_AGE, DEFAULT_REFERENCE_MAX_AGE),
        ): max_age_selector(),
    }


def zone_data(
    user_input: Mapping[str, Any],
    zone_id: str,
    existing_routes: list[Mapping[str, Any]] | None = None,
    existing_metadata: list[Mapping[str, Any]] | None = None,
    existing_humidity_metadata: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize one zone and preserve route UUIDs for retained circuits."""
    user_input = flatten_sections(user_input)
    circuit_ids = list(user_input[CONF_CIRCUIT_IDS])
    sensor_ids = [str(sensor_id) for sensor_id in user_input.get(CONF_TEMPERATURE_SENSORS, [])]
    raw_metadata = user_input.get(CONF_TEMPERATURE_SENSOR_METADATA)
    if raw_metadata is None:
        metadata_by_entity = {
            str(sensor_data.get("entity_id")): dict(sensor_data)
            for sensor_data in existing_metadata or ()
            if sensor_data.get("entity_id") is not None
        }
        metadata = [
            metadata_by_entity.get(
                sensor_id,
                {
                    "entity_id": sensor_id,
                    CONF_REQUIRED: True,
                    CONF_WEIGHT: DEFAULT_SENSOR_WEIGHT,
                    CONF_CALIBRATION_OFFSET: 0.0,
                    CONF_MAX_AGE: DEFAULT_SENSOR_MAX_AGE,
                    CONF_DESIGNATED_REFERENCE: False,
                },
            )
            for sensor_id in sensor_ids
        ]
    elif isinstance(raw_metadata, Mapping):
        metadata = [
            {"entity_id": str(sensor_id), **dict(sensor_data)}
            for sensor_id, sensor_data in raw_metadata.items()
            if isinstance(sensor_data, Mapping)
        ]
    elif isinstance(raw_metadata, list):
        metadata = [dict(sensor_data) for sensor_data in raw_metadata]
    else:
        metadata = raw_metadata
    humidity_sensor_ids = [
        str(sensor_id) for sensor_id in user_input.get(CONF_HUMIDITY_SENSORS, [])
    ]
    raw_humidity_metadata = user_input.get(CONF_HUMIDITY_SENSOR_METADATA)
    if raw_humidity_metadata is None or (not raw_humidity_metadata and humidity_sensor_ids):
        existing_humidity_metadata = [
            dict(sensor_data)
            for sensor_data in existing_humidity_metadata or ()
            if sensor_data.get("entity_id") in humidity_sensor_ids
        ]
        humidity_metadata = [
            next(
                (
                    record
                    for record in existing_humidity_metadata
                    if record.get("entity_id") == sensor_id
                ),
                {
                    "entity_id": sensor_id,
                    CONF_REQUIRED: True,
                    CONF_WEIGHT: DEFAULT_SENSOR_WEIGHT,
                    CONF_CALIBRATION_OFFSET: 0.0,
                    CONF_MAX_AGE: DEFAULT_SENSOR_MAX_AGE,
                    CONF_DESIGNATED_REFERENCE: False,
                },
            )
            for sensor_id in humidity_sensor_ids
        ]
    elif isinstance(raw_humidity_metadata, Mapping):
        humidity_metadata = [
            {"entity_id": str(sensor_id), **dict(sensor_data)}
            for sensor_id, sensor_data in raw_humidity_metadata.items()
            if isinstance(sensor_data, Mapping)
        ]
    elif isinstance(raw_humidity_metadata, list):
        humidity_metadata = [dict(sensor_data) for sensor_data in raw_humidity_metadata]
    else:
        humidity_metadata = raw_humidity_metadata
    raw_preset_targets = user_input.get(CONF_PRESET_TARGETS, {})
    preset_targets = dict(raw_preset_targets) if isinstance(raw_preset_targets, Mapping) else {}
    for preset_name in (CONF_COMFORT_TARGET, CONF_ECO_TARGET, CONF_AWAY_TARGET):
        if preset_name in user_input and user_input[preset_name] is not None:
            preset_targets[preset_name] = user_input[preset_name]
    kind = str(user_input.get(CONF_THERMOSTAT_KIND, THERMOSTAT_KIND_HYDRONICUS))
    if kind == THERMOSTAT_KIND_EXTERNAL_CLIMATE:
        thermostat: dict[str, Any] = {
            "kind": kind,
            "entity_id": str(user_input[CONF_EXTERNAL_CLIMATE_ENTITY]),
        }
    else:
        thermostat = {
            "kind": THERMOSTAT_KIND_HYDRONICUS,
            CONF_INITIAL_TARGET_TEMPERATURE: DEFAULT_TARGET_TEMPERATURE,
            CONF_HEATING_START_DELTA: user_input.get(
                CONF_HEATING_START_DELTA, DEFAULT_HEATING_START_DELTA
            ),
            CONF_HEATING_STOP_DELTA: user_input.get(
                CONF_HEATING_STOP_DELTA, DEFAULT_HEATING_STOP_DELTA
            ),
            CONF_COOLING_START_DELTA: user_input.get(
                CONF_COOLING_START_DELTA, DEFAULT_COOLING_START_DELTA
            ),
            CONF_COOLING_STOP_DELTA: user_input.get(
                CONF_COOLING_STOP_DELTA, DEFAULT_COOLING_STOP_DELTA
            ),
            CONF_MINIMUM_ACTIVE_DURATION: user_input.get(
                CONF_MINIMUM_ACTIVE_DURATION, DEFAULT_MINIMUM_ACTIVE_DURATION
            ),
            CONF_MINIMUM_IDLE_DURATION: user_input.get(
                CONF_MINIMUM_IDLE_DURATION, DEFAULT_MINIMUM_IDLE_DURATION
            ),
            CONF_PRESET_TARGETS: preset_targets,
            CONF_INITIAL_PRESET: "none",
        }
    return {
        "id": zone_id,
        CONF_NAME: str(user_input[CONF_NAME]).strip(),
        CONF_THERMOSTAT: thermostat,
        CONF_TEMPERATURE_SENSOR_METADATA: metadata,
        CONF_HUMIDITY_SENSOR_METADATA: humidity_metadata,
        CONF_TEMPERATURE_AGGREGATION: user_input.get(
            CONF_TEMPERATURE_AGGREGATION, DEFAULT_TEMPERATURE_AGGREGATION
        ),
        CONF_CIRCUIT_IDS: circuit_ids,
        CONF_ROUTES: routes_with_retained_fields(
            existing_routes,
            relationship_key="circuit_id",
            relationship_ids=circuit_ids,
        ),
    }


def sensor_metadata_schema(
    sensor_id: str,
    defaults: Mapping[str, Any] | None = None,
) -> vol.Schema:
    """Build one explicit editor for one sensor's immutable metadata."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_SENSOR_ENTITY,
                default=defaults.get("entity_id", sensor_id),
            ): sensor_selector(SensorDeviceClass.TEMPERATURE),
            vol.Required(
                CONF_REQUIRED,
                default=defaults.get(CONF_REQUIRED, True),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_WEIGHT,
                default=defaults.get(CONF_WEIGHT, DEFAULT_SENSOR_WEIGHT),
            ): positive(number(step="any", minimum=0)),
            vol.Required(
                CONF_CALIBRATION_OFFSET,
                default=defaults.get(CONF_CALIBRATION_OFFSET, 0.0),
            ): number(step="any", unit=UnitOfTemperature.CELSIUS),
            vol.Required(
                CONF_MAX_AGE,
                default=defaults.get(CONF_MAX_AGE, DEFAULT_SENSOR_MAX_AGE),
            ): max_age_selector(),
            vol.Required(
                CONF_DESIGNATED_REFERENCE,
                default=defaults.get(CONF_DESIGNATED_REFERENCE, False),
            ): selector.BooleanSelector(),
        }
    )


def sensor_metadata_record(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one metadata form result for canonical persistence."""
    return {
        "entity_id": str(user_input[CONF_SENSOR_ENTITY]),
        CONF_REQUIRED: bool(user_input[CONF_REQUIRED]),
        CONF_WEIGHT: user_input[CONF_WEIGHT],
        CONF_CALIBRATION_OFFSET: user_input[CONF_CALIBRATION_OFFSET],
        CONF_MAX_AGE: user_input[CONF_MAX_AGE],
        CONF_DESIGNATED_REFERENCE: bool(user_input[CONF_DESIGNATED_REFERENCE]),
    }


def _preset_targets_schema(defaults: Mapping[str, Any] | None = None) -> dict[Any, Any]:
    """Return optional finite target fields for standard heating presets."""
    defaults = defaults or {}
    targets = defaults.get(CONF_PRESET_TARGETS, {})
    if not isinstance(targets, Mapping):
        targets = {}
    fields: dict[Any, Any] = {}
    for name in (CONF_COMFORT_TARGET, CONF_ECO_TARGET, CONF_AWAY_TARGET):
        key: Any = vol.Optional(
            name,
            **({"default": targets[name]} if name in targets else {}),
        )
        fields[key] = number(
            step=0.1,
            unit=UnitOfTemperature.CELSIUS,
            minimum=MIN_ZONE_TARGET_TEMPERATURE,
            maximum=MAX_ZONE_TARGET_TEMPERATURE,
        )
    return fields


def _zone_advanced_fields(defaults: Mapping[str, Any] | None = None) -> dict[Any, Any]:
    """Return the Hydronicus thermostat fields of the thermostat step."""
    defaults = defaults or {}
    return {
        vol.Required(
            CONF_HEATING_START_DELTA,
            default=defaults.get(CONF_HEATING_START_DELTA, DEFAULT_HEATING_START_DELTA),
        ): temperature_delta_selector(),
        vol.Required(
            CONF_HEATING_STOP_DELTA,
            default=defaults.get(CONF_HEATING_STOP_DELTA, DEFAULT_HEATING_STOP_DELTA),
        ): temperature_delta_selector(),
        vol.Required(
            CONF_MINIMUM_ACTIVE_DURATION,
            default=defaults.get(CONF_MINIMUM_ACTIVE_DURATION, DEFAULT_MINIMUM_ACTIVE_DURATION),
        ): seconds_selector(),
        vol.Required(
            CONF_MINIMUM_IDLE_DURATION,
            default=defaults.get(CONF_MINIMUM_IDLE_DURATION, DEFAULT_MINIMUM_IDLE_DURATION),
        ): seconds_selector(),
        **_preset_targets_schema(defaults),
        vol.Optional(SECTION_COOLING): collapsed_section(
            {
                vol.Required(
                    CONF_COOLING_START_DELTA,
                    default=defaults.get(CONF_COOLING_START_DELTA, DEFAULT_COOLING_START_DELTA),
                ): temperature_delta_selector(),
                vol.Required(
                    CONF_COOLING_STOP_DELTA,
                    default=defaults.get(CONF_COOLING_STOP_DELTA, DEFAULT_COOLING_STOP_DELTA),
                ): temperature_delta_selector(),
            }
        ),
    }


def zone_temperature_sensor_defaults(defaults: Mapping[str, Any]) -> Any:
    """Return list-form defaults from canonical metadata or the current form input."""
    metadata = defaults.get(CONF_TEMPERATURE_SENSOR_METADATA)
    if isinstance(metadata, list):
        return [
            str(record["entity_id"])
            for record in metadata
            if isinstance(record, Mapping) and record.get("entity_id")
        ]
    if CONF_TEMPERATURE_SENSORS in defaults:
        return defaults[CONF_TEMPERATURE_SENSORS]
    return vol.UNDEFINED


def _zone_humidity_sensor_defaults(defaults: Mapping[str, Any]) -> list[str]:
    """Return list-form defaults derived from canonical humidity metadata."""
    metadata = defaults.get(CONF_HUMIDITY_SENSOR_METADATA)
    if isinstance(metadata, list):
        return [
            str(record["entity_id"])
            for record in metadata
            if isinstance(record, Mapping) and record.get("entity_id")
        ]
    return [str(sensor_id) for sensor_id in defaults.get(CONF_HUMIDITY_SENSORS, [])]


def _zone_temperature_aggregation_default(defaults: Mapping[str, Any]) -> str:
    """Return the persisted or legacy-default aggregation policy."""
    return str(defaults.get(CONF_TEMPERATURE_AGGREGATION, DEFAULT_TEMPERATURE_AGGREGATION))


def _zone_has_editable_sensor_metadata(defaults: Mapping[str, Any]) -> bool:
    """Return whether a persisted zone can expose metadata-dependent policies."""
    metadata = defaults.get(CONF_TEMPERATURE_SENSOR_METADATA)
    return isinstance(metadata, list) and bool(metadata)


def _temperature_aggregation_selector(
    *, include_metadata_policies: bool = False
) -> selector.SelectSelector:
    """Build a policy selector with weighted mean gated by metadata editing."""
    user_selectable = [
        TemperatureAggregation.MEAN,
        TemperatureAggregation.MEDIAN,
        TemperatureAggregation.MINIMUM,
        TemperatureAggregation.MAXIMUM,
    ]
    if include_metadata_policies:
        user_selectable.extend(
            [TemperatureAggregation.DESIGNATED_REFERENCE, TemperatureAggregation.WEIGHTED_MEAN]
        )
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[policy.value for policy in user_selectable],
            translation_key=CONF_TEMPERATURE_AGGREGATION,
        )
    )


def sensor_policy_schema(zone_draft: Mapping[str, Any]) -> vol.Schema:
    """Build the aggregation form offered after sensor metadata editing."""
    return vol.Schema(
        {
            vol.Required(
                CONF_TEMPERATURE_AGGREGATION,
                default=_zone_temperature_aggregation_default(zone_draft),
            ): _temperature_aggregation_selector(include_metadata_policies=True),
        }
    )


def zone_schema(
    defaults: Mapping[str, Any] | None = None,
    *,
    thermostat_kind: str = THERMOSTAT_KIND_HYDRONICUS,
) -> vol.Schema:
    """Build the zone fields that the zone flow's thermostat and sensors steps pick from."""
    defaults = defaults or {}
    thermostat_defaults = defaults.get(CONF_THERMOSTAT, {})
    if not isinstance(thermostat_defaults, Mapping):
        thermostat_defaults = {}
    schema: dict[Any, Any] = {
        vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)): name_selector(),
        (vol.Required if thermostat_kind == THERMOSTAT_KIND_HYDRONICUS else vol.Optional)(
            CONF_TEMPERATURE_SENSORS,
            default=zone_temperature_sensor_defaults(defaults),
        ): sensor_selector(SensorDeviceClass.TEMPERATURE, multiple=True),
        vol.Optional(
            CONF_HUMIDITY_SENSORS,
            default=_zone_humidity_sensor_defaults(defaults),
        ): sensor_selector(SensorDeviceClass.HUMIDITY, multiple=True),
        vol.Required(
            CONF_TEMPERATURE_AGGREGATION,
            default=_zone_temperature_aggregation_default(defaults),
        ): _temperature_aggregation_selector(
            include_metadata_policies=_zone_has_editable_sensor_metadata(defaults)
        ),
        vol.Optional(
            CONF_CONFIGURE_SENSOR_METADATA,
            default=False,
        ): selector.BooleanSelector(),
    }
    if thermostat_kind == THERMOSTAT_KIND_EXTERNAL_CLIMATE:
        schema[
            vol.Required(
                CONF_EXTERNAL_CLIMATE_ENTITY,
                default=thermostat_defaults.get("entity_id", vol.UNDEFINED),
            )
        ] = selector.EntitySelector(selector.EntitySelectorConfig(domain="climate"))
    else:
        schema.update(_zone_advanced_fields(thermostat_defaults or defaults))
    return vol.Schema(schema)


def requires_sensor_metadata_path(data: Mapping[str, Any]) -> bool:
    """Return whether the selected policy requires the typed metadata editor."""
    return data.get(CONF_TEMPERATURE_AGGREGATION) in {
        TemperatureAggregation.DESIGNATED_REFERENCE.value,
        TemperatureAggregation.WEIGHTED_MEAN.value,
    }


def valve_feedback_fields(defaults: Mapping[str, Any]) -> dict[Any, Any]:
    """Return the optional feedback fields of the valve details step."""
    return {
        optional_entity(CONF_VALVE_READINESS_ENTITY, defaults): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["binary_sensor", "switch", "valve"])
        ),
        optional_entity(CONF_POSITION_FEEDBACK_ENTITY, defaults): sensor_selector(),
        vol.Optional(
            CONF_POSITION_FEEDBACK_MAX_AGE,
            default=defaults.get(CONF_POSITION_FEEDBACK_MAX_AGE, DEFAULT_FEEDBACK_MAX_AGE),
        ): max_age_selector(),
    }
