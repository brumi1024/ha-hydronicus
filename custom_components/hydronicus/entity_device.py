"""Device metadata helpers for Hydronicus entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .runtime import HydronicRuntime

# The UI name of each device kind. The kind itself stays in the device identifier,
# and the model is display text only, so renaming a model changes no ID.
_MODEL_NAMES = {"zone": "Room", "circuit": "Loop"}


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
    carries the Plant name, and a room thermostat reads best as just the room.
    """
    if runtime.plant_device_id is None:
        raise RuntimeError("The Hydronicus Plant device must exist before object entities load.")
    return DeviceInfo(
        identifiers={(DOMAIN, f"{runtime.plant_id}:{kind}:{object_id}")},
        name=name,
        manufacturer="Hydronicus",
        model=f"Hydronicus {_MODEL_NAMES.get(kind, kind.title())}",
        via_device_id=runtime.plant_device_id,
    )
