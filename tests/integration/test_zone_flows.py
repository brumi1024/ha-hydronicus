"""Zone subentries: add, reconfigure, and remove one zone with its areas, sensors, and loops.

Decision 13 and invariant 9: a zone's record lives in its subentry, it references
only Plant-level pumps, and every zone change is validated as the whole Plant,
with the same rules as setup.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hydronicus.core.model import ExternalThermostat
from tests.integration.helpers import (
    FLOOR_PUMP,
    LIVING_FLOOR,
    REFERENCE_PLANT,
    async_choose,
    async_import,
    async_set_options,
    async_submit,
    create_area,
    fields,
    reference_world,
    set_temperature,
    stored,
    suggested,
    zone_subentry_id,
)


async def async_open(
    hass: HomeAssistant, entry: ConfigEntry, slug: str | None = None
) -> dict[str, Any]:
    """Open the zone form: a new zone, or the reconfigure flow of zone ``slug``."""
    context: dict[str, Any] = {"source": "user"}
    if slug is not None:
        context = {"source": "reconfigure", "subentry_id": zone_subentry_id(entry, slug)}
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "zone"), context=context
    )
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "zone", result
    return result


async def test_add_a_zone_through_its_subentry(hass: HomeAssistant) -> None:
    reference_world(hass)
    set_temperature(hass, "sensor.guest_temperature", 20.0)
    create_area(hass, "Guest room", temperature="sensor.guest_temperature")
    entry = await async_import(hass, REFERENCE_PLANT)
    await async_set_options(hass, entry, armed=[FLOOR_PUMP], control=True)
    flows = hass.config_entries.subentries
    result = await async_open(hass, entry)

    result = await async_submit(flows, result, {"areas": ["guest_room"]})
    assert result["step_id"] == "loop"
    pumps = {option["value"] for option in _options(result, "pump")}
    assert pumps == {"heat_pump", "floor", "towel_dryer"}, "only the Plant's pumps"
    result = await async_submit(
        flows, result, {"name": "Radiator", "valves": ["switch.guest_valve"], "pump": "floor"}
    )
    assert result["type"] is FlowResultType.MENU and result["step_id"] == "menu"
    result = await async_choose(flows, result, "save")
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    _data, zones = stored(entry)
    title, data = zones["guest_room"]
    assert title == "Guest room"
    assert data == {
        "slug": "guest_room",
        "areas": ["guest_room"],
        "loops": {
            "radiator": {"valves": ["switch.guest_valve"], "pump": "floor", "modes": ["heat"]}
        },
    }
    assert hass.states.get("climate.guest_room") is not None
    assert entry.options["armed_outputs"] == [FLOOR_PUMP], "adding a zone never changes arming"


async def test_reconfigure_a_zone_edits_its_settings_and_its_loops(hass: HomeAssistant) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    flows = hass.config_entries.subentries
    result = await async_open(hass, entry, "living_area")
    assert suggested(result, "name") == "Living area"
    assert suggested(result, "areas") == ["living_room", "dining_room", "kitchen", "hallway"]

    result = await async_submit(
        flows,
        result,
        {
            "name": "Living",
            "areas": ["living_room", "kitchen"],
            "temperature": ["sensor.sofa"],
            "aggregation": "min",
            "thermostat": "climate.living_wall",
        },
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["zone", "loop_pick", "save"]
    result = await async_choose(flows, result, "loop_pick")
    options = {option["value"]: option["label"] for option in _options(result, "loop")}
    assert options == {"ceiling": "Ceiling", "floor": "Floor", "__new__": "Add a loop"}
    result = await async_submit(flows, result, {"loop": "floor"})
    assert suggested(result, "valves") == [LIVING_FLOOR]
    assert "remove" in fields(result)
    result = await async_submit(flows, result, {"name": "Floor", "pump": "floor", "remove": True})
    result = await async_choose(flows, result, "loop_pick")
    result = await async_submit(flows, result, {"loop": "__new__"})
    result = await async_submit(
        flows,
        result,
        {"name": "Wall", "valves": ["switch.wall_valve"], "pump": "floor", "opening_time": 300},
    )
    result = await async_choose(flows, result, "save")
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    subentry = entry.subentries[zone_subentry_id(entry, "living_area")]
    assert subentry.title == "Living"
    zone = entry.runtime_data.plant.zone("living_area")
    assert [area.area for area in zone.areas] == ["living_room", "kitchen"]
    assert zone.thermostat == ExternalThermostat("climate.living_wall")
    assert [loop.slug for loop in zone.loops] == ["ceiling", "wall"]
    assert zone.loops[1].valves[0].opening_time == 300.0
    assert entry.state is ConfigEntryState.LOADED


async def test_a_zone_edit_keeps_settings_the_form_does_not_show(hass: HomeAssistant) -> None:
    text = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump}
zones:
  study:
    temperature: [{entity: sensor.study, required: false, max_age: 600}]
    thermostat: {digital: {target: 19, heat_start_delta: 0.5, presets: {eco: 17}}}
    loops:
      radiator:
        valves: [{entity: switch.study_valve, opening_time: 90, readiness: binary_sensor.open}]
        pump: pump
"""
    entry = await async_import(hass, text)
    flows = hass.config_entries.subentries
    result = await async_open(hass, entry, "study")
    result = await async_submit(
        flows,
        result,
        {"name": "Study", "temperature": ["sensor.study"], "presets": {"eco": 16, "away": 12}},
    )
    result = await async_choose(flows, result, "loop_pick")
    result = await async_submit(flows, result, {"loop": "radiator"})
    assert suggested(result, "opening_time") == 90
    result = await async_submit(
        flows,
        result,
        {"name": "Radiator", "valves": ["switch.study_valve"], "pump": "pump", "opening_time": 90},
    )
    result = await async_choose(flows, result, "save")
    await hass.async_block_till_done()

    _data, zones = stored(entry)
    assert zones["study"][1] == {
        "slug": "study",
        "temperature": [{"entity": "sensor.study", "required": False, "max_age": 600}],
        "thermostat": {
            "digital": {"target": 19, "presets": {"eco": 16, "away": 12}, "heat_start_delta": 0.5}
        },
        "loops": {
            "radiator": {
                "valves": [
                    {
                        "entity": "switch.study_valve",
                        "opening_time": 90,
                        "readiness": "binary_sensor.open",
                    }
                ],
                "pump": "pump",
                "modes": ["heat"],
            }
        },
    }


async def test_removing_a_loop_a_pump_holds_open_is_refused_in_words(
    hass: HomeAssistant,
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    flows = hass.config_entries.subentries
    result = await async_open(hass, entry, "living_area")
    result = await async_submit(flows, result, {"name": "Living area", "areas": ["living_room"]})
    result = await async_choose(flows, result, "loop_pick")
    result = await async_submit(flows, result, {"loop": "ceiling"})

    result = await async_submit(
        flows, result, {"name": "Ceiling", "pump": "heat_pump", "remove": True}
    )

    assert result["errors"] == {"base": "invalid_plant"}
    assert result["description_placeholders"]["where"] == "Pump Heat pump, min-flow loop 1"
    assert "There is no loop living_area.ceiling" in result["description_placeholders"]["problem"]


async def test_a_zone_refuses_an_output_of_another_plant_and_a_pump_it_does_not_have(
    hass: HomeAssistant,
) -> None:
    reference_world(hass)
    await async_import(hass, REFERENCE_PLANT)
    flat = await async_import(
        hass,
        """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.flat_pump}
zones:
  study:
    temperature: [sensor.study]
""",
    )
    flows = hass.config_entries.subentries
    result = await async_open(hass, flat)
    result = await async_submit(flows, result, {"name": "Den", "temperature": ["sensor.den"]})

    result = await async_submit(flows, result, {"valves": [LIVING_FLOOR], "pump": "pump"})

    assert result["errors"] == {"valves": "output_bound_elsewhere"}
    assert result["description_placeholders"]["entity_id"] == LIVING_FLOOR


async def test_removing_a_zone_subentry_removes_exactly_its_objects(hass: HomeAssistant) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    data_before, _zones = stored(entry)

    hass.config_entries.async_remove_subentry(entry, zone_subentry_id(entry, "bedroom_area"))
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    data, zones = stored(entry)
    assert data == data_before
    assert set(zones) == {"basement", "living_area"}
    assert hass.states.get("climate.bedroom_area") is None
    assert [zone.slug for zone in entry.runtime_data.plant.zones] == ["basement", "living_area"]


def _options(result: dict[str, Any], field: str) -> list[dict[str, str]]:
    for key, value in result["data_schema"].schema.items():
        if str(key) == field:
            return value.serialize()["selector"]["select"]["options"]
    raise AssertionError(field)
