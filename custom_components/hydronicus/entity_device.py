"""Device metadata helpers for Hydronicus entities."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .runtime import HydronicRuntime

# The UI name of each device kind. The kind itself stays in the device identifier,
# and the model is display text only, so renaming a model changes no ID.
_MODEL_NAMES = {"zone": "Zone", "circuit": "Loop"}


def plant_device_info(runtime: HydronicRuntime) -> DeviceInfo:
    """Return the parent Plant device for Plant-level entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, runtime.plant_id)},
        name=runtime.name,
        manufacturer="Hydronicus",
        model="Hydronicus Plant",
    )


def _identifier(runtime: HydronicRuntime, kind: str, object_id: str) -> tuple[str, str]:
    """Return the device identifier of one topology object."""
    return (DOMAIN, f"{runtime.plant_id}:{kind}:{object_id}")


def topology_device_info(
    runtime: HydronicRuntime,
    kind: str,
    object_id: str,
    name: str,
) -> DeviceInfo:
    """Return a subentry-safe device for one topology object.

    The device takes the object name alone: the Plant device above it already
    carries the Plant name, and a zone thermostat reads best as just the zone.
    """
    if runtime.plant_device_id is None:
        raise RuntimeError("The Hydronicus Plant device must exist before object entities load.")
    return DeviceInfo(
        identifiers={_identifier(runtime, kind, object_id)},
        name=name,
        manufacturer="Hydronicus",
        model=f"Hydronicus {_MODEL_NAMES.get(kind, kind.title())}",
        via_device_id=runtime.plant_device_id,
    )


@callback
def zones_without_device(
    hass: HomeAssistant, entry_id: str, runtime: HydronicRuntime
) -> tuple[str, ...]:
    """Return the zones whose device does not exist yet, before entities create it."""
    registry = dr.async_get(hass)
    return tuple(
        zone_id
        for zone_id in sorted(runtime.plant.zones)
        if registry.async_get_device_by_identifier(_identifier(runtime, "zone", zone_id), entry_id)
        is None
    )


@callback
def async_place_new_zone_devices(
    hass: HomeAssistant, entry_id: str, runtime: HydronicRuntime, zone_ids: tuple[str, ...]
) -> None:
    """Put each newly created zone device in the one existing area its zone covers.

    Home Assistant puts the device's area name in front of the entity IDs it
    generates, so a suggested area would give a zone named after its area
    entity IDs such as ``climate.kitchen_kitchen``. The area is therefore set
    after the entities have registered, and only for a device this setup
    created, so a device the user moved elsewhere stays there. A device has one
    area, so a zone over several areas stays unassigned.
    """
    registry = dr.async_get(hass)
    for zone_id in zone_ids:
        if (area_id := _single_area_id(runtime, zone_id)) is None:
            continue
        device = registry.async_get_device_by_identifier(
            _identifier(runtime, "zone", zone_id), entry_id
        )
        if device is not None and device.area_id is None:
            registry.async_update_device(device.id, area_id=area_id)


def _single_area_id(runtime: HydronicRuntime, zone_id: str) -> str | None:
    """Return the one existing area a zone covers, or None."""
    zone = runtime.plant.zones.get(zone_id)
    if zone is None or len(zone.areas) != 1:
        return None
    area_id = zone.areas[0].area_id
    resolution = runtime.area_resolution
    if area_id in resolution.missing_area_ids or area_id not in resolution.area_names:
        return None
    return area_id
