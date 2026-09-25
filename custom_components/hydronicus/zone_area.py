"""Place a zone's climate entity in the one area its zone covers."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .runtime import HydronicRuntime

_CLIMATE = "climate"


def zone_climate_unique_id(plant_id: str, zone_id: str) -> str:
    """Return the unique ID of a zone's climate entity."""
    return f"{plant_id}_{zone_id}_climate"


@callback
def zones_without_climate(hass: HomeAssistant, runtime: HydronicRuntime) -> tuple[str, ...]:
    """Return the zones whose climate entity is not registered yet, before entities load."""
    registry = er.async_get(hass)
    return tuple(
        zone_id
        for zone_id in sorted(runtime.plant.zones)
        if registry.async_get_entity_id(
            _CLIMATE, DOMAIN, zone_climate_unique_id(runtime.plant_id, zone_id)
        )
        is None
    )


@callback
def async_place_new_zone_climates(
    hass: HomeAssistant, runtime: HydronicRuntime, zone_ids: tuple[str, ...]
) -> None:
    """Put each newly created zone climate entity in the one existing area its zone covers.

    Only the climate entity goes in the area, never the zone device: a device in
    an area takes all its entities along, and the area settings would then offer
    the zone's own Combined temperature as the area's temperature sensor.
    Home Assistant puts an area's name in front of the entity IDs it generates,
    so the area is set after the entities have registered, which keeps IDs such
    as ``climate.kitchen`` rather than ``climate.kitchen_kitchen``. Only a
    climate entity this setup created is placed, so an area the user later
    chooses for the entity or its device stays. A zone over several areas
    places nothing, because an entity has one area.
    """
    registry = er.async_get(hass)
    for zone_id in zone_ids:
        if (area_id := _single_area_id(runtime, zone_id)) is None:
            continue
        entity_id = registry.async_get_entity_id(
            _CLIMATE, DOMAIN, zone_climate_unique_id(runtime.plant_id, zone_id)
        )
        if entity_id is None:
            # A zone with an existing climate thermostat has no Hydronicus one.
            continue
        entity = registry.async_get(entity_id)
        if entity is not None and entity.area_id is None:
            registry.async_update_entity(entity_id, area_id=area_id)


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
