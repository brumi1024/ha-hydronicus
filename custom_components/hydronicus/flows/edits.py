"""The zone and loop forms' rules, which the config flow and the zone subentry flow share.

A submitted form's change is kept in the flow's document only once the whole
Plant it makes is valid; otherwise the problem goes back to the form.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant

from ..core.model import RunKind
from . import documents as docs
from . import forms


class DocumentEdits:
    """Keep a submitted zone or loop form in a flow's plant file document."""

    hass: HomeAssistant
    _document: docs.Document
    # The zone being added or edited.
    _zone: str | None

    def _check(
        self, document: docs.Document, prefix: str = "", fields: dict[str, str] | None = None
    ) -> forms.Checked:
        raise NotImplementedError

    def _submit_zone(
        self, slug: str | None, values: Mapping[str, Any], schema: vol.Schema
    ) -> forms.Checked | None:
        """Keep a new or edited zone as the flow's zone, or return the problem to show.

        A zone needs a name, typed or given by its areas.
        """
        if (name := forms.zone_name(self.hass, values)) is None:
            return forms.Checked(None, {"name": "zone_name_required"})
        document, slug = docs.with_zone(self._document, slug, values, name)
        checked = self._check(document, f"zones.{slug}", forms.shown(forms.ZONE_FIELDS, schema))
        if checked.plant is None:
            return checked
        self._document, self._zone = document, slug
        return None

    def _submit_loop(
        self, zone: str | None, slug: str | None, values: Mapping[str, Any], schema: vol.Schema
    ) -> forms.Checked | None:
        """Keep a zone's loop or a plant loop, added, edited, or removed, or return the problem.

        A new zone loop left without valves and pump adds nothing, for a zone that
        only a plant loop serves.
        """
        if slug is not None and values.get("remove"):
            document = docs.without_loop(self._document, zone, slug)
            checked = self._check(document)
        elif not values.get("pump"):
            if zone is not None and slug is None and not values.get("valves"):
                return None
            return forms.Checked(None, {"pump": "pump_required"})
        elif values.get("runs") == RunKind.WITH_ZONES.value and not values.get("with_zones"):
            return forms.Checked(None, {"with_zones": "zones_required"})
        else:
            document, slug = docs.with_loop(self._document, zone, slug, values)
            checked = self._check(
                document, forms.loop_path(zone, slug), forms.shown(forms.LOOP_FIELDS, schema)
            )
        if checked.plant is None:
            return checked
        self._document = document
        return None
