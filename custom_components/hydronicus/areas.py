"""The Home Assistant areas that zones cover, and the sensors those areas name.

Every area and floor registry read goes through this module. A zone follows the
temperature and humidity sensors that each of its areas currently names, so the
runtime resolves them on every evaluation (decision 12), and the setup reviews,
diagnostics, and Repairs resolve them here too.

Home Assistant does not update an area's sensors when one of those entities is
renamed in the entity registry (checked against 2026.9), so a renamed sensor
leaves the area naming an entity that no longer exists. The runtime then reports
it as a missing binding, and the area settings fix it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.util import slugify
from homeassistant.util.hass_dict import HassKey

from .bindings import is_hydronicus_owned
from .core.model import DigitalThermostat, Plant
from .core.step import AreaSensors

# The name each covered area last had, so a removed area is still named in a
# message. Home Assistant forgets a removed area, and this memory lasts until
# Home Assistant stops.
_LAST_AREA_NAMES: HassKey[dict[str, str]] = HassKey("hydronicus_last_area_names")


def listed(names: Sequence[str]) -> str:
    """Join names the way a sentence lists them, such as ``A, B and C``."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"


@dataclass(frozen=True, slots=True)
class AreaResolution:
    """What the covered areas name in Home Assistant right now.

    ``area_sensors`` holds every existing area with the sensors a zone may
    follow. A sensor that Hydronicus provides would feed the Plant back into
    itself, so it is dropped there and listed in ``self_provided`` by area.
    """

    area_sensors: Mapping[str, AreaSensors] = field(default_factory=dict)
    missing_area_ids: tuple[str, ...] = ()
    self_provided: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    # Names are for messages only. A missing area keeps the name it last had
    # while Home Assistant ran.
    area_names: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze the mappings at the adapter boundary."""
        for name in ("area_sensors", "self_provided", "area_names"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    @property
    def self_provided_entity_ids(self) -> tuple[str, ...]:
        """Return every Hydronicus entity an area names, which the zone ignores."""
        return tuple(
            sorted({entity_id for ids in self.self_provided.values() for entity_id in ids})
        )

    def followed_entity_ids(self) -> frozenset[str]:
        """Return every sensor a covered area names that a zone follows."""
        return frozenset(
            entity_id
            for sensors in self.area_sensors.values()
            for entity_id in (sensors.temperature, sensors.humidity)
            if entity_id
        )

    def named_entity_ids(self) -> frozenset[str]:
        """Return every entity a covered area names, followed or ignored."""
        return self.followed_entity_ids() | set(self.self_provided_entity_ids)

    def name(self, area_id: str) -> str:
        """Return an area's name, its last name when it is missing, or a name from its ID."""
        return self.area_names.get(area_id) or _name_from_id(area_id)

    def recreate_name(self, area_id: str) -> str:
        """Return a name that gives a new area this ID again.

        Home Assistant makes a new area's ID from its name, so a missing area
        comes back by its last name when that still makes its ID, and otherwise
        by a name spelled from the ID, such as ``Kids room`` for ``kids_room``.
        """
        for name in (self.area_names.get(area_id), _name_from_id(area_id)):
            if name and slugify(name) == area_id:
                return name
        return area_id


def _name_from_id(area_id: str) -> str:
    """Spell an area ID as a name, such as ``Kids room`` for ``kids_room``."""
    return area_id.replace("_", " ").capitalize()


def covered_area_ids(plant: Plant) -> tuple[str, ...]:
    """Return every area a zone of the Plant covers, each once, in zone order."""
    return tuple(dict.fromkeys(area.area for zone in plant.zones for area in zone.areas))


def resolve_area_sensors(hass: HomeAssistant, area_ids: Iterable[str]) -> AreaResolution:
    """Resolve the sensors that Home Assistant currently names for each area."""
    registry = ar.async_get(hass)
    last_names = hass.data.setdefault(_LAST_AREA_NAMES, {})
    area_sensors: dict[str, AreaSensors] = {}
    missing: list[str] = []
    self_provided: dict[str, tuple[str, ...]] = {}
    names: dict[str, str] = {}
    for area_id in dict.fromkeys(area_ids):
        area = registry.async_get_area(area_id)
        if area is None:
            missing.append(area_id)
            if area_id in last_names:
                names[area_id] = last_names[area_id]
            continue
        names[area_id] = last_names[area_id] = area.name
        named = (area.temperature_entity_id, area.humidity_entity_id)
        own = tuple(
            entity_id for entity_id in named if entity_id and is_hydronicus_owned(hass, entity_id)
        )
        if own:
            self_provided[area_id] = own
        temperature, humidity = (
            entity_id if entity_id and entity_id not in own else None for entity_id in named
        )
        area_sensors[area_id] = AreaSensors(temperature, humidity)
    return AreaResolution(
        area_sensors=area_sensors,
        missing_area_ids=tuple(missing),
        self_provided=self_provided,
        area_names=names,
    )


def names_temperature_sensor(hass: HomeAssistant, area_ids: Iterable[str]) -> bool:
    """Return whether any of the areas names a temperature sensor a zone can follow."""
    resolution = resolve_area_sensors(hass, area_ids)
    return any(sensors.temperature for sensors in resolution.area_sensors.values())


def area_names(hass: HomeAssistant) -> list[tuple[str, str]]:
    """Return the ID and name of every Home Assistant area, by name."""
    areas = sorted(ar.async_get(hass).async_list_areas(), key=lambda area: area.name.casefold())
    return [(area.id, area.name) for area in areas]


def areas_with_temperature_sensor(hass: HomeAssistant) -> list[str]:
    """Return every area that names a temperature sensor a zone can follow, by name."""
    areas = sorted(ar.async_get(hass).async_list_areas(), key=lambda area: area.name.casefold())
    resolution = resolve_area_sensors(hass, (area.id for area in areas))
    return [area.id for area in areas if resolution.area_sensors[area.id].temperature is not None]


def zone_name_for_areas(hass: HomeAssistant, area_ids: Sequence[str]) -> str | None:
    """Return the name a zone over these areas takes when the user gives none.

    One area gives its own name, and areas that all lie on one floor give the
    floor's name. Anything else, including an area that does not exist, gives
    no name, so the user names the zone.
    """
    registry = ar.async_get(hass)
    wanted = tuple(dict.fromkeys(area_ids))
    areas = [area for area_id in wanted if (area := registry.async_get_area(area_id))]
    if not areas or len(areas) != len(wanted):
        return None
    if len(areas) == 1:
        return areas[0].name
    floor_ids = {area.floor_id for area in areas}
    if len(floor_ids) != 1 or (floor_id := floor_ids.pop()) is None:
        return None
    floor = fr.async_get(hass).async_get_floor(floor_id)
    return floor.name if floor is not None else None


def async_track_area_changes(
    hass: HomeAssistant,
    area_ids: Iterable[str],
    resolution: AreaResolution,
    action: Callable[[], None],
) -> CALLBACK_TYPE:
    """Call ``action`` when a covered area, or an entity it names, changes.

    Area events cover a changed sensor choice, a removed area, and an area
    created with a covered ID. Home Assistant does not follow an entity rename
    into the area, but an entity registry change can turn a named sensor into
    one that Hydronicus provides, so those events are followed too.
    """
    covered = frozenset(area_ids)
    named = resolution.named_entity_ids()
    unsubscribers: list[CALLBACK_TYPE] = []

    @callback
    def _covered_area(event_data: ar.EventAreaRegistryUpdatedData) -> bool:
        return event_data["area_id"] in covered

    @callback
    def _named_entity(event_data: er.EventEntityRegistryUpdatedData) -> bool:
        return event_data["entity_id"] in named or event_data.get("old_entity_id") in named

    @callback
    def _changed(_event: Event[Any]) -> None:
        action()

    if covered:
        unsubscribers.append(
            hass.bus.async_listen(
                ar.EVENT_AREA_REGISTRY_UPDATED, _changed, event_filter=_covered_area
            )
        )
    if named:
        unsubscribers.append(
            hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, _changed, event_filter=_named_entity
            )
        )

    @callback
    def _unsubscribe() -> None:
        while unsubscribers:
            unsubscribers.pop()()

    return _unsubscribe


# Problems a Repair reports.


class ZoneAreaProblemKind(StrEnum):
    """The kinds of area problem a Repair reports."""

    AREA_MISSING = "zone_area_missing"
    NO_TEMPERATURE_SOURCE = "zone_without_temperature_source"
    SELF_FEED = "zone_area_self_feed"


@dataclass(frozen=True, slots=True)
class ZoneAreaProblem:
    """One area problem of one zone."""

    kind: ZoneAreaProblemKind
    zone: str
    area_id: str | None = None
    entity_ids: tuple[str, ...] = ()


def zone_area_problems(plant: Plant, resolution: AreaResolution) -> tuple[ZoneAreaProblem, ...]:
    """Return the area problems of a Plant, in zone and area order.

    A zone with a digital thermostat and no explicit temperature sensor has no
    temperature source when none of its areas names one.
    """
    problems: list[ZoneAreaProblem] = []
    missing = set(resolution.missing_area_ids)
    for zone in plant.zones:
        for area in zone.areas:
            if area.area in missing:
                problems.append(
                    ZoneAreaProblem(ZoneAreaProblemKind.AREA_MISSING, zone.slug, area.area)
                )
            elif own := resolution.self_provided.get(area.area):
                problems.append(
                    ZoneAreaProblem(ZoneAreaProblemKind.SELF_FEED, zone.slug, area.area, own)
                )
        if (
            zone.areas
            and isinstance(zone.thermostat, DigitalThermostat)
            and not zone.temperature
            and not any(
                (sensors := resolution.area_sensors.get(area.area)) is not None
                and sensors.temperature is not None
                for area in zone.areas
            )
        ):
            problems.append(ZoneAreaProblem(ZoneAreaProblemKind.NO_TEMPERATURE_SOURCE, zone.slug))
    return tuple(problems)


# The setup and plant file reviews.


@dataclass(frozen=True, slots=True)
class AreaReviewWarning:
    """One area warning a review lists, and whether saving needs a confirmation."""

    code: str
    area_id: str
    zones: tuple[str, ...]
    message: str
    needs_confirmation: bool

    @property
    def key(self) -> tuple[str, str, tuple[str, ...]]:
        """Identify the warning across two versions of a Plant."""
        return (self.code, self.area_id, self.zones)


def area_review_warnings(hass: HomeAssistant, plant: Plant) -> tuple[AreaReviewWarning, ...]:
    """Return the area warnings of a Plant, for a review before saving it.

    An area that does not exist, and an area without a humidity sensor in a zone
    that cools, need a confirmation. An area without a temperature sensor, and
    an area that several zones cover, do not.
    """
    resolution = resolve_area_sensors(hass, covered_area_ids(plant))
    missing = set(resolution.missing_area_ids)
    covering: dict[str, list[str]] = {}
    warnings: list[AreaReviewWarning] = []
    for zone in plant.zones:
        for area_id in dict.fromkeys(area.area for area in zone.areas):
            covering.setdefault(area_id, []).append(zone.slug)
            name = resolution.name(area_id)
            sensors = resolution.area_sensors.get(area_id, AreaSensors())
            if area_id in missing:
                warnings.append(
                    AreaReviewWarning(
                        "area_missing",
                        area_id,
                        (zone.slug,),
                        f"Zone {zone.title} covers area {area_id}, which does not exist in "
                        "Home Assistant, so it adds no reading until the area exists. Home "
                        "Assistant makes a new area's ID from its name, so an area named "
                        f"{resolution.recreate_name(area_id)} gets this ID.",
                        needs_confirmation=True,
                    )
                )
                continue
            if sensors.temperature is None:
                warnings.append(
                    AreaReviewWarning(
                        "area_without_temperature_sensor",
                        area_id,
                        (zone.slug,),
                        f"Area {name} of zone {zone.title} has no temperature sensor in its "
                        "area settings, so it adds no temperature reading.",
                        needs_confirmation=False,
                    )
                )
            if zone.cools and sensors.humidity is None:
                warnings.append(
                    AreaReviewWarning(
                        "area_without_humidity_sensor",
                        area_id,
                        (zone.slug,),
                        f"Area {name} of zone {zone.title} has no humidity sensor in its area "
                        "settings, although a loop of the zone cools, so cooling cannot "
                        "watch that area for condensation.",
                        needs_confirmation=True,
                    )
                )
    for area_id, zones in covering.items():
        if len(zones) > 1:
            names = [plant.zone(slug).title for slug in zones]
            warnings.append(
                AreaReviewWarning(
                    "area_in_several_zones",
                    area_id,
                    tuple(sorted(zones)),
                    f"Area {resolution.name(area_id)} is covered by zones {listed(names)}, "
                    "so its sensors count in each of them.",
                    needs_confirmation=False,
                )
            )
    return tuple(warnings)


def area_warnings_to_confirm(
    warnings: Iterable[AreaReviewWarning], before: Iterable[AreaReviewWarning] = ()
) -> tuple[AreaReviewWarning, ...]:
    """Return the warnings that need a confirmation and that the Plant did not have before."""
    known = {warning.key for warning in before}
    return tuple(
        warning for warning in warnings if warning.needs_confirmation and warning.key not in known
    )
