"""Config flow for Hydronicus."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as entity_registry_helper
from homeassistant.helpers import selector

from .const import (
    ACTUATOR_KIND_VALVE,
    CONF_ACTUATOR_KIND,
    CONF_AWAY_TARGET,
    CONF_CALIBRATION_OFFSET,
    CONF_CIRCUIT_IDS,
    CONF_CIRCUITS,
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
    CONF_FAULT_FEEDBACK_MAX_AGE,
    CONF_FLOW_FEEDBACK_ENTITY,
    CONF_FLOW_FEEDBACK_MAX_AGE,
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
    CONF_OVERRUN,
    CONF_PLANT_ID,
    CONF_POSITION_FEEDBACK_ENTITY,
    CONF_POSITION_FEEDBACK_MAX_AGE,
    CONF_POWER_FEEDBACK_ENTITY,
    CONF_POWER_FEEDBACK_MAX_AGE,
    CONF_PRESET_TARGETS,
    CONF_PUMP_ENTITY,
    CONF_PUMP_ID,
    CONF_PUMP_OVERRUN,
    CONF_PUMPS,
    CONF_REQUIRED,
    CONF_ROUTES,
    CONF_SENSOR_ENTITY,
    CONF_SOURCE_AVAILABILITY_ENTITY,
    CONF_SOURCE_DEMAND_ENTITY,
    CONF_SOURCE_HYSTERESIS,
    CONF_SOURCE_MAXIMUM_AGE,
    CONF_SOURCE_MINIMUM_TEMPERATURE,
    CONF_SOURCE_PRIORITY,
    CONF_SOURCE_TEMPERATURE_ENTITY,
    CONF_SOURCE_TYPE,
    CONF_SUPPLY_TEMPERATURE_MAX_AGE,
    CONF_SUPPLY_TEMPERATURE_SENSOR,
    CONF_SURFACE_TEMPERATURE_MAX_AGE,
    CONF_SURFACE_TEMPERATURE_SENSOR,
    CONF_TEMPERATURE_AGGREGATION,
    CONF_TEMPERATURE_SENSOR_METADATA,
    CONF_TEMPERATURE_SENSORS,
    CONF_THERMOSTAT,
    CONF_THERMOSTAT_KIND,
    CONF_TOPOLOGY,
    CONF_VALVE_ENTITY,
    CONF_VALVE_IDS,
    CONF_VALVE_OPENING_TIME,
    CONF_VALVE_READINESS_ENTITY,
    CONF_VALVES,
    CONF_WEIGHT,
    CONF_ZONE_IDS,
    CONF_ZONES,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DEFAULT_CONDENSATION_MARGIN,
    DEFAULT_COOLING_START_DELTA,
    DEFAULT_COOLING_STOP_DELTA,
    DEFAULT_HEATING_START_DELTA,
    DEFAULT_HEATING_STOP_DELTA,
    DEFAULT_MINIMUM_ACTIVE_DURATION,
    DEFAULT_MINIMUM_IDLE_DURATION,
    DEFAULT_PLANT_NAME,
    DEFAULT_PUMP_OVERRUN,
    DEFAULT_REFERENCE_MAX_AGE,
    DEFAULT_SENSOR_MAX_AGE,
    DEFAULT_SENSOR_WEIGHT,
    DEFAULT_SOURCE_HYSTERESIS,
    DEFAULT_SOURCE_MAXIMUM_AGE,
    DEFAULT_SOURCE_PRIORITY,
    DEFAULT_TARGET_TEMPERATURE,
    DEFAULT_TEMPERATURE_AGGREGATION,
    DEFAULT_VALVE_OPENING_TIME,
    DOMAIN,
    SOURCE_KIND_BUFFER,
    SOURCE_KIND_EXTERNAL,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_CIRCUIT,
    SUBENTRY_TYPE_SOURCE,
    SUBENTRY_TYPE_ZONE,
    THERMOSTAT_KIND_EXTERNAL_CLIMATE,
    THERMOSTAT_KIND_HYDRONICUS,
)
from .core.configuration import (
    BufferTemperatureRequiredError,
    DesignatedReferenceError,
    StoredTopologyError,
    plant_configuration_from_entry_data,
)
from .core.model import (
    MAX_ZONE_TARGET_TEMPERATURE,
    MIN_ZONE_TARGET_TEMPERATURE,
    CompiledPlant,
    TemperatureAggregation,
)
from .core.topology import (
    CoolingObservationError,
    CoolingReferenceError,
    DuplicateActuatorBindingError,
    TopologyValidationError,
    compile_topology,
)
from .entry_configuration import (
    authorization_output_lines,
    authorize_outputs,
    effective_plant_configuration,
    entry_data_with_subentry_draft,
    invalidate_output_authorization,
    output_authorization,
    subentry_draft,
    subentry_owned_ids,
)


@dataclass(frozen=True, slots=True)
class CircuitOptions:
    """Parent-owned topology choices available to a circuit flow."""

    zones: list[selector.SelectOptionDict]
    valves: list[selector.SelectOptionDict]
    pumps: list[selector.SelectOptionDict]


SECTION_FEEDBACK: Final = "feedback"
SECTION_COOLING: Final = "cooling"
_FORM_SECTIONS: Final = (SECTION_FEEDBACK, SECTION_COOLING)
_DEFAULT_FEEDBACK_MAX_AGE: Final = 1800.0


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
    }
)


def _entity_ids_in(value: Any) -> set[str]:
    """Return the entity IDs held by a single or multiple entity field value."""
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, (list, tuple)):
        return {item for item in value if isinstance(item, str) and item}
    return set()


def _is_hydronicus_owned(hass: Any, entity_id: str) -> bool:
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
    return any(_is_hydronicus_owned(hass, entity_id) for entity_id in _entity_ids_in(value))


def _own_entity_errors(hass: Any, user_input: Mapping[str, Any]) -> dict[str, str]:
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


class _OwnEntityPickerMixin:
    """Keep Hydronicus entities out of the entity pickers of every form.

    Selecting one, such as a zone's aggregate temperature, would create a feedback loop.
    """

    hass: Any

    def async_show_form(self, *, data_schema: vol.Schema | None = None, **kwargs: Any) -> Any:
        """Show a form whose entity pickers exclude this integration's entities."""
        if data_schema is not None:
            data_schema = _schema_without_own_entities(data_schema, _own_entity_ids(self.hass))
        return super().async_show_form(data_schema=data_schema, **kwargs)  # type: ignore[misc]


def _flatten_sections(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Merge collapsible form sections back into the flat persisted field layout."""
    flat = {key: value for key, value in user_input.items() if key not in _FORM_SECTIONS}
    for section_key in _FORM_SECTIONS:
        nested = user_input.get(section_key)
        if isinstance(nested, Mapping):
            flat.update(nested)
    return flat


def _collapsed_section(fields: Mapping[Any, Any]) -> section:
    """Wrap optional fields in a collapsed form section."""
    return section(vol.Schema(dict(fields)), {"collapsed": True})


def _number(
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


def _seconds_selector() -> selector.NumberSelector:
    """Return a non-negative duration in seconds."""
    return _number(step=1, unit=UnitOfTime.SECONDS, minimum=0)


def _max_age_selector() -> vol.All:
    """Return a strictly positive freshness limit in seconds."""
    return _positive(_number(step=1, unit=UnitOfTime.SECONDS, minimum=0))


def _temperature_delta_selector() -> selector.NumberSelector:
    """Return a non-negative temperature difference in degrees Celsius."""
    return _number(step=0.1, unit=UnitOfTemperature.CELSIUS, minimum=0)


def _name_selector() -> selector.TextSelector:
    """Return the free-text name selector."""
    return selector.TextSelector()


def _sensor_selector(
    device_class: SensorDeviceClass | None = None, *, multiple: bool = False
) -> selector.EntitySelector:
    """Return a sensor picker, optionally filtered by device class."""
    config = selector.EntitySelectorConfig(domain="sensor", multiple=multiple)
    if device_class is not None:
        config["device_class"] = device_class
    return selector.EntitySelector(config)


def _optional_entity(key: str, defaults: Mapping[str, Any]) -> vol.Optional:
    """Build an optional entity field that suggests a stored entity ID.

    A suggested value, unlike a default, lets the user clear the binding.
    """
    value = defaults.get(key)
    if isinstance(value, str) and value:
        return vol.Optional(key, description={"suggested_value": value})
    return vol.Optional(key)


def _with_submitted_values(
    flow: config_entries.ConfigFlow | config_entries.ConfigSubentryFlow,
    schema: vol.Schema,
    user_input: Mapping[str, Any] | None,
) -> vol.Schema:
    """Re-show a rejected form with the values the user just submitted."""
    if user_input is None:
        return schema
    return flow.add_suggested_values_to_schema(schema, user_input)


def _subentry_handle(draft: Mapping[str, Any]) -> dict[str, str]:
    """Store only the stable pointer needed for UI and entity ownership."""
    return {"id": str(draft["id"])}


async def _async_persist_subentry_graph(
    flow: config_entries.ConfigSubentryFlow,
    entry: config_entries.ConfigEntry,
    subentry_type: str,
    draft: Mapping[str, Any],
    *,
    excluded_subentry_id: str | None = None,
) -> bool:
    """Safely persist one complete graph mutation before returning its UI handle."""
    if not bool(entry.data.get(CONF_DRY_RUN, True)):
        runtime = getattr(entry, "runtime_data", None)
        if runtime is None or not await runtime.async_set_dry_run(True, hass=flow.hass):
            return False
    data = entry_data_with_subentry_draft(
        entry,
        subentry_type,
        draft,
        excluded_subentry_id=excluded_subentry_id,
    )
    flow.hass.config_entries.async_update_entry(entry, data=data)
    return True


def _routes_with_retained_fields(
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


def _circuit_data(
    user_input: Mapping[str, Any],
    circuit_id: str,
    existing_routes: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize one circuit and preserve route UUIDs for retained zones."""
    user_input = _flatten_sections(user_input)
    zone_ids = list(user_input[CONF_ZONE_IDS])
    cooling_enabled = user_input.get(CONF_COOLING_ENABLED, False)
    if not isinstance(cooling_enabled, bool):
        raise ValueError("Cooling enablement must be an explicit boolean.")
    return {
        "id": circuit_id,
        CONF_NAME: str(user_input[CONF_NAME]).strip(),
        CONF_ZONE_IDS: zone_ids,
        CONF_VALVE_IDS: list(user_input[CONF_VALVE_IDS]),
        CONF_PUMP_ID: user_input[CONF_PUMP_ID],
        CONF_COOLING_ENABLED: cooling_enabled,
        CONF_SUPPLY_TEMPERATURE_SENSOR: user_input.get(CONF_SUPPLY_TEMPERATURE_SENSOR),
        CONF_SURFACE_TEMPERATURE_SENSOR: user_input.get(CONF_SURFACE_TEMPERATURE_SENSOR),
        CONF_CONDENSATION_MARGIN: user_input.get(
            CONF_CONDENSATION_MARGIN, DEFAULT_CONDENSATION_MARGIN
        ),
        CONF_SUPPLY_TEMPERATURE_MAX_AGE: user_input.get(
            CONF_SUPPLY_TEMPERATURE_MAX_AGE, DEFAULT_REFERENCE_MAX_AGE
        ),
        CONF_SURFACE_TEMPERATURE_MAX_AGE: user_input.get(
            CONF_SURFACE_TEMPERATURE_MAX_AGE, DEFAULT_REFERENCE_MAX_AGE
        ),
        CONF_ROUTES: _routes_with_retained_fields(
            existing_routes,
            relationship_key="zone_id",
            relationship_ids=zone_ids,
        ),
    }


def _topology_select(
    options: list[selector.SelectOptionDict],
    *,
    multiple: bool,
) -> selector.SelectSelector:
    """Build a UUID-backed topology object selector."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=options, multiple=multiple)
    )


def _cooling_reference_fields(defaults: Mapping[str, Any]) -> dict[Any, Any]:
    """Return the circuit cooling fields shared by initial and subentry forms."""
    return {
        vol.Optional(
            CONF_COOLING_ENABLED, default=defaults.get(CONF_COOLING_ENABLED, False)
        ): selector.BooleanSelector(),
        _optional_entity(CONF_SUPPLY_TEMPERATURE_SENSOR, defaults): _sensor_selector(
            SensorDeviceClass.TEMPERATURE
        ),
        _optional_entity(CONF_SURFACE_TEMPERATURE_SENSOR, defaults): _sensor_selector(
            SensorDeviceClass.TEMPERATURE
        ),
        vol.Optional(
            CONF_CONDENSATION_MARGIN,
            default=defaults.get(CONF_CONDENSATION_MARGIN, DEFAULT_CONDENSATION_MARGIN),
        ): _temperature_delta_selector(),
        vol.Optional(
            CONF_SUPPLY_TEMPERATURE_MAX_AGE,
            default=defaults.get(CONF_SUPPLY_TEMPERATURE_MAX_AGE, DEFAULT_REFERENCE_MAX_AGE),
        ): _max_age_selector(),
        vol.Optional(
            CONF_SURFACE_TEMPERATURE_MAX_AGE,
            default=defaults.get(CONF_SURFACE_TEMPERATURE_MAX_AGE, DEFAULT_REFERENCE_MAX_AGE),
        ): _max_age_selector(),
    }


def _circuit_schema(
    options: CircuitOptions,
    *,
    defaults: Mapping[str, Any] | None = None,
) -> vol.Schema:
    """Build the shared circuit form schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)
            ): _name_selector(),
            vol.Required(
                CONF_ZONE_IDS, default=defaults.get(CONF_ZONE_IDS, vol.UNDEFINED)
            ): _topology_select(options.zones, multiple=True),
            vol.Required(
                CONF_VALVE_IDS, default=defaults.get(CONF_VALVE_IDS, vol.UNDEFINED)
            ): _topology_select(options.valves, multiple=True),
            vol.Required(
                CONF_PUMP_ID, default=defaults.get(CONF_PUMP_ID, vol.UNDEFINED)
            ): _topology_select(options.pumps, multiple=False),
            vol.Optional(SECTION_COOLING): _collapsed_section(_cooling_reference_fields(defaults)),
        }
    )


def _effective_topology_error(
    entry: config_entries.ConfigEntry,
    *,
    proposed_actuators: Sequence[Mapping[str, Any]] = (),
    proposed_circuits: Sequence[Mapping[str, Any]] = (),
    proposed_zones: Sequence[Mapping[str, Any]] = (),
    proposed_sources: Sequence[Mapping[str, Any]] = (),
    excluded_subentry_id: str | None = None,
) -> StoredTopologyError | TopologyValidationError | None:
    """Return why a complete proposed topology is rejected, without mutating the entry."""
    try:
        effective = effective_plant_configuration(
            entry,
            proposed_actuators=proposed_actuators,
            proposed_circuits=proposed_circuits,
            proposed_zones=proposed_zones,
            proposed_sources=proposed_sources,
            excluded_subentry_id=excluded_subentry_id,
        )
        compile_topology(effective.configuration)
    except (StoredTopologyError, TopologyValidationError) as error:
        return error
    return None


def _circuit_cooling_error(error: Exception, circuit_id: str) -> str | None:
    """Explain a rejected cooling setting of one circuit, if that caused the rejection."""
    if isinstance(error, CoolingReferenceError) and error.circuit_id == circuit_id:
        return "cooling_reference_required"
    if isinstance(error, CoolingObservationError) and error.circuit_id == circuit_id:
        return "cooling_requires_zone_observations"
    return None


def _effective_topology_compile(
    entry: config_entries.ConfigEntry,
    *,
    proposed_actuators: Sequence[Mapping[str, Any]] = (),
    proposed_circuits: Sequence[Mapping[str, Any]] = (),
    proposed_zones: Sequence[Mapping[str, Any]] = (),
    proposed_sources: Sequence[Mapping[str, Any]] = (),
    excluded_subentry_id: str | None = None,
) -> CompiledPlant | None:
    """Compile a complete proposed topology without mutating the config entry."""
    try:
        effective = effective_plant_configuration(
            entry,
            proposed_actuators=proposed_actuators,
            proposed_circuits=proposed_circuits,
            proposed_zones=proposed_zones,
            proposed_sources=proposed_sources,
            excluded_subentry_id=excluded_subentry_id,
        )
        return compile_topology(effective.configuration)
    except StoredTopologyError, TopologyValidationError:
        return None


def _warning_text(compiled: Any) -> str:
    """Render structured compiler warnings for a confirmation form."""
    warnings = getattr(compiled, "warnings", ())
    return "\n".join(f"- {warning.message}" for warning in warnings)


def _initial_review_placeholders(
    topology: Mapping[str, Any],
    compiled: CompiledPlant | None,
    validation_error: str | None = None,
) -> dict[str, str]:
    """Render complete initial-review context, including validation failures."""
    logic = (
        "\n".join(f"- {line}" for line in compiled.logic_summary)
        if compiled is not None
        else f"- Topology could not be compiled: {validation_error or 'unknown validation error'}"
    )
    return {
        "zone": str(topology[CONF_ZONES][0][CONF_NAME]),
        "circuit": str(topology[CONF_CIRCUITS][0][CONF_NAME]),
        "logic": logic,
        "warnings": _warning_text(compiled) or "- None",
        "outputs": authorization_output_lines({CONF_PLANT_ID: "pending", CONF_TOPOLOGY: topology}),
    }


def _warning_review_schema() -> vol.Schema:
    """Require an explicit acknowledgement before persisting warnings."""
    return vol.Schema(
        {
            vol.Required("confirm", default=False): selector.BooleanSelector(),
        }
    )


def _dry_run_confirmation_schema() -> vol.Schema:
    """Require one explicit acknowledgement before enabling equipment control."""
    return vol.Schema(
        {
            vol.Required(CONF_DRY_RUN_CONFIRMATION, default=False): selector.BooleanSelector(),
        }
    )


def _dry_run_reconfigure_schema(default: bool) -> vol.Schema:
    """Return the Plant Dry run reconfigure schema."""
    return vol.Schema(
        {
            vol.Required(CONF_DRY_RUN, default=default): selector.BooleanSelector(),
        }
    )


def _circuit_validation_errors(
    entry: config_entries.ConfigEntry,
    data: Mapping[str, Any],
    *,
    excluded_subentry_id: str | None = None,
) -> dict[str, str]:
    """Return flow errors after validating a proposed circuit atomically."""
    if not data[CONF_NAME]:
        return {"base": "name_required"}
    error = _effective_topology_error(
        entry,
        proposed_circuits=(data,),
        excluded_subentry_id=excluded_subentry_id,
    )
    if error is None:
        return {}
    if cooling_error := _circuit_cooling_error(error, str(data["id"])):
        return {"base": cooling_error}
    return {"base": "invalid_circuit"}


class CircuitSubentryFlowHandler(_OwnEntityPickerMixin, config_entries.ConfigSubentryFlow):
    """Add a circuit and its delivery routes to existing plant objects."""

    _draft: dict[str, Any]
    _draft_compiled: CompiledPlant
    _reconfigure: bool

    def _options(self) -> CircuitOptions:
        """Return parent-owned dependencies with deletion-safe lifecycles."""
        entry = self._get_entry()
        configuration = plant_configuration_from_entry_data(entry.data)
        dynamic_zone_ids = subentry_owned_ids(entry.data, SUBENTRY_TYPE_ZONE)
        dynamic_valve_ids = subentry_owned_ids(entry.data, SUBENTRY_TYPE_ACTUATOR)
        return CircuitOptions(
            zones=[
                selector.SelectOptionDict(value=zone.id, label=zone.name)
                for zone in configuration.zones
                if zone.id not in dynamic_zone_ids
            ],
            valves=[
                selector.SelectOptionDict(value=valve.id, label=valve.name)
                for valve in configuration.valves
                if valve.id not in dynamic_valve_ids
            ],
            pumps=[
                selector.SelectOptionDict(value=pump.id, label=pump.name)
                for pump in configuration.pumps
            ],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Create one circuit serving one or more existing zones."""
        entry = self._get_entry()
        options = self._options()
        if not options.zones or not options.valves or not options.pumps:
            return self.async_abort(reason="incomplete_plant")

        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_ZONE_IDS):
                errors[CONF_ZONE_IDS] = "zones_required"
            if not user_input.get(CONF_VALVE_IDS):
                errors[CONF_VALVE_IDS] = "valves_required"
            errors.update(_own_entity_errors(self.hass, user_input))
        if user_input is not None and not errors:
            circuit_id = str(uuid4())
            data = _circuit_data(user_input, circuit_id)
            if validation_errors := _circuit_validation_errors(entry, data):
                errors.update(validation_errors)
            else:
                self._draft = data
                self._reconfigure = False
                compiled = _effective_topology_compile(
                    entry,
                    proposed_circuits=(data,),
                )
                if compiled is not None and compiled.warnings:
                    self._draft_compiled = compiled
                    return await self.async_step_review()
                if await _async_persist_subentry_graph(
                    self,
                    entry,
                    SUBENTRY_TYPE_CIRCUIT,
                    data,
                ):
                    return self.async_create_entry(
                        title=data[CONF_NAME], data=_subentry_handle(data), unique_id=circuit_id
                    )
                errors["base"] = "dry_run_shutdown_in_progress"

        return self.async_show_form(
            step_id="user",
            data_schema=_with_submitted_values(self, _circuit_schema(options), user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Update a circuit without changing retained circuit or route UUIDs."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        defaults = subentry_draft(entry, subentry)
        options = self._options()
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_ZONE_IDS):
                errors[CONF_ZONE_IDS] = "zones_required"
            if not user_input.get(CONF_VALVE_IDS):
                errors[CONF_VALVE_IDS] = "valves_required"
            errors.update(_own_entity_errors(self.hass, user_input))
        if user_input is not None and not errors:
            data = _circuit_data(
                user_input,
                defaults["id"],
                defaults[CONF_ROUTES],
            )
            if validation_errors := _circuit_validation_errors(
                entry,
                data,
                excluded_subentry_id=subentry.subentry_id,
            ):
                errors.update(validation_errors)
            else:
                self._draft = data
                self._reconfigure = True
                compiled = _effective_topology_compile(
                    entry,
                    proposed_circuits=(data,),
                    excluded_subentry_id=subentry.subentry_id,
                )
                if compiled is not None and compiled.warnings:
                    self._draft_compiled = compiled
                    return await self.async_step_review()
                if await _async_persist_subentry_graph(
                    self,
                    entry,
                    SUBENTRY_TYPE_CIRCUIT,
                    data,
                    excluded_subentry_id=subentry.subentry_id,
                ):
                    return self.async_update_and_abort(
                        entry,
                        subentry,
                        title=data[CONF_NAME],
                        data=_subentry_handle(data),
                    )
                errors["base"] = "dry_run_shutdown_in_progress"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_with_submitted_values(
                self, _circuit_schema(options, defaults=defaults), user_input
            ),
            errors=errors,
        )

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Confirm structured warnings before saving the proposed circuit."""
        if user_input is not None:
            if not user_input.get("confirm", False):
                return self.async_show_form(
                    step_id="review",
                    data_schema=_warning_review_schema(),
                    errors={"base": "confirm_required"},
                    description_placeholders={"warnings": _warning_text(self._draft_compiled)},
                )
            if self._reconfigure:
                subentry = self._get_reconfigure_subentry()
                if not await _async_persist_subentry_graph(
                    self,
                    self._get_entry(),
                    SUBENTRY_TYPE_CIRCUIT,
                    self._draft,
                    excluded_subentry_id=subentry.subentry_id,
                ):
                    return self.async_show_form(
                        step_id="review",
                        data_schema=_warning_review_schema(),
                        errors={"base": "dry_run_shutdown_in_progress"},
                        description_placeholders={"warnings": _warning_text(self._draft_compiled)},
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=self._draft[CONF_NAME],
                    data=_subentry_handle(self._draft),
                )
            if not await _async_persist_subentry_graph(
                self,
                self._get_entry(),
                SUBENTRY_TYPE_CIRCUIT,
                self._draft,
            ):
                return self.async_show_form(
                    step_id="review",
                    data_schema=_warning_review_schema(),
                    errors={"base": "dry_run_shutdown_in_progress"},
                    description_placeholders={"warnings": _warning_text(self._draft_compiled)},
                )
            return self.async_create_entry(
                title=self._draft[CONF_NAME],
                data=_subentry_handle(self._draft),
                unique_id=self._draft["id"],
            )
        return self.async_show_form(
            step_id="review",
            data_schema=_warning_review_schema(),
            description_placeholders={"warnings": _warning_text(self._draft_compiled)},
        )


def _zone_data(
    user_input: Mapping[str, Any],
    zone_id: str,
    existing_routes: list[Mapping[str, Any]] | None = None,
    existing_metadata: list[Mapping[str, Any]] | None = None,
    existing_humidity_metadata: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize one zone and preserve route UUIDs for retained circuits."""
    user_input = _flatten_sections(user_input)
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
        CONF_ROUTES: _routes_with_retained_fields(
            existing_routes,
            relationship_key="circuit_id",
            relationship_ids=circuit_ids,
        ),
    }


def _sensor_metadata_schema(
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
            ): _sensor_selector(SensorDeviceClass.TEMPERATURE),
            vol.Required(
                CONF_REQUIRED,
                default=defaults.get(CONF_REQUIRED, True),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_WEIGHT,
                default=defaults.get(CONF_WEIGHT, DEFAULT_SENSOR_WEIGHT),
            ): _positive(_number(step="any", minimum=0)),
            vol.Required(
                CONF_CALIBRATION_OFFSET,
                default=defaults.get(CONF_CALIBRATION_OFFSET, 0.0),
            ): _number(step="any", unit=UnitOfTemperature.CELSIUS),
            vol.Required(
                CONF_MAX_AGE,
                default=defaults.get(CONF_MAX_AGE, DEFAULT_SENSOR_MAX_AGE),
            ): _max_age_selector(),
            vol.Required(
                CONF_DESIGNATED_REFERENCE,
                default=defaults.get(CONF_DESIGNATED_REFERENCE, False),
            ): selector.BooleanSelector(),
        }
    )


def _sensor_metadata_record(user_input: Mapping[str, Any]) -> dict[str, Any]:
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
        fields[key] = _number(
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
        ): _temperature_delta_selector(),
        vol.Required(
            CONF_HEATING_STOP_DELTA,
            default=defaults.get(CONF_HEATING_STOP_DELTA, DEFAULT_HEATING_STOP_DELTA),
        ): _temperature_delta_selector(),
        vol.Required(
            CONF_MINIMUM_ACTIVE_DURATION,
            default=defaults.get(CONF_MINIMUM_ACTIVE_DURATION, DEFAULT_MINIMUM_ACTIVE_DURATION),
        ): _seconds_selector(),
        vol.Required(
            CONF_MINIMUM_IDLE_DURATION,
            default=defaults.get(CONF_MINIMUM_IDLE_DURATION, DEFAULT_MINIMUM_IDLE_DURATION),
        ): _seconds_selector(),
        **_preset_targets_schema(defaults),
        vol.Optional(SECTION_COOLING): _collapsed_section(
            {
                vol.Required(
                    CONF_COOLING_START_DELTA,
                    default=defaults.get(CONF_COOLING_START_DELTA, DEFAULT_COOLING_START_DELTA),
                ): _temperature_delta_selector(),
                vol.Required(
                    CONF_COOLING_STOP_DELTA,
                    default=defaults.get(CONF_COOLING_STOP_DELTA, DEFAULT_COOLING_STOP_DELTA),
                ): _temperature_delta_selector(),
            }
        ),
    }


def _zone_temperature_sensor_defaults(defaults: Mapping[str, Any]) -> Any:
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


def _sensor_policy_schema(zone_draft: Mapping[str, Any]) -> vol.Schema:
    """Build the aggregation form offered after sensor metadata editing."""
    return vol.Schema(
        {
            vol.Required(
                CONF_TEMPERATURE_AGGREGATION,
                default=_zone_temperature_aggregation_default(zone_draft),
            ): _temperature_aggregation_selector(include_metadata_policies=True),
        }
    )


def _zone_schema(
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
        vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)): _name_selector(),
        (vol.Required if thermostat_kind == THERMOSTAT_KIND_HYDRONICUS else vol.Optional)(
            CONF_TEMPERATURE_SENSORS,
            default=_zone_temperature_sensor_defaults(defaults),
        ): _sensor_selector(SensorDeviceClass.TEMPERATURE, multiple=True),
        vol.Optional(
            CONF_HUMIDITY_SENSORS,
            default=_zone_humidity_sensor_defaults(defaults),
        ): _sensor_selector(SensorDeviceClass.HUMIDITY, multiple=True),
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
        ] = _topology_select(circuit_options, multiple=True)
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


def _thermostat_kind_schema(default: str = THERMOSTAT_KIND_HYDRONICUS) -> vol.Schema:
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


def _zone_validation_errors(
    entry: config_entries.ConfigEntry,
    data: Mapping[str, Any],
    *,
    excluded_subentry_id: str | None = None,
) -> dict[str, str]:
    """Return flow errors after validating a proposed zone atomically."""
    if not data[CONF_NAME]:
        return {"base": "name_required"}
    error = _effective_topology_error(
        entry,
        proposed_zones=(data,),
        excluded_subentry_id=excluded_subentry_id,
    )
    if error is None:
        return {}
    zone_id = str(data["id"])
    if isinstance(error, CoolingObservationError) and error.zone_id == zone_id:
        if error.observation == "humidity":
            return {CONF_HUMIDITY_SENSORS: "humidity_required_for_cooling"}
        return {CONF_TEMPERATURE_SENSORS: "temperature_required_for_cooling"}
    if isinstance(error, DesignatedReferenceError) and error.zone_id == zone_id:
        return {"base": "designated_reference_count"}
    return {"base": "invalid_zone"}


def _requires_sensor_metadata_path(data: Mapping[str, Any]) -> bool:
    """Return whether the selected policy requires the typed metadata editor."""
    return data.get(CONF_TEMPERATURE_AGGREGATION) in {
        TemperatureAggregation.DESIGNATED_REFERENCE.value,
        TemperatureAggregation.WEIGHTED_MEAN.value,
    }


class ZoneSubentryFlowHandler(_OwnEntityPickerMixin, config_entries.ConfigSubentryFlow):
    """Add a comfort zone routed through existing parent-owned circuits."""

    _zone_draft: dict[str, Any]
    _metadata_records: list[dict[str, Any]]
    _metadata_index: int
    _zone_reconfigure: bool
    _zone_compiled: CompiledPlant
    _selected_thermostat_kind: str

    def _circuit_options(self) -> list[selector.SelectOptionDict]:
        entry = self._get_entry()
        configuration = plant_configuration_from_entry_data(entry.data)
        dynamic_circuit_ids = subentry_owned_ids(entry.data, SUBENTRY_TYPE_CIRCUIT)
        return [
            selector.SelectOptionDict(value=circuit.id, label=circuit.name)
            for circuit in configuration.circuits
            if circuit.id not in dynamic_circuit_ids
        ]

    async def _finish_zone(self) -> config_entries.SubentryFlowResult:
        """Validate and persist the completed zone draft as one atomic operation."""
        entry = self._get_entry()
        excluded_subentry_id = None
        if self._zone_reconfigure:
            excluded_subentry_id = self._get_reconfigure_subentry().subentry_id
        if errors := _zone_validation_errors(
            entry,
            self._zone_draft,
            excluded_subentry_id=excluded_subentry_id,
        ):
            # The policy form has no sensor fields, so a field error is shown as the form error.
            return self._sensor_policy_form(errors[next(iter(errors))])
        compiled = _effective_topology_compile(
            entry,
            proposed_zones=(self._zone_draft,),
            excluded_subentry_id=excluded_subentry_id,
        )
        if compiled is None:
            return self._sensor_policy_form("invalid_zone")
        if compiled.warnings:
            self._zone_compiled = compiled
            return await self.async_step_review()
        if self._zone_reconfigure:
            subentry = self._get_reconfigure_subentry()
            if not await _async_persist_subentry_graph(
                self,
                entry,
                SUBENTRY_TYPE_ZONE,
                self._zone_draft,
                excluded_subentry_id=subentry.subentry_id,
            ):
                return self._sensor_policy_form("dry_run_shutdown_in_progress")
            return self.async_update_and_abort(
                entry,
                subentry,
                title=self._zone_draft[CONF_NAME],
                data=_subentry_handle(self._zone_draft),
            )
        if not await _async_persist_subentry_graph(
            self,
            entry,
            SUBENTRY_TYPE_ZONE,
            self._zone_draft,
        ):
            return self._sensor_policy_form("dry_run_shutdown_in_progress")
        return self.async_create_entry(
            title=self._zone_draft[CONF_NAME],
            data=_subentry_handle(self._zone_draft),
            unique_id=self._zone_draft["id"],
        )

    async def async_step_sensor_metadata(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Edit one sensor at a time so weights and safety metadata stay typed."""
        sensor_ids = _zone_temperature_sensor_defaults(self._zone_draft)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _own_entity_errors(self.hass, user_input)
            if not errors:
                self._metadata_records.append(_sensor_metadata_record(user_input))
                self._metadata_index += 1
        if self._metadata_index < len(sensor_ids):
            sensor_id = sensor_ids[self._metadata_index]
            defaults: Mapping[str, Any] = next(
                (
                    record
                    for record in self._zone_draft[CONF_TEMPERATURE_SENSOR_METADATA]
                    if record.get("entity_id") == sensor_id
                ),
                {},
            )
            return self.async_show_form(
                step_id="sensor_metadata",
                data_schema=_with_submitted_values(
                    self,
                    _sensor_metadata_schema(sensor_id, defaults),
                    user_input if errors else None,
                ),
                errors=errors,
                description_placeholders={"sensor": sensor_id},
            )
        if self._metadata_records:
            self._zone_draft[CONF_TEMPERATURE_SENSOR_METADATA] = self._metadata_records
        return await self.async_step_sensor_policy()

    async def async_step_sensor_policy(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Choose policies that require the completed editable sensor metadata path."""
        if user_input is not None:
            self._zone_draft[CONF_TEMPERATURE_AGGREGATION] = user_input[
                CONF_TEMPERATURE_AGGREGATION
            ]
            return await self._finish_zone()
        return self._sensor_policy_form()

    def _sensor_policy_form(self, error: str | None = None) -> config_entries.SubentryFlowResult:
        """Show the aggregation policy form, optionally with a retryable error."""
        return self.async_show_form(
            step_id="sensor_policy",
            data_schema=_sensor_policy_schema(self._zone_draft),
            errors={"base": error} if error else None,
        )

    def _details_form(
        self,
        user_input: Mapping[str, Any],
        kind: str,
        *,
        reconfigure: bool,
        errors: dict[str, str],
    ) -> config_entries.SubentryFlowResult:
        """Re-show the Zone details form with the submitted values and errors."""
        self._selected_thermostat_kind = kind
        self._zone_reconfigure = reconfigure
        defaults = (
            subentry_draft(self._get_entry(), self._get_reconfigure_subentry())
            if reconfigure
            else None
        )
        schema = _zone_schema(self._circuit_options(), defaults, thermostat_kind=kind)
        return self.async_show_form(
            step_id="details",
            data_schema=_with_submitted_values(self, schema, user_input),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Choose the thermostat owner before collecting Zone-specific fields."""
        circuit_options = self._circuit_options()
        if not circuit_options:
            return self.async_abort(reason="no_circuits")
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=_thermostat_kind_schema())
        kind = str(user_input.get(CONF_THERMOSTAT_KIND, THERMOSTAT_KIND_HYDRONICUS))
        if set(user_input) <= {CONF_THERMOSTAT_KIND}:
            self._selected_thermostat_kind = kind
            self._zone_reconfigure = False
            return await self.async_step_details()
        return await self._async_process_zone_input(user_input, kind, reconfigure=False)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Choose the thermostat owner before updating the Zone."""
        subentry = self._get_reconfigure_subentry()
        defaults = subentry_draft(self._get_entry(), subentry)
        thermostat = defaults.get(CONF_THERMOSTAT, {})
        default_kind = (
            str(thermostat.get("kind", THERMOSTAT_KIND_HYDRONICUS))
            if isinstance(thermostat, Mapping)
            else THERMOSTAT_KIND_HYDRONICUS
        )
        if user_input is None:
            return self.async_show_form(
                step_id="reconfigure", data_schema=_thermostat_kind_schema(default_kind)
            )
        kind = str(user_input.get(CONF_THERMOSTAT_KIND, default_kind))
        if set(user_input) <= {CONF_THERMOSTAT_KIND}:
            self._selected_thermostat_kind = kind
            self._zone_reconfigure = True
            return await self.async_step_details()
        return await self._async_process_zone_input(user_input, kind, reconfigure=True)

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Collect only the fields owned by the selected thermostat kind."""
        defaults: Mapping[str, Any] | None = None
        if self._zone_reconfigure:
            subentry = self._get_reconfigure_subentry()
            defaults = subentry_draft(self._get_entry(), subentry)
        if user_input is not None:
            return await self._async_process_zone_input(
                {**user_input, CONF_THERMOSTAT_KIND: self._selected_thermostat_kind},
                self._selected_thermostat_kind,
                reconfigure=self._zone_reconfigure,
            )
        return self.async_show_form(
            step_id="details",
            data_schema=_zone_schema(
                self._circuit_options(),
                defaults,
                thermostat_kind=self._selected_thermostat_kind,
            ),
        )

    async def _async_process_zone_input(
        self,
        user_input: Mapping[str, Any],
        kind: str,
        *,
        reconfigure: bool,
    ) -> config_entries.SubentryFlowResult:
        """Validate one complete thermostat-specific Zone form."""
        # vol.Required accepts an empty list, which a lazily loaded frontend picker
        # can submit, so required selections are checked before normalization.
        errors: dict[str, str] = {}
        if kind == THERMOSTAT_KIND_HYDRONICUS and not user_input.get(CONF_TEMPERATURE_SENSORS):
            errors[CONF_TEMPERATURE_SENSORS] = "temperature_sensors_required"
        if not user_input.get(CONF_CIRCUIT_IDS):
            errors[CONF_CIRCUIT_IDS] = "circuits_required"
        errors.update(_own_entity_errors(self.hass, user_input))
        if errors:
            return self._details_form(user_input, kind, reconfigure=reconfigure, errors=errors)
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry() if reconfigure else None
        defaults = subentry_draft(entry, subentry) if subentry is not None else None
        zone_id = str(defaults["id"]) if defaults is not None else str(uuid4())
        data = _zone_data(
            {**user_input, CONF_THERMOSTAT_KIND: kind},
            zone_id,
            defaults[CONF_ROUTES] if defaults is not None else None,
            defaults.get(CONF_TEMPERATURE_SENSOR_METADATA) if defaults is not None else None,
            defaults.get(CONF_HUMIDITY_SENSOR_METADATA) if defaults is not None else None,
        )
        if kind == THERMOSTAT_KIND_EXTERNAL_CLIMATE and _is_hydronicus_owned(
            self.hass, str(user_input[CONF_EXTERNAL_CLIMATE_ENTITY])
        ):
            return self._details_form(
                user_input, kind, reconfigure=reconfigure, errors={"base": "thermostat_loop"}
            )
        if user_input.get(CONF_CONFIGURE_SENSOR_METADATA):
            self._zone_draft = data
            self._metadata_records = []
            self._metadata_index = 0
            self._zone_reconfigure = reconfigure
            return await self.async_step_sensor_metadata()
        if _requires_sensor_metadata_path(data) and (
            CONF_TEMPERATURE_SENSOR_METADATA not in user_input
        ):
            return self._details_form(
                user_input,
                kind,
                reconfigure=reconfigure,
                errors={"base": "sensor_metadata_required"},
            )
        if errors := _zone_validation_errors(
            entry,
            data,
            excluded_subentry_id=subentry.subentry_id if subentry is not None else None,
        ):
            return self._details_form(user_input, kind, reconfigure=reconfigure, errors=errors)
        self._zone_draft = data
        self._zone_reconfigure = reconfigure
        return await self._finish_zone()

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Confirm structured warnings before saving the proposed zone."""
        if user_input is not None:
            if not user_input.get("confirm", False):
                return self.async_show_form(
                    step_id="review",
                    data_schema=_warning_review_schema(),
                    errors={"base": "confirm_required"},
                    description_placeholders={"warnings": _warning_text(self._zone_compiled)},
                )
            if self._zone_reconfigure:
                subentry = self._get_reconfigure_subentry()
                if not await _async_persist_subentry_graph(
                    self,
                    self._get_entry(),
                    SUBENTRY_TYPE_ZONE,
                    self._zone_draft,
                    excluded_subentry_id=subentry.subentry_id,
                ):
                    return self.async_show_form(
                        step_id="review",
                        data_schema=_warning_review_schema(),
                        errors={"base": "dry_run_shutdown_in_progress"},
                        description_placeholders={"warnings": _warning_text(self._zone_compiled)},
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=self._zone_draft[CONF_NAME],
                    data=_subentry_handle(self._zone_draft),
                )
            if not await _async_persist_subentry_graph(
                self,
                self._get_entry(),
                SUBENTRY_TYPE_ZONE,
                self._zone_draft,
            ):
                return self.async_show_form(
                    step_id="review",
                    data_schema=_warning_review_schema(),
                    errors={"base": "dry_run_shutdown_in_progress"},
                    description_placeholders={"warnings": _warning_text(self._zone_compiled)},
                )
            return self.async_create_entry(
                title=self._zone_draft[CONF_NAME],
                data=_subentry_handle(self._zone_draft),
                unique_id=self._zone_draft["id"],
            )
        return self.async_show_form(
            step_id="review",
            data_schema=_warning_review_schema(),
            description_placeholders={"warnings": _warning_text(self._zone_compiled)},
        )


def _valve_actuator_data(user_input: Mapping[str, Any], actuator_id: str) -> dict[str, Any]:
    """Normalize one valve actuator payload for persistent subentry storage."""
    user_input = _flatten_sections(user_input)
    data = {
        "id": actuator_id,
        CONF_ACTUATOR_KIND: ACTUATOR_KIND_VALVE,
        CONF_NAME: str(user_input[CONF_NAME]).strip(),
        CONF_ENTITY_ID: user_input[CONF_ENTITY_ID],
        CONF_OPENING_TIME: user_input[CONF_OPENING_TIME],
        CONF_POSITION_FEEDBACK_ENTITY: user_input.get(CONF_POSITION_FEEDBACK_ENTITY),
        CONF_POSITION_FEEDBACK_MAX_AGE: user_input.get(
            CONF_POSITION_FEEDBACK_MAX_AGE, _DEFAULT_FEEDBACK_MAX_AGE
        ),
        CONF_CIRCUIT_IDS: user_input[CONF_CIRCUIT_IDS],
    }
    if user_input.get(CONF_VALVE_READINESS_ENTITY):
        data[CONF_VALVE_READINESS_ENTITY] = user_input[CONF_VALVE_READINESS_ENTITY]
    return data


def _valve_feedback_fields(defaults: Mapping[str, Any]) -> dict[Any, Any]:
    """Return optional valve feedback fields shared by initial and actuator forms."""
    return {
        _optional_entity(CONF_VALVE_READINESS_ENTITY, defaults): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["binary_sensor", "switch", "valve"])
        ),
        _optional_entity(CONF_POSITION_FEEDBACK_ENTITY, defaults): _sensor_selector(),
        vol.Optional(
            CONF_POSITION_FEEDBACK_MAX_AGE,
            default=defaults.get(CONF_POSITION_FEEDBACK_MAX_AGE, _DEFAULT_FEEDBACK_MAX_AGE),
        ): _max_age_selector(),
    }


def _valve_actuator_schema(
    circuit_options: list[selector.SelectOptionDict],
    defaults: Mapping[str, Any] | None = None,
) -> vol.Schema:
    """Build the shared valve form schema with optional reconfigure defaults."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)
            ): _name_selector(),
            vol.Required(
                CONF_ENTITY_ID, default=defaults.get(CONF_ENTITY_ID, vol.UNDEFINED)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain=["switch", "valve"])),
            vol.Required(
                CONF_OPENING_TIME,
                default=defaults.get(CONF_OPENING_TIME, DEFAULT_VALVE_OPENING_TIME),
            ): _seconds_selector(),
            vol.Required(
                CONF_CIRCUIT_IDS,
                default=defaults.get(CONF_CIRCUIT_IDS, vol.UNDEFINED),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=circuit_options,
                    multiple=True,
                )
            ),
            vol.Optional(SECTION_FEEDBACK): _collapsed_section(_valve_feedback_fields(defaults)),
        }
    )


def _actuator_validation_errors(
    entry: config_entries.ConfigEntry,
    data: Mapping[str, Any],
    *,
    excluded_subentry_id: str | None = None,
) -> dict[str, str]:
    """Return flow errors after validating the complete proposed topology."""
    if not data[CONF_NAME]:
        return {"base": "name_required"}
    error = _effective_topology_error(
        entry,
        proposed_actuators=(data,),
        excluded_subentry_id=excluded_subentry_id,
    )
    if error is None:
        return {}
    if isinstance(error, DuplicateActuatorBindingError) and data[CONF_ENTITY_ID] in (
        error.entity_ids
    ):
        return {CONF_ENTITY_ID: "actuator_entity_in_use"}
    return {"base": "invalid_actuator"}


class ActuatorSubentryFlowHandler(_OwnEntityPickerMixin, config_entries.ConfigSubentryFlow):
    """Add an actuator that extends one or more existing hydraulic circuits."""

    _draft: dict[str, Any]
    _draft_compiled: CompiledPlant
    _reconfigure: bool

    def _circuit_options(self) -> list[selector.SelectOptionDict]:
        entry = self._get_entry()
        configuration = plant_configuration_from_entry_data(entry.data)
        dynamic_circuit_ids = subentry_owned_ids(entry.data, SUBENTRY_TYPE_CIRCUIT)
        return [
            selector.SelectOptionDict(value=circuit.id, label=circuit.name)
            for circuit in configuration.circuits
            if circuit.id not in dynamic_circuit_ids
        ]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Create one valve actuator attached to selected circuits."""
        entry = self._get_entry()
        circuit_options = self._circuit_options()
        if not circuit_options:
            return self.async_abort(reason="no_circuits")

        errors: dict[str, str] = {}
        if user_input is not None and not user_input.get(CONF_CIRCUIT_IDS):
            errors[CONF_CIRCUIT_IDS] = "circuits_required"
        if user_input is not None:
            errors.update(_own_entity_errors(self.hass, user_input))
        if user_input is not None and not errors:
            actuator_id = str(uuid4())
            data = _valve_actuator_data(user_input, actuator_id)
            if validation_errors := _actuator_validation_errors(entry, data):
                errors.update(validation_errors)
            else:
                self._draft = data
                self._reconfigure = False
                compiled = _effective_topology_compile(
                    entry,
                    proposed_actuators=(data,),
                )
                if compiled is not None and compiled.warnings:
                    self._draft_compiled = compiled
                    return await self.async_step_review()
                if await _async_persist_subentry_graph(
                    self,
                    entry,
                    SUBENTRY_TYPE_ACTUATOR,
                    data,
                ):
                    return self.async_create_entry(
                        title=data[CONF_NAME], data=_subentry_handle(data), unique_id=actuator_id
                    )
                errors["base"] = "dry_run_shutdown_in_progress"

        return self.async_show_form(
            step_id="user",
            data_schema=_with_submitted_values(
                self, _valve_actuator_schema(circuit_options), user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Update one valve actuator without changing its stable UUID."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        defaults = subentry_draft(entry, subentry)
        circuit_options = self._circuit_options()
        errors: dict[str, str] = {}
        if user_input is not None and not user_input.get(CONF_CIRCUIT_IDS):
            errors[CONF_CIRCUIT_IDS] = "circuits_required"
        if user_input is not None:
            errors.update(_own_entity_errors(self.hass, user_input))
        if user_input is not None and not errors:
            data = _valve_actuator_data(user_input, defaults["id"])
            if validation_errors := _actuator_validation_errors(
                entry,
                data,
                excluded_subentry_id=subentry.subentry_id,
            ):
                errors.update(validation_errors)
            else:
                self._draft = data
                self._reconfigure = True
                compiled = _effective_topology_compile(
                    entry,
                    proposed_actuators=(data,),
                    excluded_subentry_id=subentry.subentry_id,
                )
                if compiled is not None and compiled.warnings:
                    self._draft_compiled = compiled
                    return await self.async_step_review()
                if await _async_persist_subentry_graph(
                    self,
                    entry,
                    SUBENTRY_TYPE_ACTUATOR,
                    data,
                    excluded_subentry_id=subentry.subentry_id,
                ):
                    return self.async_update_and_abort(
                        entry,
                        subentry,
                        title=data[CONF_NAME],
                        data=_subentry_handle(data),
                    )
                errors["base"] = "dry_run_shutdown_in_progress"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_with_submitted_values(
                self, _valve_actuator_schema(circuit_options, defaults), user_input
            ),
            errors=errors,
        )

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Confirm structured warnings before saving the proposed actuator."""
        if user_input is not None:
            if not user_input.get("confirm", False):
                return self.async_show_form(
                    step_id="review",
                    data_schema=_warning_review_schema(),
                    errors={"base": "confirm_required"},
                    description_placeholders={"warnings": _warning_text(self._draft_compiled)},
                )
            if self._reconfigure:
                subentry = self._get_reconfigure_subentry()
                if not await _async_persist_subentry_graph(
                    self,
                    self._get_entry(),
                    SUBENTRY_TYPE_ACTUATOR,
                    self._draft,
                    excluded_subentry_id=subentry.subentry_id,
                ):
                    return self.async_show_form(
                        step_id="review",
                        data_schema=_warning_review_schema(),
                        errors={"base": "dry_run_shutdown_in_progress"},
                        description_placeholders={"warnings": _warning_text(self._draft_compiled)},
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=self._draft[CONF_NAME],
                    data=_subentry_handle(self._draft),
                )
            if not await _async_persist_subentry_graph(
                self,
                self._get_entry(),
                SUBENTRY_TYPE_ACTUATOR,
                self._draft,
            ):
                return self.async_show_form(
                    step_id="review",
                    data_schema=_warning_review_schema(),
                    errors={"base": "dry_run_shutdown_in_progress"},
                    description_placeholders={"warnings": _warning_text(self._draft_compiled)},
                )
            return self.async_create_entry(
                title=self._draft[CONF_NAME],
                data=_subentry_handle(self._draft),
                unique_id=self._draft["id"],
            )
        return self.async_show_form(
            step_id="review",
            data_schema=_warning_review_schema(),
            description_placeholders={"warnings": _warning_text(self._draft_compiled)},
        )


def _initial_circuit_schema() -> vol.Schema:
    """Build the first circuit form, including its first valve and pump."""
    no_defaults: Mapping[str, Any] = {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME): _name_selector(),
            vol.Required(CONF_VALVE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["switch", "valve"])
            ),
            vol.Required(CONF_PUMP_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            vol.Required(
                CONF_VALVE_OPENING_TIME, default=DEFAULT_VALVE_OPENING_TIME
            ): _seconds_selector(),
            vol.Required(CONF_PUMP_OVERRUN, default=DEFAULT_PUMP_OVERRUN): _seconds_selector(),
            vol.Optional(SECTION_FEEDBACK): _collapsed_section(
                {
                    **_valve_feedback_fields(no_defaults),
                    vol.Optional(CONF_POWER_FEEDBACK_ENTITY): _sensor_selector(),
                    vol.Optional(
                        CONF_POWER_FEEDBACK_MAX_AGE, default=_DEFAULT_FEEDBACK_MAX_AGE
                    ): _max_age_selector(),
                    vol.Optional(CONF_FLOW_FEEDBACK_ENTITY): _sensor_selector(),
                    vol.Optional(
                        CONF_FLOW_FEEDBACK_MAX_AGE, default=_DEFAULT_FEEDBACK_MAX_AGE
                    ): _max_age_selector(),
                    vol.Optional(CONF_FAULT_FEEDBACK_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"])
                    ),
                    vol.Optional(
                        CONF_FAULT_FEEDBACK_MAX_AGE, default=_DEFAULT_FEEDBACK_MAX_AGE
                    ): _max_age_selector(),
                }
            ),
            vol.Optional(SECTION_COOLING): _collapsed_section(
                _cooling_reference_fields(no_defaults)
            ),
        }
    )


def _initial_circuit_cooling_error(draft: Mapping[str, Any], circuit_id: str) -> str | None:
    """Explain a rejected cooling setting on the first circuit form, where it can be fixed.

    Any other rejection is left to the review step, which shows the compiler reason.
    """
    try:
        compile_topology(plant_configuration_from_entry_data(draft))
    except (StoredTopologyError, TopologyValidationError) as error:
        return _circuit_cooling_error(error, circuit_id)
    return None


def _source_data(user_input: Mapping[str, Any], source_id: str) -> dict[str, Any]:
    """Normalize one source subentry into stable persisted configuration."""
    return {
        "id": source_id,
        CONF_NAME: str(user_input[CONF_NAME]).strip(),
        CONF_SOURCE_TYPE: str(user_input.get(CONF_SOURCE_TYPE, SOURCE_KIND_EXTERNAL)),
        # The number selector returns a float; the priority has always been stored as int.
        CONF_SOURCE_PRIORITY: int(user_input.get(CONF_SOURCE_PRIORITY, DEFAULT_SOURCE_PRIORITY)),
        CONF_SOURCE_AVAILABILITY_ENTITY: user_input.get(CONF_SOURCE_AVAILABILITY_ENTITY),
        CONF_SOURCE_DEMAND_ENTITY: user_input.get(CONF_SOURCE_DEMAND_ENTITY),
        CONF_SOURCE_TEMPERATURE_ENTITY: user_input.get(CONF_SOURCE_TEMPERATURE_ENTITY),
        CONF_SOURCE_MINIMUM_TEMPERATURE: user_input.get(CONF_SOURCE_MINIMUM_TEMPERATURE, 0.0),
        CONF_SOURCE_MAXIMUM_AGE: user_input.get(
            CONF_SOURCE_MAXIMUM_AGE, DEFAULT_SOURCE_MAXIMUM_AGE
        ),
        CONF_SOURCE_HYSTERESIS: user_input.get(CONF_SOURCE_HYSTERESIS, DEFAULT_SOURCE_HYSTERESIS),
    }


def _source_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    """Build the generic and temperature-qualified source editor."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)
            ): _name_selector(),
            vol.Required(
                CONF_SOURCE_TYPE,
                default=defaults.get(CONF_SOURCE_TYPE, SOURCE_KIND_EXTERNAL),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[SOURCE_KIND_EXTERNAL, SOURCE_KIND_BUFFER],
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key=CONF_SOURCE_TYPE,
                )
            ),
            vol.Required(
                CONF_SOURCE_PRIORITY,
                default=defaults.get(CONF_SOURCE_PRIORITY, DEFAULT_SOURCE_PRIORITY),
            ): _number(step=1, minimum=0),
            # vol.Maybe keeps accepting an explicit None, which clears a binding.
            _optional_entity(CONF_SOURCE_AVAILABILITY_ENTITY, defaults): vol.Maybe(
                selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["binary_sensor", "input_boolean", "sensor"]
                    )
                )
            ),
            _optional_entity(CONF_SOURCE_TEMPERATURE_ENTITY, defaults): vol.Maybe(
                _sensor_selector(SensorDeviceClass.TEMPERATURE)
            ),
            _optional_entity(CONF_SOURCE_DEMAND_ENTITY, defaults): vol.Maybe(
                selector.EntitySelector(selector.EntitySelectorConfig(domain=["switch", "valve"]))
            ),
            vol.Required(
                CONF_SOURCE_MINIMUM_TEMPERATURE,
                default=defaults.get(CONF_SOURCE_MINIMUM_TEMPERATURE, 0.0),
            ): _number(step=0.1, unit=UnitOfTemperature.CELSIUS),
            vol.Required(
                CONF_SOURCE_MAXIMUM_AGE,
                default=defaults.get(CONF_SOURCE_MAXIMUM_AGE, DEFAULT_SOURCE_MAXIMUM_AGE),
            ): _max_age_selector(),
            vol.Required(
                CONF_SOURCE_HYSTERESIS,
                default=defaults.get(CONF_SOURCE_HYSTERESIS, DEFAULT_SOURCE_HYSTERESIS),
            ): _temperature_delta_selector(),
        }
    )


def _source_validation_errors(
    entry: config_entries.ConfigEntry,
    data: Mapping[str, Any],
    *,
    excluded_subentry_id: str | None = None,
) -> dict[str, str]:
    """Return flow errors after compiling the complete source topology."""
    if not data[CONF_NAME]:
        return {"base": "name_required"}
    error = _effective_topology_error(
        entry,
        proposed_sources=(data,),
        excluded_subentry_id=excluded_subentry_id,
    )
    if error is None:
        return {}
    if isinstance(error, BufferTemperatureRequiredError) and error.source_id == data["id"]:
        return {CONF_SOURCE_TEMPERATURE_ENTITY: "buffer_temperature_required"}
    return {"base": "invalid_source"}


class SourceSubentryFlowHandler(_OwnEntityPickerMixin, config_entries.ConfigSubentryFlow):
    """Add a source used by the read-only source recommendation."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Create one source configuration without any actuator binding."""
        entry = self._get_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            source_id = str(uuid4())
            data = _source_data(user_input, source_id)
            errors = _own_entity_errors(self.hass, user_input)
            if not errors:
                errors = _source_validation_errors(entry, data)
            if not errors:
                if await _async_persist_subentry_graph(
                    self,
                    entry,
                    SUBENTRY_TYPE_SOURCE,
                    data,
                ):
                    return self.async_create_entry(
                        title=data[CONF_NAME], data=_subentry_handle(data), unique_id=source_id
                    )
                errors["base"] = "dry_run_shutdown_in_progress"
        return self.async_show_form(
            step_id="user",
            data_schema=_with_submitted_values(self, _source_schema(), user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Update a source while preserving its stable UUID."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        defaults = subentry_draft(entry, subentry)
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _source_data(user_input, defaults["id"])
            errors = _own_entity_errors(self.hass, user_input)
            if not errors:
                errors = _source_validation_errors(
                    entry, data, excluded_subentry_id=subentry.subentry_id
                )
            if not errors:
                if await _async_persist_subentry_graph(
                    self,
                    entry,
                    SUBENTRY_TYPE_SOURCE,
                    data,
                    excluded_subentry_id=subentry.subentry_id,
                ):
                    return self.async_update_and_abort(
                        entry,
                        subentry,
                        title=data[CONF_NAME],
                        data=_subentry_handle(data),
                    )
                errors["base"] = "dry_run_shutdown_in_progress"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_with_submitted_values(self, _source_schema(defaults), user_input),
            errors=errors,
        )


class HydronicClimateConfigFlow(  # type: ignore[call-arg]
    _OwnEntityPickerMixin, config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle creation of a hydronic plant config entry."""

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    _draft: dict[str, Any]
    _zone_draft: dict[str, Any]
    _metadata_records: list[dict[str, Any]]
    _metadata_index: int
    _selected_thermostat_kind: str

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return dynamic object types supported by this plant."""
        return {
            SUBENTRY_TYPE_ACTUATOR: ActuatorSubentryFlowHandler,
            SUBENTRY_TYPE_CIRCUIT: CircuitSubentryFlowHandler,
            SUBENTRY_TYPE_ZONE: ZoneSubentryFlowHandler,
            SUBENTRY_TYPE_SOURCE: SourceSubentryFlowHandler,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if not name:
                errors["base"] = "name_required"
            else:
                self._draft = {
                    CONF_NAME: name,
                    CONF_PLANT_ID: str(uuid4()),
                    CONF_DRY_RUN: bool(user_input.get(CONF_DRY_RUN, True)),
                }
                return await self.async_step_zone()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_PLANT_NAME): _name_selector(),
                vol.Optional(CONF_DRY_RUN, default=True): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=_with_submitted_values(self, schema, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Change the Plant Dry run setting through Home Assistant reconfiguration."""
        entry = self._get_reconfigure_entry()
        current_dry_run = bool(entry.data.get(CONF_DRY_RUN, True))
        if user_input is not None:
            requested_dry_run = bool(user_input[CONF_DRY_RUN])
            if requested_dry_run is False and current_dry_run:
                self._requested_dry_run = False
                return await self.async_step_dry_run_confirmation()
            return await self._async_apply_dry_run(entry, requested_dry_run)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_dry_run_reconfigure_schema(current_dry_run),
        )

    async def async_step_dry_run_confirmation(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm the exact heating outputs before leaving Dry run."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            if not user_input.get(CONF_DRY_RUN_CONFIRMATION, False):
                return self.async_show_form(
                    step_id="dry_run_confirmation",
                    data_schema=_dry_run_confirmation_schema(),
                    errors={"base": "dry_run_confirmation_required"},
                    description_placeholders={"outputs": authorization_output_lines(entry.data)},
                )
            return await self._async_apply_dry_run(entry, self._requested_dry_run)
        return self.async_show_form(
            step_id="dry_run_confirmation",
            data_schema=_dry_run_confirmation_schema(),
            description_placeholders={"outputs": authorization_output_lines(entry.data)},
        )

    async def _async_apply_dry_run(
        self, entry: config_entries.ConfigEntry, dry_run: bool
    ) -> config_entries.ConfigFlowResult:
        """Apply Dry run, completing any active heating shutdown first."""
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None:
            authorization = None if dry_run else output_authorization(entry.data)
            if not await runtime.async_set_dry_run(
                dry_run,
                hass=self.hass,
                authorization=authorization,
            ):
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=_dry_run_reconfigure_schema(dry_run),
                    errors={"base": "dry_run_shutdown_in_progress"},
                )
        else:
            if not dry_run:
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=_dry_run_reconfigure_schema(
                        bool(entry.data.get(CONF_DRY_RUN, True))
                    ),
                    errors={"base": "dry_run_runtime_unavailable"},
                )
            data = invalidate_output_authorization(entry.data)
            self.hass.config_entries.async_update_entry(entry, data=data)
        return self.async_abort(reason="reconfigure_successful")

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose the first Zone's thermostat owner."""
        if user_input is None:
            return self.async_show_form(step_id="zone", data_schema=_thermostat_kind_schema())
        kind = str(user_input.get(CONF_THERMOSTAT_KIND, THERMOSTAT_KIND_HYDRONICUS))
        if set(user_input) <= {CONF_THERMOSTAT_KIND}:
            self._selected_thermostat_kind = kind
            return await self.async_step_zone_details()
        return await self._async_process_initial_zone(user_input, kind)

    async def async_step_zone_details(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect only fields owned by the selected initial thermostat kind."""
        if user_input is not None:
            return await self._async_process_initial_zone(
                {**user_input, CONF_THERMOSTAT_KIND: self._selected_thermostat_kind},
                self._selected_thermostat_kind,
            )
        return self._zone_details_form(None, self._selected_thermostat_kind)

    def _zone_details_form(
        self,
        user_input: Mapping[str, Any] | None,
        kind: str,
        *,
        errors: dict[str, str] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Show the first Zone's details form, re-filled after a rejected submit."""
        self._selected_thermostat_kind = kind
        schema = _zone_schema([], thermostat_kind=kind, include_circuits=False)
        return self.async_show_form(
            step_id="zone_details",
            data_schema=_with_submitted_values(self, schema, user_input),
            errors=errors,
        )

    async def _async_process_initial_zone(
        self, user_input: Mapping[str, Any], kind: str
    ) -> config_entries.ConfigFlowResult:
        """Normalize the first thermostat-specific Zone without adding a route yet."""
        name = str(user_input.get(CONF_NAME, "")).strip()
        errors: dict[str, str] = {}
        if not name:
            errors["base"] = "name_required"
        # vol.Required accepts an empty list, which a lazily loaded frontend picker
        # can submit, so the required sensor selection is checked explicitly.
        if kind == THERMOSTAT_KIND_HYDRONICUS and not user_input.get(CONF_TEMPERATURE_SENSORS):
            errors[CONF_TEMPERATURE_SENSORS] = "temperature_sensors_required"
        errors.update(_own_entity_errors(self.hass, user_input))
        if errors:
            return self._zone_details_form(user_input, kind, errors=errors)
        if kind == THERMOSTAT_KIND_EXTERNAL_CLIMATE and _is_hydronicus_owned(
            self.hass, str(user_input[CONF_EXTERNAL_CLIMATE_ENTITY])
        ):
            return self._zone_details_form(user_input, kind, errors={"base": "thermostat_loop"})
        draft = _zone_data(
            {
                **user_input,
                CONF_NAME: name,
                CONF_THERMOSTAT_KIND: kind,
                CONF_CIRCUIT_IDS: ["pending"],
            },
            str(uuid4()),
        )
        draft.pop(CONF_CIRCUIT_IDS, None)
        draft.pop(CONF_ROUTES, None)
        self._zone_draft = draft
        if user_input.get(CONF_CONFIGURE_SENSOR_METADATA):
            self._metadata_records = []
            self._metadata_index = 0
            return await self.async_step_sensor_metadata()
        if _requires_sensor_metadata_path(draft) and (
            CONF_TEMPERATURE_SENSOR_METADATA not in user_input
        ):
            return self._zone_details_form(
                user_input, kind, errors={"base": "sensor_metadata_required"}
            )
        self._draft[CONF_TOPOLOGY] = {CONF_ZONES: [draft]}
        return await self.async_step_circuit()

    async def async_step_sensor_metadata(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Edit initial sensor metadata through typed one-sensor forms."""
        sensor_ids = _zone_temperature_sensor_defaults(self._zone_draft)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _own_entity_errors(self.hass, user_input)
            if not errors:
                self._metadata_records.append(_sensor_metadata_record(user_input))
                self._metadata_index += 1
        if self._metadata_index < len(sensor_ids):
            sensor_id = sensor_ids[self._metadata_index]
            defaults: Mapping[str, Any] = next(
                (
                    record
                    for record in self._zone_draft[CONF_TEMPERATURE_SENSOR_METADATA]
                    if record.get("entity_id") == sensor_id
                ),
                {},
            )
            return self.async_show_form(
                step_id="sensor_metadata",
                data_schema=_with_submitted_values(
                    self,
                    _sensor_metadata_schema(sensor_id, defaults),
                    user_input if errors else None,
                ),
                errors=errors,
                description_placeholders={"sensor": sensor_id},
            )
        if self._metadata_records:
            self._zone_draft[CONF_TEMPERATURE_SENSOR_METADATA] = self._metadata_records
        return await self.async_step_sensor_policy()

    async def async_step_sensor_policy(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose designated-reference or weighted aggregation after metadata editing."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._zone_draft[CONF_TEMPERATURE_AGGREGATION] = user_input[
                CONF_TEMPERATURE_AGGREGATION
            ]
            try:
                # The zone alone decodes without a circuit, which the next step adds.
                plant_configuration_from_entry_data(
                    {
                        CONF_PLANT_ID: self._draft[CONF_PLANT_ID],
                        CONF_TOPOLOGY: {CONF_ZONES: [self._zone_draft]},
                    }
                )
            except DesignatedReferenceError:
                errors["base"] = "designated_reference_count"
            except StoredTopologyError:
                pass  # The review step explains any other rejection in full.
            if not errors:
                self._draft[CONF_TOPOLOGY] = {CONF_ZONES: [self._zone_draft]}
                return await self.async_step_circuit()
        return self.async_show_form(
            step_id="sensor_policy",
            data_schema=_sensor_policy_schema(self._zone_draft),
            errors=errors,
        )

    async def async_step_circuit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect the first hydraulic circuit and its Dry run equipment path."""
        errors: dict[str, str] = {}
        if user_input is not None:
            fields = _flatten_sections(user_input)
            name = str(fields[CONF_NAME]).strip()
            if not name:
                errors["base"] = "name_required"
            elif fields[CONF_VALVE_ENTITY] == fields[CONF_PUMP_ENTITY]:
                errors["base"] = "duplicate_actuator_entity"
            elif own_entity_errors := _own_entity_errors(self.hass, user_input):
                errors.update(own_entity_errors)
            else:
                circuit_id = str(uuid4())
                valve_id = str(uuid4())
                pump_id = str(uuid4())
                zone_id = self._draft[CONF_TOPOLOGY][CONF_ZONES][0]["id"]
                valve_data = {
                    "id": valve_id,
                    CONF_NAME: f"{name} valve",
                    CONF_ENTITY_ID: fields[CONF_VALVE_ENTITY],
                    CONF_OPENING_TIME: fields[CONF_VALVE_OPENING_TIME],
                }
                if fields.get(CONF_VALVE_READINESS_ENTITY):
                    valve_data[CONF_VALVE_READINESS_ENTITY] = fields[CONF_VALVE_READINESS_ENTITY]
                valve_data[CONF_POSITION_FEEDBACK_ENTITY] = fields.get(
                    CONF_POSITION_FEEDBACK_ENTITY
                )
                valve_data[CONF_POSITION_FEEDBACK_MAX_AGE] = fields.get(
                    CONF_POSITION_FEEDBACK_MAX_AGE, _DEFAULT_FEEDBACK_MAX_AGE
                )
                self._draft[CONF_TOPOLOGY][CONF_VALVES] = [valve_data]
                self._draft[CONF_TOPOLOGY][CONF_PUMPS] = [
                    {
                        "id": pump_id,
                        CONF_NAME: f"{name} pump",
                        CONF_ENTITY_ID: fields[CONF_PUMP_ENTITY],
                        CONF_OVERRUN: fields[CONF_PUMP_OVERRUN],
                        CONF_POWER_FEEDBACK_ENTITY: fields.get(CONF_POWER_FEEDBACK_ENTITY),
                        CONF_POWER_FEEDBACK_MAX_AGE: fields.get(
                            CONF_POWER_FEEDBACK_MAX_AGE, _DEFAULT_FEEDBACK_MAX_AGE
                        ),
                        CONF_FLOW_FEEDBACK_ENTITY: fields.get(CONF_FLOW_FEEDBACK_ENTITY),
                        CONF_FLOW_FEEDBACK_MAX_AGE: fields.get(
                            CONF_FLOW_FEEDBACK_MAX_AGE, _DEFAULT_FEEDBACK_MAX_AGE
                        ),
                        CONF_FAULT_FEEDBACK_ENTITY: fields.get(CONF_FAULT_FEEDBACK_ENTITY),
                        CONF_FAULT_FEEDBACK_MAX_AGE: fields.get(
                            CONF_FAULT_FEEDBACK_MAX_AGE, _DEFAULT_FEEDBACK_MAX_AGE
                        ),
                    }
                ]
                self._draft[CONF_TOPOLOGY][CONF_CIRCUITS] = [
                    {
                        "id": circuit_id,
                        CONF_NAME: name,
                        CONF_VALVE_IDS: [valve_id],
                        "pump_id": pump_id,
                        CONF_COOLING_ENABLED: bool(fields.get(CONF_COOLING_ENABLED, False)),
                        CONF_SUPPLY_TEMPERATURE_SENSOR: fields.get(CONF_SUPPLY_TEMPERATURE_SENSOR),
                        CONF_SURFACE_TEMPERATURE_SENSOR: fields.get(
                            CONF_SURFACE_TEMPERATURE_SENSOR
                        ),
                        CONF_CONDENSATION_MARGIN: fields.get(
                            CONF_CONDENSATION_MARGIN, DEFAULT_CONDENSATION_MARGIN
                        ),
                        CONF_SUPPLY_TEMPERATURE_MAX_AGE: fields.get(
                            CONF_SUPPLY_TEMPERATURE_MAX_AGE, DEFAULT_REFERENCE_MAX_AGE
                        ),
                        CONF_SURFACE_TEMPERATURE_MAX_AGE: fields.get(
                            CONF_SURFACE_TEMPERATURE_MAX_AGE, DEFAULT_REFERENCE_MAX_AGE
                        ),
                    }
                ]
                self._draft[CONF_TOPOLOGY][CONF_ROUTES] = [
                    {"id": str(uuid4()), "zone_id": zone_id, "circuit_id": circuit_id}
                ]
                if cooling_error := _initial_circuit_cooling_error(self._draft, circuit_id):
                    errors["base"] = cooling_error
                else:
                    return await self.async_step_review()
        return self.async_show_form(
            step_id="circuit",
            data_schema=_with_submitted_values(self, _initial_circuit_schema(), user_input),
            errors=errors,
        )

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Validate the initial topology before storing it in a config entry."""
        topology = self._draft[CONF_TOPOLOGY]
        try:
            plant = compile_topology(plant_configuration_from_entry_data(self._draft))
        except (StoredTopologyError, TopologyValidationError) as error:
            return self.async_show_form(
                step_id="review",
                errors={"base": "invalid_topology"},
                description_placeholders=_initial_review_placeholders(topology, None, str(error)),
            )

        if user_input is not None:
            if not self._draft[CONF_DRY_RUN] and not user_input.get(
                CONF_DRY_RUN_CONFIRMATION, False
            ):
                return self.async_show_form(
                    step_id="review",
                    data_schema=_dry_run_confirmation_schema(),
                    errors={"base": "dry_run_confirmation_required"},
                    description_placeholders=_initial_review_placeholders(topology, plant),
                )
            await self.async_set_unique_id(self._draft[CONF_PLANT_ID])
            self._abort_if_unique_id_configured()
            if not self._draft[CONF_DRY_RUN]:
                self._draft = authorize_outputs(self._draft)
            return self.async_create_entry(title=self._draft[CONF_NAME], data=self._draft)

        return self.async_show_form(
            step_id="review",
            data_schema=(_dry_run_confirmation_schema() if not self._draft[CONF_DRY_RUN] else None),
            description_placeholders=_initial_review_placeholders(topology, plant),
        )
