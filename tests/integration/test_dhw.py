"""The source's DHW in Home Assistant: its entities, the boost actions, and adoption."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.hydronicus.const import DOMAIN
from tests.integration.helpers import (
    REFERENCE_PLANT,
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    entity_id_of,
    reference_world,
)

DHW_SWITCH = "switch.boiler_dhw"
DHW_SETPOINT = "number.boiler_dhw_setpoint"
BOILER = f"""
hydronicus: 2
name: Flat
source:
  request: switch.boiler
  name: Boiler
  write_interval: 300
  dhw: {{switch: {DHW_SWITCH}, setpoint: {DHW_SETPOINT}, step: 1, max_boost: 3600}}
pumps:
  pump: {{switch: switch.pump}}
zones:
  flat:
    temperature: [sensor.flat]
    loops:
      radiator: {{valves: [switch.valve], pump: pump}}
"""
SETPOINT_ATTRIBUTES = {"unit_of_measurement": "°C", "min": 30, "max": 60, "step": 1}


async def _flat(hass: HomeAssistant) -> tuple[Actuators, str, str]:
    actuators = Actuators(hass)
    for entity in ("switch.boiler", "switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set(DHW_SWITCH, "on")
    hass.states.async_set(DHW_SETPOINT, "50", SETPOINT_ATTRIBUTES)
    hass.states.async_set("sensor.flat", "21", {"unit_of_measurement": "°C"})
    entry = await async_import(hass, BOILER)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    plant_id = entry.runtime_data.plant.id
    return (
        actuators,
        entity_id_of(hass, "switch", f"{plant_id}_dhw"),
        entity_id_of(hass, "number", f"{plant_id}_dhw_target"),
    )


async def test_the_dhw_entities_show_and_change_the_owned_settings(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    actuators, switch, target = await _flat(hass)
    assert hass.states.get(switch).state == "on"
    assert hass.states.get(target).state == "50.0"
    assert actuators.to(DHW_SETPOINT) == []

    await async_call(hass, "switch", "turn_off", entity_id=switch)
    await async_call(hass, "number", "set_value", entity_id=target, value=52)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(DHW_SWITCH).state == "off"
    assert float(hass.states.get(DHW_SETPOINT).state) == 52.0
    assert hass.states.get(switch).state == "off"
    assert hass.states.get(target).state == "52.0"

    hass.states.async_set(DHW_SETPOINT, "47", SETPOINT_ATTRIBUTES)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(target).state == "47.0", "a change on the device is adopted"


async def test_a_boost_raises_the_target_and_restores_it(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    _, _, target = await _flat(hass)
    entry_id = hass.config_entries.async_entries(DOMAIN)[0].entry_id

    await async_call(
        hass, DOMAIN, "boost_dhw", config_entry_id=entry_id, temperature=58, duration="00:10:00"
    )
    await async_advance(hass, freezer, 5)
    assert float(hass.states.get(DHW_SETPOINT).state) == 55.0, "a boost keeps the limits"
    attributes = hass.states.get(target).attributes
    assert attributes["boost"] == 55.0 and attributes["boost_until"] is not None
    assert hass.states.get(target).state == "50.0", "the owned target stays"

    await async_advance(hass, freezer, 600, step=30)
    assert float(hass.states.get(DHW_SETPOINT).state) == 50.0
    assert hass.states.get(target).attributes["boost"] is None

    await async_call(hass, DOMAIN, "boost_dhw", config_entry_id=entry_id, temperature=54)
    await async_advance(hass, freezer, 300, step=30)
    await async_call(hass, DOMAIN, "end_dhw_boost", config_entry_id=entry_id)
    await async_advance(hass, freezer, 300, step=30)
    assert float(hass.states.get(DHW_SETPOINT).state) == 50.0


async def test_a_boost_needs_a_plant_with_a_dhw_setpoint(hass: HomeAssistant) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)

    with pytest.raises(ServiceValidationError):
        await async_call(hass, DOMAIN, "boost_dhw", config_entry_id=entry.entry_id, temperature=55)
    with pytest.raises(ServiceValidationError):
        await async_call(hass, DOMAIN, "end_dhw_boost", config_entry_id="missing")
