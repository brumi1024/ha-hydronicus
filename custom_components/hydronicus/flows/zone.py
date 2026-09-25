"""Zone subentry flow.

A zone is the space one thermostat controls, with its areas, its sensors, its
Delivery Routes, and its private loops and valves. Adding a zone asks for the
zone basics; editing one opens a menu of focused steps. Every save applies the whole
zone with ``data_with_zone``, reviews warnings when needed, and reaches Dry run
first.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers import selector

from ..areas import (
    AreaResolution,
    area_review_warnings,
    area_warnings_to_confirm,
    names_temperature_sensor,
    resolve_area_sensors,
)
from ..const import (
    CONF_AREA_ID,
    CONF_AREAS,
    CONF_CONDENSATION_MARGIN,
    CONF_CONFIGURE_SENSOR_METADATA,
    CONF_COOLING_ENABLED,
    CONF_COOLING_START_DELTA,
    CONF_COOLING_STOP_DELTA,
    CONF_ENTITY_ID,
    CONF_HEATING_START_DELTA,
    CONF_HEATING_STOP_DELTA,
    CONF_HUMIDITY_SENSOR_METADATA,
    CONF_HUMIDITY_SENSORS,
    CONF_MINIMUM_ACTIVE_DURATION,
    CONF_MINIMUM_IDLE_DURATION,
    CONF_NAME,
    CONF_OPENING_TIME,
    CONF_POSITION_FEEDBACK_ENTITY,
    CONF_POSITION_FEEDBACK_MAX_AGE,
    CONF_PRESET_TARGETS,
    CONF_PUMP_ID,
    CONF_SUPPLY_TEMPERATURE_MAX_AGE,
    CONF_SUPPLY_TEMPERATURE_SENSOR,
    CONF_SURFACE_TEMPERATURE_MAX_AGE,
    CONF_SURFACE_TEMPERATURE_SENSOR,
    CONF_TEMPERATURE_AGGREGATION,
    CONF_TEMPERATURE_SENSOR_METADATA,
    CONF_THERMOSTAT,
    CONF_VALVE_IDS,
    CONF_VALVE_OPENING_TIME,
    CONF_VALVE_READINESS_ENTITY,
    CONF_VALVES,
    DEFAULT_CONDENSATION_MARGIN,
    DEFAULT_REFERENCE_MAX_AGE,
    DEFAULT_VALVE_OPENING_TIME,
    THERMOSTAT_KIND_HYDRONICUS,
)
from ..entry_configuration import (
    GRAPH_EDIT_ERRORS,
    EffectivePlant,
    ZoneDraft,
    canonical_id,
    data_with_zone,
    effective_plant,
    effective_plant_from_data,
    object_ids,
    zone_draft,
)
from ..registrations import async_remove_object_registrations
from .common import (
    SECTION_COOLING,
    OwnEntityPickerMixin,
    async_persist_entry_data,
    collapsed_section,
    flatten_sections,
    name_selector,
    own_entity_errors,
    seconds_selector,
    shared_outputs,
    sharing_to_confirm,
    topology_select,
    warning_review_schema,
    warning_text,
    warnings_to_confirm,
    with_submitted_values,
)
from .zone_form import (
    CONF_PUMP,
    area_metadata_record,
    area_metadata_schema,
    areas_for,
    cooling_reference_fields,
    graph_errors,
    new_route,
    new_valves,
    pump_options,
    requires_sensor_metadata_path,
    sensor_entity_ids,
    sensor_metadata_for,
    sensor_metadata_record,
    sensor_metadata_schema,
    sensor_policy_schema,
    shared_loop_options,
    valve_entity_selector,
    valve_feedback_fields,
    zone_draft_from_form,
    zone_form_defaults,
    zone_form_errors,
    zone_form_schema,
    zone_schema,
)

CONF_LOOP = "loop"
CONF_SHARED_VALVES = "shared_valves"
CONF_CONFIGURE_VALVE_FEEDBACK = "configure_valve_feedback"
CONF_REMOVE_LOOP = "remove_loop"
_THERMOSTAT_FIELDS = frozenset(
    {
        CONF_HEATING_START_DELTA,
        CONF_HEATING_STOP_DELTA,
        CONF_MINIMUM_ACTIVE_DURATION,
        CONF_MINIMUM_IDLE_DURATION,
        "comfort",
        "eco",
        "away",
        SECTION_COOLING,
    }
)
_SENSOR_FIELDS = frozenset(
    {
        CONF_AREAS,
        CONF_TEMPERATURE_AGGREGATION,
        CONF_HUMIDITY_SENSORS,
        CONF_CONFIGURE_SENSOR_METADATA,
    }
)
_LOOP_COOLING_FIELDS = (
    CONF_COOLING_ENABLED,
    CONF_SUPPLY_TEMPERATURE_SENSOR,
    CONF_SURFACE_TEMPERATURE_SENSOR,
    CONF_CONDENSATION_MARGIN,
    CONF_SUPPLY_TEMPERATURE_MAX_AGE,
    CONF_SURFACE_TEMPERATURE_MAX_AGE,
)


def _picked(schema: vol.Schema, keys: frozenset[str]) -> vol.Schema:
    """Keep only the named fields of a schema."""
    return vol.Schema({key: value for key, value in schema.schema.items() if str(key) in keys})


def _is_hydronicus_thermostat(zone: Mapping[str, Any]) -> bool:
    thermostat = zone.get(CONF_THERMOSTAT)
    return isinstance(thermostat, Mapping) and thermostat.get("kind") == THERMOSTAT_KIND_HYDRONICUS


class ZoneSubentryFlowHandler(OwnEntityPickerMixin, config_entries.ConfigSubentryFlow):
    """Add or edit one zone."""

    _draft: ZoneDraft
    _proposed: dict[str, Any]
    _origin: Callable[[], Awaitable[config_entries.SubentryFlowResult]]
    _review_warnings: str
    _zone: dict[str, Any]
    _metadata_records: list[dict[str, Any]]
    _metadata_index: int
    _area_records: list[dict[str, Any]]
    _area_index: int
    _loop_id: str | None
    _loop_input: dict[str, Any]
    _loop_draft: ZoneDraft
    _loop_valve_ids: list[str]
    _valve_details: dict[str, dict[str, Any]]  # valve entity id -> valve details form
    _valve_index: int

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _zone_subentry(self) -> config_entries.ConfigSubentry:
        """Return the handle of the zone being reconfigured, ending the flow if it is gone."""
        try:
            return self._get_reconfigure_subentry()
        except config_entries.UnknownSubEntry as error:
            # The zone was deleted while this flow was open.
            raise AbortFlow("subentry_removed") from error

    def _stored_zone(self) -> ZoneDraft:
        """Return the stored records of the zone being reconfigured."""
        subentry = self._zone_subentry()
        return zone_draft(self._get_entry().data, str(subentry.data["id"]))

    def _propose(
        self, draft: ZoneDraft, fields: frozenset[str]
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Check a drafted zone against the whole graph and remember it when valid."""
        if not draft.routes:
            return {"base": "delivery_required"}, {}
        try:
            self._proposed = data_with_zone(self._get_entry().data, draft)
        except GRAPH_EDIT_ERRORS as error:
            return graph_errors(error, draft, fields)
        self._draft = draft
        return {}, {}

    async def _async_save(
        self, origin: Callable[[], Awaitable[config_entries.SubentryFlowResult]]
    ) -> config_entries.SubentryFlowResult | None:
        """Review warnings first, or save now; ``None`` means Dry run is still pending.

        A warning this change introduces, including an area warning that needs a
        confirmation, or an output newly shared with another Plant, needs an
        explicit confirmation. A warning the Plant already had does not. ``origin``
        submits the form that drafted the zone again, which reports why a Plant
        changed meanwhile rejects it.
        """
        self._origin = origin
        entry = self._get_entry()
        compiled = effective_plant_from_data(self._proposed).compiled
        sharing = shared_outputs(self.hass, entry.entry_id, self._proposed)
        before = effective_plant(entry).compiled
        areas = area_review_warnings(self.hass, self._proposed)
        if (
            sharing_to_confirm(sharing, shared_outputs(self.hass, entry.entry_id, entry.data))
            or warnings_to_confirm(compiled, before)
            or area_warnings_to_confirm(areas, area_review_warnings(self.hass, entry.data))
        ):
            self._review_warnings = warning_text(
                compiled,
                (
                    *(warning.message for warning in areas),
                    *(shared.message for shared in sharing),
                ),
            )
            return self._review_form()
        return await self._async_persist()

    async def _async_persist(self) -> config_entries.SubentryFlowResult | None:
        """Store the drafted zone and finish, or return ``None`` if Dry run is pending.

        The draft applies to the Plant as it is when the save happens. When another
        flow changed it so that the draft no longer fits, the drafting form is shown
        again with the reason.
        """
        entry = self._get_entry()
        draft = self._draft
        reconfiguring = self.source == config_entries.SOURCE_RECONFIGURE

        hass = self.hass

        def build(data: Mapping[str, Any]) -> dict[str, Any]:
            if reconfiguring:
                # A zone deleted meanwhile must not come back.
                self._zone_subentry()
            return data_with_zone(data, draft)

        def on_stored(previous: Mapping[str, Any], stored: Mapping[str, Any]) -> None:
            # A removed loop, or a valve whose entity the loop dropped, leaves no
            # entities or devices behind.
            async_remove_object_registrations(
                hass, entry, object_ids(previous) - object_ids(stored)
            )

        try:
            if not await async_persist_entry_data(self, entry, build, on_stored=on_stored):
                return None
        except GRAPH_EDIT_ERRORS:
            return await self._origin()
        title = str(draft.zone[CONF_NAME])
        if reconfiguring:
            return self.async_update_and_abort(entry, self._zone_subentry(), title=title)
        zone_id = str(draft.zone["id"])
        return self.async_create_entry(title=title, data={"id": zone_id}, unique_id=zone_id)

    def _review_form(
        self, errors: dict[str, str] | None = None
    ) -> config_entries.SubentryFlowResult:
        return self.async_show_form(
            step_id="review",
            data_schema=warning_review_schema(),
            errors=errors,
            description_placeholders={"warnings": self._review_warnings},
        )

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Confirm the listed warnings before saving the zone."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get("confirm", False):
                errors["base"] = "confirm_required"
            elif result := await self._async_persist():
                return result
            else:
                errors["base"] = "dry_run_shutdown_in_progress"
        return self._review_form(errors)

    # ------------------------------------------------------------------
    # Adding a zone
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Add a zone from its basics."""
        entry = self._get_entry()
        plant = effective_plant(entry)
        if not plant.configuration.pumps:
            return self.async_abort(reason="no_pumps")
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        schema = zone_form_schema(
            pumps=pump_options(plant), shared_loops=shared_loop_options(plant)
        )
        if user_input is not None:
            form_errors, placeholders = zone_form_errors(self.hass, user_input, plant)
            errors.update(form_errors)
            if not errors:
                draft = zone_draft_from_form(self.hass, user_input, plant=plant, existing=None)
                zone_id = str(draft.zone["id"])
                if any(subentry.unique_id == zone_id for subentry in entry.subentries.values()):
                    return self.async_abort(reason="already_configured")
                graph, placeholders = self._propose(draft, frozenset(schema.schema))
                errors.update(graph)
            if not errors:
                if result := await self._async_save(lambda: self.async_step_user(user_input)):
                    return result
                errors["base"] = "dry_run_shutdown_in_progress"
        return self.async_show_form(
            step_id="user",
            data_schema=with_submitted_values(self, schema, user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    # ------------------------------------------------------------------
    # Editing a zone
    # ------------------------------------------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Choose what to change about the zone."""
        current = self._stored_zone()
        options = ["zone"]
        if _is_hydronicus_thermostat(current.zone):
            options.append("thermostat")
        options.extend(["sensors", "add_loop"])
        if current.circuits:
            options.append("edit_loop")
        # A repair opens this menu directly, so it names the zone it edits.
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=options,
            description_placeholders={"zone": str(current.zone[CONF_NAME])},
        )

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Change the zone's name, areas, thermostat owner, sensors, and shared loops."""
        entry = self._get_entry()
        plant = effective_plant(entry)
        current = self._stored_zone()
        schema = zone_form_schema(
            pumps=(),
            shared_loops=shared_loop_options(plant),
            defaults=zone_form_defaults(current),
            include_valves=False,
        )
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            form_errors, placeholders = zone_form_errors(self.hass, user_input, plant)
            errors.update(form_errors)
            # Private loops deliver heat too, which zone basics cannot see.
            if current.circuits and errors.get("base") == "delivery_required":
                del errors["base"]
            if not errors:
                draft = zone_draft_from_form(self.hass, user_input, plant=plant, existing=current)
                graph, placeholders = self._propose(draft, frozenset(schema.schema))
                errors.update(graph)
            if not errors:
                if result := await self._async_save(lambda: self.async_step_zone(user_input)):
                    return result
                errors["base"] = "dry_run_shutdown_in_progress"
        return self.async_show_form(
            step_id="zone",
            data_schema=with_submitted_values(self, schema, user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_thermostat(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Change the Hydronicus thermostat settings."""
        current = self._stored_zone()
        schema = _picked(zone_schema(current.zone), _THERMOSTAT_FIELDS)
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            fields = flatten_sections(user_input)
            zone = deepcopy(current.zone)
            thermostat = dict(zone[CONF_THERMOSTAT])
            for key in (
                CONF_HEATING_START_DELTA,
                CONF_HEATING_STOP_DELTA,
                CONF_MINIMUM_ACTIVE_DURATION,
                CONF_MINIMUM_IDLE_DURATION,
                CONF_COOLING_START_DELTA,
                CONF_COOLING_STOP_DELTA,
            ):
                if key in fields:
                    thermostat[key] = fields[key]
            thermostat[CONF_PRESET_TARGETS] = {
                preset: fields[preset]
                for preset in ("comfort", "eco", "away")
                if fields.get(preset) is not None
            }
            zone[CONF_THERMOSTAT] = thermostat
            errors, placeholders = self._propose(
                ZoneDraft(
                    zone=zone,
                    circuits=current.circuits,
                    valves=current.valves,
                    routes=current.routes,
                ),
                frozenset(schema.schema),
            )
            if not errors:
                if result := await self._async_save(lambda: self.async_step_thermostat(user_input)):
                    return result
                errors["base"] = "dry_run_shutdown_in_progress"
        return self.async_show_form(
            step_id="thermostat",
            data_schema=with_submitted_values(self, schema, user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Change the areas, aggregation, and humidity sensors, or edit sensor metadata."""
        current = self._stored_zone()
        schema = _picked(zone_schema(current.zone), _SENSOR_FIELDS)
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            errors = own_entity_errors(self.hass, user_input)
            zone = deepcopy(current.zone)
            chosen = [str(area_id) for area_id in user_input.get(CONF_AREAS) or ()]
            if areas := areas_for(zone.get(CONF_AREAS), chosen):
                zone[CONF_AREAS] = areas
            else:
                zone.pop(CONF_AREAS, None)
            if (
                _is_hydronicus_thermostat(zone)
                and not sensor_entity_ids(zone.get(CONF_TEMPERATURE_SENSOR_METADATA))
                and not names_temperature_sensor(self.hass, chosen)
            ):
                errors[CONF_AREAS] = "no_temperature_source"
            aggregation = str(user_input[CONF_TEMPERATURE_AGGREGATION])
            zone[CONF_TEMPERATURE_AGGREGATION] = aggregation
            zone[CONF_HUMIDITY_SENSOR_METADATA] = sensor_metadata_for(
                zone.get(CONF_HUMIDITY_SENSOR_METADATA),
                [str(entity_id) for entity_id in user_input.get(CONF_HUMIDITY_SENSORS) or ()],
            )
            if not errors and user_input.get(CONF_CONFIGURE_SENSOR_METADATA):
                self._zone = zone
                self._metadata_records = []
                self._metadata_index = 0
                self._area_records = []
                self._area_index = 0
                return await self.async_step_sensor_metadata()
            if (
                not errors
                and requires_sensor_metadata_path(zone)
                and aggregation != current.zone.get(CONF_TEMPERATURE_AGGREGATION)
            ):
                errors["base"] = "sensor_metadata_required"
            if not errors:
                errors, placeholders = self._propose(
                    ZoneDraft(
                        zone=zone,
                        circuits=current.circuits,
                        valves=current.valves,
                        routes=current.routes,
                    ),
                    frozenset(schema.schema),
                )
            if not errors:
                if result := await self._async_save(lambda: self.async_step_sensors(user_input)):
                    return result
                errors["base"] = "dry_run_shutdown_in_progress"
        return self.async_show_form(
            step_id="sensors",
            data_schema=with_submitted_values(self, schema, user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_sensor_metadata(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Edit one temperature sensor at a time so its metadata stays typed."""
        sensor_ids = sensor_entity_ids(self._zone.get(CONF_TEMPERATURE_SENSOR_METADATA))
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
                    for record in self._zone[CONF_TEMPERATURE_SENSOR_METADATA]
                    if record.get(CONF_ENTITY_ID) == sensor_id
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
            self._zone[CONF_TEMPERATURE_SENSOR_METADATA] = self._metadata_records
        return await self.async_step_area_metadata()

    async def async_step_area_metadata(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Edit the settings of one area at a time, after the explicit sensors."""
        areas = self._zone.get(CONF_AREAS) or []
        if user_input is not None:
            area_id = str(areas[self._area_index][CONF_AREA_ID])
            self._area_records.append(area_metadata_record(area_id, user_input))
            self._area_index += 1
        if self._area_index < len(areas):
            area = areas[self._area_index]
            area_id = str(area[CONF_AREA_ID])
            resolution = resolve_area_sensors(self.hass, [area_id])
            return self.async_show_form(
                step_id="area_metadata",
                data_schema=area_metadata_schema(area),
                description_placeholders=_area_placeholders(resolution, area_id),
            )
        if self._area_records:
            self._zone[CONF_AREAS] = self._area_records
        return await self.async_step_sensor_policy()

    async def async_step_sensor_policy(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Choose the aggregation policy once every sensor has editable metadata."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            current = self._stored_zone()
            self._zone[CONF_TEMPERATURE_AGGREGATION] = user_input[CONF_TEMPERATURE_AGGREGATION]
            # Apply only the sensor settings to the zone as it is now, which another
            # flow may have changed while the metadata steps were open.
            zone = deepcopy(current.zone)
            for key in (
                CONF_AREAS,
                CONF_TEMPERATURE_SENSOR_METADATA,
                CONF_HUMIDITY_SENSOR_METADATA,
                CONF_TEMPERATURE_AGGREGATION,
            ):
                if key in self._zone:
                    zone[key] = deepcopy(self._zone[key])
                else:
                    zone.pop(key, None)
            errors, placeholders = self._propose(
                ZoneDraft(
                    zone=zone,
                    circuits=current.circuits,
                    valves=current.valves,
                    routes=current.routes,
                ),
                frozenset({CONF_TEMPERATURE_AGGREGATION}),
            )
            if not errors:
                if result := await self._async_save(
                    lambda: self.async_step_sensor_policy(user_input)
                ):
                    return result
                errors["base"] = "dry_run_shutdown_in_progress"
        return self.async_show_form(
            step_id="sensor_policy",
            data_schema=sensor_policy_schema(self._zone),
            errors=errors,
            description_placeholders=placeholders,
        )

    # ------------------------------------------------------------------
    # Loops
    # ------------------------------------------------------------------

    async def async_step_add_loop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Add a private loop to the zone."""
        if not effective_plant(self._get_entry()).configuration.pumps:
            return self.async_abort(reason="no_pumps")
        self._loop_id = None
        return await self.async_step_loop()

    async def async_step_edit_loop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Choose which private loop of the zone to edit."""
        current = self._stored_zone()
        if user_input is not None:
            self._loop_id = canonical_id(user_input[CONF_LOOP])
            return await self.async_step_loop()
        options = [
            selector.SelectOptionDict(value=str(circuit["id"]), label=str(circuit[CONF_NAME]))
            for circuit in current.circuits
        ]
        return self.async_show_form(
            step_id="edit_loop",
            data_schema=vol.Schema(
                {vol.Required(CONF_LOOP): topology_select(options, multiple=False)}
            ),
        )

    def _loop_schema(self, current: ZoneDraft, plant: EffectivePlant) -> vol.Schema:
        """Build the loop form, prefilled from the loop being edited."""
        circuit = next(
            (c for c in current.circuits if canonical_id(c["id"]) == self._loop_id),
            None,
        )
        private_valves = {canonical_id(valve["id"]): valve for valve in current.valves}
        defaults: dict[str, Any] = {}
        if circuit is not None:
            valve_ids = [canonical_id(valve_id) for valve_id in circuit[CONF_VALVE_IDS]]
            loop_valves = [private_valves[vid] for vid in valve_ids if vid in private_valves]
            defaults = {
                CONF_NAME: circuit[CONF_NAME],
                CONF_VALVES: [str(valve[CONF_ENTITY_ID]) for valve in loop_valves],
                CONF_SHARED_VALVES: [vid for vid in valve_ids if vid not in private_valves],
                CONF_PUMP: canonical_id(circuit[CONF_PUMP_ID]),
                CONF_VALVE_OPENING_TIME: (
                    loop_valves[0].get(CONF_OPENING_TIME, DEFAULT_VALVE_OPENING_TIME)
                    if loop_valves
                    else DEFAULT_VALVE_OPENING_TIME
                ),
            }
        elif len(plant.configuration.pumps) == 1:
            defaults[CONF_PUMP] = plant.configuration.pumps[0].id
        shared_valves = [
            selector.SelectOptionDict(value=valve.id, label=valve.name)
            for valve in plant.configuration.valves
            if valve.id not in plant.ownership.zone_objects
        ]
        schema: dict[Any, Any] = {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)): (
                name_selector()
            ),
            vol.Optional(
                CONF_VALVES,
                description={"suggested_value": defaults.get(CONF_VALVES) or None},
            ): valve_entity_selector(),
        }
        if shared_valves:
            schema[
                vol.Optional(
                    CONF_SHARED_VALVES,
                    description={"suggested_value": defaults.get(CONF_SHARED_VALVES) or None},
                )
            ] = topology_select(shared_valves, multiple=True)
        schema.update(
            {
                vol.Optional(
                    CONF_PUMP, description={"suggested_value": defaults.get(CONF_PUMP)}
                ): topology_select(pump_options(plant), multiple=False),
                vol.Required(
                    CONF_VALVE_OPENING_TIME,
                    default=defaults.get(CONF_VALVE_OPENING_TIME, DEFAULT_VALVE_OPENING_TIME),
                ): seconds_selector(),
                vol.Optional(CONF_CONFIGURE_VALVE_FEEDBACK, default=False): (
                    selector.BooleanSelector()
                ),
                vol.Optional(SECTION_COOLING): collapsed_section(
                    cooling_reference_fields(circuit or {})
                ),
            }
        )
        if circuit is not None:
            schema[vol.Optional(CONF_REMOVE_LOOP, default=False)] = selector.BooleanSelector()
        return vol.Schema(schema)

    def _drafted_loop(
        self, current: ZoneDraft, user_input: Mapping[str, Any]
    ) -> tuple[ZoneDraft, list[str]]:
        """Apply the loop form to the zone, returning the loop's private valve ids.

        Within a zone a valve's identity is its entity ID: a retained entity keeps
        its valve, a new entity creates one, and a dropped entity removes its valve
        unless another loop of the zone still uses it.
        """
        fields = flatten_sections(user_input)
        zone_id = str(current.zone["id"])
        circuits = deepcopy(current.circuits)
        routes = deepcopy(current.routes)
        if fields.get(CONF_REMOVE_LOOP):
            circuits = [c for c in circuits if canonical_id(c["id"]) != self._loop_id]
            routes = [r for r in routes if canonical_id(r["circuit_id"]) != self._loop_id]
            return self._with_used_valves(current, circuits, routes, []), []
        name = str(fields[CONF_NAME]).strip()
        opening_time = fields.get(CONF_VALVE_OPENING_TIME, DEFAULT_VALVE_OPENING_TIME)
        by_entity = {str(valve[CONF_ENTITY_ID]): deepcopy(valve) for valve in current.valves}
        entities = list(dict.fromkeys(str(e) for e in fields.get(CONF_VALVES) or ()))
        new = new_valves(
            name,
            [entity_id for entity_id in entities if entity_id not in by_entity],
            taken_names={str(valve[CONF_NAME]) for valve in current.valves},
            opening_time=opening_time,
        )
        by_entity.update({str(valve[CONF_ENTITY_ID]): valve for valve in new})
        loop_valves = [by_entity[entity_id] for entity_id in entities]
        for valve in loop_valves:
            valve[CONF_OPENING_TIME] = opening_time
        private_ids = [str(valve["id"]) for valve in loop_valves]
        existing = next((c for c in circuits if canonical_id(c["id"]) == self._loop_id), None)
        circuit = deepcopy(existing) if existing is not None else {"id": str(uuid4())}
        circuit.update(
            {
                CONF_NAME: name,
                CONF_VALVE_IDS: [
                    *private_ids,
                    *(str(value) for value in fields.get(CONF_SHARED_VALVES) or ()),
                ],
                CONF_PUMP_ID: str(fields[CONF_PUMP]),
                **{key: fields.get(key, _COOLING_DEFAULTS[key]) for key in _LOOP_COOLING_FIELDS},
            }
        )
        if existing is None:
            circuits.append(circuit)
            routes.append(new_route(zone_id, str(circuit["id"])))
        else:
            circuits = [circuit if c is existing else c for c in circuits]
        draft = self._with_used_valves(current, circuits, routes, loop_valves)
        return draft, [canonical_id(valve_id) for valve_id in private_ids]

    @staticmethod
    def _with_used_valves(
        current: ZoneDraft,
        circuits: list[dict[str, Any]],
        routes: list[dict[str, Any]],
        loop_valves: Sequence[dict[str, Any]],
    ) -> ZoneDraft:
        """Keep the zone valves its loops still use, updated by the edited loop."""
        edited = {canonical_id(valve["id"]): valve for valve in loop_valves}
        candidates = [
            edited.pop(canonical_id(valve["id"]), valve) for valve in deepcopy(current.valves)
        ] + list(edited.values())
        used = {canonical_id(valve_id) for c in circuits for valve_id in c[CONF_VALVE_IDS]}
        return ZoneDraft(
            zone=deepcopy(current.zone),
            circuits=circuits,
            valves=[valve for valve in candidates if canonical_id(valve["id"]) in used],
            routes=routes,
        )

    def _loop_errors(self, user_input: Mapping[str, Any]) -> dict[str, str]:
        """Return the form errors of a submitted loop."""
        errors: dict[str, str] = {}
        if user_input.get(CONF_REMOVE_LOOP):
            return errors
        if not str(user_input.get(CONF_NAME, "")).strip():
            errors[CONF_NAME] = "name_required"
        # vol.Required accepts an empty list, so the valve selection is checked explicitly.
        if not user_input.get(CONF_VALVES) and not user_input.get(CONF_SHARED_VALVES):
            errors[CONF_VALVES] = "valves_required"
        if not user_input.get(CONF_PUMP):
            errors[CONF_PUMP] = "pump_required"
        errors.update(own_entity_errors(self.hass, user_input))
        return errors

    def _loop_form(
        self,
        user_input: Mapping[str, Any] | None,
        errors: dict[str, str] | None = None,
        placeholders: dict[str, str] | None = None,
    ) -> config_entries.SubentryFlowResult:
        current = self._stored_zone()
        schema = self._loop_schema(current, effective_plant(self._get_entry()))
        return self.async_show_form(
            step_id="loop",
            data_schema=with_submitted_values(self, schema, user_input),
            errors=errors,
            description_placeholders={"zone": str(current.zone[CONF_NAME]), **(placeholders or {})},
        )

    async def async_step_loop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Add or edit one private loop of the zone."""
        if user_input is None:
            return self._loop_form(None)
        errors = self._loop_errors(user_input)
        if errors:
            return self._loop_form(user_input, errors)
        self._loop_input = dict(user_input)
        self._valve_details = {}
        self._loop_draft, self._loop_valve_ids = self._drafted_loop(self._stored_zone(), user_input)
        if user_input.get(CONF_CONFIGURE_VALVE_FEEDBACK) and self._loop_valve_ids:
            self._valve_index = 0
            return await self.async_step_valve_details()
        return await self._async_finish_loop()

    async def _async_finish_loop(self) -> config_entries.SubentryFlowResult:
        """Propose the edited loop, showing any error on the loop form.

        The loop and the valve details apply to the zone as it is now, because
        another flow may have changed it while the valve details were open.
        """
        current = self._stored_zone()
        draft, _ = self._drafted_loop(current, self._loop_input)
        for valve in draft.valves:
            if details := self._valve_details.get(str(valve[CONF_ENTITY_ID])):
                _apply_valve_details(valve, details)
        fields = frozenset(self._loop_schema(current, effective_plant(self._get_entry())).schema)
        errors, placeholders = self._propose(draft, fields)
        if not errors:
            if result := await self._async_save(self._async_finish_loop):
                return result
            errors["base"] = "dry_run_shutdown_in_progress"
        return self._loop_form(self._loop_input, errors, placeholders)

    async def async_step_valve_details(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Set the feedback entities of each private valve of the loop."""
        valves = {canonical_id(valve["id"]): valve for valve in self._loop_draft.valves}
        valve = valves[self._loop_valve_ids[self._valve_index]]
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = own_entity_errors(self.hass, user_input)
            if not errors:
                self._valve_details[str(valve[CONF_ENTITY_ID])] = dict(user_input)
                self._valve_index += 1
                if self._valve_index >= len(self._loop_valve_ids):
                    return await self._async_finish_loop()
                valve = valves[self._loop_valve_ids[self._valve_index]]
                user_input = None
        return self.async_show_form(
            step_id="valve_details",
            data_schema=with_submitted_values(
                self, vol.Schema(valve_feedback_fields(valve)), user_input
            ),
            errors=errors,
            description_placeholders={
                "valve": str(valve[CONF_NAME]),
                "entity": str(valve[CONF_ENTITY_ID]),
            },
        )


def _area_placeholders(resolution: AreaResolution, area_id: str) -> dict[str, str]:
    """Name an area and the sensors it names, which its settings apply to."""
    sensors = resolution.area_sensors.get(area_id)
    return {
        "area": resolution.name(area_id),
        "temperature_sensor": (sensors and sensors.temperature_entity_id) or "None",
        "humidity_sensor": (sensors and sensors.humidity_entity_id) or "None",
    }


def _apply_valve_details(valve: dict[str, Any], details: Mapping[str, Any]) -> None:
    """Set the feedback entities of one valve from its valve details form."""
    if readiness := details.get(CONF_VALVE_READINESS_ENTITY):
        valve[CONF_VALVE_READINESS_ENTITY] = readiness
    else:
        valve.pop(CONF_VALVE_READINESS_ENTITY, None)
    valve[CONF_POSITION_FEEDBACK_ENTITY] = details.get(CONF_POSITION_FEEDBACK_ENTITY) or None
    valve[CONF_POSITION_FEEDBACK_MAX_AGE] = details[CONF_POSITION_FEEDBACK_MAX_AGE]


_COOLING_DEFAULTS: dict[str, Any] = {
    CONF_COOLING_ENABLED: False,
    CONF_SUPPLY_TEMPERATURE_SENSOR: None,
    CONF_SURFACE_TEMPERATURE_SENSOR: None,
    CONF_CONDENSATION_MARGIN: DEFAULT_CONDENSATION_MARGIN,
    CONF_SUPPLY_TEMPERATURE_MAX_AGE: DEFAULT_REFERENCE_MAX_AGE,
    CONF_SURFACE_TEMPERATURE_MAX_AGE: DEFAULT_REFERENCE_MAX_AGE,
}
