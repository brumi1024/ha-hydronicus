"""Forecast recovery enters the shared proposal without acquiring equipment authority."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.hydronicus.core.model import Mode
from custom_components.hydronicus.core.thermal import (
    RecoveryEpisode,
    RecoveryEstimate,
    ThermalModel,
    record_episode,
)
from custom_components.hydronicus.runtime import PlantRuntime
from tests.integration.helpers import (
    Actuators,
    async_call,
    async_import,
    async_set_options,
    set_temperature,
)
from tests.integration.test_forecast import Provider, advance, rows, settled

PLANT = """
hydronicus: 2
name: Predictive
weather:
  entity: weather.forecast_home
  max_age: 7200
pumps:
  pump: {switch: switch.pump}
zones:
  study:
    temperature: [{entity: sensor.study, max_age: 14400}]
    thermostat:
      digital:
        target: 21
        min_on: 0
        min_off: 0
        learning: assist
        weather_aware: true
        schedule:
          entity: schedule.study
          max_early_start: 7200
          heating_rate: 2
    loops:
      floor: {pump: pump, valves: [{entity: switch.valve, opening_time: 0}], modes: [heat]}
"""


async def setup(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, *, live: bool = False
) -> tuple[ConfigEntry, Provider]:
    freezer.move_to("2026-02-01T07:00:00+00:00")
    provider = Provider(hass)
    provider.response["weather.forecast_home"]["forecast"] = rows(provider.now, (0,) * 6)
    hass.states.async_set("switch.pump", "off")
    hass.states.async_set("switch.valve", "off")
    set_temperature(hass, "sensor.study", 20)
    hass.states.async_set(
        "schedule.study",
        "off",
        {"next_event": datetime.fromtimestamp(provider.now + 10800, UTC).isoformat()},
    )
    entry = await async_import(hass, PLANT)
    if live:
        await async_set_options(hass, entry, armed=("switch.pump", "switch.valve"), control=True)
    await settled(hass)
    assert entry.runtime_data.plant.source is None
    return entry, provider


async def follow(hass: HomeAssistant) -> None:
    await async_call(
        hass, "select", "select_option", entity_id="select.predictive_mode", option="heat"
    )
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")
    await async_call(
        hass, "climate", "set_preset_mode", entity_id="climate.study", preset_mode="schedule"
    )


def mock_estimator(
    runtime: PlantRuntime,
    monkeypatch: pytest.MonkeyPatch,
    *,
    baseline_confidence: bool = True,
    weather_confidence: bool = True,
) -> Mock:
    def estimate(
        _zone: str, _mode: Mode, _deficit: float, now: float, outdoor: float | None = None
    ) -> RecoveryEstimate:
        weather = outdoor is not None
        return RecoveryEstimate(
            7200 if outdoor is not None and outdoor < 5 else 3600,
            weather_confidence if weather else baseline_confidence,
            "ready",
            "validated weather" if weather else "validated learned baseline",
            episode_count=14,
            valid_until=now + 86400,
            weather_adjusted=weather,
        )

    patched = Mock(side_effect=estimate)
    monkeypatch.setattr(runtime.learning, "estimate", patched)
    return patched


@pytest.mark.parametrize(
    "forecast_state,weather_confidence,baseline_confidence,method,seconds",
    [
        ("fresh", True, True, "weather", 7200),
        ("fresh", False, True, "learned", 3600),
        ("fresh", False, False, "configured", 1800),
        ("expired", True, True, "learned", 3600),
        ("expired", True, False, "configured", 1800),
        ("missing", True, True, "learned", 3600),
        ("short", True, True, "learned", 3600),
    ],
)
async def test_shared_proposal_uses_only_valid_forecast_and_confident_history(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
    forecast_state: str,
    weather_confidence: bool,
    baseline_confidence: bool,
    method: str,
    seconds: float,
) -> None:
    entry, provider = await setup(hass, freezer)
    runtime = entry.runtime_data
    estimator = mock_estimator(
        runtime,
        monkeypatch,
        baseline_confidence=baseline_confidence,
        weather_confidence=weather_confidence,
    )
    assert runtime.forecast is not None and runtime.forecast.snapshot is not None
    snapshot = runtime.forecast.snapshot
    if forecast_state == "expired":
        runtime.forecast.snapshot = replace(snapshot, expires_at=provider.now)
    elif forecast_state == "missing":
        runtime.forecast.snapshot = None
    elif forecast_state == "short":
        runtime.forecast.snapshot = replace(snapshot, points=snapshot.points[:2])
    await follow(hass)
    proposal = runtime.view.desired.comfort["study"]
    climate = hass.states.get("climate.study")
    assert proposal.recovery_method == method
    assert proposal.recovery_seconds == seconds
    assert climate.attributes["recovery_method"] == method
    assert climate.attributes["planned_recovery_seconds"] == seconds
    assert climate.attributes["effective_target"] == proposal.target == 19
    assert hass.states.get("binary_sensor.study_heating_demand").state == "off"
    if method == "weather":
        estimate = runtime.view.observations.recovery["study"]
        assert estimate.valid_until == snapshot.expires_at
        assert estimate.valid_until < provider.now + 86400
    if forecast_state != "fresh":
        assert all(len(call.args) == 4 for call in estimator.call_args_list)
    calls = len(provider.calls)
    for _ in range(10):
        runtime.evaluate()
    assert len(provider.calls) == calls
    await settled(hass)
    assert len(provider.calls) == calls
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_provider_updates_change_planning_without_revoking_latch_or_manual_override(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
    actuators: Actuators,
) -> None:
    entry, provider = await setup(hass, freezer, live=True)
    runtime = entry.runtime_data
    mock_estimator(runtime, monkeypatch)
    hass.states.async_set(
        "schedule.study",
        "off",
        {"next_event": datetime.fromtimestamp(provider.now + 14400, UTC).isoformat()},
    )
    await follow(hass)
    assert hass.states.get("climate.study").attributes["recovery_method"] == "weather"
    assert hass.states.get("climate.study").attributes["planned_recovery_seconds"] == 7200
    assert not hass.states.get("climate.study").attributes["early_start"]
    # A provider revision updates the same proposal displayed by the climate entity.
    provider.response["weather.forecast_home"]["forecast"] = rows(provider.now, (15,) * 6)
    await advance(hass, freezer, 3600)
    assert hass.states.get("climate.study").attributes["planned_recovery_seconds"] == 3600
    assert not hass.states.get("climate.study").attributes["early_start"]
    # A cold revision starts recovery at its cap through normal valve and pump sequencing.
    provider.response["weather.forecast_home"]["forecast"] = rows(provider.now, (0,) * 6)
    provider.report(temperature=0)
    await advance(hass, freezer, 3600)
    assert hass.states.get("climate.study").attributes["early_start"]
    assert hass.states.get("switch.valve").state == "on"
    assert hass.states.get("switch.pump").state == "on"
    assert {call.entity_id for call in actuators.calls} <= {"switch.valve", "switch.pump"}
    event = runtime.state.demands["study"].early_start_event
    assert event == provider.now + 14400
    # A later provider failure falls back for estimates but cannot revoke accepted recovery.
    provider.response = {}
    set_temperature(hass, "sensor.study", 20)
    provider.report()
    await advance(hass, freezer, 3600)
    assert runtime.forecast.snapshot is None
    assert runtime.state.demands["study"].early_start_event == event
    assert hass.states.get("climate.study").attributes["recovery_method"] == "latched"
    assert hass.states.get("climate.study").attributes["effective_target"] == 21
    await async_call(
        hass, "climate", "set_temperature", entity_id="climate.study", temperature=22.5
    )
    assert hass.states.get("climate.study").attributes["preset_mode"] == "none"
    assert runtime.state.demands["study"].early_start_event is None
    provider.response = {"weather.forecast_home": {"forecast": rows(dt_util.utcnow().timestamp())}}
    await advance(hass, freezer, 60)
    assert runtime.forecast.snapshot is not None
    assert hass.states.get("climate.study").attributes["effective_target"] == 22.5
    assert hass.states.get("climate.study").attributes["schedule_status"] == "manual"
    assert await hass.config_entries.async_unload(entry.entry_id)


def weather_history(now: float) -> ThermalModel:
    """Record each outcome after predicting it only from prior completed episodes."""
    model = ThermalModel()
    for index in range(28):
        cold = index % 2 == 0
        started = now - (28 - index) * 86400
        episode = RecoveryEpisode(
            mode=Mode.HEAT,
            started_at=started,
            ended_at=started + (7200 if cold else 3600),
            deficit=1,
            outcome="reached",
            outdoor_temperature=0 if cold else 15,
        )
        model = record_episode(model, episode, episode.ended_at)
    return model


async def test_real_weather_model_survives_reload_and_drives_only_source_less_outputs(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    actuators: Actuators,
) -> None:
    entry, provider = await setup(hass, freezer, live=True)
    runtime = entry.runtime_data
    runtime.learning.sampler.zones["study"].models[Mode.HEAT] = weather_history(provider.now)
    await follow(hass)
    estimate = runtime.view.observations.recovery["study"]
    assert estimate.confidence and estimate.weather_adjusted
    assert estimate.seconds == 7200
    assert estimate.episode_count == 14
    assert estimate.validation_count >= 3
    assert hass.states.get("climate.study").attributes["recovery_method"] == "weather"
    old_forecast = runtime.forecast
    assert await hass.config_entries.async_reload(entry.entry_id)
    await settled(hass)
    runtime = entry.runtime_data
    assert runtime.forecast is not old_forecast
    estimate = runtime.view.observations.recovery["study"]
    assert estimate.confidence and estimate.weather_adjusted
    assert estimate.seconds == 7200
    await advance(hass, freezer, 3600)
    assert hass.states.get("climate.study").attributes["early_start"]
    assert hass.states.get("switch.pump").state == "on"
    assert hass.states.get("switch.valve").state == "on"
    assert {call.entity_id for call in actuators.calls} <= {"switch.valve", "switch.pump"}
    count = len(provider.calls)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    await advance(hass, freezer, 3600)
    assert len(provider.calls) == count


async def test_provider_does_not_block_import_and_unload_cancels_late_publication(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    original = Provider.retrieve

    async def slow(provider: Provider, call: Any) -> dict[str, Any]:
        entered.set()
        await release.wait()
        return await original(provider, call)

    monkeypatch.setattr(Provider, "retrieve", slow)
    freezer.move_to("2026-02-01T07:00:00+00:00")
    provider = Provider(hass)
    hass.states.async_set("switch.pump", "off")
    hass.states.async_set("switch.valve", "off")
    set_temperature(hass, "sensor.study", 20)
    # Import waits for ordinary setup work, but never the background weather request.
    entry = await async_import(hass, PLANT)
    await entered.wait()
    assert entry.state is ConfigEntryState.LOADED
    runtime = entry.runtime_data
    assert runtime.forecast.snapshot is None
    assert await hass.config_entries.async_unload(entry.entry_id)
    release.set()
    await settled(hass)
    assert runtime.forecast.snapshot is None
    assert provider.calls == []
    await advance(hass, freezer, 3600)
    assert provider.calls == []
