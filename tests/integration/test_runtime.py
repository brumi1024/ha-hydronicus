"""What the runtime survives.

An evaluation that raises, a stored state it cannot read, and a platform that
fails to unload.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.hydronicus import runtime as runtime_module
from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.issues import IssueKind
from tests.integration.helpers import (
    REFERENCE_OUTPUTS,
    REFERENCE_PLANT,
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    reference_world,
    set_zone_temperature,
)


def issues(hass: HomeAssistant, kind: IssueKind) -> list[ir.IssueEntry]:
    return [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == kind
    ]


async def test_a_failed_evaluation_raises_a_repair_and_is_retried(
    hass: HomeAssistant,
    actuators: Actuators,
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    await async_set_options(hass, entry, armed=REFERENCE_OUTPUTS, control=True)
    await async_call(hass, "select", "select_option", entity_id="select.home_mode", option="heat")
    real_step = runtime_module.step
    failing = True

    def step(*args: Any) -> Any:
        if failing:
            raise KeyError("floor")
        return real_step(*args)

    monkeypatch.setattr(runtime_module, "step", step)
    with caplog.at_level(logging.ERROR):
        await async_call(
            hass, "climate", "set_hvac_mode", entity_id="climate.living_area", hvac_mode="heat"
        )
        set_zone_temperature(hass, "living_area", 19.0)
        await hass.async_block_till_done()

    assert "Plant Home could not evaluate and tries again in 60 seconds" in caplog.text
    (issue,) = issues(hass, IssueKind.EVALUATION_FAILED)
    assert issue.translation_placeholders == {"plant": "Home", "error": "KeyError: 'floor'"}
    assert actuators.calls == []

    # Nothing changes, so only the retry evaluates again.
    failing = False
    await async_advance(hass, freezer, 55, step=5)
    assert issues(hass, IssueKind.EVALUATION_FAILED)
    await async_advance(hass, freezer, 5)

    assert issues(hass, IssueKind.EVALUATION_FAILED) == []
    assert "switch.home_living_area_floor_heating_valve:on" in actuators.shorts()


async def test_a_stored_state_of_the_wrong_shape_starts_over(
    hass: HomeAssistant, hass_storage: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    stored = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]
    stored["state"] = ["not", "a", "mapping"]
    stored["outputs"] = {"switch.a": "not a mapping"}
    stored["commanding"] = {"plant": {"zones": "not a mapping"}, "outputs": []}

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert "The persisted state of Plant Home could not be read and starts over" in caplog.text
    assert "The previous configuration of Plant Home could not be read" in caplog.text
    assert hass.states.get("sensor.home_status").state == "off"


async def test_a_failed_platform_unload_leaves_the_plant_running(
    hass: HomeAssistant, actuators: Actuators, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    await async_set_options(hass, entry, armed=REFERENCE_OUTPUTS, control=True)
    await async_call(hass, "select", "select_option", entity_id="select.home_mode", option="heat")

    async def fail(*_args: Any) -> bool:
        return False

    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", fail)
    assert not await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.FAILED_UNLOAD

    await async_call(
        hass, "climate", "set_hvac_mode", entity_id="climate.living_area", hvac_mode="heat"
    )
    set_zone_temperature(hass, "living_area", 19.0)
    await hass.async_block_till_done()

    assert "switch.home_living_area_floor_heating_valve:on" in actuators.shorts()
    # Home Assistant will not unload an entry that failed to unload; stop it for the test.
    await entry.runtime_data.async_stop()
