"""Real Home Assistant schedules, separate comfort targets, and manual overrides."""

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from custom_components.hydronicus.core.model import DigitalThermostat
from custom_components.hydronicus.storage import async_store_plant
from tests.integration.helpers import (
    async_advance,
    async_call,
    async_import,
    set_humidity,
    set_temperature,
)

PLANT = """
hydronicus: 2
name: Scheduled
pumps:
  pump: {switch: switch.pump, supply_temperature: sensor.supply}
zones:
  study:
    temperature: [sensor.study]
    humidity: [sensor.humidity]
    thermostat:
      digital:
        target: 21
        cool_target: 24
        min_on: 0
        min_off: 0
        schedule:
          entity: schedule.study
          max_early_start: 1800
    loops:
      ceiling: {pump: pump, modes: [heat, cool]}
"""


@pytest.fixture(autouse=True)
async def schedule_environment(hass: HomeAssistant) -> AsyncIterator[None]:
    """Keep local helper times explicit and unload the real schedule's timer."""
    await hass.config.async_set_time_zone("UTC")
    yield
    if component := hass.data.get(DATA_INSTANCES, {}).get("schedule"):
        await component.async_remove_entity("schedule.study")


async def setup_schedule(
    hass: HomeAssistant, *, day: str = "monday", start: str = "08:00", end: str = "10:00"
) -> None:
    assert await async_setup_component(
        hass,
        "schedule",
        {"schedule": {"study": {"name": "Study", day: [{"from": start, "to": end}]}}},
    )
    await hass.async_block_till_done()
    hass.states.async_set("switch.pump", "off")
    set_temperature(hass, "sensor.study", 20)
    set_humidity(hass, "sensor.humidity", 50)
    set_temperature(hass, "sensor.supply", 22)


async def follow_schedule(hass: HomeAssistant, mode: str = "heat") -> None:
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode=mode)
    await async_call(
        hass, "climate", "set_preset_mode", entity_id="climate.study", preset_mode="schedule"
    )


async def test_a_real_schedule_starts_early_at_its_bound_and_retains_manual_override(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-01-05T07:00:00+00:00")
    await setup_schedule(hass)
    entry = await async_import(hass, PLANT)
    await follow_schedule(hass)
    climate = hass.states.get("climate.study")
    assert climate.attributes["temperature"] == 19
    assert climate.attributes["planned_target"] == 21
    assert climate.attributes["schedule_status"] == "setback"
    assert hass.states.get("binary_sensor.study_heating_demand").state == "off"

    await async_advance(hass, freezer, 1799, step=1799)
    assert not hass.states.get("climate.study").attributes["early_start"]
    await async_advance(hass, freezer, 1)
    climate = hass.states.get("climate.study")
    assert climate.attributes["early_start"]
    assert climate.attributes["temperature"] == 21
    assert hass.states.get("binary_sensor.study_heating_demand").state == "on"

    # Reaching comfort must not undo early start or oscillate back to setback.
    set_temperature(hass, "sensor.study", 21.2)
    await hass.async_block_till_done()
    assert hass.states.get("climate.study").attributes["temperature"] == 21
    assert hass.states.get("binary_sensor.study_heating_demand").state == "off"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("climate.study").attributes["early_start"]

    await async_call(
        hass, "climate", "set_temperature", entity_id="climate.study", temperature=22.5
    )
    assert hass.states.get("climate.study").attributes["preset_mode"] == "none"
    await async_advance(hass, freezer, 1800, step=1800)
    assert hass.states.get("schedule.study").state == "on"
    assert hass.states.get("climate.study").attributes["temperature"] == 22.5
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("climate.study").attributes["preset_mode"] == "none"
    assert hass.states.get("climate.study").attributes["temperature"] == 22.5


async def test_schedule_cooling_has_a_higher_setback_and_explicit_resume(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-01-05T07:00:00+00:00")
    await setup_schedule(hass)
    await async_import(hass, PLANT)
    set_temperature(hass, "sensor.study", 25)
    await follow_schedule(hass, "cool")
    assert hass.states.get("climate.study").attributes["temperature"] == 26
    assert hass.states.get("binary_sensor.study_cooling_demand").state == "off"
    await async_advance(hass, freezer, 1800, step=1800)
    assert hass.states.get("climate.study").attributes["temperature"] == 24
    assert hass.states.get("binary_sensor.study_cooling_demand").state == "on"
    await async_call(
        hass, "climate", "set_temperature", entity_id="climate.study", temperature=25.5
    )
    assert hass.states.get("climate.study").attributes["schedule_status"] == "manual"
    await async_call(
        hass, "climate", "set_preset_mode", entity_id="climate.study", preset_mode="schedule"
    )
    assert hass.states.get("climate.study").attributes["temperature"] == 27.5
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")
    assert hass.states.get("climate.study").attributes["heat_target"] == 21
    assert hass.states.get("climate.study").attributes["cool_target"] == 25.5


@pytest.mark.parametrize("new_cap", [0, 300])
async def test_reconfiguring_early_start_revokes_a_latch_outside_the_new_bound(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, new_cap: float
) -> None:
    freezer.move_to("2026-01-05T07:30:00+00:00")
    await setup_schedule(hass)
    entry = await async_import(hass, PLANT)
    await follow_schedule(hass)
    runtime = entry.runtime_data
    assert hass.states.get("climate.study").attributes["early_start"]
    assert runtime.state.demands["study"].early_start_event is not None
    assert hass.states.get("binary_sensor.study_heating_demand").state == "on"

    zone = runtime.plant.zone("study")
    config = zone.thermostat
    assert isinstance(config, DigitalThermostat) and config.schedule is not None
    updated_zone = replace(
        zone, thermostat=replace(config, schedule=replace(config.schedule, max_early_start=new_cap))
    )
    async_store_plant(hass, entry, replace(runtime.plant, zones=(updated_zone,)))
    await hass.async_block_till_done()

    assert entry.runtime_data is not runtime, "configuration changes reload the runtime"
    climate = hass.states.get("climate.study")
    assert climate.attributes["preset_mode"] == "schedule"
    assert climate.attributes["temperature"] == 19
    assert not climate.attributes["early_start"]
    assert entry.runtime_data.state.demands["study"].early_start_event is None
    assert hass.states.get("binary_sensor.study_heating_demand").state == "off"

    # A reduced limit can still start at its new boundary; disabling cannot.
    await async_advance(hass, freezer, 1500, step=1500)
    climate = hass.states.get("climate.study")
    assert climate.attributes["early_start"] is (new_cap > 0)
    assert climate.attributes["temperature"] == (21 if new_cap else 19)


async def test_unavailable_schedule_restores_manual_comfort_without_changing_preset(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set("switch.pump", "off")
    set_temperature(hass, "sensor.study", 20)
    set_temperature(hass, "sensor.supply", 22)
    await async_import(hass, PLANT)
    await follow_schedule(hass)
    assert hass.states.get("climate.study").attributes["temperature"] == 21
    assert hass.states.get("climate.study").attributes["schedule_status"] == "unavailable"
    hass.states.async_set("schedule.study", "off", {"next_event": "invalid"})
    await hass.async_block_till_done()
    assert hass.states.get("climate.study").attributes["temperature"] == 19
    assert not hass.states.get("climate.study").attributes["early_start"]
    hass.states.async_set("schedule.study", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get("climate.study").attributes["temperature"] == 21
    assert hass.states.get("climate.study").attributes["preset_mode"] == "schedule"


async def test_precise_both_mode_targets_restore_without_treating_displayed_setback_as_manual(
    hass: HomeAssistant,
) -> None:
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("climate.study", "cool", {"temperature": 27.0, "preset_mode": "schedule"}),
                {
                    "last_active_hvac_mode": "cool",
                    "heat_target_temperature_celsius": 20.73,
                    "cool_target_temperature_celsius": 24.91,
                },
            )
        ],
    )
    hass.states.async_set("switch.pump", "off")
    hass.states.async_set("schedule.study", "off")
    set_temperature(hass, "sensor.study", 25)
    set_temperature(hass, "sensor.supply", 22)
    await async_import(hass, PLANT)
    assert hass.states.get("climate.study").attributes["planned_target"] == 24.91
    assert hass.states.get("climate.study").attributes["temperature"] == 26.9
    assert hass.states.get("climate.study").attributes["effective_target"] == 26.91
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")
    assert hass.states.get("climate.study").attributes["planned_target"] == 20.73


@pytest.mark.parametrize(
    "now,expected",
    [
        ("2026-03-29T00:45:00+00:00", "2026-03-29T01:30:00+00:00"),
        ("2026-10-25T01:45:00+00:00", "2026-10-25T02:30:00+00:00"),
    ],
)
async def test_real_schedule_deadlines_use_utc_across_dst_changes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, now: str, expected: str
) -> None:
    freezer.move_to(now)
    await hass.config.async_set_time_zone("Europe/Budapest")
    await setup_schedule(hass, day="sunday", start="03:30", end="04:30")
    entry = await async_import(hass, PLANT)
    await follow_schedule(hass)
    observation = entry.runtime_data.view.observations.schedules["schedule.study"]
    assert observation.next_event == datetime.fromisoformat(expected).astimezone(UTC).timestamp()
    assert not hass.states.get("climate.study").attributes["early_start"]
    await async_advance(hass, freezer, 900, step=900)
    assert hass.states.get("climate.study").attributes["early_start"]
