"""The loop runtime and zone duty cycle sensors (contract K7).

Only flow that the Plant observes while it is live counts: never a Dry run
proposal, and never time while the Plant is not loaded. The counters survive a
reload, and the duty cycle covers the 24 whole hours before the current one.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.hydronicus import runtime as runtime_module
from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.diagnostics import async_get_config_entry_diagnostics
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    entity_id_of,
    set_temperature,
)

# A radiator loop without a valve, so it flows as soon as its pump runs, and a
# thermostat that follows the temperature at once.
STUDY = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump, overrun: 0}
zones:
  study:
    temperature: [sensor.study]
    thermostat: {digital: {target: 21, min_on: 0, min_off: 0}}
    loops:
      radiator: {pump: pump}
"""
RUNTIME = "sensor.study_radiator_runtime"
DUTY_CYCLE = "sensor.study_duty_cycle"
FLOWING = "binary_sensor.study_radiator_flowing"
# A whole hour, so that the duty cycle's hours are easy to follow.
START = datetime(2026, 1, 5, 0, 0, tzinfo=dt_util.UTC)


def value(hass: HomeAssistant, entity_id: str) -> float:
    return float(hass.states.get(entity_id).state)


async def async_study(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, *, control: bool = True
) -> Any:
    """Set the study up and let it call for heat, live or in Dry run."""
    freezer.move_to(START)
    hass.states.async_set("switch.pump", "off")
    set_temperature(hass, "sensor.study", 19.0)
    entry = await async_import(hass, STUDY)
    await async_set_options(hass, entry, armed=["switch.pump"], control=control)
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")
    assert hass.states.get(FLOWING).state == "on"
    return entry


async def async_run(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    """Let time pass while the study's sensor reports every ten minutes, as a real one would."""
    for _ in range(int(seconds // 600)):
        await async_advance(hass, freezer, 600, step=60)
        set_temperature(hass, "sensor.study", 19.0)
        await hass.async_block_till_done()


async def async_stop_heating(hass: HomeAssistant) -> None:
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="off")
    assert hass.states.get(FLOWING).state == "off"


async def test_the_runtime_counts_observed_flow_while_the_plant_is_live(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_study(hass, freezer)
    assert actuators.shorts() == ["switch.pump:on"]
    assert value(hass, RUNTIME) == 0.0

    await async_run(hass, freezer, 5400)
    assert value(hass, RUNTIME) == 1.5
    await async_stop_heating(hass)
    await async_run(hass, freezer, 3600)
    assert value(hass, RUNTIME) == 1.5

    # Turning Control equipment off stops the pump, and from then on the Plant
    # runs in Dry run, whose proposed flow does not count.
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")
    await async_run(hass, freezer, 1800)
    await async_set_options(hass, entry, control=False)
    assert actuators.shorts()[-1] == "switch.pump:off"
    assert hass.states.get("switch.pump").state == "off"
    await async_run(hass, freezer, 3600)
    assert hass.states.get(FLOWING).state == "on", "the flowing sensor follows the proposal"
    assert value(hass, RUNTIME) == 2.0


async def test_the_sensors_refresh_every_minute_without_evaluating(
    hass: HomeAssistant,
    actuators: Actuators,
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = await async_study(hass, freezer)
    runtime = entry.runtime_data
    actuators.clear()
    evaluations = 0
    real_step = runtime_module.step

    def counting(*args: Any) -> Any:
        nonlocal evaluations
        evaluations += 1
        return real_step(*args)

    monkeypatch.setattr(runtime_module, "step", counting)
    await async_advance(hass, freezer, 59)
    assert value(hass, RUNTIME) == 0.0
    await async_advance(hass, freezer, 1)
    assert value(hass, RUNTIME) == pytest.approx(60 / 3600, abs=0.001)
    await async_advance(hass, freezer, 540, step=60)
    assert value(hass, RUNTIME) == pytest.approx(600 / 3600, abs=0.001)
    assert evaluations == 0 and actuators.calls == []

    # Nothing flows, so nothing refreshes but the hour the duty cycle moves on.
    await async_stop_heating(hass)
    now = dt_util.utcnow().timestamp()
    assert runtime.flow.next_refresh(now) == (START + timedelta(hours=1)).timestamp()


async def test_dry_run_proposals_count_no_runtime(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_study(hass, freezer, control=False)
    assert actuators.calls == []

    await async_run(hass, freezer, 7200)
    assert hass.states.get(FLOWING).state == "on", "the flowing sensor follows the proposal"
    assert value(hass, RUNTIME) == 0.0
    assert value(hass, DUTY_CYCLE) == 0.0
    assert entry.runtime_data.flow.next_refresh(dt_util.utcnow().timestamp()) is None


async def test_the_runtime_survives_a_reload_and_skips_the_time_unloaded(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    actuators: Actuators,
    freezer: FrozenDateTimeFactory,
) -> None:
    entry = await async_study(hass, freezer)
    await async_run(hass, freezer, 3600)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert value(hass, RUNTIME) == 1.0

    # While the Plant is not loaded, the pump keeps running, and none of it counts.
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    stored = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]["flow"]
    assert stored["runtimes"] == {"study.radiator": 3600.0}
    await async_advance(hass, freezer, 7200, step=3600)
    set_temperature(hass, "sensor.study", 19.0)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("switch.pump").state == "on"
    assert value(hass, RUNTIME) == 1.0

    await async_run(hass, freezer, 1800)
    assert value(hass, RUNTIME) == 1.5
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["flow"]["runtimes"] == {"study.radiator": 5400.0}


async def test_the_counters_are_saved_when_home_assistant_stops(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    actuators: Actuators,
    freezer: FrozenDateTimeFactory,
) -> None:
    entry = await async_study(hass, freezer)
    await async_run(hass, freezer, 1800)

    await hass.async_stop(force=True)

    stored = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]["flow"]
    assert stored["runtimes"] == {"study.radiator": 1800.0}


async def test_the_duty_cycle_covers_the_24_hours_before_the_current_one(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_study(hass, freezer)
    assert value(hass, DUTY_CYCLE) == 0.0

    # Six hours of flow from midnight; an hour counts once it is over.
    await async_run(hass, freezer, 3000)
    assert value(hass, DUTY_CYCLE) == 0.0
    await async_run(hass, freezer, 600)
    assert value(hass, DUTY_CYCLE) == pytest.approx(100 / 24, abs=0.05)
    await async_run(hass, freezer, 5 * 3600)
    await async_stop_heating(hass)
    assert value(hass, DUTY_CYCLE) == 25.0

    # With nothing flowing, the window moves on at every hour, and the first hour
    # of flow leaves it at one o'clock the next day.
    await async_advance(hass, freezer, 18 * 3600, step=3600)
    assert value(hass, DUTY_CYCLE) == 25.0
    await async_advance(hass, freezer, 3600, step=3600)
    assert value(hass, DUTY_CYCLE) == pytest.approx(500 / 24, abs=0.05)

    # A jump of the clock past the window empties it, and then nothing refreshes.
    await async_advance(hass, freezer, 30 * 3600, step=30 * 3600)
    assert value(hass, DUTY_CYCLE) == 0.0
    runtime = entry.runtime_data
    assert runtime.flow.next_refresh(dt_util.utcnow().timestamp()) is None
    assert runtime.flow.to_dict()["hours"] == {}
    assert value(hass, RUNTIME) == 6.0


async def test_the_flow_sensors_are_diagnostic_with_stable_unique_ids(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_study(hass, freezer)
    plant_id = entry.unique_id
    registry = er.async_get(hass)

    runtime = registry.async_get(
        entity_id_of(hass, "sensor", f"{plant_id}_loop_study.radiator_runtime")
    )
    duty_cycle = registry.async_get(
        entity_id_of(hass, "sensor", f"{plant_id}_zone_study_duty_cycle")
    )
    assert (runtime.entity_id, duty_cycle.entity_id) == (RUNTIME, DUTY_CYCLE)
    assert runtime.entity_category is duty_cycle.entity_category is EntityCategory.DIAGNOSTIC
    state = hass.states.get(RUNTIME).attributes
    assert state["device_class"] == "duration" and state["state_class"] == "total_increasing"
    assert state["unit_of_measurement"] == "h"
    state = hass.states.get(DUTY_CYCLE).attributes
    assert state["state_class"] == "measurement" and state["unit_of_measurement"] == "%"
