"""Keep every physical output owned by at most one live Plant.

Two live Plants that command the same valve, pump, or source demand switch fight
over it, and either one's safe shutdown can stop equipment the other needs.
Hydronicus therefore enforces one live Plant per exclusive output:

- Leaving Dry run is refused while another live Plant shares an exclusive output.
- A live Plant that sets up while another live Plant owns a shared output yields
  to Dry run before its runtime exists, so it never sends a command, and raises
  an ``output_conflict`` repair until the conflict is gone.
- Flows warn when a chosen output is already bound by another Plant.

The guards only ever move a Plant toward Dry run.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import CONF_DRY_RUN, DOMAIN
from .core.configuration import StoredTopologyError
from .entry_configuration import exclusive_output_entity_ids

OUTPUT_CONFLICT_ISSUE = "output_conflict"
_ISSUE_PREFIX = f"{OUTPUT_CONFLICT_ISSUE}_"


@dataclass(frozen=True, slots=True)
class OutputConflict:
    """Another Plant that binds some of the same exclusive outputs."""

    other_entry_id: str
    other_plant: str
    entity_ids: tuple[str, ...]

    @property
    def placeholders(self) -> dict[str, str]:
        """Return translation placeholders naming the other Plant and the shared entities."""
        return {"other_plant": self.other_plant, "entities": ", ".join(self.entity_ids)}


def _stored_exclusive_outputs(data: Mapping[str, Any]) -> frozenset[str]:
    """Return a stored Plant's exclusive outputs, treating an undecodable graph as none.

    A Plant whose graph cannot be decoded never sets up, so it commands nothing.
    """
    try:
        return exclusive_output_entity_ids(data)
    except StoredTopologyError:
        return frozenset()


def _first_conflict(others: list[ConfigEntry], outputs: frozenset[str]) -> OutputConflict | None:
    for other in others:
        if shared := outputs & _stored_exclusive_outputs(other.data):
            return OutputConflict(other.entry_id, other.title, tuple(sorted(shared)))
    return None


def _other_entries(hass: HomeAssistant, entry_id: str | None) -> list[ConfigEntry]:
    return [
        entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.entry_id != entry_id
    ]


@callback
def live_output_conflict(
    hass: HomeAssistant, entry_id: str, data: Mapping[str, Any]
) -> OutputConflict | None:
    """Return a running, live Plant that shares an exclusive output with ``data``.

    A Plant counts as running from the moment its setup claims its runtime until
    Home Assistant discards that runtime after unload. Callers check and then
    claim or flip Dry run without awaiting in between, so two Plants can never
    both pass this check for the same output.
    """
    running_live = [
        other
        for other in _other_entries(hass, entry_id)
        if (runtime := getattr(other, "runtime_data", None)) is not None and not runtime.dry_run
    ]
    return _first_conflict(running_live, exclusive_output_entity_ids(data))


@callback
def bound_by_other_plant(
    hass: HomeAssistant, entry_id: str | None, entity_id: Any
) -> OutputConflict | None:
    """Return another Plant, live or in Dry run, that already binds ``entity_id``."""
    if not isinstance(entity_id, str) or not entity_id:
        return None
    return _first_conflict(_other_entries(hass, entry_id), frozenset({entity_id}))


def _issue_id(entry_id: str) -> str:
    return f"{_ISSUE_PREFIX}{entry_id}"


@callback
def async_create_output_conflict_issue(
    hass: HomeAssistant, entry: ConfigEntry, conflict: OutputConflict
) -> None:
    """Explain why a Plant was moved to Dry run and how to resolve it."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry.entry_id),
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key=OUTPUT_CONFLICT_ISSUE,
        translation_placeholders={"plant": entry.title, **conflict.placeholders},
    )


@callback
def async_sync_output_conflict_issues(
    hass: HomeAssistant, *, removed_entry_id: str | None = None
) -> None:
    """Remove every output conflict repair whose conflict is gone.

    The other Plant counts by its stored Dry run setting, not by whether it has
    finished setting up, so the result does not depend on startup order.
    """
    registry = ir.async_get(hass)
    for domain, issue_id in tuple(registry.issues):
        if domain != DOMAIN or not issue_id.startswith(_ISSUE_PREFIX):
            continue
        entry_id = issue_id.removeprefix(_ISSUE_PREFIX)
        entry = hass.config_entries.async_get_entry(entry_id)
        conflict = None
        if (
            entry is not None
            and entry_id != removed_entry_id
            and bool(entry.data.get(CONF_DRY_RUN, True))
        ):
            stored_live = [
                other
                for other in _other_entries(hass, entry_id)
                if other.entry_id != removed_entry_id
                and other.disabled_by is None
                and not bool(other.data.get(CONF_DRY_RUN, True))
            ]
            conflict = _first_conflict(stored_live, _stored_exclusive_outputs(entry.data))
        if conflict is None:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
