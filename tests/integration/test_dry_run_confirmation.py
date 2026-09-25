"""The Dry run confirmation authorizes exactly the outputs it showed."""

from __future__ import annotations

import copy

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hydronicus.const import CONF_DRY_RUN, CONF_DRY_RUN_CONFIRMATION
from custom_components.hydronicus.entry_configuration import output_authorization
from tests.integration.test_source_subentry import SELECTOR_ID, _entry


async def _show_confirmation(hass: HomeAssistant, entry) -> dict:
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DRY_RUN: False}
    )
    assert result["step_id"] == "dry_run_confirmation"
    return result


async def test_confirmation_refuses_outputs_changed_after_it_was_shown(
    hass: HomeAssistant,
) -> None:
    """A concurrent rebinding is shown again instead of being authorized unseen."""
    hass.states.async_set("sensor.living_temperature", "19.0")
    hass.states.async_set("switch.boiler_room_heater", "off")
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    result = await _show_confirmation(hass, entry)
    assert "switch.floor_valve" in result["description_placeholders"]["outputs"]

    # A concurrent edit, such as another browser tab, rebinds the valve.
    data = copy.deepcopy(dict(entry.data))
    data["topology"]["valves"][0]["entity_id"] = "switch.boiler_room_heater"
    hass.config_entries.async_update_entry(entry, data=data)
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DRY_RUN_CONFIRMATION: True}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dry_run_confirmation"
    assert result["errors"] == {"base": "outputs_changed"}
    assert "switch.boiler_room_heater" in result["description_placeholders"]["outputs"]
    assert "switch.floor_valve" not in result["description_placeholders"]["outputs"]
    assert entry.data[CONF_DRY_RUN] is True
    assert "output_authorization" not in entry.data
    assert entry.runtime_data.dry_run is True

    # Confirming the list that is now shown authorizes exactly that list.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DRY_RUN_CONFIRMATION: True}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_DRY_RUN] is False
    assert entry.data["output_authorization"] == output_authorization(entry.data)
    assert [output["entity_id"] for output in entry.data["output_authorization"]["outputs"]] == [
        "switch.floor_pump",
        "switch.boiler_room_heater",
    ]


async def test_confirmation_lists_the_source_selector(hass: HomeAssistant) -> None:
    """A configured source selector is part of what the user reviews."""
    hass.states.async_set("sensor.living_temperature", "19.0")
    entry = _entry()
    entry.data["topology"]["source_selector"] = {
        "id": SELECTOR_ID,
        "name": "Heat source selector",
        "entity_id": "select.heat_source",
    }
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    result = await _show_confirmation(hass, entry)

    assert "select.heat_source" in result["description_placeholders"]["outputs"]
