"""Config flow steps that create a new Plant: guided setup and plant file import.

Guided setup asks for the Plant and its one pump, then how the home is zoned,
then one form per zone, and reviews the result. Import reads a whole plant
file. Both build stored data with the graph edit API, so every new Plant starts
in Dry run.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from ..areas import (
    area_review_warnings,
    area_warnings_to_confirm,
    areas_with_temperature_sensor,
    covered_area_ids,
    resolve_area_sensors,
    zone_name_for_areas,
)
from ..const import (
    CONF_AREAS,
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
    new_plant_data,
    subentries_for,
    topology_copy,
)
from ..plant_file import first_own_entity, parsed_plant_file
from .common import (
    ConfigFlowBase,
    collapsed_section,
    listed,
    name_selector,
    own_entity_errors,
    seconds_selector,
    shared_outputs,
    sharing_messages,
    warning_review_schema,
    warning_text,
    warnings_to_confirm,
    with_submitted_values,
)
from .zone_form import (
    area_ids,
    area_selector,
    graph_errors,
    zone_draft_from_form,
    zone_form_errors,
    zone_form_schema,
)

CONF_ADD_ANOTHER: Final = "add_another"
CONF_CONFIRM: Final = "confirm"
CONF_DOCUMENT: Final = "document"
SECTION_PUMP_OPTIONS: Final = "pump_options"
MENU_OPTIONS: Final = ("guided", "import_plant")
ZONING_WHOLE_HOME: Final = "zoning_whole_home"
ZONING_PER_AREA: Final = "zoning_per_area"
ZONING_GROUPED: Final = "zoning_grouped"
ZONING_OPTIONS: Final = (ZONING_WHOLE_HOME, ZONING_PER_AREA, ZONING_GROUPED)
# The name of the one zone that covers the whole home.
WHOLE_HOME_ZONE_NAME: Final = "Home"
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


def _zone_schema(
    hass: HomeAssistant, defaults: Mapping[str, Any], *, add_another: bool
) -> vol.Schema:
    """Return the zone form: zone basics with the implied pump, and ``add_another``.

    A Plant being set up has one pump and no shared loops, so neither is asked for.
    Only grouping areas into zones asks whether another zone follows.
    """
    schema = zone_form_schema(hass, pumps=(), shared_loops=(), defaults=defaults)
    if not add_another:
        return schema
    return schema.extend(
        {vol.Optional(CONF_ADD_ANOTHER, default=False): selector.BooleanSelector()}
    )


def _areas_schema(hass: HomeAssistant, areas: list[str]) -> vol.Schema:
    """Return the form that chooses the areas that each get their own zone."""
    return vol.Schema(
        {
            vol.Optional(CONF_AREAS, description={"suggested_value": areas or None}): (
                area_selector(hass)
            )
        }
    )


def _import_schema() -> vol.Schema:
    """Return the plant file form.

    The document is optional so that the editor opens empty and a missing or
    unparseable file reaches the flow, which explains it instead of the
    frontend's generic required-field message.
    """
    return vol.Schema({vol.Optional(CONF_DOCUMENT): selector.ObjectSelector()})


def _zone_descriptions(hass: HomeAssistant, data: Mapping[str, Any]) -> list[str]:
    """Describe each zone of Plant data, in the order they were added, with its areas.

    A zone over areas reads like ``Ground floor, covering areas Kitchen and
    Hall``, which stays readable when a zone is named after its one area, and a
    zone without areas is its name alone.
    """
    resolution = resolve_area_sensors(hass, covered_area_ids(data))
    descriptions = []
    for zone in topology_copy(data)[CONF_ZONES]:
        name = str(zone.get(CONF_NAME, ""))
        areas = [resolution.name(area_id) for area_id in area_ids(zone.get(CONF_AREAS))]
        noun = "area" if len(areas) == 1 else "areas"
        descriptions.append(f"{name}, covering {noun} {listed(areas)}" if areas else name)
    return descriptions


def _zone_lines(hass: HomeAssistant, data: Mapping[str, Any]) -> str:
    """List the zones of Plant data and their areas, in the order they were added."""
    return "\n".join(f"- {zone}" for zone in _zone_descriptions(hass, data)) or "- None"


def _zones_so_far(hass: HomeAssistant, data: Mapping[str, Any]) -> str:
    """List the zones guided setup has added, or nothing before the first zone."""
    if not (zones := _zone_descriptions(hass, data)):
        return ""
    return "\n\nZones added so far:\n" + "\n".join(f"- {zone}" for zone in zones)


def _logic_lines(compiled: CompiledPlant) -> str:
    return "\n".join(f"- {line}" for line in compiled.logic_summary) or "- None"


class SetupSteps(ConfigFlowBase):
    """Create a new Plant by guided setup or from a plant file."""

    _data: dict[str, Any]
    _zoning: str
    # One zone per area: the chosen areas, and the index of the zone being added.
    _zone_areas: list[str]
    _zone_index: int

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
        sharing = shared_outputs(self.hass, None, self._data)
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
                "zones": _zone_lines(self.hass, self._data),
                "logic": _logic_lines(compiled),
                "warnings": warning_text(
                    compiled,
                    (
                        *(warning.message for warning in areas),
                        *sharing_messages(sharing),
                    ),
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
                return await self.async_step_zoning()
        return self.async_show_form(
            step_id="guided",
            data_schema=with_submitted_values(self, _guided_schema(), user_input),
            errors=errors,
        )

    async def async_step_zoning(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask how the home is zoned; every answer ends in the zone form."""
        return self.async_show_menu(step_id="zoning", menu_options=list(ZONING_OPTIONS))

    async def async_step_zoning_whole_home(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add one zone over every area that names a temperature sensor."""
        self._zoning = ZONING_WHOLE_HOME
        return await self.async_step_zone()

    async def async_step_zoning_per_area(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose the areas that each get a zone of their own."""
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = list(dict.fromkeys(str(area) for area in user_input.get(CONF_AREAS) or ()))
            if chosen:
                self._zoning = ZONING_PER_AREA
                self._zone_areas = chosen
                self._zone_index = 0
                return await self.async_step_zone()
            errors[CONF_AREAS] = "areas_required"
        return self.async_show_form(
            step_id="zoning_per_area",
            data_schema=_areas_schema(self.hass, areas_with_temperature_sensor(self.hass)),
            errors=errors,
        )

    async def async_step_zoning_grouped(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add zones one by one, each over the areas the user groups into it."""
        self._zoning = ZONING_GROUPED
        return await self.async_step_zone()

    def _zone_defaults(self) -> tuple[dict[str, Any], str]:
        """Return the prefilled values of the next zone form, and its progress text."""
        if self._zoning == ZONING_WHOLE_HOME:
            areas = areas_with_temperature_sensor(self.hass)
            return {CONF_NAME: WHOLE_HOME_ZONE_NAME, CONF_AREAS: areas}, ""
        if self._zoning == ZONING_PER_AREA:
            area_id = self._zone_areas[self._zone_index]
            name = zone_name_for_areas(self.hass, [area_id]) or ""
            progress = f"\n\nZone {self._zone_index + 1} of {len(self._zone_areas)}: {name}."
            return {CONF_NAME: name, CONF_AREAS: [area_id]}, progress
        return {}, ""

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add one zone with its own loop on the Plant's pump, which may also cool it."""
        plant = effective_plant_from_data(self._data)
        defaults, progress = self._zone_defaults()
        schema = _zone_schema(self.hass, defaults, add_another=self._zoning == ZONING_GROUPED)
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            form_errors, placeholders = zone_form_errors(self.hass, user_input, plant)
            errors.update(form_errors)
            if not errors:
                draft = zone_draft_from_form(self.hass, user_input, plant=plant, existing=None)
                try:
                    data = data_with_zone(self._data, draft)
                except GRAPH_EDIT_ERRORS as error:
                    graph, placeholders = graph_errors(error, draft, frozenset(schema.schema))
                    errors.update(graph)
                else:
                    self._data = data
                    return await self._async_next_zone(user_input)
        return self.async_show_form(
            step_id="zone",
            data_schema=with_submitted_values(self, schema, user_input),
            errors=errors,
            description_placeholders={
                **placeholders,
                "progress": progress,
                "zones": _zones_so_far(self.hass, self._data),
            },
        )

    async def _async_next_zone(
        self, user_input: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Show the next zone form of the chosen zoning, or the review after the last."""
        if self._zoning == ZONING_GROUPED and user_input.get(CONF_ADD_ANOTHER, False):
            return await self.async_step_zone()
        if self._zoning == ZONING_PER_AREA and self._zone_index + 1 < len(self._zone_areas):
            self._zone_index += 1
            return await self.async_step_zone()
        return await self.async_step_review()

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
