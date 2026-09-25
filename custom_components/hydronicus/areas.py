"""The Home Assistant areas that zones cover, and the sensors those areas name.

Every area registry read goes through this module. A zone follows the
temperature and humidity sensors that each of its areas currently names, so the
runtime, the plant file review, diagnostics, and repairs resolve them here.

Home Assistant does not update an area's sensors when one of those entities is
renamed in the entity registry (checked against 2026.9), so a renamed sensor
leaves the area naming an entity that no longer exists. The runtime then reports
it as a missing sensor of the area, and the area settings fix it.
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

from .const import (
    CONF_AREA_ID,
    CONF_AREAS,
    CONF_CIRCUITS,
    CONF_COOLING_ENABLED,
    CONF_NAME,
    CONF_ROUTES,
    CONF_TOPOLOGY,
    CONF_ZONES,
)
from .core.model import AreaSensors, CompiledPlant, HydronicusThermostatConfig
from .flows.common import is_hydronicus_owned


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
    # Names are for messages only, so renaming an area never reloads the Plant.
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

    def named_entity_ids(self) -> frozenset[str]:
        """Return every entity a covered area names, followed or ignored."""
        named = {
            entity_id
            for sensors in self.area_sensors.values()
            for entity_id in (sensors.temperature_entity_id, sensors.humidity_entity_id)
            if entity_id
        }
        return frozenset(named | set(self.self_provided_entity_ids))

    def name(self, area_id: str) -> str:
        """Return an area's name, or its ID when it does not exist."""
        return self.area_names.get(area_id, area_id)

    def fingerprint(self) -> dict[str, Any]:
        """Return the JSON-serializable part of the resolution that shapes the Plant."""
        return {
            "sensors": {
                area_id: [sensors.temperature_entity_id, sensors.humidity_entity_id]
                for area_id, sensors in sorted(self.area_sensors.items())
            },
            "missing": sorted(self.missing_area_ids),
            "self_provided": {
                area_id: sorted(entity_ids)
                for area_id, entity_ids in sorted(self.self_provided.items())
            },
        }


def _stored_zones(data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return the stored zone records, tolerating malformed data that setup rejects."""
    topology = data.get(CONF_TOPOLOGY)
    zones = topology.get(CONF_ZONES) if isinstance(topology, Mapping) else None
    if not isinstance(zones, list):
        return []
    return [zone for zone in zones if isinstance(zone, Mapping)]


def _zone_area_ids(zone: Mapping[str, Any]) -> list[str]:
    """Return the area IDs one stored zone covers, in stored order."""
    areas = zone.get(CONF_AREAS)
    if not isinstance(areas, list):
        return []
    return [
        area[CONF_AREA_ID]
        for area in areas
        if isinstance(area, Mapping) and isinstance(area.get(CONF_AREA_ID), str)
    ]


def covered_area_ids(data: Mapping[str, Any]) -> tuple[str, ...]:
    """Return every area a zone of the stored Plant covers, each once."""
    return tuple(
        dict.fromkeys(area_id for zone in _stored_zones(data) for area_id in _zone_area_ids(zone))
    )


def resolve_area_sensors(hass: HomeAssistant, area_ids: Iterable[str]) -> AreaResolution:
    """Resolve the sensors that Home Assistant currently names for each area."""
    registry = ar.async_get(hass)
    area_sensors: dict[str, AreaSensors] = {}
    missing: list[str] = []
    self_provided: dict[str, tuple[str, ...]] = {}
    names: dict[str, str] = {}
    for area_id in dict.fromkeys(area_ids):
        area = registry.async_get_area(area_id)
        if area is None:
            missing.append(area_id)
            continue
        names[area_id] = area.name
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


def entry_area_resolution(hass: HomeAssistant, entry: Any) -> AreaResolution:
    """Resolve the areas that the zones of a config entry cover."""
    return resolve_area_sensors(hass, covered_area_ids(entry.data))


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
    one that Hydronicus provides, so those events are followed too. The action
    decides whether anything the Plant depends on actually changed.
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
    zone_id: str
    area_id: str | None = None
    entity_ids: tuple[str, ...] = ()


def zone_area_problems(
    plant: CompiledPlant, resolution: AreaResolution
) -> tuple[ZoneAreaProblem, ...]:
    """Return the area problems of a compiled Plant, in stable zone and area order."""
    problems: list[ZoneAreaProblem] = []
    missing = set(resolution.missing_area_ids)
    for zone_id in sorted(plant.zones):
        zone = plant.zones[zone_id]
        for area in zone.areas:
            if area.area_id in missing:
                problems.append(
                    ZoneAreaProblem(ZoneAreaProblemKind.AREA_MISSING, zone_id, area.area_id)
                )
            elif own := resolution.self_provided.get(area.area_id):
                problems.append(
                    ZoneAreaProblem(ZoneAreaProblemKind.SELF_FEED, zone_id, area.area_id, own)
                )
        if (
            zone.areas
            and isinstance(zone.thermostat, HydronicusThermostatConfig)
            and not zone.temperature_sensor_metadata
        ):
            problems.append(ZoneAreaProblem(ZoneAreaProblemKind.NO_TEMPERATURE_SOURCE, zone_id))
    return tuple(problems)


# The plant file and setup review.


@dataclass(frozen=True, slots=True)
class AreaReviewWarning:
    """One area warning a review lists, and whether saving needs a confirmation."""

    code: str
    area_id: str
    zone_ids: tuple[str, ...]
    message: str
    needs_confirmation: bool

    @property
    def key(self) -> tuple[str, str, tuple[str, ...]]:
        """Identify the warning across two versions of a Plant."""
        return (self.code, self.area_id, self.zone_ids)


def _cooled_zone_ids(data: Mapping[str, Any]) -> set[str]:
    """Return the zones that an enabled route connects to a cooling loop."""
    topology = data.get(CONF_TOPOLOGY)
    if not isinstance(topology, Mapping):
        return set()
    cooling = {
        circuit.get("id")
        for circuit in topology.get(CONF_CIRCUITS, ())
        if isinstance(circuit, Mapping) and circuit.get(CONF_COOLING_ENABLED) is True
    }
    return {
        str(route.get("zone_id"))
        for route in topology.get(CONF_ROUTES, ())
        if isinstance(route, Mapping)
        and route.get("enabled", True) is True
        and route.get("circuit_id") in cooling
    }


def listed(names: Sequence[str]) -> str:
    """Join names the way a sentence lists them, such as ``A, B and C``."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"


def area_review_warnings(
    hass: HomeAssistant, data: Mapping[str, Any]
) -> tuple[AreaReviewWarning, ...]:
    """Return the area warnings of stored Plant data, for a review before saving it.

    An area that does not exist, and an area without a humidity sensor in a zone
    that a cooling loop serves, need a confirmation. An area without a
    temperature sensor, and an area that several zones cover, do not.
    """
    zones = _stored_zones(data)
    resolution = resolve_area_sensors(hass, covered_area_ids(data))
    cooled = _cooled_zone_ids(data)
    missing = set(resolution.missing_area_ids)
    covering: dict[str, list[Mapping[str, Any]]] = {}
    warnings: list[AreaReviewWarning] = []
    for zone in zones:
        zone_id = str(zone.get("id"))
        zone_name = str(zone.get(CONF_NAME, zone_id))
        for area_id in dict.fromkeys(_zone_area_ids(zone)):
            covering.setdefault(area_id, []).append(zone)
            area = resolution.name(area_id)
            sensors = resolution.area_sensors.get(area_id, AreaSensors())
            if area_id in missing:
                warnings.append(
                    AreaReviewWarning(
                        "area_missing",
                        area_id,
                        (zone_id,),
                        f"Zone {zone_name} covers area {area_id}, which does not exist in "
                        "Home Assistant, so it adds no reading until an area with this ID "
                        "is created.",
                        needs_confirmation=True,
                    )
                )
                continue
            if sensors.temperature_entity_id is None:
                warnings.append(
                    AreaReviewWarning(
                        "area_without_temperature_sensor",
                        area_id,
                        (zone_id,),
                        f"Area {area} of zone {zone_name} has no temperature sensor in its "
                        "area settings, so it adds no temperature reading.",
                        needs_confirmation=False,
                    )
                )
            if zone_id in cooled and sensors.humidity_entity_id is None:
                warnings.append(
                    AreaReviewWarning(
                        "area_without_humidity_sensor",
                        area_id,
                        (zone_id,),
                        f"Area {area} of zone {zone_name} has no humidity sensor in its area "
                        "settings, although a cooling loop serves the zone, so cooling cannot "
                        "watch that area for condensation.",
                        needs_confirmation=True,
                    )
                )
    for area_id, area_zones in covering.items():
        if len(area_zones) > 1:
            names = [str(zone.get(CONF_NAME, zone.get("id"))) for zone in area_zones]
            warnings.append(
                AreaReviewWarning(
                    "area_in_several_zones",
                    area_id,
                    tuple(sorted(str(zone.get("id")) for zone in area_zones)),
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
