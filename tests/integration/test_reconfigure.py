"""Entry reconfigure: the Plant, its source, pumps, and plant loops, and replace from a plant file.

Decisions 13, 14, and 18: Plant-level data is edited through the entry's
reconfigure flow, a pump that a loop still uses cannot be removed, a replace
updates zone subentries by slug after a summary, and an output belongs to one
Plant.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hydronicus.core.model import MinFlow, RunKind
from custom_components.hydronicus.core.plant_file import read_plant_file
from tests.integration.helpers import (
    FLOOR_PUMP,
    LIVING_FLOOR,
    REFERENCE_PLANT,
    SOURCE_REQUEST,
    TOWEL_PUMP,
    async_choose,
    async_import,
    async_submit,
    option_values,
    reference_world,
    stored,
    suggested,
    zone_subentry_id,
)

TWO_ZONES = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.flat_pump}
zones:
  study:
    temperature: [sensor.study]
    loops:
      radiator: {valves: [switch.study_valve], pump: pump}
"""


async def async_reconfigure(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(
        entry.domain, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    assert result["type"] is FlowResultType.MENU and result["step_id"] == "reconfigure"
    return result


async def async_save(hass: HomeAssistant, result: dict[str, Any]) -> dict[str, Any]:
    flow = hass.config_entries.flow
    result = await async_choose(flow, result, "save")
    assert result["step_id"] == "save", result
    result = await async_submit(flow, result)
    assert result["type"] is FlowResultType.ABORT, result
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    return result


async def test_reconfigure_the_plant_and_its_source(hass: HomeAssistant) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    flow = hass.config_entries.flow
    result = await async_reconfigure(hass, entry)
    assert result["menu_options"] == ["plant", "pump_pick", "plant_loop_pick", "replace", "save"]

    result = await async_choose(flow, result, "plant")
    assert suggested(result, "request") == SOURCE_REQUEST
    result = await async_submit(
        flow,
        result,
        {
            "name": "House",
            "source_name": "Heat pump",
            "request": SOURCE_REQUEST,
            "mode_select": "select.heat_pump_mode",
            "timing": {"mode_dwell": 1800, "post_run": 240, "min_on": 600, "min_off": 900},
        },
    )
    assert result["step_id"] == "source_mode"
    assert suggested(result, "heat") == "Heat"
    result = await async_submit(flow, result, {"heat": "Heat", "cool": "Cool"})
    assert result["step_id"] == "reconfigure"
    await async_save(hass, result)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.title == "House"
    plant = entry.runtime_data.plant
    assert (plant.name, plant.mode_dwell) == ("House", 1800.0)
    assert plant.source is not None
    assert (plant.source.post_run, plant.source.min_off) == (240.0, 900.0)
    assert plant.zones == read_plant_file(REFERENCE_PLANT).zones


async def test_reconfigure_adds_a_pump_and_a_plant_loop_and_edits_a_pump(
    hass: HomeAssistant,
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    flow = hass.config_entries.flow
    result = await async_reconfigure(hass, entry)

    result = await async_choose(flow, result, "pump_pick")
    result = await async_submit(flow, result, {"pump": "__new__"})
    assert result["step_id"] == "pump"
    assert "remove" not in {str(key) for key in result["data_schema"].schema}
    result = await async_submit(
        flow, result, {"name": "Garage pump", "switch": "switch.garage_pump", "overrun": 60}
    )
    result = await async_choose(flow, result, "plant_loop_pick")
    result = await async_submit(flow, result, {"loop": "__new__"})
    result = await async_submit(
        flow,
        result,
        {
            "name": "Garage",
            "valves": ["switch.garage_valve"],
            "pump": "garage_pump",
            "runs": "with_zones",
            "with_zones": ["basement", "bedroom_area"],
        },
    )
    result = await async_choose(flow, result, "pump_pick")
    result = await async_submit(flow, result, {"pump": "heat_pump"})
    assert suggested(result, "min_flow_loops") == ["living_area.ceiling"]
    result = await async_submit(
        flow,
        result,
        {
            "name": "Heat pump",
            "min_flow": "path",
            "min_flow_loops": ["basement.ceiling", "living_area.ceiling"],
            "supply_temperature": "sensor.ceiling_supply_temperature",
        },
    )
    result = await async_save(hass, result)

    plant = entry.runtime_data.plant
    assert plant.pump("garage_pump").switch == "switch.garage_pump"
    garage = plant.loop(plant.loops[1].ref)
    assert (garage.runs.kind, garage.runs.zones) == (
        RunKind.WITH_ZONES,
        ("basement", "bedroom_area"),
    )
    assert [str(ref) for ref in plant.pump("heat_pump").min_flow_loops] == [
        "basement.ceiling",
        "living_area.ceiling",
    ]
    assert "switch.garage_valve" in plant.outputs()


async def test_a_pump_that_a_loop_uses_cannot_be_removed(hass: HomeAssistant) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    flow = hass.config_entries.flow
    result = await async_reconfigure(hass, entry)
    result = await async_choose(flow, result, "pump_pick")
    result = await async_submit(flow, result, {"pump": "floor"})
    fields = [str(key) for key in result["data_schema"].schema]
    assert "min_flow_loops" not in fields, "only a pump the source drives holds loops open"

    result = await async_submit(
        flow, result, {"name": "Floor", "switch": FLOOR_PUMP, "overrun": 180, "remove": True}
    )

    assert result["errors"] == {"remove": "pump_in_use"}
    assert result["description_placeholders"]["loops"] == "Living area / Floor"


async def test_an_unused_pump_and_a_plant_loop_are_removed(hass: HomeAssistant) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    flow = hass.config_entries.flow
    result = await async_reconfigure(hass, entry)
    result = await async_choose(flow, result, "plant_loop_pick")
    result = await async_submit(flow, result, {"loop": "towel_dryer"})
    result = await async_submit(
        flow,
        result,
        {"name": "Towel dryer", "pump": "towel_dryer", "runs": "with_source", "remove": True},
    )
    result = await async_choose(flow, result, "pump_pick")
    result = await async_submit(flow, result, {"pump": "towel_dryer"})
    result = await async_submit(
        flow, result, {"name": "Towel dryer", "switch": TOWEL_PUMP, "remove": True}
    )
    await async_save(hass, result)

    plant = entry.runtime_data.plant
    assert plant.loops == ()
    assert [pump.slug for pump in plant.pumps] == ["heat_pump", "floor"]


async def test_reconfigure_refuses_an_output_of_another_plant(hass: HomeAssistant) -> None:
    reference_world(hass)
    await async_import(hass, REFERENCE_PLANT)
    flat = await async_import(hass, TWO_ZONES)
    flow = hass.config_entries.flow
    result = await async_reconfigure(hass, flat)
    result = await async_choose(flow, result, "pump_pick")
    result = await async_submit(flow, result, {"pump": "pump"})

    result = await async_submit(flow, result, {"name": "Pump", "switch": FLOOR_PUMP})

    assert result["errors"] == {"switch": "output_bound_elsewhere"}
    assert result["description_placeholders"]["other_plant"] == "Home"


async def test_replace_from_a_plant_file_shows_a_summary_then_updates_zones_by_slug(
    hass: HomeAssistant,
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    basement = zone_subentry_id(entry, "basement")
    living = zone_subentry_id(entry, "living_area")
    replacement = (
        REFERENCE_PLANT.replace(
            """  bedroom_area:
    areas: [main_bedroom, lilla_bedroom]
    loops:
      ceiling:
        valves: [switch.home_bedroom_area_ceiling_heating_valve]
        pump: heat_pump
        modes: [heat, cool]
""",
            """  study:
    temperature: [sensor.study]
    loops:
      radiator:
        valves: [switch.study_valve]
        pump: floor
""",
        )
        .replace(LIVING_FLOOR, "switch.living_area_floor_valve")
        .replace("mode_dwell: 3600", "mode_dwell: 7200")
    )
    flow = hass.config_entries.flow
    result = await async_reconfigure(hass, entry)
    result = await async_choose(flow, result, "replace")

    result = await async_submit(flow, result, {"plant_file": replacement})

    assert result["step_id"] == "save"
    summary = result["description_placeholders"]["summary"]
    assert "Zones added: Study" in summary
    assert "Zones removed: Bedroom area" in summary
    assert "Zones changed: Living area" in summary
    assert "Basement" not in summary
    assert "Outputs added: switch.living_area_floor_valve, switch.study_valve" in summary
    assert (
        "Outputs removed: switch.home_bedroom_area_ceiling_heating_valve, "
        f"{LIVING_FLOOR}" in summary
    )
    assert "Plant settings changed: mode dwell" in summary
    result = await async_submit(flow, result)
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    data, zones = stored(entry)
    assert set(zones) == {"basement", "living_area", "study"}
    assert zone_subentry_id(entry, "basement") == basement, "kept, not recreated"
    assert zone_subentry_id(entry, "living_area") == living
    assert zones["living_area"][1]["loops"][1] == {
        "slug": "floor",
        "valves": ["switch.living_area_floor_valve"],
        "pump": "floor",
        "modes": ["heat"],
    }
    assert data["mode_dwell"] == 7200
    replaced, expected = entry.runtime_data.plant, read_plant_file(replacement)
    assert {zone.slug: zone for zone in replaced.zones} == {
        zone.slug: zone for zone in expected.zones
    }
    assert replaced.pumps == expected.pumps and replaced.mode_dwell == expected.mode_dwell
    assert hass.states.get("climate.study") is not None
    assert hass.states.get("climate.bedroom_area") is None


async def test_replace_refuses_another_plants_file_and_an_invalid_file(
    hass: HomeAssistant,
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    flow = hass.config_entries.flow
    result = await async_reconfigure(hass, entry)
    result = await async_choose(flow, result, "replace")

    result = await async_submit(
        flow,
        result,
        {"plant_file": REFERENCE_PLANT.replace("7c9e6679", "00000000")},
    )
    assert result["errors"] == {"base": "different_plant"}

    result = await async_submit(
        flow, result, {"plant_file": REFERENCE_PLANT.replace("pump: floor", "pump: flor")}
    )
    assert result["errors"] == {"base": "invalid_plant_file"}
    assert result["description_placeholders"]["where"] == "Zone Living area, loop Floor, pump"

    result = await async_submit(
        flow,
        result,
        {"plant_file": REFERENCE_PLANT.replace("id: 7c9e6679-7425-40de-944b-e07fc1f90ae7", "")},
    )
    assert result["step_id"] == "save", "a file without an id keeps the Plant's"
    assert result["description_placeholders"]["summary"] == "Nothing changes."


async def test_a_new_source_driven_pump_gets_its_min_flow_loops_at_save(
    hass: HomeAssistant,
) -> None:
    """A new pump has no loops yet, so Review and save asks for them once a loop uses it."""
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    flow = hass.config_entries.flow
    result = await async_reconfigure(hass, entry)
    result = await async_choose(flow, result, "pump_pick")
    result = await async_submit(flow, result, {"pump": "__new__"})
    result = await async_submit(flow, result, {"name": "Primary", "min_flow": "path"})
    assert result["step_id"] == "reconfigure", result.get("errors")
    status = result["description_placeholders"]["status"]
    assert status.startswith("Pump Primary needs min-flow loops")

    result = await async_choose(flow, result, "plant_loop_pick")
    result = await async_submit(flow, result, {"loop": "__new__"})
    result = await async_submit(
        flow,
        result,
        {"name": "Bypass", "pump": "primary", "runs": "with_source"},
    )
    result = await async_choose(flow, result, "save")
    assert result["step_id"] == "min_flow"
    assert result["description_placeholders"]["pump"] == "Primary"
    assert option_values(result, "min_flow_loops") == ["bypass"]
    result = await async_submit(flow, result, {})
    assert result["errors"] == {"min_flow_loops": "min_flow_loops_required"}
    result = await async_submit(flow, result, {"min_flow_loops": ["bypass"]})
    assert result["step_id"] == "save"
    result = await async_submit(flow, result)
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    pump = entry.runtime_data.plant.pump("primary")
    assert pump.driven_by_source and pump.min_flow is MinFlow.PATH
    assert [str(ref) for ref in pump.min_flow_loops] == ["bypass"]


async def test_a_pump_the_source_now_drives_gets_its_zone_loops_as_min_flow_loops(
    hass: HomeAssistant,
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    flow = hass.config_entries.flow
    result = await async_reconfigure(hass, entry)
    result = await async_choose(flow, result, "pump_pick")
    result = await async_submit(flow, result, {"pump": "floor"})
    result = await async_submit(flow, result, {"name": "Floor", "min_flow": "path"})
    assert result["step_id"] == "reconfigure", result.get("errors")

    result = await async_choose(flow, result, "save")
    assert result["step_id"] == "min_flow"
    assert option_values(result, "min_flow_loops") == ["living_area.floor"]
    result = await async_submit(flow, result, {"min_flow_loops": ["living_area.floor"]})
    await async_submit(flow, result)
    await hass.async_block_till_done()

    pump = entry.runtime_data.plant.pump("floor")
    assert pump.driven_by_source
    assert [str(ref) for ref in pump.min_flow_loops] == ["living_area.floor"]


async def test_removing_a_min_flow_loop_asks_for_another_at_save(hass: HomeAssistant) -> None:
    reference_world(hass)
    entry = await async_import(
        hass,
        REFERENCE_PLANT.replace(
            "min_flow_loops: [living_area.ceiling]", "min_flow_loops: [living_area.ceiling, bypass]"
        ).replace(
            "loops:\n  towel_dryer:",
            "loops:\n  bypass:\n    pump: heat_pump\n    runs: with_source\n    modes: [heat]\n"
            "  towel_dryer:",
        ),
    )
    flow = hass.config_entries.flow
    result = await async_reconfigure(hass, entry)
    result = await async_choose(flow, result, "plant_loop_pick")
    result = await async_submit(flow, result, {"loop": "bypass"})
    result = await async_submit(
        flow, result, {"name": "Bypass", "pump": "heat_pump", "runs": "with_source", "remove": True}
    )
    assert result["step_id"] == "reconfigure", result.get("errors")

    result = await async_choose(flow, result, "save")
    assert result["step_id"] == "min_flow"
    assert suggested(result, "min_flow_loops") == ["living_area.ceiling"]
    result = await async_submit(flow, result, {"min_flow_loops": ["living_area.ceiling"]})
    await async_submit(flow, result)
    await hass.async_block_till_done()

    pump = entry.runtime_data.plant.pump("heat_pump")
    assert [str(ref) for ref in pump.min_flow_loops] == ["living_area.ceiling"]
    assert [loop.slug for loop in entry.runtime_data.plant.loops] == ["towel_dryer"]


async def test_a_new_source_driven_pump_without_a_loop_is_explained_at_save(
    hass: HomeAssistant,
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    flow = hass.config_entries.flow
    result = await async_reconfigure(hass, entry)
    result = await async_choose(flow, result, "pump_pick")
    result = await async_submit(flow, result, {"pump": "__new__"})
    result = await async_submit(flow, result, {"name": "Primary", "min_flow": "path"})

    result = await async_choose(flow, result, "save")
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "min_flow_no_loop"
    assert result["description_placeholders"] == {"pump": "Primary"}
    assert result["menu_options"] == ["min_flow_add_loop", "min_flow_edit_pump", "reconfigure"]
    loop_form = await async_choose(flow, result, "min_flow_add_loop")
    assert loop_form["step_id"] == "plant_loop"
    assert suggested(loop_form, "pump") is None

    result = await async_reconfigure(hass, entry)
    result = await async_choose(flow, result, "pump_pick")
    result = await async_submit(flow, result, {"pump": "__new__"})
    result = await async_submit(flow, result, {"name": "Primary", "min_flow": "path"})
    result = await async_choose(flow, result, "save")
    result = await async_choose(flow, result, "min_flow_edit_pump")
    assert result["step_id"] == "pump"
    assert suggested(result, "name") == "Primary"
    result = await async_submit(flow, result, {"name": "Primary", "min_flow": "guaranteed"})
    result = await async_save(hass, result)
    assert entry.runtime_data.plant.pump("primary").min_flow is MinFlow.GUARANTEED
