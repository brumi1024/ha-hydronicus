"""Observation quality and isolated advisory storage for recovery learning."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.util import dt as dt_util

from custom_components.hydronicus.core.model import DigitalThermostat, LearningMode, Mode
from custom_components.hydronicus.core.thermal import RecoveryEpisode, ThermalModel
from custom_components.hydronicus.learning import (
    MAX_EPISODE_DURATION,
    SAMPLE_INTERVAL,
    STALL_INTERVAL,
    LearningCoordinator,
    LearningSample,
    LearningSampler,
    store_key,
)
from custom_components.hydronicus.storage import async_store_plant
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    create_area,
    set_temperature,
)

START = 1_000_000.0

LEARNING_PLANT = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump, overrun: 0}
zones:
  study:
    areas: [study]
    thermostat:
      digital:
        target: 21
        min_on: 0
        min_off: 0
        learning: observe
        schedule: {entity: schedule.study, max_early_start: 1800}
    loops:
      radiator:
        valves: [{entity: switch.study_valve, opening_time: 0}]
        pump: pump
"""


def sample(now: float = START, **changes: Any) -> LearningSample:
    """Source-less valve and pump circulation with a manual comfort target."""
    return replace(
        LearningSample(
            zone="study",
            mode=Mode.HEAT,
            learning=LearningMode.OBSERVE,
            fingerprint="sensors+topology+thermostat-v1",
            temperature=19.0,
            temperature_at=now,
            target=21.0,
            preset="comfort",
            circulating=True,
            live=True,
        ),
        **changes,
    )


def update(sampler: LearningSampler, now: float, **changes: Any) -> None:
    observation = sample(now, **changes)
    sampler.update({observation.zone: observation}, now)


def episodes(sampler: LearningSampler, mode: Mode = Mode.HEAT) -> tuple[RecoveryEpisode, ...]:
    return sampler.zones["study"].models.get(mode, ThermalModel()).episodes


@pytest.mark.parametrize("mode,start,end", [(Mode.HEAT, 19.0, 21.0), (Mode.COOL, 23.0, 21.0)])
def test_source_less_circulation_can_observe_manual_comfort_recovery(
    mode: Mode, start: float, end: float
) -> None:
    sampler = LearningSampler()
    update(sampler, START, mode=mode, temperature=start, outdoor_temperature=4)
    assert sampler.next_sample_at == START + SAMPLE_INTERVAL
    update(sampler, START + 300, mode=mode, temperature=(start + end) / 2)
    update(sampler, START + 600, mode=mode, temperature=end)
    (episode,) = episodes(sampler, mode)
    assert episode.outcome == "reached"
    assert episode.started_at == START
    assert episode.ended_at == START + 600
    assert episode.deficit == 2
    assert episode.outdoor_temperature == 4  # Before-start context, never later weather.
    diagnostic = sampler.diagnostics(START + 600)["zones"]["study"]
    assert diagnostic["active"] is None
    assert diagnostic["evidence"] == "inferred_circulation"
    assert diagnostic["heat_delivery_measured"] is False
    assert diagnostic["models"][mode.value]["episodes"] == 1
    assert not sampler.estimate("study", mode, 2, START + 600).confidence


def test_event_storm_and_duplicate_sensor_reports_do_not_create_samples() -> None:
    sampler = LearningSampler()
    update(sampler, START)
    revision = sampler.revision
    for second in range(1, 300):
        update(sampler, START + second, temperature=20.0)
    assert sampler.zones["study"].active.reports == 1
    assert sampler.revision == revision
    update(sampler, START + 300, temperature=21, temperature_at=START)
    assert sampler.zones["study"].active.reports == 1
    assert episodes(sampler) == ()
    update(sampler, START + 600, temperature=21)
    assert episodes(sampler)[0].outcome == "reached"


def test_circulation_start_between_ticks_keeps_the_entire_startup_delay() -> None:
    sampler = LearningSampler()
    update(sampler, START, circulating=False)
    update(sampler, START + 47)
    assert sampler.zones["study"].active.started_at == START + 47
    assert sampler.zones["study"].active.reports == 1
    assert sampler.next_sample_at == START + 300
    update(sampler, START + 48, temperature=20)
    assert sampler.zones["study"].active.reports == 1
    update(sampler, START + 300, temperature=20)
    assert sampler.zones["study"].active.reports == 2
    update(sampler, START + 600, temperature=21)
    (episode,) = episodes(sampler)
    assert episode.started_at == START + 47
    assert episode.ended_at == START + 600
    assert episode.elapsed_seconds == 553


def test_a_cleared_guard_does_not_restart_until_cadence_or_new_circulation() -> None:
    sampler = LearningSampler()
    update(sampler, START)
    update(sampler, START + 30, permitted=False, reason="window_open")
    update(sampler, START + 40)
    assert sampler.zones["study"].active is None
    assert episodes(sampler)[0].outcome == "censored"
    update(sampler, START + 50, circulating=False)
    update(sampler, START + 60)
    assert sampler.zones["study"].active.started_at == START + 60
    assert sampler.zones["study"].active.reports == 1


def test_a_manual_change_at_a_sample_deadline_censors_before_any_restart() -> None:
    sampler = LearningSampler()
    update(sampler, START)
    update(sampler, START + 300, target=22)
    assert sampler.zones["study"].active is None
    assert episodes(sampler)[0].reason == "thermostat_changed"
    update(sampler, START + 301, target=22)
    assert sampler.zones["study"].active is None
    update(sampler, START + 600, target=22)
    assert sampler.zones["study"].active.started_at == START + 600


def test_subresolution_movement_does_not_train_a_success() -> None:
    sampler = LearningSampler()
    update(sampler, START, temperature=20.8, resolution=0.25)
    assert sampler.zones["study"].active is None
    update(sampler, START + 300, temperature=20.5, resolution=0.25)
    assert sampler.zones["study"].active is not None
    update(sampler, START + 600, temperature=20.6, resolution=0.25)
    assert episodes(sampler) == ()


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"learning": LearningMode.OFF}, "disabled"),
        ({"live": False}, "dry_run"),
        ({"permitted": False, "reason": "window_open"}, "window_open"),
        ({"permitted": False, "reason": "condensation"}, "condensation"),
        ({"permitted": False, "reason": "frost"}, "frost"),
        ({"permitted": False}, "blocked"),
        ({"mode": Mode.OFF}, "thermostat_changed"),
        ({"target": 23.0}, "thermostat_changed"),
        ({"preset": "eco"}, "thermostat_changed"),
        ({"temperature": None}, "temperature_unavailable"),
        ({"temperature_at": START - 1000}, "temperature_unavailable"),
        ({"temperature_at": START + 1000}, "temperature_unavailable"),
        ({"circulating": False}, "circulation_stopped"),
    ],
)
def test_interruptions_censor_before_next_sampling_deadline(
    changes: dict[str, Any], reason: str
) -> None:
    sampler = LearningSampler()
    update(sampler, START)
    update(sampler, START + 1, **changes)
    assert sampler.zones["study"].active is None
    assert episodes(sampler)[0].outcome == "censored"
    assert episodes(sampler)[0].reason == reason
    assert sampler.next_sample_at in (None, START + SAMPLE_INTERVAL)


@pytest.mark.parametrize(
    "changes",
    [
        {"target": None},
        {"target": float("nan")},
        {"temperature": float("nan")},
        {"temperature_at": None},
        {"temperature_at": float("nan")},
        {"temperature_max_age": 0},
        {"temperature_max_age": float("inf")},
        {"resolution": 0},
        {"resolution": float("nan")},
        {"mode": Mode.OFF},
        {"circulating": False},
        {"live": False},
    ],
)
def test_invalid_inputs_and_dry_run_never_start_an_episode(changes: dict[str, Any]) -> None:
    sampler = LearningSampler()
    update(sampler, START, **changes)
    assert sampler.zones["study"].active is None
    assert episodes(sampler) == ()


def test_target_arrival_can_complete_when_observed_pump_stops() -> None:
    sampler = LearningSampler()
    update(sampler, START)
    update(sampler, START + 300, temperature=20)
    update(sampler, START + 450, temperature=21, circulating=False)
    assert episodes(sampler)[0].outcome == "reached"
    assert episodes(sampler)[0].ended_at == START + 450
    # Guard changes still censor an apparent arrival at the same moment.
    update(sampler, START + 600)
    update(sampler, START + 900, temperature=21, circulating=False, permitted=False)
    assert episodes(sampler)[-1].outcome == "censored"


def test_unknown_heat_delivery_with_fresh_flat_temperature_is_a_failed_recovery() -> None:
    sampler = LearningSampler()
    update(sampler, START)
    for elapsed in range(300, int(STALL_INTERVAL) + 1, 300):
        update(sampler, START + elapsed)
    (episode,) = episodes(sampler)
    assert episode.outcome == "failed"
    assert episode.reason == "no_temperature_progress"
    assert not sampler.estimate("study", Mode.HEAT, 2, START + STALL_INTERVAL).confidence


def test_slow_continuing_progress_can_reach_deadline_but_not_train_success() -> None:
    sampler = LearningSampler()
    update(sampler, START, temperature=15)
    for elapsed in range(300, int(MAX_EPISODE_DURATION) + 1, 300):
        update(sampler, START + elapsed, temperature=15 + elapsed / 10000)
    (episode,) = episodes(sampler)
    assert episode.outcome == "failed"
    assert episode.reason == "recovery_timeout"


def test_repeated_old_report_does_not_look_like_stalled_heat_delivery() -> None:
    sampler = LearningSampler()
    update(sampler, START, temperature_max_age=MAX_EPISODE_DURATION + 100)
    for elapsed in range(300, int(MAX_EPISODE_DURATION) + 1, 300):
        update(
            sampler,
            START + elapsed,
            temperature_at=START,
            temperature_max_age=MAX_EPISODE_DURATION + 100,
        )
    (episode,) = episodes(sampler)
    assert episode.outcome == "censored"
    assert episode.reason == "insufficient_sensor_reports"


@pytest.mark.parametrize("jump", [601, -1])
def test_clock_gap_never_continues_partial_recovery(jump: int) -> None:
    sampler = LearningSampler()
    update(sampler, START)
    update(sampler, START + 300, temperature=20)
    update(sampler, START + 300 + jump)
    assert episodes(sampler)[0].outcome == "censored"
    assert episodes(sampler)[0].reason == "observation_gap"
    assert sampler.zones["study"].active.started_at == START + 300 + jump


def test_nonfinite_time_is_ignored_and_no_duration_is_invented() -> None:
    sampler = LearningSampler()
    update(sampler, float("nan"))
    assert sampler.zones == {}
    update(sampler, START)
    sampler.stop(START)
    assert episodes(sampler) == ()
    assert sampler.next_sample_at is None


def test_configuration_and_sensor_resolution_change_invalidates_before_first_estimate() -> None:
    sampler = LearningSampler()
    update(sampler, START)
    update(sampler, START + 300, temperature=21)
    stored = sampler.to_dict()
    restored = LearningSampler()
    restored.load(stored, START + 600)
    assert len(episodes(restored)) == 1
    assert restored.zones["study"].active is None
    restored.synchronize({"study": "different-resolved-sensor-or-topology"})
    assert restored.estimate("study", Mode.HEAT, 2, START + 600).episode_count == 0
    assert episodes(restored) == ()
    restored.synchronize({})
    assert restored.zones == {}
    assert not restored.estimate("removed", Mode.HEAT, 2, START + 600).confidence


def test_restart_retains_history_but_never_resumes_partial_episode() -> None:
    sampler = LearningSampler()
    update(sampler, START)
    update(sampler, START + 300, temperature=21)
    update(sampler, START + 600)
    stored = sampler.to_dict()
    restored = LearningSampler()
    restored.load(stored, START + 900)
    assert len(episodes(restored)) == 1
    assert restored.zones["study"].active is None
    assert restored.diagnostics(START + 900)["zones"]["study"]["reason"] == (
        "restored_without_active_episode"
    )
    update(restored, START + 900)
    assert restored.zones["study"].active.started_at == START + 900
    restored.reset("missing")
    restored.reset("study")
    assert episodes(restored) == ()
    assert restored.zones["study"].active is None


def test_model_history_is_bounded_and_expired_records_are_dropped_on_load() -> None:
    record = asdict(RecoveryEpisode(Mode.HEAT, START, START + 300, 2, "reached"))
    many = [
        dict(record, started_at=START + i * 600, ended_at=START + i * 600 + 300) for i in range(200)
    ]
    raw = {"zones": {"study": {"fingerprint": "v1", "models": {"heat": {"episodes": many}}}}}
    sampler = LearningSampler()
    sampler.load(raw, START + 200 * 600)
    assert len(episodes(sampler)) == 128
    sampler.load(raw, START + 32 * 86400)
    assert episodes(sampler) == ()


@pytest.mark.parametrize(
    "change",
    [
        {"mode": "cool"},
        {"outcome": "unknown"},
        {"started_at": True},
        {"ended_at": float("inf")},
        {"ended_at": START},
        {"deficit": 0},
        {"reason": []},
        {"predicted_seconds": -1},
        {"outdoor_temperature": "cold"},
    ],
)
def test_corrupt_zone_history_does_not_discard_another_zone(change: dict[str, Any]) -> None:
    sampler = LearningSampler()
    update(sampler, START)
    update(sampler, START + 300, temperature=21)
    stored = sampler.to_dict()
    stored["zones"]["broken"] = deepcopy(stored["zones"]["study"])
    stored["zones"]["broken"]["models"]["heat"]["episodes"][0].update(change)
    sampler.load(stored, START + 600)
    assert "broken" not in sampler.zones
    assert len(episodes(sampler)) == 1


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        {"zones": []},
        {"zones": {"study": None}},
        {"zones": {1: {}}},
        {"zones": {"study": {"fingerprint": 1, "models": {}}}},
        {"zones": {"study": {"fingerprint": "v1", "models": []}}},
        {"zones": {"study": {"fingerprint": "v1", "models": {"off": {}}}}},
        {"zones": {"study": {"fingerprint": "v1", "models": {"heat": []}}}},
        {"zones": {"study": {"fingerprint": "v1", "models": {"heat": {"episodes": {}}}}}},
        {"zones": {"study": {"fingerprint": "v1", "models": {"heat": {"episodes": [None]}}}}},
    ],
)
def test_corrupt_store_shapes_are_isolated(raw: object) -> None:
    sampler = LearningSampler()
    sampler.load(raw, START)
    assert sampler.zones == {}


async def test_coordinator_bounds_writes_and_flushes_only_its_own_store(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = dt_util.utcnow().timestamp()
    coordinator = LearningCoordinator(hass, "plant-entry")
    queue_save = Mock()
    monkeypatch.setattr(coordinator.store, "async_delay_save", queue_save)
    coordinator.synchronize({"study": sample().fingerprint})
    coordinator.update({"study": sample(now)}, now)
    assert coordinator.next_sample_at == now + 300
    for elapsed in range(1, 300):
        coordinator.update({"study": sample(now + elapsed)}, now + elapsed)
    assert queue_save.call_count == 1
    coordinator.update({"study": sample(now + 300, temperature=21)}, now + 300)
    assert queue_save.call_count == 2
    assert coordinator.diagnostics(now + 300)["zones"]["study"]["models"]["heat"]["episodes"] == 1
    assert not coordinator.estimate("study", Mode.HEAT, 2, now + 300).confidence
    coordinator.update({"study": sample(now + 600)}, now + 600)
    coordinator.stop(now + 700)
    coordinator.stop(now + 700)
    coordinator.update({"study": sample(now + 900, temperature=21)}, now + 900)
    coordinator.synchronize({"changed": "v2"})
    assert "changed" not in coordinator.sampler.zones
    freezer.tick(timedelta(seconds=700))
    await coordinator.async_stop(now + 700)
    await coordinator.async_stop()
    assert "hydronicus.plant-entry" not in hass_storage
    data = hass_storage[store_key("plant-entry")]["data"]
    assert len(data["zones"]["study"]["models"]["heat"]["episodes"]) == 2
    assert data["zones"]["study"]["models"]["heat"]["episodes"][-1]["outcome"] == "censored"
    restored = LearningCoordinator(hass, "plant-entry")
    await restored.async_load()
    assert restored.sampler.zones["study"].active is None
    assert len(episodes(restored.sampler)) == 2
    restored.reset("study")
    await restored.async_stop()
    assert hass_storage[store_key("plant-entry")]["data"]["zones"]["study"]["models"] == {}


async def test_failed_learning_load_cannot_reset_hydraulic_safety_state(
    hass: HomeAssistant, hass_storage: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    hydraulic_state = {"state": {"source_stopped_at": 1234}, "mode": "heat"}
    hass_storage["hydronicus.plant-entry"] = {"version": 1, "data": hydraulic_state}
    coordinator = LearningCoordinator(hass, "plant-entry")
    monkeypatch.setattr(
        coordinator.store, "async_load", AsyncMock(side_effect=ValueError("bad data"))
    )
    await coordinator.async_load()
    assert coordinator.sampler.zones == {}
    assert hass_storage["hydronicus.plant-entry"]["data"] == hydraulic_state
    await coordinator.async_stop()


async def setup_learning_plant(
    hass: HomeAssistant, *, learning: str = "observe", control: bool = True
) -> ConfigEntry:
    hass.states.async_set("switch.pump", "off")
    hass.states.async_set("switch.study_valve", "off")
    hass.states.async_set("schedule.study", "on")
    set_temperature(hass, "sensor.study", 19)
    create_area(hass, "Study", temperature="sensor.study")
    entry = await async_import(
        hass, LEARNING_PLANT.replace("learning: observe", f"learning: '{learning}'")
    )
    await async_set_options(
        hass, entry, armed=["switch.pump", "switch.study_valve"], control=control
    )
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")
    return entry


async def complete_runtime_recovery(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, entry: ConfigEntry
) -> None:
    await async_advance(hass, freezer, 300, step=60)
    assert entry.runtime_data.learning.sampler.zones["study"].active is not None
    for temperature in (19.7, 20.3, 21.2):
        await async_advance(hass, freezer, 300, step=60)
        set_temperature(hass, "sensor.study", temperature)
        await hass.async_block_till_done()
    assert episodes(entry.runtime_data.learning.sampler)[0].outcome == "reached"


@pytest.mark.parametrize("learning", ["off", "observe"])
async def test_runtime_observation_does_not_change_valve_or_pump_commands(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory, learning: str
) -> None:
    entry = await setup_learning_plant(hass, learning=learning)
    assert entry.runtime_data.plant.source is None
    assert actuators.shorts() == ["switch.study_valve:on", "switch.pump:on"]
    if learning == "observe":
        await complete_runtime_recovery(hass, freezer, entry)
        assert len(episodes(entry.runtime_data.learning.sampler)) == 1
    else:
        await async_advance(hass, freezer, 1200, step=60)
        set_temperature(hass, "sensor.study", 21.2)
        await hass.async_block_till_done()
    assert actuators.shorts() == [
        "switch.study_valve:on",
        "switch.pump:on",
        "switch.pump:off",
        "switch.study_valve:off",
    ]
    assert {call.entity_id for call in actuators.calls} == {"switch.study_valve", "switch.pump"}


async def test_runtime_dry_run_never_learns_proposed_circulation(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_learning_plant(hass, control=False)
    await async_advance(hass, freezer, 300, step=60)
    set_temperature(hass, "sensor.study", 21.2)
    await async_advance(hass, freezer, 300, step=60)
    assert actuators.calls == []
    assert entry.runtime_data.learning.sampler.zones["study"].active is None
    assert episodes(entry.runtime_data.learning.sampler) == ()


async def test_runtime_reload_preserves_history_and_censors_partial_recovery(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_learning_plant(hass)
    await complete_runtime_recovery(hass, freezer, entry)
    set_temperature(hass, "sensor.study", 19)
    await hass.async_block_till_done()
    await async_advance(hass, freezer, 300, step=60)
    old_runtime = entry.runtime_data
    old_start = old_runtime.learning.sampler.zones["study"].active.started_at
    await async_advance(hass, freezer, 60, step=60)
    actuators.clear()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restored = entry.runtime_data.learning.sampler
    assert entry.runtime_data is not old_runtime
    assert episodes(restored)[0].outcome == "reached"
    assert episodes(restored)[-1].reason == "stopped"
    assert (
        restored.zones["study"].active is None
        or restored.zones["study"].active.started_at > old_start
    )
    assert actuators.calls == []


async def test_assist_opt_in_preserves_observation_history(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_learning_plant(hass)
    await complete_runtime_recovery(hass, freezer, entry)
    runtime = entry.runtime_data
    old_fingerprint = runtime.learning.sampler.zones["study"].fingerprint
    zone = runtime.plant.zone("study")
    assert isinstance(zone.thermostat, DigitalThermostat)
    changed = replace(zone, thermostat=replace(zone.thermostat, learning=LearningMode.ASSIST))
    async_store_plant(hass, entry, replace(runtime.plant, zones=(changed,)))
    await hass.async_block_till_done()
    assert entry.runtime_data is not runtime
    restored = entry.runtime_data.learning.sampler
    assert restored.zones["study"].fingerprint == old_fingerprint
    assert episodes(restored)[0].outcome == "reached"


async def test_changed_area_sensor_invalidates_history_before_runtime_prediction(
    hass: HomeAssistant,
    actuators: Actuators,
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = await setup_learning_plant(hass)
    await complete_runtime_recovery(hass, freezer, entry)
    runtime = entry.runtime_data
    old_fingerprint = runtime.learning.sampler.zones["study"].fingerprint
    assert episodes(runtime.learning.sampler)
    original = runtime.learning.estimate
    checked = False

    def check_empty(*args: Any, **kwargs: Any) -> Any:
        nonlocal checked
        assert runtime.learning.sampler.zones["study"].fingerprint != old_fingerprint
        assert episodes(runtime.learning.sampler) == ()
        checked = True
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime.learning, "estimate", check_empty)
    set_temperature(hass, "sensor.study_replaced", 19)
    ar.async_get(hass).async_update("study", temperature_entity_id="sensor.study_replaced")
    await hass.async_block_till_done()
    assert checked
    assert entry.runtime_data is runtime


async def test_home_assistant_stop_flushes_censored_observation(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    actuators: Actuators,
    freezer: FrozenDateTimeFactory,
) -> None:
    entry = await setup_learning_plant(hass)
    await async_advance(hass, freezer, 360, step=60)
    assert entry.runtime_data.learning.sampler.zones["study"].active is not None
    actuators.clear()
    await hass.async_stop(force=True)
    assert actuators.calls == []
    data = hass_storage[store_key(entry.entry_id)]["data"]
    assert data["zones"]["study"]["models"]["heat"]["episodes"][-1]["reason"] == "stopped"


async def test_runtime_counts_fresh_flat_temperature_as_unknown_heat_delivery_failure(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup_learning_plant(hass)
    for _ in range(25):
        set_temperature(hass, "sensor.study", 19)
        await hass.async_block_till_done()
        await async_advance(hass, freezer, 300, step=60)
    (episode,) = episodes(entry.runtime_data.learning.sampler)
    assert episode.outcome == "failed"
    assert episode.reason == "no_temperature_progress"
    assert actuators.shorts() == ["switch.study_valve:on", "switch.pump:on"]
    assert not entry.runtime_data.learning.estimate(
        "study", Mode.HEAT, 2, dt_util.utcnow().timestamp()
    ).confidence
