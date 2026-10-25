"""The source in Home Assistant: its DHW entities and boost actions, the inhibit, and no load."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir

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


NO_LOAD = """
hydronicus: 2
name: Flat
source:
  request: switch.boiler
  name: Heat pump
  min_on: 0
  min_off: 0
  inhibit_sensor: input_boolean.fireplace_heating
  no_load:
    supply_temperature: sensor.water_outlet
    return_temperature: sensor.water_inlet
    compressor_sensor: sensor.compressor_frequency
pumps:
  pump: {switch: switch.pump}
zones:
  flat:
    temperature: [sensor.flat]
    loops:
      radiator: {valves: [{entity: switch.valve, opening_time: 10}], pump: pump}
"""


def _issue_ids(hass: HomeAssistant) -> set[str]:
    return {
        issue.translation_key or ""
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN
    }


async def test_a_source_that_keeps_running_without_a_load_raises_a_repair(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    Actuators(hass)
    for entity in ("switch.boiler", "switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set("input_boolean.fireplace_heating", "off")

    def report() -> None:
        """The bridge republishes its state every minute, so it stays fresh."""
        hass.states.async_set("sensor.flat", "19", {"unit_of_measurement": "°C"})
        hass.states.async_set("sensor.compressor_frequency", "35", {"unit_of_measurement": "Hz"})
        for entity in ("sensor.water_outlet", "sensor.water_inlet"):
            hass.states.async_set(entity, "34", {"unit_of_measurement": "°C"})

    async def advance(seconds: float) -> None:
        for _ in range(int(seconds // 60)):
            report()
            await async_advance(hass, freezer, 60, step=10)

    report()
    entry = await async_import(hass, NO_LOAD)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.flat", hvac_mode="heat")

    await advance(120)
    assert hass.states.get("switch.boiler").state == "on"
    await advance(600)
    assert hass.states.get("switch.boiler").state == "off", "the guard releases the source"
    assert "source_no_load" not in _issue_ids(hass), "one trip may be a fluke"

    await advance(1800 + 900)
    assert "source_no_load" in _issue_ids(hass), "a second trip within a day is a pattern"

    hass.states.async_set("input_boolean.fireplace_heating", "on")
    await advance(3600)
    assert hass.states.get("switch.boiler").state == "off", "the buffer keeps the source off"
    assert hass.states.get("switch.valve").state == "on", "while the zone still circulates"


async def test_the_compressor_diagnostics_count_starts_and_cycles(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    text = NO_LOAD.replace(
        "  inhibit_sensor: input_boolean.fireplace_heating\n",
        "  compressor_sensor: sensor.compressor_frequency\n",
    )
    hass.states.async_set("sensor.compressor_frequency", "0", {"unit_of_measurement": "Hz"})
    entry = await async_import(hass, text)
    plant_id = entry.runtime_data.plant.id
    starts = entity_id_of(hass, "sensor", f"{plant_id}_compressor_starts")
    cycle = entity_id_of(hass, "sensor", f"{plant_id}_compressor_cycle")
    assert hass.states.get(starts).state == "0"
    assert hass.states.get(cycle).state == "unknown"

    for _ in range(2):
        hass.states.async_set("sensor.compressor_frequency", "40", {"unit_of_measurement": "Hz"})
        await async_advance(hass, freezer, 600, step=60)
        hass.states.async_set("sensor.compressor_frequency", "0", {"unit_of_measurement": "Hz"})
        await async_advance(hass, freezer, 300, step=60)
    assert hass.states.get(starts).state == "2"
    assert float(hass.states.get(cycle).state) == 10.0
