"""The documented trial kit: a synthetic package and a plant file bound to it.

These tests load ``docs/examples/trial/package.yaml`` through the real Home
Assistant helper and template integrations and import ``plant.yaml`` through
the config flow. Every actuator is a template switch backed by an
``input_boolean``, so a command shows up as a changed helper state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.setup import async_setup_component

from tests.integration.helpers import async_advance, async_call, async_import, async_set_options

TRIAL_KIT = Path(__file__).parents[2] / "docs" / "examples" / "trial"
PACKAGE_DOMAINS = ("input_number", "input_boolean", "template")
TRIAL_OUTPUTS = (
    "switch.hydronicus_trial_living_room_valve",
    "switch.hydronicus_trial_bedroom_valve",
    "switch.hydronicus_trial_pump",
)


async def async_setup_trial_package(hass: HomeAssistant) -> None:
    package = yaml.safe_load((TRIAL_KIT / "package.yaml").read_text(encoding="utf-8"))
    assert set(package) == set(PACKAGE_DOMAINS)
    for domain in PACKAGE_DOMAINS:
        assert await async_setup_component(hass, domain, {domain: package[domain]})
    await hass.async_block_till_done()


def record_actuator_calls(hass: HomeAssistant) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    @callback
    def record(event: Event[Any]) -> None:
        if event.data.get("domain") in ("switch", "input_boolean", "valve", "homeassistant"):
            calls.append(dict(event.data))

    hass.bus.async_listen(EVENT_CALL_SERVICE, record)
    return calls


def helper(hass: HomeAssistant, name: str) -> str:
    return hass.states.get(f"input_boolean.hydronicus_trial_{name}").state


async def test_the_trial_plant_imports_and_heats_through_dry_run_then_live(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await async_setup_trial_package(hass)
    calls = record_actuator_calls(hass)
    entry = await async_import(hass, (TRIAL_KIT / "plant.yaml").read_text(encoding="utf-8"))
    assert entry.state is ConfigEntryState.LOADED
    await async_set_options(hass, entry, armed=TRIAL_OUTPUTS, control=False)
    await async_call(
        hass, "select", "select_option", entity_id="select.trial_plant_mode", option="heat"
    )
    await async_call(
        hass, "climate", "set_hvac_mode", entity_id="climate.bedroom", hvac_mode="heat"
    )
    await async_call(
        hass,
        "input_number",
        "set_value",
        entity_id="input_number.hydronicus_trial_bedroom_temperature",
        value=18,
    )
    await async_advance(hass, freezer, 200, step=5)

    assert calls == [], "Dry run sends nothing"
    proposed = hass.states.get("sensor.trial_plant_status").attributes["proposed"]
    assert proposed == {
        "switch.hydronicus_trial_bedroom_valve": True,
        "switch.hydronicus_trial_pump": True,
    }

    await async_call(hass, "switch", "turn_on", entity_id="switch.trial_plant_control_equipment")
    assert helper(hass, "bedroom_valve") == "on"
    assert helper(hass, "pump") == "off", "the pump waits for the valve's opening time"
    await async_advance(hass, freezer, 185, step=5)
    assert helper(hass, "pump") == "on"
    assert helper(hass, "living_room_valve") == "off"


async def test_the_area_trial_plant_imports(hass: HomeAssistant) -> None:
    await async_setup_trial_package(hass)
    entry = await async_import(hass, (TRIAL_KIT / "plant-areas.yaml").read_text(encoding="utf-8"))

    assert entry.state is ConfigEntryState.LOADED
    assert [zone.slug for zone in entry.runtime_data.plant.zones] == ["living_room", "bedroom"]
