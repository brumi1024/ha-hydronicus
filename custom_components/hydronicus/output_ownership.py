"""Keep every physical output owned by at most one live Plant.

Two live Plants that command the same valve, pump, or source demand switch fight
over it, and either one's safe shutdown can stop equipment the other needs.
Hydronicus therefore enforces one live Plant per exclusive output.

A Plant is live when it has a loaded runtime that is not in Dry run. The claim
at setup, the refusal to leave Dry run, the hold, the resume, and the repair all
use that one definition:

- Leaving Dry run is refused while another live Plant shares an exclusive output.
- A Plant stored live whose setup reaches its claim while another live Plant owns
  a shared output is held: its runtime is built in Dry run, so it never sends a
  command, while its stored Dry run setting and output authorization stay exactly
  as the user confirmed them. An ``output_conflict`` repair explains the hold.
- Whenever the Plants settle after a change (a setup, a failed setup, an unload,
  a removal, or a Dry run change), held Plants are reviewed. In stored order, a
  held Plant whose conflict is gone, and that shares no output with a Plant
  already chosen to resume, resumes through a reload of its entry, which is the
  normal authorized startup path. Every other held Plant stays held.
- Flows warn when a chosen output is already bound by another Plant.

The first Plant to reach its claim wins. That is deterministic for a given
startup, but a delayed or retrying earlier entry can lose to a later one.
These guards only ever hold a runtime in Dry run, and never modify stored
authorization.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import CONF_DRY_RUN, DOMAIN
from .core.configuration import StoredTopologyError
from .entry_configuration import exclusive_output_entity_ids

OUTPUT_CONFLICT_ISSUE = "output_conflict"
_ISSUE_PREFIX = f"{OUTPUT_CONFLICT_ISSUE}_"
_REVIEW_KEY = f"{DOMAIN}_output_ownership_review"


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


def _runtime(entry: ConfigEntry) -> Any | None:
    return getattr(entry, "runtime_data", None)


def _is_live(entry: ConfigEntry) -> bool:
    """Return whether a Plant has a loaded runtime that is not in Dry run."""
    return (runtime := _runtime(entry)) is not None and not runtime.dry_run


@callback
def live_output_conflict(
    hass: HomeAssistant, entry_id: str, data: Mapping[str, Any]
) -> OutputConflict | None:
    """Return a live Plant that shares an exclusive output with ``data``.

    A Plant counts as live from the moment its setup claims a runtime that is not
    in Dry run until that runtime enters Dry run, its setup fails, or Home
    Assistant discards it after unload. Callers check and then claim or flip Dry
    run without awaiting in between, so two Plants can never both pass this
    check for the same output.
    """
    live = [other for other in _other_entries(hass, entry_id) if _is_live(other)]
    return _first_conflict(live, exclusive_output_entity_ids(data))


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
    """Explain why a Plant is held in Dry run and that it resumes by itself."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry.entry_id),
        is_fixable=False,
        # The hold lives only in the runtime, so the repair is rebuilt at setup
        # rather than restored from storage.
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=OUTPUT_CONFLICT_ISSUE,
        translation_placeholders={"plant": entry.title, **conflict.placeholders},
    )


@dataclass(slots=True)
class _Review:
    """One coalesced review of held Plants, rerun while new requests arrive."""

    task: asyncio.Task[None] | None = None
    requested: bool = False


@callback
def async_schedule_output_review(hass: HomeAssistant) -> None:
    """Review held Plants once every Plant has finished its current lifecycle step.

    Call this after anything that can change which Plants are live. The review
    itself sends no command: a held Plant resumes only through a reload of its
    own entry, which starts through the normal authorized path.
    """
    review: _Review = hass.data.setdefault(_REVIEW_KEY, _Review())
    review.requested = True
    if review.task is None or review.task.done():
        review.task = hass.async_create_task(
            _async_run_review(hass, review), "Review held Hydronicus Plants"
        )


async def _async_run_review(hass: HomeAssistant, review: _Review) -> None:
    while review.requested:
        review.requested = False
        await _async_wait_for_settled_plants(hass)
        _review_held_plants(hass)


async def _async_wait_for_settled_plants(hass: HomeAssistant) -> None:
    """Wait until no Plant is in the middle of a setup, unload, reload, or removal.

    Home Assistant holds an entry's setup lock for the whole step, so waiting on
    it means a reload of the live Plant is judged after it has claimed again,
    not in the gap between its unload and its setup.
    """
    while busy := [
        entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.setup_lock.locked()
    ]:
        for entry in busy:
            async with entry.setup_lock:
                pass


@callback
def _review_held_plants(hass: HomeAssistant) -> None:
    """Resume held Plants whose conflict is gone and keep every repair current."""
    held: dict[str, OutputConflict] = {}
    resuming: list[ConfigEntry] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = _runtime(entry)
        if (
            runtime is None
            or runtime.output_hold is None
            or entry.state is not ConfigEntryState.LOADED
        ):
            continue
        if bool(entry.data.get(CONF_DRY_RUN, True)):
            # The stored setting is Dry run now, so there is nothing to resume.
            runtime.set_output_hold(None)
            continue
        outputs = _stored_exclusive_outputs(entry.data)
        conflict = live_output_conflict(hass, entry.entry_id, entry.data) or _first_conflict(
            resuming, outputs
        )
        if conflict is None and not hass.is_stopping:
            resuming.append(entry)
            continue
        if conflict is not None:
            runtime.set_output_hold(conflict)
            held[entry.entry_id] = conflict

    registry = ir.async_get(hass)
    for domain, issue_id in tuple(registry.issues):
        if (
            domain == DOMAIN
            and issue_id.startswith(_ISSUE_PREFIX)
            and issue_id.removeprefix(_ISSUE_PREFIX) not in held
        ):
            ir.async_delete_issue(hass, DOMAIN, issue_id)
    for entry_id, conflict in held.items():
        if (entry := hass.config_entries.async_get_entry(entry_id)) is not None:
            async_create_output_conflict_issue(hass, entry, conflict)
    for entry in resuming:
        hass.config_entries.async_schedule_reload(entry.entry_id)
