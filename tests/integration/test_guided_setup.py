"""Guided setup: the Plant and its source, pumps, zoning, zones with loops, plant loops, review.

Contract K8. Every step validates the Plant so far with the plant file rules and
shows a problem on the field it belongs to, or at the form's base with its path
in words, and the review's warnings never block.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.core.model import MinFlow, Mode, RunKind
from custom_components.hydronicus.core.plant_file import read_plant_file
from tests.integration.helpers import (
    BASEMENT_CEILING,
    BEDROOM_CEILING,
    FLOOR_PUMP,
    LIVING_CEILING,
    LIVING_FLOOR,
    REFERENCE_PLANT,
    REFERENCE_PLANT_ID,
    SOURCE_MODE,
    SOURCE_REQUEST,
    SUPPLY,
    TOWEL_PUMP,
    async_choose,
    async_import,
    async_submit,
    create_area,
    fields,
    reference_world,
    set_humidity,
    set_temperature,
    stored,
    suggested,
)


async def async_start(hass: HomeAssistant) -> dict[str, Any]:
    """Open guided setup at its first form."""
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["guided", "import_plant"]
    result = await async_choose(flow, result, "guided")
    assert result["step_id"] == "plant"
    return result


async def async_create(hass: HomeAssistant, result: dict[str, Any]) -> ConfigEntry:
    """Leave the zones, add no plant loop, and create the Plant from the review."""
    flow = hass.config_entries.flow
    result = await async_choose(flow, result, "zones_done")
    result = await async_choose(flow, result, "loops_done")
    assert result["step_id"] == "review"
    result = await async_submit(flow, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()
    return result["result"]


async def async_guided_reference(hass: HomeAssistant) -> ConfigEntry:
    """Set up the reference plant of the redesign plan through guided setup."""
    flow = hass.config_entries.flow
    result = await async_start(hass)
    result = await async_submit(
        flow,
        result,
        {
            "name": "Home",
            "source_name": "Heat pump",
            "request": SOURCE_REQUEST,
            "mode_select": SOURCE_MODE,
        },
    )
    assert result["step_id"] == "source_mode"
    result = await async_submit(flow, result, {"heat": "Heat", "cool": "Cool"})
    assert result["step_id"] == "pump"
    assert result["description_placeholders"]["pumps"] == "none yet"
    result = await async_submit(
        flow,
        result,
        {
            "name": "Heat pump",
            "min_flow": "path",
            "supply_temperature": SUPPLY,
            "add_another": True,
        },
    )
    assert result["description_placeholders"]["pumps"] == "Heat pump"
    result = await async_submit(
        flow, result, {"name": "Floor", "switch": FLOOR_PUMP, "overrun": 180, "add_another": True}
    )
    assert result["description_placeholders"]["pumps"] == "Heat pump, Floor"
    result = await async_submit(
        flow, result, {"name": "Towel dryer", "switch": TOWEL_PUMP, "overrun": 120}
    )
    assert result["type"] is FlowResultType.MENU and result["step_id"] == "zoning"
    result = await async_choose(flow, result, "zoning_grouped")
    zones = (
        ("Basement", ["basement", "workshop"], [("Ceiling", BASEMENT_CEILING, "heat_pump")]),
        (
            "Bedroom area",
            ["main_bedroom", "lilla_bedroom"],
            [("Ceiling", BEDROOM_CEILING, "heat_pump")],
        ),
        (
            "Living area",
            ["living_room", "dining_room", "kitchen", "hallway"],
            [("Ceiling", LIVING_CEILING, "heat_pump"), ("Floor", LIVING_FLOOR, "floor")],
        ),
    )
    for index, (name, areas, loops) in enumerate(zones):
        assert result["step_id"] == "zone"
        zone: dict[str, Any] = {"name": name, "areas": areas}
        if index == 0:
            zone["presets"] = {"comfort": 21, "eco": 19, "away": 16}
        result = await async_submit(flow, result, zone)
        if index == 0:
            labels = {
                option["value"]: option["label"]
                for option in _selector(result, "pump")["select"]["options"]
            }
            assert labels == {
                "heat_pump": "Heat pump (driven by the source)",
                "floor": f"Floor ({FLOOR_PUMP})",
                "towel_dryer": f"Towel dryer ({TOWEL_PUMP})",
            }
        for loop_index, (loop, valve, pump) in enumerate(loops):
            assert result["step_id"] == "zone_loop", result
            modes = ["heat", "cool"] if pump == "heat_pump" else ["heat"]
            result = await async_submit(
                flow, result, {"name": loop, "valves": [valve], "pump": pump, "modes": modes}
            )
            assert result["step_id"] == "zone_menu"
            if loop_index + 1 < len(loops):
                result = await async_choose(flow, result, "zone_loop")
        if index + 1 < len(zones):
            result = await async_choose(flow, result, "zone")
    result = await async_choose(flow, result, "zones_done")
    assert result["step_id"] == "plant_loops"
    result = await async_choose(flow, result, "plant_loop")
    result = await async_submit(
        flow,
        result,
        {"name": "Towel dryer", "pump": "towel_dryer", "runs": "with_source", "modes": ["heat"]},
    )
    result = await async_choose(flow, result, "loops_done")
    assert result["step_id"] == "min_flow"
    assert result["description_placeholders"]["pump"] == "Heat pump"
    result = await async_submit(flow, result, {"min_flow_loops": ["living_area.ceiling"]})
    assert result["step_id"] == "review"
    result = await async_submit(flow, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()
    return result["result"]


async def test_guided_setup_of_the_reference_plant_stores_its_plant_file(
    hass: HomeAssistant,
) -> None:
    reference_world(hass)
    guided = await async_guided_reference(hass)
    assert guided.state is ConfigEntryState.LOADED
    guided_data, guided_zones = stored(guided)
    assert await hass.config_entries.async_remove(guided.entry_id)
    await hass.async_block_till_done()

    imported = await async_import(hass, REFERENCE_PLANT)
    imported_data, imported_zones = stored(imported)

    assert guided_data.pop("id") != imported_data.pop("id") == REFERENCE_PLANT_ID
    assert guided_data == imported_data
    assert guided_zones == imported_zones
    assert guided.options == {"armed_outputs": [], "control": False}


async def test_one_zone_per_area_prefills_each_zone_from_its_area(hass: HomeAssistant) -> None:
    flow = hass.config_entries.flow
    for name in ("Kitchen", "Study", "Attic"):
        set_temperature(hass, f"sensor.{name.lower()}_temperature", 20.0)
        create_area(hass, name, temperature=f"sensor.{name.lower()}_temperature")
    create_area(hass, "Garage")
    result = await async_start(hass)
    result = await async_submit(flow, result, {"name": "Flat"})
    result = await async_submit(flow, result, {"name": "Pump", "switch": "switch.pump"})
    result = await async_choose(flow, result, "zoning_per_area")
    assert result["step_id"] == "zoning_per_area"
    assert sorted(suggested(result, "areas")) == ["attic", "kitchen", "study"], (
        "areas with a sensor"
    )
    result = await async_submit(flow, result, {"areas": ["kitchen", "study"]})

    for area, valve in (("kitchen", "switch.kitchen_valve"), ("study", "switch.study_valve")):
        assert result["step_id"] == "zone"
        assert suggested(result, "areas") == [area]
        assert result["description_placeholders"]["progress"]
        # The name stays empty and the zone takes its one area's name.
        result = await async_submit(flow, result, {"areas": [area]})
        result = await async_submit(flow, result, {"valves": [valve], "pump": "pump"})
        assert result["step_id"] == "zone_menu"
        if area == "kitchen":
            assert "zones_done" not in result["menu_options"], "the study is still to come"
            result = await async_choose(flow, result, "zone")
    entry = await async_create(hass, result)

    plant = entry.runtime_data.plant
    assert [(zone.slug, zone.title, [a.area for a in zone.areas]) for zone in plant.zones] == [
        ("kitchen", "Kitchen", ["kitchen"]),
        ("study", "Study", ["study"]),
    ]
    assert [loop.title for loop in plant.all_loops] == ["Loop", "Loop"]
    assert {subentry.title for subentry in entry.subentries.values()} == {"Kitchen", "Study"}


async def test_zones_that_cover_several_areas_are_named_after_their_floor(
    hass: HomeAssistant,
) -> None:
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import floor_registry as fr

    flow = hass.config_entries.flow
    floor = fr.async_get(hass).async_create("Ground floor")
    for name in ("Kitchen", "Hall"):
        set_temperature(hass, f"sensor.{name.lower()}_temperature", 20.0)
        area = create_area(hass, name, temperature=f"sensor.{name.lower()}_temperature")
        ar.async_get(hass).async_update(area.id, floor_id=floor.floor_id)
    result = await async_start(hass)
    result = await async_submit(flow, result, {"name": "Flat"})
    result = await async_submit(flow, result, {"name": "Pump", "switch": "switch.pump"})
    result = await async_choose(flow, result, "zoning_grouped")
    result = await async_submit(flow, result, {"areas": ["kitchen", "hall"]})
    result = await async_submit(flow, result, {"valves": ["switch.valve"], "pump": "pump"})
    entry = await async_create(hass, result)

    (zone,) = entry.runtime_data.plant.zones
    assert (zone.slug, zone.title) == ("ground_floor", "Ground floor")
    assert [area.area for area in zone.areas] == ["kitchen", "hall"]


async def test_a_zone_from_scratch_has_no_areas_and_needs_a_temperature_sensor(
    hass: HomeAssistant,
) -> None:
    flow = hass.config_entries.flow
    result = await async_start(hass)
    result = await async_submit(flow, result, {"name": "Flat"})
    result = await async_submit(flow, result, {"name": "Pump", "switch": "switch.pump"})
    result = await async_choose(flow, result, "zoning_scratch")
    assert result["step_id"] == "zone"
    assert "areas" not in fields(result)

    result = await async_submit(flow, result, {"name": "Study"})
    assert result["errors"] == {"temperature": "invalid_value"}
    assert "temperature sensor" in result["description_placeholders"]["problem"]

    result = await async_submit(flow, result, {"name": "Study", "temperature": ["sensor.study"]})
    result = await async_submit(flow, result, {"valves": ["switch.study_valve"], "pump": "pump"})
    result = await async_choose(flow, result, "zone")
    result = await async_submit(flow, result, {"name": "Den", "thermostat": "climate.den"})
    result = await async_submit(flow, result, {"valves": ["switch.den_valve"], "pump": "pump"})
    entry = await async_create(hass, result)

    study, den = entry.runtime_data.plant.zones
    assert study.areas == () and [sensor.entity for sensor in study.temperature] == ["sensor.study"]
    assert den.thermostat.entity == "climate.den"  # type: ignore[union-attr]


async def test_a_zone_with_two_loops_and_a_loop_without_a_valve(hass: HomeAssistant) -> None:
    flow = hass.config_entries.flow
    result = await async_start(hass)
    result = await async_submit(flow, result, {"name": "Flat"})
    result = await async_submit(
        flow, result, {"name": "Radiators", "switch": "switch.radiator_pump", "add_another": True}
    )
    result = await async_submit(flow, result, {"name": "Towel", "switch": "switch.towel_pump"})
    result = await async_choose(flow, result, "zoning_scratch")
    result = await async_submit(flow, result, {"name": "Bathroom", "temperature": ["sensor.bath"]})
    result = await async_submit(
        flow,
        result,
        {
            "name": "Radiator",
            "valves": ["switch.bath_valve"],
            "pump": "radiators",
            "opening_time": 240,
        },
    )
    result = await async_choose(flow, result, "zone_loop")
    result = await async_submit(flow, result, {"name": "Towel rail", "pump": "towel"})
    entry = await async_create(hass, result)

    (zone,) = entry.runtime_data.plant.zones
    radiator, towel = zone.loops
    assert (radiator.slug, radiator.pump, radiator.valves[0].opening_time) == (
        "radiator",
        "radiators",
        240.0,
    )
    assert (towel.slug, towel.pump, towel.valves) == ("towel_rail", "towel", ())


async def test_a_zone_whose_loop_form_is_left_empty_has_no_loop_of_its_own(
    hass: HomeAssistant,
) -> None:
    flow = hass.config_entries.flow
    result = await async_start(hass)
    result = await async_submit(flow, result, {"name": "Flat"})
    result = await async_submit(flow, result, {"name": "Pump", "switch": "switch.pump"})
    result = await async_choose(flow, result, "zoning_scratch")
    result = await async_submit(flow, result, {"name": "Study", "temperature": ["sensor.study"]})

    result = await async_submit(flow, result, {"valves": ["switch.study_valve"]})
    assert result["errors"] == {"pump": "pump_required"}

    result = await async_submit(flow, result, {})
    assert result["step_id"] == "zone_menu"
    result = await async_choose(flow, result, "zones_done")
    result = await async_choose(flow, result, "plant_loop")
    result = await async_submit(
        flow,
        result,
        {"name": "Shared", "valves": ["switch.shared"], "pump": "pump", "runs": "with_zones"},
    )
    assert result["errors"] == {"with_zones": "zones_required"}
    result = await async_submit(
        flow,
        result,
        {
            "name": "Shared",
            "valves": ["switch.shared"],
            "pump": "pump",
            "runs": "with_zones",
            "with_zones": ["study"],
        },
    )
    result = await async_choose(flow, result, "loops_done")
    assert "Zone Study has no loop of its own" not in result["description_placeholders"]["warnings"]
    result = await async_submit(flow, result)
    await hass.async_block_till_done()

    plant = result["result"].runtime_data.plant
    (loop,) = plant.loops
    assert (loop.runs.kind, loop.runs.zones) == (RunKind.WITH_ZONES, ("study",))
    assert plant.zones[0].loops == ()


async def test_a_source_driven_pump_asks_for_its_min_flow_loops_after_the_loops(
    hass: HomeAssistant,
) -> None:
    flow = hass.config_entries.flow
    result = await async_start(hass)
    result = await async_submit(flow, result, {"name": "Flat", "request": "switch.boiler"})
    assert result["step_id"] == "pump", "no mode select, so no source mode step"
    result = await async_submit(flow, result, {"name": "Boiler pump", "min_flow": "path"})
    result = await async_choose(flow, result, "zoning_scratch")
    result = await async_submit(flow, result, {"name": "Study", "temperature": ["sensor.study"]})
    result = await async_submit(
        flow, result, {"name": "Radiator", "valves": ["switch.study_valve"], "pump": "boiler_pump"}
    )
    result = await async_choose(flow, result, "zones_done")
    result = await async_choose(flow, result, "plant_loop")
    result = await async_submit(
        flow, result, {"name": "Bypass", "pump": "boiler_pump", "runs": "with_source"}
    )
    result = await async_choose(flow, result, "loops_done")
    assert result["step_id"] == "min_flow"
    options = {
        option["value"]: option["label"]
        for option in _selector(result, "min_flow_loops")["select"]["options"]
    }
    assert options == {"study.radiator": "Study / Radiator", "bypass": "Bypass (plant loop)"}

    result = await async_submit(flow, result, {})
    assert result["errors"] == {"min_flow_loops": "min_flow_loops_required"}
    result = await async_submit(flow, result, {"min_flow_loops": ["bypass"]})
    assert result["step_id"] == "review"
    result = await async_submit(flow, result)
    await hass.async_block_till_done()

    pump = result["result"].runtime_data.plant.pump("boiler_pump")
    assert pump.driven_by_source and pump.min_flow is MinFlow.PATH
    assert [str(ref) for ref in pump.min_flow_loops] == ["bypass"]


async def test_a_separator_makes_the_min_flow_step_unnecessary(hass: HomeAssistant) -> None:
    flow = hass.config_entries.flow
    result = await async_start(hass)
    result = await async_submit(flow, result, {"name": "Flat", "request": "switch.boiler"})
    result = await async_submit(flow, result, {"name": "Boiler pump", "min_flow": "path"})
    result = await async_choose(flow, result, "zoning_scratch")
    result = await async_submit(flow, result, {"name": "Study", "temperature": ["sensor.study"]})
    result = await async_submit(
        flow, result, {"name": "Radiator", "valves": ["switch.v"], "pump": "boiler_pump"}
    )
    result = await async_choose(flow, result, "zones_done")
    result = await async_choose(flow, result, "loops_done")
    result = await async_submit(flow, result, {"guaranteed": True})
    assert result["step_id"] == "review"
    result = await async_submit(flow, result)
    await hass.async_block_till_done()

    assert result["result"].runtime_data.plant.pump("boiler_pump").min_flow is MinFlow.GUARANTEED


async def test_a_problem_shows_on_its_field_or_at_the_base_in_words(hass: HomeAssistant) -> None:
    flow = hass.config_entries.flow
    result = await async_start(hass)

    result = await async_submit(flow, result, {"name": " "})
    assert result["errors"] == {"name": "name_required"}
    result = await async_submit(flow, result, {"name": "Flat", "mode_select": "select.mode"})
    assert result["errors"] == {"request": "mode_needs_request"}

    result = await async_submit(flow, result, {"name": "Flat"})
    result = await async_submit(flow, result, {"name": "Pump"})
    assert result["errors"] == {"switch": "invalid_value"}, "a pump without a switch needs a source"
    assert "needs a source" in result["description_placeholders"]["problem"]
    result = await async_submit(flow, result, {"name": "Pump", "switch": "switch.pump"})

    result = await async_choose(flow, result, "zoning_scratch")
    result = await async_submit(flow, result, {"name": "Study", "temperature": ["sensor.study"]})
    result = await async_submit(
        flow, result, {"valves": ["switch.v"], "pump": "pump", "modes": ["heat", "cool"]}
    )
    assert result["errors"] == {"modes": "invalid_value"}
    assert "condensation reference" in result["description_placeholders"]["problem"]

    result = await async_submit(
        flow,
        result,
        {
            "valves": ["switch.v"],
            "pump": "pump",
            "modes": ["heat", "cool"],
            "surface_temperature": "sensor.ceiling",
        },
    )
    assert result["errors"] == {"base": "invalid_plant"}, "cooling needs the zone's humidity"
    assert result["description_placeholders"]["where"] == "Zone Study, humidity sensors"

    result = await async_submit(
        flow, result, {"valves": ["switch.pump"], "pump": "pump", "modes": ["heat"]}
    )
    assert result["errors"] == {"valves": "invalid_value"}, "an output has one role"
    assert result["description_placeholders"]["where"] == "Zone Study, loop Loop, valve 1"


async def test_a_mode_select_offers_its_own_options(hass: HomeAssistant) -> None:
    flow = hass.config_entries.flow
    hass.states.async_set(
        "select.mode",
        "Heating",
        {"options": ["Heating", "Cooling", "Auto"], "friendly_name": "Heat pump mode"},
    )
    result = await async_start(hass)
    result = await async_submit(
        flow, result, {"name": "Flat", "request": "switch.request", "mode_select": "select.mode"}
    )
    assert result["step_id"] == "source_mode"
    assert _selector(result, "heat")["select"]["options"] == ["Heating", "Cooling", "Auto"]
    assert result["description_placeholders"]["select"] == "Heat pump mode (select.mode)"
    assert (suggested(result, "heat"), suggested(result, "cool")) == ("Heating", "Cooling"), (
        "the options that name heating and cooling are suggested"
    )

    result = await async_submit(flow, result, {"heat": "Heating", "cool": "Heating"})
    assert result["errors"] == {"cool": "invalid_value"}
    result = await async_submit(flow, result, {"heat": "Heating", "cool": "Chill"})
    assert result["errors"] == {"cool": "option_not_offered"}
    result = await async_submit(flow, result, {"heat": "Heating", "cool": "Cooling"})
    assert result["step_id"] == "pump"


async def test_a_hydronicus_entity_or_another_plants_output_is_refused(
    hass: HomeAssistant,
) -> None:
    reference_world(hass)
    await async_import(hass, REFERENCE_PLANT)
    flow = hass.config_entries.flow
    result = await async_start(hass)
    result = await async_submit(flow, result, {"name": "Flat"})

    result = await async_submit(flow, result, {"name": "Pump", "switch": FLOOR_PUMP})
    assert result["errors"] == {"switch": "output_bound_elsewhere"}
    assert result["description_placeholders"]["other_plant"] == "Home"
    result = await async_submit(flow, result, {"name": "Pump", "switch": "switch.pump"})

    result = await async_choose(flow, result, "zoning_scratch")
    # The pickers leave out Hydronicus's own entities; a plant file is checked instead.
    excluded = _selector(result, "temperature")["entity"]["exclude_entities"]
    assert "sensor.living_area_combined_temperature" in excluded
    assert "climate.living_area" in _selector(result, "thermostat")["entity"]["exclude_entities"]


async def test_the_review_lists_warnings_but_never_blocks(hass: HomeAssistant) -> None:
    flow = hass.config_entries.flow
    create_area(hass, "Study")
    set_humidity(hass, "sensor.study_humidity", 50)
    result = await async_start(hass)
    result = await async_submit(flow, result, {"name": "Flat"})
    result = await async_submit(
        flow,
        result,
        {"name": "Pump", "switch": "switch.pump", "add_another": True},
    )
    result = await async_submit(flow, result, {"name": "Spare", "switch": "switch.spare"})
    result = await async_choose(flow, result, "zoning_grouped")
    result = await async_submit(
        flow, result, {"name": "Study", "areas": ["study"], "temperature": ["sensor.study"]}
    )
    result = await async_submit(flow, result, {"valves": ["switch.v"], "pump": "pump"})
    result = await async_choose(flow, result, "zones_done")
    result = await async_choose(flow, result, "loops_done")

    assert result["step_id"] == "review"
    assert "confirm" not in fields(result)
    warnings = result["description_placeholders"]["warnings"]
    assert "Area Study of zone Study has no temperature sensor" in warnings
    assert "Pump Spare drives no loop" in warnings
    summary = result["description_placeholders"]["summary"]
    assert "Study, covering area Study" in summary
    result = await async_submit(flow, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_import_the_reference_plant_and_the_trial_kit(hass: HomeAssistant) -> None:
    reference_world(hass)
    reference = await async_import(hass, REFERENCE_PLANT)
    trial_text = (
        __import__("pathlib").Path(__file__).parents[1] / "fixtures" / "trial_plant.yaml"
    ).read_text(encoding="utf-8")
    trial = await async_import(hass, trial_text)

    assert reference.runtime_data.plant == read_plant_file(REFERENCE_PLANT)
    assert reference.runtime_data.plant.zone("living_area").loops[0].modes == frozenset(
        {Mode.HEAT, Mode.COOL}
    )
    assert trial.title == "Trial plant"
    assert trial.runtime_data.plant.zones[1].slug == "bedroom"


def _selector(result: dict[str, Any], field: str) -> dict[str, Any]:
    for key, value in result["data_schema"].schema.items():
        if str(key) == field:
            return value.serialize()["selector"]
    raise AssertionError(field)
