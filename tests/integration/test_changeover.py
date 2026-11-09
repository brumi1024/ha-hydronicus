"""The Mode select's auto option in Home Assistant."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from tests.integration.helpers import (
    REFERENCE_PLANT,
    async_advance,
    async_call,
    async_import,
    reference_world,
)

MODE = "select.home_mode"
STATUS = "sensor.home_status"
CELSIUS = {"unit_of_measurement": "°C"}


async def _home(hass: HomeAssistant) -> str:
    reference_world(hass)
    hass.states.async_set("sensor.outdoor", "28", CELSIUS)
    text = REFERENCE_PLANT.replace(
        "name: Home\n", "name: Home\nchangeover: {outdoor_sensor: sensor.outdoor}\n", 1
    )
    entry = await async_import(hass, text)
    return entry.entry_id


async def test_auto_is_offered_chosen_and_kept_over_a_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry_id = await _home(hass)
    assert hass.states.get(MODE).attributes["options"] == ["off", "heat", "cool", "auto"]
    await async_call(hass, "select", "select_option", entity_id=MODE, option="auto")
    await async_advance(hass, freezer, 5)
    assert hass.states.get(MODE).state == "auto"
    status = hass.states.get(STATUS).attributes
    assert status["requested_mode"] == "auto"
    assert status["changeover"]["mode"] == "cool"
    assert status["reasons"]["changeover"].startswith("auto: cool")
    assert await hass.config_entries.async_reload(entry_id)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(MODE).state == "auto"
    await async_call(hass, "select", "select_option", entity_id=MODE, option="heat")
    await async_advance(hass, freezer, 5)
    assert hass.states.get(MODE).state == "heat"
    assert hass.states.get(STATUS).attributes["changeover"]["mode"] == "cool"
