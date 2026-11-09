"""Commissioning reports actual evidence, stale inputs, and evaluation failures."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.hydronicus import runtime as runtime_module
from custom_components.hydronicus.core.model import Mode
from custom_components.hydronicus.core.plant_file import read_plant_file
from custom_components.hydronicus.core.step import Observations, SwitchState
from custom_components.hydronicus.diagnostics import async_get_config_entry_diagnostics
from custom_components.hydronicus.view import (
    loop_operation,
    observed_flow,
    pump_operation,
    source_operation,
)
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    set_humidity,
    set_temperature,
)

PLANT = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump, overrun: 0}
zones:
  study:
    temperature: [{entity: sensor.study, max_age: 30}]
    thermostat: {digital: {target: 21, min_on: 0, min_off: 0}}
    loops:
      radiator: {pump: pump}
"""


async def start(hass: HomeAssistant, document: str = PLANT) -> Any:
    hass.states.async_set("switch.pump", "off")
    set_temperature(hass, "sensor.study", 19)
    entry = await async_import(hass, document)
    await async_set_options(hass, entry, armed=["switch.pump"], control=True)
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")
    return entry


async def test_sensor_health_and_next_evaluation_explain_a_stale_input(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    await start(hass)
    status = hass.states.get("sensor.flat_status").attributes
    health = status["sensor_health"]["sensor.study"]
    assert health == {
        "quality": "fresh",
        "age_seconds": 0.0,
        "max_age_seconds": 30.0,
        "value": 19.0,
    }
    assert status["next_evaluation_at"] is not None
    assert status["pump_operation"]["pump"]["basis"] == "Inferred from pump switch"

    await async_advance(hass, freezer, 31)
    status = hass.states.get("sensor.flat_status").attributes
    assert status["sensor_health"]["sensor.study"]["quality"] == "stale"
    assert status["blocking_reason"] == "Study: no usable temperature"
    temperature = hass.states.get("sensor.study_combined_temperature")
    assert temperature.state == "unknown"
    assert temperature.attributes["sensor_health"]["sensor.study"]["age_seconds"] >= 30


async def test_evaluation_failure_is_visible_and_recovers(
    hass: HomeAssistant,
    actuators: Actuators,
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = await start(hass, PLANT.replace("max_age: 30", "max_age: 3600"))
    real_step = runtime_module.step

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("test input failure")

    monkeypatch.setattr(runtime_module, "step", broken)
    set_temperature(hass, "sensor.study", 19.1)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.flat_status")
    assert state.state == "degraded"
    assert state.attributes["evaluation_error"] == "ValueError: test input failure"
    assert state.attributes["blocking_reason"] == "ValueError: test input failure"
    report = await async_get_config_entry_diagnostics(hass, entry)
    assert report["evaluation_error"] == state.attributes["evaluation_error"]
    assert report["next_evaluation_at"] > dt_util.utcnow().timestamp()

    monkeypatch.setattr(runtime_module, "step", real_step)
    await async_advance(hass, freezer, 61)
    state = hass.states.get("sensor.flat_status")
    assert state.state == "heating"
    assert state.attributes["evaluation_error"] is None


async def test_pending_commands_show_the_age_of_unconfirmed_equipment(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    actuators.ignoring.add("switch.pump")
    entry = await start(hass)
    await async_advance(hass, freezer, 5)
    report = await async_get_config_entry_diagnostics(hass, entry)
    pending = report["pending_commands"]["switch.pump"]
    assert pending == {"target": {"on": True}, "age_seconds": 5.0, "attempts": 1}
    assert report["pump_operation"]["pump"]["active"] is False


async def test_feedback_distinguishes_a_running_pump_from_flow_and_unknown_feedback(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    document = PLANT.replace(
        "overrun: 0}",
        "overrun: 0, running_sensor: binary_sensor.running, flow_sensor: binary_sensor.flow}",
    ).replace("max_age: 30", "max_age: 3600")
    hass.states.async_set("binary_sensor.running", "on")
    hass.states.async_set("binary_sensor.flow", "off")
    entry = await start(hass, document)
    flowing = hass.states.get("binary_sensor.study_radiator_flowing")
    assert flowing.state == "off"
    assert flowing.attributes["pump_running"] is True
    assert flowing.attributes["pump_running_basis"] == "Running sensor"
    assert flowing.attributes["flow_basis"] == "Pump flow sensor; loop path inferred"

    hass.states.async_set("binary_sensor.flow", "on")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.study_radiator_flowing").state == "on"
    await async_advance(hass, freezer, 60)
    assert entry.runtime_data.flow.runtime("study.radiator") == 60

    hass.states.async_set("binary_sensor.flow", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.study_radiator_flowing").state == "unknown"
    await async_advance(hass, freezer, 60)
    assert entry.runtime_data.flow.runtime("study.radiator") == 60


async def test_shared_cooling_loop_exposes_zone_cooling_entities_and_blocking_reason(
    hass: HomeAssistant, actuators: Actuators
) -> None:
    document = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump, supply_temperature: sensor.supply}
loops:
  ceiling: {pump: pump, modes: [cool], runs: {with_zones: [study]}}
zones:
  study:
    temperature: [sensor.study]
    humidity: [sensor.humidity]
    thermostat: {digital: {min_on: 0, min_off: 0}}
"""
    hass.states.async_set("switch.pump", "off")
    set_temperature(hass, "sensor.study", 28)
    set_temperature(hass, "sensor.supply", 8)
    set_humidity(hass, "sensor.humidity", 70)
    entry = await async_import(hass, document)
    await async_set_options(hass, entry, armed=["switch.pump"], control=True)
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="cool")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="cool")
    assert hass.states.get("binary_sensor.study_cooling_demand").state == "on"
    assert hass.states.get("sensor.study_dew_point").state not in ("unknown", "unavailable")
    assert "study" in hass.states.get("sensor.flat_status").attributes["blocked_zones"]
    assert actuators.calls == []


async def test_source_feedback_does_not_claim_the_request_is_actual_operation(
    hass: HomeAssistant,
) -> None:
    document = PLANT.replace(
        "name: Flat",
        "name: Flat\nsource: {request: switch.source, "
        "running_sensor: binary_sensor.source_running}",
    )
    hass.states.async_set("switch.source", "off")
    hass.states.async_set("switch.pump", "off")
    hass.states.async_set("binary_sensor.source_running", "on")
    set_temperature(hass, "sensor.study", 21)
    entry = await async_import(hass, document)
    source = hass.states.get("binary_sensor.heat_source_requested")
    assert source.state == "off"
    assert source.attributes["observed"] is False
    assert source.attributes["running"] is True
    assert source.attributes["running_basis"] == "Running sensor"
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["source_operation"]["active"] is True


def test_source_driven_postrun_is_an_estimate_and_ends_at_its_deadline() -> None:
    plant = read_plant_file("""
hydronicus: 2
name: Flat
source: {request: switch.source, post_run: 120}
pumps:
  pump: {driven_by: source, min_flow: guaranteed}
zones:
  study:
    thermostat: {external: climate.study}
    loops:
      radiator: {pump: pump}
""")
    observations = Observations(
        Mode.HEAT, True, frozenset(), outputs={"switch.source": SwitchState(False, 100)}
    )
    assert observed_flow(plant, observations, 200) == (frozenset(), frozenset())
    assert observed_flow(plant, observations, 200, source_winding=True) == (
        frozenset({"study.radiator"}),
        frozenset({"study"}),
    )
    assert (
        pump_operation(plant, plant.pumps[0], observations, 200, source_winding=True).basis
        == "Estimated source post-run"
    )
    assert observed_flow(plant, observations, 220, source_winding=True) == (
        frozenset(),
        frozenset(),
    )
    source = plant.source
    assert source is not None
    plant = replace(plant, source=replace(source, running_sensor="binary_sensor.source"))
    assert source_operation(plant, observations).active is None
    assert pump_operation(plant, plant.pumps[0], observations, 220).active is None
    observations = replace(observations, readiness={"binary_sensor.source": SwitchState(True, 0)})
    assert loop_operation(plant, plant.all_loops[0], observations, 220).active is True


async def test_source_supply_failure_explains_why_demand_cannot_start_the_source(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    document = PLANT.replace("max_age: 30", "max_age: 3600").replace(
        "name: Flat",
        """name: Flat
source:
  request: switch.source
  min_on: 0
  min_off: 0
  post_run: 0
  supply: {entity: number.supply, outdoor_sensor: sensor.outdoor, max_age: 30}
""",
    )
    hass.states.async_set("switch.source", "off")
    hass.states.async_set("number.supply", "35", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.outdoor", "unavailable")
    entry = await start(hass, document)
    await async_set_options(
        hass, entry, armed=["switch.pump", "switch.source", "number.supply"], control=True
    )
    assert hass.states.get("sensor.flat_status").attributes["blocking_reason"] == (
        "outdoor temperature unavailable"
    )
    set_temperature(hass, "sensor.outdoor", 5)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.flat_status").attributes["blocking_reason"] is None
    await async_advance(hass, freezer, 31)
    assert hass.states.get("sensor.flat_status").attributes["blocking_reason"] == (
        "outdoor temperature stale"
    )
    report = await async_get_config_entry_diagnostics(hass, entry)
    assert report["blocking_reason"] == "outdoor temperature stale"


async def test_source_postrun_counts_only_after_the_source_was_observed_running(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set("switch.source", "off")
    hass.states.async_set("climate.external", "heat", {"hvac_action": "idle"})
    entry = await async_import(
        hass,
        """
hydronicus: 2
name: Flat
source: {request: switch.source, post_run: 120, min_on: 0, min_off: 0}
pumps:
  pump: {driven_by: source, min_flow: guaranteed}
zones:
  study:
    thermostat: {external: climate.external}
    loops:
      radiator: {pump: pump}
""",
    )
    await async_set_options(hass, entry, armed=["switch.source"], control=True)
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    assert hass.states.get("binary_sensor.study_radiator_flowing").state == "off"
    assert entry.runtime_data.flow.runtime("study.radiator") == 0
    hass.states.async_set("climate.external", "heat", {"hvac_action": "heating"})
    await hass.async_block_till_done()
    assert hass.states.get("switch.source").state == "on"
    assert hass.states.get("binary_sensor.study_radiator_flowing").state == "on"
    hass.states.async_set("climate.external", "heat", {"hvac_action": "idle"})
    await hass.async_block_till_done()
    assert hass.states.get("switch.source").state == "off"
    flowing = hass.states.get("binary_sensor.study_radiator_flowing")
    assert flowing.state == "on"
    assert flowing.attributes["pump_running_basis"] == "Estimated source post-run"
    await async_advance(hass, freezer, 121)
    assert hass.states.get("binary_sensor.study_radiator_flowing").state == "off"
    assert entry.runtime_data.flow.runtime("study.radiator") == pytest.approx(120, abs=1)
