"""Characterization of conflicting zone modes and a Plant mode toggled while heating.

The Plant mode is the Mode select's: a zone whose thermostat asks for the
other mode is not served, and a mode change waits for the old mode's flow to
stop and for the mode dwell after it.
"""

from __future__ import annotations

from dataclasses import replace

from custom_components.hydronicus.core.model import Mode
from custom_components.hydronicus.core.step import DigitalThermostatState, State

from .test_step import HEAT_PUMP, NOW, OFF, ON, _plant, observe, run, targets

FLOOR = ("switch.c_floor", "switch.floor_pump")
# HEAT_PUMP's mode dwell.
DWELL = 600.0


def test_a_heating_plant_does_not_serve_a_zone_whose_thermostat_cools() -> None:
    plant = _plant(HEAT_PUMP)
    base = observe(plant, temperatures={"a": 26.0, "b": 26.0, "c": 19.0})
    cooling = DigitalThermostatState(Mode.COOL, 24.0)
    conflict = replace(base, thermostats={**base.thermostats, "a": cooling, "b": cooling})
    _, desired, _ = run(plant, conflict)
    assert desired.mode is Mode.HEAT
    assert desired.demands["b"].mode is Mode.COOL and desired.demands["b"].on
    assert desired.outputs["switch.b_ceiling"] == OFF
    assert desired.reasons["c.floor"] == "wanted"
    assert desired.outputs["switch.c_floor"] == ON


def test_the_min_flow_path_opens_whatever_mode_its_zone_asks_for() -> None:
    """a.ceiling opens because the heat pump needs a path, not for zone a's cooling call."""
    plant = _plant(HEAT_PUMP)
    base = observe(plant, temperatures={"a": 26.0, "c": 19.0})
    conflict = replace(
        base, thermostats={**base.thermostats, "a": DigitalThermostatState(Mode.COOL, 24.0)}
    )
    _, desired, _ = run(plant, conflict)
    assert desired.reasons["a.ceiling"] == "min-flow path"
    assert desired.outputs["switch.a_ceiling"] == ON


def test_a_cooling_plant_does_not_serve_a_zone_whose_thermostat_heats() -> None:
    plant = _plant(HEAT_PUMP)
    base = observe(plant, mode=Mode.COOL, option="Cool", temperatures={"a": 26.0, "c": 19.0})
    conflict = replace(
        base, thermostats={**base.thermostats, "c": DigitalThermostatState(Mode.HEAT, 21.0)}
    )
    _, desired, _ = run(plant, conflict)
    assert desired.mode is Mode.COOL
    assert desired.demands["c"].mode is Mode.HEAT and desired.demands["c"].on
    assert targets(desired, *FLOOR) == [OFF, OFF]
    assert desired.outputs["switch.a_ceiling"] == ON


# The Plant mode toggled while heating flows


def heating() -> State:
    return State(live=True, mode=Mode.HEAT, last_mode=Mode.HEAT, flowing=True)


def test_heat_cool_heat_while_heating_flows_never_leaves_heat() -> None:
    plant = _plant(HEAT_PUMP)
    cold = {"c": 19.0}
    state = heating()
    for offset, mode in ((0, Mode.COOL), (5, Mode.HEAT), (10, Mode.COOL), (15, Mode.HEAT)):
        flowing = observe(plant, mode=mode, on=FLOOR, temperatures=cold)
        state, desired, _ = run(plant, flowing, state, NOW + offset)
        assert desired.mode is Mode.HEAT, offset
        assert targets(desired, *FLOOR) == [ON, ON], offset
    assert "mode" not in desired.reasons
    assert state.flow_ended is None


def stopped_for_cool() -> State:
    """Heating was asked to cool, and its floor pump was seen to stop a minute later."""
    plant = _plant(HEAT_PUMP)
    flowing = observe(plant, mode=Mode.COOL, on=FLOOR)
    state, _, _ = run(plant, flowing, heating())
    stopped = observe(plant, mode=Mode.COOL, since={"switch.floor_pump": NOW})
    state, desired, _ = run(plant, stopped, state, NOW + 60)
    assert desired.mode is Mode.OFF
    assert desired.reasons["mode"] == "waiting for the mode dwell before cool"
    assert state.flow_ended == NOW + 60
    return state


def test_asking_for_heat_again_during_the_dwell_resumes_heat_at_once() -> None:
    plant = _plant(HEAT_PUMP)
    again = observe(plant, mode=Mode.HEAT, temperatures={"c": 19.0})
    _, desired, _ = run(plant, again, stopped_for_cool(), NOW + 120)
    assert desired.mode is Mode.HEAT
    assert desired.outputs["switch.c_floor"] == ON


def test_passing_through_off_does_not_shorten_the_dwell_before_cool() -> None:
    plant = _plant(HEAT_PUMP)
    state, desired, _ = run(plant, observe(plant, mode=Mode.OFF), stopped_for_cool(), NOW + 120)
    assert desired.mode is Mode.OFF
    cool = observe(plant, mode=Mode.COOL, option="Cool")
    state, desired, _ = run(plant, cool, state, NOW + 130)
    assert desired.mode is Mode.OFF
    assert desired.reasons["mode"] == "waiting for the mode dwell before cool"
    _, desired, _ = run(plant, cool, state, NOW + 60 + DWELL)
    assert desired.mode is Mode.COOL
