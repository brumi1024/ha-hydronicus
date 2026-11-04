"""The heartbeat: it advances while the Plant watches its live outputs, and only then."""

from __future__ import annotations

from datetime import datetime

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from custom_components.hydronicus import runtime as runtime_module
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
)

FLAT = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump}
zones:
  flat:
    temperature: [sensor.flat]
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      radiator: {valves: [{entity: switch.valve, opening_time: 0}], pump: pump}
"""
HEARTBEAT = "sensor.flat_heartbeat"


async def _flat(hass: HomeAssistant, *, control: bool = True) -> object:
    Actuators(hass)
    for entity in ("switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set("sensor.flat", "18", {"unit_of_measurement": "°C"})
    entry = await async_import(hass, FLAT)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=control)
    return entry


def beat(hass: HomeAssistant) -> datetime | None:
    state = hass.states.get(HEARTBEAT).state
    return None if state in ("unknown", "unavailable") else datetime.fromisoformat(state)


async def test_it_advances_every_minute_and_lists_the_outputs_wanted_on(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await _flat(hass)
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.flat", hvac_mode="heat")
    await async_advance(hass, freezer, 5)
    first = beat(hass)
    assert first is not None
    assert hass.states.get(HEARTBEAT).attributes["on_outputs"] == ["switch.pump", "switch.valve"]
    await async_advance(hass, freezer, 60)
    second = beat(hass)
    assert second is not None and second > first


async def test_it_is_unknown_in_dry_run(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await _flat(hass, control=False)
    await async_advance(hass, freezer, 120)
    assert beat(hass) is None
    assert hass.states.get(HEARTBEAT).attributes["on_outputs"] == []


async def test_it_stops_while_evaluations_fail(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = await _flat(hass)
    await async_advance(hass, freezer, 5)
    assert beat(hass) is not None

    def failing(*_: object) -> object:
        raise RuntimeError("broken")

    monkeypatch.setattr(runtime_module, "step", failing)
    entry.runtime_data.request_evaluation()  # type: ignore[attr-defined]
    await async_advance(hass, freezer, 120)
    assert beat(hass) is None
