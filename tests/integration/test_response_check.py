"""The response check's Repair and Status, and window detection on the zone entities."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.issues import IssueKind
from tests.integration.helpers import (
    REFERENCE_PLANT,
    Actuators,
    async_advance,
    async_call,
    async_heat_living_area,
    async_import,
    async_set_options,
    set_temperature,
    set_zone_temperature,
)


def _issues(hass: HomeAssistant) -> dict[str, ir.IssueEntry]:
    return {
        issue.translation_key or "": issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN
    }


async def _hold(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, zone: str, value: float, seconds: float
) -> None:
    """Keep a zone at ``value`` for ``seconds``, its sensors reporting every 10 minutes."""
    for _ in range(int(seconds // 600)):
        set_zone_temperature(hass, zone, value)
        await async_advance(hass, freezer, 600, step=60)


async def test_a_zone_that_does_not_warm_raises_a_repair_and_degrades_the_status(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, actuators: Actuators
) -> None:
    await async_heat_living_area(hass, freezer)
    status = "sensor.home_status"
    await _hold(hass, freezer, "living_area", 20.0, 3 * 3600 - 600)
    assert IssueKind.ZONE_NOT_RESPONDING not in _issues(hass)
    assert hass.states.get(status).state == "heating"

    await _hold(hass, freezer, "living_area", 20.0, 1200)
    issue = _issues(hass)[IssueKind.ZONE_NOT_RESPONDING]
    assert issue.translation_placeholders == {
        "plant": "Home",
        "zone": "Living area",
        "mode": "heating",
        "hours": "3",
        "progress": "0.2",
    }
    assert issue.severity is ir.IssueSeverity.ERROR and not issue.is_fixable
    assert hass.states.get(status).state == "degraded"
    assert list(hass.states.get(status).attributes["zones_not_responding"]) == ["living_area"]
    assert hass.states.get("switch.home_living_area_floor_heating_valve").state == "on", (
        "the check never changes control"
    )

    await _hold(hass, freezer, "living_area", 20.2, 600)
    assert IssueKind.ZONE_NOT_RESPONDING not in _issues(hass)
    assert hass.states.get(status).state == "heating"
    assert hass.states.get(status).attributes["zones_not_responding"] == {}


async def test_a_zone_without_the_check_raises_nothing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, actuators: Actuators
) -> None:
    text = REFERENCE_PLANT.replace(
        "  living_area:\n", "  living_area:\n    response_check: false\n", 1
    )
    assert text != REFERENCE_PLANT
    await async_heat_living_area(hass, freezer, text)
    await _hold(hass, freezer, "living_area", 20.0, 4 * 3600)
    assert IssueKind.ZONE_NOT_RESPONDING not in _issues(hass)
    assert hass.states.get("sensor.home_status").state == "heating"


DETECTING = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump}
zones:
  study:
    temperature: [sensor.study]
    thermostat: {digital: {min_on: 0, min_off: 0}}
    window_detection: true
    loops:
      radiator: {valves: [switch.study_valve], pump: pump}
"""


async def test_a_sudden_fall_closes_the_zone_as_an_open_window_would(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, actuators: Actuators
) -> None:
    set_temperature(hass, "sensor.study", 20.0)
    for entity_id in ("switch.pump", "switch.study_valve"):
        hass.states.async_set(entity_id, "off")
    entry = await async_import(hass, DETECTING)
    await async_set_options(hass, entry, armed={"switch.pump", "switch.study_valve"}, control=True)
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")
    await async_advance(hass, freezer, 60, step=5)
    demand = "binary_sensor.study_heating_demand"
    assert hass.states.get(demand).state == "on"

    set_temperature(hass, "sensor.study", 19.4)
    await hass.async_block_till_done()
    assert hass.states.get(demand).state == "off"
    assert hass.states.get(demand).attributes["reason"] == "window open: temperature fell 0.6 K"
    blocked = hass.states.get("sensor.flat_status").attributes["blocked_zones"]
    assert blocked == {"study": "window open: temperature fell 0.6 K"}
    holds = hass.states.get(demand).attributes["holds"]
    assert [hold["kind"] for hold in holds] == ["window_detected"]

    await async_advance(hass, freezer, 600, step=30)
    assert hass.states.get(demand).state == "on", "the temperature settled for 10 minutes"
