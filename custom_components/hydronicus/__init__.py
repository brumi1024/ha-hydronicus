"""Hydronicus integration setup."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_DRY_RUN,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    PLATFORMS,
)
from .entry_configuration import (
    GRAPH_EDIT_ERRORS,
    invalidate_output_authorization,
    output_authorization_is_valid,
    reconcile_removed_subentries,
    runtime_configuration_fingerprint,
)
from .frontend import async_register_frontend
from .migration import async_migrate_1_1_to_2_0, async_migrate_2_0_to_3_0
from .output_ownership import (
    async_create_output_conflict_issue,
    async_schedule_output_review,
    live_output_conflict,
)
from .runtime import HydronicRuntime
from .services import async_setup_services
from .websocket import (
    async_setup as async_setup_websocket,
)
from .websocket import (
    register_runtime,
    unregister_runtime,
)

type HydronicConfigEntry = ConfigEntry[HydronicRuntime]

_LOGGER = logging.getLogger(__name__)
_RELOAD_TASKS: dict[tuple[int, str], asyncio.Task[None]] = {}


def _clear_runtime_data(entry: ConfigEntry) -> None:
    """Remove runtime data after a failed setup."""
    with suppress(AttributeError):
        del entry.runtime_data


def _ensure_plant_device(hass: HomeAssistant, entry: ConfigEntry, runtime: HydronicRuntime) -> None:
    """Create the parent Plant device before topology entities reference it."""
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, runtime.plant_id)},
        name=runtime.name,
        manufacturer="Hydronicus",
        model="Hydronicus Plant",
    )
    runtime.plant_device_id = device.id


async def async_setup(hass: HomeAssistant, config: dict[str, object]) -> bool:
    """Register the actions and the read-only Plant presentation WebSocket commands."""
    async_setup_services(hass)
    await async_register_frontend(hass)
    return bool(await async_setup_websocket(hass, config))


async def _async_reload_entry(hass: HomeAssistant, entry: HydronicConfigEntry) -> None:
    """Coalesce parent and handle updates into one complete Plant reload."""
    runtime = getattr(entry, "runtime_data", None)
    if (
        runtime is not None
        and runtime.configuration_fingerprint == runtime_configuration_fingerprint(entry)
    ):
        return
    key = (id(hass), entry.entry_id)
    if existing := _RELOAD_TASKS.get(key):
        await existing
        return

    def _reconciled() -> dict[str, object] | None:
        try:
            return reconcile_removed_subentries(entry)
        except GRAPH_EDIT_ERRORS:
            # Handles that do not match the stored graph cannot be reconciled here;
            # the reload's setup reports the invalid stored graph instead.
            return None

    async def _reload() -> None:
        await asyncio.sleep(0)
        reconciled = _reconciled()
        if reconciled is not None and not bool(entry.data.get(CONF_DRY_RUN, True)):
            active_runtime = getattr(entry, "runtime_data", None)
            if (
                active_runtime is None
                or not await active_runtime.async_prepare_configuration_change(hass)
            ):
                _LOGGER.error(
                    "Plant %s could not reach Dry run after a config subentry was removed; "
                    "the parent graph and active runtime were retained",
                    entry.entry_id,
                )
                return
            reconciled = _reconciled()
        if reconciled is not None:
            hass.config_entries.async_update_entry(entry, data=reconciled)
            await asyncio.sleep(0)
        await hass.config_entries.async_reload(entry.entry_id)

    task = hass.async_create_task(_reload(), f"Reload Hydronicus Plant {entry.entry_id}")
    _RELOAD_TASKS[key] = task
    try:
        await task
    finally:
        if _RELOAD_TASKS.get(key) is task:
            _RELOAD_TASKS.pop(key, None)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate stored Hydronicus config entries before runtime setup.

    Version 1.1 chains through 2.0 to 3.0 in one call, and every step is safe to
    repeat, so a restart during migration resumes to the same result.
    """
    if entry.version > CONFIG_ENTRY_VERSION or (
        entry.version == CONFIG_ENTRY_VERSION and entry.minor_version > CONFIG_ENTRY_MINOR_VERSION
    ):
        return False
    try:
        if entry.version == 1 and entry.minor_version <= 1:
            async_migrate_1_1_to_2_0(hass, entry)
        if entry.version == 2 and entry.minor_version == 0:
            async_migrate_2_0_to_3_0(hass, entry)
    except GRAPH_EDIT_ERRORS:
        _LOGGER.exception("Could not migrate Hydronicus Plant %s", entry.entry_id)
        return False
    return entry.version == CONFIG_ENTRY_VERSION and (
        entry.minor_version == CONFIG_ENTRY_MINOR_VERSION
    )


def _stored_graph_error(entry: ConfigEntry, error: Exception) -> ConfigEntryError:
    """Describe a stored Plant graph that cannot be decoded or compiled safely."""
    return ConfigEntryError(
        translation_domain=DOMAIN,
        translation_key="invalid_stored_graph",
        translation_placeholders={"plant": entry.title, "error": str(error)},
    )


async def async_setup_entry(hass: HomeAssistant, entry: HydronicConfigEntry) -> bool:
    """Set up a hydronic plant from a config entry."""
    try:
        reconciled = reconcile_removed_subentries(entry)
    except GRAPH_EDIT_ERRORS as error:
        raise _stored_graph_error(entry, error) from error
    if reconciled:
        hass.config_entries.async_update_entry(entry, data=reconciled)
    if not bool(entry.data.get(CONF_DRY_RUN, True)) and not output_authorization_is_valid(
        entry.data
    ):
        _LOGGER.warning(
            "Hydronicus Plant %s had no valid output authorization and returned to Dry run",
            entry.entry_id,
        )
        hass.config_entries.async_update_entry(
            entry,
            data=invalidate_output_authorization(entry.data),
        )
    # Check and claim with no await in between: of two live Plants sharing an
    # output, the one whose setup reaches this point second is held. Its runtime
    # is built in Dry run, so it never sends a command, while its stored Dry run
    # setting and output authorization stay as the user confirmed them.
    hold = None
    if not bool(entry.data.get(CONF_DRY_RUN, True)) and (
        hold := live_output_conflict(hass, entry.entry_id, entry.data)
    ):
        _LOGGER.warning(
            "Hydronicus Plant %s shares outputs %s with live Plant %s and is held in Dry run "
            "until that conflict is gone; its stored setting is kept",
            entry.entry_id,
            ", ".join(hold.entity_ids),
            hold.other_entry_id,
        )
    try:
        runtime = HydronicRuntime.from_entry(entry, output_hold=hold)
    except GRAPH_EDIT_ERRORS as error:
        raise _stored_graph_error(entry, error) from error
    entry.runtime_data = runtime
    if hold is not None:
        async_create_output_conflict_issue(hass, entry, hold)
    remove_update_listener = entry.add_update_listener(_async_reload_entry)
    registered = False
    forwarded = False
    try:
        await runtime.async_start(hass, defer_initial_refresh=True)
        _ensure_plant_device(hass, entry, runtime)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        forwarded = True
        await runtime.async_finish_start(hass)
        register_runtime(hass, runtime)
        registered = True
    except Exception:
        remove_update_listener()
        if registered:
            unregister_runtime(hass, runtime.plant_id)
        if forwarded:
            # Home Assistant does not unload platforms of a failed setup, and a
            # retry could not forward them again while they are still set up.
            await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        await runtime.async_stop()
        _clear_runtime_data(entry)
        # This Plant may have claimed outputs that held Plants now need.
        async_schedule_output_review(hass)
        raise
    entry.async_on_unload(remove_update_listener)
    async_schedule_output_review(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HydronicConfigEntry) -> bool:
    """Unload a hydronic plant without issuing equipment commands."""
    runtime = entry.runtime_data
    if active_ids := runtime.active_equipment_ids():
        _LOGGER.warning(
            "Unloading active Plant %s with equipment %s without issuing equipment "
            "commands; use Safe shutdown or enable Dry run before unloading, and keep "
            "independent safeguards in place",
            runtime.plant_id,
            ", ".join(active_ids),
        )
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        unregister_runtime(hass, runtime.plant_id)
        await runtime.async_stop()
        # The review waits until Home Assistant has discarded this runtime, and
        # for a reload until this Plant has set up and claimed again.
        async_schedule_output_review(hass)
    return bool(unloaded)


async def async_remove_entry(hass: HomeAssistant, entry: HydronicConfigEntry) -> None:
    """Remove stored ownership after the command-free unload boundary."""
    # Home Assistant invokes this only after attempting async_unload_entry.
    # Device and entity registry cleanup belongs to Home Assistant itself.
    async_schedule_output_review(hass)
