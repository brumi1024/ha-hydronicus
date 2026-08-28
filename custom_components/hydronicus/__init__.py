"""Hydronicus integration setup."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_DRY_RUN,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    PLATFORMS,
)
from .core.configuration import StoredTopologyError
from .core.topology import TopologyValidationError
from .entry_configuration import (
    invalidate_output_authorization,
    migration_plan,
    output_authorization_is_valid,
    reconcile_removed_subentries,
    runtime_configuration_fingerprint,
)
from .frontend import async_register_frontend
from .runtime import HydronicRuntime
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
    """Remove runtime data after unload or failed setup."""
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
    """Register the read-only Plant presentation WebSocket commands."""
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

    async def _reload() -> None:
        await asyncio.sleep(0)
        reconciled = reconcile_removed_subentries(entry)
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
            reconciled = reconcile_removed_subentries(entry)
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
    """Migrate stored Hydronicus config entries before runtime setup."""
    if entry.version > CONFIG_ENTRY_VERSION:
        return False
    if entry.version == CONFIG_ENTRY_VERSION:
        if entry.minor_version > CONFIG_ENTRY_MINOR_VERSION:
            return False
        if entry.minor_version == CONFIG_ENTRY_MINOR_VERSION:
            return True

    if entry.version == 1 and entry.minor_version <= 1:
        try:
            plan = migration_plan(entry)
            # Make every migrated object durable in the parent before minimizing
            # any legacy subentry. A restart can safely repeat either half.
            hass.config_entries.async_update_entry(entry, data=plan.data)
            for update in plan.subentries:
                hass.config_entries.async_update_subentry(
                    entry,
                    update.subentry,
                    data={"id": update.object_id},
                    unique_id=update.object_id,
                )
            hass.config_entries.async_update_entry(
                entry,
                version=CONFIG_ENTRY_VERSION,
                minor_version=CONFIG_ENTRY_MINOR_VERSION,
            )
            return True
        except StoredTopologyError, TopologyValidationError:
            _LOGGER.exception("Could not migrate Hydronicus Plant %s", entry.entry_id)
            return False

    return False


async def async_setup_entry(hass: HomeAssistant, entry: HydronicConfigEntry) -> bool:
    """Set up a hydronic plant from a config entry."""
    if reconciled := reconcile_removed_subentries(entry):
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
    runtime = HydronicRuntime.from_entry(entry)
    entry.runtime_data = runtime
    remove_update_listener = entry.add_update_listener(_async_reload_entry)
    registered = False
    try:
        await runtime.async_start(hass, defer_initial_refresh=True)
        _ensure_plant_device(hass, entry, runtime)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        await runtime.async_finish_start(hass)
        register_runtime(hass, runtime)
        registered = True
    except Exception:
        remove_update_listener()
        if registered:
            unregister_runtime(hass, runtime.plant_id)
        await runtime.async_stop()
        _clear_runtime_data(entry)
        raise
    entry.async_on_unload(remove_update_listener)
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
        _clear_runtime_data(entry)
    return bool(unloaded)


async def async_remove_entry(hass: HomeAssistant, entry: HydronicConfigEntry) -> None:
    """Remove stored ownership after the command-free unload boundary."""
    # Home Assistant invokes this only after attempting async_unload_entry.
    # Device and entity registry cleanup belongs to Home Assistant itself.
    return None
