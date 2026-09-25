"""The zone subentry flow: add or reconfigure one zone, with its areas, sensors, and loops.

A zone's loops reference only the Plant's pumps. Each form checks the whole
Plant as it would be stored, with the entry's data and every other zone, by the
same rules as setup (invariant 9), so the zone is saved only as part of a valid
Plant.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigSubentryFlow, SubentryFlowResult

from ..core.plant_file import to_storage
from ..storage import async_reload_if_failed, stored_document
from . import documents as docs
from . import forms


class ZoneSubentryFlow(ConfigSubentryFlow):
    """Add or reconfigure one zone of a Plant."""

    def __init__(self) -> None:
        self._document: docs.Document = {}
        self._zone: str | None = None
        # The loop being edited, or None for a new one.
        self._editing: str | None = None

    def _check(
        self, document: docs.Document, prefix: str = "", fields: dict[str, str] | None = None
    ) -> forms.Checked:
        return forms.check(
            self.hass, document, prefix=prefix, fields=fields, entry_id=self._entry_id
        )

    def _form(
        self, step_id: str, schema: vol.Schema, checked: forms.Checked | None = None
    ) -> SubentryFlowResult:
        placeholders = {"plant": self._get_entry().title}
        if self._zone is not None:
            placeholders["zone"] = forms.zone_names(self._document).get(self._zone, "")
        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            errors=checked.errors if checked is not None else None,
            description_placeholders={
                **placeholders,
                **(checked.placeholders if checked is not None else {}),
            },
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Add a zone."""
        self._document = stored_document(self._get_entry())
        return await self.async_step_zone()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change a zone."""
        self._document = stored_document(self._get_entry())
        self._zone = self._get_reconfigure_subentry().unique_id
        return await self.async_step_zone()

    async def async_step_zone(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """The zone's name, areas, sensors, and thermostat."""
        values = docs.zone_values(self._document, self._zone) if user_input is None else user_input
        schema = forms.zone_schema(self.hass, values)
        checked: forms.Checked | None = None
        if user_input is not None:
            if (name := forms.zone_name(self.hass, user_input)) is None:
                checked = forms.Checked(None, {"name": "zone_name_required"})
            else:
                new = self._zone is None
                document, slug = docs.with_zone(self._document, self._zone, user_input, name)
                checked = self._check(
                    document, f"zones.{slug}", forms.shown(forms.ZONE_FIELDS, schema)
                )
                if checked.plant is not None:
                    self._document, self._zone = document, slug
                    if new:
                        self._editing = None
                        return await self.async_step_loop()
                    return await self.async_step_menu()
        return self._form("zone", schema, checked)

    async def async_step_menu(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Change the zone's settings or loops, or save it."""
        assert self._zone is not None
        zone = docs.zones(self._document)[self._zone]
        loops = [docs.title(loop, slug) for slug, loop in zone.get("loops", {}).items()]
        return self.async_show_menu(
            step_id="menu",
            menu_options=["zone", "loop_pick", "save"],
            description_placeholders={
                "zone": docs.title(zone, self._zone),
                "loops": ", ".join(loops) or "none",
            },
        )

    async def async_step_loop_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Choose a loop to edit or remove, or add one."""
        assert self._zone is not None
        if user_input is not None:
            self._editing = None if user_input["loop"] == docs.NEW else user_input["loop"]
            return await self.async_step_loop()
        loops = docs.zones(self._document)[self._zone].get("loops", {})
        names = {slug: docs.title(loop, slug) for slug, loop in loops.items()}
        return self._form("loop_pick", forms.pick_schema("loop", names, "Add a loop"))

    async def async_step_loop(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Add, edit, or remove one of the zone's loops."""
        zone, slug = self._zone, self._editing
        assert zone is not None
        values = docs.loop_values(self._document, zone, slug) if user_input is None else user_input
        schema = forms.loop_schema(
            self.hass, values, forms.pump_labels(self._document), removable=slug is not None
        )
        checked: forms.Checked | None = None
        if user_input is not None:
            document = self._document
            if slug is not None and user_input.get("remove"):
                document = docs.without_loop(self._document, zone, slug)
                checked = self._check(document)
            elif not user_input.get("pump"):
                if slug is None and not user_input.get("valves"):
                    # A new zone may leave its first loop out.
                    return await self.async_step_menu()
                checked = forms.Checked(None, {"pump": "pump_required"})
            else:
                document, slug = docs.with_loop(self._document, zone, slug, user_input)
                checked = self._check(
                    document, forms.loop_path(zone, slug), forms.shown(forms.LOOP_FIELDS, schema)
                )
            if checked.plant is not None:
                self._document = document
                return await self.async_step_menu()
        return self._form("loop", schema, checked)

    async def async_step_save(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Store the zone as part of the whole Plant."""
        zone = self._zone
        assert zone is not None
        checked = self._check(self._document)
        if (plant := checked.plant) is None:
            return self.async_abort(
                reason="invalid_plant", description_placeholders=checked.placeholders
            )
        data = to_storage(plant)[1][zone]
        title = plant.zone(zone).title
        if self.source != SOURCE_RECONFIGURE:
            return self.async_create_entry(title=title, data=data, unique_id=zone)
        entry = self._get_entry()
        result = self.async_update_and_abort(
            entry, self._get_reconfigure_subentry(), title=title, data=data
        )
        async_reload_if_failed(self.hass, entry)
        return result
