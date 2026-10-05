"""Equipment proof and supply setpoints through the Home Assistant runtime."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall, callback

from custom_components.hydronicus.core.step import NumericState
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    set_temperature,
)
from tests.integration.test_review_regressions import PLANT, start


async def test_pump_starts_before_flow_proof_and_source_waits_for_both_proofs(
    hass: HomeAssistant, actuators: Actuators
) -> None:
    text = PLANT.replace(
        "name: Review",
        "name: Review\nsource: {request: switch.source, min_on: 0, min_off: 0, post_run: 0}",
    ).replace(
        "switch: switch.pump, overrun: 0",
        "switch: switch.pump, overrun: 0, running_sensor: binary_sensor.running, "
        "flow_sensor: binary_sensor.flow",
    )
    hass.states.async_set("binary_sensor.running", "off")
    hass.states.async_set("binary_sensor.flow", "off")
    entry = await start(hass, text)
    assert hass.states.get("switch.pump").state == "on", (
        entry.runtime_data.state,
        entry.runtime_data.view.desired,
        entry.runtime_data.reconcile_state,
    )
    assert hass.states.get("switch.source").state == "off"
    hass.states.async_set("binary_sensor.running", "on")
    await hass.async_block_till_done()
    assert hass.states.get("switch.source").state == "off"
    hass.states.async_set("binary_sensor.flow", "on")
    await hass.async_block_till_done()
    assert hass.states.get("switch.source").state == "on"
    hass.states.async_set("binary_sensor.flow", "unavailable")
    await hass.async_block_till_done()
    assert entry.runtime_data.view.observations.readiness["binary_sensor.flow"].on is None
    assert hass.states.get("switch.source").state == "off"
    assert hass.states.get("switch.valve").state == "on", "running proof retains the flow path"


@pytest.mark.parametrize("proof", ["on", "unavailable"])
async def test_autonomous_source_operation_keeps_the_source_driven_path_open(
    hass: HomeAssistant, actuators: Actuators, proof: str
) -> None:
    text = """
hydronicus: 2
name: Review
exercise: null
frost_protection: null
source:
  request: switch.source
  running_sensor: binary_sensor.source_running
  min_on: 0
  min_off: 0
  post_run: 0
pumps:
  primary:
    driven_by: source
    min_flow: path
    min_flow_loops: [room.floor]
zones:
  room:
    temperature: [sensor.room]
    loops:
      floor:
        pump: primary
        valves: [{entity: switch.valve, opening_time: 0}]
"""
    hass.states.async_set("switch.source", "off")
    hass.states.async_set("switch.valve", "off")
    hass.states.async_set("binary_sensor.source_running", "off")
    set_temperature(hass, "sensor.room", 22.0)
    entry = await async_import(hass, text)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    await async_call(hass, "select", "select_option", entity_id="select.review_mode", option="heat")
    assert hass.states.get("switch.valve").state == "off"
    hass.states.async_set("binary_sensor.source_running", proof)
    await hass.async_block_till_done()
    assert hass.states.get("switch.source").state == "off"
    assert hass.states.get("switch.valve").state == "on"
    hass.states.async_set("binary_sensor.source_running", "off")
    await hass.async_block_till_done()
    assert hass.states.get("switch.valve").state == "off"


async def test_supply_number_is_observed_in_celsius_and_confirmed_before_source_start(
    hass: HomeAssistant, actuators: Actuators
) -> None:
    text = PLANT.replace(
        "name: Review",
        "name: Review\nsource:\n  request: switch.source\n  min_on: 0\n  min_off: 0\n"
        "  post_run: 0\n  supply: {entity: number.supply, heat_temperature: 35}",
    )
    native_attributes = {"unit_of_measurement": "°F", "min": 41, "max": 140, "step": 1}
    calls: list[float] = []

    @callback
    def set_value(call: ServiceCall) -> None:
        calls.append(float(call.data["value"]))
        assert hass.states.get("switch.source").state == "off"
        hass.states.async_set("number.supply", str(call.data["value"]), native_attributes)

    hass.services.async_register("number", "set_value", set_value)
    # start() initializes outputs as switches; update this number before the first live evaluation.
    for entity in ("switch.pump", "switch.valve", "switch.source"):
        hass.states.async_set(entity, "off")
    hass.states.async_set("number.supply", "77", native_attributes)
    set_temperature(hass, "sensor.room", 18.0)
    entry = await async_import(hass, text)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    await async_call(hass, "select", "select_option", entity_id="select.review_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.room", hvac_mode="heat")
    assert calls == [95.0]
    assert hass.states.get("switch.source").state == "on"
    observed = entry.runtime_data.view.observations.outputs["number.supply"]
    assert isinstance(observed, NumericState)
    assert observed.value == 35.0
    remembered = entry.runtime_data.memory.to_dict()["number.supply"]
    assert remembered["value"] == 35.0
    # A new report with native units has the same canonical target and no extra write.
    hass.states.async_set("number.supply", "35", {**native_attributes, "unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert calls == [95.0]
    assert entry.runtime_data.memory.to_dict()["number.supply"] == remembered


async def test_schedule_snapshots_follow_updates_and_unavailability(hass: HomeAssistant) -> None:
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    set_temperature(hass, "sensor.room", 18.0)
    text = PLANT.replace(
        "min_on: 0, min_off: 0",
        "min_on: 0, min_off: 0, schedule: {entity: schedule.room}",
    )
    entry = await async_import(hass, text)
    runtime = entry.runtime_data
    next_event = dt_util.utcnow() + timedelta(hours=1)
    hass.states.async_set("schedule.room", "off", {"next_event": next_event.isoformat()})
    runtime.request_evaluation()
    await hass.async_block_till_done()
    schedule = runtime.view.observations.schedules["schedule.room"]
    assert schedule.active is False
    assert schedule.next_event == next_event.timestamp()
    hass.states.async_set("schedule.room", "unavailable")
    await hass.async_block_till_done()
    assert runtime.view.observations.schedules["schedule.room"].active is None


async def test_unreachable_number_target_raises_output_repair_without_starting_source(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    from custom_components.hydronicus.issues import IssueKind

    text = PLANT.replace("max_age: 30", "max_age: 86400").replace(
        "name: Review",
        "name: Review\nsource:\n  request: switch.source\n  min_on: 0\n  min_off: 0\n"
        "  post_run: 0\n  supply: {entity: number.supply, heat_temperature: 35}",
    )
    for entity in ("switch.pump", "switch.valve", "switch.source"):
        hass.states.async_set(entity, "off")
    # The equipment advertises a lower maximum than the Plant's configured target.
    hass.states.async_set("number.supply", "25", {"unit_of_measurement": "°C", "min": 5, "max": 30})
    set_temperature(hass, "sensor.room", 18.0)
    entry = await async_import(hass, text)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    await async_call(hass, "select", "select_option", entity_id="select.review_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.room", hvac_mode="heat")
    await async_advance(hass, freezer, 120, step=5)
    assert hass.states.get("switch.source").state == "off"
    assert entry.runtime_data.evaluation_error is None
    assert any(issue.kind is IssueKind.OUTPUT_NOT_RESPONDING for issue in entry.runtime_data.issues)
