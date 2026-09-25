"""Device metadata helpers for Hydronicus entities."""

from __future__ import annotations

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


def topology_device_info(
    runtime: HydronicRuntime,
    kind: str,
    object_id: str,
    name: str,
) -> DeviceInfo:
    """Return a subentry-safe device for one topology object.

    The device takes the object name alone: the Plant device above it already
    carries the Plant name, and a zone thermostat reads best as just the zone.
    A zone that covers exactly one existing area suggests that area, which Home
    Assistant applies only when it creates the device.
    """
    if runtime.plant_device_id is None:
        raise RuntimeError("The Hydronicus Plant device must exist before object entities load.")
    info = DeviceInfo(
        identifiers={(DOMAIN, f"{runtime.plant_id}:{kind}:{object_id}")},
        name=name,
        manufacturer="Hydronicus",
        model=f"Hydronicus {_MODEL_NAMES.get(kind, kind.title())}",
        via_device_id=runtime.plant_device_id,
    )
    if kind == "zone" and (area := _single_area_name(runtime, object_id)) is not None:
        info["suggested_area"] = area
    return info


def _single_area_name(runtime: HydronicRuntime, zone_id: str) -> str | None:
    """Return the name of the one existing area a zone covers, or None.

    Home Assistant finds the suggested area by name and creates an area that
    does not exist, so a missing area is never suggested. A device has one
    area, so a zone over several areas suggests none.
    """
    zone = runtime.plant.zones.get(zone_id)
    if zone is None or len(zone.areas) != 1:
        return None
    area_id = zone.areas[0].area_id
    resolution = runtime.area_resolution
    if area_id in resolution.missing_area_ids or area_id not in resolution.area_names:
        return None
    return resolution.name(area_id)
