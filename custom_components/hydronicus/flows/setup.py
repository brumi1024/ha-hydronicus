"""Config flow steps that create a new Plant: guided setup and plant file import.

Guided setup asks for the Plant and its one pump, then one form per zone, and
reviews the result. Import reads a whole plant file. Both build stored data
with the graph edit API, so every new Plant starts in Dry run.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.helpers import selector

from ..areas import area_review_warnings, area_warnings_to_confirm
from ..const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_OVERRUN,
    CONF_PLANT_ID,
    CONF_PUMP_ENTITY,
    CONF_PUMPS,
    CONF_ZONES,
    DEFAULT_PLANT_NAME,
    DEFAULT_PUMP_OVERRUN,
)
from ..core.model import CompiledPlant
from ..core.ownership import PlantOwnership
from ..core.plant_document import PlantDocumentError, import_plant_document
from ..entry_configuration import (
    GRAPH_EDIT_ERRORS,
    canonical_id,
    data_with_zone,
    effective_plant_from_data,
    exclusive_output_entity_ids,
    new_plant_data,
    subentries_for,
    topology_copy,
)
from ..plant_file import first_own_entity, parsed_plant_file
from .common import (
    ConfigFlowBase,
    collapsed_section,
    name_selector,
    other_plant_sharing_warnings,
    own_entity_errors,
    seconds_selector,
    warning_review_schema,
    warning_text,
    warnings_to_confirm,
    with_submitted_values,
)
from .zone_form import graph_errors, zone_draft_from_form, zone_form_errors, zone_form_schema

CONF_ADD_ANOTHER: Final = "add_another"
CONF_CONFIRM: Final = "confirm"
CONF_DOCUMENT: Final = "document"
SECTION_PUMP_OPTIONS: Final = "pump_options"
MENU_OPTIONS: Final = ("guided", "import_plant")
# The name of the one pump guided setup creates; Plant settings can rename it.
GUIDED_PUMP_NAME: Final = "Circulation pump"
# The path shown for a plant file error that no single key causes.
_TOP_LEVEL: Final = "the top level"


def _guided_schema() -> vol.Schema:
    """Return the Plant form of guided setup: its name and its one pump."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=DEFAULT_PLANT_NAME): name_selector(),
            vol.Required(CONF_PUMP_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            vol.Optional(SECTION_PUMP_OPTIONS): collapsed_section(
                {vol.Required(CONF_OVERRUN, default=DEFAULT_PUMP_OVERRUN): seconds_selector()}
            ),
        }
    )


def _zone_schema() -> vol.Schema:
    """Return the zone form: zone basics with the implied pump, and ``add_another``.

    A Plant being set up has one pump and no shared loops, so neither is asked for.
    """
    return zone_form_schema(pumps=(), shared_loops=()).extend(
        {vol.Optional(CONF_ADD_ANOTHER, default=False): selector.BooleanSelector()}
    )


def _import_schema() -> vol.Schema:
    """Return the plant file form.

    The document is optional so that the editor opens empty and a missing or
    unparseable file reaches the flow, which explains it instead of the
    frontend's generic required-field message.
    """
    return vol.Schema({vol.Optional(CONF_DOCUMENT): selector.ObjectSelector()})


def _zone_names(data: Mapping[str, Any]) -> list[str]:
    """Return the zone names of Plant data in the order they were added."""
    return [str(zone.get(CONF_NAME, "")) for zone in topology_copy(data)[CONF_ZONES]]


def _zone_lines(data: Mapping[str, Any]) -> str:
    """List the zones of Plant data in the order they were added."""
    return "\n".join(f"- {name}" for name in _zone_names(data)) or "- None"


def _zones_so_far(data: Mapping[str, Any]) -> str:
    """List the zones guided setup has added, or nothing before the first zone."""
    if not (names := _zone_names(data)):
        return ""
    return "\n\nZones added so far:\n" + "\n".join(f"- {name}" for name in names)


def _logic_lines(compiled: CompiledPlant) -> str:
    return "\n".join(f"- {line}" for line in compiled.logic_summary) or "- None"


class SetupSteps(ConfigFlowBase):
    """Create a new Plant by guided setup or from a plant file."""

    _data: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose how to create the Plant."""
        return self.async_show_menu(step_id="user", menu_options=list(MENU_OPTIONS))

    # ------------------------------------------------------------------
    # Shared review and creation
    # ------------------------------------------------------------------

    async def _async_review(
        self, step_id: str, user_input: Mapping[str, Any] | None, placeholders: Mapping[str, str]
    ) -> config_entries.ConfigFlowResult:
        """Review the drafted Plant, then create it.

        Every warning of a new Plant other than unused equipment, and every output
        another Plant already binds, needs an explicit confirmation.
        """
        compiled = effective_plant_from_data(self._data).compiled
        sharing = other_plant_sharing_warnings(
            self.hass, None, sorted(exclusive_output_entity_ids(self._data))
        )
        areas = area_review_warnings(self.hass, self._data)
        blocking = (
            bool(sharing)
            or bool(warnings_to_confirm(compiled, None))
            or bool(area_warnings_to_confirm(areas))
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            if not blocking or user_input.get(CONF_CONFIRM, False):
                return await self._async_create()
            errors["base"] = "confirm_required"
        return self.async_show_form(
            step_id=step_id,
            data_schema=warning_review_schema() if blocking else vol.Schema({}),
            errors=errors,
            description_placeholders={
                **placeholders,
                "zones": _zone_lines(self._data),
                "logic": _logic_lines(compiled),
                "warnings": warning_text(
                    compiled, (*(warning.message for warning in areas), *sharing)
                )
                or "- None",
            },
        )

    async def _async_create(self) -> config_entries.ConfigFlowResult:
        """Create the entry with a zone handle per zone and a source handle per source."""
        await self.async_set_unique_id(str(self._data[CONF_PLANT_ID]))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=str(self._data[CONF_NAME]),
            data=self._data,
            subentries=cast(list[ConfigSubentryData], subentries_for(self._data)),
        )

    def _is_configured(self, plant_id: str) -> bool:
        """Return whether a Plant with this id already exists."""
        plant_id = canonical_id(plant_id)
        for entry in self._async_current_entries(include_ignore=False):
            ids = {str(entry.data.get(CONF_PLANT_ID, "")), str(entry.unique_id or "")}
            if plant_id in {canonical_id(value) for value in ids}:
                return True
        return False

    # ------------------------------------------------------------------
    # Guided setup
    # ------------------------------------------------------------------

    async def async_step_guided(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Name the Plant and choose its pump."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not str(user_input.get(CONF_NAME, "")).strip():
                errors[CONF_NAME] = "name_required"
            errors.update(own_entity_errors(self.hass, user_input))
            if not errors:
                options = user_input.get(SECTION_PUMP_OPTIONS) or {}
                pump = {
                    "id": str(uuid4()),
                    CONF_NAME: GUIDED_PUMP_NAME,
                    CONF_ENTITY_ID: str(user_input[CONF_PUMP_ENTITY]),
                    CONF_OVERRUN: float(options.get(CONF_OVERRUN, DEFAULT_PUMP_OVERRUN)),
                }
                self._data = new_plant_data(
                    name=str(user_input[CONF_NAME]).strip(),
                    plant_id=str(uuid4()),
                    topology={CONF_PUMPS: [pump]},
                    ownership=PlantOwnership(zone_objects={}),
                )
                return await self.async_step_zone()
        return self.async_show_form(
            step_id="guided",
            data_schema=with_submitted_values(self, _guided_schema(), user_input),
            errors=errors,
        )

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add one zone with its own loop on the Plant's pump, which may also cool it."""
        plant = effective_plant_from_data(self._data)
        schema = _zone_schema()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            form_errors, placeholders = zone_form_errors(self.hass, user_input, plant)
            errors.update(form_errors)
            if not errors:
                draft = zone_draft_from_form(user_input, plant=plant, existing=None)
                try:
                    data = data_with_zone(self._data, draft)
                except GRAPH_EDIT_ERRORS as error:
                    graph, placeholders = graph_errors(error, draft, frozenset(schema.schema))
                    errors.update(graph)
                else:
                    self._data = data
                    if user_input.get(CONF_ADD_ANOTHER, False):
                        return await self.async_step_zone()
                    return await self.async_step_review()
        return self.async_show_form(
            step_id="zone",
            data_schema=with_submitted_values(self, schema, user_input),
            errors=errors,
            description_placeholders={**placeholders, "zones": _zones_so_far(self._data)},
        )

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Review the zones and warnings, then create the Plant."""
        return await self._async_review("review", user_input, {})

    # ------------------------------------------------------------------
    # Plant file import
    # ------------------------------------------------------------------

    async def async_step_import_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Read a whole Plant from a plant file."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            try:
                # A file without an id becomes a new Plant with a fresh id.
                imported = import_plant_document(
                    parsed_plant_file(user_input.get(CONF_DOCUMENT)), plant_id=str(uuid4())
                )
                data = new_plant_data(
                    name=imported.name,
                    plant_id=imported.plant_id,
                    topology=imported.topology,
                    ownership=imported.ownership,
                )
            except PlantDocumentError as error:
                errors["base"] = "invalid_document"
                placeholders = {"path": error.path or _TOP_LEVEL, "error": str(error)}
            except GRAPH_EDIT_ERRORS as error:
                errors["base"] = "invalid_document"
                placeholders = {"path": _TOP_LEVEL, "error": str(error)}
            else:
                if self._is_configured(imported.plant_id):
                    return self.async_abort(reason="already_configured")
                if own := first_own_entity(self.hass, imported):
                    errors["base"] = "document_own_entity"
                    placeholders = {"path": own[0], "entity_id": own[1]}
                else:
                    self._data = data
                    return await self.async_step_import_review()
        return self.async_show_form(
            step_id="import_plant",
            data_schema=with_submitted_values(self, _import_schema(), user_input),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_import_review(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Review the imported Plant and its warnings, then create it."""
        return await self._async_review(
            "import_review", user_input, {"name": str(self._data[CONF_NAME])}
        )
