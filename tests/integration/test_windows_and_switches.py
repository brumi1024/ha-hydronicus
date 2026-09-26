"""The binary sensors a Plant reads besides valve readiness: windows and condensation switches."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.issues import IssueKind
from tests.integration.helpers import (
    async_advance,
    async_call,
    async_import,
    async_set_options,
    set_humidity,
    set_temperature,
)

STUDY = """
hydronicus: 2
name: Flat
pumps:
  pump:
    switch: switch.pump
    supply_temperature: sensor.supply
    condensation_switch: binary_sensor.dew
zones:
  study:
    temperature: [sensor.study]
    humidity: [sensor.study_rh]
    windows: [binary_sensor.study_window]
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      radiator: {valves: [switch.study_valve], pump: pump, modes: [heat, cool]}
"""


async def async_study(hass: HomeAssistant, mode: str, temperature: float) -> None:
    hass.states.async_set("switch.pump", "off")
    hass.states.async_set("switch.study_valve", "off")
    hass.states.async_set("binary_sensor.dew", "off")
    hass.states.async_set("binary_sensor.study_window", "off")
    set_temperature(hass, "sensor.study", temperature)
    set_temperature(hass, "sensor.supply", 22.0)
    set_humidity(hass, "sensor.study_rh", 50.0)
    entry = await async_import(hass, STUDY)
    # Armed in Dry run, so the loop runs as proposals.
    await async_set_options(hass, entry, armed=["switch.pump", "switch.study_valve"])
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option=mode)
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode=mode)


def missing_bindings(hass: HomeAssistant) -> list[str]:
    return sorted(
        issue.translation_placeholders["entity_id"]
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == IssueKind.MISSING_BINDING
    )


async def test_an_open_window_turns_the_zone_demand_off_and_says_why(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await async_study(hass, "heat", 19.0)
    demand = "binary_sensor.study_heating_demand"
    assert hass.states.get(demand).state == "on"

    hass.states.async_set("binary_sensor.study_window", "on")
    await async_advance(hass, freezer, 59)
    assert hass.states.get(demand).state == "on"
    await async_advance(hass, freezer, 2)
    assert hass.states.get(demand).state == "off"
    assert hass.states.get(demand).attributes["reason"] == "window open"
    assert hass.states.get("climate.study").attributes["reason"] == "window open"
    assert hass.states.get("climate.study").attributes["hvac_action"] == "idle"

    hass.states.async_set("binary_sensor.study_window", "off")
    await async_advance(hass, freezer, 59)
    assert hass.states.get(demand).state == "off"
    await async_advance(hass, freezer, 2)
    assert hass.states.get(demand).state == "on"
    assert hass.states.get("climate.study").attributes["reason"].startswith("heat to 21.0 °C")


async def test_a_missing_window_is_a_repair_and_reads_closed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await async_study(hass, "heat", 19.0)
    hass.states.async_remove("binary_sensor.study_window")
    await async_advance(hass, freezer, 120, step=60)

    assert hass.states.get("binary_sensor.study_heating_demand").state == "on"
    assert missing_bindings(hass) == ["binary_sensor.study_window"]


async def test_a_condensation_switch_blocks_cooling_and_a_missing_one_is_a_repair(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await async_study(hass, "cool", 26.0)
    reasons = hass.states.get("sensor.flat_status").attributes["reasons"]
    assert "study.radiator.guard" not in reasons and reasons["study.radiator"] == "wanted"

    hass.states.async_set("binary_sensor.dew", "on")
    await hass.async_block_till_done()
    reasons = hass.states.get("sensor.flat_status").attributes["reasons"]
    assert reasons["study.radiator.guard"] == (
        "condensation guard blocks: condensation switch binary_sensor.dew on"
    )
    assert reasons["study.radiator"] == "dropped: condensation guard blocks"

    hass.states.async_remove("binary_sensor.dew")
    await async_advance(hass, freezer, 600, step=60)
    reasons = hass.states.get("sensor.flat_status").attributes["reasons"]
    assert reasons["study.radiator.guard"] == (
        "condensation guard blocks: condensation switch binary_sensor.dew unavailable"
    )
    assert missing_bindings(hass) == ["binary_sensor.dew"]

    hass.states.async_set("binary_sensor.dew", "off")
    await async_advance(hass, freezer, 299, step=60)
    assert "study.radiator.guard" in hass.states.get("sensor.flat_status").attributes["reasons"]
    await async_advance(hass, freezer, 2)
    assert "study.radiator.guard" not in hass.states.get("sensor.flat_status").attributes["reasons"]
    assert missing_bindings(hass) == []
