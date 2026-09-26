"""Thermostats, cooling entities, missing bindings, and diagnostics (contracts K5 and K7)."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.core.model import Mode, Preset
from custom_components.hydronicus.core.step import DigitalThermostatState
from custom_components.hydronicus.diagnostics import async_get_config_entry_diagnostics
from custom_components.hydronicus.issues import IssueKind
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    set_humidity,
    set_temperature,
)

EXTERNAL = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump, overrun: 0}
zones:
  den:
    thermostat: {external: climate.den_thermostat}
    loops:
      radiator: {valves: [switch.den_valve], pump: pump}
"""

COOLING = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump, supply_temperature: sensor.supply}
zones:
  study:
    temperature: [sensor.study]
    humidity: [sensor.study_rh]
    thermostat: {digital: {target: 20.5, presets: {comfort: 22, eco: 19}}}
    loops:
      ceiling: {valves: [switch.study_valve], pump: pump, modes: [heat, cool]}
"""


def outputs_off(hass: HomeAssistant, *entity_ids: str) -> None:
    for entity_id in entity_ids:
        hass.states.async_set(entity_id, "off")


async def test_an_external_thermostat_demands_through_its_hvac_action(
    hass: HomeAssistant, actuators: Actuators
) -> None:
    outputs_off(hass, "switch.pump", "switch.den_valve")
    hass.states.async_set("climate.den_thermostat", "heat", {"hvac_action": "idle"})
    entry = await async_import(hass, EXTERNAL)
    await async_set_options(hass, entry, armed=["switch.pump", "switch.den_valve"], control=True)
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    assert hass.states.get("climate.den") is None, "an external thermostat has no Hydronicus one"
    assert actuators.calls == []

    hass.states.async_set("climate.den_thermostat", "heat", {"hvac_action": "heating"})
    await hass.async_block_till_done()
    assert actuators.shorts() == ["switch.den_valve:on"]
    demand = hass.states.get("binary_sensor.den_heating_demand")
    assert demand.state == "on" and demand.attributes["level"] == 1.0

    hass.states.async_set("climate.den_thermostat", "unavailable")
    await hass.async_block_till_done()
    status = hass.states.get("sensor.flat_status").attributes
    assert status["blocked_zones"] == {"den": "thermostat unavailable"}
    assert actuators.shorts()[-1] == "switch.den_valve:off"


async def test_a_zone_that_cools_gets_cooling_demand_and_a_dew_point(
    hass: HomeAssistant, actuators: Actuators
) -> None:
    outputs_off(hass, "switch.pump", "switch.study_valve")
    set_temperature(hass, "sensor.study", 26.0)
    set_humidity(hass, "sensor.study_rh", 50.0)
    set_temperature(hass, "sensor.supply", 22.0)
    entry = await async_import(hass, COOLING)
    await async_set_options(hass, entry, armed=["switch.pump", "switch.study_valve"], control=True)
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="cool")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="cool")

    assert hass.states.get("select.flat_mode").attributes["options"] == ["off", "heat", "cool"]
    assert hass.states.get("climate.study").attributes["hvac_modes"] == ["off", "heat", "cool"]
    assert float(hass.states.get("sensor.study_dew_point").state) == pytest.approx(14.77, abs=0.01)
    assert hass.states.get("binary_sensor.study_cooling_demand").state == "on"
    assert hass.states.get("binary_sensor.study_heating_demand").state == "off"
    assert actuators.shorts() == ["switch.study_valve:on"]
    assert hass.states.get("climate.study").attributes["current_humidity"] == 50.0


async def test_a_digital_thermostat_restores_its_exact_target_preset_and_mode(
    hass: HomeAssistant,
) -> None:
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("climate.study", "cool", {"temperature": 21.5, "preset_mode": "eco"}),
                {"last_active_hvac_mode": "cool", "target_temperature_celsius": 21.3},
            )
        ],
    )
    outputs_off(hass, "switch.pump", "switch.study_valve")
    set_temperature(hass, "sensor.study", 21.0)
    set_humidity(hass, "sensor.study_rh", 50.0)
    set_temperature(hass, "sensor.supply", 22.0)
    entry = await async_import(hass, COOLING)

    assert entry.runtime_data.thermostats["study"] == DigitalThermostatState(
        Mode.COOL, 21.3, Preset.ECO
    )
    climate = hass.states.get("climate.study")
    assert climate.state == "cool"
    assert climate.attributes["temperature"] == 19.0, "the preset's target applies"
    assert climate.attributes["preset_modes"] == ["comfort", "eco", "none"]

    await async_call(
        hass, "climate", "set_temperature", entity_id="climate.study", temperature=23.5
    )
    await async_call(hass, "climate", "turn_off", entity_id="climate.study")
    await async_call(hass, "climate", "turn_on", entity_id="climate.study")
    assert entry.runtime_data.thermostats["study"] == DigitalThermostatState(Mode.COOL, 23.5)


async def test_setting_a_target_with_a_mode_changes_both(hass: HomeAssistant) -> None:
    """``climate.set_temperature`` may carry an ``hvac_mode``, as automations often send."""
    outputs_off(hass, "switch.pump", "switch.study_valve")
    set_temperature(hass, "sensor.study", 21.0)
    set_humidity(hass, "sensor.study_rh", 50.0)
    set_temperature(hass, "sensor.supply", 22.0)
    entry = await async_import(hass, COOLING)
    assert hass.states.get("climate.study").state == "off"

    await async_call(
        hass,
        "climate",
        "set_temperature",
        entity_id="climate.study",
        temperature=22.5,
        hvac_mode="heat",
    )

    assert entry.runtime_data.thermostats["study"] == DigitalThermostatState(Mode.HEAT, 22.5)
    climate = hass.states.get("climate.study")
    assert (climate.state, climate.attributes["temperature"]) == ("heat", 22.5)

    await async_call(hass, "climate", "turn_off", entity_id="climate.study")
    await async_call(hass, "climate", "turn_on", entity_id="climate.study")
    assert hass.states.get("climate.study").state == "heat", "turn_on restores the mode it set"

    with pytest.raises(ServiceValidationError, match="unsupported_hvac_mode|no mode auto"):
        await async_call(
            hass,
            "climate",
            "set_temperature",
            entity_id="climate.study",
            temperature=20.0,
            hvac_mode="auto",
        )
    assert entry.runtime_data.thermostats["study"] == DigitalThermostatState(Mode.HEAT, 22.5)


async def test_a_missing_output_blocks_its_loop_and_raises_a_repair(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set("switch.pump", "off")
    set_temperature(hass, "sensor.study", 18.0)
    set_humidity(hass, "sensor.study_rh", 50.0)
    set_temperature(hass, "sensor.supply", 22.0)
    entry = await async_import(hass, COOLING)
    await async_set_options(hass, entry, armed=["switch.pump", "switch.study_valve"], control=True)
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")
    await async_advance(hass, freezer, 60, step=5)

    assert actuators.calls == []
    (issue,) = [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == IssueKind.MISSING_BINDING
    ]
    assert issue.translation_placeholders == {
        "plant": "Flat",
        "entity_id": "switch.study_valve",
        "path": "Zone Study, loop Ceiling, valve 1",
    }
    status = hass.states.get("sensor.flat_status")
    assert status.state == "degraded"
    assert status.attributes["blocked_zones"] == {
        "study": "dropped: switch.study_valve unarmed or unavailable"
    }


async def test_diagnostics_hold_the_plant_file_and_the_last_evaluation_redacted(
    hass: HomeAssistant, actuators: Actuators
) -> None:
    outputs_off(hass, "switch.pump", "switch.study_valve")
    set_temperature(hass, "sensor.study", 18.0)
    set_humidity(hass, "sensor.study_rh", 50.0)
    set_temperature(hass, "sensor.supply", 22.0)
    entry = await async_import(hass, COOLING)
    await async_set_options(hass, entry, armed=["switch.pump", "switch.study_valve"])
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["plant"]["id"] == "**REDACTED**"
    assert diagnostics["plant"]["name"] == "**REDACTED**"
    assert diagnostics["plant"]["zones"]["study"]["loops"]["ceiling"]["valves"] == [
        "switch.study_valve"
    ]
    assert diagnostics["observations"]["outputs"]["switch.study_valve"]["value"] is False
    assert diagnostics["observations"]["sensors"]["sensor.study"]["value"] == 18.0
    assert diagnostics["desired"]["outputs"]["switch.study_valve"] == {"on": True}
    assert diagnostics["desired"]["demands"]["study"]["on"] is True
    assert diagnostics["state"]["live"] is False
    assert diagnostics["proposals"][0]["entity"] == "switch.study_valve"
    assert diagnostics["status"] == "heating"
    assert actuators.calls == []
