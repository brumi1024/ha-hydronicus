"""The forms of the flows, and plant file problems shown on them.

``check`` reads a document as a whole Plant with the plant file rules, and
refuses an entity that Hydronicus provides or an output that another Plant binds
(decision 18). A problem is shown on the form field its path belongs to, and
otherwise at the form's base with its path in words.

Forms take the values to show from one mapping: the document's values when a
form opens, and the submitted values when it opens again with an error, so a
field the user cleared stays empty.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import voluptuous as vol
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from ..areas import (
    area_names,
    area_review_warnings,
    covered_area_ids,
    listed,
    resolve_area_sensors,
    zone_name_for_areas,
)
from ..bindings import output_bound_elsewhere, own_entity
from ..const import DOMAIN
from ..core.model import (
    ExternalThermostat,
    OutputRole,
    Plant,
    Preset,
    RunKind,
)
from ..core.plant_file import PlantFileError, describe_path, parse_plant
from .documents import NEW, Document, pumps, title, zones

_SECONDS: Final = UnitOfTime.SECONDS
_CELSIUS: Final = UnitOfTemperature.CELSIUS
_VALVE_DOMAINS: Final = ["switch", "valve"]


# Where each form shows a problem, by its path below the object the form edits.
PLANT_FIELDS: Final = {
    "name": "name",
    "source.name": "source_name",
    "source.request": "request",
    "source.mode": "mode_select",
}
MODE_FIELDS: Final = {"source.mode.heat": "heat", "source.mode.cool": "cool", "source.mode": "heat"}
PUMP_FIELDS: Final = {
    "name": "name",
    "switch": "switch",
    "driven_by": "switch",
    "overrun": "overrun",
    "min_flow": "min_flow",
    "min_flow_loops": "min_flow_loops",
    "supply_temperature": "supply_temperature",
}
LOOP_FIELDS: Final = {
    "name": "name",
    "valves": "valves",
    "pump": "pump",
    "runs": "runs",
    "runs.with_zones": "with_zones",
    "modes": "modes",
    "surface_temperature": "surface_temperature",
}
# A zone's own problem, a missing temperature reading, shows on its sensors.
ZONE_FIELDS: Final = {
    "": "temperature",
    "name": "name",
    "areas": "areas",
    "temperature": "temperature",
    "humidity": "humidity",
    "aggregation": "aggregation",
    "thermostat": "thermostat",
}


def loop_path(zone: str | None, slug: str) -> str:
    return f"loops.{slug}" if zone is None else f"zones.{zone}.loops.{slug}"


def shown(fields: Mapping[str, str], schema: vol.Schema) -> dict[str, str]:
    """Keep the paths whose field the form shows."""
    names = {str(key) for key in schema.schema}
    return {path: name for path, name in fields.items() if name in names}


def zone_name(hass: HomeAssistant, values: Mapping[str, Any]) -> str | None:
    """Return the name a zone form gives, or the name of its one area or its floor."""
    name = str(values.get("name") or "").strip()
    return name or zone_name_for_areas(hass, list(values.get("areas") or []))


@dataclass(frozen=True, slots=True)
class Checked:
    """A checked document: its Plant, or the errors and placeholders a form shows."""

    plant: Plant | None
    errors: dict[str, str] = field(default_factory=dict)
    placeholders: dict[str, str] = field(default_factory=dict)


def check(
    hass: HomeAssistant,
    document: Document,
    *,
    prefix: str = "",
    fields: Mapping[str, str] | None = None,
    entry_id: str | None = None,
) -> Checked:
    """Read ``document`` as a Plant, and map its first problem onto a form.

    ``fields`` maps a path below ``prefix``, such as ``valves`` below a loop's
    path, to the form field that shows a problem there.
    """
    try:
        plant = parse_plant(document)
    except PlantFileError as error:
        return _problem(document, error.path, "invalid", {"problem": error.message}, prefix, fields)
    if (own := own_entity(hass, plant)) is not None:
        path, entity_id = own
        return _problem(document, path, "own_entity", {"entity_id": entity_id}, prefix, fields)
    if (shared := output_bound_elsewhere(hass, plant, entry_id)) is not None:
        return _problem(
            document,
            shared.path,
            "output_bound_elsewhere",
            {"entity_id": shared.entity_id, "other_plant": shared.other_plant},
            prefix,
            fields,
        )
    return Checked(plant)


def _problem(
    document: Document,
    path: str,
    key: str,
    placeholders: dict[str, str],
    prefix: str,
    fields: Mapping[str, str] | None,
) -> Checked:
    placeholders = {"where": describe_path(document, path), **placeholders}
    target = problem_field(path, prefix, fields or {})
    if key == "invalid":
        key = "invalid_value" if target != "base" else "invalid_plant"
    return Checked(None, {target: key}, placeholders)


def problem_field(path: str, prefix: str, fields: Mapping[str, str]) -> str:
    """Return the form field that shows a problem at ``path``, or ``base``."""
    if prefix:
        if path != prefix and not path.startswith(f"{prefix}."):
            return "base"
        path = path[len(prefix) + 1 :]
    if not path:
        # A problem of the object itself.
        return fields.get("", "base")
    keys = path.split(".")
    # The longest known path wins, so source.mode.cool maps before source.mode.
    for length in range(len(keys), 0, -1):
        if (target := fields.get(".".join(keys[:length]))) is not None:
            return target
    return "base"


# Selectors


def _own_entities(hass: HomeAssistant) -> set[str]:
    registry = er.async_get(hass)
    return {entry.entity_id for entry in registry.entities.values() if entry.platform == DOMAIN}


def entity(
    hass: HomeAssistant,
    domains: str | list[str],
    *,
    multiple: bool = False,
    shown: Iterable[str] = (),
) -> selector.EntitySelector:
    """Pick entities of some domains, hiding Hydronicus's own unless already chosen."""
    config = selector.EntitySelectorConfig(domain=domains, multiple=multiple)
    if excluded := _own_entities(hass) - set(shown):
        config["exclude_entities"] = sorted(excluded)
    return selector.EntitySelector(config)


def seconds() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, step=1, unit_of_measurement=_SECONDS, mode=selector.NumberSelectorMode.BOX
        )
    )


def celsius() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=5,
            max=35,
            step=0.5,
            unit_of_measurement=_CELSIUS,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def choice(
    options: Sequence[str] | Mapping[str, str],
    *,
    key: str | None = None,
    multiple: bool = False,
    listed_: bool = False,
    custom: bool = False,
) -> selector.SelectSelector:
    """Choose from options: translated by ``key``, or labelled by a mapping."""
    config = selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value=value, label=label) for value, label in options.items()
        ]
        if isinstance(options, Mapping)
        else list(options),
        multiple=multiple,
        custom_value=custom,
        mode=selector.SelectSelectorMode.LIST if listed_ else selector.SelectSelectorMode.DROPDOWN,
    )
    if key is not None:
        config["translation_key"] = key
    return selector.SelectSelector(config)


def _text() -> selector.TextSelector:
    return selector.TextSelector()


def optional(name: str, values: Mapping[str, Any]) -> vol.Optional:
    """An optional field that shows its value and can be cleared."""
    value = values.get(name)
    if value in (None, "", []):
        return vol.Optional(name)
    return vol.Optional(name, description={"suggested_value": value})


def _default(name: str, values: Mapping[str, Any], fallback: Any) -> vol.Optional:
    """An optional field that is never empty; it starts at its value or the fallback."""
    value = values.get(name)
    return vol.Optional(name, default=fallback if value in (None, "") else value)


def _list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


# Forms


def plant_schema(hass: HomeAssistant, values: Mapping[str, Any]) -> vol.Schema:
    timing = values.get("timing") or {}
    return vol.Schema(
        {
            optional("name", values): _text(),
            optional("source_name", values): _text(),
            optional("request", values): entity(
                hass, "switch", shown=_list([values.get("request")])
            ),
            optional("mode_select", values): entity(
                hass, "select", shown=_list([values.get("mode_select")])
            ),
            vol.Optional("timing"): section(
                vol.Schema(
                    {
                        _default("mode_dwell", timing, 3600): seconds(),
                        _default("post_run", timing, 180): seconds(),
                        _default("min_on", timing, 600): seconds(),
                        _default("min_off", timing, 600): seconds(),
                    }
                ),
                {"collapsed": True},
            ),
        }
    )


def mode_options(hass: HomeAssistant, entity_id: str) -> list[str]:
    """Return the options a select entity offers now, or none when it has no state."""
    state = hass.states.get(entity_id)
    options = state.attributes.get("options") if state is not None else None
    return [str(option) for option in options] if isinstance(options, list) else []


def mode_schema(hass: HomeAssistant, entity_id: str, values: Mapping[str, Any]) -> vol.Schema:
    options = mode_options(hass, entity_id)
    return vol.Schema(
        {
            optional("heat", values): choice(options, custom=True),
            optional("cool", values): choice(options, custom=True),
        }
    )


def pump_schema(
    hass: HomeAssistant,
    values: Mapping[str, Any],
    *,
    loops: Mapping[str, str] | None = None,
    add_another: bool = False,
    removable: bool = False,
) -> vol.Schema:
    """The pump form; ``loops`` offers min-flow loops, which guided setup asks for later."""
    schema: dict[Any, Any] = {
        optional("name", values): _text(),
        optional("switch", values): entity(hass, "switch", shown=_list([values.get("switch")])),
        _default("overrun", values, 180): seconds(),
        _default("min_flow", values, "path"): choice(["path", "guaranteed"], key="min_flow"),
    }
    if loops:
        schema[optional("min_flow_loops", values)] = choice(loops, multiple=True, listed_=True)
    schema[optional("supply_temperature", values)] = entity(
        hass, "sensor", shown=_list([values.get("supply_temperature")])
    )
    if add_another:
        schema[vol.Optional("add_another", default=False)] = selector.BooleanSelector()
    if removable:
        schema[vol.Optional("remove", default=False)] = selector.BooleanSelector()
    return vol.Schema(schema)


def area_selector(hass: HomeAssistant, shown: Iterable[str] = ()) -> selector.SelectSelector:
    """The Home Assistant areas as a checkbox list, with chosen areas that no longer exist.

    Home Assistant's area selector shows its label only below the chosen areas,
    so a checkbox list reads better, and a missing area stays listed by the name
    it last had so the user sees what to clear.
    """
    options = dict(area_names(hass))
    resolution = resolve_area_sensors(hass, shown)
    for area_id in resolution.missing_area_ids:
        options[area_id] = f"{resolution.name(area_id)} (no longer exists)"
    return choice(options, multiple=True, listed_=True)


def zone_schema(
    hass: HomeAssistant, values: Mapping[str, Any], *, areas: bool = True
) -> vol.Schema:
    presets = values.get("presets") or {}
    schema: dict[Any, Any] = {optional("name", values): _text()}
    if areas:
        schema[optional("areas", values)] = area_selector(hass, _list(values.get("areas")))
    schema.update(
        {
            optional("temperature", values): entity(
                hass, "sensor", multiple=True, shown=_list(values.get("temperature"))
            ),
            optional("humidity", values): entity(
                hass, "sensor", multiple=True, shown=_list(values.get("humidity"))
            ),
            _default("aggregation", values, "mean"): choice(
                ["mean", "min", "max"], key="aggregation"
            ),
            optional("thermostat", values): entity(
                hass, "climate", shown=_list([values.get("thermostat")])
            ),
            vol.Optional("presets"): section(
                vol.Schema({optional(preset.value, presets): celsius() for preset in Preset}),
                {"collapsed": True},
            ),
        }
    )
    return vol.Schema(schema)


def loop_schema(
    hass: HomeAssistant,
    values: Mapping[str, Any],
    pumps: Mapping[str, str],
    *,
    zones: Mapping[str, str] | None = None,
    removable: bool = False,
) -> vol.Schema:
    """The loop form; ``zones`` makes it a plant loop, which runs with the source or zones."""
    schema: dict[Any, Any] = {
        optional("name", values): _text(),
        optional("valves", values): entity(
            hass, _VALVE_DOMAINS, multiple=True, shown=_list(values.get("valves"))
        ),
        optional("pump", values): choice(pumps),
    }
    if zones is not None:
        schema[_default("runs", values, RunKind.WITH_SOURCE.value)] = choice(
            [RunKind.WITH_SOURCE.value, RunKind.WITH_ZONES.value], key="runs"
        )
        schema[optional("with_zones", values)] = choice(zones, multiple=True, listed_=True)
    schema.update(
        {
            _default("modes", values, ["heat"]): choice(
                ["heat", "cool"], key="modes", multiple=True, listed_=True
            ),
            optional("surface_temperature", values): entity(
                hass, "sensor", shown=_list([values.get("surface_temperature")])
            ),
            _default("opening_time", values, 180): seconds(),
        }
    )
    if removable:
        schema[vol.Optional("remove", default=False)] = selector.BooleanSelector()
    return vol.Schema(schema)


def min_flow_schema(loops: Mapping[str, str], values: Mapping[str, Any]) -> vol.Schema:
    schema: dict[Any, Any] = {}
    if loops:
        schema[optional("min_flow_loops", values)] = choice(loops, multiple=True, listed_=True)
    schema[vol.Optional("guaranteed", default=False)] = selector.BooleanSelector()
    return vol.Schema(schema)


def areas_schema(hass: HomeAssistant, values: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema({optional("areas", values): area_selector(hass)})


def pick_schema(name: str, items: Mapping[str, str], new_label: str) -> vol.Schema:
    return vol.Schema({vol.Required(name): choice({**items, NEW: new_label})})


def plant_file_schema(text: str = "") -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("plant_file", default=text): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            )
        }
    )


def arm_schema(labels: Mapping[str, str], armed: Iterable[str] = ()) -> vol.Schema:
    chosen = [entity_id for entity_id in labels if entity_id in set(armed)]
    key = (
        vol.Optional("outputs", description={"suggested_value": chosen})
        if chosen
        else vol.Optional("outputs")
    )
    return vol.Schema({key: choice(labels, multiple=True, listed_=True)})


# Descriptions


def pump_labels(document: Document) -> dict[str, str]:
    """Each pump's slug with how the loop form names it."""
    labels = {}
    for slug, pump in pumps(document).items():
        how = f"switch {pump['switch']}" if "switch" in pump else "driven by the source"
        labels[slug] = f"{title(pump, slug)} ({how})"
    return labels


def output_labels(plant: Plant) -> dict[str, str]:
    """Every output of a Plant with its role, in the order the Plant commands them."""
    valves = {valve.entity: loop for loop in plant.all_loops for valve in loop.valves}
    labels: dict[str, str] = {}
    for entity_id, role in plant.outputs().items():
        if role is OutputRole.SOURCE_REQUEST:
            what = "Source request switch"
        elif role is OutputRole.SOURCE_MODE:
            what = "Source mode select"
        elif role is OutputRole.PUMP:
            pump = next(pump for pump in plant.pumps if pump.switch == entity_id)
            what = f"Pump {pump.title}"
        else:
            loop = valves[entity_id]
            owner = (
                f"{plant.zone(loop.zone).title} / {loop.title}"
                if loop.zone is not None
                else f"{loop.title} (plant loop)"
            )
            what = f"Valve of {owner}"
        labels[entity_id] = f"{what}: {entity_id}"
    return labels


def plant_summary(hass: HomeAssistant, plant: Plant) -> str:
    """Describe a Plant for a review: its source, pumps, zones, and plant loops."""
    lines = [f"Plant {plant.name}"]
    source = plant.source
    if source is None:
        lines.append("- No source: valves open and switched pumps run on demand.")
    else:
        mode = (
            f", mode select {source.mode.entity} ({source.mode.heat}, {source.mode.cool})"
            if source.mode is not None
            else ""
        )
        lines.append(f"- Source {source.title}: request switch {source.request}{mode}")
    for pump in plant.pumps:
        how = f"switch {pump.switch}" if pump.switch else "driven by the source"
        if pump.min_flow_loops:
            flow = "holds open " + listed([_loop_label(plant, ref) for ref in pump.min_flow_loops])
        elif pump.min_flow.value == "guaranteed":
            flow = "a separator guarantees its flow"
        else:
            flow = "runs only with a ready loop"
        lines.append(f"- Pump {pump.title}: {how}, {flow}")
    resolution = resolve_area_sensors(hass, covered_area_ids(plant))
    for zone in plant.zones:
        areas = [resolution.name(area.area) for area in zone.areas]
        covering = (
            f", covering {'area' if len(areas) == 1 else 'areas'} {listed(areas)}" if areas else ""
        )
        thermostat = (
            f"thermostat {zone.thermostat.entity}"
            if isinstance(zone.thermostat, ExternalThermostat)
            else "digital thermostat"
        )
        loops = [_loop_line(plant, loop.ref) for loop in zone.loops]
        lines.append(
            f"- Zone {zone.title}{covering}, {thermostat}"
            + (f"; loops: {'; '.join(loops)}" if loops else "; no loop of its own")
        )
    for loop in plant.loops:
        runs = (
            "with the source"
            if loop.runs.kind is RunKind.WITH_SOURCE
            else "with zones " + listed([plant.zone(slug).title for slug in loop.runs.zones])
        )
        lines.append(f"- Plant loop {_loop_line(plant, loop.ref)}, runs {runs}")
    lines.append(f"- Outputs: {len(plant.outputs())}")
    return "\n".join(lines)


def _loop_label(plant: Plant, ref: Any) -> str:
    loop = plant.loop(ref)
    return loop.title if loop.zone is None else f"{plant.zone(loop.zone).title} / {loop.title}"


def _loop_line(plant: Plant, ref: Any) -> str:
    loop = plant.loop(ref)
    modes = " and ".join(
        mode.value for mode in sorted(loop.modes, key=lambda mode: mode.value != "heat")
    )
    valves = len(loop.valves)
    valve_words = "no valve" if valves == 0 else f"{valves} valve" + ("s" if valves > 1 else "")
    return f"{loop.title} ({modes}, pump {plant.pump(loop.pump).title}, {valve_words})"


def review_warnings(hass: HomeAssistant, plant: Plant) -> str:
    """List what may not work as intended; none of it stops the Plant from being saved."""
    warnings = [warning.message for warning in area_review_warnings(hass, plant)]
    served = {slug for loop in plant.loops for slug in loop.runs.zones}
    for zone in plant.zones:
        if not zone.loops and zone.slug not in served:
            warnings.append(
                f"Zone {zone.title} has no loop of its own and no plant loop runs with it, so "
                "its demand moves no water."
            )
    for pump in plant.pumps:
        if not plant.pump_loops(pump.slug):
            warnings.append(f"Pump {pump.title} drives no loop.")
    return "\n".join(f"- {warning}" for warning in warnings) or "- None"


def zone_names(document: Document) -> dict[str, str]:
    return {slug: title(zone, slug) for slug, zone in zones(document).items()}
