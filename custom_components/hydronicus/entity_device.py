"""Device metadata helpers for Hydronicus entities."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .runtime import HydronicRuntime


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
    """Return a subentry-safe device for one topology object."""
    if runtime.plant_device_id is None:
        raise RuntimeError("The Hydronicus Plant device must exist before object entities load.")
    return DeviceInfo(
        identifiers={(DOMAIN, f"{runtime.plant_id}:{kind}:{object_id}")},
        name=f"{runtime.name} {name}",
        manufacturer="Hydronicus",
        model=f"Hydronicus {kind.title()}",
        via_device_id=runtime.plant_device_id,
    )
