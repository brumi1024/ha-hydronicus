"""Automatic heat and cool changeover from an averaged outdoor temperature."""

from __future__ import annotations

from dataclasses import replace
from math import exp

import pytest

from custom_components.hydronicus.core.changeover import ChangeoverState, changeover
from custom_components.hydronicus.core.model import Changeover, Mode
from custom_components.hydronicus.core.plant_file import (
    PlantFileError,
    export_plant,
    read_plant_file,
)
from custom_components.hydronicus.core.step import Reading, State

from .test_step import HEAT_PUMP, NOW, _plant, observe, run

CONFIG = Changeover("sensor.outdoor")
DAY = 86400.0


def outdoor(value: float, at: float = NOW) -> dict[str, Reading]:
    return {"sensor.outdoor": Reading(value, at)}


def test_a_first_reading_starts_the_average_and_chooses_its_mode() -> None:
    result = changeover(CONFIG, outdoor(25.0), NOW, ChangeoverState())
    assert result.state == ChangeoverState(25.0, NOW, Mode.COOL, NOW)
    assert result.reason.startswith("auto: cool, mean 25.0 °C")


def test_the_average_moves_by_its_time_constant() -> None:
    previous = ChangeoverState(10.0, NOW - 3600, Mode.HEAT, None)
    result = changeover(CONFIG, outdoor(20.0), NOW, previous)
    assert result.state.average == pytest.approx(10 + 10 * (1 - exp(-3600 / DAY)))
    assert result.state.mode is Mode.HEAT


@pytest.mark.parametrize("value", [15.1, 18.0, 21.9])
def test_inside_the_band_the_mode_stays(value: float) -> None:
    for mode in (Mode.HEAT, Mode.COOL):
        result = changeover(CONFIG, outdoor(value), NOW, ChangeoverState(mode=mode))
        assert result.state.mode is mode


def test_a_change_waits_for_the_minimum_time_after_the_last() -> None:
    previous = ChangeoverState(23.0, NOW - 60, Mode.HEAT, NOW - 3600)
    result = changeover(CONFIG, outdoor(23.0), NOW, previous)
    assert result.state.mode is Mode.HEAT
    assert result.due == NOW - 3600 + 43200
    ends = NOW - 3600 + 43200
    later = changeover(CONFIG, outdoor(23.0, ends), ends, result.state)
    assert later.state.mode is Mode.COOL


@pytest.mark.parametrize("reading", [None, Reading(None, NOW), Reading(30.0, NOW - 3600)])
def test_an_unusable_reading_keeps_the_mode_and_the_average(reading: Reading | None) -> None:
    previous = ChangeoverState(10.0, NOW - 60, Mode.HEAT, None)
    sensors = {} if reading is None else {"sensor.outdoor": reading}
    result = changeover(CONFIG, sensors, NOW, previous)
    assert result.state == previous
    assert "not usable" in result.reason


def test_the_state_survives_a_restart() -> None:
    state = ChangeoverState(12.5, NOW, Mode.COOL, NOW - 10)
    assert ChangeoverState.from_dict(state.to_dict()) == state
    restored = State.from_dict(replace(State(), changeover=state).to_dict())
    assert restored.changeover == state


AUTO = HEAT_PUMP.replace(
    "mode_dwell: 600\n", "mode_dwell: 600\nchangeover: {outdoor_sensor: sensor.outdoor}\n"
)


def test_auto_runs_the_plant_in_the_mode_the_average_chose() -> None:
    plant = _plant(AUTO)
    warm = replace(observe(plant, mode=Mode.HEAT, sensors=outdoor(26.0)), auto=True)
    state, desired, _ = run(plant, warm, State(live=True))
    assert state.changeover.mode is Mode.COOL
    assert desired.reasons["changeover"].startswith("auto: cool")
    assert desired.mode in (Mode.COOL, Mode.OFF)


def test_without_auto_the_select_decides_and_the_changeover_state_stays() -> None:
    plant = _plant(AUTO)
    kept = ChangeoverState(26.0, NOW - 60, Mode.COOL, NOW - 60)
    observations = observe(plant, mode=Mode.HEAT, sensors=outdoor(10.0))
    state, desired, _ = run(plant, observations, replace(State(live=True), changeover=kept))
    assert state.changeover == kept
    assert "changeover" not in desired.reasons


def test_the_changeover_survives_an_export_and_is_checked() -> None:
    text = AUTO.replace(
        "{outdoor_sensor: sensor.outdoor}", "{outdoor_sensor: sensor.outdoor, cool_above: 24}"
    )
    plant = read_plant_file(text)
    assert export_plant(plant)["changeover"] == {
        "outdoor_sensor": "sensor.outdoor",
        "cool_above": 24,
    }
    with pytest.raises(PlantFileError) as error:
        read_plant_file(text.replace("cool_above: 24", "cool_above: 10"))
    assert error.value.path == "changeover.cool_above"
