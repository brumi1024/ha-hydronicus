"""Initial config flow steps that create a new Plant."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from ..const import (
    CONF_CIRCUIT_IDS,
    CONF_CIRCUITS,
    CONF_CONDENSATION_MARGIN,
    CONF_CONFIGURE_SENSOR_METADATA,
    CONF_COOLING_ENABLED,
    CONF_DRY_RUN,
    CONF_DRY_RUN_CONFIRMATION,
    CONF_ENTITY_ID,
    CONF_EXTERNAL_CLIMATE_ENTITY,
    CONF_FAULT_FEEDBACK_ENTITY,
    CONF_FAULT_FEEDBACK_MAX_AGE,
    CONF_FLOW_FEEDBACK_ENTITY,
    CONF_FLOW_FEEDBACK_MAX_AGE,
    CONF_NAME,
    CONF_OPENING_TIME,
    CONF_OVERRUN,
    CONF_PLANT_ID,
    CONF_POSITION_FEEDBACK_ENTITY,
    CONF_POSITION_FEEDBACK_MAX_AGE,
    CONF_POWER_FEEDBACK_ENTITY,
    CONF_POWER_FEEDBACK_MAX_AGE,
    CONF_PUMP_ENTITY,
    CONF_PUMP_OVERRUN,
    CONF_PUMPS,
    CONF_ROUTES,
    CONF_SUPPLY_TEMPERATURE_MAX_AGE,
    CONF_SUPPLY_TEMPERATURE_SENSOR,
    CONF_SURFACE_TEMPERATURE_MAX_AGE,
    CONF_SURFACE_TEMPERATURE_SENSOR,
    CONF_TEMPERATURE_AGGREGATION,
    CONF_TEMPERATURE_SENSOR_METADATA,
    CONF_TEMPERATURE_SENSORS,
    CONF_THERMOSTAT_KIND,
    CONF_TOPOLOGY,
    CONF_VALVE_ENTITY,
    CONF_VALVE_IDS,
    CONF_VALVE_OPENING_TIME,
    CONF_VALVE_READINESS_ENTITY,
    CONF_VALVES,
    CONF_ZONES,
    DEFAULT_CONDENSATION_MARGIN,
    DEFAULT_PLANT_NAME,
    DEFAULT_PUMP_OVERRUN,
    DEFAULT_REFERENCE_MAX_AGE,
    DEFAULT_VALVE_OPENING_TIME,
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
    TopologyValidationError,
    compile_topology,
)
from ..entry_configuration import (
    authorization_output_lines,
    authorize_outputs,
    exclusive_output_entity_ids,
)
from .common import (
    DEFAULT_FEEDBACK_MAX_AGE,
    SECTION_COOLING,
    SECTION_FEEDBACK,
    ConfigFlowBase,
    circuit_cooling_error,
    collapsed_section,
    cooling_reference_fields,
    dry_run_confirmation_schema,
    flatten_sections,
    is_hydronicus_owned,
    max_age_selector,
    name_selector,
    other_plant_sharing_warnings,
    own_entity_errors,
    requires_sensor_metadata_path,
    seconds_selector,
    sensor_metadata_record,
    sensor_metadata_schema,
    sensor_policy_schema,
    sensor_selector,
    thermostat_kind_schema,
    valve_feedback_fields,
    warning_text,
    with_submitted_values,
    zone_data,
    zone_schema,
    zone_temperature_sensor_defaults,
)


def _initial_review_placeholders(
    topology: Mapping[str, Any],
    compiled: CompiledPlant | None,
    validation_error: str | None = None,
    sharing: Sequence[str] = (),
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
        "warnings": warning_text(compiled, sharing) or "- None",
        "outputs": authorization_output_lines({CONF_PLANT_ID: "pending", CONF_TOPOLOGY: topology}),
    }


def _initial_circuit_schema() -> vol.Schema:
    """Build the first circuit form, including its first valve and pump."""
    no_defaults: Mapping[str, Any] = {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME): name_selector(),
            vol.Required(CONF_VALVE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["switch", "valve"])
            ),
            vol.Required(CONF_PUMP_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            vol.Required(
                CONF_VALVE_OPENING_TIME, default=DEFAULT_VALVE_OPENING_TIME
            ): seconds_selector(),
            vol.Required(CONF_PUMP_OVERRUN, default=DEFAULT_PUMP_OVERRUN): seconds_selector(),
            vol.Optional(SECTION_FEEDBACK): collapsed_section(
                {
                    **valve_feedback_fields(no_defaults),
                    vol.Optional(CONF_POWER_FEEDBACK_ENTITY): sensor_selector(),
                    vol.Optional(
                        CONF_POWER_FEEDBACK_MAX_AGE, default=DEFAULT_FEEDBACK_MAX_AGE
                    ): max_age_selector(),
                    vol.Optional(CONF_FLOW_FEEDBACK_ENTITY): sensor_selector(),
                    vol.Optional(
                        CONF_FLOW_FEEDBACK_MAX_AGE, default=DEFAULT_FEEDBACK_MAX_AGE
                    ): max_age_selector(),
                    vol.Optional(CONF_FAULT_FEEDBACK_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"])
                    ),
                    vol.Optional(
                        CONF_FAULT_FEEDBACK_MAX_AGE, default=DEFAULT_FEEDBACK_MAX_AGE
                    ): max_age_selector(),
                }
            ),
            vol.Optional(SECTION_COOLING): collapsed_section(cooling_reference_fields(no_defaults)),
        }
    )


def _initial_circuit_cooling_error(draft: Mapping[str, Any], circuit_id: str) -> str | None:
    """Explain a rejected cooling setting on the first circuit form, where it can be fixed.

    Any other rejection is left to the review step, which shows the compiler reason.
    """
    try:
        compile_topology(plant_configuration_from_entry_data(draft))
    except (StoredTopologyError, TopologyValidationError) as error:
        return circuit_cooling_error(error, circuit_id)
    return None


class SetupSteps(ConfigFlowBase):
    """Create a new Plant from its first zone and first circuit."""

    _draft: dict[str, Any]
    _zone_draft: dict[str, Any]
    _metadata_records: list[dict[str, Any]]
    _metadata_index: int
    _selected_thermostat_kind: str

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
                vol.Required(CONF_NAME, default=DEFAULT_PLANT_NAME): name_selector(),
                vol.Optional(CONF_DRY_RUN, default=True): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=with_submitted_values(self, schema, user_input),
            errors=errors,
        )

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose the first Zone's thermostat owner."""
        if user_input is None:
            return self.async_show_form(step_id="zone", data_schema=thermostat_kind_schema())
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
        schema = zone_schema([], thermostat_kind=kind, include_circuits=False)
        return self.async_show_form(
            step_id="zone_details",
            data_schema=with_submitted_values(self, schema, user_input),
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
        errors.update(own_entity_errors(self.hass, user_input))
        if errors:
            return self._zone_details_form(user_input, kind, errors=errors)
        if kind == THERMOSTAT_KIND_EXTERNAL_CLIMATE and is_hydronicus_owned(
            self.hass, str(user_input[CONF_EXTERNAL_CLIMATE_ENTITY])
        ):
            return self._zone_details_form(user_input, kind, errors={"base": "thermostat_loop"})
        draft = zone_data(
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
        if requires_sensor_metadata_path(draft) and (
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
            data_schema=sensor_policy_schema(self._zone_draft),
            errors=errors,
        )

    async def async_step_circuit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect the first hydraulic circuit and its Dry run equipment path."""
        errors: dict[str, str] = {}
        if user_input is not None:
            fields = flatten_sections(user_input)
            name = str(fields[CONF_NAME]).strip()
            if not name:
                errors["base"] = "name_required"
            elif fields[CONF_VALVE_ENTITY] == fields[CONF_PUMP_ENTITY]:
                errors["base"] = "duplicate_actuator_entity"
            elif entity_errors := own_entity_errors(self.hass, user_input):
                errors.update(entity_errors)
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
                    CONF_POSITION_FEEDBACK_MAX_AGE, DEFAULT_FEEDBACK_MAX_AGE
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
                            CONF_POWER_FEEDBACK_MAX_AGE, DEFAULT_FEEDBACK_MAX_AGE
                        ),
                        CONF_FLOW_FEEDBACK_ENTITY: fields.get(CONF_FLOW_FEEDBACK_ENTITY),
                        CONF_FLOW_FEEDBACK_MAX_AGE: fields.get(
                            CONF_FLOW_FEEDBACK_MAX_AGE, DEFAULT_FEEDBACK_MAX_AGE
                        ),
                        CONF_FAULT_FEEDBACK_ENTITY: fields.get(CONF_FAULT_FEEDBACK_ENTITY),
                        CONF_FAULT_FEEDBACK_MAX_AGE: fields.get(
                            CONF_FAULT_FEEDBACK_MAX_AGE, DEFAULT_FEEDBACK_MAX_AGE
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
            data_schema=with_submitted_values(self, _initial_circuit_schema(), user_input),
            errors=errors,
        )

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Validate the initial topology before storing it in a config entry."""
        topology = self._draft[CONF_TOPOLOGY]
        sharing = other_plant_sharing_warnings(
            self.hass,
            None,
            sorted(
                exclusive_output_entity_ids({CONF_PLANT_ID: "pending", CONF_TOPOLOGY: topology})
            ),
        )
        try:
            plant = compile_topology(plant_configuration_from_entry_data(self._draft))
        except (StoredTopologyError, TopologyValidationError) as error:
            return self.async_show_form(
                step_id="review",
                errors={"base": "invalid_topology"},
                description_placeholders=_initial_review_placeholders(
                    topology, None, str(error), sharing
                ),
            )

        if user_input is not None:
            if not self._draft[CONF_DRY_RUN] and not user_input.get(
                CONF_DRY_RUN_CONFIRMATION, False
            ):
                return self.async_show_form(
                    step_id="review",
                    data_schema=dry_run_confirmation_schema(),
                    errors={"base": "dry_run_confirmation_required"},
                    description_placeholders=_initial_review_placeholders(
                        topology, plant, sharing=sharing
                    ),
                )
            await self.async_set_unique_id(self._draft[CONF_PLANT_ID])
            self._abort_if_unique_id_configured()
            if not self._draft[CONF_DRY_RUN]:
                self._draft = authorize_outputs(self._draft)
            return self.async_create_entry(title=self._draft[CONF_NAME], data=self._draft)

        return self.async_show_form(
            step_id="review",
            data_schema=(dry_run_confirmation_schema() if not self._draft[CONF_DRY_RUN] else None),
            description_placeholders=_initial_review_placeholders(topology, plant, sharing=sharing),
        )
