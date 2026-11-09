"""End-to-end regressions for the safety and runtime defects found in the review."""

from __future__ import annotations

import asyncio

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback

from custom_components.hydronicus.core.plant_file import read_plant_file
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    set_temperature,
)
from tests.integration.test_sending import ValveServices, async_flat, async_until, control_on

PLANT = """
hydronicus: 2
name: Review
exercise: null
frost_protection: null
pumps:
  pump: {switch: switch.pump, overrun: 0}
zones:
  room:
    temperature: [{entity: sensor.room, max_age: 30}]
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      floor: {valves: [{entity: switch.valve, opening_time: 0}], pump: pump}
"""


async def start(hass: HomeAssistant, text: str = PLANT) -> ConfigEntry:
    for entity in read_plant_file(text).outputs():
        hass.states.async_set(entity, "off")
    set_temperature(hass, "sensor.room", 18.0)
    entry = await async_import(hass, text)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    await async_call(hass, "select", "select_option", entity_id="select.review_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.room", hvac_mode="heat")
    return entry


async def test_same_value_sensor_report_resumes_heating(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    await start(hass)
    assert hass.states.get("switch.pump").state == "on"
    await async_advance(hass, freezer, 32)
    assert hass.states.get("switch.pump").state == "off"
    state = hass.states.get("sensor.room")
    old_report = state.last_reported_timestamp
    hass.states.async_set("sensor.room", state.state, dict(state.attributes))
    await hass.async_block_till_done()
    new_report = hass.states.get("sensor.room").last_reported_timestamp
    assert new_report > old_report
    assert hass.states.get("switch.pump").state == "on", "Fresh unchanged report must resume heat"


async def test_ha_stop_drops_queued_commands(hass: HomeAssistant, actuators: Actuators) -> None:
    valves = ValveServices(hass)
    entry = await async_flat(hass, "den", "study")
    valves.hold("valve.den")
    control_on(hass, entry)
    await async_until(lambda: valves.waiting)
    assert actuators.shorts() == ["valve.den:on"]
    stopped = asyncio.Event()

    @callback
    def on_stop(_event: Event) -> None:
        stopped.set()
        valves.release("valve.den")

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_stop)
    await hass.async_stop(force=True)
    assert stopped.is_set()
    assert actuators.shorts() == ["valve.den:on"], "No queued command may start after HA stop"


async def test_source_min_off_starts_from_observed_stop(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    text = PLANT.replace(
        "name: Review",
        "name: Review\nsource: {request: switch.source, min_on: 0, min_off: 600, post_run: 0}",
    ).replace("max_age: 30", "max_age: 86400")
    entry = await start(hass, text)
    assert hass.states.get("switch.source").state == "on"
    actuators.ignoring.add("switch.source")
    set_temperature(hass, "sensor.room", 22.0)
    await hass.async_block_till_done()
    assert entry.runtime_data.view.desired.source_request is False
    await async_advance(hass, freezer, 610, step=10)
    assert hass.states.get("switch.source").state == "on"
    actuators.ignoring.remove("switch.source")
    hass.states.async_set("switch.source", "off")
    await hass.async_block_till_done()
    actuators.clear()
    set_temperature(hass, "sensor.room", 18.0)
    await hass.async_block_till_done()
    assert hass.states.get("switch.source").state == "off", (
        "Source just stopped and owes 600 seconds off"
    )
    await async_advance(hass, freezer, 599, step=10)
    assert hass.states.get("switch.source").state == "off"
    await async_advance(hass, freezer, 2)
    assert hass.states.get("switch.source").state == "on"


SHARED = """
hydronicus: 2
name: Shared
pumps:
  pump: {switch: switch.pump, supply_temperature: sensor.supply}
loops:
  ceiling:
    valves: [switch.shared_valve]
    pump: pump
    modes: [heat, cool]
    runs: {with_zones: [room]}
zones:
  room:
    temperature: [sensor.room]
    humidity: [sensor.humidity]
"""


async def test_shared_cooling_loop_offers_cool_mode(hass: HomeAssistant) -> None:
    await async_import(hass, SHARED)
    state = hass.states.get("climate.room")
    assert "cool" in state.attributes["hvac_modes"], "Shared cooling loop must enable zone cooling"


async def test_disarming_an_output_cancels_its_queued_command(
    hass: HomeAssistant, actuators: Actuators
) -> None:
    from custom_components.hydronicus.const import OPTION_ARMED_OUTPUTS

    valves = ValveServices(hass)
    entry = await async_flat(hass, "den", "study")
    valves.hold("valve.den")
    control_on(hass, entry)
    await async_until(lambda: valves.waiting)
    armed = set(entry.options[OPTION_ARMED_OUTPUTS]) - {"valve.study"}
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, OPTION_ARMED_OUTPUTS: list(armed)}
    )
    await async_until(lambda: "valve.study" not in entry.runtime_data.view.observations.armed)
    valves.release("valve.den")
    await hass.async_block_till_done()
    assert "valve.study:on" not in actuators.shorts(), "Disarmed output must receive zero commands"


async def test_dry_run_to_live_keeps_real_mode_dwell(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    text = """
hydronicus: 2
name: Review
mode_dwell: 300
exercise: null
frost_protection: null
pumps:
  heating: {switch: switch.heating_pump, overrun: 0}
  cooling: {switch: switch.cooling_pump, overrun: 0, supply_temperature: sensor.supply}
zones:
  room:
    temperature: [{entity: sensor.room, max_age: 86400}]
    humidity: [{entity: sensor.humidity, max_age: 86400}]
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      radiator: {pump: heating, modes: [heat]}
      ceiling: {pump: cooling, modes: [cool]}
"""
    hass.states.async_set("switch.heating_pump", "on")
    hass.states.async_set("switch.cooling_pump", "off")
    set_temperature(hass, "sensor.room", 26.0)
    set_temperature(hass, "sensor.supply", 22.0)
    hass.states.async_set("sensor.humidity", "40", {"unit_of_measurement": "%"})
    entry = await async_import(hass, text)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs())
    await async_call(hass, "select", "select_option", entity_id="select.review_mode", option="heat")
    await async_call(hass, "select", "select_option", entity_id="select.review_mode", option="cool")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.room", hvac_mode="cool")
    await async_advance(hass, freezer, 310, step=10)
    assert hass.states.get("switch.heating_pump").state == "on"
    assert not actuators.calls
    await async_set_options(hass, entry, control=True)
    cool = hass.states.get("switch.cooling_pump")
    assert cool.state == "off", "Cooling must wait 300 seconds after real heating stops"
    stopped_at = hass.states.get("switch.heating_pump").last_changed_timestamp
    await async_advance(hass, freezer, 301, step=10)
    cool = hass.states.get("switch.cooling_pump")
    assert cool.state == "on"
    assert cool.last_changed_timestamp - stopped_at >= 300


async def test_source_min_on_starts_from_observed_start(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    text = PLANT.replace("max_age: 30", "max_age: 86400").replace(
        "name: Review",
        "name: Review\nsource: {request: switch.source, min_on: 600, min_off: 0, post_run: 0}",
    )
    actuators.ignoring.add("switch.source")
    entry = await start(hass, text)
    assert entry.runtime_data.view.desired.source_request is True
    assert hass.states.get("switch.source").state == "off"
    await async_advance(hass, freezer, 610, step=10)
    actuators.ignoring.remove("switch.source")
    hass.states.async_set("switch.source", "on")
    await hass.async_block_till_done()
    set_temperature(hass, "sensor.room", 22.0)
    await hass.async_block_till_done()
    assert hass.states.get("switch.source").state == "on"
    await async_advance(hass, freezer, 599, step=10)
    assert hass.states.get("switch.source").state == "on"
    await async_advance(hass, freezer, 2)
    assert hass.states.get("switch.source").state == "off"
