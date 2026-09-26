"""Import a Plant from a pasted plant file, format 2."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hydronicus.const import DOMAIN
from tests.integration.helpers import (
    REFERENCE_PLANT,
    async_choose,
    async_import,
    async_submit,
    reference_world,
)

TWO_ZONES = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump}
zones:
  study:
    temperature: [sensor.study]
    loops:
      radiator: {valves: [switch.study_valve], pump: pump}
"""


async def _submit(hass: HomeAssistant, text: str) -> dict:
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": "user"})
    result = await async_choose(flow, result, "import_plant")
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "import_plant"
    return await async_submit(flow, result, {"plant_file": text})


async def test_an_invalid_plant_file_is_shown_with_its_path(hass: HomeAssistant) -> None:
    result = await _submit(hass, TWO_ZONES.replace("pump: pump}", "pump: pumps}"))

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_plant_file"}
    assert result["description_placeholders"]["where"] == "Zone Study, loop Radiator, pump"
    assert result["description_placeholders"]["problem"] == "There is no pump pumps."
    assert "pumps}" in result["data_schema"]({})["plant_file"], "the text is kept to fix"


async def test_yaml_that_does_not_parse_is_refused(hass: HomeAssistant) -> None:
    result = await _submit(hass, "hydronicus: [2")

    assert result["errors"] == {"base": "invalid_plant_file"}
    assert result["description_placeholders"]["where"] == "The plant file"
    assert "not valid YAML" in result["description_placeholders"]["problem"]


async def test_a_hydronicus_entity_is_refused(hass: HomeAssistant) -> None:
    reference_world(hass)
    await async_import(hass, REFERENCE_PLANT)

    result = await _submit(
        hass, TWO_ZONES.replace("sensor.study]", "sensor.living_area_combined_temperature]")
    )

    assert result["errors"] == {"base": "own_entity"}
    assert result["description_placeholders"]["where"] == "Zone Study, temperature sensor 1"
    assert result["description_placeholders"]["entity_id"] == (
        "sensor.living_area_combined_temperature"
    )


async def test_an_output_of_another_plant_is_refused(hass: HomeAssistant) -> None:
    reference_world(hass)
    await async_import(hass, REFERENCE_PLANT)

    result = await _submit(
        hass, TWO_ZONES.replace("switch.pump}", "switch.home_underfloor_heating_pump}")
    )

    assert result["errors"] == {"base": "output_bound_elsewhere"}
    assert result["description_placeholders"]["where"] == "Pump Pump, switch"
    assert result["description_placeholders"]["entity_id"] == "switch.home_underfloor_heating_pump"
    assert result["description_placeholders"]["other_plant"] == "Home"


async def test_the_same_plant_cannot_be_imported_twice(hass: HomeAssistant) -> None:
    reference_world(hass)
    await async_import(hass, REFERENCE_PLANT)

    result = await _submit(hass, REFERENCE_PLANT)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_a_plant_file_without_an_id_gets_one_that_its_export_keeps(
    hass: HomeAssistant,
) -> None:
    entry = await async_import(hass, TWO_ZONES)

    assert entry.unique_id == entry.data["id"] == entry.runtime_data.plant.id
    assert entry.title == "Flat"


async def test_the_review_names_windows_switches_and_settings_off_their_defaults(
    hass: HomeAssistant,
) -> None:
    text = """
hydronicus: 2
name: Flat
exercise: false
frost_protection: 8
pumps:
  pump:
    switch: switch.pump
    supply_temperature: sensor.supply
    condensation_switch: binary_sensor.dew
zones:
  study:
    temperature: [sensor.study]
    humidity: [sensor.study_rh]
    windows: [binary_sensor.study_window, binary_sensor.study_door]
    max_humidity: 65
    loops:
      floor:
        valves: [switch.study_valve]
        pump: pump
        modes: [heat, cool]
        surface_temperature: sensor.study_floor
        surface_minimum: 18
        condensation_switch: binary_sensor.study_dew
      ceiling:
        valves: [switch.study_ceiling_valve]
        pump: pump
        modes: [heat, cool]
        surface_temperature: sensor.study_ceiling
  hall:
    temperature: [sensor.hall]
    humidity: [sensor.hall_rh]
    max_humidity: null
"""
    result = await _submit(hass, text)

    assert result["step_id"] == "review"
    assert result["description_placeholders"]["summary"].splitlines() == [
        "Plant Flat",
        "- Protection: no exercise; frost protection at 8 °C",
        "- No source: valves open and switched pumps run on demand.",
        "- Pump Pump: switch switch.pump, runs only with a ready loop, "
        "condensation switch binary_sensor.dew",
        "- Zone Study, digital thermostat, "
        "windows binary_sensor.study_window and binary_sensor.study_door, "
        "humidity limit 65 %; loops: "
        "Floor (heat and cool, pump Pump, 1 valve, surface minimum 18 °C, "
        "condensation switch binary_sensor.study_dew); "
        "Ceiling (heat and cool, pump Pump, 1 valve)",
        "- Zone Hall, digital thermostat, no humidity limit; no loop of its own",
        "- Outputs: 3",
    ]


async def test_the_review_leaves_out_settings_at_their_defaults(hass: HomeAssistant) -> None:
    result = await _submit(hass, TWO_ZONES)

    assert result["step_id"] == "review"
    assert result["description_placeholders"]["summary"].splitlines() == [
        "Plant Flat",
        "- No source: valves open and switched pumps run on demand.",
        "- Pump Pump: switch switch.pump, runs only with a ready loop",
        "- Zone Study, digital thermostat; loops: Radiator (heat, pump Pump, 1 valve)",
        "- Outputs: 2",
    ]
