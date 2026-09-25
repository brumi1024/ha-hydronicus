"""Plant settings: the Plant entry's options menu, pumps, and the plant file."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from copy import deepcopy
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID, uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import selector

from ..areas import area_review_warnings, area_warnings_to_confirm
from ..const import (
    CONF_CIRCUITS,
    CONF_DRY_RUN,
    CONF_DRY_RUN_CONFIRMATION,
    CONF_ENTITY_ID,
    CONF_FAULT_FEEDBACK_ENTITY,
    CONF_FAULT_FEEDBACK_MAX_AGE,
    CONF_FLOW_FEEDBACK_ENTITY,
    CONF_FLOW_FEEDBACK_MAX_AGE,
    CONF_NAME,
    CONF_OVERRUN,
    CONF_PLANT_ID,
    CONF_POWER_FEEDBACK_ENTITY,
    CONF_POWER_FEEDBACK_MAX_AGE,
    CONF_PUMPS,
    CONF_ROUTES,
    CONF_SOURCES,
    CONF_VALVES,
    CONF_ZONES,
    DEFAULT_PUMP_OVERRUN,
    SUBENTRY_TYPE_SOURCE,
    SUBENTRY_TYPE_ZONE,
)
from ..core.configuration import StoredTopologyError
from ..core.model import CompiledPlant
from ..core.plant_document import ImportedPlant, PlantDocumentError, import_plant_document
from ..core.topology import DuplicateActuatorBindingError
from ..entry_configuration import (
    GRAPH_EDIT_ERRORS,
    EquipmentInUseError,
    authorization_output_lines,
    canonical_id,
    data_with_plant,
    data_with_pump,
    effective_plant,
    effective_plant_from_data,
    invalidate_output_authorization,
    object_ids,
    output_authorization,
    subentry_sync,
    topology_copy,
    zone_objects,
)
from ..plant_file import first_own_entity, parsed_plant_file, plant_file, plant_file_yaml
from ..registrations import async_move_object_registrations, async_remove_object_registrations
from .common import (
    DEFAULT_FEEDBACK_MAX_AGE,
    SECTION_FEEDBACK,
    OwnEntityPickerMixin,
    async_persist_entry_data,
    collapsed_section,
    dry_run_confirmation_schema,
    flatten_sections,
    max_age_selector,
    name_selector,
    optional_entity,
    other_plant_sharing_warnings,
    own_entity_errors,
    seconds_selector,
    sensor_selector,
    topology_select,
    warning_review_schema,
    warning_text,
    warnings_to_confirm,
    with_submitted_values,
)

CONF_DOCUMENT: Final = "document"
CONF_PUMP: Final = "pump"
CONF_REMOVE_PUMP: Final = "remove_pump"
CONF_CONFIRM: Final = "confirm"
MENU_OPTIONS: Final = ("dry_run", "add_pump", "edit_pump", "export_plant", "edit_plant")
# The path shown for a plant file error that no single key causes.
_TOP_LEVEL: Final = "the top level"
_PUMP_FEEDBACK: Final = (
    (CONF_POWER_FEEDBACK_ENTITY, CONF_POWER_FEEDBACK_MAX_AGE),
    (CONF_FLOW_FEEDBACK_ENTITY, CONF_FLOW_FEEDBACK_MAX_AGE),
    (CONF_FAULT_FEEDBACK_ENTITY, CONF_FAULT_FEEDBACK_MAX_AGE),
)
# Graph collections and the word the review's change list uses for their objects.
_CHANGE_KINDS: Final = (
    (CONF_ZONES, "zone"),
    (CONF_CIRCUITS, "loop"),
    (CONF_VALVES, "valve"),
    (CONF_PUMPS, "pump"),
    (CONF_SOURCES, "source"),
)
_SOURCE_SELECTOR: Final = "source_selector"


class _PlantChangedError(Exception):
    """The Plant changed after the plant file review listed its changes."""


def _dry_run_schema(default: bool) -> vol.Schema:
    """Return the Plant Dry run form schema."""
    return vol.Schema(
        {
            vol.Required(CONF_DRY_RUN, default=default): selector.BooleanSelector(),
        }
    )


def _pump_schema(defaults: Mapping[str, Any], *, editing: bool) -> vol.Schema:
    """Return the pump form, prefilled from a stored pump when editing."""
    feedback: dict[Any, Any] = {}
    for entity_key, age_key in _PUMP_FEEDBACK:
        entity_selector = (
            selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"])
            )
            if entity_key == CONF_FAULT_FEEDBACK_ENTITY
            else sensor_selector()
        )
        feedback[optional_entity(entity_key, defaults)] = entity_selector
        feedback[vol.Optional(age_key, default=defaults.get(age_key, DEFAULT_FEEDBACK_MAX_AGE))] = (
            max_age_selector()
        )
    fields: dict[Any, Any] = {
        vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)): name_selector(),
        vol.Required(
            CONF_ENTITY_ID, default=defaults.get(CONF_ENTITY_ID, vol.UNDEFINED)
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch")),
        vol.Required(
            CONF_OVERRUN, default=defaults.get(CONF_OVERRUN, DEFAULT_PUMP_OVERRUN)
        ): seconds_selector(),
        vol.Optional(SECTION_FEEDBACK): collapsed_section(feedback),
    }
    if editing:
        fields[vol.Optional(CONF_REMOVE_PUMP, default=False)] = selector.BooleanSelector()
    return vol.Schema(fields)


def _pump_record(
    pump_id: str, existing: Mapping[str, Any], user_input: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a stored pump record, keeping stored fields the form does not show."""
    fields = flatten_sections(user_input)
    record = deepcopy(dict(existing))
    record.update(
        {
            "id": pump_id,
            CONF_NAME: str(fields[CONF_NAME]).strip(),
            CONF_ENTITY_ID: str(fields[CONF_ENTITY_ID]),
            CONF_OVERRUN: fields[CONF_OVERRUN],
        }
    )
    # An edit that never opened the section keeps the stored feedback bindings.
    if SECTION_FEEDBACK in user_input:
        for entity_key, age_key in _PUMP_FEEDBACK:
            if entity_id := fields.get(entity_key):
                record[entity_key] = str(entity_id)
            else:
                record.pop(entity_key, None)
            record[age_key] = fields.get(age_key, DEFAULT_FEEDBACK_MAX_AGE)
    return record


# Every error a pump change can raise against the graph.
_PUMP_EDIT_ERRORS: Final = (EquipmentInUseError, *GRAPH_EDIT_ERRORS)


def _pump_edit_errors(error: Exception) -> tuple[dict[str, str], dict[str, str]]:
    """Map a rejected pump change to the pump form field that can fix it."""
    if isinstance(error, EquipmentInUseError):
        return {CONF_REMOVE_PUMP: "equipment_in_use"}, {"users": ", ".join(error.users)}
    if isinstance(error, DuplicateActuatorBindingError):
        return {CONF_ENTITY_ID: "actuator_entity_in_use"}, {}
    return {"base": "invalid_pump"}, {"error": str(error)}


def _signature(data: Mapping[str, Any]) -> tuple[Any, ...]:
    """Describe a Plant graph independent of record order, for change detection."""
    topology = topology_copy(data)
    collections = {
        collection: sorted(json.dumps(record, sort_keys=True) for record in records)
        for collection, records in topology.items()
        if isinstance(records, list)
    }
    return (
        data.get(CONF_NAME),
        json.dumps(collections, sort_keys=True),
        json.dumps(topology.get(_SOURCE_SELECTOR), sort_keys=True),
        zone_objects(data),
    )


def _owner_label(object_id: str, owners: Mapping[str, str], zones: Mapping[str, Any]) -> str:
    zone_id = owners.get(object_id)
    if zone_id is None:
        return "the Plant"
    return str(zones.get(zone_id, {}).get(CONF_NAME, zone_id))


def _plant_changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> str:
    """List what applying ``after`` changes in the Plant stored as ``before``."""
    lines: list[str] = []
    if before.get(CONF_NAME) != after.get(CONF_NAME):
        lines.append(f"Renames the Plant from {before.get(CONF_NAME)} to {after.get(CONF_NAME)}")
    old_topology, new_topology = topology_copy(before), topology_copy(after)
    old_owners, new_owners = zone_objects(before), zone_objects(after)
    old_zones = {canonical_id(zone.get("id")): zone for zone in old_topology[CONF_ZONES]}
    new_zones = {canonical_id(zone.get("id")): zone for zone in new_topology[CONF_ZONES]}
    for collection, kind in _CHANGE_KINDS:
        old = {canonical_id(record.get("id")): record for record in old_topology[collection]}
        new = {canonical_id(record.get("id")): record for record in new_topology[collection]}
        for object_id, record in new.items():
            if object_id not in old:
                lines.append(f"Adds {kind} {record.get(CONF_NAME)}")
        for object_id, record in old.items():
            if object_id not in new:
                lines.append(f"Removes {kind} {record.get(CONF_NAME)}")
        for object_id in old.keys() & new.keys():
            old_record, new_record = old[object_id], new[object_id]
            old_name, new_name = old_record.get(CONF_NAME), new_record.get(CONF_NAME)
            if old_name != new_name:
                lines.append(f"Renames {kind} {old_name} to {new_name}")
            if {key: value for key, value in old_record.items() if key != CONF_NAME} != {
                key: value for key, value in new_record.items() if key != CONF_NAME
            }:
                lines.append(f"Changes {kind} {new_name}")
            if old_owners.get(object_id) != new_owners.get(object_id):
                old_owner = _owner_label(object_id, old_owners, old_zones)
                new_owner = _owner_label(object_id, new_owners, new_zones)
                lines.append(f"Moves {kind} {new_name} from {old_owner} to {new_owner}")
    for zone_id in old_zones.keys() & new_zones.keys():
        if _routes_of(old_topology, zone_id) != _routes_of(new_topology, zone_id):
            lines.append(f"Changes the loops of zone {new_zones[zone_id].get(CONF_NAME)}")
    old_selector = old_topology.get(_SOURCE_SELECTOR)
    new_selector = new_topology.get(_SOURCE_SELECTOR)
    if old_selector is None and new_selector is not None:
        lines.append("Adds the source selector")
    elif old_selector is not None and new_selector is None:
        lines.append("Removes the source selector")
    elif old_selector != new_selector:
        lines.append("Changes the source selector")
    return "\n".join(f"- {line}" for line in lines) or "- None"


def _routes_of(topology: Mapping[str, Any], zone_id: str) -> list[str]:
    return sorted(
        json.dumps(route, sort_keys=True)
        for route in topology[CONF_ROUTES]
        if str(route.get("zone_id")) == zone_id
    )


def _handle_owners(
    entry: config_entries.ConfigEntry, data: Mapping[str, Any], kept: Iterable[str]
) -> dict[str, str | None]:
    """Return the subentry, or ``None`` for the Plant, that owns every object of ``data``."""
    handles = {
        (subentry.subentry_type, subentry.unique_id): subentry.subentry_id
        for subentry_id, subentry in entry.subentries.items()
        if subentry_id in kept
    }
    topology = topology_copy(data)
    owners: dict[str, str | None] = {}
    for zone in topology[CONF_ZONES]:
        zone_id = canonical_id(zone.get("id"))
        owners[zone_id] = handles.get((SUBENTRY_TYPE_ZONE, zone_id))
    for collection in (CONF_CIRCUITS, CONF_VALVES, CONF_PUMPS):
        for record in topology[collection]:
            owners[canonical_id(record.get("id"))] = None
    for source in topology[CONF_SOURCES]:
        source_id = canonical_id(source.get("id"))
        owners[source_id] = handles.get((SUBENTRY_TYPE_SOURCE, source_id))
    for object_id, zone_id in zone_objects(data).items():
        owners[object_id] = handles.get((SUBENTRY_TYPE_ZONE, zone_id))
    return owners


@callback
def async_apply_plant_handles(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    data: Mapping[str, Any],
    removed_object_ids: set[str],
) -> None:
    """Make the subentries and registrations of an entry match its new parent data.

    Everything here is synchronous: together with the parent data update that
    precedes it, the reload listener sees one consistent graph. New handles are
    added first, so objects can move into them; then every object's entities and
    devices move to their owner; then removed objects lose their registrations,
    and only then are vanished handles removed, which deletes nothing that moved.
    """
    sync = subentry_sync(entry, data)
    for handle in sync.add:
        hass.config_entries.async_add_subentry(
            entry,
            config_entries.ConfigSubentry(
                data=MappingProxyType(dict(handle["data"])),
                subentry_type=handle["subentry_type"],
                title=handle["title"],
                unique_id=handle["unique_id"],
            ),
        )
    kept = set(entry.subentries) - set(sync.remove)
    async_move_object_registrations(hass, entry, _handle_owners(entry, data, kept))
    async_remove_object_registrations(hass, entry, removed_object_ids)
    for subentry_id in sync.remove:
        hass.config_entries.async_remove_subentry(entry, subentry_id)
    for subentry_id, title in sync.retitle:
        hass.config_entries.async_update_subentry(entry, entry.subentries[subentry_id], title=title)
    if (name := str(data.get(CONF_NAME, ""))) and entry.title != name:
        hass.config_entries.async_update_entry(entry, title=name)


class PlantSettingsOptionsFlow(OwnEntityPickerMixin, config_entries.OptionsFlow):
    """Change Plant settings from the Plant entry's Configure button.

    Plant settings edit the Plant graph, which lives in the entry data, so every
    save stores entry data through ``async_persist_entry_data`` and ends with an
    abort. The entry's update listener then reloads the Plant, and the entry
    options stay unused.
    """

    _requested_dry_run: bool
    _shown_authorization: dict[str, Any]
    _pump_id: str | None
    _pump_input: dict[str, Any]  # the submitted pump form
    _pump_edit: tuple[str, dict[str, Any] | None]  # pump id, new record or None to remove
    _pump_review_warnings: str
    _imported: ImportedPlant
    _document: Any  # the submitted plant file
    _reviewed: tuple[Any, ...]  # the signature of the Plant the review showed
    _review_blocking: bool

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Show the Plant settings menu."""
        entry = self.config_entry
        options = [
            option for option in MENU_OPTIONS if option != "edit_pump" or self._pump_options(entry)
        ]
        # A repair opens this menu directly, so it names the Plant it edits.
        return self.async_show_menu(
            step_id="init",
            menu_options=options,
            description_placeholders={"plant": entry.title},
        )

    # Dry run

    async def async_step_dry_run(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Change the Plant Dry run setting."""
        entry = self.config_entry
        # A Plant held in Dry run by an output conflict is stored live but is
        # not live, so the form offers its effective setting. Leaving Dry run then
        # takes the confirmed, conflict-checked path; choosing Dry run stores it.
        runtime = getattr(entry, "runtime_data", None)
        current_dry_run = (
            bool(runtime.dry_run)
            if runtime is not None
            else bool(entry.data.get(CONF_DRY_RUN, True))
        )
        if user_input is not None:
            requested_dry_run = bool(user_input[CONF_DRY_RUN])
            if requested_dry_run is False and current_dry_run:
                self._requested_dry_run = False
                return await self.async_step_dry_run_confirmation()
            return await self._async_apply_dry_run(entry, requested_dry_run)
        return self.async_show_form(
            step_id="dry_run",
            data_schema=_dry_run_schema(current_dry_run),
        )

    async def async_step_dry_run_confirmation(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm the exact heating outputs before leaving Dry run."""
        entry = self.config_entry
        if user_input is None:
            return self._dry_run_confirmation_form(entry)
        if not user_input.get(CONF_DRY_RUN_CONFIRMATION, False):
            return self._dry_run_confirmation_form(
                entry, errors={"base": "dry_run_confirmation_required"}
            )
        try:
            # Authorize exactly the outputs the form showed, never a later graph.
            return await self._async_apply_dry_run(
                entry, self._requested_dry_run, authorization=self._shown_authorization
            )
        except ServiceValidationError as error:
            if error.translation_key == "output_authorization_mismatch":
                return self._dry_run_confirmation_form(entry, errors={"base": "outputs_changed"})
            if error.translation_key == "output_conflict":
                placeholders = dict(error.translation_placeholders or {})
                placeholders.pop("plant", None)
                return self._dry_run_confirmation_form(
                    entry, errors={"base": "output_conflict"}, placeholders=placeholders
                )
            raise

    def _dry_run_confirmation_form(
        self,
        entry: config_entries.ConfigEntry,
        *,
        errors: dict[str, str] | None = None,
        placeholders: Mapping[str, str] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Show the current outputs and remember exactly what the user confirms."""
        data = entry.data
        self._shown_authorization = output_authorization(data)
        return self.async_show_form(
            step_id="dry_run_confirmation",
            data_schema=dry_run_confirmation_schema(),
            errors=errors,
            description_placeholders={
                "outputs": authorization_output_lines(data),
                **(placeholders or {}),
            },
        )

    async def _async_apply_dry_run(
        self,
        entry: config_entries.ConfigEntry,
        dry_run: bool,
        *,
        authorization: Mapping[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Apply Dry run, completing any active heating shutdown first."""
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None:
            if not await runtime.async_set_dry_run(
                dry_run,
                hass=self.hass,
                authorization=authorization,
            ):
                return self.async_show_form(
                    step_id="dry_run",
                    data_schema=_dry_run_schema(dry_run),
                    errors={"base": "dry_run_shutdown_in_progress"},
                )
        else:
            if not dry_run:
                return self.async_show_form(
                    step_id="dry_run",
                    data_schema=_dry_run_schema(bool(entry.data.get(CONF_DRY_RUN, True))),
                    errors={"base": "dry_run_runtime_unavailable"},
                )
            data = invalidate_output_authorization(entry.data)
            self.hass.config_entries.async_update_entry(entry, data=data)
        return self.async_abort(reason="settings_saved")

    # Pumps

    @staticmethod
    def _pump_options(entry: config_entries.ConfigEntry) -> list[selector.SelectOptionDict]:
        """Return the Plant pumps as select options, or none when the graph is unreadable."""
        try:
            pumps = topology_copy(entry.data)[CONF_PUMPS]
        except GRAPH_EDIT_ERRORS:
            return []
        return [
            selector.SelectOptionDict(
                value=canonical_id(pump.get("id")),
                label=str(pump.get(CONF_NAME, canonical_id(pump.get("id")))),
            )
            for pump in pumps
        ]

    def _stored_pump(self, entry: config_entries.ConfigEntry) -> dict[str, Any]:
        if self._pump_id is None:
            return {}
        for pump in topology_copy(entry.data)[CONF_PUMPS]:
            if canonical_id(pump.get("id")) == self._pump_id:
                return pump
        return {}

    async def async_step_add_pump(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Open an empty pump form."""
        self._pump_id = None
        return await self.async_step_pump()

    async def async_step_edit_pump(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose the Plant pump to edit."""
        entry = self.config_entry
        options = self._pump_options(entry)
        if user_input is not None:
            self._pump_id = str(user_input[CONF_PUMP])
            return await self.async_step_pump()
        return self.async_show_form(
            step_id="edit_pump",
            data_schema=vol.Schema(
                {vol.Required(CONF_PUMP): topology_select(options, multiple=False)}
            ),
        )

    async def async_step_pump(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add, edit, or remove one Plant pump, reviewing the warnings it introduces."""
        entry = self.config_entry
        existing = self._stored_pump(entry)
        editing = self._pump_id is not None
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            errors.update(own_entity_errors(self.hass, user_input))
            if not str(user_input.get(CONF_NAME, "")).strip():
                errors[CONF_NAME] = "name_required"
            if not errors:
                pump_id = self._pump_id or str(uuid4())
                removing = editing and bool(user_input.get(CONF_REMOVE_PUMP, False))
                self._pump_input = dict(user_input)
                self._pump_edit = (
                    pump_id,
                    None if removing else _pump_record(pump_id, existing, user_input),
                )
                try:
                    # Check the current Plant first, then save against the Plant as it
                    # is once the safe shutdown completes.
                    if warnings := self._pump_warnings(entry, self._pump_data(entry.data)):
                        self._pump_review_warnings = warnings
                        return self._pump_review_form()
                    stored = await self._async_save_pump(entry)
                except _PUMP_EDIT_ERRORS as error:
                    graph, placeholders = _pump_edit_errors(error)
                    errors.update(graph)
                else:
                    if stored:
                        return self.async_abort(reason="settings_saved")
                    errors["base"] = "dry_run_shutdown_in_progress"
        return self.async_show_form(
            step_id="pump",
            data_schema=with_submitted_values(
                self, _pump_schema(existing, editing=editing), user_input
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    def _pump_data(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Apply the drafted pump change to Plant data, raising a graph edit error."""
        pump_id, record = self._pump_edit
        if self._pump_id is not None and not any(
            canonical_id(pump.get("id")) == pump_id for pump in topology_copy(data)[CONF_PUMPS]
        ):
            # A pump deleted meanwhile must not come back.
            raise StoredTopologyError("The pump was removed meanwhile.")
        return data_with_pump(data, pump_id, record)

    def _pump_warnings(self, entry: config_entries.ConfigEntry, proposed: Mapping[str, Any]) -> str:
        """Describe what the pump change needs confirmed, or return an empty string.

        That is a compiler warning the change introduces (Decision 11), or a pump
        entity another Plant already binds, which is confirmed on every save.
        """
        compiled = effective_plant_from_data(proposed).compiled
        _pump_id, record = self._pump_edit
        sharing = (
            other_plant_sharing_warnings(self.hass, entry.entry_id, (record[CONF_ENTITY_ID],))
            if record is not None
            else ()
        )
        try:
            before: CompiledPlant | None = effective_plant(entry).compiled
        except GRAPH_EDIT_ERRORS:
            before = None
        if sharing or warnings_to_confirm(compiled, before):
            return warning_text(compiled, sharing)
        return ""

    async def _async_save_pump(self, entry: config_entries.ConfigEntry) -> bool:
        """Store the drafted pump change once the Plant reached Dry run.

        A removed pump leaves no entities or devices behind. A graph edit error
        against a Plant that changed meanwhile stores nothing and is raised.
        """
        hass = self.hass

        def on_stored(previous: Mapping[str, Any], stored: Mapping[str, Any]) -> None:
            async_remove_object_registrations(
                hass, entry, object_ids(previous) - object_ids(stored)
            )

        return await async_persist_entry_data(self, entry, self._pump_data, on_stored=on_stored)

    def _pump_review_form(
        self, errors: dict[str, str] | None = None
    ) -> config_entries.ConfigFlowResult:
        return self.async_show_form(
            step_id="pump_review",
            data_schema=warning_review_schema(),
            errors=errors,
            description_placeholders={"warnings": self._pump_review_warnings},
        )

    async def async_step_pump_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm the listed warnings before saving the pump.

        A Plant that changed meanwhile so that the pump no longer fits sends the
        user back to the pump form, which explains why.
        """
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_CONFIRM, False):
                errors["base"] = "confirm_required"
            else:
                try:
                    stored = await self._async_save_pump(entry)
                except _PUMP_EDIT_ERRORS:
                    return await self.async_step_pump(self._pump_input)
                if stored:
                    return self.async_abort(reason="settings_saved")
                errors["base"] = "dry_run_shutdown_in_progress"
        return self._pump_review_form(errors)

    # Plant file

    async def async_step_export_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Show the plant file of this Plant."""
        entry = self.config_entry
        try:
            document = plant_file_yaml(plant_file(entry.data))
        except ValueError as error:
            # A stored graph that does not decode has no faithful plant file.
            return self.async_abort(
                reason="plant_file_unavailable", description_placeholders={"error": str(error)}
            )
        return self.async_abort(
            reason="plant_exported",
            description_placeholders={"document": f"```yaml\n{document}```"},
        )

    async def async_step_edit_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Edit the whole Plant as a plant file."""
        entry = self.config_entry
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            plant_id = str(UUID(str(entry.data[CONF_PLANT_ID])))
            try:
                imported = import_plant_document(
                    parsed_plant_file(user_input.get(CONF_DOCUMENT)), plant_id=plant_id
                )
                data = data_with_plant(entry.data, imported)
            except PlantDocumentError as error:
                errors["base"] = "invalid_document"
                placeholders = {"path": error.path or _TOP_LEVEL, "error": str(error)}
            except GRAPH_EDIT_ERRORS as error:
                errors["base"] = "invalid_document"
                placeholders = {"path": _TOP_LEVEL, "error": str(error)}
            else:
                if imported.plant_id != plant_id:
                    errors["base"] = "plant_id_mismatch"
                elif own := first_own_entity(self.hass, imported):
                    errors["base"] = "document_own_entity"
                    placeholders = {"path": own[0], "entity_id": own[1]}
                elif _signature(data) == _signature(entry.data):
                    return self.async_abort(reason="no_changes")
                else:
                    self._imported = imported
                    self._document = user_input.get(CONF_DOCUMENT)
                    return await self.async_step_edit_plant_review()
        return self.async_show_form(
            step_id="edit_plant",
            data_schema=with_submitted_values(self, self._edit_plant_schema(entry), user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    def _edit_plant_schema(self, entry: config_entries.ConfigEntry) -> vol.Schema:
        """Return the plant file editor, prefilled with the current export when it has one.

        The document is optional, like on import, so that an emptied or
        unparseable file reaches the flow and is explained there.
        """
        try:
            current: dict[str, Any] | None = plant_file(entry.data)
        except ValueError:
            # A stored graph without a faithful plant file can still be replaced.
            current = None
        key = (
            vol.Optional(CONF_DOCUMENT)
            if current is None
            else vol.Optional(CONF_DOCUMENT, description={"suggested_value": current})
        )
        return vol.Schema({key: selector.ObjectSelector()})

    async def async_step_edit_plant_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Review the changes of an edited plant file, then apply them.

        The review lists the changes against the Plant as it was shown. A Plant
        that another flow changed meanwhile is reviewed again before anything is
        applied, and a file that no longer fits it returns to the editor.
        """
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                if self._reviewed != _signature(entry.data):
                    raise _PlantChangedError
                if self._review_blocking and not user_input.get(CONF_CONFIRM, False):
                    errors["base"] = "confirm_required"
                elif await self._async_apply_plant(entry):
                    return self.async_abort(reason="settings_saved")
                else:
                    errors["base"] = "dry_run_shutdown_in_progress"
            except _PlantChangedError:
                errors["base"] = "plant_changed"
            except GRAPH_EDIT_ERRORS:
                return await self._async_edit_plant_again()
        try:
            return self._edit_plant_review_form(entry, errors)
        except GRAPH_EDIT_ERRORS:
            return await self._async_edit_plant_again()

    async def _async_edit_plant_again(self) -> config_entries.ConfigFlowResult:
        """Submit the file to the editor again, which explains why it no longer fits."""
        return await self.async_step_edit_plant({CONF_DOCUMENT: self._document})

    def _edit_plant_review_form(
        self, entry: config_entries.ConfigEntry, errors: dict[str, str]
    ) -> config_entries.ConfigFlowResult:
        """Show the changes against the current Plant, and remember which Plant was shown."""
        data = data_with_plant(entry.data, self._imported)
        compiled: CompiledPlant = self._imported.compiled
        sharing = other_plant_sharing_warnings(
            self.hass,
            entry.entry_id,
            (output["entity_id"] for output in output_authorization(data)["outputs"]),
        )
        try:
            before: CompiledPlant | None = effective_plant(entry).compiled
        except GRAPH_EDIT_ERRORS:
            # An unreadable stored graph can still be replaced by a plant file.
            before = None
        areas = area_review_warnings(self.hass, data)
        self._review_blocking = (
            bool(sharing)
            or bool(warnings_to_confirm(compiled, before))
            or bool(area_warnings_to_confirm(areas, area_review_warnings(self.hass, entry.data)))
        )
        self._reviewed = _signature(entry.data)
        blocking = self._review_blocking
        return self.async_show_form(
            step_id="edit_plant_review",
            data_schema=warning_review_schema() if blocking else vol.Schema({}),
            errors=errors,
            description_placeholders={
                "changes": _plant_changes(entry.data, data),
                "logic": "\n".join(f"- {line}" for line in compiled.logic_summary) or "- None",
                "warnings": warning_text(
                    compiled, (*(warning.message for warning in areas), *sharing)
                )
                or "- None",
            },
        )

    async def _async_apply_plant(self, entry: config_entries.ConfigEntry) -> bool:
        """Store the edited graph and bring subentries and registrations in line with it.

        The Plant must still be the one the review showed once the safe shutdown
        completes. The parent data and every handle and registration change are
        then applied with no await in between, so the reload listener sees one
        consistent graph.
        """
        reviewed = self._reviewed
        imported = self._imported
        hass = self.hass

        def build(current: Mapping[str, Any]) -> dict[str, Any]:
            if _signature(current) != reviewed:
                raise _PlantChangedError
            return data_with_plant(current, imported)

        def on_stored(previous: Mapping[str, Any], stored: Mapping[str, Any]) -> None:
            removed = object_ids(previous) - object_ids(stored)
            async_apply_plant_handles(hass, entry, stored, removed)

        return await async_persist_entry_data(self, entry, build, on_stored=on_stored)
