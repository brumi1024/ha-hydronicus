"""The format 2 plant file: parse, validate, export, and the storage split."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest
import yaml
from hydronicus_core.model import (
    Aggregation,
    DigitalThermostat,
    ExternalThermostat,
    LoopRef,
    LoopRun,
    MinFlow,
    Mode,
    OutputRole,
    Plant,
    Pump,
    RunKind,
    Sensor,
    Valve,
    ZoneArea,
)
from hydronicus_core.plant_file import (
    PLANT_FILE_FORMAT,
    PlantFileError,
    describe_path,
    dump_yaml,
    entity_paths,
    export_plant,
    from_storage,
    load_yaml,
    parse_plant,
    read_plant_file,
    to_storage,
    validate_plant,
    write_plant_file,
)

from tests.core.plant_files import REFERENCE_PLANT, TRIAL_PLANTS

PLANT_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
_COMMENT = re.compile(r"\s+#.*$", re.MULTILINE)
_ENTITY_ID = re.compile(r"[a-z_]+\.[a-z0-9_]+")

# A canonical plant file that uses every long form and every optional key.
EVERY_KEY = """\
hydronicus: 2
id: 00000000-0000-4000-8000-000000000001
name: Workshop
mode_dwell: 1800
source:
  strategy: request
  request: switch.boiler_request
  post_run: 60
  min_on: 300
  min_off: 240.5
pumps:
  primary:
    name: Primary circulator
    driven_by: source
    min_flow: guaranteed
    supply_temperature: sensor.primary_supply
  secondary:
    switch: switch.secondary_pump
    overrun: 0
    min_flow: guaranteed
loops:
  garage:
    name: Garage radiators
    valves: [{entity: valve.garage, opening_time: 60, readiness: binary_sensor.garage_open}]
    pump: secondary
    runs: {with_zones: [office, lab]}
    modes: [heat, cool]
    surface_temperature: sensor.garage_floor
zones:
  office:
    name: Front office
    areas: [office, {area: hall, required: true, max_age: 600}]
    temperature: [sensor.office, {entity: sensor.office_desk, required: false, max_age: 900}]
    humidity: [sensor.office_humidity]
    aggregation: max
    thermostat: {digital: {target: 20.5, presets: {eco: 18}, heat_start_delta: 0.5, \
heat_stop_delta: 0.2, cool_start_delta: 0.4, cool_stop_delta: 0.3, min_on: 300, min_off: 600, \
proportional_band: 2}}
    loops:
      radiators:
        valves: [switch.office_valve_a, {entity: switch.office_valve_b, opening_time: 240}]
        pump: primary
        modes: [cool]
  lab:
    temperature: [sensor.lab]
    humidity: [sensor.lab_humidity]
    thermostat: {external: climate.lab}
    loops:
      bench:
        pump: secondary
        modes: [heat]
"""


def _strings(value: Any) -> list[str]:
    """Return every text key and value of a parsed document."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.items() for part in item for text in _strings(part)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def reference_text() -> str:
    return REFERENCE_PLANT.read_text(encoding="utf-8")


def reference_document() -> dict[str, Any]:
    return load_yaml(reference_text())


def reference_plant() -> Plant:
    return read_plant_file(reference_text())


# Round trips


def test_the_reference_plant_imports_and_exports_byte_stable() -> None:
    """Export writes the reference plant exactly as the plan writes it, less its comments."""
    exported = write_plant_file(reference_plant())

    assert exported == _COMMENT.sub("", reference_text())
    assert write_plant_file(read_plant_file(exported)) == exported


def test_a_plant_file_with_every_key_is_its_own_export() -> None:
    assert write_plant_file(read_plant_file(EVERY_KEY)) == EVERY_KEY


def test_a_plant_file_with_every_key_decodes_every_key() -> None:
    plant = read_plant_file(EVERY_KEY)

    assert plant.id == "00000000-0000-4000-8000-000000000001"
    assert plant.mode_dwell == 1800
    assert plant.source is not None
    assert plant.source.name is None
    assert plant.source.title == "Heat source"
    assert plant.source.mode is None
    assert (plant.source.post_run, plant.source.min_on, plant.source.min_off) == (60, 300, 240.5)
    assert plant.pump("primary") == Pump(
        slug="primary",
        switch=None,
        min_flow=MinFlow.GUARANTEED,
        supply_temperature="sensor.primary_supply",
        name="Primary circulator",
    )
    assert plant.pump("secondary").overrun == 0
    garage = plant.loop(LoopRef(None, "garage"))
    assert garage.valves == (
        Valve("valve.garage", opening_time=60, readiness="binary_sensor.garage_open"),
    )
    assert garage.runs == LoopRun(RunKind.WITH_ZONES, ("office", "lab"))
    assert garage.modes == frozenset({Mode.HEAT, Mode.COOL})
    assert garage.surface_temperature == "sensor.garage_floor"
    office = plant.zone("office")
    assert office.title == "Front office"
    assert office.areas == (ZoneArea("office"), ZoneArea("hall", required=True, max_age=600))
    assert office.temperature == (
        Sensor("sensor.office"),
        Sensor("sensor.office_desk", required=False, max_age=900),
    )
    assert office.humidity == (Sensor("sensor.office_humidity"),)
    assert office.aggregation is Aggregation.MAX
    assert isinstance(office.thermostat, DigitalThermostat)
    assert office.thermostat.target == 20.5
    assert office.thermostat.proportional_band == 2
    radiators = plant.loop(LoopRef("office", "radiators"))
    assert radiators.runs == LoopRun(RunKind.ZONE)
    assert radiators.valves[1] == Valve("switch.office_valve_b", opening_time=240)
    assert plant.zone("lab").thermostat == ExternalThermostat("climate.lab")
    assert plant.loop(LoopRef("lab", "bench")).valves == ()


@pytest.mark.parametrize("converted", list(TRIAL_PLANTS), ids=lambda path: path.name)
def test_the_trial_kit_converts_to_format_2(converted: Any) -> None:
    """The converted trial kit binds exactly the entities of the shipped trial kit."""
    plant = read_plant_file(converted.read_text(encoding="utf-8"), new_id=lambda: PLANT_ID)
    shipped = {
        text
        for text in _strings(yaml.safe_load(TRIAL_PLANTS[converted].read_text(encoding="utf-8")))
        if _ENTITY_ID.fullmatch(text)
    }

    assert set(entity_paths(plant)) == shipped
    assert [zone.slug for zone in plant.zones] == ["living_room", "bedroom"]
    assert all(loop.pump == "circulation_pump" for loop in plant.all_loops)
    exported = write_plant_file(plant)
    assert read_plant_file(exported) == plant
    assert write_plant_file(read_plant_file(exported)) == exported


def test_a_missing_id_is_assigned_once_and_then_kept() -> None:
    document = reference_document()
    del document["id"]

    plant = parse_plant(document, new_id=lambda: PLANT_ID.upper())

    assert plant.id == PLANT_ID
    assert export_plant(plant)["id"] == PLANT_ID


def test_defaults() -> None:
    plant = parse_plant(
        {
            "hydronicus": 2,
            "name": "Minimal",
            "pumps": {"pump": {"switch": "switch.pump"}},
            "zones": {"room": {"areas": ["room"], "loops": {"loop": {"pump": "pump"}}}},
        }
    )

    assert plant.mode_dwell == 3600
    assert plant.source is None
    assert plant.pump("pump").overrun == 180
    assert plant.pump("pump").min_flow is MinFlow.PATH
    room = plant.zone("room")
    assert room.thermostat == DigitalThermostat()
    assert room.aggregation is Aggregation.MEAN
    assert room.loops[0].modes == frozenset({Mode.HEAT})
    assert room.loops[0].valves == ()
    assert export_plant(plant) == {
        "hydronicus": 2,
        "id": plant.id,
        "name": "Minimal",
        "mode_dwell": 3600,
        "pumps": {"pump": {"switch": "switch.pump", "overrun": 180}},
        "zones": {
            "room": {"areas": ["room"], "loops": {"loop": {"pump": "pump", "modes": ["heat"]}}}
        },
    }


def test_an_empty_plant_is_valid() -> None:
    plant = parse_plant({"hydronicus": 2, "id": PLANT_ID, "name": "Empty"})

    assert (plant.pumps, plant.loops, plant.zones) == ((), (), ())
    assert write_plant_file(plant) == (
        f"hydronicus: 2\nid: {PLANT_ID}\nname: Empty\nmode_dwell: 3600\n"
    )


# The shapes the reference plant needs


def test_loops_without_a_valve_or_without_a_switched_pump_validate() -> None:
    plant = reference_plant()

    towel_dryer = plant.loop(LoopRef(None, "towel_dryer"))
    assert towel_dryer.valves == ()
    assert towel_dryer.runs == LoopRun(RunKind.WITH_SOURCE)
    ceiling = plant.loop(LoopRef("living_area", "ceiling"))
    assert plant.pump(ceiling.pump).switch is None
    assert plant.pump("heat_pump").min_flow_loops == (LoopRef("living_area", "ceiling"),)
    validate_plant(plant)


def test_a_zone_loop_with_neither_a_valve_nor_a_switched_pump_validates() -> None:
    document = reference_document()
    del document["zones"]["basement"]["loops"]["ceiling"]["valves"]

    plant = parse_plant(document)

    assert plant.loop(LoopRef("basement", "ceiling")).valves == ()


def test_a_guaranteed_source_driven_pump_needs_no_min_flow_loops() -> None:
    document = reference_document()
    document["pumps"]["heat_pump"]["min_flow"] = "guaranteed"
    del document["pumps"]["heat_pump"]["min_flow_loops"]

    assert parse_plant(document).pump("heat_pump").min_flow is MinFlow.GUARANTEED


def test_a_plant_loop_min_flow_path_and_a_loop_surface_sensor_count() -> None:
    document = reference_document()
    document["pumps"]["heat_pump"]["min_flow_loops"] = ["heat_pump_bypass"]
    del document["pumps"]["heat_pump"]["supply_temperature"]
    document["loops"]["heat_pump_bypass"] = {
        "pump": "heat_pump",
        "runs": "with_source",
        "modes": ["heat"],
    }
    for zone in ("basement", "bedroom_area", "living_area"):
        document["zones"][zone]["loops"]["ceiling"]["surface_temperature"] = (
            f"sensor.{zone}_ceiling"
        )

    plant = parse_plant(document)

    assert plant.pump("heat_pump").min_flow_loops == (LoopRef(None, "heat_pump_bypass"),)


def test_a_plant_without_a_source_opens_valves_and_runs_switched_pumps() -> None:
    plant = read_plant_file(next(iter(TRIAL_PLANTS)).read_text(encoding="utf-8"))

    assert plant.source is None
    assert set(plant.outputs().values()) == {OutputRole.PUMP, OutputRole.VALVE}
    validate_plant(plant)


def test_a_zone_with_an_external_thermostat_needs_no_temperature_sensor() -> None:
    document = reference_document()
    basement = document["zones"]["basement"]
    del basement["areas"]
    basement["thermostat"] = {"external": "climate.basement"}
    basement["loops"]["ceiling"]["modes"] = ["heat"]

    assert parse_plant(document).zone("basement").thermostat == ExternalThermostat(
        "climate.basement"
    )


# Rejections


def _without_source(document: dict[str, Any]) -> None:
    del document["source"]
    del document["loops"]


def _set(path: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def mutate(document: dict[str, Any]) -> None:
        *parents, last = path.split(".")
        target: Any = document
        for key in parents:
            target = target[int(key)] if isinstance(target, list) else target[key]
        if isinstance(target, list):
            target[int(last)] = value
        else:
            target[last] = value

    return mutate


def _delete(path: str) -> Callable[[dict[str, Any]], None]:
    def mutate(document: dict[str, Any]) -> None:
        *parents, last = path.split(".")
        target: Any = document
        for key in parents:
            target = target[key]
        del target[last]

    return mutate


def _both(*mutations: Callable[[dict[str, Any]], None]) -> Callable[[dict[str, Any]], None]:
    def mutate(document: dict[str, Any]) -> None:
        for mutation in mutations:
            mutation(document)

    return mutate


CEILING = "zones.basement.loops.ceiling"
FLOOR = "zones.living_area.loops.floor"
HEAT_PUMP = "pumps.heat_pump"

REJECTIONS: list[tuple[str, Callable[[dict[str, Any]], None], str, str]] = [
    # The whole file
    ("format missing", _delete("hydronicus"), "hydronicus", "format"),
    ("format 1", _set("hydronicus", 1), "hydronicus", "format 1"),
    ("format as text", _set("hydronicus", "2"), "hydronicus", "format"),
    ("unknown top-level key", _set("valves", {}), "valves", "Unknown key"),
    ("invalid id", _set("id", "home"), "id", "UUID"),
    ("missing name", _delete("name"), "name", "required"),
    ("blank name", _set("name", "  "), "name", "text"),
    ("name as a number", _set("name", 7), "name", "text"),
    ("negative mode dwell", _set("mode_dwell", -1), "mode_dwell", "negative"),
    ("boolean mode dwell", _set("mode_dwell", True), "mode_dwell", "number"),
    ("infinite mode dwell", _set("mode_dwell", float("inf")), "mode_dwell", "number"),
    ("pumps as a list", _set("pumps", ["floor"]), "pumps", "mapping"),
    ("invalid pump slug", _set("pumps.Floor", {"switch": "switch.x"}), "pumps.Floor", "slug"),
    ("numeric pump slug", _set("pumps", {1: {"switch": "switch.x"}}), "pumps", "text"),
    # Source
    ("unknown source key", _set("source.flow", 35), "source.flow", "Unknown key"),
    ("source without request", _delete("source.request"), "source.request", "required"),
    ("request in the wrong domain", _set("source.request", "light.x"), "source.request", "switch"),
    ("malformed request", _set("source.request", "switch"), "source.request", "entity ID"),
    ("setpoint strategy", _set("source.strategy", "setpoint"), "source.strategy", "setpoint"),
    ("unknown strategy", _set("source.strategy", "curve"), "source.strategy", "request"),
    ("mode without cool", _delete("source.mode.cool"), "source.mode.cool", "required"),
    ("same mode options", _set("source.mode.cool", "Heat"), "source.mode.cool", "differ"),
    ("mode option as bool", _set("source.mode.heat", True), "source.mode.heat", "text"),
    (
        "mode in the wrong domain",
        _set("source.mode.entity", "switch.x"),
        "source.mode.entity",
        "select",
    ),
    # Pumps
    (
        "pump with switch and driven_by",
        _set("pumps.floor.driven_by", "source"),
        "pumps.floor",
        "either",
    ),
    ("pump with neither", _delete("pumps.floor.switch"), "pumps.floor", "either"),
    (
        "driven by a boiler",
        _set(f"{HEAT_PUMP}.driven_by", "boiler"),
        f"{HEAT_PUMP}.driven_by",
        "source",
    ),
    ("driven pump overrun", _set(f"{HEAT_PUMP}.overrun", 60), f"{HEAT_PUMP}.overrun", "post_run"),
    ("driven pump without a source", _without_source, f"{HEAT_PUMP}.driven_by", "source"),
    ("unknown min flow", _set(f"{HEAT_PUMP}.min_flow", "some"), f"{HEAT_PUMP}.min_flow", "path"),
    (
        "path pump without min-flow loops",
        _delete(f"{HEAT_PUMP}.min_flow_loops"),
        f"{HEAT_PUMP}.min_flow_loops",
        "min_flow_loops",
    ),
    (
        "min-flow loop missing",
        _set(f"{HEAT_PUMP}.min_flow_loops", ["attic.ceiling"]),
        f"{HEAT_PUMP}.min_flow_loops.0",
        "no loop",
    ),
    (
        "min-flow loop of another pump",
        _set(f"{HEAT_PUMP}.min_flow_loops", ["living_area.floor"]),
        f"{HEAT_PUMP}.min_flow_loops.0",
        "pump floor",
    ),
    (
        "malformed min-flow loop",
        _set(f"{HEAT_PUMP}.min_flow_loops", ["a.b.c"]),
        f"{HEAT_PUMP}.min_flow_loops.0",
        "<zone>.<loop>",
    ),
    (
        "duplicate min-flow loop",
        _set(f"{HEAT_PUMP}.min_flow_loops", ["basement.ceiling", "basement.ceiling"]),
        f"{HEAT_PUMP}.min_flow_loops.1",
        "twice",
    ),
    (
        "min-flow loops on a switched pump",
        _set("pumps.floor.min_flow_loops", ["living_area.floor"]),
        "pumps.floor.min_flow_loops",
        "source-driven",
    ),
    (
        "min-flow loops on a guaranteed pump",
        _set(f"{HEAT_PUMP}.min_flow", "guaranteed"),
        f"{HEAT_PUMP}.min_flow_loops",
        "guaranteed",
    ),
    ("negative overrun", _set("pumps.floor.overrun", -5), "pumps.floor.overrun", "negative"),
    (
        "pump switch in the wrong domain",
        _set("pumps.floor.switch", "valve.x"),
        "pumps.floor.switch",
        "switch",
    ),
    # Plant loops
    (
        "plant loop without runs",
        _delete("loops.towel_dryer.runs"),
        "loops.towel_dryer.runs",
        "required",
    ),
    (
        "unknown runs",
        _set("loops.towel_dryer.runs", "always"),
        "loops.towel_dryer.runs",
        "with_source",
    ),
    (
        "runs mapping with an unknown key",
        _set("loops.towel_dryer.runs", {"with_zone": ["basement"]}),
        "loops.towel_dryer.runs.with_zone",
        "Unknown key",
    ),
    (
        "runs with a missing zone",
        _set("loops.towel_dryer.runs", {"with_zones": ["attic"]}),
        "loops.towel_dryer.runs.with_zones.0",
        "no zone",
    ),
    (
        "runs with no zones",
        _set("loops.towel_dryer.runs", {"with_zones": []}),
        "loops.towel_dryer.runs.with_zones",
        "at least one",
    ),
    (
        "runs with a zone twice",
        _set("loops.towel_dryer.runs", {"with_zones": ["basement", "basement"]}),
        "loops.towel_dryer.runs.with_zones.1",
        "twice",
    ),
    (
        "plant loop with a missing pump",
        _set("loops.towel_dryer.pump", "boiler"),
        "loops.towel_dryer.pump",
        "no pump",
    ),
    # Zone loops
    ("zone loop without a pump", _delete(f"{FLOOR}.pump"), f"{FLOOR}.pump", "required"),
    ("zone loop with a missing pump", _set(f"{FLOOR}.pump", "attic"), f"{FLOOR}.pump", "no pump"),
    (
        "zone loop with runs",
        _set(f"{CEILING}.runs", "with_source"),
        f"{CEILING}.runs",
        "Unknown key",
    ),
    ("unknown zone loop key", _set(f"{FLOOR}.pumps", "floor"), f"{FLOOR}.pumps", "Unknown key"),
    (
        "invalid zone loop slug",
        _set("zones.basement.loops.Ceiling", {"pump": "floor"}),
        "zones.basement.loops.Ceiling",
        "slug",
    ),
    ("no modes", _set(f"{FLOOR}.modes", []), f"{FLOOR}.modes", "at least one"),
    ("unknown mode", _set(f"{FLOOR}.modes", ["off"]), f"{FLOOR}.modes.0", "heat"),
    ("mode twice", _set(f"{FLOOR}.modes", ["heat", "heat"]), f"{FLOOR}.modes.1", "twice"),
    ("modes as text", _set(f"{FLOOR}.modes", "heat"), f"{FLOOR}.modes", "list"),
    (
        "cooling without a condensation reference",
        _delete(f"{HEAT_PUMP}.supply_temperature"),
        f"{CEILING}.modes",
        "condensation reference",
    ),
    (
        "cooling a loop of a pump without a supply sensor",
        _set(f"{FLOOR}.modes", ["heat", "cool"]),
        f"{FLOOR}.modes",
        "condensation reference",
    ),
    (
        "supply sensor in the wrong domain",
        _set(f"{HEAT_PUMP}.supply_temperature", "switch.x"),
        f"{HEAT_PUMP}.supply_temperature",
        "sensor",
    ),
    # Valves and roles
    ("valves as text", _set(f"{FLOOR}.valves", "switch.x"), f"{FLOOR}.valves", "list"),
    (
        "valve in the wrong domain",
        _set(f"{FLOOR}.valves.0", "light.x"),
        f"{FLOOR}.valves.0",
        "switch",
    ),
    ("valve as a number", _set(f"{FLOOR}.valves.0", 3), f"{FLOOR}.valves.0", "entity ID"),
    (
        "valve mapping without entity",
        _set(f"{FLOOR}.valves.0", {"opening_time": 60}),
        f"{FLOOR}.valves.0.entity",
        "required",
    ),
    (
        "valve mapping with an unknown key",
        _set(f"{FLOOR}.valves.0", {"entity": "switch.x", "opening": 60}),
        f"{FLOOR}.valves.0.opening",
        "Unknown key",
    ),
    (
        "readiness in the wrong domain",
        _set(f"{FLOOR}.valves.0", {"entity": "switch.x", "readiness": "sensor.x"}),
        f"{FLOOR}.valves.0.readiness",
        "binary_sensor",
    ),
    (
        "valve that is also a pump",
        _set(f"{FLOOR}.valves.0", "switch.home_underfloor_heating_pump"),
        f"{FLOOR}.valves.0",
        "pumps.floor.switch",
    ),
    (
        "valve in two loops",
        _set(f"{FLOOR}.valves.0", "switch.home_basement_ceiling_heating_valve"),
        f"{FLOOR}.valves.0",
        f"{CEILING}.valves.0",
    ),
    (
        "valve twice in one loop",
        _set(f"{FLOOR}.valves", ["switch.a", "switch.a"]),
        f"{FLOOR}.valves.1",
        f"{FLOOR}.valves.0",
    ),
    (
        "pump that is the source request",
        _set("pumps.floor.switch", "switch.heat_pump_heat_request"),
        "pumps.floor.switch",
        "source.request",
    ),
    # Zones
    ("unknown zone key", _set("zones.basement.rooms", []), "zones.basement.rooms", "Unknown key"),
    ("blank zone name", _set("zones.basement.name", ""), "zones.basement.name", "text"),
    ("areas as text", _set("zones.basement.areas", "basement"), "zones.basement.areas", "list"),
    (
        "area twice",
        _set("zones.basement.areas", ["basement", "basement"]),
        "zones.basement.areas.1",
        "twice",
    ),
    ("area as a number", _set("zones.basement.areas", [4]), "zones.basement.areas.0", "area ID"),
    (
        "area mapping with an unknown key",
        _set("zones.basement.areas", [{"area": "basement", "weight": 2}]),
        "zones.basement.areas.0.weight",
        "Unknown key",
    ),
    (
        "sensor required as text",
        _set("zones.basement.temperature", [{"entity": "sensor.a", "required": "yes"}]),
        "zones.basement.temperature.0.required",
        "true or false",
    ),
    (
        "sensor max age zero",
        _set("zones.basement.temperature", [{"entity": "sensor.a", "max_age": 0}]),
        "zones.basement.temperature.0.max_age",
        "positive",
    ),
    (
        "sensor twice",
        _set("zones.basement.humidity", ["sensor.a", "sensor.a"]),
        "zones.basement.humidity.1",
        "twice",
    ),
    (
        "median aggregation",
        _set("zones.basement.aggregation", "median"),
        "zones.basement.aggregation",
        "mean",
    ),
    (
        "digital thermostat without a temperature source",
        _delete("zones.basement.areas"),
        "zones.basement",
        "temperature sensor or an area",
    ),
    (
        "cooling zone without a humidity source",
        _both(_delete("zones.basement.areas"), _set("zones.basement.temperature", ["sensor.b"])),
        "zones.basement.humidity",
        "humidity sensor or an area",
    ),
    (
        "cooling zone without a temperature source",
        _both(
            _delete("zones.basement.areas"),
            _set("zones.basement.humidity", ["sensor.b_rh"]),
            _set("zones.basement.thermostat", {"external": "climate.basement"}),
        ),
        "zones.basement.temperature",
        "temperature sensor or an area",
    ),
    (
        "zone a cooling plant loop runs with, without a humidity source",
        _both(
            _set("zones.basement.loops.ceiling.modes", ["heat"]),
            _delete("zones.basement.areas"),
            _set("zones.basement.temperature", ["sensor.b"]),
            _set(
                "loops.hall",
                {
                    "valves": ["switch.hall_valve"],
                    "pump": "heat_pump",
                    "runs": {"with_zones": ["bedroom_area", "basement"]},
                    "modes": ["heat", "cool"],
                },
            ),
        ),
        "zones.basement.humidity",
        "because loop hall cools with it",
    ),
    (
        "zone a cooling plant loop runs with, without a temperature source",
        _both(
            _set("zones.basement.loops.ceiling.modes", ["heat"]),
            _delete("zones.basement.areas"),
            _set("zones.basement.humidity", ["sensor.b_rh"]),
            _set("zones.basement.thermostat", {"external": "climate.basement"}),
            _set(
                "loops.hall",
                {"pump": "heat_pump", "runs": {"with_zones": ["basement"]}, "modes": ["cool"]},
            ),
        ),
        "zones.basement.temperature",
        "Zone basement needs a temperature sensor or an area",
    ),
    (
        "zone a cooling plant loop runs with the source, without a humidity source",
        _both(
            _set("zones.basement.loops.ceiling.modes", ["heat"]),
            _delete("zones.basement.areas"),
            _set("zones.basement.temperature", ["sensor.b"]),
            _set("loops.towel_dryer.modes", ["heat", "cool"]),
            _set("pumps.towel_dryer.supply_temperature", "sensor.towel_supply"),
        ),
        "zones.basement.humidity",
        "because loop towel_dryer cools with it",
    ),
    (
        "thermostat with both kinds",
        _set("zones.basement.thermostat", {"digital": {}, "external": "climate.x"}),
        "zones.basement.thermostat",
        "digital or external",
    ),
    (
        "thermostat as text",
        _set("zones.basement.thermostat", "climate.x"),
        "zones.basement.thermostat",
        "digital or external",
    ),
    (
        "external thermostat in the wrong domain",
        _set("zones.basement.thermostat", {"external": "sensor.x"}),
        "zones.basement.thermostat.external",
        "climate",
    ),
    (
        "unknown digital thermostat key",
        _set("zones.basement.thermostat", {"digital": {"hysteresis": 1}}),
        "zones.basement.thermostat.digital.hysteresis",
        "Unknown key",
    ),
    (
        "unknown preset",
        _set("zones.basement.thermostat", {"digital": {"presets": {"boost": 24}}}),
        "zones.basement.thermostat.digital.presets.boost",
        "Unknown key",
    ),
    (
        "preset as text",
        _set("zones.basement.thermostat", {"digital": {"presets": {"eco": "low"}}}),
        "zones.basement.thermostat.digital.presets.eco",
        "number",
    ),
    (
        "zero proportional band",
        _set("zones.basement.thermostat", {"digital": {"proportional_band": 0}}),
        "zones.basement.thermostat.digital.proportional_band",
        "positive",
    ),
    (
        "negative target is allowed but not NaN",
        _set("zones.basement.thermostat", {"digital": {"target": float("nan")}}),
        "zones.basement.thermostat.digital.target",
        "number",
    ),
]


@pytest.mark.parametrize(
    ("mutate", "path", "fragment"),
    [pytest.param(mutate, path, fragment, id=name) for name, mutate, path, fragment in REJECTIONS],
)
def test_rejections_name_the_path(
    mutate: Callable[[dict[str, Any]], None], path: str, fragment: str
) -> None:
    document = deepcopy(reference_document())
    mutate(document)

    with pytest.raises(PlantFileError) as caught:
        parse_plant(document)

    assert caught.value.path == path
    assert fragment in caught.value.message
    assert str(caught.value) == f"{path}: {caught.value.message}"


def test_a_document_that_is_not_a_mapping_is_rejected_at_the_top() -> None:
    with pytest.raises(PlantFileError) as caught:
        parse_plant(["hydronicus", 2])

    assert caught.value.path == ""
    assert str(caught.value) == caught.value.message


def test_a_loop_that_runs_with_the_source_needs_a_source() -> None:
    document = {
        "hydronicus": 2,
        "name": "No source",
        "pumps": {"dryer": {"switch": "switch.dryer"}},
        "loops": {"dryer": {"pump": "dryer", "runs": "with_source"}},
    }

    with pytest.raises(PlantFileError) as caught:
        parse_plant(document)

    assert caught.value.path == "loops.dryer.runs"


def test_validate_plant_checks_a_plant_built_by_hand() -> None:
    plant = reference_plant()
    broken = Plant(
        id=plant.id,
        name=plant.name,
        pumps=(*plant.pumps, plant.pumps[1]),
        zones=plant.zones,
        source=plant.source,
        loops=plant.loops,
    )

    with pytest.raises(PlantFileError) as caught:
        validate_plant(broken)

    assert caught.value.path == "pumps.floor"
    assert "twice" in caught.value.message


def test_validate_plant_rejects_a_zone_loop_that_runs_with_the_source() -> None:
    plant = reference_plant()
    zone = plant.zones[0]
    loop = zone.loops[0]
    broken_loop = type(loop)(
        ref=loop.ref,
        valves=loop.valves,
        pump=loop.pump,
        modes=loop.modes,
        runs=LoopRun(RunKind.WITH_SOURCE),
    )
    broken_zone = type(zone)(slug=zone.slug, areas=zone.areas, loops=(broken_loop,))
    broken = Plant(
        id=plant.id,
        name=plant.name,
        source=plant.source,
        pumps=plant.pumps,
        loops=plant.loops,
        zones=(broken_zone, *plant.zones[1:]),
    )

    with pytest.raises(PlantFileError) as caught:
        validate_plant(broken)

    assert caught.value.path == f"{CEILING}.runs"


# YAML


def test_yaml_errors_and_duplicate_keys_are_plant_file_errors() -> None:
    with pytest.raises(PlantFileError, match="not valid YAML"):
        load_yaml("hydronicus: [2")
    with pytest.raises(PlantFileError, match="duplicate key 'floor'"):
        load_yaml("pumps:\n  floor: {switch: switch.a}\n  floor: {switch: switch.b}\n")
    with pytest.raises(PlantFileError, match="empty"):
        read_plant_file("")


def test_yaml_quotes_text_that_would_read_as_another_type() -> None:
    document = {"name": "On", "ids": ["2026-01-01", "12"], "nested": {"a": "b: c"}}

    assert yaml.safe_load(dump_yaml(document)) == document


# Storage


def test_storage_splits_the_plant_into_entry_data_and_zone_subentries() -> None:
    plant = reference_plant()

    entry_data, zones = to_storage(plant)

    assert "zones" not in entry_data
    assert entry_data["hydronicus"] == PLANT_FILE_FORMAT
    assert entry_data["id"] == PLANT_ID
    assert list(zones) == ["basement", "bedroom_area", "living_area"]
    assert zones["living_area"]["slug"] == "living_area"
    assert [loop["slug"] for loop in zones["living_area"]["loops"]] == ["ceiling", "floor"]
    assert json.loads(json.dumps([entry_data, zones])) == [entry_data, zones]
    assert from_storage(entry_data, zones) == plant


def test_storage_is_the_plant_file_split_at_zones_with_objects_listed() -> None:
    document = export_plant(reference_plant())
    entry_data, zones = to_storage(reference_plant())

    def listed(table: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"slug": slug, **item} for slug, item in table.items()]

    assert entry_data == {
        **{key: value for key, value in document.items() if key != "zones"},
        "pumps": listed(document["pumps"]),
        "loops": listed(document["loops"]),
    }
    assert zones == {
        slug: {"slug": slug, **data, "loops": listed(data["loops"])}
        for slug, data in document["zones"].items()
    }


# Pumps, plant loops, and a zone's loops in an order that sorting the keys changes.
UNSORTED = """\
hydronicus: 2
id: 7c9e6679-7425-40de-944b-e07fc1f90ae7
name: Home
mode_dwell: 3600
pumps:
  radiators:
    switch: switch.radiator_pump
    overrun: 180
  floor:
    switch: switch.floor_pump
    overrun: 180
loops:
  towel_dryer:
    pump: radiators
    runs: {with_zones: [study]}
    modes: [heat]
  garage:
    valves: [switch.garage_valve]
    pump: floor
    runs: {with_zones: [study]}
    modes: [heat]
zones:
  study:
    temperature: [sensor.study]
    loops:
      radiator:
        valves: [switch.study_radiator_valve]
        pump: radiators
        modes: [heat]
      floor:
        valves: [switch.study_floor_valve]
        pump: floor
        modes: [heat]
  attic:
    temperature: [sensor.attic]
"""


def test_storage_keeps_the_order_of_pumps_and_loops_through_sorted_keys() -> None:
    """Home Assistant stores config entries with sorted keys; the order must survive.

    ``ConfigEntry.as_storage_fragment`` writes the entry, its data and its
    subentries' data, with ``json_bytes_sorted``, while the subentries stay a
    list in their own order.
    """
    plant = read_plant_file(UNSORTED)
    assert write_plant_file(plant) == UNSORTED
    entry_data, zones = to_storage(plant)

    stored_data = json.loads(json.dumps(entry_data, sort_keys=True))
    stored_zones = {
        slug: json.loads(json.dumps(data, sort_keys=True)) for slug, data in zones.items()
    }

    assert write_plant_file(from_storage(stored_data, stored_zones)) == UNSORTED


def test_storage_rejects_inconsistent_data() -> None:
    entry_data, zones = to_storage(reference_plant())

    with pytest.raises(PlantFileError) as caught:
        from_storage({**entry_data, "zones": {}}, zones)
    assert caught.value.path == "zones"

    with pytest.raises(PlantFileError) as caught:
        from_storage(entry_data, {**zones, "attic": {**zones["basement"]}})
    assert caught.value.path == "zones.attic.slug"

    with pytest.raises(PlantFileError) as caught:
        from_storage(entry_data, {"basement": ["not", "a", "mapping"]})
    assert caught.value.path == "zones.basement"

    without_id = {key: value for key, value in entry_data.items() if key != "id"}
    with pytest.raises(PlantFileError) as caught:
        from_storage(without_id, zones)
    assert caught.value.path == "id"

    with pytest.raises(PlantFileError) as caught:
        from_storage({**entry_data, "pumps": {"floor": {"switch": "switch.floor"}}}, zones)
    assert (caught.value.path, caught.value.message) == ("pumps", "Expected a list.")

    with pytest.raises(PlantFileError) as caught:
        from_storage({**entry_data, "pumps": [{"switch": "switch.floor"}]}, zones)
    assert caught.value.path == "pumps.0.slug"

    living = zones["living_area"]
    twice = {**living, "loops": [living["loops"][0], living["loops"][0]]}
    with pytest.raises(PlantFileError) as caught:
        from_storage(entry_data, {**zones, "living_area": twice})
    assert caught.value.path == "zones.living_area.loops.ceiling"


def test_removing_a_zone_subentry_leaves_the_rest_of_the_plant() -> None:
    entry_data, zones = to_storage(reference_plant())
    del zones["bedroom_area"]

    plant = from_storage(entry_data, zones)

    assert [zone.slug for zone in plant.zones] == ["basement", "living_area"]


# Bound entities


def test_entity_paths_name_where_each_entity_is_bound() -> None:
    document = load_yaml(EVERY_KEY)
    document["source"]["mode"] = {"entity": "select.boiler_mode", "heat": "h", "cool": "c"}
    paths = entity_paths(parse_plant(document))

    assert paths == {
        "switch.boiler_request": "source.request",
        "select.boiler_mode": "source.mode.entity",
        "sensor.primary_supply": "pumps.primary.supply_temperature",
        "switch.secondary_pump": "pumps.secondary.switch",
        "valve.garage": "loops.garage.valves.0",
        "binary_sensor.garage_open": "loops.garage.valves.0.readiness",
        "sensor.garage_floor": "loops.garage.surface_temperature",
        "sensor.office": "zones.office.temperature.0",
        "sensor.office_desk": "zones.office.temperature.1",
        "sensor.office_humidity": "zones.office.humidity.0",
        "switch.office_valve_a": "zones.office.loops.radiators.valves.0",
        "switch.office_valve_b": "zones.office.loops.radiators.valves.1",
        "sensor.lab": "zones.lab.temperature.0",
        "sensor.lab_humidity": "zones.lab.humidity.0",
        "climate.lab": "zones.lab.thermostat.external",
    }


def test_more_rejections_of_values_a_file_can_hold() -> None:
    cases: list[tuple[Any, str]] = [
        ({**reference_document(), "hydronicus": 3}, "hydronicus"),
        ({**reference_document(), "id": 5}, "id"),
        ({**reference_document(), "source": {1: "x"}}, "source"),
    ]
    for document, path in cases:
        with pytest.raises(PlantFileError) as caught:
            parse_plant(document)
        assert caught.value.path == path
    with pytest.raises(PlantFileError, match="unhashable key"):
        load_yaml("? [a, b]\n: 1\n")


def test_validate_plant_rejects_run_and_mode_values_a_file_cannot_hold() -> None:
    plant = reference_plant()
    dryer = plant.loops[0]
    for broken_loop, path in (
        (replace(dryer, runs=LoopRun(RunKind.ZONE)), "loops.towel_dryer.runs"),
        (replace(dryer, modes=frozenset({Mode.OFF})), "loops.towel_dryer.modes"),
        (replace(dryer, modes=frozenset()), "loops.towel_dryer.modes"),
    ):
        with pytest.raises(PlantFileError) as caught:
            validate_plant(replace(plant, loops=(broken_loop,)))
        assert caught.value.path == path


def test_a_zone_without_loops_runs_a_plant_loop() -> None:
    document = load_yaml(EVERY_KEY)
    del document["zones"]["lab"]["loops"]
    plant = parse_plant(document)

    assert plant.zone("lab").loops == ()
    assert "loops" not in export_plant(plant)["zones"]["lab"]
    assert write_plant_file(read_plant_file(write_plant_file(plant))) == write_plant_file(plant)


def test_a_source_without_a_mode_select_binds_only_its_request() -> None:
    plant = read_plant_file(EVERY_KEY)

    assert plant.outputs() == {
        "switch.boiler_request": OutputRole.SOURCE_REQUEST,
        "switch.secondary_pump": OutputRole.PUMP,
        "valve.garage": OutputRole.VALVE,
        "switch.office_valve_a": OutputRole.VALVE,
        "switch.office_valve_b": OutputRole.VALVE,
    }
    assert "source.mode.entity" not in entity_paths(plant).values()


# Paths in words


@pytest.mark.parametrize(
    ("path", "words"),
    [
        ("", "The plant file"),
        ("name", "Plant name"),
        ("mode_dwell", "Mode dwell"),
        ("hydronicus", "Plant file format"),
        ("source.mode.cool", "Source, mode select, cool option"),
        ("source.request", "Source, request switch"),
        ("pumps.heat_pump.min_flow_loops.0", "Pump Heat pump, min-flow loop 1"),
        ("pumps.heat_pump.supply_temperature", "Pump Heat pump, supply temperature sensor"),
        ("loops.towel_dryer.runs.with_zones.1", "Plant loop Towel dryer, runs with, zone 2"),
        ("zones.living_area.loops.floor.pump", "Zone Living area, loop Floor, pump"),
        ("zones.living_area.loops.floor.valves.0", "Zone Living area, loop Floor, valve 1"),
        (
            "zones.living_area.loops.floor.valves.0.readiness",
            "Zone Living area, loop Floor, valve 1, readiness sensor",
        ),
        ("zones.basement.areas.1", "Zone Basement, area 2"),
        ("zones.basement.temperature.0", "Zone Basement, temperature sensor 1"),
        ("zones.basement.humidity", "Zone Basement, humidity sensors"),
        (
            "zones.basement.thermostat.digital.presets.eco",
            "Zone Basement, thermostat, digital, presets, eco",
        ),
        ("zones.nowhere.odd_key", "Zone Nowhere, odd key"),
        ("pumps", "Pumps"),
    ],
)
def test_a_path_reads_in_words_with_the_names_of_its_objects(path: str, words: str) -> None:
    document = load_yaml(REFERENCE_PLANT.read_text(encoding="utf-8"))
    document["zones"]["basement"]["name"] = "Basement"
    document["pumps"]["heat_pump"]["name"] = "Heat pump"

    assert describe_path(document, path) == words


def test_a_path_names_an_object_by_its_name() -> None:
    document = {"pumps": {"p1": {"name": "Main circulator"}}, "zones": "not a mapping"}

    assert describe_path(document, "pumps.p1.switch") == "Pump Main circulator, switch"
    assert describe_path(document, "zones.study") == "Zone Study"
