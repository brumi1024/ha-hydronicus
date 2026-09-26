"""The plant file, format 2, which is also the storage schema.

A plant file describes one whole Plant: an optional source, its pumps, its plant
loops, and its zones with their loops, all addressed by slugs. ``parse_plant``
reads a parsed document into a validated ``Plant``, and ``export_plant`` writes
the canonical document back, so exporting and importing a Plant reproduces it,
its ID, and therefore its entity IDs.

Storage is the same document split in two: the config entry's data holds
everything except ``zones``, and each zone subentry's data holds that zone's
mapping plus its slug. Home Assistant stores both with sorted keys, so storage
lists pumps and loops as objects that carry their slugs, which keeps their order.
``to_storage`` and ``from_storage`` convert between them.

The canonical export writes every structural and timing key and omits optional
keys at their defaults: names, sensors, and settings a user left out. Lists and
small mappings are written in flow style, so ``write_plant_file`` produces the
compact form that ``docs/redesign-plan.md`` uses.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from enum import StrEnum
from typing import Any, Final
from uuid import UUID, uuid4

import yaml

from .model import (
    DEFAULT_MAX_AGE,
    DEFAULT_MIN_OFF,
    DEFAULT_MIN_ON,
    DEFAULT_MODE_DWELL,
    DEFAULT_OPENING_TIME,
    DEFAULT_OVERRUN,
    DEFAULT_POST_RUN,
    RUNS_WITH_SOURCE,
    RUNS_WITH_ZONE,
    Aggregation,
    DigitalThermostat,
    ExternalThermostat,
    Loop,
    LoopRef,
    LoopRun,
    MinFlow,
    Mode,
    Plant,
    Preset,
    Pump,
    RunKind,
    Sensor,
    Source,
    SourceModeSelect,
    SourceStrategy,
    Thermostat,
    Valve,
    Zone,
    ZoneArea,
    title_from_slug,
)

PLANT_FILE_FORMAT: Final = 2

# Keys in canonical order.
_TOP_KEYS: Final = ("hydronicus", "id", "name", "mode_dwell", "source", "pumps", "loops", "zones")
_SOURCE_KEYS: Final = ("name", "strategy", "request", "mode", "post_run", "min_on", "min_off")
_SOURCE_MODE_KEYS: Final = ("entity", "heat", "cool")
_PUMP_KEYS: Final = (
    "name",
    "switch",
    "driven_by",
    "overrun",
    "min_flow",
    "min_flow_loops",
    "supply_temperature",
)
_PLANT_LOOP_KEYS: Final = ("name", "valves", "pump", "runs", "modes", "surface_temperature")
_ZONE_LOOP_KEYS: Final = ("name", "valves", "pump", "modes", "surface_temperature")
_ZONE_KEYS: Final = (
    "name",
    "areas",
    "temperature",
    "humidity",
    "aggregation",
    "thermostat",
    "loops",
)
_VALVE_KEYS: Final = ("entity", "opening_time", "readiness")
_SENSOR_KEYS: Final = ("entity", "required", "max_age")
_AREA_KEYS: Final = ("area", "required", "max_age")
_THERMOSTAT_KEYS: Final = ("digital", "external")
_DIGITAL_KEYS: Final = (
    "target",
    "presets",
    "heat_start_delta",
    "heat_stop_delta",
    "cool_start_delta",
    "cool_stop_delta",
    "min_on",
    "min_off",
    "proportional_band",
)
_RUNS_KEYS: Final = ("with_zones",)
_LOOP_MODES: Final = (Mode.HEAT, Mode.COOL)
_DEFAULT_MODES: Final = frozenset({Mode.HEAT})
_DEFAULT_THERMOSTAT: Final = DigitalThermostat()
_SLUG_KEY: Final = "slug"

_VALVE_DOMAINS: Final = ("switch", "valve")
_SWITCH_DOMAINS: Final = ("switch",)
_SELECT_DOMAINS: Final = ("select",)
_SENSOR_DOMAINS: Final = ("sensor",)
_READINESS_DOMAINS: Final = ("binary_sensor",)
_CLIMATE_DOMAINS: Final = ("climate",)

_SLUG: Final = re.compile(r"[a-z][a-z0-9_]*")
# Home Assistant's entity ID rule: lowercase words joined by single underscores.
_ENTITY_ID: Final = re.compile(r"(?!_)[a-z0-9_]+(?<!_)\.(?!_)[a-z0-9_]+(?<!_)")
_THERMOSTAT_SHAPE: Final = (
    "A thermostat is either digital or external: {digital: {...}} or {external: climate.x}."
)


class PlantFileError(ValueError):
    """A plant file or stored Plant is not valid.

    ``path`` is the dotted path of the offending key, such as
    ``zones.living_area.loops.floor.pump``, with list items as indices. It is
    empty for errors about the whole document, and the message starts with it.
    """

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}" if path else message)


def _new_id() -> str:
    return str(uuid4())


# Reading


def parse_plant(document: object, *, new_id: Callable[[], str] = _new_id) -> Plant:
    """Return the validated Plant a parsed plant file describes.

    A file without an ``id`` gets ``new_id()``, which the export then keeps.
    Raise ``PlantFileError`` for the first problem found.
    """
    if document is None or document == "":
        raise PlantFileError("", "The plant file is empty.")
    top = _mapping(document, "", _TOP_KEYS)
    _check_format(top)
    plant = Plant(
        id=_plant_id(top["id"] if "id" in top else new_id(), "id"),
        name=_text(_required(top, "name", ""), "name"),
        mode_dwell=_number(top.get("mode_dwell", DEFAULT_MODE_DWELL), "mode_dwell"),
        source=_source(top["source"], "source") if "source" in top else None,
        pumps=tuple(
            _pump(slug, value, path) for slug, value, path in _slugs(top.get("pumps", {}), "pumps")
        ),
        loops=tuple(
            _loop(LoopRef(None, slug), value, path)
            for slug, value, path in _slugs(top.get("loops", {}), "loops")
        ),
        zones=tuple(
            _zone(slug, value, path) for slug, value, path in _slugs(top.get("zones", {}), "zones")
        ),
    )
    validate_plant(plant)
    return plant


def _check_format(top: Mapping[str, Any]) -> None:
    if "hydronicus" not in top:
        raise PlantFileError(
            "hydronicus", f"State the plant file format: hydronicus: {PLANT_FILE_FORMAT}."
        )
    value = top["hydronicus"]
    if isinstance(value, int) and not isinstance(value, bool):
        if value == PLANT_FILE_FORMAT:
            return
        if value == 1:
            raise PlantFileError(
                "hydronicus",
                "Plant file format 1 is no longer read; describe the Plant in format 2.",
            )
    raise PlantFileError(
        "hydronicus",
        f"Unsupported plant file format {value!r}; this version reads format {PLANT_FILE_FORMAT}.",
    )


def _source(value: object, path: str) -> Source:
    source = _mapping(value, path, _SOURCE_KEYS)
    return Source(
        request=_entity(
            _required(source, "request", path), _join(path, "request"), _SWITCH_DOMAINS
        ),
        strategy=_choice(
            source.get("strategy", SourceStrategy.REQUEST),
            _join(path, "strategy"),
            tuple(SourceStrategy),
        ),
        mode=_source_mode(source["mode"], _join(path, "mode")) if "mode" in source else None,
        post_run=_number(source.get("post_run", DEFAULT_POST_RUN), _join(path, "post_run")),
        min_on=_number(source.get("min_on", DEFAULT_MIN_ON), _join(path, "min_on")),
        min_off=_number(source.get("min_off", DEFAULT_MIN_OFF), _join(path, "min_off")),
        name=_name(source, path),
    )


def _source_mode(value: object, path: str) -> SourceModeSelect:
    mode = _mapping(value, path, _SOURCE_MODE_KEYS)
    entity = _entity(_required(mode, "entity", path), _join(path, "entity"), _SELECT_DOMAINS)
    heat = _text(_required(mode, "heat", path), _join(path, "heat"))
    cool = _text(_required(mode, "cool", path), _join(path, "cool"))
    if heat == cool:
        raise PlantFileError(_join(path, "cool"), "The heat and cool options must differ.")
    return SourceModeSelect(entity=entity, heat=heat, cool=cool)


def _pump(slug: str, value: object, path: str) -> Pump:
    pump = _mapping(value, path, _PUMP_KEYS)
    if ("switch" in pump) == ("driven_by" in pump):
        raise PlantFileError(path, "A pump has either a switch or driven_by: source.")
    min_flow = _choice(pump.get("min_flow", MinFlow.PATH), _join(path, "min_flow"), tuple(MinFlow))
    min_flow_loops = (
        _loop_refs(pump["min_flow_loops"], _join(path, "min_flow_loops"))
        if "min_flow_loops" in pump
        else ()
    )
    supply_temperature = (
        _entity(pump["supply_temperature"], _join(path, "supply_temperature"), _SENSOR_DOMAINS)
        if "supply_temperature" in pump
        else None
    )
    if "switch" in pump:
        return Pump(
            slug=slug,
            switch=_entity(pump["switch"], _join(path, "switch"), _SWITCH_DOMAINS),
            overrun=_number(pump.get("overrun", DEFAULT_OVERRUN), _join(path, "overrun")),
            min_flow=min_flow,
            min_flow_loops=min_flow_loops,
            supply_temperature=supply_temperature,
            name=_name(pump, path),
        )
    if pump["driven_by"] != "source":
        raise PlantFileError(
            _join(path, "driven_by"), "driven_by must be source, for a pump the source runs."
        )
    if "overrun" in pump:
        raise PlantFileError(
            _join(path, "overrun"),
            "A source-driven pump has no overrun; the source's post_run covers it.",
        )
    return Pump(
        slug=slug,
        switch=None,
        min_flow=min_flow,
        min_flow_loops=min_flow_loops,
        supply_temperature=supply_temperature,
        name=_name(pump, path),
    )


def _loop_refs(value: object, path: str) -> tuple[LoopRef, ...]:
    refs = []
    for item, item_path in _items(value, path):
        try:
            refs.append(LoopRef.parse(_text(item, item_path)))
        except ValueError:
            raise PlantFileError(item_path, "Expected a loop slug or <zone>.<loop>.") from None
    return tuple(refs)


def _loop(ref: LoopRef, value: object, path: str) -> Loop:
    plant_loop = ref.zone is None
    loop = _mapping(value, path, _PLANT_LOOP_KEYS if plant_loop else _ZONE_LOOP_KEYS)
    return Loop(
        ref=ref,
        valves=tuple(
            _valve(item, item_path) for item, item_path in _items_of(loop, "valves", path)
        ),
        pump=_text(_required(loop, "pump", path), _join(path, "pump")),
        modes=_modes(loop["modes"], _join(path, "modes")) if "modes" in loop else _DEFAULT_MODES,
        runs=_runs(_required(loop, "runs", path), _join(path, "runs"))
        if plant_loop
        else RUNS_WITH_ZONE,
        surface_temperature=(
            _entity(
                loop["surface_temperature"], _join(path, "surface_temperature"), _SENSOR_DOMAINS
            )
            if "surface_temperature" in loop
            else None
        ),
        name=_name(loop, path),
    )


def _modes(value: object, path: str) -> frozenset[Mode]:
    modes: list[Mode] = []
    for item, item_path in _items(value, path):
        mode = _choice(item, item_path, _LOOP_MODES)
        if mode in modes:
            raise PlantFileError(item_path, f"Mode {mode} is listed twice.")
        modes.append(mode)
    if not modes:
        raise PlantFileError(path, "List at least one mode.")
    return frozenset(modes)


def _runs(value: object, path: str) -> LoopRun:
    if value == RunKind.WITH_SOURCE:
        return RUNS_WITH_SOURCE
    if isinstance(value, Mapping):
        runs = _mapping(value, path, _RUNS_KEYS)
        zones_path = _join(path, "with_zones")
        return LoopRun(
            RunKind.WITH_ZONES,
            tuple(
                _text(item, item_path)
                for item, item_path in _items(_required(runs, "with_zones", path), zones_path)
            ),
        )
    raise PlantFileError(path, "Expected with_source or {with_zones: [<zone>, ...]}.")


def _valve(value: object, path: str) -> Valve:
    if not isinstance(value, Mapping):
        return Valve(_entity(value, path, _VALVE_DOMAINS))
    valve = _mapping(value, path, _VALVE_KEYS)
    return Valve(
        entity=_entity(_required(valve, "entity", path), _join(path, "entity"), _VALVE_DOMAINS),
        opening_time=_number(
            valve.get("opening_time", DEFAULT_OPENING_TIME), _join(path, "opening_time")
        ),
        readiness=(
            _entity(valve["readiness"], _join(path, "readiness"), _READINESS_DOMAINS)
            if "readiness" in valve
            else None
        ),
    )


def _zone(slug: str, value: object, path: str) -> Zone:
    zone = _mapping(value, path, _ZONE_KEYS)
    loops_path = _join(path, "loops")
    return Zone(
        slug=slug,
        loops=tuple(
            _loop(LoopRef(slug, loop_slug), loop, loop_path)
            for loop_slug, loop, loop_path in _slugs(zone.get("loops", {}), loops_path)
        ),
        areas=tuple(_area(item, item_path) for item, item_path in _items_of(zone, "areas", path)),
        temperature=tuple(
            _sensor(item, item_path) for item, item_path in _items_of(zone, "temperature", path)
        ),
        humidity=tuple(
            _sensor(item, item_path) for item, item_path in _items_of(zone, "humidity", path)
        ),
        aggregation=_choice(
            zone.get("aggregation", Aggregation.MEAN),
            _join(path, "aggregation"),
            tuple(Aggregation),
        ),
        thermostat=(
            _thermostat(zone["thermostat"], _join(path, "thermostat"))
            if "thermostat" in zone
            else _DEFAULT_THERMOSTAT
        ),
        name=_name(zone, path),
    )


def _area(value: object, path: str) -> ZoneArea:
    if not isinstance(value, Mapping):
        return ZoneArea(_area_id(value, path))
    area = _mapping(value, path, _AREA_KEYS)
    return ZoneArea(
        area=_area_id(_required(area, "area", path), _join(path, "area")),
        required=_flag(area.get("required", False), _join(path, "required")),
        max_age=_number(
            area.get("max_age", DEFAULT_MAX_AGE), _join(path, "max_age"), positive=True
        ),
    )


def _area_id(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlantFileError(path, "Expected an area ID.")
    return value


def _sensor(value: object, path: str) -> Sensor:
    if not isinstance(value, Mapping):
        return Sensor(_entity(value, path, _SENSOR_DOMAINS))
    sensor = _mapping(value, path, _SENSOR_KEYS)
    return Sensor(
        entity=_entity(_required(sensor, "entity", path), _join(path, "entity"), _SENSOR_DOMAINS),
        required=_flag(sensor.get("required", True), _join(path, "required")),
        max_age=_number(
            sensor.get("max_age", DEFAULT_MAX_AGE), _join(path, "max_age"), positive=True
        ),
    )


def _thermostat(value: object, path: str) -> Thermostat:
    if not isinstance(value, Mapping):
        raise PlantFileError(path, _THERMOSTAT_SHAPE)
    thermostat = _mapping(value, path, _THERMOSTAT_KEYS)
    if len(thermostat) != 1:
        raise PlantFileError(path, _THERMOSTAT_SHAPE)
    if "external" in thermostat:
        return ExternalThermostat(
            _entity(thermostat["external"], _join(path, "external"), _CLIMATE_DOMAINS)
        )
    path = _join(path, "digital")
    digital = _mapping(thermostat["digital"], path, _DIGITAL_KEYS)
    defaults = _DEFAULT_THERMOSTAT

    def setting(key: str, *, signed: bool = False, positive: bool = False) -> float:
        value = digital.get(key, getattr(defaults, key))
        return _number(value, _join(path, key), signed=signed, positive=positive)

    presets_path = _join(path, "presets")
    presets = _mapping(digital.get("presets", {}), presets_path, tuple(Preset))
    return DigitalThermostat(
        target=setting("target", signed=True),
        presets=tuple(
            (preset, _number(presets[preset], _join(presets_path, preset), signed=True))
            for preset in Preset
            if preset in presets
        ),
        heat_start_delta=setting("heat_start_delta"),
        heat_stop_delta=setting("heat_stop_delta"),
        cool_start_delta=setting("cool_start_delta"),
        cool_stop_delta=setting("cool_stop_delta"),
        min_on=setting("min_on"),
        min_off=setting("min_off"),
        proportional_band=setting("proportional_band", positive=True),
    )


# Scalar and collection readers


def _join(path: str, key: object) -> str:
    return f"{path}.{key}" if path else str(key)


def _mapping(value: object, path: str, keys: Sequence[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PlantFileError(path, "Expected a mapping.")
    for key in value:
        if not isinstance(key, str):
            raise PlantFileError(path, f"Key {key!r} must be text.")
        if key not in keys:
            raise PlantFileError(
                _join(path, key), f"Unknown key; expected one of: {', '.join(keys)}."
            )
    return value


def _slugs(value: object, path: str) -> Iterator[tuple[str, Any, str]]:
    """Yield the slug, value, and path of each entry of a mapping keyed by slugs."""
    if not isinstance(value, Mapping):
        raise PlantFileError(path, "Expected a mapping.")
    for key, item in value.items():
        if not isinstance(key, str):
            raise PlantFileError(path, f"Key {key!r} must be text.")
        item_path = _join(path, key)
        if not _SLUG.fullmatch(key):
            raise PlantFileError(
                item_path,
                "A slug starts with a lowercase letter and holds only lowercase letters, "
                "digits, and underscores.",
            )
        yield key, item, item_path


def _items(value: object, path: str) -> Iterator[tuple[Any, str]]:
    """Yield each item of a list with its path."""
    if not isinstance(value, list):
        raise PlantFileError(path, "Expected a list.")
    for index, item in enumerate(value):
        yield item, _join(path, index)


def _items_of(mapping: Mapping[str, Any], key: str, path: str) -> Iterator[tuple[Any, str]]:
    """Yield each item of an optional list key with its path."""
    if key in mapping:
        yield from _items(mapping[key], _join(path, key))


def _required(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        raise PlantFileError(_join(path, key), "This key is required.")
    return mapping[key]


def _name(mapping: Mapping[str, Any], path: str) -> str | None:
    return _text(mapping["name"], _join(path, "name")) if "name" in mapping else None


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlantFileError(path, "Expected non-empty text.")
    return value


def _entity(value: object, path: str, domains: Sequence[str]) -> str:
    if not isinstance(value, str) or not _ENTITY_ID.fullmatch(value):
        raise PlantFileError(path, f"Expected an entity ID, such as {domains[0]}.example.")
    if value.split(".", 1)[0] not in domains:
        raise PlantFileError(path, f"Expected an entity of the {' or '.join(domains)} domain.")
    return value


def _number(value: object, path: str, *, signed: bool = False, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PlantFileError(path, "Expected a number.")
    if not math.isfinite(value):
        raise PlantFileError(path, "Expected a finite number.")
    if positive and value <= 0:
        raise PlantFileError(path, "Must be positive.")
    if not signed and value < 0:
        raise PlantFileError(path, "Must not be negative.")
    return float(value)


def _flag(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise PlantFileError(path, "Expected true or false.")
    return value


def _choice[E: StrEnum](value: object, path: str, choices: Sequence[E]) -> E:
    for choice in choices:
        if value == choice.value:
            return choice
    raise PlantFileError(path, f"Expected one of: {', '.join(choices)}.")


def _plant_id(value: object, path: str) -> str:
    if isinstance(value, str):
        try:
            return str(UUID(value))
        except ValueError:
            pass
    raise PlantFileError(path, "Expected a UUID, such as 7c9e6679-7425-40de-944b-e07fc1f90ae7.")


# Validation


def validate_plant(plant: Plant) -> None:
    """Check the relationships between a Plant's objects.

    ``parse_plant`` calls this after it has checked every value, so a Plant built
    by hand, such as one with a zone removed, gets the same structural checks.
    Raise ``PlantFileError`` with the plant file path of the first problem.
    """
    _plant_id(plant.id, "id")
    _text(plant.name, "name")
    if plant.source is not None and plant.source.strategy is SourceStrategy.SETPOINT:
        raise PlantFileError(
            "source.strategy",
            "The setpoint strategy arrives with weather compensation; use request.",
        )
    _check_unique("pumps", (pump.slug for pump in plant.pumps), "Pump")
    _check_unique("loops", (loop.slug for loop in plant.loops), "Loop")
    _check_unique("zones", (zone.slug for zone in plant.zones), "Zone")
    for zone in plant.zones:
        _check_unique(f"zones.{zone.slug}.loops", (loop.slug for loop in zone.loops), "Loop")
    for pump in plant.pumps:
        _check_pump(plant, pump)
    for loop in plant.all_loops:
        _check_loop(plant, loop)
    for zone in plant.zones:
        _check_zone(zone)
    for loop in plant.loops:
        if loop.cools:
            for zone in plant.dew_point_zones(loop):
                _check_dew_point(zone, loop)
    _check_roles(plant)


def _check_unique(path: str, slugs: Iterator[str] | Sequence[str], kind: str) -> None:
    seen: set[str] = set()
    for slug in slugs:
        if slug in seen:
            raise PlantFileError(_join(path, slug), f"{kind} {slug} is listed twice.")
        seen.add(slug)


def _check_pump(plant: Plant, pump: Pump) -> None:
    path = f"pumps.{pump.slug}"
    loops_path = _join(path, "min_flow_loops")
    if pump.driven_by_source and plant.source is None:
        raise PlantFileError(
            _join(path, "driven_by"),
            "A source-driven pump needs a source; add one or give the pump a switch.",
        )
    if pump.min_flow_loops and not pump.driven_by_source:
        raise PlantFileError(
            loops_path,
            "Only a source-driven pump with min_flow: path names min_flow_loops; "
            "a switched pump never runs without a ready loop.",
        )
    if pump.min_flow_loops and pump.min_flow is MinFlow.GUARANTEED:
        raise PlantFileError(
            loops_path, "A pump with min_flow: guaranteed needs no min_flow_loops."
        )
    if pump.driven_by_source and pump.min_flow is MinFlow.PATH and not pump.min_flow_loops:
        raise PlantFileError(
            loops_path,
            "A source-driven pump with min_flow: path needs min_flow_loops, the loops held open "
            "while it may run, or min_flow: guaranteed when a separator protects it.",
        )
    seen: set[LoopRef] = set()
    for index, ref in enumerate(pump.min_flow_loops):
        item_path = _join(loops_path, index)
        if ref in seen:
            raise PlantFileError(item_path, f"Loop {ref} is listed twice.")
        seen.add(ref)
        try:
            loop = plant.loop(ref)
        except KeyError:
            raise PlantFileError(item_path, f"There is no loop {ref}.") from None
        if loop.pump != pump.slug:
            raise PlantFileError(
                item_path, f"Loop {ref} runs on pump {loop.pump}, not {pump.slug}."
            )


def _check_loop(plant: Plant, loop: Loop) -> None:
    path = _loop_path(loop.ref)
    try:
        pump = plant.pump(loop.pump)
    except KeyError:
        raise PlantFileError(_join(path, "pump"), f"There is no pump {loop.pump}.") from None
    _check_runs(plant, loop, _join(path, "runs"))
    modes_path = _join(path, "modes")
    if not loop.modes or not loop.modes <= set(_LOOP_MODES):
        raise PlantFileError(modes_path, "List at least one mode, heat or cool.")
    if loop.cools and pump.supply_temperature is None and loop.surface_temperature is None:
        raise PlantFileError(
            modes_path,
            "A loop that cools needs a condensation reference: a supply_temperature on pump "
            f"{pump.slug} or the loop's surface_temperature. Without one the loop is heat only.",
        )


def _check_runs(plant: Plant, loop: Loop, path: str) -> None:
    runs = loop.runs
    if loop.zone is not None:
        if runs != RUNS_WITH_ZONE:
            raise PlantFileError(path, "A zone loop runs with its zone.")
        return
    if runs.kind is RunKind.ZONE:
        raise PlantFileError(path, "A plant loop runs with_source or with_zones.")
    if runs.kind is RunKind.WITH_SOURCE:
        if plant.source is None:
            raise PlantFileError(path, "A loop that runs with the source needs a source.")
        return
    zones_path = _join(path, "with_zones")
    if not runs.zones:
        raise PlantFileError(zones_path, "List at least one zone.")
    slugs = {zone.slug for zone in plant.zones}
    seen: set[str] = set()
    for index, slug in enumerate(runs.zones):
        item_path = _join(zones_path, index)
        if slug in seen:
            raise PlantFileError(item_path, f"Zone {slug} is listed twice.")
        seen.add(slug)
        if slug not in slugs:
            raise PlantFileError(item_path, f"There is no zone {slug}.")


def _check_zone(zone: Zone) -> None:
    path = f"zones.{zone.slug}"
    _check_listed_once(_join(path, "areas"), [area.area for area in zone.areas], "Area")
    _check_listed_once(
        _join(path, "temperature"), [sensor.entity for sensor in zone.temperature], "Sensor"
    )
    _check_listed_once(
        _join(path, "humidity"), [sensor.entity for sensor in zone.humidity], "Sensor"
    )
    if isinstance(zone.thermostat, DigitalThermostat) and not zone.temperature and not zone.areas:
        raise PlantFileError(path, "A digital thermostat needs a temperature sensor or an area.")
    if zone.cools and not zone.humidity and not zone.areas:
        raise PlantFileError(
            _join(path, "humidity"),
            "A zone that cools needs a humidity sensor or an area for its dew point.",
        )
    if zone.cools and not zone.temperature and not zone.areas:
        raise PlantFileError(
            _join(path, "temperature"),
            "A zone that cools needs a temperature sensor or an area for its dew point.",
        )


def _check_dew_point(zone: Zone, loop: Loop) -> None:
    """Refuse a zone whose dew point a cooling plant loop's guard needs and cannot have."""
    path = f"zones.{zone.slug}"
    because = f"because loop {loop.slug} cools with it"
    if not zone.humidity and not zone.areas:
        raise PlantFileError(
            _join(path, "humidity"),
            f"Zone {zone.slug} needs a humidity sensor or an area for its dew point, {because}.",
        )
    if not zone.temperature and not zone.areas:
        raise PlantFileError(
            _join(path, "temperature"),
            f"Zone {zone.slug} needs a temperature sensor or an area for its dew point, {because}.",
        )


def _check_listed_once(path: str, values: Sequence[str], kind: str) -> None:
    seen: set[str] = set()
    for index, value in enumerate(values):
        if value in seen:
            raise PlantFileError(_join(path, index), f"{kind} {value} is listed twice.")
        seen.add(value)


def _check_roles(plant: Plant) -> None:
    """Refuse an output entity that has more than one role in the Plant."""
    bound: dict[str, str] = {}
    for entity, path in _output_paths(plant):
        if entity in bound:
            raise PlantFileError(
                path,
                f"{entity} is already bound at {bound[entity]}; "
                "an output has exactly one role in a Plant.",
            )
        bound[entity] = path


def _output_paths(plant: Plant) -> Iterator[tuple[str, str]]:
    if plant.source is not None:
        yield plant.source.request, "source.request"
        if plant.source.mode is not None:
            yield plant.source.mode.entity, "source.mode.entity"
    for pump in plant.pumps:
        if pump.switch is not None:
            yield pump.switch, f"pumps.{pump.slug}.switch"
    for loop in plant.all_loops:
        for index, valve in enumerate(loop.valves):
            yield valve.entity, f"{_loop_path(loop.ref)}.valves.{index}"


def _loop_path(ref: LoopRef) -> str:
    return f"loops.{ref.loop}" if ref.zone is None else f"zones.{ref.zone}.loops.{ref.loop}"


def entity_paths(plant: Plant) -> dict[str, str]:
    """Return every entity the Plant binds, inputs included, with the path of its first use.

    Adapters use it to refuse an entity that another Plant binds, or that
    Hydronicus itself provides, and to name where the file binds it.
    """
    paths: dict[str, str] = {}

    def bind(entity: str | None, path: str) -> None:
        if entity is not None:
            paths.setdefault(entity, path)

    if plant.source is not None:
        bind(plant.source.request, "source.request")
        if plant.source.mode is not None:
            bind(plant.source.mode.entity, "source.mode.entity")
    for pump in plant.pumps:
        bind(pump.switch, f"pumps.{pump.slug}.switch")
        bind(pump.supply_temperature, f"pumps.{pump.slug}.supply_temperature")
    for loop in plant.loops:
        _bind_loop(loop, bind)
    for zone in plant.zones:
        path = f"zones.{zone.slug}"
        for index, sensor in enumerate(zone.temperature):
            bind(sensor.entity, f"{path}.temperature.{index}")
        for index, sensor in enumerate(zone.humidity):
            bind(sensor.entity, f"{path}.humidity.{index}")
        if isinstance(zone.thermostat, ExternalThermostat):
            bind(zone.thermostat.entity, f"{path}.thermostat.external")
        for loop in zone.loops:
            _bind_loop(loop, bind)
    return paths


def _bind_loop(loop: Loop, bind: Callable[[str | None, str], None]) -> None:
    path = _loop_path(loop.ref)
    for index, valve in enumerate(loop.valves):
        bind(valve.entity, f"{path}.valves.{index}")
        bind(valve.readiness, f"{path}.valves.{index}.readiness")
    bind(loop.surface_temperature, f"{path}.surface_temperature")


# Paths in words

_TOP_WORDS: Final = {
    "": "The plant file",
    "hydronicus": "Plant file format",
    "id": "Plant ID",
    "name": "Plant name",
    "mode_dwell": "Mode dwell",
    "source": "Source",
    "pumps": "Pumps",
    "loops": "Plant loops",
    "zones": "Zones",
}
_KEY_WORDS: Final = {
    "request": "request switch",
    "mode": "mode select",
    "heat": "heat option",
    "cool": "cool option",
    "post_run": "post-run",
    "min_on": "minimum on time",
    "min_off": "minimum off time",
    "driven_by": "driven by",
    "min_flow": "minimum flow",
    "min_flow_loops": "min-flow loops",
    "supply_temperature": "supply temperature sensor",
    "surface_temperature": "surface temperature sensor",
    "opening_time": "opening time",
    "readiness": "readiness sensor",
    "runs": "runs with",
    "with_zones": "zones",
    "temperature": "temperature sensors",
    "humidity": "humidity sensors",
    "max_age": "maximum age",
}
# A list key and the word for one of its items, which the path numbers from 1.
_ITEM_WORDS: Final = {
    "min_flow_loops": "min-flow loop",
    "valves": "valve",
    "with_zones": "zone",
    "areas": "area",
    "temperature": "temperature sensor",
    "humidity": "humidity sensor",
}
_OBJECT_WORDS: Final = {"pumps": "Pump", "loops": "Plant loop", "zones": "Zone"}


def describe_path(document: Mapping[str, Any], path: str) -> str:
    """Return a plant file path in words, naming each object by its name.

    ``zones.living_area.loops.floor.pump`` reads ``Zone Living area, loop Floor,
    pump``, so a form can show where a problem is without the file's keys.
    """
    keys = path.split(".") if path else []
    if len(keys) <= 1:
        key = keys[0] if keys else ""
        return _TOP_WORDS.get(key, _words(key))
    parts: list[str] = []
    rest = keys
    if keys[0] in _OBJECT_WORDS:
        objects = document.get(keys[0])
        item = _named_item(objects, keys[1])
        parts.append(f"{_OBJECT_WORDS[keys[0]]} {_item_title(item, keys[1])}")
        rest = keys[2:]
        if keys[0] == "zones" and len(rest) >= 2 and rest[0] == "loops":
            loop = _named_item(item.get("loops") if isinstance(item, Mapping) else None, rest[1])
            parts.append(f"loop {_item_title(loop, rest[1])}")
            rest = rest[2:]
    else:
        parts.append(_TOP_WORDS.get(keys[0], _words(keys[0])))
        rest = keys[1:]
    index = 0
    while index < len(rest):
        key = rest[index]
        following = rest[index + 1] if index + 1 < len(rest) else None
        if key in _ITEM_WORDS and following is not None and following.isdigit():
            parts.append(f"{_ITEM_WORDS[key]} {int(following) + 1}")
            index += 2
            continue
        parts.append(_KEY_WORDS.get(key, _words(key)))
        index += 1
    return ", ".join(parts)


def _named_item(objects: object, slug: str) -> Mapping[str, Any] | None:
    if isinstance(objects, Mapping) and isinstance(item := objects.get(slug), Mapping):
        return item
    return None


def _item_title(item: Mapping[str, Any] | None, slug: str) -> str:
    name = item.get("name") if item is not None else None
    return name if isinstance(name, str) and name.strip() else title_from_slug(slug)


def _words(key: str) -> str:
    return key.replace("_", " ")


# Writing


def export_plant(plant: Plant) -> dict[str, Any]:
    """Return the canonical plant file of a Plant."""
    document: dict[str, Any] = {
        "hydronicus": PLANT_FILE_FORMAT,
        "id": plant.id,
        "name": plant.name,
        "mode_dwell": _export_number(plant.mode_dwell),
    }
    if plant.source is not None:
        document["source"] = _export_source(plant.source)
    if plant.pumps:
        document["pumps"] = {pump.slug: _export_pump(pump) for pump in plant.pumps}
    if plant.loops:
        document["loops"] = {loop.slug: _export_loop(loop) for loop in plant.loops}
    if plant.zones:
        document["zones"] = {zone.slug: _export_zone(zone) for zone in plant.zones}
    return document


def _export_number(value: float) -> int | float:
    """Write a whole number without a fraction, as a person would."""
    return int(value) if float(value).is_integer() else value


def _export_source(source: Source) -> dict[str, Any]:
    document = _named(source.name)
    document["strategy"] = str(source.strategy)
    document["request"] = source.request
    if source.mode is not None:
        document["mode"] = {
            "entity": source.mode.entity,
            "heat": source.mode.heat,
            "cool": source.mode.cool,
        }
    document["post_run"] = _export_number(source.post_run)
    document["min_on"] = _export_number(source.min_on)
    document["min_off"] = _export_number(source.min_off)
    return document


def _export_pump(pump: Pump) -> dict[str, Any]:
    document = _named(pump.name)
    if pump.switch is None:
        document["driven_by"] = "source"
    else:
        document["switch"] = pump.switch
        document["overrun"] = _export_number(pump.overrun)
    # A source-driven pump always states its minimum flow, which is a safety decision.
    if pump.driven_by_source or pump.min_flow is not MinFlow.PATH:
        document["min_flow"] = str(pump.min_flow)
    if pump.min_flow_loops:
        document["min_flow_loops"] = [str(ref) for ref in pump.min_flow_loops]
    if pump.supply_temperature is not None:
        document["supply_temperature"] = pump.supply_temperature
    return document


def _export_loop(loop: Loop) -> dict[str, Any]:
    document = _named(loop.name)
    if loop.valves:
        document["valves"] = [_export_valve(valve) for valve in loop.valves]
    document["pump"] = loop.pump
    if loop.runs.kind is RunKind.WITH_SOURCE:
        document["runs"] = str(RunKind.WITH_SOURCE)
    elif loop.runs.kind is RunKind.WITH_ZONES:
        document["runs"] = {"with_zones": list(loop.runs.zones)}
    document["modes"] = [str(mode) for mode in _LOOP_MODES if mode in loop.modes]
    if loop.surface_temperature is not None:
        document["surface_temperature"] = loop.surface_temperature
    return document


def _export_valve(valve: Valve) -> str | dict[str, Any]:
    document: dict[str, Any] = {"entity": valve.entity}
    if valve.opening_time != DEFAULT_OPENING_TIME:
        document["opening_time"] = _export_number(valve.opening_time)
    if valve.readiness is not None:
        document["readiness"] = valve.readiness
    return valve.entity if len(document) == 1 else document


def _export_zone(zone: Zone) -> dict[str, Any]:
    document = _named(zone.name)
    if zone.areas:
        document["areas"] = [
            _export_reading(area.area, "area", area.required, False, area.max_age)
            for area in zone.areas
        ]
    if zone.temperature:
        document["temperature"] = [_export_sensor(sensor) for sensor in zone.temperature]
    if zone.humidity:
        document["humidity"] = [_export_sensor(sensor) for sensor in zone.humidity]
    if zone.aggregation is not Aggregation.MEAN:
        document["aggregation"] = str(zone.aggregation)
    if zone.thermostat != _DEFAULT_THERMOSTAT:
        document["thermostat"] = _export_thermostat(zone.thermostat)
    if zone.loops:
        document["loops"] = {loop.slug: _export_loop(loop) for loop in zone.loops}
    return document


def _export_sensor(sensor: Sensor) -> str | dict[str, Any]:
    return _export_reading(sensor.entity, "entity", sensor.required, True, sensor.max_age)


def _export_reading(
    key: str, name: str, required: bool, default_required: bool, max_age: float
) -> str | dict[str, Any]:
    """Write an area or sensor as its ID, or as a mapping when a setting differs."""
    document: dict[str, Any] = {name: key}
    if required != default_required:
        document["required"] = required
    if max_age != DEFAULT_MAX_AGE:
        document["max_age"] = _export_number(max_age)
    return key if len(document) == 1 else document


def _export_thermostat(thermostat: Thermostat) -> dict[str, Any]:
    if isinstance(thermostat, ExternalThermostat):
        return {"external": thermostat.entity}
    settings: dict[str, Any] = {}
    for key in _DIGITAL_KEYS:
        value = getattr(thermostat, key)
        if value == getattr(_DEFAULT_THERMOSTAT, key):
            continue
        if key == "presets":
            settings[key] = {str(preset): _export_number(target) for preset, target in value}
        else:
            settings[key] = _export_number(value)
    return {"digital": settings}


def _named(name: str | None) -> dict[str, Any]:
    return {} if name is None else {"name": name}


# Storage


# The mappings keyed by slugs whose order the user chose. Home Assistant stores a
# config entry with sorted keys, so storage lists their objects, each with its slug.
_LISTED_KEYS: Final = ("pumps", "loops")


def to_storage(plant: Plant) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Split a Plant into its config entry data and its zone subentry data by slug.

    Pumps, plant loops, and each zone's loops are stored as lists of objects
    that carry their slug, as zone subentries do, so their order survives Home
    Assistant sorting the keys of what it stores.
    """
    entry_data = export_plant(plant)
    zones: dict[str, dict[str, Any]] = entry_data.pop("zones", {})
    return _listed(entry_data), {
        slug: {_SLUG_KEY: slug, **_listed(zone)} for slug, zone in zones.items()
    }


def _listed(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: [{_SLUG_KEY: slug, **item} for slug, item in value.items()]
        if key in _LISTED_KEYS
        else value
        for key, value in document.items()
    }


def plant_file_from_storage(
    entry_data: Mapping[str, Any], zones: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Return the plant file stored as config entry data and zone subentry data, unvalidated.

    ``zones`` maps each zone subentry's slug, its unique ID, to its data. Raise
    ``PlantFileError`` when the stored data does not have the storage's shape.
    """
    if "zones" in entry_data:
        raise PlantFileError("zones", "Zones are stored in their subentries, not the entry data.")
    if "id" not in entry_data:
        raise PlantFileError("id", "A stored Plant keeps its ID.")
    documents: dict[str, Any] = {}
    for slug, data in zones.items():
        path = _join("zones", slug)
        if not isinstance(data, Mapping):
            raise PlantFileError(path, "Expected a mapping.")
        if data.get(_SLUG_KEY) != slug:
            raise PlantFileError(
                _join(path, _SLUG_KEY),
                f"The subentry of zone {slug} holds the slug {data.get(_SLUG_KEY)!r}.",
            )
        documents[slug] = _unlisted(
            {key: value for key, value in data.items() if key != _SLUG_KEY}, path
        )
    return {**_unlisted(entry_data, ""), "zones": documents}


def _unlisted(data: Mapping[str, Any], path: str) -> dict[str, Any]:
    """Return stored data with each list of objects as a mapping by slug, in list order."""
    document = dict(data)
    for key in _LISTED_KEYS:
        if key not in document:
            continue
        key_path = _join(path, key)
        if not isinstance(document[key], list):
            raise PlantFileError(key_path, "Expected a list.")
        table: dict[str, Any] = {}
        for item, item_path in _items(document[key], key_path):
            slug = item.get(_SLUG_KEY) if isinstance(item, Mapping) else None
            if not isinstance(slug, str):
                raise PlantFileError(_join(item_path, _SLUG_KEY), "A stored object keeps its slug.")
            if slug in table:
                raise PlantFileError(_join(key_path, slug), f"Slug {slug} is stored twice.")
            table[slug] = {name: value for name, value in item.items() if name != _SLUG_KEY}
        document[key] = table
    return document


def from_storage(entry_data: Mapping[str, Any], zones: Mapping[str, Mapping[str, Any]]) -> Plant:
    """Return the validated Plant stored as config entry data and zone subentry data.

    ``zones`` maps each zone subentry's slug, its unique ID, to its data.
    """
    return parse_plant(plant_file_from_storage(entry_data, zones))


# YAML


class _Dumper(yaml.SafeDumper):
    """Write block mappings, and flow lists and small mappings, without aliases."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


class _FlowMapping(dict[str, Any]):
    """A mapping written on one line."""


# Mappings under these keys are written on one line.
_FLOW_MAPPINGS: Final = frozenset({"mode", "runs", "thermostat"})
_MAP_TAG: Final = "tag:yaml.org,2002:map"
_SEQ_TAG: Final = "tag:yaml.org,2002:seq"
# Never fold a long line.
_UNLIMITED_WIDTH: Final = 1 << 20

_Dumper.add_representer(
    dict, lambda dumper, data: dumper.represent_mapping(_MAP_TAG, data, flow_style=False)
)
_Dumper.add_representer(
    _FlowMapping, lambda dumper, data: dumper.represent_mapping(_MAP_TAG, data, flow_style=True)
)
_Dumper.add_representer(
    list, lambda dumper, data: dumper.represent_sequence(_SEQ_TAG, data, flow_style=True)
)


def _styled(value: Any, key: object = None) -> Any:
    if isinstance(value, Mapping):
        styled = {item_key: _styled(item, item_key) for item_key, item in value.items()}
        return _FlowMapping(styled) if key in _FLOW_MAPPINGS else styled
    if isinstance(value, list | tuple):
        return [_styled(item) for item in value]
    return value


def dump_yaml(document: Mapping[str, Any]) -> str:
    """Render a plant file as YAML in the canonical style."""
    return str(
        yaml.dump(
            _styled(document),
            Dumper=_Dumper,
            sort_keys=False,
            allow_unicode=True,
            width=_UNLIMITED_WIDTH,
        )
    )


class _Loader(yaml.SafeLoader):
    """Read YAML safely and refuse a mapping that repeats a key."""


def _construct_mapping(loader: _Loader, node: Any) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    keys: set[Any] = set()
    for key_node, _value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            repeated = key in keys
        except TypeError:
            continue
        if repeated:
            raise yaml.constructor.ConstructorError(
                "while reading a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        keys.add(key)
    return dict(loader.construct_mapping(node, deep=True))


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_yaml(text: str) -> Any:
    """Parse plant file text; raise ``PlantFileError`` when it is not valid YAML."""
    try:
        # _Loader is a SafeLoader, which builds only plain data.
        return yaml.load(text, Loader=_Loader)
    except yaml.YAMLError as error:
        raise PlantFileError("", f"The plant file is not valid YAML: {error}") from error


def read_plant_file(text: str, *, new_id: Callable[[], str] = _new_id) -> Plant:
    """Return the validated Plant that plant file text describes."""
    return parse_plant(load_yaml(text), new_id=new_id)


def write_plant_file(plant: Plant) -> str:
    """Return the canonical plant file text of a Plant."""
    return dump_yaml(export_plant(plant))
