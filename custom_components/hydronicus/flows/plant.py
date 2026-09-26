"""The config flow: guided setup or import of a new Plant, and the entry's reconfigure flow.

Guided setup asks for the Plant and its source, its pumps, how the home is
zoned, one zone at a time with its loops, the plant loops, and each
source-driven pump's min-flow loops once the loops exist, then shows a review
whose warnings never block. Import reads a whole plant file into the same
review.

Reconfigure edits what the entry's data holds (the Plant, its source, pumps,
and plant loops) or replaces the whole Plant from a plant file, and stores it
after a summary of what changes: zone subentries are created, updated, and
removed by slug. A pump that a loop still uses cannot be removed (decision 13).

Both check each form without the min-flow loops that a source-driven pump
does not name yet, such as a new pump's, and ask for them at the end, once
the pump's loops exist: after the plant loops in guided setup, and in Review
and save when reconfiguring.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
)
from homeassistant.core import callback

from ..areas import areas_with_temperature_sensor, listed, zone_name_for_areas
from ..const import (
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    INIT_PATH,
    SUBENTRY_TYPE_ZONE,
)
from ..core.plant_file import (
    PlantFileError,
    describe_path,
    export_plant,
    load_yaml,
    parse_plant,
)
from ..storage import (
    async_store_plant,
    new_entry,
    new_options,
    plant_from_entry,
    stored_document,
)
from . import documents as docs
from . import forms
from .edits import DocumentEdits
from .settings import PlantSettingsFlow
from .zone import ZoneSubentryFlow


class HydronicusConfigFlow(DocumentEdits, ConfigFlow, domain=DOMAIN):
    """Set up a Plant by guided setup or from a plant file, and reconfigure it."""

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    def __init__(self) -> None:
        self._document: docs.Document = docs.new_document()
        self._loaded = False
        # The source's mode select, whose options the source mode form asks for.
        self._mode_entity: str | None = None
        # Whether the zone form offers areas, and in one zone per area the areas
        # still to get a zone each.
        self._with_areas = True
        self._areas: list[str] = []
        self._zone: str | None = None
        # The pump or plant loop being edited, or None for a new one.
        self._editing: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PlantSettingsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_TYPE_ZONE: ZoneSubentryFlow}

    @property
    def _reconfiguring(self) -> bool:
        return self.source == SOURCE_RECONFIGURE

    @property
    def _entry_id(self) -> str | None:
        return self._reconfigure_entry_id if self._reconfiguring else None

    def _check(
        self,
        document: docs.Document,
        prefix: str = "",
        fields: dict[str, str] | None = None,
        asked: str | None = None,
    ) -> forms.Checked:
        """Check a draft without the min-flow loops still to ask for, except pump ``asked``'s."""
        pending = [slug for slug in docs.unresolved_min_flow(document) if slug != asked]
        draft = docs.pending_min_flow(document, pending) if pending else document
        return forms.check(self.hass, draft, prefix=prefix, fields=fields, entry_id=self._entry_id)

    async def _back(self, then: Callable[[], Awaitable[ConfigFlowResult]]) -> ConfigFlowResult:
        """Go back to the reconfigure menu, or on to guided setup's next step ``then``."""
        if self._reconfiguring:
            return await self.async_step_reconfigure()
        return await then()

    def _form(
        self,
        step_id: str,
        schema: vol.Schema,
        checked: forms.Checked | None = None,
        placeholders: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            errors=checked.errors if checked is not None else None,
            description_placeholders={
                **(placeholders or {}),
                **(checked.placeholders if checked is not None else {}),
            },
        )

    # Creating a Plant

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose guided setup or a plant file."""
        return self.async_show_menu(step_id="user", menu_options=["guided", "import_plant"])

    async def async_step_guided(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self.async_step_plant()

    async def async_step_import_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Read a whole Plant from a plant file; a file without an ID gets a new one."""
        text = "" if user_input is None else str(user_input.get("plant_file", ""))
        checked: forms.Checked | None = None
        if user_input is not None:
            checked, document = self._read_file(text, None)
            if checked.plant is not None:
                # The same Plant set up already aborts before any binding is compared.
                await self.async_set_unique_id(checked.plant.id)
                self._abort_if_unique_id_configured()
                checked = forms.check(self.hass, document)
            if checked.plant is not None:
                self._document = document
                return await self.async_step_review()
        return self._form("import_plant", forms.plant_file_schema(text), checked)

    def _read_file(self, text: str, plant_id: str | None) -> tuple[forms.Checked, docs.Document]:
        """Read plant file text, for an import or for the replace of Plant ``plant_id``.

        Only the file itself is checked here; the caller checks its bindings.
        """
        document: Any = None
        try:
            document = load_yaml(text)
            if isinstance(document, dict) and "id" not in document:
                document["id"] = plant_id or docs.new_document()["id"]
            parse_plant(document)
        except PlantFileError as error:
            where = describe_path(document if isinstance(document, dict) else {}, error.path)
            problem = {"where": where, "problem": error.message}
            return forms.Checked(None, {"base": "invalid_plant_file"}, problem), {}
        if plant_id is not None and document["id"] != plant_id:
            return forms.Checked(None, {"base": "different_plant"}, {"id": str(document["id"])}), {}
        return forms.Checked(parse_plant(document)), document

    async def async_step_review(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the Plant and its warnings, then create it; warnings never block."""
        checked = forms.check(self.hass, self._document)
        if (plant := checked.plant) is None:
            # Every step checked the Plant, so only a change elsewhere, such as another
            # Plant binding an output meanwhile, gets here.
            return self._form("review", vol.Schema({}), checked, {"summary": "", "warnings": ""})
        if user_input is not None:
            await self.async_set_unique_id(plant.id)
            self._abort_if_unique_id_configured()
            data, subentries = new_entry(plant)
            return self.async_create_entry(
                title=plant.name, data=data, options=new_options(), subentries=subentries
            )
        return self._form(
            "review",
            vol.Schema({}),
            placeholders={
                "summary": forms.plant_summary(self.hass, plant),
                "warnings": forms.review_warnings(self.hass, plant),
            },
        )

    # The Plant and its source

    async def async_step_plant(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Name the Plant, and choose its source's request switch and mode select."""
        values = docs.plant_values(self._document) if user_input is None else user_input
        checked: forms.Checked | None = None
        if user_input is not None:
            if not str(user_input.get("name") or "").strip():
                checked = forms.Checked(None, {"name": "name_required"})
            elif user_input.get("mode_select") and not user_input.get("request"):
                checked = forms.Checked(None, {"request": "mode_needs_request"})
            else:
                document = docs.with_plant(self._document, user_input)
                checked = self._check(document, fields=forms.PLANT_FIELDS)
                if checked.plant is not None:
                    self._document = document
                    self._mode_entity = user_input.get("mode_select")
                    if self._mode_entity:
                        return await self.async_step_source_mode()
                    return await self._back(self.async_step_pump)
        return self._form("plant", forms.plant_schema(self.hass, values), checked)

    async def async_step_source_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the options of the source's mode select for heating and cooling."""
        entity_id = self._mode_entity
        assert entity_id is not None
        values = docs.mode_values(self._document, entity_id) if user_input is None else user_input
        if not values:
            values = forms.mode_suggestions(self.hass, entity_id)
        checked: forms.Checked | None = None
        if user_input is not None:
            heat, cool = str(user_input.get("heat") or ""), str(user_input.get("cool") or "")
            document = docs.with_mode(self._document, entity_id, heat, cool)
            checked = self._check(document, fields=forms.MODE_FIELDS)
            offered = forms.mode_options(self.hass, entity_id)
            if checked.plant is not None and offered:
                for key, option in (("heat", heat), ("cool", cool)):
                    if option not in offered:
                        checked = forms.Checked(
                            None, {key: "option_not_offered"}, {"options": ", ".join(offered)}
                        )
                        break
            if checked.plant is not None:
                self._document = document
                return await self._back(self.async_step_pump)
        return self._form(
            "source_mode",
            forms.mode_schema(self.hass, entity_id, values),
            checked,
            {"select": forms.entity_label(self.hass, entity_id)},
        )

    # Pumps

    async def async_step_pump(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Add a pump, or edit or remove one when reconfiguring."""
        slug = self._editing
        values = docs.pump_values(self._document, slug) if user_input is None else user_input
        # Only a pump the source drives holds loops open; the form offers them for a
        # pump that exists and has no switch.
        loops = docs.loop_refs(self._document, slug) if slug and not values.get("switch") else {}
        schema = forms.pump_schema(
            self.hass,
            values,
            loops=loops,
            add_another=not self._reconfiguring,
            removable=slug is not None,
        )
        checked: forms.Checked | None = None
        if user_input is not None:
            if user_input.get("remove") and slug is not None:
                if using := docs.loops_using(self._document, slug):
                    checked = forms.Checked(
                        None, {"remove": "pump_in_use"}, {"loops": ", ".join(using)}
                    )
                else:
                    self._document = docs.without_pump(self._document, slug)
                    return await self.async_step_reconfigure()
            elif not str(user_input.get("name") or "").strip():
                checked = forms.Checked(None, {"name": "name_required"})
            else:
                document, slug = docs.with_pump(self._document, slug, user_input)
                # Without the min-flow loops field, their problem shows on the minimum flow.
                fields = {"min_flow_loops": "min_flow", **forms.shown(forms.PUMP_FIELDS, schema)}
                checked = self._check(document, f"pumps.{slug}", fields)
                if checked.plant is not None:
                    self._document = document
                    add_another = user_input.get("add_another")
                    return await self._back(
                        self.async_step_pump if add_another else self.async_step_zoning
                    )
        names = [docs.title(pump, key) for key, pump in docs.pumps(self._document).items()]
        return self._form("pump", schema, checked, {"pumps": ", ".join(names) or "none yet"})

    # Zoning and zones

    async def async_step_zoning(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask how the home is zoned; every answer leads to the zone form."""
        return self.async_show_menu(
            step_id="zoning", menu_options=["zoning_per_area", "zoning_grouped", "zoning_scratch"]
        )

    async def async_step_zoning_per_area(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the areas that each get a zone of their own."""
        values: dict[str, Any] = {"areas": areas_with_temperature_sensor(self.hass)}
        checked: forms.Checked | None = None
        if user_input is not None:
            values = user_input
            if areas := list(dict.fromkeys(user_input.get("areas") or [])):
                self._areas = areas
                return await self.async_step_zone()
            checked = forms.Checked(None, {"areas": "areas_required"})
        return self._form("zoning_per_area", forms.areas_schema(self.hass, values), checked)

    async def async_step_zoning_grouped(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_zone()

    async def async_step_zoning_scratch(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._with_areas = False
        return await self.async_step_zone()

    def _next_area(self) -> str:
        """Name the next area that gets a zone of its own."""
        return zone_name_for_areas(self.hass, self._areas[:1]) or self._areas[0]

    async def async_step_zone(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Add one zone: its name, areas, sensors, and thermostat."""
        values = docs.zone_values(self._document, None)
        progress = ""
        if self._areas:
            # One zone per area fills the form in with the next area.
            values["areas"] = self._areas[:1]
            more = len(self._areas) - 1
            progress = f"This zone covers {self._next_area()}; {more} more to come.\n\n"
        if user_input is not None:
            values = user_input
        schema = forms.zone_schema(self.hass, values, areas=self._with_areas)
        checked = None if user_input is None else self._submit_zone(None, user_input, schema)
        if user_input is not None and checked is None:
            self._areas = self._areas[1:]
            return await self.async_step_zone_loop()
        zones = ", ".join(forms.zone_names(self._document).values()) or "none yet"
        return self._form("zone", schema, checked, {"progress": progress, "zones": zones})

    async def async_step_zone_loop(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a loop to the zone; with no valve and no pump the zone gets no loop."""
        zone = self._zone
        assert zone is not None
        values = docs.loop_values(self._document, zone, None) if user_input is None else user_input
        schema = forms.loop_schema(self.hass, values, forms.pump_labels(self._document))
        checked = None if user_input is None else self._submit_loop(zone, None, user_input, schema)
        if user_input is not None and checked is None:
            return await self.async_step_zone_menu()
        name = forms.zone_names(self._document)[zone]
        return self._form("zone_loop", schema, checked, {"zone": name})

    async def async_step_zone_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add another loop to the zone, add another zone, or go on to the plant loops."""
        zone_slug = self._zone
        assert zone_slug is not None
        zone = docs.zones(self._document)[zone_slug]
        loops = [docs.title(loop, slug) for slug, loop in zone.get("loops", {}).items()]
        options = ["zone_loop", "zone"]
        following = ""
        if self._areas:
            following = f" The next zone covers {self._next_area()}."
        else:
            options.append("zones_done")
        return self.async_show_menu(
            step_id="zone_menu",
            menu_options=options,
            description_placeholders={
                "zone": docs.title(zone, zone_slug),
                "loops": ", ".join(loops) or "none",
                "next": following,
            },
        )

    async def async_step_zones_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_plant_loops()

    # Plant loops and min-flow loops

    async def async_step_plant_loops(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a plant loop, which runs with the source or with zones, or go on."""
        loops = [docs.title(loop, slug) for slug, loop in docs.plant_loops(self._document).items()]
        return self.async_show_menu(
            step_id="plant_loops",
            menu_options=["plant_loop", "loops_done"],
            description_placeholders={"loops": ", ".join(loops) or "none"},
        )

    async def async_step_plant_loop(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a plant loop, or edit or remove one when reconfiguring."""
        slug = self._editing
        values = docs.loop_values(self._document, None, slug) if user_input is None else user_input
        schema = forms.loop_schema(
            self.hass,
            values,
            forms.pump_labels(self._document),
            zones=forms.zone_names(self._document),
            removable=slug is not None,
        )
        checked = None if user_input is None else self._submit_loop(None, slug, user_input, schema)
        if user_input is not None and checked is None:
            return await self._back(self.async_step_plant_loops)
        return self._form("plant_loop", schema, checked)

    async def async_step_loops_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_min_flow()

    async def async_step_min_flow(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the loops held open for each source-driven pump that needs a path."""
        unresolved = docs.unresolved_min_flow(self._document)
        if not unresolved:
            return await (
                self.async_step_save() if self._reconfiguring else self.async_step_review()
            )
        slug = unresolved[0]
        pump = docs.pumps(self._document)[slug]
        loops = docs.loop_refs(self._document, slug)
        if not loops and self._reconfiguring:
            return await self.async_step_min_flow_no_loop()
        values = (
            {"min_flow_loops": docs.own_min_flow_loops(self._document, slug)}
            if user_input is None
            else user_input
        )
        checked: forms.Checked | None = None
        if user_input is not None:
            chosen = list(user_input.get("min_flow_loops") or [])
            guaranteed = bool(user_input.get("guaranteed"))
            if not chosen and not guaranteed:
                checked = forms.Checked(None, {"min_flow_loops": "min_flow_loops_required"})
            else:
                document = docs.with_min_flow(self._document, slug, chosen, guaranteed=guaranteed)
                checked = self._check(
                    document,
                    f"pumps.{slug}",
                    {"min_flow_loops": "min_flow_loops", "min_flow": "min_flow_loops"},
                    asked=slug,
                )
                if checked.plant is not None:
                    self._document = document
                    return await self.async_step_min_flow()
        return self._form(
            "min_flow",
            forms.min_flow_schema(loops, values),
            checked,
            {"pump": docs.title(pump, slug)},
        )

    async def async_step_min_flow_no_loop(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain that a source-driven pump needs a loop before it has min-flow loops."""
        slug = docs.unresolved_min_flow(self._document)[0]
        return self.async_show_menu(
            step_id="min_flow_no_loop",
            menu_options=["min_flow_add_loop", "min_flow_edit_pump", "reconfigure"],
            description_placeholders={"pump": docs.title(docs.pumps(self._document)[slug], slug)},
        )

    async def async_step_min_flow_add_loop(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._editing = None
        return await self.async_step_plant_loop()

    async def async_step_min_flow_edit_pump(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._editing = docs.unresolved_min_flow(self._document)[0]
        return await self.async_step_pump()

    # Reconfigure

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose what to change: the Plant, a pump, a plant loop, or all of it from a file.

        A Repair passes the path of a missing binding as the flow's init data,
        which opens the form that binds it instead.
        """
        entry = self._get_reconfigure_entry()
        if not self._loaded:
            self._loaded, self._document = True, stored_document(entry)
            path = (user_input or {}).get(INIT_PATH)
            if isinstance(path, str) and (opened := await self._open_path(path)) is not None:
                return opened
        checked = self._check(self._document)
        status = "The Plant is valid."
        if pending := docs.unresolved_min_flow(self._document):
            names = listed([docs.title(docs.pumps(self._document)[slug], slug) for slug in pending])
            which = f"Pump {names} needs" if len(pending) == 1 else f"Pumps {names} need"
            status = f"{which} min-flow loops, which Review and save asks for."
        if checked.plant is None:
            where = checked.placeholders.get("where", "")
            problem = checked.placeholders.get("problem") or checked.placeholders.get(
                "entity_id", ""
            )
            status = f"The Plant is not valid, so it does not run. {where}: {problem}"
        self._editing = None
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["plant", "pump_pick", "plant_loop_pick", "replace", "save"],
            description_placeholders={"plant": entry.title, "status": status},
        )

    async def _open_path(self, path: str) -> ConfigFlowResult | None:
        """Open the form of a plant file path: a pump, a plant loop, or the Plant and source."""
        keys = path.split(".")
        if len(keys) > 1 and keys[0] == "pumps" and keys[1] in docs.pumps(self._document):
            self._editing = keys[1]
            return await self.async_step_pump()
        if len(keys) > 1 and keys[0] == "loops" and keys[1] in docs.plant_loops(self._document):
            self._editing = keys[1]
            return await self.async_step_plant_loop()
        if keys[0] == "source":
            return await self.async_step_plant()
        return None

    async def async_step_pump_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a pump to edit or remove, or add one."""
        if user_input is not None:
            self._editing = None if user_input["pump"] == docs.NEW else user_input["pump"]
            return await self.async_step_pump()
        names = {slug: docs.title(pump, slug) for slug, pump in docs.pumps(self._document).items()}
        return self._form("pump_pick", forms.pick_schema("pump_pick", "pump", names))

    async def async_step_plant_loop_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a plant loop to edit or remove, or add one."""
        if user_input is not None:
            self._editing = None if user_input["loop"] == docs.NEW else user_input["loop"]
            return await self.async_step_plant_loop()
        names = {
            slug: docs.title(loop, slug) for slug, loop in docs.plant_loops(self._document).items()
        }
        return self._form("plant_loop_pick", forms.pick_schema("plant_loop_pick", "loop", names))

    async def async_step_replace(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace the whole Plant from a plant file of the same Plant."""
        entry = self._get_reconfigure_entry()
        text = "" if user_input is None else str(user_input.get("plant_file", ""))
        checked: forms.Checked | None = None
        if user_input is not None:
            checked, document = self._read_file(text, str(entry.unique_id))
            if checked.plant is not None:
                checked = forms.check(self.hass, document, entry_id=entry.entry_id)
            if checked.plant is not None:
                self._document = export_plant(checked.plant)
                return await self.async_step_save()
        return self._form("replace", forms.plant_file_schema(text), checked)

    async def async_step_save(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the min-flow loops still missing, show what changes, then store it."""
        if docs.unresolved_min_flow(self._document):
            return await self.async_step_min_flow()
        entry = self._get_reconfigure_entry()
        checked = forms.check(self.hass, self._document, entry_id=entry.entry_id)
        if (plant := checked.plant) is None:
            if user_input is not None:
                return await self.async_step_reconfigure()
            return self._form("save", vol.Schema({}), checked, {"summary": "", "warnings": ""})
        if user_input is not None:
            async_store_plant(self.hass, entry, plant)
            return self.async_abort(reason="reconfigure_successful")
        try:
            old_outputs: set[str] | None = set(plant_from_entry(entry).outputs())
        except PlantFileError:
            old_outputs = None
        return self._form(
            "save",
            vol.Schema({}),
            placeholders={
                "summary": docs.change_summary(stored_document(entry), old_outputs, plant),
                "warnings": forms.review_warnings(self.hass, plant),
            },
        )
