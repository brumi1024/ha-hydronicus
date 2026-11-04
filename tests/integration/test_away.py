"""The Away switch and actions in Home Assistant."""

from __future__ import annotations

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.hydronicus.const import DOMAIN
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
)

FLAT = """
hydronicus: 2
name: Flat
away: {heat_target: 15}
pumps:
  pump: {switch: switch.pump}
zones:
  flat:
    temperature: [sensor.flat]
    loops:
      radiator: {valves: [switch.valve], pump: pump}
"""
AWAY = "switch.flat_away"
CLIMATE = "climate.flat"


async def _flat(hass: HomeAssistant) -> str:
    Actuators(hass)
    for entity in ("switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set("sensor.flat", "20", {"unit_of_measurement": "°C"})
    entry = await async_import(hass, FLAT)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id=CLIMATE, hvac_mode="heat")
    return entry.entry_id


def effective(hass: HomeAssistant) -> float:
    return float(hass.states.get(CLIMATE).attributes["effective_target"])


async def test_the_switch_holds_the_away_target_and_survives_a_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry_id = await _flat(hass)
    await async_advance(hass, freezer, 5)
    assert effective(hass) == 21.0
    await async_call(hass, "switch", "turn_on", entity_id=AWAY)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(AWAY).state == "on"
    assert effective(hass) == 15.0
    assert hass.states.get(CLIMATE).attributes["heat_target"] == 21.0
    assert await hass.config_entries.async_reload(entry_id)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(AWAY).state == "on" and effective(hass) == 15.0
    await async_call(hass, "switch", "turn_off", entity_id=AWAY)
    await async_advance(hass, freezer, 5)
    assert effective(hass) == 21.0


async def test_set_away_ends_by_itself_at_its_return_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry_id = await _flat(hass)
    until = dt_util.utcnow() + timedelta(hours=1)
    await async_call(hass, DOMAIN, "set_away", config_entry_id=entry_id, until=until)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(AWAY).attributes["until"] == until.isoformat()
    assert effective(hass) == 15.0
    await async_advance(hass, freezer, 3600)
    assert hass.states.get(AWAY).state == "off"
    assert effective(hass) == 21.0


async def test_set_away_refuses_a_return_time_in_the_past(hass: HomeAssistant) -> None:
    entry_id = await _flat(hass)
    with pytest.raises(ServiceValidationError):
        await async_call(
            hass,
            DOMAIN,
            "set_away",
            config_entry_id=entry_id,
            until=dt_util.utcnow() - timedelta(minutes=1),
        )
    await async_call(hass, DOMAIN, "end_away", config_entry_id=entry_id)
    assert hass.states.get(AWAY).state == "off"
