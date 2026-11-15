"""The heating curve in Home Assistant: its offset number, Status attribute, and outdoor Repair."""

from __future__ import annotations

from dataclasses import replace

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.hydronicus.const import DOMAIN
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    entity_id_of,
)

SUPPLY = "number.boiler_supply"
FLAT = f"""
hydronicus: 2
name: Flat
source:
  request: switch.boiler
  name: Boiler
  supply: {{entity: {SUPPLY}, outdoor_sensor: sensor.outdoor, offset: 1, max_age: 900}}
pumps:
  pump: {{switch: switch.pump}}
zones:
  flat:
    temperature: [sensor.flat]
    loops:
      radiator: {{valves: [switch.valve], pump: pump}}
"""
CELSIUS = {"unit_of_measurement": "°C"}


async def _flat(hass: HomeAssistant) -> tuple[Actuators, str, str]:
    actuators = Actuators(hass)
    for entity in ("switch.boiler", "switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set(SUPPLY, "30", {**CELSIUS, "min": 20, "max": 60, "step": 0.5})
    hass.states.async_set("sensor.flat", "21", CELSIUS)
    hass.states.async_set("sensor.outdoor", "5", CELSIUS)
    entry = await async_import(hass, FLAT)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    plant_id = entry.runtime_data.plant.id
    return (
        actuators,
        entity_id_of(hass, "number", f"{plant_id}_heating_curve_offset"),
        entity_id_of(hass, "sensor", f"{plant_id}_status"),
    )


async def test_the_offset_number_shifts_the_curve_and_survives_a_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    _, offset, status = await _flat(hass)
    assert hass.states.get(offset).state == "1.0"
    curve = hass.states.get(status).attributes["heating_curve"]
    assert curve == {
        "outdoor": 5.0,
        "fallback": False,
        "warm_weather": False,
        "curve": 35.0,
        "offset": 1.0,
        "room_trim": 0.0,
        "learned": None,
    }
    await async_call(hass, "number", "set_value", entity_id=offset, value=-2)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(offset).state == "-2.0"
    assert hass.states.get(status).attributes["heating_curve"]["offset"] == -2.0

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(offset).state == "-2.0"


async def test_a_lost_outdoor_sensor_raises_its_repair_after_ten_minutes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await _flat(hass)
    hass.states.async_set("sensor.outdoor", "unavailable")
    await async_advance(hass, freezer, 60)

    def raised() -> list[ir.IssueEntry]:
        return [
            issue
            for (domain, _), issue in ir.async_get(hass).issues.items()
            if domain == DOMAIN and issue.translation_key == "outdoor_sensor_unusable"
        ]

    assert raised() == []
    await async_advance(hass, freezer, 600)
    [issue] = raised()
    assert issue.translation_placeholders is not None
    assert issue.translation_placeholders["entity_id"] == "sensor.outdoor"
    assert "frost protection" in issue.translation_placeholders["effect"]
    hass.states.async_set("sensor.outdoor", "4", CELSIUS)
    await async_advance(hass, freezer, 5)
    assert raised() == []


# The flat leads the curve, its digital thermostat at its default 21 °C.
TRIMMED = FLAT.replace(
    "offset: 1, max_age: 900}",
    "offset: 1, max_age: 900, room_influence: {zones: [flat], learn_after: 0}}",
)


async def test_the_room_trim_sensor_shows_its_parts_and_the_button_resets_it(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    for entity in ("switch.boiler", "switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set(SUPPLY, "30", {**CELSIUS, "min": 20, "max": 60, "step": 0.5})
    hass.states.async_set("sensor.flat", "20.5", CELSIUS)
    hass.states.async_set("sensor.outdoor", "5", CELSIUS)
    entry = await async_import(hass, TRIMMED)
    runtime = entry.runtime_data
    await async_set_options(hass, entry, armed=runtime.plant.outputs(), control=True)
    plant_id = runtime.plant.id
    trim = entity_id_of(hass, "sensor", f"{plant_id}_room_trim")
    reset = entity_id_of(hass, "button", f"{plant_id}_reset_room_trim")
    state = hass.states.get(trim)
    assert state is not None and state.state == "0.3"
    assert state.attributes["unit_of_measurement"] == "K"
    assert state.attributes["proportional"] == 0.3
    assert state.attributes["learned"] == 0.0
    assert state.attributes["lead_zone"] == "flat"
    assert state.attributes["filtered_error"] == 0.5

    runtime.state = replace(runtime.state, room_trim=replace(runtime.state.room_trim, learned=1.25))
    runtime.request_evaluation()
    await async_advance(hass, freezer, 5)
    assert hass.states.get(trim).attributes["learned"] == pytest.approx(1.25, abs=0.01)

    await async_call(hass, "button", "press", entity_id=reset)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(trim).attributes["learned"] == pytest.approx(0.0, abs=0.01)
    assert runtime.supply_command is None
