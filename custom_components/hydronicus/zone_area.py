"""Place a zone's climate entity in the one area its zone covers."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .core.model import Plant
from .entity import zone_unique_id

_CLIMATE = "climate"


@callback
def zones_without_climate(hass: HomeAssistant, plant: Plant) -> tuple[str, ...]:
    """Return the zones whose climate entity is not registered yet, before entities load."""
    registry = er.async_get(hass)
    return tuple(
        zone.slug
        for zone in plant.zones
        if registry.async_get_entity_id(
            _CLIMATE, DOMAIN, zone_unique_id(plant.id, zone.slug, _CLIMATE)
        )
        is None
    )


@callback
def async_place_new_zone_climates(
    hass: HomeAssistant, plant: Plant, zones: tuple[str, ...]
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
    areas = ar.async_get(hass)
    for slug in zones:
        zone = plant.zone(slug)
        if len(zone.areas) != 1 or areas.async_get_area(zone.areas[0].area) is None:
            continue
        entity_id = registry.async_get_entity_id(
            _CLIMATE, DOMAIN, zone_unique_id(plant.id, slug, _CLIMATE)
        )
        if entity_id is None:
            # A zone with an external thermostat has no Hydronicus one.
            continue
        entity = registry.async_get(entity_id)
        if entity is not None and entity.area_id is None:
            registry.async_update_entity(entity_id, area_id=zone.areas[0].area)
