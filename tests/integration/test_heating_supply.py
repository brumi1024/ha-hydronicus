"""The heating supply in Home Assistant: its select, its fixed temperature, and adoption."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from custom_components.hydronicus.const import DOMAIN
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    entity_id_of,
)

CURVE = "switch.heat_pump_weather_curve"
SUPPLY = "number.heat_pump_supply"
REQUEST = "switch.heat_pump"
FLAT = f"""
hydronicus: 2
name: Flat
source:
  request: {REQUEST}
  name: Heat pump
  min_on: 0
  min_off: 0
  weather_curve: {{switch: {CURVE}}}
  supply:
    entity: {SUPPLY}
    outdoor_sensor: sensor.outdoor
    heat_temperature: 33
    minimum: 20
    maximum: 50
    step: 1
    max_age: 900
pumps:
  pump: {{switch: switch.pump}}
zones:
  flat:
    temperature: [sensor.flat]
    thermostat: {{digital: {{min_on: 0, min_off: 0}}}}
    loops:
      radiator: {{valves: [switch.valve], pump: pump}}
"""
CELSIUS = {"unit_of_measurement": "°C"}


async def _flat(hass: HomeAssistant) -> tuple[Actuators, str, str, str]:
    actuators = Actuators(hass)
    for entity in (REQUEST, "switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set(CURVE, "on")
    hass.states.async_set(SUPPLY, "30", {**CELSIUS, "min": 20, "max": 60, "step": 1})
    hass.states.async_set("sensor.flat", "21", CELSIUS)
    hass.states.async_set("sensor.outdoor", "5", CELSIUS)
    entry = await async_import(hass, FLAT)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    plant_id = entry.runtime_data.plant.id
    mode = entity_id_of(hass, "select", f"{plant_id}_mode")
    await async_call(hass, "select", "select_option", entity_id=mode, option="heat")
    return (
        actuators,
        entity_id_of(hass, "select", f"{plant_id}_heating_supply"),
        entity_id_of(hass, "number", f"{plant_id}_heating_supply_temperature"),
        entity_id_of(hass, "number", f"{plant_id}_heating_curve_offset"),
    )


async def test_the_select_offers_the_strategies_and_starts_from_what_the_source_does(
    hass: HomeAssistant,
) -> None:
    _, select, fixed, offset = await _flat(hass)
    state = hass.states.get(select)
    assert state.state == "source_curve"
    assert state.attributes["options"] == ["source_curve", "fixed", "curve"]
    assert hass.states.get(fixed).state == "unavailable"
    assert hass.states.get(offset).state == "unavailable"


async def test_a_fixed_temperature_chosen_in_home_assistant_survives_a_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    actuators, select, fixed, _ = await _flat(hass)
    await async_call(hass, "select", "select_option", entity_id=select, option="fixed")
    await async_advance(hass, freezer, 5)
    assert hass.states.get(select).state == "fixed"
    assert hass.states.get(CURVE).state == "off"
    assert hass.states.get(fixed).state == "33.0"

    await async_call(hass, "number", "set_value", entity_id=fixed, value=34.6)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(fixed).state == "35.0", "rounded to the setpoint's step"
    assert hass.states.get(SUPPLY).state == "35.0"
    assert any(call.entity_id == SUPPLY for call in actuators.calls)

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(select).state == "fixed"
    assert hass.states.get(fixed).state == "35.0"


async def test_the_curve_turned_off_elsewhere_is_adopted_and_not_turned_on_again(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    actuators, select, fixed, _ = await _flat(hass)
    hass.states.async_set(SUPPLY, "34", {**CELSIUS, "min": 20, "max": 60, "step": 1})
    hass.states.async_set(CURVE, "off")
    await async_advance(hass, freezer, 60)
    assert hass.states.get(select).state == "fixed"
    assert hass.states.get(fixed).state == "34.0"
    assert hass.states.get(CURVE).state == "off"
    assert not [call for call in actuators.calls if call.entity_id in (CURVE, SUPPLY)]

    hass.states.async_set(CURVE, "on")
    await async_advance(hass, freezer, 60)
    assert hass.states.get(select).state == "source_curve"
    assert not [call for call in actuators.calls if call.entity_id == CURVE]
