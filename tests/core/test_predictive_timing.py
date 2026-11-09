"""Learned recovery begins at circulation; scheduling also budgets valve preparation."""

from dataclasses import replace
from math import inf

import pytest

from custom_components.hydronicus.core.comfort import ScheduleState
from custom_components.hydronicus.core.model import (
    DigitalThermostat,
    LearningMode,
    Loop,
    LoopRef,
    LoopRun,
    Mode,
    Plant,
    Preset,
    RunKind,
    SwitchTarget,
    Valve,
)
from custom_components.hydronicus.core.plant_file import read_plant_file
from custom_components.hydronicus.core.step import (
    TICK,
    DigitalThermostatState,
    Observations,
    Reading,
    Sent,
    State,
    SwitchState,
    step,
)
from custom_components.hydronicus.core.thermal import RecoveryEstimate

NOW = 1_800_000_000.0


def _plant() -> Plant:
    return replace(
        read_plant_file("""
hydronicus: 2
name: Circuit recovery
pumps:
  floor: {switch: switch.pump, overrun: 0}
zones:
  room:
    temperature: [sensor.room]
    thermostat:
      digital:
        learning: assist
        min_on: 0
        min_off: 0
        schedule:
          entity: schedule.room
          max_early_start: 3600
          heating_rate: 4
    loops:
      floor:
        pump: floor
        valves:
          - entity: switch.valve
            opening_time: 600
            readiness: binary_sensor.valve_ready
"""),
        exercise=None,
    )


def _observations(plant: Plant, event: float) -> Observations:
    return Observations(
        Mode.HEAT,
        True,
        frozenset(plant.outputs()),
        outputs={entity: SwitchState(False, NOW - 3600) for entity in plant.outputs()},
        sensors={"sensor.room": Reading(20, NOW)},
        thermostats={"room": DigitalThermostatState(Mode.HEAT, 21, Preset.SCHEDULE)},
        schedules={"schedule.room": ScheduleState(False, event)},
        recovery={
            "room": RecoveryEstimate(
                1800, True, "ready", "validated recovery", valid_until=NOW + 86400
            )
        },
    )


def test_closed_valve_starts_at_event_minus_recovery_minus_opening_time() -> None:
    plant = _plant()
    event = NOW + 2401
    observations = _observations(plant, event)
    state, desired, due = step(plant, observations, State(live=True, mode=Mode.HEAT), NOW)
    assert not desired.comfort["room"].early_start
    assert desired.comfort["room"].recovery_seconds == 2400
    assert due == pytest.approx(1 + TICK)
    state, desired, _ = step(plant, observations, state, NOW + 1)
    assert desired.comfort["room"].early_start
    assert desired.comfort["room"].early_start_event == event
    assert desired.demands["room"].on
    assert desired.outputs["switch.valve"] == SwitchTarget(True)
    assert desired.outputs["switch.pump"] == SwitchTarget(False)
    # The schedule budget never skips the actual hydraulic opening wait.
    opened = replace(
        observations,
        outputs={
            **observations.outputs,
            "switch.valve": SwitchState(True, NOW + 1),
        },
    )
    state, desired, _ = step(plant, opened, state, NOW + 600)
    assert desired.outputs["switch.pump"] == SwitchTarget(False)
    _, desired, _ = step(plant, opened, state, NOW + 601)
    assert desired.outputs["switch.pump"] == SwitchTarget(True)


@pytest.mark.parametrize(
    "observed,ready,remaining",
    [
        (SwitchState(False, NOW - 3600), None, 600),
        (SwitchState(True, NOW - 600), None, 0),
        (SwitchState(True, NOW - 200), None, 400),
        (SwitchState(True, NOW - 200, moving=True), None, 400),
        (SwitchState(True, NOW + 100), None, 700),
        (SwitchState(True, NOW), True, 0),
        (SwitchState(True, NOW - 200), False, 400),
        (SwitchState(None, NOW), None, 600),
        (None, None, 600),
    ],
    ids=[
        "closed",
        "already-settled",
        "partly-open",
        "reports-opening",
        "clock-moved-backward",
        "readiness-proved",
        "readiness-not-proved",
        "unavailable",
        "missing",
    ],
)
def test_only_remaining_known_valve_preparation_is_added(
    observed: SwitchState | None, ready: bool | None, remaining: float
) -> None:
    plant = _plant()
    observations = _observations(plant, NOW + 3000)
    outputs = {"switch.pump": observations.outputs["switch.pump"]}
    if observed is not None:
        outputs["switch.valve"] = observed
    observations = replace(
        observations,
        outputs=outputs,
        readiness={} if ready is None else {"binary_sensor.valve_ready": SwitchState(ready, NOW)},
    )
    _, desired, _ = step(plant, observations, State(live=True, mode=Mode.HEAT), NOW)
    proposal = desired.comfort["room"]
    assert proposal.recovery_seconds == 1800 + remaining
    assert proposal.recovery_method == "learned"
    assert not proposal.early_start
    assert observations.recovery["room"].seconds == 1800


def test_observed_readiness_survives_a_backward_clock_step_without_new_preparation() -> None:
    plant = _plant()
    observations = _observations(plant, NOW + 3000)
    observations = replace(
        observations,
        outputs={**observations.outputs, "switch.valve": SwitchState(True, NOW + 100)},
    )
    state = State(live=True, mode=Mode.HEAT, ready={"switch.valve": NOW + 100})
    _, desired, _ = step(plant, observations, state, NOW)
    assert desired.comfort["room"].recovery_seconds == 1800


def test_a_pending_close_does_not_count_as_an_already_prepared_valve() -> None:
    plant = _plant()
    observations = _observations(plant, NOW + 3000)
    observations = replace(
        observations,
        outputs={**observations.outputs, "switch.valve": SwitchState(True, NOW - 3600)},
        sent={"switch.valve": Sent(SwitchTarget(False), NOW)},
    )
    _, desired, _ = step(plant, observations, State(live=True, mode=Mode.HEAT), NOW)
    assert desired.comfort["room"].recovery_seconds == 2400


def test_parallel_owned_and_shared_valves_use_the_longest_wait_in_the_current_mode() -> None:
    plant = _plant()
    zone = plant.zone("room")
    owned = replace(
        zone.loops[0], valves=(*zone.loops[0].valves, Valve("switch.second", opening_time=900))
    )
    cooling = replace(
        zone.loops[0],
        ref=LoopRef("room", "cooling"),
        valves=(Valve("switch.cooling", opening_time=3600),),
        modes=frozenset((Mode.COOL,)),
    )
    shared = Loop(
        LoopRef(None, "shared"),
        (Valve("switch.shared", opening_time=1200),),
        "floor",
        frozenset((Mode.HEAT,)),
        LoopRun(RunKind.WITH_ZONES, ("room",)),
    )
    plant = replace(plant, zones=(replace(zone, loops=(owned, cooling)),), loops=(shared,))
    observations = _observations(plant, NOW + 3000)
    _, desired, _ = step(plant, observations, State(live=True, mode=Mode.HEAT), NOW)
    assert desired.comfort["room"].recovery_seconds == 3000
    assert desired.comfort["room"].early_start
    assert desired.outputs["switch.shared"] == SwitchTarget(True)
    assert desired.outputs["switch.second"] == SwitchTarget(True)
    assert desired.outputs["switch.cooling"] == SwitchTarget(False)


def test_a_valveless_loop_adds_no_preparation_budget() -> None:
    plant = _plant()
    zone = plant.zone("room")
    plant = replace(plant, zones=(replace(zone, loops=(replace(zone.loops[0], valves=()),)),))
    _, desired, _ = step(
        plant, _observations(plant, NOW + 3000), State(live=True, mode=Mode.HEAT), NOW
    )
    assert desired.comfort["room"].recovery_seconds == 1800


@pytest.mark.parametrize("learning", [LearningMode.OFF, LearningMode.OBSERVE])
def test_valve_budget_does_not_change_off_or_observe_mode(learning: LearningMode) -> None:
    plant = _plant()
    zone = plant.zone("room")
    assert isinstance(zone.thermostat, DigitalThermostat)
    plant = replace(
        plant, zones=(replace(zone, thermostat=replace(zone.thermostat, learning=learning)),)
    )
    _, desired, due = step(
        plant, _observations(plant, NOW + 1000), State(live=True, mode=Mode.HEAT), NOW
    )
    assert desired.comfort["room"].recovery_method == "configured"
    assert desired.comfort["room"].recovery_seconds == 900
    assert not desired.comfort["room"].early_start
    assert due == pytest.approx(100 + TICK)


@pytest.mark.parametrize(
    "problem", ["missing", "unconfident", "expired", "no-duration", "infinite"]
)
def test_unusable_learning_keeps_the_unchanged_configured_rate_fallback(problem: str) -> None:
    plant = _plant()
    observations = _observations(plant, NOW + 1000)
    candidate = observations.recovery["room"]
    match problem:
        case "missing":
            observations = replace(observations, recovery={})
        case "unconfident":
            observations = replace(
                observations, recovery={"room": replace(candidate, confidence=False)}
            )
        case "expired":
            observations = replace(
                observations, recovery={"room": replace(candidate, valid_until=NOW)}
            )
        case "no-duration":
            observations = replace(
                observations, recovery={"room": replace(candidate, seconds=None)}
            )
        case _:
            observations = replace(observations, recovery={"room": replace(candidate, seconds=inf)})
    _, desired, due = step(plant, observations, State(live=True, mode=Mode.HEAT), NOW)
    assert desired.comfort["room"].recovery_method == "configured"
    assert desired.comfort["room"].recovery_seconds == 900
    assert not desired.comfort["room"].early_start
    assert due == pytest.approx(100 + TICK)


def test_the_same_owner_cap_bounds_recovery_plus_valve_preparation() -> None:
    plant = _plant()
    zone = plant.zone("room")
    assert isinstance(zone.thermostat, DigitalThermostat)
    assert zone.thermostat.schedule is not None
    config = replace(
        zone.thermostat, schedule=replace(zone.thermostat.schedule, max_early_start=600)
    )
    plant = replace(plant, zones=(replace(zone, thermostat=config),))
    observations = _observations(plant, NOW + 601)
    state, desired, due = step(plant, observations, State(live=True, mode=Mode.HEAT), NOW)
    assert desired.comfort["room"].recovery_seconds == 2400
    assert not desired.comfort["room"].early_start
    assert due == pytest.approx(1 + TICK)
    _, desired, _ = step(plant, observations, state, NOW + 1)
    assert desired.comfort["room"].early_start
    assert desired.outputs["switch.valve"] == SwitchTarget(True)
    assert desired.outputs["switch.pump"] == SwitchTarget(False)


def test_an_accepted_event_is_not_cancelled_as_preparation_shrinks_or_learning_disappears() -> None:
    plant = _plant()
    observations = _observations(plant, NOW + 2300)
    state, desired, _ = step(plant, observations, State(live=True, mode=Mode.HEAT), NOW)
    event = desired.comfort["room"].early_start_event
    assert event == NOW + 2300
    observations = replace(
        observations,
        outputs={**observations.outputs, "switch.valve": SwitchState(True, NOW)},
    )
    state, desired, _ = step(plant, observations, state, NOW + 300)
    assert desired.comfort["room"].early_start_event == event
    assert desired.comfort["room"].recovery_method == "latched"
    observations = replace(observations, recovery={})
    _, desired, _ = step(plant, observations, state, NOW + 301)
    assert desired.comfort["room"].early_start_event == event
    assert desired.comfort["room"].target == 21
