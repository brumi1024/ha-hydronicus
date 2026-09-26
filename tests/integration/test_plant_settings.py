"""Plant settings: arm outputs with their roles, and show the plant file (contract K6)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hydronicus.core.plant_file import read_plant_file, write_plant_file
from tests.integration.helpers import (
    FLOOR_PUMP,
    LIVING_CEILING,
    LIVING_FLOOR,
    REFERENCE_OUTPUTS,
    REFERENCE_PLANT,
    SOURCE_MODE,
    SOURCE_REQUEST,
    TOWEL_PUMP,
    async_choose,
    async_import,
    async_set_options,
    async_submit,
    reference_world,
    suggested,
)


async def test_arm_outputs_lists_every_output_with_its_role(hass: HomeAssistant) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    await async_set_options(hass, entry, armed=[TOWEL_PUMP], control=True)
    flow = hass.config_entries.options
    result = await flow.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["arm", "plant_file"]

    result = await async_choose(flow, result, "arm")
    (key,) = result["data_schema"].schema
    options = result["data_schema"].schema[key].serialize()["selector"]["select"]["options"]
    labels = {option["value"]: option["label"] for option in options}
    assert list(labels) == list(REFERENCE_OUTPUTS)
    assert labels[SOURCE_REQUEST] == f"Source request switch: {SOURCE_REQUEST}"
    assert labels[SOURCE_MODE] == f"Source mode select: {SOURCE_MODE}"
    assert labels[FLOOR_PUMP] == f"Pump Floor: {FLOOR_PUMP}"
    assert labels[LIVING_FLOOR] == f"Valve of Living area / Floor: {LIVING_FLOOR}"
    assert suggested(result, "outputs") == [TOWEL_PUMP]

    result = await async_submit(flow, result, {"outputs": [LIVING_CEILING, FLOOR_PUMP]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.options == {"armed_outputs": [FLOOR_PUMP, LIVING_CEILING], "control": True}


async def test_the_plant_file_in_plant_settings_round_trips(hass: HomeAssistant) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    flow = hass.config_entries.options
    result = await flow.async_init(entry.entry_id)

    result = await async_choose(flow, result, "plant_file")

    # Shown in a closing dialog, since nothing is saved: an options entry would say
    # "Options successfully saved".
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "plant_file"
    text = result["description_placeholders"]["plant_file"]
    assert text == write_plant_file(entry.runtime_data.plant)
    assert read_plant_file(text) == entry.runtime_data.plant
    assert entry.options == {"armed_outputs": [], "control": False}
