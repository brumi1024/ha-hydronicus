"""The timers that hold an object as it is, which the desired state names with their ends."""

from __future__ import annotations

from dataclasses import replace

from custom_components.hydronicus.core.model import Desired, HoldKind, Mode
from custom_components.hydronicus.core.step import (
    GUARD_MIN_BLOCKED,
    DemandState,
    ExerciseState,
    GuardState,
    State,
)

from .test_step import (
    HEAT_PUMP,
    NOW,
    RADIATOR,
    WINDOWED,
    _plant,
    observe,
    run,
    windows,
)


def holds(desired: Desired, target: str) -> dict[HoldKind, float | None]:
    return {hold.kind: hold.until for hold in desired.holds if hold.target == target}


def test_a_pump_waits_for_its_opening_valve_and_both_name_when_it_is_ready() -> None:
    plant = _plant(RADIATOR)
    cold = {"room": 19.0}
    _, desired, _ = run(plant, observe(plant, temperatures=cold))
    assert desired.reasons["switch.pump"] == "waiting for its valves to open"
    assert holds(desired, "switch.pump") == {HoldKind.WAITING_FOR_VALVES: None}, (
        "the valve is not seen open yet, so its end is open"
    )

    opening = observe(
        plant, temperatures=cold, on=["switch.valve"], since={"switch.valve": NOW - 60}
    )
    _, desired, _ = run(plant, opening)
    assert holds(desired, "switch.valve") == {HoldKind.VALVE_OPENING: NOW + 120}
    assert holds(desired, "switch.pump") == {HoldKind.WAITING_FOR_VALVES: NOW + 120}

    _, desired, _ = run(plant, observe(plant, temperatures=cold, on=["switch.valve"]))
    assert desired.holds == () and "switch.pump" not in desired.reasons


def test_an_overrun_names_its_end_and_a_closing_valve_its_travel() -> None:
    plant = _plant(RADIATOR)
    running = observe(plant, on=["switch.valve", "switch.pump"])
    state, desired, _ = run(plant, running)
    assert desired.reasons["switch.pump"] == "overrun"
    assert holds(desired, "switch.pump") == {HoldKind.OVERRUN: NOW + 120}

    closing = observe(plant, since={"switch.valve": NOW + 200, "switch.pump": NOW + 120})
    winding = replace(state, overruns={}, winding=frozenset({"switch.valve"}))
    _, desired, _ = run(plant, closing, winding, NOW + 230)
    assert holds(desired, "switch.valve") == {HoldKind.VALVE_CLOSING: NOW + 380}


def test_the_source_names_its_minimum_on_and_off_times_and_its_post_run() -> None:
    plant = _plant(RADIATOR)
    cold = {"room": 19.0}
    state, _, _ = run(plant, observe(plant, temperatures=cold, on=["switch.valve", "switch.pump"]))
    warm = observe(
        plant,
        temperatures={"room": 22.0},
        on=["switch.valve", "switch.pump", "switch.boiler"],
        since={"switch.boiler": NOW},
    )
    held, desired, _ = run(plant, warm, state, NOW + 100)
    assert holds(desired, "source")[HoldKind.MIN_ON] == NOW + 300

    released, _, _ = run(plant, warm, held, NOW + 300)
    stopped = observe(
        plant,
        temperatures=cold,
        on=["switch.valve", "switch.pump"],
        since={"switch.boiler": NOW + 300},
    )
    _, desired, _ = run(plant, stopped, released, NOW + 330)
    assert holds(desired, "source") == {
        HoldKind.POST_RUN: NOW + 360,
        HoldKind.MIN_OFF: NOW + 600,
    }
    assert [hold.until for hold in desired.holds] == sorted(
        hold.until or 0.0 for hold in desired.holds
    ), "ordered by when they end"


def test_a_source_waiting_for_proof_names_its_feedback_timeout() -> None:
    plant = _plant(
        RADIATOR.replace("min_off: 300}", "min_off: 300, running_sensor: binary_sensor.burner}")
    )
    observed = observe(
        plant,
        temperatures={"room": 19.0},
        on=["switch.valve", "switch.pump", "switch.boiler"],
        since={"switch.boiler": NOW - 10},
        readiness={"binary_sensor.burner": False},
    )
    state = State(
        live=True,
        mode=Mode.HEAT,
        last_mode=Mode.HEAT,
        source_request=True,
        source_observed=True,
        source_observed_changed=NOW - 10,
    )
    _, desired, _ = run(plant, observed, state)
    assert desired.source_request
    assert holds(desired, "source")[HoldKind.FEEDBACK] == NOW + 290


def test_a_mode_change_names_the_end_of_its_dwell() -> None:
    plant = _plant(HEAT_PUMP)
    ended = State(live=True, mode=Mode.OFF, last_mode=Mode.HEAT, flow_ended=NOW - 100)
    _, desired, _ = run(plant, observe(plant, mode=Mode.COOL), ended)
    assert desired.reasons["mode"] == "waiting for the mode dwell before cool"
    assert holds(desired, "mode") == {HoldKind.MODE_DWELL: NOW + 500}


def test_windows_name_their_open_and_close_delays() -> None:
    plant = _plant(WINDOWED)
    calling = State(
        live=True, mode=Mode.HEAT, demands={"room": DemandState(Mode.HEAT, True, NOW - 3600)}
    )
    opened = windows(plant, 19.0, window=True, since=NOW - 30)
    state, desired, _ = run(plant, opened, calling)
    assert holds(desired, "room") == {HoldKind.WINDOW_OPEN_DELAY: NOW + 30}

    inhibited, _, _ = run(plant, opened, state, NOW + 30)
    closed = windows(plant, 19.0, since=NOW + 100)
    _, desired, _ = run(plant, closed, inhibited, NOW + 130)
    assert holds(desired, "room")[HoldKind.WINDOW_CLOSE_DELAY] == NOW + 160


def test_a_thermostat_names_the_end_of_its_minimum_on_time() -> None:
    plant = _plant(WINDOWED)
    calling = State(live=True, mode=Mode.HEAT, demands={"room": DemandState(Mode.HEAT, True, NOW)})
    _, desired, _ = run(plant, windows(plant, 21.5), calling, NOW + 100)
    assert desired.demands["room"].held_until == NOW + 600
    assert holds(desired, "room") == {HoldKind.DEMAND_MIN_ON: NOW + 600}


def test_an_exercise_names_the_end_of_its_run() -> None:
    plant = _plant(RADIATOR.replace("hydronicus: 2", "hydronicus: 2\nexercise: {run: 60}"))
    state = State(
        live=True,
        mode=Mode.HEAT,
        exercise=ExerciseState("pump", NOW - 30, started=NOW - 20),
    )
    _, desired, _ = run(plant, observe(plant, on=["switch.valve", "switch.pump"]), state)
    assert desired.exercise == "pump"
    assert holds(desired, "switch.pump") == {HoldKind.EXERCISE: NOW + 40}


def test_a_guard_hold_shows_only_while_cooling() -> None:
    plant = _plant(HEAT_PUMP)
    guards = {"a.ceiling": GuardState(True, NOW - 60)}
    cooling = State(live=True, mode=Mode.COOL, last_mode=Mode.COOL, guards=guards)
    observed = observe(plant, mode=Mode.COOL, option="Cool")
    _, desired, _ = run(plant, observed, cooling)
    assert holds(desired, "a.ceiling.guard") == {
        HoldKind.GUARD_MIN_BLOCKED: NOW - 60 + GUARD_MIN_BLOCKED
    }
    heating = State(live=True, mode=Mode.HEAT, last_mode=Mode.HEAT, guards=guards)
    _, desired, _ = run(plant, observe(plant), heating)
    assert not holds(desired, "a.ceiling.guard")
