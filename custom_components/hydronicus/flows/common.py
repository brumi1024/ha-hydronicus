"""Helpers shared by the Hydronicus config and subentry flows."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as entity_registry_helper
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
    CONF_DRY_RUN,
    CONF_DRY_RUN_CONFIRMATION,
    CONF_ECO_TARGET,
    CONF_ENTITY_ID,
    CONF_EXTERNAL_CLIMATE_ENTITY,
    CONF_FAULT_FEEDBACK_ENTITY,
    CONF_FLOW_FEEDBACK_ENTITY,
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
    CONF_POSITION_FEEDBACK_ENTITY,
    CONF_POSITION_FEEDBACK_MAX_AGE,
    CONF_POWER_FEEDBACK_ENTITY,
    CONF_PRESET_TARGETS,
    CONF_PUMP_ENTITY,
    CONF_REQUIRED,
    CONF_ROUTES,
    CONF_SENSOR_ENTITY,
    CONF_SOURCE_AVAILABILITY_ENTITY,
    CONF_SOURCE_DEMAND_ENTITY,
    CONF_SOURCE_TEMPERATURE_ENTITY,
    CONF_SUPPLY_TEMPERATURE_MAX_AGE,
    CONF_SUPPLY_TEMPERATURE_SENSOR,
    CONF_SURFACE_TEMPERATURE_MAX_AGE,
    CONF_SURFACE_TEMPERATURE_SENSOR,
    CONF_TEMPERATURE_AGGREGATION,
    CONF_TEMPERATURE_SENSOR_METADATA,
    CONF_TEMPERATURE_SENSORS,
    CONF_THERMOSTAT,
    CONF_THERMOSTAT_KIND,
    CONF_VALVE_ENTITY,
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
    DOMAIN,
    SUBENTRY_TYPE_SOURCE,
    THERMOSTAT_KIND_EXTERNAL_CLIMATE,
    THERMOSTAT_KIND_HYDRONICUS,
)
from ..core.configuration import (
    StoredTopologyError,
)
from ..core.model import (
    MAX_ZONE_TARGET_TEMPERATURE,
    MIN_ZONE_TARGET_TEMPERATURE,
    TemperatureAggregation,
)
from ..core.ownership import OwnershipError
from ..core.topology import (
    CoolingObservationError,
    CoolingReferenceError,
    TopologyValidationError,
)
from ..entry_configuration import (
    data_with_source,
    effective_plant_from_data,
)
from ..output_ownership import bound_by_other_plant

if TYPE_CHECKING:
    ConfigFlowBase = config_entries.ConfigFlow
else:
    ConfigFlowBase = object


SECTION_FEEDBACK: Final = "feedback"
SECTION_COOLING: Final = "cooling"
_FORM_SECTIONS: Final = (SECTION_FEEDBACK, SECTION_COOLING)
DEFAULT_FEEDBACK_MAX_AGE: Final = 1800.0


# Form fields that hold Home Assistant entity IDs bound into the plant topology.
# The external climate thermostat is checked separately with its own error.
_ENTITY_FIELDS: Final = frozenset(
    {
        CONF_ENTITY_ID,
        CONF_FAULT_FEEDBACK_ENTITY,
        CONF_FLOW_FEEDBACK_ENTITY,
        CONF_HUMIDITY_SENSORS,
        CONF_POSITION_FEEDBACK_ENTITY,
        CONF_POWER_FEEDBACK_ENTITY,
        CONF_PUMP_ENTITY,
        CONF_SENSOR_ENTITY,
        CONF_SOURCE_AVAILABILITY_ENTITY,
        CONF_SOURCE_DEMAND_ENTITY,
        CONF_SOURCE_TEMPERATURE_ENTITY,
        CONF_SUPPLY_TEMPERATURE_SENSOR,
        CONF_SURFACE_TEMPERATURE_SENSOR,
        CONF_TEMPERATURE_SENSORS,
        CONF_VALVE_ENTITY,
        CONF_VALVE_READINESS_ENTITY,
        CONF_VALVES,
    }
)


def _entity_ids_in(value: Any) -> set[str]:
    """Return the entity IDs held by a single or multiple entity field value."""
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, (list, tuple)):
        return {item for item in value if isinstance(item, str) and item}
    return set()


def is_hydronicus_owned(hass: Any, entity_id: str) -> bool:
    """Return whether an entity is provided by this integration."""
    registry_entry = entity_registry_helper.async_get(hass).async_get(entity_id)
    return registry_entry is not None and registry_entry.platform == DOMAIN


def _own_entity_ids(hass: Any) -> frozenset[str]:
    """Return every entity provided by this integration."""
    registry = entity_registry_helper.async_get(hass)
    return frozenset(
        registry_entry.entity_id
        for registry_entry in registry.entities.values()
        if registry_entry.platform == DOMAIN
    )


def _holds_own_entity(hass: Any, value: Any) -> bool:
    """Return whether an entity field value holds an entity of this integration."""
    return any(is_hydronicus_owned(hass, entity_id) for entity_id in _entity_ids_in(value))


def own_entity_errors(hass: Any, user_input: Mapping[str, Any]) -> dict[str, str]:
    """Reject submitted Hydronicus entities, which would feed the plant back into itself.

    The pickers already hide them, but a previously stored binding stays visible
    and selectable, so the backend checks every entity field on submit too.
    """
    errors: dict[str, str] = {}
    for key, value in user_input.items():
        if isinstance(value, Mapping):
            # A field inside a collapsed section is reported as a form error.
            if any(
                field in _ENTITY_FIELDS and _holds_own_entity(hass, nested)
                for field, nested in value.items()
            ):
                errors["base"] = "own_entity"
        elif key in _ENTITY_FIELDS and _holds_own_entity(hass, value):
            errors[key] = "own_entity"
    return errors


def _shown_entity_ids(key: Any) -> set[str]:
    """Return the entity IDs a form field pre-fills from its default or suggested value."""
    shown: set[str] = set()
    default = getattr(key, "default", vol.UNDEFINED)
    if callable(default):
        shown |= _entity_ids_in(default())
    description = getattr(key, "description", None)
    if isinstance(description, Mapping):
        shown |= _entity_ids_in(description.get("suggested_value"))
    return shown


def _without_own_entities(key: Any, validator: Any, own: frozenset[str]) -> Any:
    """Hide this integration's entities from one field's entity pickers."""
    if isinstance(validator, section):
        return section(_schema_without_own_entities(validator.schema, own), validator.options)
    if isinstance(validator, vol.Maybe):
        return vol.Maybe(_without_own_entities(key, validator.validator, own), msg=validator.msg)
    if isinstance(validator, selector.EntitySelector):
        # A stored or just-submitted value stays visible so the user sees what to replace.
        excluded = own - _shown_entity_ids(key)
        if not excluded:
            return validator
        config = dict(validator.config)
        config["exclude_entities"] = sorted(excluded | set(config.get("exclude_entities", ())))
        return selector.EntitySelector(selector.EntitySelectorConfig(**config))
    return validator


def _schema_without_own_entities(schema: vol.Schema, own: frozenset[str]) -> vol.Schema:
    """Return the schema with this integration's entities excluded from every picker."""
    if not own or not isinstance(schema, vol.Schema) or not isinstance(schema.schema, Mapping):
        return schema
    return vol.Schema(
        {key: _without_own_entities(key, value, own) for key, value in schema.schema.items()},
        required=schema.required,
        extra=schema.extra,
    )


class OwnEntityPickerMixin:
    """Keep Hydronicus entities out of the entity pickers of every form.

    Selecting one, such as a zone's aggregate temperature, would create a feedback loop.
    """

    hass: Any

    def async_show_form(self, *, data_schema: vol.Schema | None = None, **kwargs: Any) -> Any:
        """Show a form whose entity pickers exclude this integration's entities."""
        if data_schema is not None:
            data_schema = _schema_without_own_entities(data_schema, _own_entity_ids(self.hass))
        return super().async_show_form(data_schema=data_schema, **kwargs)  # type: ignore[misc]


def other_plant_sharing_warnings(
    hass: HomeAssistant, entry_id: str | None, entity_ids: Iterable[Any]
) -> tuple[str, ...]:
    """Describe chosen outputs that another Plant already binds, for a review step.

    Sharing is allowed, because Dry run Plants may share entities with a live
    Plant, for example to compare a draft configuration. The review lets users
    learn about sharing before it matters. The runtime guard that keeps one live
    Plant per output is authoritative.
    """
    warnings = []
    for entity_id in dict.fromkeys(entity_ids):
        if conflict := bound_by_other_plant(hass, entry_id, entity_id):
            warnings.append(
                f"{entity_id} is already bound by {conflict.other_plant}. Only one of the "
                "two plants can be out of Dry run at a time: while one is live, the other "
                "cannot leave Dry run, and if it is stored out of Dry run it is held in "
                "Dry run until the conflict is gone."
            )
    return tuple(warnings)


def flatten_sections(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Merge collapsible form sections back into the flat persisted field layout."""
    flat = {key: value for key, value in user_input.items() if key not in _FORM_SECTIONS}
    for section_key in _FORM_SECTIONS:
        nested = user_input.get(section_key)
        if isinstance(nested, Mapping):
            flat.update(nested)
    return flat


def collapsed_section(fields: Mapping[Any, Any]) -> section:
    """Wrap optional fields in a collapsed form section."""
    return section(vol.Schema(dict(fields)), {"collapsed": True})


def number(
    *,
    step: float | Literal["any"],
    unit: str | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> selector.NumberSelector:
    """Build a box-mode number selector that returns a float."""
    config = selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step=step)
    if unit is not None:
        config["unit_of_measurement"] = unit
    if minimum is not None:
        config["min"] = minimum
    if maximum is not None:
        config["max"] = maximum
    return selector.NumberSelector(config)


def _positive(number: selector.NumberSelector) -> vol.All:
    """Keep the exclusive zero bound that a number selector cannot express."""
    return vol.All(number, vol.Range(min=0, min_included=False))


def _whole_number(value: float) -> int:
    """Return a finite whole number as an int, or raise ValueError.

    The number selector returns a float and accepts NaN and infinity, so a
    plain int() would raise or silently truncate a fractional value.
    """
    if not math.isfinite(value) or not float(value).is_integer():
        raise ValueError("expected a whole number")
    return int(value)


def whole_number_selector(*, minimum: float) -> vol.All:
    """Return a box number selector that only admits finite whole numbers."""
    # Coerce turns the ValueError into a schema error and still serializes cleanly.
    return vol.All(number(step=1, minimum=minimum), vol.Coerce(_whole_number))


def seconds_selector() -> selector.NumberSelector:
    """Return a non-negative duration in seconds."""
    return number(step=1, unit=UnitOfTime.SECONDS, minimum=0)


def max_age_selector() -> vol.All:
    """Return a strictly positive freshness limit in seconds."""
    return _positive(number(step=1, unit=UnitOfTime.SECONDS, minimum=0))


def temperature_delta_selector() -> selector.NumberSelector:
    """Return a non-negative temperature difference in degrees Celsius."""
    return number(step=0.1, unit=UnitOfTemperature.CELSIUS, minimum=0)


def name_selector() -> selector.TextSelector:
    """Return the free-text name selector."""
    return selector.TextSelector()


def sensor_selector(
    device_class: SensorDeviceClass | None = None, *, multiple: bool = False
) -> selector.EntitySelector:
    """Return a sensor picker, optionally filtered by device class."""
    config = selector.EntitySelectorConfig(domain="sensor", multiple=multiple)
    if device_class is not None:
        config["device_class"] = device_class
    return selector.EntitySelector(config)


def optional_entity(key: str, defaults: Mapping[str, Any]) -> vol.Optional:
    """Build an optional entity field that suggests a stored entity ID.

    A suggested value, unlike a default, lets the user clear the binding.
    """
    value = defaults.get(key)
    if isinstance(value, str) and value:
        return vol.Optional(key, description={"suggested_value": value})
    return vol.Optional(key)


def with_submitted_values(
    flow: config_entries.ConfigFlow | config_entries.ConfigSubentryFlow,
    schema: vol.Schema,
    user_input: Mapping[str, Any] | None,
) -> vol.Schema:
    """Re-show a rejected form with the values the user just submitted."""
    if user_input is None:
        return schema
    return flow.add_suggested_values_to_schema(schema, user_input)


def subentry_handle(draft: Mapping[str, Any]) -> dict[str, str]:
    """Store only the stable pointer needed for UI and entity ownership."""
    return {"id": str(draft["id"])}


async def async_persist_entry_data(
    flow: config_entries.ConfigFlow
    | config_entries.OptionsFlow
    | config_entries.ConfigSubentryFlow,
    entry: config_entries.ConfigEntry,
    data: Mapping[str, Any],
) -> bool:
    """Store edited Plant data once the Plant has safely reached Dry run.

    An active Plant first completes its safe shutdown through the runtime. When
    that cannot finish, nothing is stored and ``False`` is returned.
    """
    if not bool(entry.data.get(CONF_DRY_RUN, True)):
        runtime = getattr(entry, "runtime_data", None)
        if runtime is None or not await runtime.async_set_dry_run(True, hass=flow.hass):
            return False
    flow.hass.config_entries.async_update_entry(entry, data=dict(data))
    return True


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


def topology_select(
    options: list[selector.SelectOptionDict],
    *,
    multiple: bool,
) -> selector.SelectSelector:
    """Build a UUID-backed topology object selector."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=options, multiple=multiple)
    )


def cooling_reference_fields(defaults: Mapping[str, Any]) -> dict[Any, Any]:
    """Return the circuit cooling fields shared by initial and subentry forms."""
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


def effective_topology_error(
    entry: config_entries.ConfigEntry,
    *,
    proposed_sources: Sequence[Mapping[str, Any]] = (),
    excluded_subentry_id: str | None = None,
) -> StoredTopologyError | TopologyValidationError | OwnershipError | None:
    """Return why proposed source records are rejected, without mutating the entry.

    A reconfigured source replaces its stored record by id, so the excluded
    subentry needs no separate handling and is accepted for the source flow.
    """
    del excluded_subentry_id
    data: Mapping[str, Any] = entry.data
    try:
        for record in proposed_sources:
            data = data_with_source(data, record)
        effective_plant_from_data(data)
    except (StoredTopologyError, TopologyValidationError, OwnershipError) as error:
        return error
    return None


def circuit_cooling_error(error: Exception, circuit_id: str) -> str | None:
    """Explain a rejected cooling setting of one circuit, if that caused the rejection."""
    if isinstance(error, CoolingReferenceError) and error.circuit_id == circuit_id:
        return "cooling_reference_required"
    if isinstance(error, CoolingObservationError) and error.circuit_id == circuit_id:
        return "cooling_requires_zone_observations"
    return None


def warning_text(compiled: Any, sharing: Sequence[str] = ()) -> str:
    """Render compiler warnings, then outputs shared with other Plants, for a review form."""
    messages = [warning.message for warning in getattr(compiled, "warnings", ())]
    return "\n".join(f"- {message}" for message in (*messages, *sharing))


def warning_review_schema() -> vol.Schema:
    """Require an explicit acknowledgement before persisting warnings."""
    return vol.Schema(
        {
            vol.Required("confirm", default=False): selector.BooleanSelector(),
        }
    )


def dry_run_confirmation_schema() -> vol.Schema:
    """Require one explicit acknowledgement before enabling equipment control."""
    return vol.Schema(
        {
            vol.Required(CONF_DRY_RUN_CONFIRMATION, default=False): selector.BooleanSelector(),
        }
    )


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
            ): _positive(number(step="any", minimum=0)),
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
    """Return fields shared by initial and subentry zone forms."""
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
    circuit_options: list[selector.SelectOptionDict],
    defaults: Mapping[str, Any] | None = None,
    *,
    thermostat_kind: str = THERMOSTAT_KIND_HYDRONICUS,
    include_circuits: bool = True,
) -> vol.Schema:
    """Build the shared zone form schema."""
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
    if include_circuits:
        schema[
            vol.Required(
                CONF_CIRCUIT_IDS,
                default=defaults.get(CONF_CIRCUIT_IDS, vol.UNDEFINED),
            )
        ] = topology_select(circuit_options, multiple=True)
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


def thermostat_kind_schema(default: str = THERMOSTAT_KIND_HYDRONICUS) -> vol.Schema:
    """Build the first Zone step while accepting legacy test inputs as extras."""
    return vol.Schema(
        {
            vol.Optional(CONF_THERMOSTAT_KIND, default=default): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[THERMOSTAT_KIND_HYDRONICUS, THERMOSTAT_KIND_EXTERNAL_CLIMATE],
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key=CONF_THERMOSTAT_KIND,
                )
            )
        },
        extra=vol.ALLOW_EXTRA,
    )


def requires_sensor_metadata_path(data: Mapping[str, Any]) -> bool:
    """Return whether the selected policy requires the typed metadata editor."""
    return data.get(CONF_TEMPERATURE_AGGREGATION) in {
        TemperatureAggregation.DESIGNATED_REFERENCE.value,
        TemperatureAggregation.WEIGHTED_MEAN.value,
    }


def valve_feedback_fields(defaults: Mapping[str, Any]) -> dict[Any, Any]:
    """Return optional valve feedback fields shared by initial and actuator forms."""
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


if TYPE_CHECKING:
    _SubentryFlowBase = config_entries.ConfigSubentryFlow
else:
    _SubentryFlowBase = object


class SubentryReviewMixin(_SubentryFlowBase):
    """Save one drafted subentry, after a review step when there are warnings.

    The review lists non-fatal compiler warnings and outputs that another Plant
    already binds, and requires an explicit acknowledgement before saving.
    """

    _subentry_type: str
    _draft: dict[str, Any]
    _reconfigure: bool
    _review_warnings: str

    def _entry_data_with_draft(
        self, data: Mapping[str, Any], draft: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Return the Plant data with the draft applied, validated and in Dry run."""
        if self._subentry_type == SUBENTRY_TYPE_SOURCE:
            return data_with_source(data, draft)
        raise StoredTopologyError(f"Unsupported subentry type {self._subentry_type!r}.")

    async def _async_save_draft(
        self,
        draft: dict[str, Any],
        *,
        reconfigure: bool,
        warnings: str,
        errors: dict[str, str],
    ) -> config_entries.SubentryFlowResult | None:
        """Review warnings first, or save the draft now; ``None`` means the save failed."""
        self._draft = draft
        self._reconfigure = reconfigure
        if warnings:
            self._review_warnings = warnings
            return await self.async_step_review()
        if result := await self._async_persist_draft():
            return result
        errors["base"] = "dry_run_shutdown_in_progress"
        return None

    async def _async_persist_draft(self) -> config_entries.SubentryFlowResult | None:
        """Persist the draft graph and return its UI handle, or ``None`` if Dry run is pending."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry() if self._reconfigure else None
        if not await async_persist_entry_data(
            self, entry, self._entry_data_with_draft(entry.data, self._draft)
        ):
            return None
        if subentry is not None:
            return self.async_update_and_abort(
                entry,
                subentry,
                title=self._draft[CONF_NAME],
                data=subentry_handle(self._draft),
            )
        return self.async_create_entry(
            title=self._draft[CONF_NAME],
            data=subentry_handle(self._draft),
            unique_id=self._draft["id"],
        )

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Confirm the listed warnings before saving the drafted subentry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get("confirm", False):
                errors["base"] = "confirm_required"
            elif result := await self._async_persist_draft():
                return result
            else:
                errors["base"] = "dry_run_shutdown_in_progress"
        return self.async_show_form(
            step_id="review",
            data_schema=warning_review_schema(),
            errors=errors,
            description_placeholders={"warnings": self._review_warnings},
        )
