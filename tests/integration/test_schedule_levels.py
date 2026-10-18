"""Block levels, setbacks, and Repairs through a real, editable Home Assistant schedule."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.hydronicus.const import DOMAIN
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
        presets: {eco: 18}
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
    await hass.config.async_set_time_zone("UTC")
    assert await async_setup_component(hass, "schedule", {})
    hass.states.async_set("switch.pump", "off")
    set_temperature(hass, "sensor.study", 20)
    set_humidity(hass, "sensor.humidity", 50)
    set_temperature(hass, "sensor.supply", 22)
    yield
    if component := hass.data.get(DATA_INSTANCES, {}).get("schedule"):
        for entity in list(component.entities):
            await component.async_remove_entity(entity.entity_id)


class Helper:
    """The schedule helper as a dashboard edits it: whole weeks over the websocket."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.id = ""

    async def _send(self, message: dict[str, Any]) -> dict[str, Any]:
        await self.client.send_json_auto_id(message)
        response = await self.client.receive_json()
        assert response["success"], response
        result: dict[str, Any] = response["result"]
        return result

    async def create(self, **days: list[dict[str, Any]]) -> None:
        self.id = (await self._send({"type": "schedule/create", "name": "Study", **days}))["id"]

    async def update(self, **days: list[dict[str, Any]]) -> None:
        await self._send(
            {"type": "schedule/update", "schedule_id": self.id, "name": "Study", **days}
        )


@pytest.fixture
async def helper(hass_ws_client: WebSocketGenerator) -> Helper:
    return Helper(await hass_ws_client())


def block(start: str, end: str, **data: object) -> dict[str, Any]:
    return {"from": start, "to": end, **({"data": data} if data else {})}


async def follow_schedule(hass: HomeAssistant) -> None:
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")
    await async_call(
        hass, "climate", "set_preset_mode", entity_id="climate.study", preset_mode="schedule"
    )


def attributes(hass: HomeAssistant) -> dict[str, Any]:
    return dict(hass.states.get("climate.study").attributes)


async def test_blocks_hold_their_levels_and_early_start_recovers_to_the_next_one(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, helper: Helper
) -> None:
    freezer.move_to("2026-01-05T08:30:00+00:00")
    await helper.create(
        monday=[block("08:00", "10:00", preset="eco"), block("10:00", "12:00", heat_target=22)]
    )
    await async_import(hass, PLANT)
    await follow_schedule(hass)
    state = attributes(hass)
    assert state["temperature"] == 18
    assert state["schedule_level"] == "eco"
    assert state["schedule_status"] == "comfort"
    assert state["schedule_entity"] == "schedule.study"
    assert state["schedule_next_change"] == datetime(2026, 1, 5, 10, tzinfo=UTC)

    # 4 K below the next block's 22 °C at 1 K/h needs longer than the half-hour cap.
    await async_advance(hass, freezer, 3599, step=1800)
    assert not attributes(hass)["early_start"]
    await async_advance(hass, freezer, 1)
    state = attributes(hass)
    assert state["early_start"] and state["temperature"] == 22
    assert state["schedule_level"] == "target"
    assert hass.states.get("binary_sensor.study_heating_demand").state == "on"

    await async_advance(hass, freezer, 1800, step=1800)
    state = attributes(hass)
    assert not state["early_start"]
    assert state["temperature"] == 22 and state["schedule_status"] == "comfort"


async def test_editing_a_later_block_is_seen_without_a_state_change(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, helper: Helper
) -> None:
    freezer.move_to("2026-01-05T08:30:00+00:00")
    week = [block("08:00", "10:00"), block("10:00", "12:00", preset="eco")]
    await helper.create(monday=week)
    entry = await async_import(hass, PLANT)
    await follow_schedule(hass)
    await async_advance(hass, freezer, 3600, step=1800)
    assert not attributes(hass)["early_start"], "eco is lower than comfort"

    before = hass.states.get("schedule.study")
    await helper.update(monday=[week[0], block("10:00", "12:00", heat_target=23)])
    await hass.async_block_till_done()
    after = hass.states.get("schedule.study")
    assert (after.state, after.attributes) == (before.state, before.attributes)
    observed = entry.runtime_data.view.observations.schedules["schedule.study"]
    assert observed.next_active and observed.next_level.heat_target == 23

    # Half an hour before 10:00 is inside the cap for the 3 K the new level needs.
    await async_advance(hass, freezer, 1)
    state = attributes(hass)
    assert state["early_start"] and state["temperature"] == 23


async def test_setbacks_are_numbers_that_persist_across_a_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, helper: Helper
) -> None:
    freezer.move_to("2026-01-05T06:00:00+00:00")
    await helper.create(monday=[block("08:00", "10:00")])
    entry = await async_import(hass, PLANT)
    await follow_schedule(hass)
    assert attributes(hass)["temperature"] == 19
    assert hass.states.get("number.study_heating_setback").state == "2.0"
    assert hass.states.get("number.study_cooling_setback").state == "2.0"

    await async_call(
        hass, "number", "set_value", entity_id="number.study_heating_setback", value=3.5
    )
    assert attributes(hass)["temperature"] == 17.5
    assert attributes(hass)["schedule_level"] == "setback"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("number.study_heating_setback").state == "3.5"
    assert attributes(hass)["temperature"] == 17.5


def schedule_issues(hass: HomeAssistant) -> list[ir.IssueEntry]:
    return [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == "invalid_schedule_block"
    ]


async def test_an_unusable_block_raises_a_repair_until_it_is_edited(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, helper: Helper
) -> None:
    freezer.move_to("2026-01-05T08:30:00+00:00")
    await helper.create(
        monday=[block("08:00", "10:00"), block("10:00", "12:00", preset="eco", heat_target=20)]
    )
    await async_import(hass, PLANT)
    await follow_schedule(hass)
    (issue,) = schedule_issues(hass)
    assert issue.translation_placeholders is not None
    assert "Monday 10:00" in issue.translation_placeholders["blocks"]
    assert attributes(hass)["temperature"] == 21, "a later block does not affect this one"

    await async_advance(hass, freezer, 5400, step=1800)
    state = attributes(hass)
    assert state["schedule_status"] == "invalid_block" and state["temperature"] == 21

    await helper.update(monday=[block("08:00", "10:00"), block("10:00", "12:00", preset="eco")])
    await hass.async_block_till_done()
    await async_advance(hass, freezer, 1)
    assert schedule_issues(hass) == []
    assert attributes(hass)["temperature"] == 18
