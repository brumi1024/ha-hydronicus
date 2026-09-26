"""Plant file documents as the flows edit them.

A flow holds the whole plant file as plain data. Each form reads its values
from the document and writes them back into a copy, and keeps every setting it
does not show: a valve's readiness sensor, a sensor's maximum age, or a digital
thermostat's deltas survive an edit of the zone. The flows then check the copy
as a whole Plant before they keep it.

Slugs are made from names when an object is created and never change; a name
is stored only when it reads differently from its slug.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from copy import deepcopy
from typing import Any, Final
from uuid import uuid4

from homeassistant.util import slugify

from ..core.model import (
    DEFAULT_MIN_OFF,
    DEFAULT_MIN_ON,
    DEFAULT_MODE_DWELL,
    DEFAULT_OPENING_TIME,
    DEFAULT_OVERRUN,
    DEFAULT_POST_RUN,
    DEFAULT_SOURCE_TITLE,
    LoopRef,
    MinFlow,
    Mode,
    Plant,
    Preset,
    RunKind,
    title_from_slug,
)
from ..core.plant_file import PLANT_FILE_FORMAT, export_plant

type Document = dict[str, Any]

# The pick option that adds a new pump or loop. A slug never holds a hyphen, and
# the value is a valid translation key, which translates the option's label.
NEW: Final = "add-new"
DEFAULT_PLANT_NAME: Final = "Home"
DEFAULT_LOOP_NAME: Final = "Loop"
_SLUG: Final = re.compile(r"[a-z][a-z0-9_]*")
_MODES: Final = (Mode.HEAT.value, Mode.COOL.value)
_STRUCTURE: Final = ("name", "mode_dwell", "source", "pumps", "loops")
_STRUCTURE_WORDS: Final = {
    "name": "name",
    "mode_dwell": "mode dwell",
    "source": "source",
    "pumps": "pumps",
    "loops": "plant loops",
}


def new_document() -> Document:
    """Return the document of a new Plant, with its ID."""
    return {"hydronicus": PLANT_FILE_FORMAT, "id": str(uuid4()), "name": DEFAULT_PLANT_NAME}


def new_slug(name: str, taken: Collection[str], fallback: str) -> str:
    """Return a slug for a new object named ``name`` that no object in ``taken`` has."""
    base = slugify(name) if name.strip() else ""
    if base == "unknown" or not base:
        base = fallback
    elif not _SLUG.fullmatch(base):
        base = f"{fallback}_{base}"
    slug, number = base, 2
    while slug in taken:
        slug, number = f"{base}_{number}", number + 1
    return slug


def title(item: object, slug: str) -> str:
    """Return an object's name, or its slug in words."""
    name = item.get("name") if isinstance(item, Mapping) else None
    return name if isinstance(name, str) and name.strip() else title_from_slug(slug)


def _named(name: str, slug: str) -> dict[str, Any]:
    name = name.strip()
    return {"name": name} if name and name != title_from_slug(slug) else {}


def _mapping(document: Mapping[str, Any], key: str) -> dict[str, Any]:
    """Return a mapping under a key, or an empty one when there is none."""
    value = document.get(key)
    return value if isinstance(value, dict) else {}


def _entity(item: object, key: str = "entity") -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, Mapping) and isinstance(value := item.get(key), str):
        return value
    return None


def _entities(items: object, key: str = "entity") -> list[str]:
    if not isinstance(items, list):
        return []
    return [entity for item in items if (entity := _entity(item, key)) is not None]


def _kept(items: object, chosen: Iterable[str], key: str = "entity") -> list[Any]:
    """Return the chosen entities or areas, each with its stored settings kept."""
    stored = {}
    if isinstance(items, list):
        stored = {entity: item for item in items if (entity := _entity(item, key)) is not None}
    return [deepcopy(stored.get(value, value)) for value in dict.fromkeys(chosen)]


def _put(target: dict[str, Any], key: str, value: Any) -> None:
    """Set a key, or drop it when the value is empty."""
    if value in (None, "", [], {}):
        target.pop(key, None)
    else:
        target[key] = value


def zones(document: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(document, "zones")


def pumps(document: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(document, "pumps")


def plant_loops(document: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(document, "loops")


# The Plant and its source


def plant_values(document: Mapping[str, Any]) -> dict[str, Any]:
    source = _mapping(document, "source")
    mode = _mapping(source, "mode")
    return {
        "name": document.get("name") or DEFAULT_PLANT_NAME,
        "source_name": source.get("name", DEFAULT_SOURCE_TITLE),
        "request": source.get("request"),
        "mode_select": mode.get("entity"),
        "timing": {
            "mode_dwell": document.get("mode_dwell", DEFAULT_MODE_DWELL),
            "post_run": source.get("post_run", DEFAULT_POST_RUN),
            "min_on": source.get("min_on", DEFAULT_MIN_ON),
            "min_off": source.get("min_off", DEFAULT_MIN_OFF),
        },
    }


def with_plant(document: Mapping[str, Any], values: Mapping[str, Any]) -> Document:
    """Return the document with the Plant's name, timing, and source from the form.

    The source's mode select is left out here; the source mode step adds it
    with its options.
    """
    result = deepcopy(dict(document))
    old = _mapping(document, "source")
    # Without the timing section the stored timing stays.
    timing = {
        "mode_dwell": document.get("mode_dwell", DEFAULT_MODE_DWELL),
        "post_run": old.get("post_run", DEFAULT_POST_RUN),
        "min_on": old.get("min_on", DEFAULT_MIN_ON),
        "min_off": old.get("min_off", DEFAULT_MIN_OFF),
        **(values.get("timing") or {}),
    }
    result["name"] = str(values.get("name", "")).strip()
    result["mode_dwell"] = timing["mode_dwell"]
    request = values.get("request")
    if not request:
        result.pop("source", None)
        return result
    source: dict[str, Any] = {}
    name = str(values.get("source_name") or "").strip()
    if name and name != DEFAULT_SOURCE_TITLE:
        source["name"] = name
    source["strategy"] = old.get("strategy", "request")
    source["request"] = request
    if isinstance(mode := old.get("mode"), Mapping) and mode.get("entity") == values.get(
        "mode_select"
    ):
        source["mode"] = deepcopy(dict(mode))
    source["post_run"] = timing["post_run"]
    source["min_on"] = timing["min_on"]
    source["min_off"] = timing["min_off"]
    result["source"] = source
    return result


def mode_values(document: Mapping[str, Any], entity: str) -> dict[str, Any]:
    mode = _mapping(_mapping(document, "source"), "mode")
    if mode.get("entity") != entity:
        return {}
    return {"heat": mode.get("heat"), "cool": mode.get("cool")}


def with_mode(document: Mapping[str, Any], entity: str, heat: str, cool: str) -> Document:
    result = deepcopy(dict(document))
    source = result.setdefault("source", {})
    source["mode"] = {"entity": entity, "heat": heat, "cool": cool}
    # Keep the canonical key order: the mode follows the request.
    result["source"] = {
        key: source[key]
        for key in ("name", "strategy", "request", "mode", "post_run", "min_on", "min_off")
        if key in source
    }
    return result


# Pumps


def pump_values(document: Mapping[str, Any], slug: str | None) -> dict[str, Any]:
    if slug is None:
        return {"overrun": DEFAULT_OVERRUN, "min_flow": MinFlow.PATH.value}
    pump = pumps(document).get(slug, {})
    return {
        "name": title(pump, slug),
        "switch": pump.get("switch"),
        "overrun": pump.get("overrun", DEFAULT_OVERRUN),
        "min_flow": pump.get("min_flow", MinFlow.PATH.value),
        "min_flow_loops": list(pump.get("min_flow_loops", [])),
        "supply_temperature": pump.get("supply_temperature"),
    }


def with_pump(
    document: Mapping[str, Any], slug: str | None, values: Mapping[str, Any]
) -> tuple[Document, str]:
    """Return the document with a new or edited pump, and the pump's slug.

    A pump without a switch is driven by the source. Min-flow loops count only
    for a source-driven pump that needs a path, so they are dropped otherwise.
    """
    result = deepcopy(dict(document))
    table = result.setdefault("pumps", {})
    name = str(values.get("name", ""))
    if slug is None:
        slug = new_slug(name, table, "pump")
    pump: dict[str, Any] = _named(name, slug)
    min_flow = values.get("min_flow", MinFlow.PATH.value)
    if switch := values.get("switch"):
        pump["switch"] = switch
        pump["overrun"] = values.get("overrun", DEFAULT_OVERRUN)
    else:
        pump["driven_by"] = "source"
    pump["min_flow"] = min_flow
    if not switch and min_flow == MinFlow.PATH.value:
        _put(pump, "min_flow_loops", list(values.get("min_flow_loops") or []))
    _put(pump, "supply_temperature", values.get("supply_temperature"))
    table[slug] = pump
    return result, slug


def with_min_flow(
    document: Mapping[str, Any], slug: str, loops: list[str], *, guaranteed: bool
) -> Document:
    result = deepcopy(dict(document))
    pump = result["pumps"][slug]
    if guaranteed:
        pump["min_flow"] = MinFlow.GUARANTEED.value
        pump.pop("min_flow_loops", None)
    else:
        pump["min_flow"] = MinFlow.PATH.value
        _put(pump, "min_flow_loops", loops)
    return result


def without_pump(document: Mapping[str, Any], slug: str) -> Document:
    result = deepcopy(dict(document))
    pumps(result).pop(slug, None)
    if not result.get("pumps"):
        result.pop("pumps", None)
    return result


def pending_min_flow(document: Mapping[str, Any], slugs: Iterable[str]) -> Document:
    """Return the document as if the pumps whose min-flow loops are still to come had a separator.

    The flows ask for a source-driven pump's min-flow loops only once the loops
    exist, so until then the rest of the Plant is checked without them.
    """
    result = deepcopy(dict(document))
    for slug in slugs:
        pump = pumps(result).get(slug)
        if isinstance(pump, dict):
            pump["min_flow"] = MinFlow.GUARANTEED.value
            pump.pop("min_flow_loops", None)
    return result


def needs_min_flow_loops(document: Mapping[str, Any], slug: str) -> bool:
    pump = pumps(document).get(slug, {})
    return "switch" not in pump and pump.get("min_flow", MinFlow.PATH.value) == MinFlow.PATH.value


def unresolved_min_flow(document: Mapping[str, Any]) -> list[str]:
    """Return the pumps that need min-flow loops and do not name only loops of their own.

    A new source-driven pump has no loops, and a removed loop or one moved to
    another pump leaves a reference behind; the flows ask for these pumps'
    min-flow loops at the end, once the loops exist.
    """
    unresolved = []
    for slug, pump in pumps(document).items():
        if needs_min_flow_loops(document, slug):
            refs = pump.get("min_flow_loops")
            if not refs or own_min_flow_loops(document, slug) != refs:
                unresolved.append(slug)
    return unresolved


def own_min_flow_loops(document: Mapping[str, Any], slug: str) -> list[str]:
    """Return the min-flow loops a pump names that are still loops of that pump."""
    refs = pumps(document).get(slug, {}).get("min_flow_loops")
    if not isinstance(refs, list):
        return []
    own = loop_refs(document, slug)
    return [ref for ref in refs if isinstance(ref, str) and ref in own]


# Loops


def loop_refs(document: Mapping[str, Any], pump: str | None = None) -> dict[str, str]:
    """Return every loop's reference with its label, or only the loops of one pump."""
    refs: dict[str, str] = {}
    for zone_slug, zone in zones(document).items():
        loops = zone.get("loops") if isinstance(zone, Mapping) else None
        for slug, loop in (loops if isinstance(loops, Mapping) else {}).items():
            if pump is None or loop.get("pump") == pump:
                refs[str(LoopRef(zone_slug, slug))] = (
                    f"{title(zone, zone_slug)} / {title(loop, slug)}"
                )
    for slug, loop in plant_loops(document).items():
        if pump is None or loop.get("pump") == pump:
            refs[slug] = f"{title(loop, slug)} (plant loop)"
    return refs


def _loop_table(document: Document, zone: str | None) -> dict[str, Any]:
    owner = document if zone is None else document.setdefault("zones", {})[zone]
    loops = owner.setdefault("loops", {})
    assert isinstance(loops, dict)
    return loops


def loop_values(document: Mapping[str, Any], zone: str | None, slug: str | None) -> dict[str, Any]:
    if slug is None:
        return {"modes": [Mode.HEAT.value], "opening_time": DEFAULT_OPENING_TIME}
    owner = document if zone is None else zones(document).get(zone, {})
    loop = _mapping(owner, "loops").get(slug, {})
    valves = loop.get("valves", [])
    opening = [
        item["opening_time"]
        for item in valves
        if isinstance(item, Mapping) and "opening_time" in item
    ]
    runs = loop.get("runs")
    values = {
        "name": title(loop, slug),
        "valves": _entities(valves),
        "pump": loop.get("pump"),
        "modes": [mode for mode in _MODES if mode in loop.get("modes", [Mode.HEAT.value])],
        "surface_temperature": loop.get("surface_temperature"),
        "opening_time": opening[0] if opening else DEFAULT_OPENING_TIME,
    }
    if zone is None:
        values["runs"] = (
            RunKind.WITH_ZONES.value if isinstance(runs, Mapping) else RunKind.WITH_SOURCE.value
        )
        values["with_zones"] = list(runs.get("with_zones", [])) if isinstance(runs, Mapping) else []
    return values


def with_loop(
    document: Mapping[str, Any], zone: str | None, slug: str | None, values: Mapping[str, Any]
) -> tuple[Document, str]:
    """Return the document with a new or edited loop of a zone, or a plant loop, and its slug."""
    result = deepcopy(dict(document))
    table = _loop_table(result, zone)
    name = str(values.get("name") or "").strip()
    old = table.get(slug, {}) if slug is not None else {}
    if slug is None:
        slug = new_slug(name or DEFAULT_LOOP_NAME, table, "loop")
    # A loop left unnamed reads as its slug, such as Loop 2 for loop_2.
    loop: dict[str, Any] = _named(name, slug)
    opening_time = values.get("opening_time", DEFAULT_OPENING_TIME)
    valves = []
    for item in _kept(old.get("valves"), values.get("valves") or []):
        valve = dict(item) if isinstance(item, Mapping) else {"entity": item}
        _put(valve, "opening_time", None if opening_time == DEFAULT_OPENING_TIME else opening_time)
        valves.append(valve["entity"] if len(valve) == 1 else valve)
    _put(loop, "valves", valves)
    loop["pump"] = values.get("pump")
    if zone is None:
        if values.get("runs") == RunKind.WITH_ZONES.value:
            loop["runs"] = {"with_zones": list(values.get("with_zones") or [])}
        else:
            loop["runs"] = RunKind.WITH_SOURCE.value
    modes = values.get("modes") or [Mode.HEAT.value]
    loop["modes"] = [mode for mode in _MODES if mode in modes]
    _put(loop, "surface_temperature", values.get("surface_temperature"))
    table[slug] = loop
    return result, slug


def without_loop(document: Mapping[str, Any], zone: str | None, slug: str) -> Document:
    result = deepcopy(dict(document))
    owner = result if zone is None else result["zones"][zone]
    loops = owner.get("loops", {})
    loops.pop(slug, None)
    if not loops:
        owner.pop("loops", None)
    return result


def loops_using(document: Mapping[str, Any], pump: str) -> list[str]:
    """Return the labels of the loops a pump drives."""
    return list(loop_refs(document, pump).values())


# Zones


def zone_values(document: Mapping[str, Any], slug: str | None) -> dict[str, Any]:
    if slug is None:
        return {"aggregation": "mean"}
    zone = zones(document).get(slug, {})
    thermostat = _mapping(zone, "thermostat")
    presets = _mapping(_mapping(thermostat, "digital"), "presets")
    return {
        "name": title(zone, slug),
        "areas": _entities(zone.get("areas"), "area"),
        "temperature": _entities(zone.get("temperature")),
        "humidity": _entities(zone.get("humidity")),
        "aggregation": zone.get("aggregation", "mean"),
        "thermostat": thermostat.get("external"),
        "presets": {preset.value: presets[preset.value] for preset in Preset if preset in presets},
    }


def with_zone(
    document: Mapping[str, Any], slug: str | None, values: Mapping[str, Any], name: str
) -> tuple[Document, str]:
    """Return the document with a new or edited zone named ``name``, and the zone's slug."""
    result = deepcopy(dict(document))
    table = result.setdefault("zones", {})
    old = table.get(slug, {}) if slug is not None else {}
    if slug is None:
        slug = new_slug(name, table, "zone")
    zone: dict[str, Any] = _named(name, slug)
    _put(zone, "areas", _kept(old.get("areas"), values.get("areas") or [], "area"))
    _put(zone, "temperature", _kept(old.get("temperature"), values.get("temperature") or []))
    _put(zone, "humidity", _kept(old.get("humidity"), values.get("humidity") or []))
    if (aggregation := values.get("aggregation", "mean")) != "mean":
        zone["aggregation"] = aggregation
    if external := values.get("thermostat"):
        zone["thermostat"] = {"external": external}
    else:
        digital = dict(_mapping(_mapping(old, "thermostat"), "digital"))
        presets = values.get("presets") or {}
        _put(
            digital,
            "presets",
            {
                preset.value: presets[preset.value]
                for preset in Preset
                if presets.get(preset.value) is not None
            },
        )
        if digital:
            zone["thermostat"] = {"digital": digital}
    if "loops" in old:
        zone["loops"] = deepcopy(old["loops"])
    table[slug] = zone
    return result, slug


# Changes


def change_summary(
    old: Mapping[str, Any], old_outputs: Collection[str] | None, plant: Plant
) -> str:
    """Describe what storing ``plant`` over the stored document ``old`` changes.

    It names the zones added, removed, and changed, the outputs added and
    removed, and which Plant settings change, not each field.
    """
    data = export_plant(plant)
    new_zones = zones(data)
    old_zones = {slug: zone for slug, zone in zones(old).items() if isinstance(zone, dict)}
    lines: list[str] = []

    def names(slugs: Iterable[str], table: Mapping[str, Any]) -> str:
        return ", ".join(title(table[slug], slug) for slug in slugs)

    added = [slug for slug in new_zones if slug not in old_zones]
    removed = [slug for slug in old_zones if slug not in new_zones]
    changed = [
        slug for slug in new_zones if slug in old_zones and new_zones[slug] != old_zones[slug]
    ]
    if added:
        lines.append(f"Zones added: {names(added, new_zones)}")
    if removed:
        lines.append(f"Zones removed: {names(removed, old_zones)}")
    if changed:
        lines.append(f"Zones changed: {names(changed, new_zones)}")
    settings = [_STRUCTURE_WORDS[key] for key in _STRUCTURE if data.get(key) != old.get(key)]
    if settings:
        lines.append(f"Plant settings changed: {', '.join(settings)}")
    outputs = set(plant.outputs())
    if old_outputs is None:
        lines.append("The stored Plant is not valid, so every output is listed as new.")
        old_outputs = ()
    if new := sorted(outputs - set(old_outputs)):
        lines.append(f"Outputs added: {', '.join(new)}")
    if gone := sorted(set(old_outputs) - outputs):
        lines.append(f"Outputs removed: {', '.join(gone)}")
    return "\n".join(f"- {line}" for line in lines) if lines else "Nothing changes."
