"""Zone, circuit, and actuator subentry flows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from ..const import (
    ACTUATOR_KIND_VALVE,
    CONF_ACTUATOR_KIND,
    CONF_CIRCUIT_IDS,
    CONF_CONDENSATION_MARGIN,
    CONF_CONFIGURE_SENSOR_METADATA,
    CONF_COOLING_ENABLED,
    CONF_ENTITY_ID,
    CONF_EXTERNAL_CLIMATE_ENTITY,
    CONF_HUMIDITY_SENSOR_METADATA,
    CONF_HUMIDITY_SENSORS,
    CONF_NAME,
    CONF_OPENING_TIME,
    CONF_POSITION_FEEDBACK_ENTITY,
    CONF_POSITION_FEEDBACK_MAX_AGE,
    CONF_PUMP_ID,
    CONF_ROUTES,
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
    CONF_ZONE_IDS,
    DEFAULT_CONDENSATION_MARGIN,
    DEFAULT_REFERENCE_MAX_AGE,
    DEFAULT_VALVE_OPENING_TIME,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_CIRCUIT,
    SUBENTRY_TYPE_ZONE,
    THERMOSTAT_KIND_EXTERNAL_CLIMATE,
    THERMOSTAT_KIND_HYDRONICUS,
)
from ..core.configuration import (
    DesignatedReferenceError,
    StoredTopologyError,
    plant_configuration_from_entry_data,
)
from ..core.model import (
    CompiledPlant,
)
from ..core.topology import (
    CoolingObservationError,
    DuplicateActuatorBindingError,
    TopologyValidationError,
    compile_topology,
)
from ..entry_configuration import (
    effective_plant_configuration,
    subentry_draft,
    subentry_owned_ids,
)
from .common import (
    DEFAULT_FEEDBACK_MAX_AGE,
    SECTION_COOLING,
    SECTION_FEEDBACK,
    OwnEntityPickerMixin,
    SubentryReviewMixin,
    async_persist_subentry_graph,
    circuit_cooling_error,
    collapsed_section,
    cooling_reference_fields,
    effective_topology_error,
    flatten_sections,
    is_hydronicus_owned,
    name_selector,
    other_plant_sharing_warnings,
    own_entity_errors,
    requires_sensor_metadata_path,
    routes_with_retained_fields,
    seconds_selector,
    sensor_metadata_record,
    sensor_metadata_schema,
    sensor_policy_schema,
    subentry_handle,
    thermostat_kind_schema,
    topology_select,
    valve_feedback_fields,
    warning_review_schema,
    warning_text,
    with_submitted_values,
    zone_data,
    zone_schema,
    zone_temperature_sensor_defaults,
)


@dataclass(frozen=True, slots=True)
class CircuitOptions:
    """Parent-owned topology choices available to a circuit flow."""

    zones: list[selector.SelectOptionDict]
    valves: list[selector.SelectOptionDict]
    pumps: list[selector.SelectOptionDict]


def _circuit_data(
    user_input: Mapping[str, Any],
    circuit_id: str,
    existing_routes: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize one circuit and preserve route UUIDs for retained zones."""
    user_input = flatten_sections(user_input)
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
        CONF_ROUTES: routes_with_retained_fields(
            existing_routes,
            relationship_key="zone_id",
            relationship_ids=zone_ids,
        ),
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
            ): name_selector(),
            vol.Required(
                CONF_ZONE_IDS, default=defaults.get(CONF_ZONE_IDS, vol.UNDEFINED)
            ): topology_select(options.zones, multiple=True),
            vol.Required(
                CONF_VALVE_IDS, default=defaults.get(CONF_VALVE_IDS, vol.UNDEFINED)
            ): topology_select(options.valves, multiple=True),
            vol.Required(
                CONF_PUMP_ID, default=defaults.get(CONF_PUMP_ID, vol.UNDEFINED)
            ): topology_select(options.pumps, multiple=False),
            vol.Optional(SECTION_COOLING): collapsed_section(cooling_reference_fields(defaults)),
        }
    )


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


def _circuit_validation_errors(
    entry: config_entries.ConfigEntry,
    data: Mapping[str, Any],
    *,
    excluded_subentry_id: str | None = None,
) -> dict[str, str]:
    """Return flow errors after validating a proposed circuit atomically."""
    if not data[CONF_NAME]:
        return {"base": "name_required"}
    error = effective_topology_error(
        entry,
        proposed_circuits=(data,),
        excluded_subentry_id=excluded_subentry_id,
    )
    if error is None:
        return {}
    if cooling_error := circuit_cooling_error(error, str(data["id"])):
        return {"base": cooling_error}
    return {"base": "invalid_circuit"}


class CircuitSubentryFlowHandler(OwnEntityPickerMixin, config_entries.ConfigSubentryFlow):
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
            errors.update(own_entity_errors(self.hass, user_input))
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
                if await async_persist_subentry_graph(
                    self,
                    entry,
                    SUBENTRY_TYPE_CIRCUIT,
                    data,
                ):
                    return self.async_create_entry(
                        title=data[CONF_NAME], data=subentry_handle(data), unique_id=circuit_id
                    )
                errors["base"] = "dry_run_shutdown_in_progress"

        return self.async_show_form(
            step_id="user",
            data_schema=with_submitted_values(self, _circuit_schema(options), user_input),
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
            errors.update(own_entity_errors(self.hass, user_input))
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
                if await async_persist_subentry_graph(
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
                        data=subentry_handle(data),
                    )
                errors["base"] = "dry_run_shutdown_in_progress"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=with_submitted_values(
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
                    data_schema=warning_review_schema(),
                    errors={"base": "confirm_required"},
                    description_placeholders={"warnings": warning_text(self._draft_compiled)},
                )
            if self._reconfigure:
                subentry = self._get_reconfigure_subentry()
                if not await async_persist_subentry_graph(
                    self,
                    self._get_entry(),
                    SUBENTRY_TYPE_CIRCUIT,
                    self._draft,
                    excluded_subentry_id=subentry.subentry_id,
                ):
                    return self.async_show_form(
                        step_id="review",
                        data_schema=warning_review_schema(),
                        errors={"base": "dry_run_shutdown_in_progress"},
                        description_placeholders={"warnings": warning_text(self._draft_compiled)},
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=self._draft[CONF_NAME],
                    data=subentry_handle(self._draft),
                )
            if not await async_persist_subentry_graph(
                self,
                self._get_entry(),
                SUBENTRY_TYPE_CIRCUIT,
                self._draft,
            ):
                return self.async_show_form(
                    step_id="review",
                    data_schema=warning_review_schema(),
                    errors={"base": "dry_run_shutdown_in_progress"},
                    description_placeholders={"warnings": warning_text(self._draft_compiled)},
                )
            return self.async_create_entry(
                title=self._draft[CONF_NAME],
                data=subentry_handle(self._draft),
                unique_id=self._draft["id"],
            )
        return self.async_show_form(
            step_id="review",
            data_schema=warning_review_schema(),
            description_placeholders={"warnings": warning_text(self._draft_compiled)},
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
    error = effective_topology_error(
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


class ZoneSubentryFlowHandler(OwnEntityPickerMixin, config_entries.ConfigSubentryFlow):
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
            if not await async_persist_subentry_graph(
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
                data=subentry_handle(self._zone_draft),
            )
        if not await async_persist_subentry_graph(
            self,
            entry,
            SUBENTRY_TYPE_ZONE,
            self._zone_draft,
        ):
            return self._sensor_policy_form("dry_run_shutdown_in_progress")
        return self.async_create_entry(
            title=self._zone_draft[CONF_NAME],
            data=subentry_handle(self._zone_draft),
            unique_id=self._zone_draft["id"],
        )

    async def async_step_sensor_metadata(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Edit one sensor at a time so weights and safety metadata stay typed."""
        sensor_ids = zone_temperature_sensor_defaults(self._zone_draft)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = own_entity_errors(self.hass, user_input)
            if not errors:
                self._metadata_records.append(sensor_metadata_record(user_input))
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
                data_schema=with_submitted_values(
                    self,
                    sensor_metadata_schema(sensor_id, defaults),
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
            data_schema=sensor_policy_schema(self._zone_draft),
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
        schema = zone_schema(self._circuit_options(), defaults, thermostat_kind=kind)
        return self.async_show_form(
            step_id="details",
            data_schema=with_submitted_values(self, schema, user_input),
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
            return self.async_show_form(step_id="user", data_schema=thermostat_kind_schema())
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
                step_id="reconfigure", data_schema=thermostat_kind_schema(default_kind)
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
            data_schema=zone_schema(
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
        errors.update(own_entity_errors(self.hass, user_input))
        if errors:
            return self._details_form(user_input, kind, reconfigure=reconfigure, errors=errors)
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry() if reconfigure else None
        defaults = subentry_draft(entry, subentry) if subentry is not None else None
        zone_id = str(defaults["id"]) if defaults is not None else str(uuid4())
        data = zone_data(
            {**user_input, CONF_THERMOSTAT_KIND: kind},
            zone_id,
            defaults[CONF_ROUTES] if defaults is not None else None,
            defaults.get(CONF_TEMPERATURE_SENSOR_METADATA) if defaults is not None else None,
            defaults.get(CONF_HUMIDITY_SENSOR_METADATA) if defaults is not None else None,
        )
        if kind == THERMOSTAT_KIND_EXTERNAL_CLIMATE and is_hydronicus_owned(
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
        if requires_sensor_metadata_path(data) and (
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
                    data_schema=warning_review_schema(),
                    errors={"base": "confirm_required"},
                    description_placeholders={"warnings": warning_text(self._zone_compiled)},
                )
            if self._zone_reconfigure:
                subentry = self._get_reconfigure_subentry()
                if not await async_persist_subentry_graph(
                    self,
                    self._get_entry(),
                    SUBENTRY_TYPE_ZONE,
                    self._zone_draft,
                    excluded_subentry_id=subentry.subentry_id,
                ):
                    return self.async_show_form(
                        step_id="review",
                        data_schema=warning_review_schema(),
                        errors={"base": "dry_run_shutdown_in_progress"},
                        description_placeholders={"warnings": warning_text(self._zone_compiled)},
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=self._zone_draft[CONF_NAME],
                    data=subentry_handle(self._zone_draft),
                )
            if not await async_persist_subentry_graph(
                self,
                self._get_entry(),
                SUBENTRY_TYPE_ZONE,
                self._zone_draft,
            ):
                return self.async_show_form(
                    step_id="review",
                    data_schema=warning_review_schema(),
                    errors={"base": "dry_run_shutdown_in_progress"},
                    description_placeholders={"warnings": warning_text(self._zone_compiled)},
                )
            return self.async_create_entry(
                title=self._zone_draft[CONF_NAME],
                data=subentry_handle(self._zone_draft),
                unique_id=self._zone_draft["id"],
            )
        return self.async_show_form(
            step_id="review",
            data_schema=warning_review_schema(),
            description_placeholders={"warnings": warning_text(self._zone_compiled)},
        )


def _valve_actuator_data(user_input: Mapping[str, Any], actuator_id: str) -> dict[str, Any]:
    """Normalize one valve actuator payload for persistent subentry storage."""
    user_input = flatten_sections(user_input)
    data = {
        "id": actuator_id,
        CONF_ACTUATOR_KIND: ACTUATOR_KIND_VALVE,
        CONF_NAME: str(user_input[CONF_NAME]).strip(),
        CONF_ENTITY_ID: user_input[CONF_ENTITY_ID],
        CONF_OPENING_TIME: user_input[CONF_OPENING_TIME],
        CONF_POSITION_FEEDBACK_ENTITY: user_input.get(CONF_POSITION_FEEDBACK_ENTITY),
        CONF_POSITION_FEEDBACK_MAX_AGE: user_input.get(
            CONF_POSITION_FEEDBACK_MAX_AGE, DEFAULT_FEEDBACK_MAX_AGE
        ),
        CONF_CIRCUIT_IDS: user_input[CONF_CIRCUIT_IDS],
    }
    if user_input.get(CONF_VALVE_READINESS_ENTITY):
        data[CONF_VALVE_READINESS_ENTITY] = user_input[CONF_VALVE_READINESS_ENTITY]
    return data


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
            ): name_selector(),
            vol.Required(
                CONF_ENTITY_ID, default=defaults.get(CONF_ENTITY_ID, vol.UNDEFINED)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain=["switch", "valve"])),
            vol.Required(
                CONF_OPENING_TIME,
                default=defaults.get(CONF_OPENING_TIME, DEFAULT_VALVE_OPENING_TIME),
            ): seconds_selector(),
            vol.Required(
                CONF_CIRCUIT_IDS,
                default=defaults.get(CONF_CIRCUIT_IDS, vol.UNDEFINED),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=circuit_options,
                    multiple=True,
                )
            ),
            vol.Optional(SECTION_FEEDBACK): collapsed_section(valve_feedback_fields(defaults)),
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
    error = effective_topology_error(
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


class ActuatorSubentryFlowHandler(
    SubentryReviewMixin, OwnEntityPickerMixin, config_entries.ConfigSubentryFlow
):
    """Add an actuator that extends one or more existing hydraulic circuits."""

    _subentry_type = SUBENTRY_TYPE_ACTUATOR

    def _circuit_options(self) -> list[selector.SelectOptionDict]:
        entry = self._get_entry()
        configuration = plant_configuration_from_entry_data(entry.data)
        dynamic_circuit_ids = subentry_owned_ids(entry.data, SUBENTRY_TYPE_CIRCUIT)
        return [
            selector.SelectOptionDict(value=circuit.id, label=circuit.name)
            for circuit in configuration.circuits
            if circuit.id not in dynamic_circuit_ids
        ]

    def _review_text(
        self,
        entry: config_entries.ConfigEntry,
        data: Mapping[str, Any],
        *,
        excluded_subentry_id: str | None = None,
    ) -> str:
        """Collect compiler warnings and the other Plant already binding this actuator."""
        compiled = _effective_topology_compile(
            entry,
            proposed_actuators=(data,),
            excluded_subentry_id=excluded_subentry_id,
        )
        sharing = other_plant_sharing_warnings(self.hass, entry.entry_id, (data[CONF_ENTITY_ID],))
        return warning_text(compiled, sharing)

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
            errors.update(own_entity_errors(self.hass, user_input))
        if user_input is not None and not errors:
            data = _valve_actuator_data(user_input, str(uuid4()))
            if validation_errors := _actuator_validation_errors(entry, data):
                errors.update(validation_errors)
            elif result := await self._async_save_draft(
                data,
                reconfigure=False,
                warnings=self._review_text(entry, data),
                errors=errors,
            ):
                return result

        return self.async_show_form(
            step_id="user",
            data_schema=with_submitted_values(
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
            errors.update(own_entity_errors(self.hass, user_input))
        if user_input is not None and not errors:
            data = _valve_actuator_data(user_input, defaults["id"])
            if validation_errors := _actuator_validation_errors(
                entry,
                data,
                excluded_subentry_id=subentry.subentry_id,
            ):
                errors.update(validation_errors)
            elif result := await self._async_save_draft(
                data,
                reconfigure=True,
                warnings=self._review_text(entry, data, excluded_subentry_id=subentry.subentry_id),
                errors=errors,
            ):
                return result

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=with_submitted_values(
                self, _valve_actuator_schema(circuit_options, defaults), user_input
            ),
            errors=errors,
        )
