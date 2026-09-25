"""The plant file: one Plant as a portable, human-writable document.

The plant file describes a whole Plant with zones, loops, valves, pumps, and
sources addressed by slugs instead of UUIDs. Import turns a parsed document into
stored topology records and zone ownership, then validates them with
the stored decoder, the ownership rules, and the topology compiler. Export writes
the canonical form of stored data, so exporting and importing rebuilds a Plant
with the same object IDs, and therefore the same entity IDs, on any instance.

The module works on parsed mappings only. YAML is the transport, and adapters
parse and dump it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID, uuid5

from .configuration import (
    DesignatedReferenceError,
    StoredTopologyError,
    plant_configuration_from_entry_data,
)
from .model import CompiledPlant
from .ownership import OwnershipError, PlantOwnership, validate_ownership
from .topology import (
    CoolingObservationError,
    CoolingReferenceError,
    DuplicateActuatorBindingError,
    TopologyValidationError,
    compile_topology,
)

PLANT_FILE_FORMAT: Final = 1


class PlantDocumentError(ValueError):
    """A plant file cannot be imported.

    ``path`` is the dotted path of the offending key, such as
    ``zones.bedroom.loops.bedroom_loop.pump``, with list items as indices. It is
    empty for errors about the whole Plant.
    """

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ImportedPlant:
    """A validated Plant built from a plant file."""

    plant_id: str
    name: str
    topology: dict[str, Any]
    ownership: PlantOwnership
    compiled: CompiledPlant
    entity_paths: Mapping[str, str]


# Stored record fields in stored-decoder order, which is also the canonical
# order of plant file keys after ``id`` and ``name``.
_PUMP_FIELDS: Final = (
    "entity_id",
    "overrun_seconds",
    "power_feedback_entity",
    "flow_feedback_entity",
    "fault_feedback_entity",
    "power_feedback_max_age_seconds",
    "flow_feedback_max_age_seconds",
    "fault_feedback_max_age_seconds",
)
_VALVE_FIELDS: Final = (
    "entity_id",
    "opening_time_seconds",
    "readiness_entity_id",
    "position_feedback_entity",
    "position_feedback_max_age_seconds",
)
_CIRCUIT_FIELDS: Final = (
    "cooling_enabled",
    "supply_temperature_sensor",
    "surface_temperature_sensor",
    "condensation_margin",
    "supply_temperature_max_age_seconds",
    "surface_temperature_max_age_seconds",
)
_SOURCE_FIELDS: Final = (
    "source_type",
    "temperature_entity",
    "availability_entity",
    "maximum_age_seconds",
    "hysteresis",
    "source_demand_entity",
    "minimum_temperature",
    "priority",
)
_SELECTOR_FIELDS: Final = (
    "entity_id",
    "break_interval_seconds",
    "minimum_dwell_seconds",
    "release_option",
    "shadow_only",
)
_SENSOR_FIELDS: Final = (
    "entity_id",
    "required",
    "designated_reference",
    "weight",
    "calibration_offset",
    "max_age_seconds",
)
_THERMOSTAT_FIELDS: Final[Mapping[str, tuple[str, ...]]] = {
    "hydronicus": (
        "kind",
        "initial_target_temperature",
        "heating_start_delta",
        "heating_stop_delta",
        "cooling_start_delta",
        "cooling_stop_delta",
        "minimum_active_duration_seconds",
        "minimum_idle_duration_seconds",
        "preset_targets",
        "initial_preset",
    ),
    "external_climate": ("kind", "entity_id"),
}
# Area settings in canonical order, with the defaults an export leaves out.
_AREA_SETTINGS: Final[Mapping[str, object]] = {
    "required": False,
    "designated_reference": False,
    "weight": 1.0,
    "max_age_seconds": 1800.0,
}
_AREA_KEYS: Final = frozenset({"area", *_AREA_SETTINGS})
_ZONE_FIELDS: Final = (
    "thermostat",
    "areas",
    "temperature_sensor_metadata",
    "humidity_sensor_metadata",
    "temperature_aggregation",
)
# Stored fields that bind a Home Assistant entity.
_ENTITY_FIELDS: Final = frozenset(
    {
        "entity_id",
        "power_feedback_entity",
        "flow_feedback_entity",
        "fault_feedback_entity",
        "readiness_entity_id",
        "position_feedback_entity",
        "supply_temperature_sensor",
        "surface_temperature_sensor",
        "temperature_entity",
        "availability_entity",
        "source_demand_entity",
    }
)
_TOP_LEVEL_KEYS: Final = (
    "hydronicus",
    "id",
    "name",
    "pumps",
    "valves",
    "loops",
    "zones",
    "sources",
    "source_selector",
)
_ZONE_KEYS: Final = frozenset(
    {
        "id",
        "name",
        "thermostat",
        "areas",
        "temperature_sensors",
        "humidity_sensors",
        "temperature_aggregation",
        "valves",
        "loops",
        "shared_loops",
    }
)
_SENSOR_COLLECTIONS: Final = (
    ("temperature_sensor_metadata", "temperature_sensors"),
    ("humidity_sensor_metadata", "humidity_sensors"),
)
_ROUTE_KEYS: Final = ("route_id", "route_enabled")
_SHARED_LOOP_KEYS: Final = frozenset({"loop", *_ROUTE_KEYS})
_COLLECTIONS: Final = ("zones", "valves", "pumps", "circuits", "routes", "sources")
_SLUG: Final = re.compile(r"[a-z][a-z0-9_]*")


def _join(path: str, key: object) -> str:
    """Return the dotted path of one key below ``path``."""
    return f"{path}.{key}" if path else str(key)


def _name_from_slug(slug: str) -> str:
    """Turn ``living_room`` into ``Living room``."""
    text = slug.replace("_", " ")
    return text[:1].upper() + text[1:]


def _unknown_key(path: str, key: object) -> PlantDocumentError:
    return PlantDocumentError(_join(path, key), f"Unknown key {key!r}.")


def _uuid(value: object, path: str) -> str:
    """Read an explicit UUID."""
    if not isinstance(value, str):
        raise PlantDocumentError(path, "An id must be a UUID string.")
    try:
        return str(UUID(value))
    except ValueError as error:
        raise PlantDocumentError(path, f"{value!r} is not a UUID.") from error


def _entries(value: object, path: str) -> Iterator[tuple[str, Any, str]]:
    """Yield the slug, value, and path of every entry of a slug mapping."""
    if not isinstance(value, Mapping):
        raise PlantDocumentError(path, f"{path} must be a mapping from slugs to objects.")
    for slug, item in value.items():
        item_path = _join(path, slug)
        if not isinstance(slug, str) or not _SLUG.fullmatch(slug):
            raise PlantDocumentError(
                item_path,
                f"Slug {slug!r} must start with a lowercase letter and contain only lowercase "
                "letters, digits, and underscores.",
            )
        yield slug, item, item_path


@dataclass(frozen=True, slots=True)
class _Declared:
    """One named object of the file, before its record is built."""

    object_id: str
    path: str
    zone: str | None  # the owning zone slug, or None for the Plant


class _Importer:
    """Build stored records from one plant file.

    The first pass declares every slug in document order, so references can
    point forward and duplicate slugs are reported at their second occurrence.
    The second pass builds stored records, also in document order, so
    ``entity_paths`` records the first binding of every entity.
    """

    def __init__(self, plant_id: str) -> None:
        self._plant_id = plant_id
        self._namespace = UUID(plant_id)
        self._zones: dict[str, _Declared] = {}
        self._valves: dict[str, _Declared] = {}
        self._loops: dict[str, _Declared] = {}
        self._pumps: dict[str, _Declared] = {}
        self._sources: dict[str, _Declared] = {}
        self._shorthand_valves: dict[str, str] = {}  # item path -> generated valve slug
        self._id_paths: dict[str, str] = {}  # object or route id -> defining path
        self._topology: dict[str, Any] = {collection: [] for collection in _COLLECTIONS}
        self._records: list[tuple[str, dict[str, Any], str]] = []
        self._zone_objects: dict[str, str] = {}
        self._entity_paths: dict[str, str] = {}
        self._actuator_paths: list[tuple[str, str]] = []

    # Pass one: slugs and ids.

    def declare(self, document: Mapping[str, Any]) -> None:
        for key, value in document.items():
            if key == "pumps":
                for slug, item, path in _entries(value, key):
                    self._declare(self._pumps, "pump", slug, item, path, None)
            elif key == "valves":
                for slug, item, path in _entries(value, key):
                    self._declare(self._valves, "valve", slug, item, path, None)
            elif key == "loops":
                for slug, item, path in _entries(value, key):
                    self._declare_loop(slug, item, path, None)
            elif key == "sources":
                for slug, item, path in _entries(value, key):
                    self._declare(self._sources, "source", slug, item, path, None)
            elif key == "zones":
                for slug, item, path in _entries(value, key):
                    self._declare_zone(slug, item, path)

    def _declare_zone(self, slug: str, zone: object, path: str) -> None:
        self._declare(self._zones, "zone", slug, zone, path, None)
        if not isinstance(zone, Mapping):
            return
        for key, value in zone.items():
            if key == "valves":
                for valve_slug, item, item_path in _entries(value, _join(path, key)):
                    self._declare(self._valves, "valve", valve_slug, item, item_path, slug)
            elif key == "loops":
                for loop_slug, item, item_path in _entries(value, _join(path, key)):
                    self._declare_loop(loop_slug, item, item_path, slug)

    def _declare_loop(self, slug: str, loop: object, path: str, zone: str | None) -> None:
        self._declare(self._loops, "circuit", slug, loop, path, zone)
        valves = loop.get("valves") if isinstance(loop, Mapping) else None
        if not isinstance(valves, list):
            return
        count = 0
        for index, item in enumerate(valves):
            if isinstance(item, str) and "." in item:
                count += 1
                valve_slug = f"{slug}_valve" if count == 1 else f"{slug}_valve_{count}"
                item_path = _join(_join(path, "valves"), index)
                self._shorthand_valves[item_path] = valve_slug
                self._declare(self._valves, "valve", valve_slug, None, item_path, zone)

    def _declare(
        self,
        table: dict[str, _Declared],
        kind: str,
        slug: str,
        item: object,
        path: str,
        zone: str | None,
    ) -> None:
        if slug in table:
            raise PlantDocumentError(path, f"Slug {slug!r} is already used at {table[slug].path}.")
        if isinstance(item, Mapping) and "id" in item:
            object_id = _uuid(item["id"], _join(path, "id"))
            self._claim(object_id, path, _join(path, "id"))
        else:
            object_id = str(uuid5(self._namespace, f"{kind}:{slug}"))
            self._claim(object_id, path, path)
        table[slug] = _Declared(object_id, path, zone)

    def _claim(self, object_id: str, path: str, error_path: str) -> None:
        if object_id in self._id_paths:
            raise PlantDocumentError(
                error_path, f"Id {object_id} is already used at {self._id_paths[object_id]}."
            )
        self._id_paths[object_id] = path

    # Pass two: stored records.

    def build(self, document: Mapping[str, Any]) -> None:
        for key, value in document.items():
            if key == "pumps":
                for slug, item, path in _entries(value, key):
                    record = self._actuator(
                        self._pumps[slug], item, path, _PUMP_FIELDS, _name_from_slug(slug)
                    )
                    self._add("pumps", record, path)
            elif key == "valves":
                for slug, item, path in _entries(value, key):
                    self._valve(slug, item, path, None)
            elif key == "loops":
                for slug, item, path in _entries(value, key):
                    self._loop(slug, item, path, None)
            elif key == "zones":
                for slug, item, path in _entries(value, key):
                    self._zone(slug, item, path)
            elif key == "sources":
                for slug, item, path in _entries(value, key):
                    if not isinstance(item, Mapping):
                        raise PlantDocumentError(path, "A source must be a mapping.")
                    record = self._record(
                        self._sources[slug].object_id,
                        item,
                        path,
                        _SOURCE_FIELDS,
                        _name_from_slug(slug),
                    )
                    self._add("sources", record, path)
            elif key == "source_selector":
                self._source_selector(value, key)

    def _add(self, collection: str, record: dict[str, Any], path: str) -> None:
        self._topology[collection].append(record)
        self._records.append((collection, record, path))

    def _bind(self, value: object, path: str, *, required: bool = False) -> None:
        """Record an entity binding, and reject a malformed entity ID."""
        if value is None and not required:
            return
        if not isinstance(value, str) or not value.strip():
            raise PlantDocumentError(path, "An entity ID must be a non-empty string.")
        self._entity_paths.setdefault(value, path)

    def _name(self, item: Mapping[str, Any], path: str, default: str) -> str:
        if "name" not in item:
            return default
        name = item["name"]
        if not isinstance(name, str) or not name.strip():
            raise PlantDocumentError(_join(path, "name"), "A name must be a non-empty string.")
        return name

    def _record(
        self,
        object_id: str,
        item: Mapping[str, Any],
        path: str,
        fields: tuple[str, ...],
        default_name: str,
        *,
        entity_id_path: str | None = None,
    ) -> dict[str, Any]:
        """Build one stored record whose leaf fields use the stored keys.

        With ``entity_id_path``, ``entity_id`` is a required actuator binding
        found at that path.
        """
        record: dict[str, Any] = {"id": object_id, "name": self._name(item, path, default_name)}
        for key, value in item.items():
            if key in ("id", "name"):
                continue
            if key not in fields:
                raise _unknown_key(path, key)
            if key == "entity_id" and entity_id_path is not None:
                self._bind(value, entity_id_path, required=True)
            elif key in _ENTITY_FIELDS:
                self._bind(value, _join(path, key))
        record.update((key, deepcopy(item[key])) for key in fields if key in item)
        return record

    def _actuator(
        self,
        declared: _Declared,
        item: object,
        path: str,
        fields: tuple[str, ...],
        default_name: str,
    ) -> dict[str, Any]:
        """Build a pump or valve record from its long form or entity ID shorthand."""
        if isinstance(item, str):
            item, entity_path = {"entity_id": item}, path
        elif isinstance(item, Mapping):
            entity_path = _join(path, "entity_id")
            if "entity_id" not in item:
                raise PlantDocumentError(entity_path, "An entity_id is required.")
        else:
            raise PlantDocumentError(path, "Expected an entity ID or a mapping.")
        record = self._record(
            declared.object_id, item, path, fields, default_name, entity_id_path=entity_path
        )
        self._actuator_paths.append((record["entity_id"], entity_path))
        return record

    def _valve(
        self, slug: str, item: object, path: str, zone: str | None, *, name: str | None = None
    ) -> None:
        declared = self._valves[slug]
        record = self._actuator(declared, item, path, _VALVE_FIELDS, name or _name_from_slug(slug))
        if zone is not None:
            self._zone_objects[declared.object_id] = self._zones[zone].object_id
        self._add("valves", record, path)

    def _loop(self, slug: str, item: object, path: str, zone: str | None) -> None:
        declared = self._loops[slug]
        if not isinstance(item, Mapping):
            raise PlantDocumentError(path, "A loop must be a mapping.")
        allowed = {"id", "name", "valves", "pump", *_CIRCUIT_FIELDS}
        if zone is not None:
            allowed.update(_ROUTE_KEYS)
        name = self._name(item, path, _name_from_slug(slug))
        valve_ids: list[str] | None = None
        pump_id: str | None = None
        for key, value in item.items():
            key_path = _join(path, key)
            if key not in allowed:
                raise _unknown_key(path, key)
            if key == "valves":
                valve_ids = self._loop_valves(name, value, key_path, zone)
            elif key == "pump":
                pump = self._pumps.get(value) if isinstance(value, str) else None
                if pump is None:
                    raise PlantDocumentError(key_path, f"Unknown pump {value!r}.")
                pump_id = pump.object_id
            elif key in _ENTITY_FIELDS:
                self._bind(value, key_path)
        if valve_ids is None:
            raise PlantDocumentError(_join(path, "valves"), "A loop needs a list of valves.")
        if pump_id is None:
            raise PlantDocumentError(_join(path, "pump"), "A loop needs a pump.")
        record: dict[str, Any] = {
            "id": declared.object_id,
            "name": name,
            "valve_ids": valve_ids,
            "pump_id": pump_id,
        }
        record.update((key, deepcopy(item[key])) for key in _CIRCUIT_FIELDS if key in item)
        self._add("circuits", record, path)
        if zone is not None:
            self._zone_objects[declared.object_id] = self._zones[zone].object_id
            self._route(zone, slug, item, path)

    def _loop_valves(self, loop_name: str, value: object, path: str, zone: str | None) -> list[str]:
        if not isinstance(value, list) or not value:
            raise PlantDocumentError(path, "A loop needs a non-empty list of valves.")
        valve_ids: list[str] = []
        count = 0
        for index, item in enumerate(value):
            item_path = _join(path, index)
            if not isinstance(item, str) or not item:
                raise PlantDocumentError(item_path, "Expected a valve slug or an entity ID.")
            if "." in item:
                count += 1
                valve_slug = self._shorthand_valves[item_path]
                valve_name = f"{loop_name} valve" if count == 1 else f"{loop_name} valve {count}"
                self._valve(valve_slug, item, item_path, zone, name=valve_name)
                declared = self._valves[valve_slug]
            else:
                found = self._valves.get(item)
                if found is None:
                    raise PlantDocumentError(item_path, f"Unknown valve {item!r}.")
                if found.zone is not None and found.zone != zone:
                    if zone is None:
                        raise PlantDocumentError(
                            item_path,
                            f"Valve {item!r} is private to zone {found.zone!r}, and a Plant "
                            "loop can only use Plant valves.",
                        )
                    raise PlantDocumentError(
                        item_path, f"Valve {item!r} is private to zone {found.zone!r}."
                    )
                declared = found
            if declared.object_id in valve_ids:
                raise PlantDocumentError(item_path, f"Valve {item!r} is listed twice.")
            valve_ids.append(declared.object_id)
        return valve_ids

    def _route(self, zone: str, loop: str, options: Mapping[str, Any], path: str) -> None:
        if "route_id" in options:
            route_path = _join(path, "route_id")
            route_id = _uuid(options["route_id"], route_path)
            self._claim(route_id, path, route_path)
        else:
            route_id = str(uuid5(self._namespace, f"route:{zone}:{loop}"))
            self._claim(route_id, path, path)
        enabled = options.get("route_enabled", True)
        if not isinstance(enabled, bool):
            raise PlantDocumentError(
                _join(path, "route_enabled"), "route_enabled must be true or false."
            )
        record: dict[str, Any] = {
            "id": route_id,
            "zone_id": self._zones[zone].object_id,
            "circuit_id": self._loops[loop].object_id,
        }
        if not enabled:
            record["enabled"] = False
        self._add("routes", record, path)

    def _zone(self, slug: str, item: object, path: str) -> None:
        declared = self._zones[slug]
        if not isinstance(item, Mapping):
            raise PlantDocumentError(path, "A zone must be a mapping.")
        fields: dict[str, Any] = {"thermostat": {"kind": "hydronicus"}}
        for key, value in item.items():
            key_path = _join(path, key)
            if key not in _ZONE_KEYS:
                raise _unknown_key(path, key)
            if key == "thermostat":
                fields["thermostat"] = self._thermostat(value, key_path)
            elif key == "areas":
                fields["areas"] = self._areas(value, key_path)
            elif key == "temperature_sensors":
                fields["temperature_sensor_metadata"] = self._sensors(value, key_path)
            elif key == "humidity_sensors":
                fields["humidity_sensor_metadata"] = self._sensors(value, key_path)
            elif key == "temperature_aggregation":
                fields["temperature_aggregation"] = deepcopy(value)
            elif key == "valves":
                for valve_slug, valve, valve_path in _entries(value, key_path):
                    self._valve(valve_slug, valve, valve_path, slug)
            elif key == "loops":
                for loop_slug, loop, loop_path in _entries(value, key_path):
                    self._loop(loop_slug, loop, loop_path, slug)
            elif key == "shared_loops":
                self._shared_loops(slug, value, key_path)
        if (
            fields["thermostat"]["kind"] == "hydronicus"
            and not fields.get("temperature_sensor_metadata")
            and not fields.get("areas")
        ):
            raise PlantDocumentError(
                _join(path, "temperature_sensors"),
                "A zone with a Hydronicus thermostat needs at least one temperature sensor "
                "or area.",
            )
        if not any(
            route["zone_id"] == declared.object_id and route.get("enabled", True)
            for route in self._topology["routes"]
        ):
            raise PlantDocumentError(path, "A zone needs at least one enabled loop.")
        record: dict[str, Any] = {
            "id": declared.object_id,
            "name": self._name(item, path, _name_from_slug(slug)),
        }
        record.update((key, fields[key]) for key in _ZONE_FIELDS if key in fields)
        self._add("zones", record, path)

    def _thermostat(self, value: object, path: str) -> dict[str, Any]:
        if isinstance(value, str):
            if not value.startswith("climate."):
                raise PlantDocumentError(
                    path, "A thermostat entity ID must belong to the climate domain."
                )
            self._bind(value, path)
            return {"kind": "external_climate", "entity_id": value}
        if not isinstance(value, Mapping):
            raise PlantDocumentError(path, "Expected a climate entity ID or a mapping.")
        kind = value.get("kind", "hydronicus")
        fields = _THERMOSTAT_FIELDS.get(kind) if isinstance(kind, str) else None
        if fields is None:
            raise PlantDocumentError(
                _join(path, "kind"), "The thermostat kind must be hydronicus or external_climate."
            )
        for key, item in value.items():
            if key not in fields:
                raise _unknown_key(path, key)
            if key == "entity_id":
                self._bind(item, _join(path, key), required=True)
        thermostat: dict[str, Any] = {"kind": kind}
        thermostat.update((key, deepcopy(value[key])) for key in fields[1:] if key in value)
        return thermostat

    def _sensors(self, value: object, path: str) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise PlantDocumentError(path, "Expected a list of sensors.")
        records: list[dict[str, Any]] = []
        for index, item in enumerate(value):
            item_path = _join(path, index)
            if isinstance(item, str) and item.strip():
                self._bind(item, item_path)
                records.append({"entity_id": item})
            elif isinstance(item, Mapping):
                for key in item:
                    if key not in _SENSOR_FIELDS:
                        raise _unknown_key(item_path, key)
                self._bind(item.get("entity_id"), _join(item_path, "entity_id"), required=True)
                records.append({key: deepcopy(item[key]) for key in _SENSOR_FIELDS if key in item})
            else:
                raise PlantDocumentError(item_path, "Expected an entity ID or a sensor mapping.")
        return records

    def _areas(self, value: object, path: str) -> list[dict[str, Any]]:
        """Read areas, each an area ID or a mapping of ``area`` and its settings."""
        if not isinstance(value, list):
            raise PlantDocumentError(path, "Expected a list of areas.")
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(value):
            item_path = _join(path, index)
            if isinstance(item, str) and item.strip():
                area_id, settings = item, {}
            elif isinstance(item, Mapping):
                for key in item:
                    if key not in _AREA_KEYS:
                        raise _unknown_key(item_path, key)
                area_id = item.get("area")
                if not isinstance(area_id, str) or not area_id.strip():
                    raise PlantDocumentError(_join(item_path, "area"), "An area needs an area ID.")
                settings = {key: deepcopy(item[key]) for key in _AREA_SETTINGS if key in item}
            else:
                raise PlantDocumentError(item_path, "Expected an area ID or an area mapping.")
            if area_id in seen:
                raise PlantDocumentError(item_path, f"Area {area_id!r} is listed twice.")
            seen.add(area_id)
            records.append({"area_id": area_id, **settings})
        return records

    def _shared_loops(self, zone: str, value: object, path: str) -> None:
        if not isinstance(value, list):
            raise PlantDocumentError(path, "Expected a list of loop slugs.")
        seen: set[str] = set()
        for index, item in enumerate(value):
            item_path = _join(path, index)
            options: Mapping[str, Any]
            if isinstance(item, str):
                slug, options, slug_path = item, {}, item_path
            elif isinstance(item, Mapping):
                for key in item:
                    if key not in _SHARED_LOOP_KEYS:
                        raise _unknown_key(item_path, key)
                slug_path = _join(item_path, "loop")
                if "loop" not in item:
                    raise PlantDocumentError(slug_path, "A shared loop needs a loop slug.")
                slug, options = item["loop"], item
            else:
                raise PlantDocumentError(item_path, "Expected a loop slug or a mapping.")
            declared = self._loops.get(slug) if isinstance(slug, str) else None
            if declared is None:
                raise PlantDocumentError(slug_path, f"Unknown loop {slug!r}.")
            if declared.zone is not None:
                raise PlantDocumentError(
                    slug_path,
                    f"Loop {slug!r} is private to zone {declared.zone!r}; shared_loops can "
                    "only list Plant loops.",
                )
            if slug in seen:
                raise PlantDocumentError(slug_path, f"Loop {slug!r} is listed twice.")
            seen.add(slug)
            self._route(zone, slug, options, item_path)

    def _source_selector(self, value: object, path: str) -> None:
        if not isinstance(value, Mapping):
            raise PlantDocumentError(path, "The source selector must be a mapping.")
        if "id" in value:
            selector_id = _uuid(value["id"], _join(path, "id"))
            self._claim(selector_id, path, _join(path, "id"))
        else:
            selector_id = str(uuid5(self._namespace, "source_selector:source_selector"))
            self._claim(selector_id, path, path)
        record = self._record(
            selector_id, value, path, _SELECTOR_FIELDS, _name_from_slug("source_selector")
        )
        self._topology["source_selector"] = record
        self._records.append(("source_selector", record, path))

    # Validation.

    def finish(self, name: str) -> ImportedPlant:
        # Decode each record alone first, so a decode error names its object.
        for collection, record, path in self._records:
            single = record if collection == "source_selector" else [record]
            try:
                plant_configuration_from_entry_data(
                    {"plant_id": self._plant_id, "topology": {collection: single}}
                )
            except DesignatedReferenceError as error:
                raise PlantDocumentError(_join(path, "temperature_sensors"), str(error)) from error
            except StoredTopologyError as error:
                raise PlantDocumentError(path, str(error)) from error
        configuration = plant_configuration_from_entry_data(
            {"plant_id": self._plant_id, "topology": self._topology}
        )
        ownership = PlantOwnership(zone_objects=self._zone_objects)
        try:
            validate_ownership(configuration, ownership)
        except OwnershipError as error:
            raise PlantDocumentError(self._id_paths[error.object_ids[0]], str(error)) from error
        try:
            compiled = compile_topology(configuration)
        except DuplicateActuatorBindingError as error:
            entity_id = error.entity_ids[0]
            bindings = [path for entity, path in self._actuator_paths if entity == entity_id]
            raise PlantDocumentError(bindings[1], str(error)) from error
        except CoolingReferenceError as error:
            raise PlantDocumentError(self._id_paths[error.circuit_id], str(error)) from error
        except CoolingObservationError as error:
            field = f"{error.observation}_sensors"
            raise PlantDocumentError(_join(self._id_paths[error.zone_id], field), str(error)) from (
                error
            )
        except TopologyValidationError as error:
            raise PlantDocumentError("", str(error)) from error
        return ImportedPlant(
            plant_id=self._plant_id,
            name=name,
            topology=self._topology,
            ownership=ownership,
            compiled=compiled,
            entity_paths=self._entity_paths,
        )


def import_plant_document(document: Mapping[str, Any], *, plant_id: str) -> ImportedPlant:
    """Build and validate a Plant from a parsed plant file.

    The file's ``id`` wins over ``plant_id``, which is the fallback for a file
    without one. Raise ``PlantDocumentError`` at the most specific path when the
    file is malformed, references something unknown, breaks ownership, or does
    not compile.
    """
    if not isinstance(document, Mapping):
        raise PlantDocumentError("", "A plant file must be a mapping.")
    for key in document:
        if key not in _TOP_LEVEL_KEYS:
            raise _unknown_key("", key)
    if "hydronicus" not in document:
        raise PlantDocumentError(
            "hydronicus",
            f"A plant file starts with the format version: hydronicus: {PLANT_FILE_FORMAT}.",
        )
    version = document["hydronicus"]
    if type(version) is not int or version != PLANT_FILE_FORMAT:
        raise PlantDocumentError(
            "hydronicus",
            f"Plant file format {version!r} is not supported; expected {PLANT_FILE_FORMAT}.",
        )
    if "id" in document:
        resolved_id = _uuid(document["id"], "id")
    else:
        try:
            resolved_id = str(UUID(plant_id))
        except ValueError as error:
            raise PlantDocumentError("", f"Plant id {plant_id!r} is not a UUID.") from error
    name = document.get("name")
    if not isinstance(name, str) or not name.strip():
        raise PlantDocumentError("name", "A plant file needs a non-empty name.")

    importer = _Importer(resolved_id)
    importer.declare(document)
    importer.build(document)
    return importer.finish(name)


# Export.


def _slug_base(name: str, kind: str) -> str:
    """Make a slug from a name, folding accented letters to ASCII."""
    folded = unicodedata.normalize("NFKD", name.casefold()).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", folded).strip("_")
    if not base:
        return kind
    if base[0].isdigit():
        return f"{kind}_{base}"
    return base


def _slugs(records: tuple[Mapping[str, Any], ...], kind: str) -> dict[str, str]:
    """Return a unique slug for the id of every record, assigned in (name, id) order."""
    taken: set[str] = set()
    slugs: dict[str, str] = {}
    for record in sorted(records, key=lambda item: (str(item["name"]), str(item["id"]))):
        base = _slug_base(str(record["name"]), kind)
        slug, suffix = base, 2
        while slug in taken:
            slug, suffix = f"{base}_{suffix}", suffix + 1
        taken.add(slug)
        slugs[record["id"]] = slug
    return slugs


def _ordered(
    record: Mapping[str, Any], fields: tuple[str, ...], *, skip: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Copy stored fields in canonical order, with unknown keys sorted last.

    Unknown keys are kept rather than dropped, so importing the file rejects
    them instead of silently losing data.
    """
    result = {key: deepcopy(record[key]) for key in fields if key in record}
    known = {*fields, *skip}
    result.update(
        (key, deepcopy(record[key])) for key in sorted(record, key=str) if key not in known
    )
    return result


def _long_form(
    record: Mapping[str, Any],
    fields: tuple[str, ...],
    *,
    references: Mapping[str, Any] | None = None,
    skip: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return the canonical long form of one object: id, name, references, fields."""
    return {
        "id": record["id"],
        "name": record["name"],
        **(references or {}),
        **_ordered(record, fields, skip=("id", "name", *skip)),
    }


def _area_entry(area: Mapping[str, Any]) -> str | dict[str, Any]:
    """Write an area as its bare ID when every setting is the default."""
    entry: dict[str, Any] = {"area": area["area_id"]}
    entry.update(_ordered(area, tuple(_AREA_SETTINGS), skip=("area_id",)))
    if all(
        key == "area" or (key in _AREA_SETTINGS and value == _AREA_SETTINGS[key])
        for key, value in entry.items()
    ):
        return str(area["area_id"])
    return entry


def _route_options(route: Mapping[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {"route_id": route["id"]}
    if route.get("enabled", True) is False:
        options["route_enabled"] = False
    return options


def _by_slug(items: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    return dict(sorted(items))


def export_plant_document(
    *, name: str, plant_id: str, topology: Mapping[str, Any], ownership: PlantOwnership
) -> dict[str, Any]:
    """Write the canonical plant file of a stored Plant.

    Raise ``ValueError`` when the stored topology does not decode or the
    ownership breaks a rule, since such a Plant has no faithful plant file.
    """
    configuration = plant_configuration_from_entry_data(
        {"plant_id": plant_id, "topology": topology}
    )
    validate_ownership(configuration, ownership)
    owners = ownership.zone_objects
    zones, valves, pumps, circuits, routes, sources = (
        tuple(topology.get(key, ())) for key in _COLLECTIONS
    )
    circuits_by_id = {circuit["id"]: circuit for circuit in circuits}
    valve_slugs = _slugs(valves, "valve")
    loop_slugs = _slugs(circuits, "loop")
    pump_slugs = _slugs(pumps, "pump")

    def loop(circuit: Mapping[str, Any]) -> dict[str, Any]:
        references = {
            "valves": [valve_slugs[valve_id] for valve_id in circuit["valve_ids"]],
            "pump": pump_slugs[circuit["pump_id"]],
        }
        return _long_form(
            circuit, _CIRCUIT_FIELDS, references=references, skip=("valve_ids", "pump_id")
        )

    def owned_valves(owner: str | None) -> dict[str, Any]:
        return _by_slug(
            (valve_slugs[valve["id"]], _long_form(valve, _VALVE_FIELDS))
            for valve in valves
            if owners.get(valve["id"]) == owner
        )

    def zone_entry(zone: Mapping[str, Any]) -> dict[str, Any]:
        zone_id = zone["id"]
        thermostat = zone["thermostat"]
        result: dict[str, Any] = {
            "id": zone_id,
            "name": zone["name"],
            "thermostat": _ordered(thermostat, _THERMOSTAT_FIELDS[thermostat["kind"]]),
        }
        if "areas" in zone:
            result["areas"] = [_area_entry(area) for area in zone["areas"]]
        for stored_key, file_key in _SENSOR_COLLECTIONS:
            if stored_key in zone:
                result[file_key] = [_ordered(sensor, _SENSOR_FIELDS) for sensor in zone[stored_key]]
        result.update(_ordered(zone, ("temperature_aggregation",), skip=("id", *_ZONE_FIELDS)))
        if zone_valves := owned_valves(zone_id):
            result["valves"] = zone_valves
        own_routes = [route for route in routes if route["zone_id"] == zone_id]
        # Ownership rules R5 and R6 give every private loop exactly one route.
        if private_loops := _by_slug(
            (
                loop_slugs[route["circuit_id"]],
                loop(circuits_by_id[route["circuit_id"]]) | _route_options(route),
            )
            for route in own_routes
            if route["circuit_id"] in owners
        ):
            result["loops"] = private_loops
        if shared_loops := sorted(
            (
                {"loop": loop_slugs[route["circuit_id"]], **_route_options(route)}
                for route in own_routes
                if route["circuit_id"] not in owners
            ),
            key=lambda item: str(item["loop"]),
        ):
            result["shared_loops"] = shared_loops
        return result

    zone_slugs = _slugs(zones, "zone")
    source_slugs = _slugs(sources, "source")
    sections = {
        "pumps": _by_slug(
            (pump_slugs[pump["id"]], _long_form(pump, _PUMP_FIELDS)) for pump in pumps
        ),
        "valves": owned_valves(None),
        "loops": _by_slug(
            (loop_slugs[circuit["id"]], loop(circuit))
            for circuit in circuits
            if circuit["id"] not in owners
        ),
        "zones": _by_slug((zone_slugs[zone["id"]], zone_entry(zone)) for zone in zones),
        "sources": _by_slug(
            (source_slugs[source["id"]], _long_form(source, _SOURCE_FIELDS)) for source in sources
        ),
    }
    document: dict[str, Any] = {"hydronicus": PLANT_FILE_FORMAT, "id": plant_id, "name": name}
    document.update((key, section) for key, section in sections.items() if section)
    if (selector := topology.get("source_selector")) is not None:
        document["source_selector"] = _long_form(selector, _SELECTOR_FIELDS)
    return document
