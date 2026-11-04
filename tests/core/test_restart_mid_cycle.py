"""Characterization of a restart mid-cycle, with the stored State and without it.

A restart restores the State that ``step()`` persisted, so its timers carry on.
When the store is lost, for example because it had the wrong shape, ``step()``
starts from ``State()`` and sees only what the outputs show. These tests pin
what each of the two does with the same observations.
"""

from __future__ import annotations

from custom_components.hydronicus.core.demand import DemandState
from custom_components.hydronicus.core.model import Mode, Plant
from custom_components.hydronicus.core.step import Observations, State, step

from .test_step import NOW, OFF, ON, RADIATOR, _plant, observe, targets

# RADIATOR with a thermostat that holds its decisions for ten minutes.
HELD_RADIATOR = RADIATOR.replace(
    "{digital: {min_on: 0, min_off: 0}}", "{digital: {min_on: 600, min_off: 600}}"
)
OUTPUTS = ("switch.valve", "switch.pump", "switch.boiler")
# The zone and the boiler started a minute before the restart.
STARTED = NOW - 60


def stored_heating_state() -> State:
    """The State persisted a moment before the restart, while the room heated."""
    return State(
        live=True,
        mode=Mode.HEAT,
        last_mode=Mode.HEAT,
        flowing=True,
        source_request=True,
        source_changed=STARTED,
        source_observed=True,
        source_observed_changed=STARTED,
        source_starts=(STARTED,),
        source_demanding=True,
        demands={"room": DemandState(Mode.HEAT, True, STARTED)},
        ready={"switch.valve": NOW - 3600},
    )


def after_restart(temperature: float) -> tuple[Plant, Observations]:
    plant = _plant(HELD_RADIATOR)
    return plant, observe(
        plant, temperatures={"room": temperature}, on=OUTPUTS, since={"switch.boiler": STARTED}
    )


def test_a_restored_call_inside_the_band_is_held_for_its_minimum_on_time() -> None:
    plant, observations = after_restart(21.2)
    state, desired, _ = step(plant, observations, stored_heating_state(), NOW)
    assert desired.reasons["room"].endswith("held for its minimum on time")
    assert state.demands["room"] == DemandState(Mode.HEAT, True, STARTED)
    assert targets(desired, *OUTPUTS) == [ON, ON, ON]
    assert desired.reasons["source"] == "requested"


def test_a_restored_call_ends_when_its_minimum_on_time_has_passed_during_the_restart() -> None:
    plant, observations = after_restart(21.2)
    later = STARTED + 600
    state, desired, _ = step(plant, observations, stored_heating_state(), later)
    assert state.demands["room"] == DemandState(Mode.HEAT, False, later)
    assert desired.source_request is False
    assert desired.reasons["source"] == "released"


def test_without_the_store_a_call_inside_the_band_is_not_resumed() -> None:
    plant, observations = after_restart(21.2)
    state, desired, _ = step(plant, observations, State(), NOW)
    assert desired.reasons["room"] == "idle: heat to 21.0 °C from 21.2 °C"
    assert state.demands["room"] == DemandState(Mode.HEAT, False, None)


def test_without_the_store_a_boiler_found_on_is_released_inside_its_minimum_on_time() -> None:
    """The boiler's 300 s minimum on time counts from an observed start a minute ago."""
    plant, observations = after_restart(21.2)
    state, desired, _ = step(plant, observations, State(), NOW)
    assert state.source_observed_changed == STARTED
    assert desired.reasons["source"] == "no ready loop calls"
    assert targets(desired, *OUTPUTS) == [ON, ON, OFF]


def test_without_the_store_a_cold_room_keeps_the_boiler_it_finds_on() -> None:
    plant, observations = after_restart(19.0)
    state, desired, _ = step(plant, observations, State(), NOW)
    assert state.demands["room"] == DemandState(Mode.HEAT, True, NOW)
    assert targets(desired, *OUTPUTS) == [ON, ON, ON]
    assert desired.reasons["source"] == "requested"
    assert state.source_observed_changed == STARTED
