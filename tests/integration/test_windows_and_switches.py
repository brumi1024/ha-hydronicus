"""The binary sensors a Plant reads besides valve readiness: windows and condensation switches.

It also covers the Repair of a condensation input, a switch or a guard
reference, that stays unusable.
"""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry
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


async def async_study(hass: HomeAssistant, mode: str, temperature: float) -> ConfigEntry:
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
    return entry


def repairs(hass: HomeAssistant, kind: IssueKind) -> list[ir.IssueEntry]:
    return [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == kind
    ]


def missing_bindings(hass: HomeAssistant) -> list[str]:
    return sorted(
        issue.translation_placeholders["entity_id"]
        for issue in repairs(hass, IssueKind.MISSING_BINDING)
    )


def blocked_zones(hass: HomeAssistant) -> dict[str, str]:
    return hass.states.get("sensor.flat_status").attributes["blocked_zones"]


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
    assert blocked_zones(hass) == {"study": "window open"}
    assert hass.states.get("sensor.flat_status").state == "idle"

    hass.states.async_set("binary_sensor.study_window", "off")
    await async_advance(hass, freezer, 59)
    assert hass.states.get(demand).state == "off"
    await async_advance(hass, freezer, 2)
    assert hass.states.get(demand).state == "on"
    assert blocked_zones(hass) == {}
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


async def test_a_zone_that_frost_protection_heats_is_not_blocked_by_its_window(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await async_study(hass, "heat", 19.0)
    hass.states.async_set("binary_sensor.study_window", "on")
    await async_advance(hass, freezer, 61)
    assert blocked_zones(hass) == {"study": "window open"}

    set_temperature(hass, "sensor.study", 3.0)
    await hass.async_block_till_done()
    demand = hass.states.get("binary_sensor.study_heating_demand")
    assert demand.state == "on"
    assert demand.attributes["reason"].startswith("frost protection")
    assert blocked_zones(hass) == {}


async def test_an_unavailable_condensation_switch_raises_a_repair_after_ten_minutes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    # Whatever the Plant mode: the switch is needed before cooling can start.
    await async_study(hass, "heat", 19.0)

    # A short dropout raises nothing, and the next one starts the 10 minutes again.
    hass.states.async_set("binary_sensor.dew", "unavailable")
    await hass.async_block_till_done()
    await async_advance(hass, freezer, 300, step=300)
    hass.states.async_set("binary_sensor.dew", "off")
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.dew", "unknown")
    await hass.async_block_till_done()
    await async_advance(hass, freezer, 599, step=599)
    assert repairs(hass, IssueKind.CONDENSATION_INPUT_UNUSABLE) == []

    await async_advance(hass, freezer, 2)
    (issue,) = repairs(hass, IssueKind.CONDENSATION_INPUT_UNUSABLE)
    assert issue.translation_placeholders == {
        "plant": "Flat",
        "entity_id": "binary_sensor.dew",
        "input": "condensation switch",
        "loops": "loop Study / Radiator",
    }
    assert issue.severity is ir.IssueSeverity.ERROR and not issue.is_fixable

    hass.states.async_set("binary_sensor.dew", "off")
    await hass.async_block_till_done()
    assert repairs(hass, IssueKind.CONDENSATION_INPUT_UNUSABLE) == []


async def test_a_stale_condensation_reference_raises_a_repair(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await async_study(hass, "cool", 26.0)

    # The supply temperature is stale 1800 seconds after its last report.
    await async_advance(hass, freezer, 1801, step=1801)
    reasons = hass.states.get("sensor.flat_status").attributes["reasons"]
    assert reasons["study.radiator.guard"] == (
        "condensation guard blocks: no usable condensation reference or dew point"
    )
    await async_advance(hass, freezer, 599, step=599)
    assert repairs(hass, IssueKind.CONDENSATION_INPUT_UNUSABLE) == []
    await async_advance(hass, freezer, 2)
    (issue,) = repairs(hass, IssueKind.CONDENSATION_INPUT_UNUSABLE)
    assert issue.translation_placeholders["entity_id"] == "sensor.supply"
    assert issue.translation_placeholders["input"] == "supply temperature sensor"

    set_temperature(hass, "sensor.supply", 22.0)
    await hass.async_block_till_done()
    assert repairs(hass, IssueKind.CONDENSATION_INPUT_UNUSABLE) == []


async def test_the_ten_minutes_of_a_condensation_input_count_across_a_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_study(hass, "cool", 26.0)
    hass.states.async_set("binary_sensor.dew", "unavailable")
    await hass.async_block_till_done()
    await async_advance(hass, freezer, 300, step=300)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert repairs(hass, IssueKind.CONDENSATION_INPUT_UNUSABLE) == []
    await async_advance(hass, freezer, 301, step=301)
    assert len(repairs(hass, IssueKind.CONDENSATION_INPUT_UNUSABLE)) == 1


async def test_a_missing_condensation_input_has_only_its_own_repair(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await async_study(hass, "cool", 26.0)
    hass.states.async_remove("binary_sensor.dew")
    hass.states.async_remove("sensor.supply")
    await async_advance(hass, freezer, 900, step=300)

    assert repairs(hass, IssueKind.CONDENSATION_INPUT_UNUSABLE) == []
    assert missing_bindings(hass) == ["binary_sensor.dew", "sensor.supply"]
