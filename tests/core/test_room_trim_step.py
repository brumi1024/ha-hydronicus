"""The room trim in ``step()``: its holds, the reset, persistence, and the written setpoint."""

from __future__ import annotations

from dataclasses import replace

import pytest

from custom_components.hydronicus.core.dhw import DhwState
from custom_components.hydronicus.core.heating_supply import HeatingSupplyState, SupplyCommand
from custom_components.hydronicus.core.model import HeatingSupply, Mode, NumericTarget
from custom_components.hydronicus.core.plant_file import (
    PlantFileError,
    export_plant,
    read_plant_file,
)
from custom_components.hydronicus.core.room_trim import RoomTrimState
from custom_components.hydronicus.core.step import Observations, Reading, State, SwitchState

from .test_heating_curve import _dump, calling, curve_plant
from .test_step import NOW, _plant, run

HALF_HOUR = 1800.0
# The room leads at once, and the curve reads 35 °C at 5 °C outdoors.
TRIM = curve_plant(step=1, room_influence="{zones: [room], learn_after: 0}")


def trimmed(text: str = TRIM, temperature: float = 20.5, **kwargs: object) -> Observations:
    """The room calling 0.5 K below its 21 °C target, with the setpoint showing 35 °C."""
    observations = calling(text, 5.0, 35.0, **kwargs)
    return replace(
        observations,
        sensors={**observations.sensors, "sensor.room": Reading(temperature, NOW)},
    )


def settled(learned: float = 0.0) -> State:
    """A State whose filter has held the room's 0.5 K for half an hour."""
    return State(
        live=True,
        mode=Mode.HEAT,
        room_trim=RoomTrimState(0.5, NOW - HALF_HOUR, learned),
    )


def test_the_room_trim_learns_and_survives_a_restart() -> None:
    plant = _plant(TRIM)
    first, desired, _ = run(plant, trimmed())
    assert first.room_trim == RoomTrimState(0.5, NOW, 0.0)
    curve = desired.heating_curve
    assert curve is not None and curve.trim is not None and curve.curve == 35.0
    assert curve.trim.lead == "room" and curve.room_shift == pytest.approx(0.3)

    restored = State.from_dict(first.to_dict())
    assert restored.room_trim == first.room_trim
    later, desired, _ = run(plant, trimmed(), restored, NOW + HALF_HOUR)
    # 0.3 K beyond the deadband for half an hour at 0.3 K per hour per K.
    assert later.room_trim.learned == pytest.approx(0.045)
    assert later.room_trim.at == NOW + HALF_HOUR


def test_the_learned_part_moves_the_written_setpoint() -> None:
    _, desired, _ = run(_plant(TRIM), trimmed(), settled(1.4))
    assert desired.outputs["number.supply"] == NumericTarget(37, 0.5)
    assert desired.reasons["source_supply"] == (
        "supply target 37.0 °C: curve 35.0 °C, offset +0.0 K, room trim +1.7 K (learned +1.4 K)"
    )


def held(observations: Observations, state: State | None = None, text: str = TRIM) -> str | None:
    """Why the learned part kept its value in an evaluation half an hour after ``settled``."""
    next_state, desired, _ = run(_plant(text), observations, state or settled(0.5))
    assert next_state.room_trim.learned == 0.5
    curve = desired.heating_curve
    assert curve is not None and curve.trim is not None
    return curve.trim.held


def test_a_warm_up_holds_the_learned_part() -> None:
    observations = replace(trimmed(), supply_command=SupplyCommand(NOW, warm_up=True))
    assert held(observations) == "a warm-up holds the heating supply"


def test_hot_water_holds_the_learned_part() -> None:
    boosting = replace(settled(0.5), dhw=DhwState(boost=50.0, boost_until=NOW + 600))
    assert held(trimmed(), boosting) == "hot water has the source"
    disinfecting = replace(settled(0.5), dhw=DhwState(disinfect_started=NOW - 600))
    assert held(trimmed(), disinfecting) == "hot water has the source"


def test_a_held_off_request_holds_the_learned_part() -> None:
    text = TRIM.replace(
        "request: switch.boiler,", "request: switch.boiler, inhibit_sensor: binary_sensor.fire,"
    )
    observations = trimmed(text)
    observations = replace(observations, readiness={"binary_sensor.fire": SwitchState(True, NOW)})
    assert held(observations, text=text) == "the heating request is held off"


def test_a_plant_that_does_not_heat_on_the_curve_holds_the_learned_part() -> None:
    fixed = replace(trimmed(), supply_command=SupplyCommand(NOW, strategy=HeatingSupply.FIXED))
    assert held(fixed) == "the Plant does not heat on Hydronicus's heating curve"
    cooling = replace(settled(0.5), mode=Mode.COOL, last_mode=Mode.COOL)
    reason = held(replace(trimmed(), mode=Mode.COOL), cooling)
    assert reason == "the Plant does not heat on Hydronicus's heating curve"


def test_dry_run_holds_the_learned_part() -> None:
    assert held(replace(trimmed(), control=False)) == "the heating supply setpoint is only proposed"
    unarmed = replace(trimmed(), armed=trimmed().armed - {"number.supply"})
    assert held(unarmed) == "the heating supply setpoint is only proposed"


def test_a_curve_without_an_outdoor_reading_holds_the_learned_part() -> None:
    observations = trimmed()
    sensors = {key: value for key, value in observations.sensors.items() if key != "sensor.outdoor"}
    reason = held(replace(observations, sensors=sensors))
    assert reason == "the heating curve has no outdoor temperature"


def test_a_satisfied_lead_zone_lowers_the_learned_part() -> None:
    state, _, _ = run(_plant(TRIM), trimmed(temperature=21.0), settled(0.5))
    assert state.room_trim.learned < 0.5


def test_a_reset_forgets_the_learned_part_once() -> None:
    plant = _plant(TRIM)
    command = SupplyCommand(NOW - 60, reset_trim=True)
    state, desired, _ = run(plant, replace(trimmed(), supply_command=command), settled(1.5))
    # It starts again from nothing, and this evaluation's half hour counts.
    assert state.room_trim.learned == pytest.approx(0.045)
    assert state.heating_supply.command_at == NOW - 60
    # The same command, not yet cleared by the runtime, does not reset again.
    again = replace(state, room_trim=replace(state.room_trim, learned=1.0))
    state, _, _ = run(plant, replace(trimmed(), supply_command=command), again, NOW + 60)
    assert state.room_trim.learned == pytest.approx(1.0, abs=0.01)


# The written setpoint


@pytest.mark.parametrize(
    ("offset", "target"),
    [
        # Within 0.6 of a step of the last proposal, it stays.
        (0.55, 35),
        (-0.55, 35),
        # Beyond it, the proposal rounds to the nearest step.
        (0.65, 36),
        (-0.65, 34),
    ],
)
def test_a_stepped_heating_target_moves_only_beyond_its_hysteresis(
    offset: float, target: float
) -> None:
    text = curve_plant(step=1)
    state = State(live=True, mode=Mode.HEAT, heating_supply=HeatingSupplyState(last_target=35.0))
    observations = replace(calling(text, 5.0, 35.0), curve_offset=offset)
    next_state, desired, _ = run(_plant(text), observations, state)
    assert desired.outputs["number.supply"] == NumericTarget(target, 0.5)
    assert next_state.heating_supply.last_target == target
    # Hydronicus's own value showing is never taken for a change made elsewhere.
    assert desired.heating_supply is not None
    assert desired.heating_supply.strategy is HeatingSupply.CURVE
    assert not desired.heating_supply.events


def test_the_hysteresis_keeps_no_target_off_the_setpoint_resolution() -> None:
    text = curve_plant(step=1)
    state = State(live=True, mode=Mode.HEAT, heating_supply=HeatingSupplyState(last_target=35.5))
    observations = replace(calling(text, 5.0, 35.0), curve_offset=0.3)
    _, desired, _ = run(_plant(text), observations, state)
    assert desired.outputs["number.supply"] == NumericTarget(35, 0.5)


# Plant file


def test_the_room_trim_settings_survive_an_export() -> None:
    text = curve_plant(
        room_influence=(
            "{zones: [room], smoothing: 7200, deadband: 0.3, learn_rate: 0.1,"
            " learn_limit: 1.5, learn_after: 14400}"
        )
    )
    plant = _plant(text)
    influence = export_plant(plant)["source"]["supply"]["room_influence"]
    assert influence == {
        "zones": ["room"],
        "smoothing": 7200,
        "deadband": 0.3,
        "learn_rate": 0.1,
        "learn_limit": 1.5,
        "learn_after": 14400,
    }
    assert read_plant_file(_dump(export_plant(plant))) == plant


def test_a_room_influence_without_the_new_keys_gets_their_defaults() -> None:
    plant = _plant(curve_plant(room_influence="{zones: [room]}"))
    assert plant.source is not None and plant.source.supply is not None
    influence = plant.source.supply.room_influence
    assert influence is not None
    assert (influence.limit, influence.smoothing, influence.deadband) == (2.0, 3600.0, 0.2)
    assert (influence.learn_rate, influence.learn_limit, influence.learn_after) == (
        0.3,
        2.0,
        28800.0,
    )
    assert export_plant(plant)["source"]["supply"]["room_influence"] == {"zones": ["room"]}


@pytest.mark.parametrize(
    "setting",
    [
        "smoothing: -1",
        "smoothing: 90000",
        "deadband: -0.1",
        "deadband: 3",
        "learn_rate: -0.1",
        "learn_rate: 6",
        "learn_limit: 0",
        "learn_after: -1",
    ],
)
def test_room_trim_settings_are_checked(setting: str) -> None:
    with pytest.raises(PlantFileError) as error:
        read_plant_file(curve_plant(room_influence=f"{{zones: [room], {setting}}}"))
    key = setting.split(":")[0]
    assert error.value.path == f"source.supply.room_influence.{key}"
