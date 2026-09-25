"""Room subentry flow.

A room is one zone with its thermostat and sensors, its Delivery Routes, and
its private loops and valves. Adding a room asks for the room basics; editing
one opens a menu of focused steps. Every save applies the whole room with
``data_with_room``, reviews warnings when needed, and reaches Dry run first.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from ..const import (
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
    RoomDraft,
    data_with_room,
    effective_plant,
    effective_plant_from_data,
    room_draft,
)
from .common import (
    SECTION_COOLING,
    OwnEntityPickerMixin,
    async_persist_entry_data,
    collapsed_section,
    cooling_reference_fields,
    flatten_sections,
    name_selector,
    other_plant_sharing_warnings,
    own_entity_errors,
    requires_sensor_metadata_path,
    seconds_selector,
    sensor_metadata_record,
    sensor_metadata_schema,
    sensor_policy_schema,
    topology_select,
    valve_feedback_fields,
    warning_review_schema,
    warning_text,
    warnings_to_confirm,
    with_submitted_values,
    zone_schema,
)
from .room_form import (
    CONF_PUMP,
    canonical_id,
    graph_errors,
    new_route,
    new_valves,
    pump_options,
    room_draft_from_form,
    room_form_defaults,
    room_form_errors,
    room_form_schema,
    sensor_entity_ids,
    sensor_metadata_for,
    shared_loop_options,
    valve_entity_selector,
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
    {CONF_TEMPERATURE_AGGREGATION, CONF_HUMIDITY_SENSORS, CONF_CONFIGURE_SENSOR_METADATA}
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


class RoomSubentryFlowHandler(OwnEntityPickerMixin, config_entries.ConfigSubentryFlow):
    """Add or edit one room."""

    _draft: RoomDraft
    _proposed: dict[str, Any]
    _review_warnings: str
    _zone: dict[str, Any]
    _metadata_records: list[dict[str, Any]]
    _metadata_index: int
    _loop_id: str | None
    _loop_input: dict[str, Any]
    _loop_draft: RoomDraft
    _loop_valve_ids: list[str]
    _valve_index: int

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _room(self) -> RoomDraft:
        """Return the stored records of the room being reconfigured."""
        subentry = self._get_reconfigure_subentry()
        return room_draft(self._get_entry().data, str(subentry.data["id"]))

    def _propose(
        self, draft: RoomDraft, fields: frozenset[str]
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Check a drafted room against the whole graph and remember it when valid."""
        if not draft.routes:
            return {"base": "delivery_required"}, {}
        try:
            self._proposed = data_with_room(self._get_entry().data, draft)
        except GRAPH_EDIT_ERRORS as error:
            return graph_errors(error, draft, fields)
        self._draft = draft
        return {}, {}

    def _sharing(self) -> tuple[str, ...]:
        """Describe room valves that another Plant already binds."""
        return other_plant_sharing_warnings(
            self.hass,
            self._get_entry().entry_id,
            (valve.get(CONF_ENTITY_ID) for valve in self._draft.valves),
        )

    async def _async_save(self) -> config_entries.SubentryFlowResult | None:
        """Review warnings first, or save now; ``None`` means Dry run is still pending.

        A warning this change introduces, or an output shared with another Plant,
        needs an explicit confirmation.
        """
        compiled = effective_plant_from_data(self._proposed).compiled
        sharing = self._sharing()
        before = effective_plant(self._get_entry()).compiled
        if sharing or warnings_to_confirm(compiled, before):
            self._review_warnings = warning_text(compiled, sharing)
            return self._review_form()
        return await self._async_persist()

    async def _async_persist(self) -> config_entries.SubentryFlowResult | None:
        """Store the drafted room and finish, or return ``None`` if Dry run is pending."""
        entry = self._get_entry()
        data = data_with_room(entry.data, self._draft)
        if not await async_persist_entry_data(self, entry, data):
            return None
        title = str(self._draft.zone[CONF_NAME])
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return self.async_update_and_abort(entry, self._get_reconfigure_subentry(), title=title)
        zone_id = str(self._draft.zone["id"])
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
        """Confirm the listed warnings before saving the room."""
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
    # Adding a room
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Add a room from its basics."""
        entry = self._get_entry()
        plant = effective_plant(entry)
        if not plant.configuration.pumps:
            return self.async_abort(reason="no_pumps")
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        schema = room_form_schema(
            pumps=pump_options(plant), shared_loops=shared_loop_options(plant)
        )
        if user_input is not None:
            form_errors, placeholders = room_form_errors(self.hass, user_input, plant)
            errors.update(form_errors)
            if not errors:
                draft = room_draft_from_form(user_input, plant=plant, existing=None)
                zone_id = str(draft.zone["id"])
                if any(subentry.unique_id == zone_id for subentry in entry.subentries.values()):
                    return self.async_abort(reason="already_configured")
                graph, placeholders = self._propose(draft, frozenset(schema.schema))
                errors.update(graph)
            if not errors:
                if result := await self._async_save():
                    return result
                errors["base"] = "dry_run_shutdown_in_progress"
        return self.async_show_form(
            step_id="user",
            data_schema=with_submitted_values(self, schema, user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    # ------------------------------------------------------------------
    # Editing a room
    # ------------------------------------------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Choose what to change about the room."""
        room = self._room()
        options = ["room"]
        if _is_hydronicus_thermostat(room.zone):
            options.append("thermostat")
        options.extend(["sensors", "add_loop"])
        if room.circuits:
            options.append("edit_loop")
        return self.async_show_menu(step_id="reconfigure", menu_options=options)

    async def async_step_room(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Change the room's name, thermostat owner, temperature sensors, and shared loops."""
        entry = self._get_entry()
        plant = effective_plant(entry)
        room = self._room()
        schema = room_form_schema(
            pumps=(),
            shared_loops=shared_loop_options(plant),
            defaults=room_form_defaults(room),
            include_valves=False,
        )
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            form_errors, placeholders = room_form_errors(self.hass, user_input, plant)
            errors.update(form_errors)
            # Private loops deliver heat too, which room basics cannot see.
            if room.circuits and errors.get("base") == "delivery_required":
                del errors["base"]
            if not errors:
                draft = room_draft_from_form(user_input, plant=plant, existing=room)
                graph, placeholders = self._propose(draft, frozenset(schema.schema))
                errors.update(graph)
            if not errors:
                if result := await self._async_save():
                    return result
                errors["base"] = "dry_run_shutdown_in_progress"
        return self.async_show_form(
            step_id="room",
            data_schema=with_submitted_values(self, schema, user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_thermostat(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Change the Hydronicus thermostat settings."""
        room = self._room()
        schema = _picked(zone_schema([], room.zone, include_circuits=False), _THERMOSTAT_FIELDS)
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            fields = flatten_sections(user_input)
            zone = deepcopy(room.zone)
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
                RoomDraft(
                    zone=zone, circuits=room.circuits, valves=room.valves, routes=room.routes
                ),
                frozenset(schema.schema),
            )
            if not errors:
                if result := await self._async_save():
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
        """Change the temperature aggregation and humidity sensors, or edit sensor metadata."""
        room = self._room()
        schema = _picked(zone_schema([], room.zone, include_circuits=False), _SENSOR_FIELDS)
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            errors = own_entity_errors(self.hass, user_input)
            zone = deepcopy(room.zone)
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
                return await self.async_step_sensor_metadata()
            if (
                not errors
                and requires_sensor_metadata_path(zone)
                and aggregation != room.zone.get(CONF_TEMPERATURE_AGGREGATION)
            ):
                errors["base"] = "sensor_metadata_required"
            if not errors:
                errors, placeholders = self._propose(
                    RoomDraft(
                        zone=zone, circuits=room.circuits, valves=room.valves, routes=room.routes
                    ),
                    frozenset(schema.schema),
                )
            if not errors:
                if result := await self._async_save():
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
        return await self.async_step_sensor_policy()

    async def async_step_sensor_policy(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Choose the aggregation policy once every sensor has editable metadata."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            room = self._room()
            self._zone[CONF_TEMPERATURE_AGGREGATION] = user_input[CONF_TEMPERATURE_AGGREGATION]
            errors, placeholders = self._propose(
                RoomDraft(
                    zone=self._zone, circuits=room.circuits, valves=room.valves, routes=room.routes
                ),
                frozenset({CONF_TEMPERATURE_AGGREGATION}),
            )
            if not errors:
                if result := await self._async_save():
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
        """Add a private loop to the room."""
        if not effective_plant(self._get_entry()).configuration.pumps:
            return self.async_abort(reason="no_pumps")
        self._loop_id = None
        return await self.async_step_loop()

    async def async_step_edit_loop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Choose which private loop of the room to edit."""
        room = self._room()
        if user_input is not None:
            self._loop_id = canonical_id(user_input[CONF_LOOP])
            return await self.async_step_loop()
        options = [
            selector.SelectOptionDict(value=str(circuit["id"]), label=str(circuit[CONF_NAME]))
            for circuit in room.circuits
        ]
        return self.async_show_form(
            step_id="edit_loop",
            data_schema=vol.Schema(
                {vol.Required(CONF_LOOP): topology_select(options, multiple=False)}
            ),
        )

    def _loop_schema(self, room: RoomDraft, plant: EffectivePlant) -> vol.Schema:
        """Build the loop form, prefilled from the loop being edited."""
        circuit = next(
            (c for c in room.circuits if canonical_id(c["id"]) == self._loop_id),
            None,
        )
        private_valves = {canonical_id(valve["id"]): valve for valve in room.valves}
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
            if valve.id not in plant.ownership.room_objects
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
        self, room: RoomDraft, user_input: Mapping[str, Any]
    ) -> tuple[RoomDraft, list[str]]:
        """Apply the loop form to the room, returning the loop's private valve ids.

        Within a room a valve's identity is its entity ID: a retained entity keeps
        its valve, a new entity creates one, and a dropped entity removes its valve
        unless another loop of the room still uses it.
        """
        fields = flatten_sections(user_input)
        zone_id = str(room.zone["id"])
        circuits = deepcopy(room.circuits)
        routes = deepcopy(room.routes)
        if fields.get(CONF_REMOVE_LOOP):
            circuits = [c for c in circuits if canonical_id(c["id"]) != self._loop_id]
            routes = [r for r in routes if canonical_id(r["circuit_id"]) != self._loop_id]
            return self._with_used_valves(room, circuits, routes, []), []
        name = str(fields[CONF_NAME]).strip()
        opening_time = fields.get(CONF_VALVE_OPENING_TIME, DEFAULT_VALVE_OPENING_TIME)
        by_entity = {str(valve[CONF_ENTITY_ID]): deepcopy(valve) for valve in room.valves}
        entities = list(dict.fromkeys(str(e) for e in fields.get(CONF_VALVES) or ()))
        new = new_valves(
            name,
            [entity_id for entity_id in entities if entity_id not in by_entity],
            taken_names={str(valve[CONF_NAME]) for valve in room.valves},
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
        draft = self._with_used_valves(room, circuits, routes, loop_valves)
        return draft, [canonical_id(valve_id) for valve_id in private_ids]

    @staticmethod
    def _with_used_valves(
        room: RoomDraft,
        circuits: list[dict[str, Any]],
        routes: list[dict[str, Any]],
        loop_valves: Sequence[dict[str, Any]],
    ) -> RoomDraft:
        """Keep the room valves its loops still use, updated by the edited loop."""
        edited = {canonical_id(valve["id"]): valve for valve in loop_valves}
        candidates = [
            edited.pop(canonical_id(valve["id"]), valve) for valve in deepcopy(room.valves)
        ] + list(edited.values())
        used = {canonical_id(valve_id) for c in circuits for valve_id in c[CONF_VALVE_IDS]}
        return RoomDraft(
            zone=deepcopy(room.zone),
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
        room = self._room()
        schema = self._loop_schema(room, effective_plant(self._get_entry()))
        return self.async_show_form(
            step_id="loop",
            data_schema=with_submitted_values(self, schema, user_input),
            errors=errors,
            description_placeholders={"room": str(room.zone[CONF_NAME]), **(placeholders or {})},
        )

    async def async_step_loop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Add or edit one private loop of the room."""
        if user_input is None:
            return self._loop_form(None)
        errors = self._loop_errors(user_input)
        if errors:
            return self._loop_form(user_input, errors)
        self._loop_input = dict(user_input)
        self._loop_draft, self._loop_valve_ids = self._drafted_loop(self._room(), user_input)
        if user_input.get(CONF_CONFIGURE_VALVE_FEEDBACK) and self._loop_valve_ids:
            self._valve_index = 0
            return await self.async_step_valve_details()
        return await self._async_finish_loop()

    async def _async_finish_loop(self) -> config_entries.SubentryFlowResult:
        """Propose the edited loop, showing any error on the loop form."""
        room = self._room()
        fields = frozenset(self._loop_schema(room, effective_plant(self._get_entry())).schema)
        errors, placeholders = self._propose(self._loop_draft, fields)
        if not errors:
            if result := await self._async_save():
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
                if readiness := user_input.get(CONF_VALVE_READINESS_ENTITY):
                    valve[CONF_VALVE_READINESS_ENTITY] = readiness
                else:
                    valve.pop(CONF_VALVE_READINESS_ENTITY, None)
                valve[CONF_POSITION_FEEDBACK_ENTITY] = (
                    user_input.get(CONF_POSITION_FEEDBACK_ENTITY) or None
                )
                valve[CONF_POSITION_FEEDBACK_MAX_AGE] = user_input[CONF_POSITION_FEEDBACK_MAX_AGE]
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


_COOLING_DEFAULTS: dict[str, Any] = {
    CONF_COOLING_ENABLED: False,
    CONF_SUPPLY_TEMPERATURE_SENSOR: None,
    CONF_SURFACE_TEMPERATURE_SENSOR: None,
    CONF_CONDENSATION_MARGIN: DEFAULT_CONDENSATION_MARGIN,
    CONF_SUPPLY_TEMPERATURE_MAX_AGE: DEFAULT_REFERENCE_MAX_AGE,
    CONF_SURFACE_TEMPERATURE_MAX_AGE: DEFAULT_REFERENCE_MAX_AGE,
}
