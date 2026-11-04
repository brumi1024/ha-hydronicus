"""Characterization of a zone sensor that drops out or goes stale mid-cycle.

Each test starts from a radiator zone that is heating with its valve open, its
pump running, and its boiler on, then takes its temperature away, and pins
what ``step()`` and ``zone_demand`` do with it now.
"""

from __future__ import annotations

import pytest

from custom_components.hydronicus.core.demand import (
    DemandState,
    DigitalThermostatState,
    zone_demand,
    zone_values,
)
from custom_components.hydronicus.core.model import (
    Aggregation,
    DigitalThermostat,
    Mode,
    Sensor,
    Zone,
)
from custom_components.hydronicus.core.step import Reading, State

from .test_step import LONG_AGO, NOW, OFF, ON, RADIATOR, _plant, observe, run, targets

OUTPUTS = ("switch.valve", "switch.pump", "switch.boiler")
# The boiler was switched on a minute ago, inside its 300 s minimum on time.
BOILER_STARTED = {"switch.boiler": NOW - 60}

UNAVAILABLE = Reading(None, NOW)
STALE = Reading(19.0, LONG_AGO)


def heating_state() -> State:
    """The State after an evaluation in which the cold room heats."""
    plant = _plant(RADIATOR)
    cold = observe(plant, temperatures={"room": 19.0}, on=OUTPUTS, since=BOILER_STARTED)
    state, desired, _ = run(plant, cold)
    assert targets(desired, *OUTPUTS) == [ON, ON, ON]
    assert state.demands["room"] == DemandState(Mode.HEAT, True, NOW)
    return state


@pytest.mark.parametrize("reading", [UNAVAILABLE, STALE], ids=["unavailable", "stale"])
def test_a_lost_reading_ends_the_call_at_once_and_names_the_sensor(reading: Reading) -> None:
    plant = _plant(RADIATOR)
    lost = observe(plant, on=OUTPUTS, since=BOILER_STARTED, sensors={"sensor.room": reading})
    state, desired, _ = run(plant, lost, heating_state(), NOW + 1)
    assert desired.reasons["room"] == "idle: no usable temperature"
    assert desired.blocking_sensors == {"room": ("sensor.room",)}
    assert state.demands["room"] == DemandState(Mode.HEAT, False, NOW + 1)


def test_a_lost_reading_keeps_the_boiler_for_its_minimum_on_time() -> None:
    plant = _plant(RADIATOR)
    lost = observe(plant, on=OUTPUTS, since=BOILER_STARTED, sensors={"sensor.room": UNAVAILABLE})
    _, desired, _ = run(plant, lost, heating_state(), NOW + 1)
    assert targets(desired, *OUTPUTS) == [ON, ON, ON]
    assert desired.source_request is True
    min_on_ends = NOW - 60 + 300
    assert [(hold.target, hold.until) for hold in desired.holds] == [
        ("source", min_on_ends),
        ("switch.pump", min_on_ends),
    ]


def test_after_the_minimum_on_time_the_boiler_stops_and_the_pump_overruns() -> None:
    plant = _plant(RADIATOR)
    lost = observe(plant, on=OUTPUTS, since=BOILER_STARTED, sensors={"sensor.room": UNAVAILABLE})
    later = NOW + 241
    _, desired, _ = run(plant, lost, heating_state(), later)
    assert targets(desired, *OUTPUTS) == [ON, ON, OFF]
    assert desired.source_request is False
    assert [(hold.target, hold.kind.value) for hold in desired.holds] == [
        ("switch.pump", "overrun")
    ]


def test_a_reading_that_returns_inside_the_band_does_not_resume_the_call() -> None:
    """The call ended for want of a reading, so hysteresis starts again from off."""
    plant = _plant(RADIATOR)
    lost = observe(plant, on=OUTPUTS, since=BOILER_STARTED, sensors={"sensor.room": UNAVAILABLE})
    state, _, _ = run(plant, lost, heating_state(), NOW + 1)
    back = observe(plant, on=OUTPUTS, since=BOILER_STARTED, temperatures={"room": 20.9})
    state, desired, _ = run(plant, back, state, NOW + 2)
    assert desired.reasons["room"] == "idle: heat to 21.0 °C from 20.9 °C"
    assert state.demands["room"] == DemandState(Mode.HEAT, False, NOW + 1)


def test_a_reading_that_returns_cold_waits_for_the_thermostats_minimum_off_time() -> None:
    zone = Zone(
        slug="room",
        temperature=(Sensor("sensor.room"),),
        thermostat=DigitalThermostat(min_on=600.0, min_off=600.0),
    )
    heat = DigitalThermostatState(Mode.HEAT, 21.0)
    calling = DemandState(Mode.HEAT, True, NOW - 10)

    def reached(deadline: float) -> bool:
        return False

    dropped, demand = zone_demand(zone, heat, None, calling, NOW, reached)
    assert not demand.on and dropped == DemandState(Mode.HEAT, False, NOW)
    held, demand = zone_demand(zone, heat, 18.0, dropped, NOW + 60, reached)
    assert not demand.on and held == dropped
    assert demand.held_until == NOW + 600


def test_an_optional_sensor_dropping_out_moves_the_mean_and_can_start_a_call() -> None:
    zone = Zone(
        slug="room",
        temperature=(Sensor("sensor.a"), Sensor("sensor.b", required=False)),
        aggregation=Aggregation.MEAN,
    )
    both = {"sensor.a": Reading(20.6, NOW), "sensor.b": Reading(21.0, NOW)}
    only_a = {"sensor.a": Reading(20.6, NOW), "sensor.b": UNAVAILABLE}

    def reached(deadline: float) -> bool:
        return deadline <= NOW

    assert zone_values(zone, {}, both, reached) == [20.6, 21.0]
    assert zone_values(zone, {}, only_a, reached) == [20.6]
    zone = Zone(
        slug="room",
        temperature=zone.temperature,
        aggregation=zone.aggregation,
        thermostat=DigitalThermostat(min_on=0.0, min_off=0.0),
    )
    heat = DigitalThermostatState(Mode.HEAT, 21.0)
    assert not zone_demand(zone, heat, 20.8, None, NOW, reached)[1].on
    assert zone_demand(zone, heat, 20.6, None, NOW, reached)[1].on


# Frost protection

FROST_DROPOUT = "a dropout clears the frost state, so a reading below the release no longer heats"


def frost_state() -> State:
    """The State after frost protection started heating the room while the Plant is off."""
    plant = _plant(RADIATOR)
    freezing = observe(plant, mode=Mode.OFF, temperatures={"room": 4.0})
    state, desired, _ = run(plant, freezing, State(live=True, mode=Mode.OFF))
    assert desired.frost_protection == ("room",) and desired.mode is Mode.HEAT
    return state


def test_frost_protection_keeps_heating_below_its_release_without_a_dropout() -> None:
    plant = _plant(RADIATOR)
    warmer = observe(plant, mode=Mode.OFF, temperatures={"room": 5.5})
    state, desired, _ = run(plant, warmer, frost_state(), NOW + 60)
    assert desired.frost_protection == ("room",)
    assert state.frost == frozenset({"room"})


def test_frost_protection_stops_while_the_room_has_no_reading() -> None:
    plant = _plant(RADIATOR)
    lost = observe(plant, mode=Mode.OFF, sensors={"sensor.room": UNAVAILABLE})
    state, desired, _ = run(plant, lost, frost_state(), NOW + 60)
    assert desired.frost_protection == ()
    assert state.frost == frozenset()
    assert desired.reasons["room"] == "idle: thermostat off"


@pytest.mark.xfail(reason=FROST_DROPOUT, strict=True)
def test_frost_protection_resumes_below_its_release_after_a_dropout() -> None:
    plant = _plant(RADIATOR)
    lost = observe(plant, mode=Mode.OFF, sensors={"sensor.room": UNAVAILABLE})
    state, _, _ = run(plant, lost, frost_state(), NOW + 60)
    warmer = observe(plant, mode=Mode.OFF, temperatures={"room": 5.5})
    _, desired, _ = run(plant, warmer, state, NOW + 120)
    assert desired.frost_protection == ("room",)
