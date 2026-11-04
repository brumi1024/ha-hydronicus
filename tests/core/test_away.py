"""The Plant away: each digital thermostat's away level, and its early return."""

from __future__ import annotations

from dataclasses import replace

import pytest

from custom_components.hydronicus.core.comfort import Away, away_target
from custom_components.hydronicus.core.model import (
    AwayConfig,
    DigitalThermostat,
    Mode,
    Preset,
    Schedule,
)
from custom_components.hydronicus.core.plant_file import (
    PlantFileError,
    export_plant,
    read_plant_file,
)
from custom_components.hydronicus.core.step import DigitalThermostatState, State
from tests.core.test_demand import NOW, Clock

from .test_step import RADIATOR, _plant, observe, run

PLAIN = DigitalThermostat()
FOREVER = Away()
SCHEDULED = DigitalThermostat(schedule=Schedule("schedule.room", max_early_start=7200))


def target(
    config: DigitalThermostat = PLAIN,
    mode: Mode = Mode.HEAT,
    temperature: float | None = 18.0,
    away: Away = FOREVER,
    now: float = NOW,
    latched: float | None = None,
) -> tuple[float | None, str | None]:
    result = away_target(
        config, mode, 21.0, temperature, away, AwayConfig(), now, Clock(now), latched
    )
    return (None, None) if result is None else (result.target, result.schedule_status)


@pytest.mark.parametrize(("mode", "expected"), [(Mode.HEAT, 16.0), (Mode.COOL, 30.0)])
def test_away_holds_the_plant_targets_without_an_away_preset(mode: Mode, expected: float) -> None:
    assert target(mode=mode) == (expected, "away")


def test_away_holds_the_thermostats_own_away_preset() -> None:
    config = DigitalThermostat(presets=((Preset.AWAY, 14.0),))
    assert target(config) == (14.0, "away")


def test_away_does_nothing_in_off_or_after_its_return_time() -> None:
    assert target(mode=Mode.OFF) == (None, None)
    assert target(away=Away(NOW)) == (None, None)


def test_away_returns_early_within_the_schedules_bound() -> None:
    # 3 K below 21 °C at 1 K/h needs 3 h, bounded to the schedule's 2 h.
    away = Away(NOW + 7200)
    assert target(SCHEDULED, away=away, now=NOW - 1) == (16.0, "away")
    assert target(SCHEDULED, away=away, now=NOW) == (21.0, "away_return")


def test_an_early_return_stays_once_it_began() -> None:
    away = Away(NOW + 3600)
    assert target(SCHEDULED, temperature=20.9, away=away) == (16.0, "away")
    assert target(SCHEDULED, temperature=20.9, away=away, latched=NOW + 3600) == (
        21.0,
        "away_return",
    )


def test_without_a_schedule_there_is_no_early_return() -> None:
    assert target(away=Away(NOW + 60)) == (16.0, "away")


def test_away_lowers_a_zones_target_and_ends_by_itself() -> None:
    plant = _plant(RADIATOR)
    cold = observe(plant, temperatures={"room": 20.0})
    _, desired, _ = run(plant, cold)
    assert desired.demands["room"].on
    away = replace(cold, away=Away(NOW + 600))
    state, desired, due = run(plant, away)
    assert not desired.demands["room"].on
    assert desired.comfort["room"].target == 16.0
    assert due is not None and due <= 600 + 1
    _, desired, _ = run(plant, away, state, NOW + 600)
    assert desired.demands["room"].on, "the return time ended the away"


def test_frost_protection_heats_while_away() -> None:
    plant = _plant(RADIATOR)
    frozen = replace(observe(plant, temperatures={"room": 4.0}), away=Away())
    _, desired, _ = run(plant, frozen, State(live=True, mode=Mode.HEAT))
    assert desired.demands["room"].on
    assert desired.frost_protection == ("room",)


def test_away_never_changes_the_thermostats_targets() -> None:
    plant = _plant(RADIATOR)
    away = replace(observe(plant, temperatures={"room": 20.0}), away=Away())
    assert away.thermostats["room"] == DigitalThermostatState(Mode.HEAT, 21.0)
    _, desired, _ = run(plant, away)
    assert desired.comfort["room"].target == 16.0


def test_the_away_targets_survive_an_export_and_are_checked() -> None:
    text = RADIATOR.replace("name: Flat\n", "name: Flat\naway: {heat_target: 15}\n")
    plant = read_plant_file(text)
    assert plant.away == AwayConfig(heat_target=15.0)
    assert export_plant(plant)["away"] == {"heat_target": 15}
    with pytest.raises(PlantFileError) as error:
        read_plant_file(text.replace("heat_target: 15", "heat_target: 2"))
    assert error.value.path == "away.heat_target"
