"""Helpers shared by the Hydronicus config and subentry flows."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow, section
from homeassistant.helpers import entity_registry as entity_registry_helper
from homeassistant.helpers import selector

from ..const import (
    CONF_DRY_RUN,
    CONF_DRY_RUN_CONFIRMATION,
    CONF_ENTITY_ID,
    CONF_FAULT_FEEDBACK_ENTITY,
    CONF_FLOW_FEEDBACK_ENTITY,
    CONF_HUMIDITY_SENSORS,
    CONF_NAME,
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
    DOMAIN,
    SUBENTRY_TYPE_SOURCE,
)
from ..core.configuration import (
    StoredTopologyError,
)
from ..core.model import (
    CompiledPlant,
)
from ..core.ownership import OwnershipError
from ..core.topology import (
    TopologyValidationError,
)
from ..entry_configuration import (
    GRAPH_EDIT_ERRORS,
    data_with_source,
    effective_plant_from_data,
)
from ..output_ownership import plants_binding_outputs

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


def listed(names: Sequence[str]) -> str:
    """Join names the way a sentence lists them, such as ``A, B and C``."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"


@dataclass(frozen=True, slots=True)
class SharedOutput:
    """An output of a Plant that other Plants bind too, and the names of those Plants."""

    entity_id: str
    plants: tuple[str, ...]


def sharing_messages(sharing: Iterable[SharedOutput]) -> tuple[str, ...]:
    """Describe shared outputs for a review step, one sentence per set of other Plants."""
    by_plants: dict[tuple[str, ...], list[str]] = {}
    for shared in sharing:
        by_plants.setdefault(shared.plants, []).append(shared.entity_id)
    messages = []
    for plants, entity_ids in by_plants.items():
        several = len(entity_ids) > 1
        messages.append(
            f"{listed(entity_ids)} {'are' if several else 'is'} already bound by "
            f"{listed(plants)}. Only one Plant that binds {'them' if several else 'it'} can "
            "be out of Dry run at a time: while one is live, the others cannot leave Dry "
            "run, and one stored out of Dry run is held in Dry run until the conflict is gone."
        )
    return tuple(messages)


def shared_outputs(
    hass: HomeAssistant, entry_id: str | None, data: Mapping[str, Any]
) -> tuple[SharedOutput, ...]:
    """Return the outputs of Plant ``data`` that other Plants already bind, for a review step.

    Sharing is allowed, because Dry run Plants may share entities with a live
    Plant, for example to compare a draft configuration. The review lets users
    learn about sharing before it matters. The runtime guard that keeps one live
    Plant per output is authoritative.
    """
    return tuple(
        SharedOutput(entity_id, plants)
        for entity_id, plants in plants_binding_outputs(hass, entry_id, data).items()
    )


def sharing_to_confirm(
    sharing: Iterable[SharedOutput], before: Iterable[SharedOutput] = ()
) -> tuple[SharedOutput, ...]:
    """Return the sharing a save must confirm: what the Plant did not share before the change.

    Sharing the Plant already had was confirmed when it appeared, or existed
    before this edit, so editing a zone does not ask about it again.
    """
    known = set(before)
    return tuple(shared for shared in sharing if shared not in known)


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


def positive(number: selector.NumberSelector) -> vol.All:
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
    return positive(number(step=1, unit=UnitOfTime.SECONDS, minimum=0))


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
    """Re-show a rejected form with the values the user just submitted.

    The frontend leaves out an optional field the user cleared, and Home
    Assistant keeps a field's own suggested value when the submission has none,
    so a cleared field that the form prefilled is shown empty here instead of
    showing the prefilled value again.
    """
    if user_input is None:
        return schema
    return flow.add_suggested_values_to_schema(_without_cleared(schema, user_input), user_input)


def _without_cleared(schema: vol.Schema, user_input: Mapping[str, Any]) -> vol.Schema:
    """Drop the suggested value of every optional field that ``user_input`` leaves out."""
    fields: dict[Any, Any] = {}
    for key, value in schema.schema.items():
        name = str(key)
        if isinstance(value, section):
            nested = user_input.get(name)
            if isinstance(nested, Mapping):
                value = section(_without_cleared(value.schema, nested), value.options)
        elif (
            isinstance(key, vol.Optional)
            and name not in user_input
            and isinstance(key.description, Mapping)
            and "suggested_value" in key.description
        ):
            key = vol.Optional(key.schema, default=key.default, description=None)
        fields[key] = value
    return vol.Schema(fields, required=schema.required, extra=schema.extra)


def subentry_handle(draft: Mapping[str, Any]) -> dict[str, str]:
    """Store only the stable pointer needed for UI and entity ownership."""
    return {"id": str(draft["id"])}


type EntryDataBuilder = Callable[[Mapping[str, Any]], Mapping[str, Any]]
type StoredCallback = Callable[[Mapping[str, Any], Mapping[str, Any]], None]


async def async_persist_entry_data(
    flow: config_entries.ConfigFlow
    | config_entries.OptionsFlow
    | config_entries.ConfigSubentryFlow,
    entry: config_entries.ConfigEntry,
    build: EntryDataBuilder,
    *,
    on_stored: StoredCallback | None = None,
) -> bool:
    """Store edited Plant data once the Plant has safely reached Dry run.

    An active Plant first completes its safe shutdown through the runtime. When
    that cannot finish, nothing is stored and ``False`` is returned.

    The safe shutdown can wait, and another flow may store the Plant meanwhile, so
    ``build`` receives the entry data as it is after the wait and returns the data
    to store. Building, storing, and ``on_stored(previous, stored)`` run with no
    await in between, so no other edit is lost and every handle change made in
    ``on_stored`` meets the data it belongs to. An error ``build`` raises, such as
    a graph edit error against a Plant that changed meanwhile, stores nothing and
    reaches the caller, which reports it on its form.
    """
    if not bool(entry.data.get(CONF_DRY_RUN, True)):
        runtime = getattr(entry, "runtime_data", None)
        if runtime is None or not await runtime.async_set_dry_run(True, hass=flow.hass):
            return False
    previous = entry.data
    stored = dict(build(previous))
    flow.hass.config_entries.async_update_entry(entry, data=stored)
    if on_stored is not None:
        on_stored(previous, stored)
    return True


def topology_select(
    options: list[selector.SelectOptionDict],
    *,
    multiple: bool,
) -> selector.SelectSelector:
    """Build a UUID-backed topology object selector."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=options, multiple=multiple)
    )


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


# Unused equipment is reported but never requested, so it needs no confirmation.
NON_BLOCKING_WARNINGS: Final = frozenset({"unused_equipment"})


def warnings_to_confirm(compiled: CompiledPlant, before: CompiledPlant | None) -> tuple[Any, ...]:
    """Return the warnings a save must confirm: the ones this change introduces.

    A warning names its code and equipment. One the Plant already had before the
    change was confirmed when it appeared, so editing a zone of a manifold does
    not ask about the shared pump again. Without a previous Plant, every warning
    other than unused equipment is new.
    """
    previous = before.warnings if before is not None else ()
    known = {(warning.code, warning.equipment_kind, warning.equipment_id) for warning in previous}
    return tuple(
        warning
        for warning in compiled.warnings
        if warning.code not in NON_BLOCKING_WARNINGS
        and (warning.code, warning.equipment_kind, warning.equipment_id) not in known
    )


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
    _origin_input: dict[str, Any]
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
        user_input: dict[str, Any],
    ) -> config_entries.SubentryFlowResult | None:
        """Review warnings first, or save the draft now; ``None`` means the save failed.

        ``user_input`` is the submitted form that drafted the subentry. It is
        submitted again when a Plant changed meanwhile rejects the draft, so that
        form reports why.
        """
        self._draft = draft
        self._reconfigure = reconfigure
        self._origin_input = user_input
        if warnings:
            self._review_warnings = warnings
            return await self.async_step_review()
        if result := await self._async_persist_draft():
            return result
        errors["base"] = "dry_run_shutdown_in_progress"
        return None

    def _handle_subentry(self) -> config_entries.ConfigSubentry:
        """Return the reconfigured handle, ending the flow if it was deleted meanwhile."""
        try:
            return self._get_reconfigure_subentry()
        except config_entries.UnknownSubEntry as error:
            raise AbortFlow("subentry_removed") from error

    async def _async_persist_draft(self) -> config_entries.SubentryFlowResult | None:
        """Persist the draft graph and return its UI handle, or ``None`` if Dry run is pending.

        The draft applies to the Plant as it is when the save happens.
        """
        entry = self._get_entry()
        draft = self._draft
        reconfigure = self._reconfigure

        def build(data: Mapping[str, Any]) -> dict[str, Any]:
            if reconfigure:
                # A handle deleted meanwhile must not come back.
                self._handle_subentry()
            return self._entry_data_with_draft(data, draft)

        try:
            if not await async_persist_entry_data(self, entry, build):
                return None
        except GRAPH_EDIT_ERRORS:
            step = self.async_step_reconfigure if reconfigure else self.async_step_user
            return await step(self._origin_input)
        if reconfigure:
            return self.async_update_and_abort(
                entry,
                self._handle_subentry(),
                title=draft[CONF_NAME],
                data=subentry_handle(draft),
            )
        return self.async_create_entry(
            title=draft[CONF_NAME],
            data=subentry_handle(draft),
            unique_id=draft["id"],
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
