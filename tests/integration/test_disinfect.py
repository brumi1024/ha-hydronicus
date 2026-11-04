"""The disinfection cycle in Home Assistant: its setpoint, Last disinfection sensor, and Repair."""

from __future__ import annotations

from datetime import datetime

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.hydronicus.const import DOMAIN
from tests.integration.helpers import Actuators, async_advance, async_import, async_set_options

SETPOINT = "number.boiler_dhw_setpoint"
TANK = "sensor.tank"
FLAT = f"""
hydronicus: 2
name: Flat
source:
  request: switch.boiler
  name: Boiler
  dhw:
    setpoint: {SETPOINT}
    disinfect: {{tank_temperature: {TANK}, interval: 86400, hold: 600, timeout: 3600}}
pumps:
  pump: {{switch: switch.pump}}
zones:
  flat:
    temperature: [sensor.flat]
    loops:
      radiator: {{valves: [switch.valve], pump: pump}}
"""
LAST = "sensor.boiler_last_disinfection"
CELSIUS = {"unit_of_measurement": "°C"}
SETPOINT_ATTRIBUTES = {**CELSIUS, "min": 30, "max": 70, "step": 1}
DAY = 86400


async def _flat(hass: HomeAssistant) -> Actuators:
    actuators = Actuators(hass)
    for entity in ("switch.boiler", "switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set(SETPOINT, "50", SETPOINT_ATTRIBUTES)
    hass.states.async_set("sensor.flat", "21", CELSIUS)
    hass.states.async_set(TANK, "50", CELSIUS)
    entry = await async_import(hass, FLAT)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    return actuators


def disinfect_issues(hass: HomeAssistant) -> list[ir.IssueEntry]:
    return [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == "disinfect_failed"
    ]


async def test_a_cycle_heats_the_tank_holds_it_and_records_its_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await _flat(hass)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(LAST).state == "unknown"
    await async_advance(hass, freezer, DAY, step=60)
    assert float(hass.states.get(SETPOINT).state) == 60.0
    assert hass.states.get(LAST).attributes["running"] is True
    hass.states.async_set(TANK, "60", CELSIUS)
    await async_advance(hass, freezer, 5)
    await async_advance(hass, freezer, 600, step=60)
    assert float(hass.states.get(SETPOINT).state) == 50.0
    assert datetime.fromisoformat(hass.states.get(LAST).state) is not None
    assert hass.states.get(LAST).attributes["running"] is False
    assert disinfect_issues(hass) == []


async def test_a_cycle_that_times_out_raises_its_repair(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await _flat(hass)
    await async_advance(hass, freezer, DAY + 5, step=60)
    assert float(hass.states.get(SETPOINT).state) == 60.0
    await async_advance(hass, freezer, 3600, step=60)
    assert float(hass.states.get(SETPOINT).state) == 50.0
    assert len(disinfect_issues(hass)) == 1
    assert hass.states.get(LAST).state == "unknown"
