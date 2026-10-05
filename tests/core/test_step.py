"""The step pipeline, stage by stage, on small Plants with hand-built observations."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import replace

import pytest

from custom_components.hydronicus.core.model import (
    DEFAULT_EXERCISE_INTERVAL,
    DEFAULT_MAX_AGE,
    Demand,
    Desired,
    Mode,
    OptionTarget,
    OutputRole,
    OutputTarget,
    Plant,
    SwitchTarget,
)
from custom_components.hydronicus.core.plant_file import read_plant_file
from custom_components.hydronicus.core.reconcile import TRAVEL_GRACE
from custom_components.hydronicus.core.step import (
    CALL_TIMEOUT,
    EXERCISE_GRACE,
    GUARD_MIN_BLOCKED,
    GUARD_REFERENCE_MAX_AGE,
    HUMIDITY_RELEASE,
    TICK,
    DemandState,
    DigitalThermostatState,
    ExerciseState,
    ExternalThermostatState,
    GuardState,
    Observations,
    OptionState,
    Reading,
    Sent,
    State,
    SwitchState,
    satisfies,
    step,
    value_of,
)

NOW = 1_800_000_000.0
LONG_AGO = NOW - 3600.0
ON = SwitchTarget(True)
OFF = SwitchTarget(False)

# A boiler, a circulator, and one radiator zone whose thermostat follows the
# temperature at once.
RADIATOR = """
hydronicus: 2
name: Flat
source: {request: switch.boiler, post_run: 60, min_on: 300, min_off: 300}
pumps:
  pump: {switch: switch.pump, overrun: 120}
zones:
  room:
    temperature: [sensor.room]
    humidity: [sensor.room_rh]
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      radiator: {valves: [switch.valve], pump: pump}
"""

# A heat pump driving ceiling loops, with a min-flow loop, and a switched floor pump.
HEAT_PUMP = """
hydronicus: 2
name: Home
mode_dwell: 600
source:
  request: switch.hp
  mode: {entity: select.hp, heat: Heat, cool: Cool}
  post_run: 120
  min_on: 0
  min_off: 0
pumps:
  hp: {driven_by: source, min_flow_loops: [a.ceiling], supply_temperature: sensor.supply}
  floor: {switch: switch.floor_pump, overrun: 60}
  towel: {switch: switch.towel, overrun: 0}
loops:
  towel: {pump: towel, runs: with_source}
zones:
  a:
    temperature: [sensor.a]
    humidity: [sensor.a_rh]
    loops:
      ceiling: {valves: [switch.a_ceiling], pump: hp, modes: [heat, cool]}
  b:
    temperature: [sensor.b]
    humidity: [sensor.b_rh]
    loops:
      ceiling: {valves: [switch.b_ceiling], pump: hp, modes: [heat, cool]}
  c:
    temperature: [sensor.c]
    humidity: [sensor.c_rh]
    loops:
      floor: {valves: [switch.c_floor], pump: floor}
"""


def _plant(text: str) -> Plant:
    return read_plant_file(text)


def observe(
    plant: Plant,
    *,
    mode: Mode = Mode.HEAT,
    control: bool = True,
    on: Iterable[str] = (),
    since: Mapping[str, float] | None = None,
    unavailable: Iterable[str] = (),
    armed: Iterable[str] | None = None,
    temperatures: Mapping[str, float] | None = None,
    sensors: Mapping[str, Reading] | None = None,
    sent: Mapping[str, Sent] | None = None,
    option: str | None = "Heat",
    readiness: Mapping[str, bool] | None = None,
) -> Observations:
    """Observations with every output off since long ago unless told otherwise."""
    on, unavailable, since = set(on), set(unavailable), since or {}
    outputs: dict[str, SwitchState | OptionState] = {}
    for entity, role in plant.outputs().items():
        stamp = since.get(entity, LONG_AGO)
        if role is OutputRole.SOURCE_MODE:
            outputs[entity] = OptionState(None if entity in unavailable else option, stamp)
        else:
            outputs[entity] = SwitchState(None if entity in unavailable else entity in on, stamp)
    readings = {f"sensor.{zone.slug}": Reading(21.0, NOW) for zone in plant.zones} | {
        f"sensor.{zone.slug}_rh": Reading(50.0, NOW) for zone in plant.zones
    }
    readings["sensor.supply"] = Reading(20.0, NOW)
    for zone, value in (temperatures or {}).items():
        readings[f"sensor.{zone}"] = Reading(value, NOW)
    readings.update(sensors or {})
    return Observations(
        mode=mode,
        control=control,
        armed=frozenset(plant.outputs() if armed is None else armed),
        outputs=outputs,
        readiness={key: SwitchState(value, NOW) for key, value in (readiness or {}).items()},
        sensors=readings,
        thermostats={zone.slug: DigitalThermostatState(mode, 21.0) for zone in plant.zones},
        sent=sent or {},
    )


def run(
    plant: Plant, observations: Observations, state: State | None = None, now: float = NOW
) -> tuple[State, Desired, float | None]:
    return step(plant, observations, state or State(live=True, mode=observations.mode), now)


def targets(desired: Desired, *entities: str) -> list[OutputTarget]:
    return [desired.outputs[entity] for entity in entities]


# Values


def test_observed_outputs_satisfy_their_targets() -> None:
    assert satisfies(SwitchState(True, NOW), ON)
    assert not satisfies(SwitchState(None, NOW), OFF)
    assert satisfies(OptionState("Heat", NOW), OptionTarget("Heat"))
    assert not satisfies(OptionState("Heat", NOW), ON)
    assert not satisfies(None, ON)
    assert [value_of(SwitchState(True, 0)), value_of(OptionState("x", 0))] == [True, "x"]
    assert value_of(SwitchState(None, 0)) is None


def test_state_round_trips_through_json_and_defaults_every_field() -> None:
    state = State(
        live=True,
        mode=Mode.HEAT,
        last_mode=Mode.HEAT,
        flowing=True,
        flow_ended=NOW,
        source_request=True,
        source_changed=NOW - 5,
        demands={
            "room": DemandState(Mode.HEAT, True, NOW),
            "hall": DemandState(Mode.OFF, False, None),
        },
        guards={"room.radiator": GuardState(True, NOW)},
        overruns={"pump": NOW},
        ready={"switch.valve": LONG_AGO},
        winding=frozenset({"switch.valve", "switch.boiler"}),
        windows_open=frozenset({"room"}),
        frost=frozenset({"room"}),
        idle_since={"switch.valve": LONG_AGO, "switch.pump": None},
        exercise=ExerciseState("pump", NOW - 200, NOW - 5, done=True),
        exercise_ended={"towel": NOW - 900},
    )
    assert State.from_dict(json.loads(json.dumps(state.to_dict()))) == state
    assert State.from_dict({}) == State()


# Stages 1 to 5: demand, wanted loops, and readiness


def test_nothing_runs_while_no_zone_calls_and_the_next_evaluation_is_when_a_reading_ages() -> None:
    plant = _plant(RADIATOR)
    state, desired, due = run(plant, observe(plant))
    assert all(target == OFF for target in desired.outputs.values())
    assert desired.mode is Mode.HEAT and not desired.source_request
    assert desired.reasons["room"].startswith("idle")
    assert due == pytest.approx(DEFAULT_MAX_AGE + TICK)
    assert state.live and state.mode is Mode.HEAT


def test_a_calling_zone_opens_its_valve_then_runs_its_pump_then_asks_the_source() -> None:
    plant = _plant(RADIATOR)
    cold = {"room": 19.0}
    _, desired, _ = run(plant, observe(plant, temperatures=cold))
    assert targets(desired, "switch.valve", "switch.pump", "switch.boiler") == [ON, OFF, OFF]

    opening = observe(
        plant, temperatures=cold, on=["switch.valve"], since={"switch.valve": NOW - 60}
    )
    _, desired, due = run(plant, opening)
    assert targets(desired, "switch.valve", "switch.pump") == [ON, OFF]
    assert due == pytest.approx(120.0 + TICK), "due when the valve has had its opening time"

    ready = observe(plant, temperatures=cold, on=["switch.valve"])
    state, desired, _ = run(plant, ready)
    assert targets(desired, "switch.pump", "switch.boiler") == [ON, OFF]
    assert state.ready == {"switch.valve": LONG_AGO}

    running = observe(plant, temperatures=cold, on=["switch.valve", "switch.pump"])
    state, desired, _ = run(plant, running)
    assert desired.outputs["switch.boiler"] == ON and state.source_changed == NOW


def test_the_desired_state_reports_each_zone_demand() -> None:
    plant = _plant(RADIATOR)
    _, desired, _ = run(plant, observe(plant, temperatures={"room": 20.5}))
    demand = desired.demands["room"]
    assert demand.on and demand.mode is Mode.HEAT
    _, desired, _ = run(plant, observe(plant))
    assert not desired.demands["room"].on


def test_a_valve_that_shows_opening_is_not_ready_and_one_closing_may_pass_flow() -> None:
    plant = _plant(RADIATOR)
    cold = observe(plant, temperatures={"room": 19.0}, on=["switch.valve"])
    opening = replace(
        cold, outputs={**cold.outputs, "switch.valve": SwitchState(True, LONG_AGO, moving=True)}
    )
    state, desired, _ = run(plant, opening)
    assert targets(desired, "switch.valve", "switch.pump") == [ON, OFF], "opening is not ready"
    assert "switch.valve" not in state.ready
    arrived = replace(cold, outputs={**cold.outputs, "switch.valve": SwitchState(True, NOW)})
    state, desired, due = run(plant, arrived, state)
    assert targets(desired, "switch.pump") == [OFF]
    assert due == pytest.approx(180.0 + TICK), "the opening time counts from open"

    warm = observe(plant, on=["switch.pump"])
    closing = replace(
        warm, outputs={**warm.outputs, "switch.valve": SwitchState(False, NOW, moving=True)}
    )
    state, desired, _ = run(plant, closing)
    assert targets(desired, "switch.valve", "switch.pump") == [ON, OFF], (
        "a closing valve is held open as the path of a pump that runs"
    )
    assert "switch.valve" in state.winding
    assert not satisfies(SwitchState(True, NOW, moving=True), ON)


def test_the_desired_state_names_the_required_sensors_that_block_each_zone() -> None:
    plant = _plant(HEAT_PUMP)
    unusable = {entity: Reading(None, NOW) for entity in ("sensor.a_rh", "sensor.c", "sensor.c_rh")}
    _, desired, _ = run(plant, observe(plant, sensors=unusable))
    assert desired.blocking_sensors == {"a": ("sensor.a_rh",), "c": ("sensor.c",)}, (
        "a humidity sensor blocks only a zone whose dew point guards a loop that cools"
    )
    external = read_plant_file(
        RADIATOR.replace("{digital: {min_on: 0, min_off: 0}}", "{external: climate.room}")
    )
    _, desired, _ = run(external, observe(external, sensors={"sensor.room": Reading(None, NOW)}))
    assert desired.blocking_sensors == {}, "an external thermostat needs no temperature to heat"


def test_readiness_is_confirmed_by_a_sensor_and_kept_across_a_backward_clock_step() -> None:
    plant = read_plant_file(
        RADIATOR.replace(
            "valves: [switch.valve]",
            "valves: [{entity: switch.valve, readiness: binary_sensor.valve_open}]",
        )
    )
    cold = {"room": 19.0}
    just_on = {"switch.valve": NOW - 5}
    confirmed = observe(
        plant,
        temperatures=cold,
        on=["switch.valve"],
        since=just_on,
        readiness={"binary_sensor.valve_open": True},
    )
    state, desired, _ = run(plant, confirmed)
    assert desired.outputs["switch.pump"] == ON
    # The clock steps back 300 s: the valve is still the one observed ready.
    stepped = observe(plant, temperatures=cold, on=["switch.valve"], since=just_on)
    _, desired, _ = run(plant, stepped, state, NOW - 300)
    assert desired.outputs["switch.pump"] == ON
    # A new change of the valve is not ready until its opening time.
    changed = observe(plant, temperatures=cold, on=["switch.valve"], since={"switch.valve": NOW})
    assert run(plant, changed, state)[1].outputs["switch.pump"] == OFF


def test_a_loop_is_dropped_when_an_output_it_needs_is_unarmed_or_unavailable() -> None:
    plant = _plant(RADIATOR)
    cold = {"room": 19.0}
    _, desired, _ = run(plant, observe(plant, temperatures=cold, armed=["switch.valve"]))
    assert desired.outputs["switch.valve"] == OFF
    assert desired.reasons["room.radiator"] == "dropped: switch.pump unarmed or unavailable"
    _, desired, _ = run(plant, observe(plant, temperatures=cold, unavailable=["switch.valve"]))
    assert desired.outputs["switch.valve"] == OFF
    assert "switch.valve" in desired.reasons["room.radiator"]


# Stages 6 to 8: min flow, valves, and pumps


def test_a_pump_overruns_in_heating_with_its_last_path_held_open() -> None:
    plant = _plant(RADIATOR)
    running = observe(plant, on=["switch.valve", "switch.pump"])
    state, desired, due = run(plant, running)
    assert targets(desired, "switch.pump", "switch.valve") == [ON, ON]
    assert state.overruns == {"pump": NOW}
    assert due == pytest.approx(120.0 + TICK)
    later = NOW + 120
    state, desired, _ = run(plant, running, state, later)
    assert targets(desired, "switch.pump", "switch.valve") == [OFF, ON], "the valve waits"
    stopped = observe(plant, on=["switch.valve"], since={"switch.pump": later})
    state, desired, _ = run(plant, stopped, state, later + 1)
    assert targets(desired, "switch.pump", "switch.valve") == [OFF, OFF]
    assert state.overruns == {}


def test_an_overrun_never_starts_a_pump_and_a_path_pump_needs_a_ready_loop() -> None:
    plant = _plant(RADIATOR)
    state = State(live=True, mode=Mode.HEAT, last_mode=Mode.HEAT, overruns={"pump": NOW - 10})
    _, desired, _ = run(plant, observe(plant, on=["switch.valve"]), state)
    assert desired.outputs["switch.pump"] == OFF
    # A pump found running with its valve still closing stops: it has no ready loop.
    closing = observe(plant, on=["switch.pump"], since={"switch.valve": NOW - 5})
    winding = replace(state, overruns={}, winding=frozenset({"switch.valve"}))
    _, desired, _ = run(plant, closing, winding)
    assert targets(desired, "switch.pump", "switch.valve") == [OFF, ON], (
        "the closing valve reopens while the pump may still run"
    )


def test_a_pump_that_may_start_counts_as_running_and_one_that_may_stop_does_not() -> None:
    plant = _plant(RADIATOR)
    starting = observe(plant, sent={"switch.pump": Sent(ON, NOW - 2)})
    _, desired, due = run(plant, starting)
    assert desired.outputs["switch.pump"] == OFF
    assert due == pytest.approx(8.0 + TICK), "due when the call can no longer act"
    # The pump may start, so its valve that is still closing stays open.
    winding = State(
        live=True, mode=Mode.HEAT, last_mode=Mode.HEAT, winding=frozenset({"switch.valve"})
    )
    closing = replace(
        starting, outputs={**starting.outputs, "switch.valve": SwitchState(False, NOW - 5)}
    )
    assert run(plant, closing, winding)[1].outputs["switch.valve"] == ON
    # A call that timed out no longer counts.
    expired = observe(plant, sent={"switch.pump": Sent(ON, NOW - CALL_TIMEOUT)})
    assert (
        run(plant, replace(expired, outputs=closing.outputs), winding)[1].outputs["switch.valve"]
        == OFF
    )
    # A stop in flight makes a running pump unfit to carry the source.
    cold = {"room": 19.0}
    stopping = observe(
        plant,
        temperatures=cold,
        on=["switch.valve", "switch.pump"],
        sent={"switch.pump": Sent(OFF, NOW - 1)},
    )
    assert run(plant, stopping)[1].outputs["switch.boiler"] == OFF


def test_a_pump_is_blocked_by_a_loop_that_would_flow_in_the_wrong_mode() -> None:
    plant = read_plant_file(
        """
hydronicus: 2
name: Mixed
pumps:
  pump: {switch: switch.pump, overrun: 0, supply_temperature: sensor.supply}
zones:
  room:
    temperature: [sensor.room]
    humidity: [sensor.room_rh]
    loops:
      floor: {valves: [switch.floor], pump: pump}
      ceiling: {valves: [switch.ceiling], pump: pump, modes: [cool]}
      towel: {pump: pump, modes: [heat]}
"""
    )
    cold = {"room": 19.0}
    ready = observe(plant, temperatures=cold, on=["switch.floor"])
    assert run(plant, ready)[1].outputs["switch.pump"] == ON
    ceiling_open = observe(plant, temperatures=cold, on=["switch.floor", "switch.ceiling"])
    _, desired, _ = run(plant, ceiling_open)
    assert targets(desired, "switch.pump", "switch.ceiling") == [OFF, OFF]
    # In cooling the valveless heating loop would carry chilled water.
    warm = observe(plant, mode=Mode.COOL, temperatures={"room": 26.0}, on=["switch.ceiling"])
    assert run(plant, warm)[1].outputs["switch.pump"] == OFF


def test_the_min_flow_path_opens_when_the_source_is_wanted_without_a_loop_of_its_pump() -> None:
    plant = _plant(HEAT_PUMP)
    cold = {"c": 19.0}
    _, desired, _ = run(plant, observe(plant, temperatures=cold))
    assert targets(desired, "switch.c_floor", "switch.a_ceiling", "switch.b_ceiling") == [
        ON,
        ON,
        OFF,
    ]
    assert desired.reasons["a.ceiling"] == "min-flow path"
    both_ready = observe(plant, temperatures=cold, on=["switch.c_floor", "switch.a_ceiling"])
    _, desired, _ = run(plant, both_ready)
    assert targets(desired, "switch.floor_pump", "switch.hp") == [ON, OFF]
    running = observe(
        plant, temperatures=cold, on=["switch.c_floor", "switch.a_ceiling", "switch.floor_pump"]
    )
    _, desired, _ = run(plant, running)
    assert desired.outputs["switch.hp"] == ON
    assert desired.outputs["select.hp"] == OptionTarget("Heat")


def test_a_ready_loop_is_held_as_the_last_path_while_the_source_may_run() -> None:
    plant = _plant(HEAT_PUMP)
    post_run = observe(plant, on=["switch.b_ceiling"], since={"switch.hp": NOW - 30})
    winding = State(
        live=True, mode=Mode.HEAT, last_mode=Mode.HEAT, winding=frozenset({"switch.hp"})
    )
    _, desired, due = run(plant, post_run, winding)
    assert targets(desired, "switch.b_ceiling", "switch.a_ceiling") == [ON, OFF]
    assert due == pytest.approx(90.0 + TICK), "due when the post-run ends"
    _, desired, _ = run(plant, post_run, winding, NOW + 90)
    assert desired.outputs["switch.b_ceiling"] == OFF


def test_a_plant_loop_with_the_source_follows_the_observed_request() -> None:
    plant = _plant(HEAT_PUMP)
    requested = observe(plant, on=["switch.hp", "switch.a_ceiling"])
    assert run(plant, requested)[1].outputs["switch.towel"] == ON
    releasing = replace(requested, sent={"switch.hp": Sent(OFF, NOW)})
    assert run(plant, releasing)[1].outputs["switch.towel"] == OFF
    assert run(plant, observe(plant))[1].outputs["switch.towel"] == OFF


# Stage 9: the source


def test_the_source_waits_for_its_mode_select_and_keeps_min_on_and_min_off() -> None:
    plant = _plant(RADIATOR)
    cold = {"room": 19.0}
    running = observe(plant, temperatures=cold, on=["switch.valve", "switch.pump"])
    state, desired, _ = run(plant, running)
    assert desired.source_request
    warm = observe(
        plant,
        temperatures={"room": 22.0},
        on=["switch.valve", "switch.pump", "switch.boiler"],
        since={"switch.boiler": NOW},
    )
    held_state, desired, due = run(plant, warm, state, NOW + 100)
    assert desired.source_request and desired.reasons["source"] == "held for its minimum on time"
    assert due == pytest.approx(200.0 + TICK), "the source minimum on time keeps its pump running"
    released, desired, _ = run(plant, warm, held_state, NOW + 300)
    assert not desired.source_request and released.source_changed == NOW + 300
    stopped = replace(
        running, outputs={**running.outputs, "switch.boiler": SwitchState(False, NOW + 300)}
    )
    _, desired, _ = run(plant, stopped, released, NOW + 400)
    assert (
        not desired.source_request
        and desired.reasons["source"] == "held off for its minimum off time"
    )
    assert run(plant, stopped, released, NOW + 600)[1].source_request

    heat_pump = _plant(HEAT_PUMP)
    ready = observe(heat_pump, temperatures={"a": 19.0}, on=["switch.a_ceiling"], option="Cool")
    _, desired, _ = run(heat_pump, ready)
    assert not desired.source_request and desired.reasons["source"] == "waiting for the source mode"
    pending = replace(
        ready,
        outputs={**ready.outputs, "select.hp": OptionState("Heat", LONG_AGO)},
        sent={"select.hp": Sent(OptionTarget("Cool"), NOW - 1)},
    )
    assert not run(heat_pump, pending)[1].source_request


def test_a_released_request_keeps_its_running_pump_until_it_is_observed_off() -> None:
    plant = _plant(RADIATOR)
    state = State(
        live=True,
        mode=Mode.HEAT,
        last_mode=Mode.HEAT,
        source_request=True,
        source_changed=NOW - 1000,
        overruns={"pump": NOW - 1000},
    )
    on = ["switch.valve", "switch.pump", "switch.boiler"]
    _, desired, _ = run(plant, observe(plant, on=on), state)
    assert not desired.source_request
    assert targets(desired, "switch.pump", "switch.valve") == [ON, ON]
    assert desired.reasons["switch.pump"] == "held until the source request is off"
    off = observe(plant, on=on[:2], since={"switch.boiler": NOW})
    assert run(plant, off, state)[1].outputs["switch.pump"] == OFF


def test_a_condensation_guard_neither_blocks_nor_reports_while_heating() -> None:
    plant = _plant(HEAT_PUMP)
    # 18 °C at 50 % has a dew point of 7.4 °C: 8 °C is inside the 2 K margin.
    cold_supply = {"sensor.supply": Reading(8.0, NOW)}
    heating = observe(plant, temperatures={"a": 18.0}, on=["switch.a_ceiling"], sensors=cold_supply)
    state, desired, _ = run(plant, heating)
    assert state.guards["a.ceiling"].blocked, "the guard is ready for a change to cooling"
    assert desired.source_request
    assert not [key for key in desired.reasons if key.endswith(".guard")]


def test_the_condensation_guard_blocks_a_cooling_loop_and_releases_with_hysteresis() -> None:
    plant = _plant(HEAT_PUMP)
    warm = {"a": 26.0}
    ready = observe(
        plant, mode=Mode.COOL, temperatures=warm, on=["switch.a_ceiling"], option="Cool"
    )
    state, desired, _ = run(plant, ready)
    assert desired.source_request and desired.outputs["select.hp"] == OptionTarget("Cool")
    assert state.guards["a.ceiling"] == GuardState(False, NOW)

    # 26 °C at 50 % has a dew point of 14.8 °C: 16 °C is inside the 2 K margin.
    cold_supply = {"sensor.supply": Reading(16.0, NOW)}
    running = replace(
        observe(
            plant,
            mode=Mode.COOL,
            temperatures=warm,
            on=["switch.a_ceiling", "switch.hp"],
            option="Cool",
            sensors=cold_supply,
        ),
    )
    blocked, desired, _ = run(plant, running, replace(state, source_request=True))
    assert blocked.guards["a.ceiling"] == GuardState(True, NOW)
    assert not desired.source_request, "the guard overrides the minimum on time"
    assert desired.reasons["a.ceiling.guard"] == (
        "condensation guard blocks: reference 16.0 °C below 16.8 °C"
    )
    assert desired.reasons["source"] == "a condensation guard blocks a loop the source drives"
    assert desired.outputs["switch.a_ceiling"] == ON, "held for the post-run"

    # 17.5 °C is above the threshold but not 1 K above it: still blocked.
    above = {"sensor.supply": Reading(17.5, NOW)}
    later = NOW + GUARD_MIN_BLOCKED
    ready_above = replace(ready, sensors={**ready.sensors, **above})
    held, desired, _ = run(plant, ready_above, blocked, later)
    assert held.guards["a.ceiling"].blocked
    assert desired.reasons["a.ceiling.guard"] == (
        "condensation guard blocks: reference 17.5 °C, releases at 17.8 °C"
    )
    clear = {"sensor.supply": Reading(18.0, NOW)}
    ready_clear = replace(ready, sensors={**ready.sensors, **clear})
    early, desired, due = run(plant, ready_clear, blocked, NOW + 10)
    assert early.guards["a.ceiling"].blocked and due == pytest.approx(GUARD_MIN_BLOCKED - 10 + TICK)
    assert desired.reasons["a.ceiling.guard"] == (
        "condensation guard blocks: reference 18.0 °C; humidity 50.0 % in zone a, "
        "held for its minimum blocked time"
    )
    assert not run(plant, ready_clear, blocked, later)[0].guards["a.ceiling"].blocked

    stale = {"sensor.supply": Reading(20.0, NOW - GUARD_REFERENCE_MAX_AGE - 1)}
    assert (
        run(plant, replace(ready, sensors={**ready.sensors, **stale}))[0]
        .guards["a.ceiling"]
        .blocked
    )


# A heat pump cooling a hall loop with the zones it runs with; zone b has no humidity sensor.
HALL = """
hydronicus: 2
name: Hall
source: {request: switch.hp, min_on: 0, min_off: 0}
pumps:
  hp: {driven_by: source, min_flow: guaranteed, supply_temperature: sensor.supply}
loops:
  hall: {valves: [switch.hall], pump: hp, runs: {with_zones: [a]}, modes: [heat, cool]}
zones:
  a: {temperature: [sensor.a], humidity: [sensor.a_rh]}
  b: {temperature: [sensor.b]}
"""


def test_a_plant_loop_is_guarded_by_the_dew_points_of_the_zones_it_runs_with() -> None:
    plant = _plant(HALL)
    warm = observe(plant, mode=Mode.COOL, temperatures={"a": 26.0, "b": 26.0})
    state, _, _ = run(plant, warm)
    assert not state.guards["hall"].blocked, "zone b has no dew point but the hall ignores it"

    with_source = _plant(
        HALL.replace("runs: {with_zones: [a]}", "runs: with_source").replace(
            "b: {temperature: [sensor.b]}", "b: {temperature: [sensor.b], humidity: [sensor.b_rh]}"
        )
    )
    # 26 °C at 95 % has a dew point of 25.1 °C, above the 20 °C supply.
    humid = replace(warm, sensors={**warm.sensors, "sensor.b_rh": Reading(95.0, NOW)})
    state, desired, _ = run(with_source, humid)
    assert state.guards["hall"].blocked, "a loop that runs with the source guards every zone"
    assert desired.reasons["hall.guard"].startswith("condensation guard blocks: reference 20.0")
    assert not run(plant, humid)[0].guards["hall"].blocked


def test_cooling_pumps_have_no_overrun() -> None:
    plant = read_plant_file(
        RADIATOR.replace("pump: pump}", "pump: pump, modes: [heat, cool]}").replace(
            "overrun: 120}", "overrun: 120, supply_temperature: sensor.supply}"
        )
    )
    running = observe(plant, mode=Mode.COOL, on=["switch.valve", "switch.pump"])
    state, desired, _ = run(plant, running)
    assert targets(desired, "switch.pump", "switch.valve") == [OFF, ON]
    assert state.overruns == {}


# A switched circulator cooling a ceiling with a surface sensor, and a condensation
# switch on the pump's supply pipe and another on the ceiling.
COOLED_CEILING = """
hydronicus: 2
name: Office
pumps:
  pump:
    switch: switch.pump
    overrun: 0
    supply_temperature: sensor.supply
    condensation_switch: binary_sensor.supply_dew
zones:
  room:
    temperature: [sensor.room]
    humidity: [sensor.room_rh]
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      ceiling:
        valves: [switch.ceiling]
        pump: pump
        modes: [heat, cool]
        surface_temperature: sensor.surface
        condensation_switch: binary_sensor.ceiling_dew
"""
DRY = {"binary_sensor.supply_dew": False, "binary_sensor.ceiling_dew": False}


def cooling(
    plant: Plant,
    *,
    switches: Mapping[str, bool | None] = DRY,
    switched: float = LONG_AGO,
    sensors: Mapping[str, float] | None = None,
    mode: Mode = Mode.COOL,
) -> Observations:
    """A room at 26 °C calling for cooling, with its switches as given since ``switched``."""
    readings = {"sensor.surface": 24.0, "sensor.supply": 24.0, "sensor.room_rh": 50.0}
    base = observe(plant, mode=mode, temperatures={"room": 26.0 if mode is Mode.COOL else 19.0})
    return replace(
        base,
        readiness={entity: SwitchState(on, switched) for entity, on in switches.items()},
        sensors={
            **base.sensors,
            **{entity: Reading(value, NOW) for entity, value in (sensors or readings).items()},
        },
    )


def test_a_condensation_switch_blocks_cooling_at_once_and_releases_once_off_long_enough() -> None:
    plant = _plant(COOLED_CEILING)
    state, desired, _ = run(plant, cooling(plant))
    assert not state.guards["room.ceiling"].blocked
    assert desired.outputs["switch.ceiling"] == ON

    wet = cooling(plant, switches={**DRY, "binary_sensor.ceiling_dew": True}, switched=NOW)
    blocked, desired, _ = run(plant, wet, state)
    assert blocked.guards["room.ceiling"] == GuardState(True, NOW)
    assert desired.reasons["room.ceiling.guard"] == (
        "condensation guard blocks: condensation switch binary_sensor.ceiling_dew on"
    )
    assert desired.reasons["room.ceiling"] == "dropped: condensation guard blocks"
    assert desired.outputs["switch.ceiling"] == OFF

    # Off again, the switch holds the guard for the minimum blocked time from when it
    # turned off, even when the guard itself has blocked longer.
    dried = cooling(plant)
    dried = replace(
        dried,
        readiness={**dried.readiness, "binary_sensor.ceiling_dew": SwitchState(False, NOW + 100)},
    )
    later = NOW + GUARD_MIN_BLOCKED + 50
    held, desired, due = run(plant, dried, blocked, later)
    assert held.guards["room.ceiling"].blocked
    assert desired.reasons["room.ceiling.guard"] == (
        "condensation guard blocks: condensation switch binary_sensor.ceiling_dew off for "
        "less than 300 s"
    )
    assert due == pytest.approx(NOW + 100 + GUARD_MIN_BLOCKED - later + TICK)
    released, desired, _ = run(plant, dried, held, NOW + 100 + GUARD_MIN_BLOCKED)
    assert not released.guards["room.ceiling"].blocked
    assert desired.outputs["switch.ceiling"] == ON


def test_a_pump_condensation_switch_that_is_unavailable_blocks_every_loop_of_the_pump() -> None:
    plant = _plant(COOLED_CEILING)
    for switches in (
        {"binary_sensor.ceiling_dew": False},
        {**DRY, "binary_sensor.supply_dew": None},
    ):
        state, desired, _ = run(plant, cooling(plant, switches=switches))
        assert state.guards["room.ceiling"].blocked
        assert desired.reasons["room.ceiling.guard"] == (
            "condensation guard blocks: condensation switch binary_sensor.supply_dew unavailable"
        )


def test_a_condensation_switch_does_not_stop_heating() -> None:
    plant = _plant(COOLED_CEILING)
    wet = cooling(plant, switches={**DRY, "binary_sensor.supply_dew": True}, mode=Mode.HEAT)
    state, desired, _ = run(plant, wet)
    assert state.guards["room.ceiling"].blocked, "ready for a change to cooling"
    assert desired.outputs["switch.ceiling"] == ON
    assert "room.ceiling.guard" not in desired.reasons


def test_a_cooled_surface_stays_above_its_minimum() -> None:
    plant = _plant(COOLED_CEILING)
    # 26 °C at 30 % has a dew point of 7.0 °C, so only the surface minimum blocks.
    dry_air = {"sensor.supply": 24.0, "sensor.room_rh": 30.0}
    cold = cooling(plant, sensors={**dry_air, "sensor.surface": 19.5})
    blocked, desired, _ = run(plant, cold)
    assert blocked.guards["room.ceiling"] == GuardState(True, NOW)
    assert desired.reasons["room.ceiling.guard"] == (
        "condensation guard blocks: surface 19.5 °C below its minimum 20 °C"
    )

    later = NOW + GUARD_MIN_BLOCKED
    near = cooling(plant, sensors={**dry_air, "sensor.surface": 20.5})
    held, desired, _ = run(plant, near, blocked, later)
    assert held.guards["room.ceiling"].blocked
    assert desired.reasons["room.ceiling.guard"] == (
        "condensation guard blocks: surface 20.5 °C, releases at 21 °C"
    )
    clear = cooling(plant, sensors={**dry_air, "sensor.surface": 21.0})
    assert not run(plant, clear, held, later)[0].guards["room.ceiling"].blocked

    lower = _plant(
        COOLED_CEILING.replace(
            "surface_temperature: sensor.surface",
            "surface_temperature: sensor.surface\n        surface_minimum: 17",
        )
    )
    assert not run(lower, cold)[0].guards["room.ceiling"].blocked
    off = _plant(
        COOLED_CEILING.replace(
            "surface_temperature: sensor.surface",
            "surface_temperature: sensor.surface\n        surface_minimum: null",
        )
    )
    very_cold = cooling(off, sensors={**dry_air, "sensor.surface": 12.0})
    assert not run(off, very_cold)[0].guards["room.ceiling"].blocked


def test_a_humid_zone_blocks_cooling_even_above_its_dew_point() -> None:
    plant = _plant(COOLED_CEILING)
    # 26 °C at 72 % has a dew point of 20.6 °C, which 25 °C references clear with the margin.
    warm = {"sensor.supply": 25.0, "sensor.surface": 25.0}
    humid = cooling(plant, sensors={**warm, "sensor.room_rh": 72.0})
    blocked, desired, _ = run(plant, humid)
    assert blocked.guards["room.ceiling"].blocked
    assert desired.reasons["room.ceiling.guard"] == (
        "condensation guard blocks: humidity 72.0 % in zone room above 70 %"
    )

    later = NOW + GUARD_MIN_BLOCKED
    drier = cooling(plant, sensors={**warm, "sensor.room_rh": 68.0})
    held, desired, _ = run(plant, drier, blocked, later)
    assert held.guards["room.ceiling"].blocked
    assert desired.reasons["room.ceiling.guard"] == (
        "condensation guard blocks: humidity 68.0 % in zone room, releases at 65 %"
    )
    dry = cooling(plant, sensors={**warm, "sensor.room_rh": 70.0 - HUMIDITY_RELEASE})
    assert not run(plant, dry, held, later)[0].guards["room.ceiling"].blocked

    off = _plant(
        COOLED_CEILING.replace(
            "thermostat: {digital", "max_humidity: null\n    thermostat: {digital"
        )
    )
    assert not run(off, humid)[0].guards["room.ceiling"].blocked
    # Several checks that block are all named.
    both = cooling(plant, sensors={**warm, "sensor.room_rh": 72.0, "sensor.surface": 19.0})
    assert run(plant, both)[1].reasons["room.ceiling.guard"] == (
        "condensation guard blocks: reference 19.0 °C below 22.6 °C; surface 19.0 °C below its "
        "minimum 20 °C; humidity 72.0 % in zone room above 70 %"
    )


def test_a_plant_loop_reads_the_humidity_of_the_zones_it_runs_with() -> None:
    plant = _plant(HALL)
    humid = observe(plant, mode=Mode.COOL, temperatures={"a": 20.0, "b": 20.0})
    # 20 °C at 75 % has a dew point of 15.4 °C, which the 20 °C supply clears, but 75 % is humid.
    humid = replace(humid, sensors={**humid.sensors, "sensor.a_rh": Reading(75.0, NOW)})
    state, desired, _ = run(plant, humid)
    assert state.guards["hall"].blocked
    assert desired.reasons["hall.guard"] == (
        "condensation guard blocks: humidity 75.0 % in zone a above 70 %"
    )


# Stage 3: the mode and its changeover


def test_a_mode_change_stops_the_old_mode_waits_for_the_dwell_and_starts_the_new_one() -> None:
    plant = _plant(HEAT_PUMP)
    heating = State(live=True, mode=Mode.HEAT, last_mode=Mode.HEAT, flowing=True)
    flowing = observe(plant, mode=Mode.COOL, on=["switch.c_floor", "switch.floor_pump"])
    state, desired, _ = run(plant, flowing, heating)
    assert desired.mode is Mode.HEAT and desired.reasons["mode"] == "stopping heat before cool"
    assert desired.outputs["switch.floor_pump"] == ON, "the heating overrun still runs"

    stopped = observe(plant, mode=Mode.COOL, since={"switch.floor_pump": NOW})
    state, desired, due = run(plant, stopped, state, NOW + 60)
    assert desired.mode is Mode.OFF and state.flow_ended == NOW + 60
    assert "select.hp" not in desired.outputs
    assert due == pytest.approx(600.0 + TICK)
    state, desired, _ = run(plant, stopped, state, NOW + 660)
    assert desired.mode is Mode.COOL and desired.outputs["select.hp"] == OptionTarget("Cool")

    # Back to the same mode needs no dwell.
    off = State(live=True, mode=Mode.OFF, last_mode=Mode.HEAT, flow_ended=NOW)
    assert run(plant, observe(plant), off)[1].mode is Mode.HEAT


def test_a_mode_change_keeps_the_source_for_its_minimum_on_time_and_control_off_does_not() -> None:
    plant = _plant(RADIATOR)
    heating = State(
        live=True,
        mode=Mode.HEAT,
        last_mode=Mode.HEAT,
        flowing=True,
        source_request=True,
        source_changed=NOW - 250,
    )
    on = ["switch.valve", "switch.pump", "switch.boiler"]
    for mode in (Mode.OFF, Mode.COOL):
        changed = observe(
            plant, mode=mode, temperatures={"room": 19.0}, on=on, since={"switch.boiler": NOW - 250}
        )
        state, desired, due = run(plant, changed, heating)
        assert desired.mode is Mode.HEAT
        assert desired.reasons["mode"] == f"stopping heat before {mode.value}"
        assert desired.source_request, f"a change to {mode.value} keeps the minimum on time"
        assert desired.reasons["source"] == "held for its minimum on time"
        assert targets(desired, "switch.pump", "switch.valve") == [ON, ON]
        assert due == pytest.approx(50.0 + TICK), "due when the minimum on time ends"
        _, desired, _ = run(plant, changed, state, NOW + 50)
        assert not desired.source_request and desired.reasons["source"] == "released"
        assert desired.outputs["switch.pump"] == ON, "the pump overruns after the release"

    # Control equipment off stops at once.
    stopping = observe(plant, control=False, temperatures={"room": 19.0}, on=on)
    _, desired, _ = run(plant, stopping, heating)
    assert not desired.source_request and desired.reasons["source"] == "off"
    # A lost path overrides the minimum on time too.
    no_pump = observe(plant, mode=Mode.OFF, on=["switch.valve", "switch.boiler"])
    assert not run(plant, no_pump, heating)[1].source_request


def test_a_first_evaluation_adopts_the_requested_mode_for_loops_found_running() -> None:
    plant = _plant(RADIATOR)
    running = observe(plant, temperatures={"room": 19.0}, on=["switch.valve", "switch.pump"])
    state, desired, _ = step(plant, running, State(), NOW)
    assert desired.mode is Mode.HEAT and desired.outputs["switch.pump"] == ON
    assert state.flowing and state.last_mode is Mode.HEAT
    # Found running while the Plant is off, their mode is unknown: the dwell applies.
    idle = observe(plant, mode=Mode.OFF, on=["switch.valve", "switch.pump"])
    state, desired, _ = step(plant, idle, State(), NOW)
    assert desired.mode is Mode.OFF and state.flowing
    stopped = observe(plant, mode=Mode.HEAT, since={"switch.pump": NOW + 1})
    state, desired, _ = step(plant, stopped, state, NOW + 1)
    assert desired.mode is Mode.OFF and desired.reasons["mode"].startswith("waiting")


def test_an_external_thermostat_demands_only_in_the_plant_mode() -> None:
    plant = read_plant_file(
        RADIATOR.replace("{digital: {min_on: 0, min_off: 0}}", "{external: climate.room}")
    )
    base = observe(plant)
    heat = replace(base, thermostats={"room": ExternalThermostatState(Mode.HEAT)})
    assert run(plant, heat)[1].outputs["switch.valve"] == ON
    cool = replace(base, thermostats={"room": ExternalThermostatState(Mode.COOL)})
    assert run(plant, cool)[1].outputs["switch.valve"] == OFF


# Control equipment and Dry run


def test_control_off_runs_the_off_sequence_then_dry_runs_the_requested_mode() -> None:
    plant = _plant(RADIATOR)
    cold = {"room": 19.0}
    live = State(live=True, mode=Mode.HEAT, last_mode=Mode.HEAT, flowing=True)
    stopping = observe(plant, control=False, temperatures=cold, on=["switch.valve", "switch.pump"])
    state, desired, _ = run(plant, stopping, live)
    assert (
        state.live and desired.mode is Mode.HEAT and desired.reasons["mode"].startswith("stopping")
    )
    assert desired.outputs["switch.pump"] == ON, "the overrun runs in the off sequence"

    stopped = observe(plant, control=False, temperatures=cold)
    state, desired, _ = run(plant, stopped, state, NOW + 200)
    assert not state.live
    state, desired, _ = run(plant, stopped, state, NOW + 201)
    assert not state.live and desired.outputs["switch.valve"] == ON, "Dry run evaluates heating"
    # A pending call keeps the off sequence live.
    pending = replace(stopped, sent={"switch.pump": Sent(ON, NOW + 199)})
    assert run(plant, pending, replace(live, flowing=False), NOW + 200)[0].live
    assert run(plant, stopped, State(), NOW)[0].live is False
    # An unarmed output that stays on cannot hold the off sequence open.
    unarmed_on = observe(
        plant, control=False, on=["switch.boiler"], armed=["switch.valve", "switch.pump"]
    )
    assert not run(plant, unarmed_on, replace(live, flowing=False), NOW + 200)[0].live


# Windows


WINDOWED = RADIATOR.replace(
    "    thermostat: {digital: {min_on: 0, min_off: 0}}",
    "    thermostat: {digital: {min_on: 600, min_off: 600}}\n"
    "    windows: [binary_sensor.window, binary_sensor.door]",
)


def windows(
    plant: Plant, temperature: float, *, window: bool | None = False, since: float = LONG_AGO
) -> Observations:
    """The room at ``temperature`` with its window as given since ``since``, and its door closed."""
    base = observe(plant, temperatures={"room": temperature})
    return replace(
        base,
        readiness={
            "binary_sensor.window": SwitchState(window, since),
            "binary_sensor.door": SwitchState(False, LONG_AGO),
        },
    )


def test_an_open_window_turns_the_demand_off_after_its_delay_and_back_on_after_closing() -> None:
    plant = _plant(WINDOWED)
    calling = State(
        live=True, mode=Mode.HEAT, demands={"room": DemandState(Mode.HEAT, True, LONG_AGO)}
    )
    opened = windows(plant, 19.0, window=True, since=NOW - 30)
    state, desired, due = run(plant, opened, calling)
    assert desired.demands["room"].on and not state.windows_open
    assert due == pytest.approx(30 + TICK)

    inhibited, desired, _ = run(plant, opened, state, NOW + 30)
    assert inhibited.windows_open == {"room"}
    assert desired.demands["room"] == Demand(Mode.HEAT, False, "window open")
    assert desired.reasons["room"] == "idle: window open"
    assert desired.outputs["switch.valve"] == OFF
    assert inhibited.demands["room"].on, "the thermostat's own decision goes on underneath"

    # A window that closes holds the inhibit for the close delay.
    closed = windows(plant, 19.0, since=NOW + 100)
    held, desired, due = run(plant, closed, inhibited, NOW + 130)
    assert held.windows_open == {"room"} and not desired.demands["room"].on
    assert due == pytest.approx(30 + TICK)
    resumed, desired, _ = run(plant, closed, held, NOW + 160)
    assert not resumed.windows_open and desired.demands["room"].on
    assert resumed.demands["room"] == DemandState(Mode.HEAT, True, NOW + 160)

    # Warm enough right after it resumed, the demand keeps its minimum on time from the
    # end of the inhibit, so the valve that just opened again does not close at once.
    warm = windows(plant, 21.5, since=NOW + 100)
    state, desired, _ = run(plant, warm, resumed, NOW + 190)
    assert desired.demands["room"].on
    assert desired.demands["room"].reason.endswith("held for its minimum on time")
    assert not run(plant, warm, calling, NOW + 190)[1].demands["room"].on, "without a window"


def test_a_window_turns_cooling_off_too_and_an_external_thermostat_is_inhibited_alike() -> None:
    plant = _plant(
        WINDOWED.replace("pump: pump}", "pump: pump, modes: [heat, cool]}").replace(
            "overrun: 120}", "overrun: 120, supply_temperature: sensor.supply}"
        )
    )
    opened = replace(
        windows(plant, 26.0, window=True),
        mode=Mode.COOL,
        thermostats={"room": DigitalThermostatState(Mode.COOL, 21.0)},
    )
    assert run(plant, opened)[1].demands["room"] == Demand(Mode.COOL, False, "window open")

    external = _plant(
        WINDOWED.replace("{digital: {min_on: 600, min_off: 600}}", "{external: climate.room}")
    )
    heating = replace(
        windows(external, 19.0, window=True),
        thermostats={"room": ExternalThermostatState(Mode.HEAT)},
    )
    assert run(external, heating)[1].demands["room"].reason == "window open"


def test_an_unavailable_window_counts_as_closed() -> None:
    plant = _plant(WINDOWED)
    lost = windows(plant, 19.0, window=None)
    state, desired, _ = run(plant, lost)
    assert desired.demands["room"].on and not state.windows_open
    missing = replace(lost, readiness={})
    assert run(plant, missing)[1].demands["room"].on

    # While the inhibit holds, a window that becomes unavailable closes after the delay.
    inhibited = State(live=True, mode=Mode.HEAT, windows_open=frozenset({"room"}))
    lost_since = windows(plant, 19.0, window=None, since=NOW - 10)
    state, desired, _ = run(plant, lost_since, inhibited)
    assert state.windows_open == {"room"} and desired.demands["room"].reason == "window open"
    assert not run(plant, lost_since, state, NOW + 50)[0].windows_open


# Frost protection

# Two radiator zones on one pump; the room also has an optional floor probe.
CABIN = """
hydronicus: 2
name: Cabin
pumps:
  pump: {switch: switch.pump, overrun: 0}
zones:
  room:
    temperature: [sensor.room, {entity: sensor.room_floor, required: false}]
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      radiator: {valves: [switch.valve], pump: pump}
  hall:
    temperature: [sensor.hall]
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      radiator: {valves: [switch.hall_valve], pump: pump}
"""


def _frosty(
    plant: Plant, floor: float, *, mode: Mode = Mode.HEAT, control: bool = True
) -> Observations:
    """The room reads 20 °C in the air and ``floor`` on its floor probe; the hall calls."""
    observations = observe(
        plant,
        mode=mode,
        control=control,
        temperatures={"room": 20.0, "hall": 18.0},
        sensors={"sensor.room_floor": Reading(floor, NOW)},
    )
    return replace(
        observations,
        thermostats={
            "room": DigitalThermostatState(Mode.OFF, 21.0),
            "hall": DigitalThermostatState(Mode.HEAT, 21.0),
        },
    )


def test_frost_protection_heats_its_zone_alone_while_the_mode_select_is_off() -> None:
    plant = _plant(CABIN)
    state, desired, _ = run(plant, _frosty(plant, 4.0, mode=Mode.OFF), State(live=True))
    assert desired.mode is Mode.HEAT and desired.frost_protection == ("room",)
    assert desired.demands["room"] == Demand(
        Mode.HEAT, True, "frost protection: heat to 6.0 °C from 4.0 °C"
    ), "the coldest reading counts, not the zone's mean"
    assert desired.reasons["room"] == "demands: frost protection: heat to 6.0 °C from 4.0 °C"
    assert desired.demands["hall"].on, "the hall's thermostat still asks"
    assert targets(desired, "switch.valve", "switch.hall_valve") == [ON, OFF], (
        "only frost protection runs while the Mode select is off"
    )
    assert state.frost == {"room"} and state.last_mode is Mode.HEAT


def test_frost_protection_holds_until_one_kelvin_above_its_temperature() -> None:
    plant = _plant(CABIN)
    state, _, _ = run(plant, _frosty(plant, 4.0))
    state, desired, _ = run(plant, _frosty(plant, 5.9), state)
    assert desired.frost_protection == ("room",), "it holds below 6 °C once it started"
    state, desired, _ = run(plant, _frosty(plant, 6.0), state)
    assert desired.frost_protection == () and state.frost == frozenset()
    assert desired.demands["room"].reason == "thermostat off"
    _, desired, _ = run(plant, _frosty(plant, 5.5), state)
    assert desired.frost_protection == (), "it starts only below 5 °C"


def test_frost_protection_overrides_a_thermostat_that_is_off_or_unavailable() -> None:
    plant = read_plant_file(
        RADIATOR.replace("{digital: {min_on: 0, min_off: 0}}", "{external: climate.room}")
    )
    base = observe(plant, temperatures={"room": 3.0})
    for action in (Mode.OFF, None):
        frosty = replace(base, thermostats={"room": ExternalThermostatState(action)})
        _, desired, _ = run(plant, frosty)
        assert desired.demands["room"].reason.startswith("frost protection")
        assert desired.outputs["switch.valve"] == ON


def test_frost_protection_overrides_an_open_window() -> None:
    plant = _plant(WINDOWED)
    state, desired, _ = run(plant, windows(plant, 3.0, window=True))
    assert state.windows_open == {"room"}, "the window still counts as open"
    assert state.demands["room"] == DemandState(Mode.HEAT, True, NOW), (
        "the thermostat's decision underneath stays its own"
    )
    assert desired.demands["room"].reason == "frost protection: heat to 6.0 °C from 3.0 °C"
    assert desired.outputs["switch.valve"] == ON


def test_frost_protection_never_heats_while_the_plant_cools_or_is_turned_off() -> None:
    plant = _plant(CABIN)
    _, desired, _ = run(plant, _frosty(plant, 3.0, mode=Mode.COOL))
    assert desired.frost_protection == () and desired.mode is Mode.COOL
    cooling = State(live=True, mode=Mode.COOL, last_mode=Mode.COOL, flowing=True)
    _, desired, _ = run(plant, _frosty(plant, 3.0, mode=Mode.OFF), cooling)
    assert desired.frost_protection == (), "not while cooling still stops"

    live = State(live=True, mode=Mode.OFF, last_mode=Mode.HEAT)
    _, desired, _ = run(plant, _frosty(plant, 3.0, mode=Mode.OFF, control=False), live)
    assert desired.mode is Mode.OFF, "Control equipment off runs the off sequence, then nothing"
    assert all(target == OFF for target in desired.outputs.values())
    assert desired.frost_protection == (), "and reports no frost protection meanwhile"

    unprotected = read_plant_file(
        CABIN.replace("name: Cabin", "name: Cabin\nfrost_protection: false")
    )
    _, desired, _ = run(unprotected, _frosty(unprotected, 3.0, mode=Mode.OFF), State(live=True))
    assert desired.mode is Mode.OFF and desired.frost_protection == ()


def test_frost_protection_after_cooling_waits_for_the_mode_dwell() -> None:
    plant = _plant(CABIN)
    after = State(live=True, mode=Mode.OFF, last_mode=Mode.COOL, flow_ended=NOW - 60)
    _, desired, due = run(plant, _frosty(plant, 3.0, mode=Mode.OFF), after)
    assert desired.mode is Mode.OFF
    assert desired.reasons["mode"] == "waiting for the mode dwell before heat"
    assert due == pytest.approx(3600.0 - 60.0 + TICK)
    _, desired, _ = run(plant, _frosty(plant, 3.0, mode=Mode.OFF), after, NOW + 3540)
    assert desired.mode is Mode.HEAT and desired.outputs["switch.valve"] == ON


# The exercise


def _overdue(plant: Plant, *entities: str) -> dict[str, float | None]:
    """Every switched pump and valve seen on just now, but ``entities`` an interval ago."""
    idle: dict[str, float | None] = {
        entity: NOW
        for entity, role in plant.outputs().items()
        if role in (OutputRole.PUMP, OutputRole.VALVE)
    }
    idle.update({entity: NOW - DEFAULT_EXERCISE_INTERVAL for entity in entities})
    return idle


def test_the_exercise_clock_starts_when_an_output_is_first_seen() -> None:
    plant = _plant(RADIATOR)
    idle = observe(plant, mode=Mode.OFF)
    state, desired, due = run(plant, idle, State(live=True))
    assert state.idle_since == {"switch.pump": NOW, "switch.valve": NOW}
    assert desired.exercise is None and state.exercise is None
    assert due == pytest.approx(DEFAULT_MAX_AGE + TICK), "the readings age first"
    later = NOW + DEFAULT_EXERCISE_INTERVAL
    assert run(plant, idle, state, later - 1)[1].exercise is None
    assert run(plant, idle, state, later)[1].exercise == "pump"

    running = observe(plant, mode=Mode.OFF, on=["switch.pump"])
    state, _, _ = run(plant, running, state, NOW + 10)
    assert state.idle_since == {"switch.pump": None, "switch.valve": NOW}
    stopped = observe(plant, mode=Mode.OFF, since={"switch.pump": NOW + 15})
    state, _, _ = run(plant, stopped, state, NOW + 20)
    assert state.idle_since["switch.pump"] == NOW + 15, "idle since it was seen to stop"


def test_an_exercise_opens_the_valve_runs_the_pump_and_never_asks_the_source() -> None:
    plant = _plant(RADIATOR)
    overdue = State(live=True, idle_since=_overdue(plant, "switch.pump"))
    state, desired, _ = run(plant, observe(plant, mode=Mode.OFF), overdue)
    assert desired.exercise == "pump" and state.exercise == ExerciseState("pump", NOW)
    assert targets(desired, "switch.valve", "switch.pump", "switch.boiler") == [ON, OFF, OFF]
    assert desired.reasons["room.radiator"] == "exercise"
    assert state.last_mode is Mode.OFF, "an exercise of a new Plant runs in heat but sets no mode"

    ready = observe(plant, mode=Mode.OFF, on=["switch.valve"])
    state, desired, _ = run(plant, ready, state)
    assert targets(desired, "switch.valve", "switch.pump", "switch.boiler") == [ON, ON, OFF]
    assert desired.reasons["switch.pump"] == "exercise"

    running = observe(plant, mode=Mode.OFF, on=["switch.valve", "switch.pump"])
    state, desired, due = run(plant, running, state)
    assert state.exercise == ExerciseState("pump", NOW, NOW) and not desired.source_request
    assert due == pytest.approx(60.0 + TICK), "the pump runs for the exercise's run time"

    state, desired, _ = run(plant, running, state, NOW + 60)
    assert desired.exercise is None
    assert state.exercise == ExerciseState("pump", NOW, NOW, done=True)
    assert state.exercise_ended == {"pump": NOW + 60}
    assert targets(desired, "switch.valve", "switch.pump") == [ON, OFF], (
        "the pump stops without overrun, and its valve waits for it"
    )
    assert desired.reasons["switch.pump"] == "exercise over"

    stopped = observe(plant, mode=Mode.OFF, on=["switch.valve"])
    state, desired, _ = run(plant, stopped, state, NOW + 70)
    assert state.exercise is None and desired.outputs["switch.valve"] == OFF
    assert state.idle_since == {"switch.pump": LONG_AGO, "switch.valve": None}
    assert (state.last_mode, state.flowing, state.flow_ended) == (Mode.OFF, False, None)


def test_an_exercise_yields_at_once_to_demand() -> None:
    plant = _plant(RADIATOR)
    exercising = State(
        live=True,
        mode=Mode.HEAT,
        last_mode=Mode.HEAT,
        exercise=ExerciseState("pump", NOW - 200, NOW - 10),
    )
    both = ["switch.valve", "switch.pump"]
    _, desired, _ = run(plant, observe(plant, on=both), exercising)
    assert desired.exercise == "pump"

    cold = observe(plant, temperatures={"room": 19.0}, on=both)
    state, desired, _ = run(plant, cold, exercising)
    assert desired.exercise is None and state.exercise is None
    assert desired.reasons["room.radiator"] == "wanted"
    assert desired.outputs["switch.boiler"] == ON, "the pump runs on for the demand"

    frosty = observe(plant, mode=Mode.OFF, temperatures={"room": 3.0}, on=both)
    _, desired, _ = run(plant, frosty, exercising)
    assert desired.exercise is None and desired.frost_protection == ("room",)


def test_an_exercise_waits_for_an_idle_plant_and_can_be_turned_off() -> None:
    plant = _plant(RADIATOR)
    overdue = State(live=True, idle_since=_overdue(plant, "switch.valve"))
    busy = [
        observe(plant, mode=Mode.OFF, on=["switch.boiler"]),
        observe(plant, mode=Mode.OFF, sent={"switch.pump": Sent(ON, NOW)}),
        observe(plant, mode=Mode.OFF, control=False),
    ]
    for observations in busy:
        assert run(plant, observations, overdue)[1].exercise is None
    changing = replace(overdue, last_mode=Mode.COOL, flow_ended=NOW - 60)
    assert run(plant, observe(plant), changing)[1].exercise is None, "not during the dwell"

    unexercised = read_plant_file(RADIATOR.replace("name: Flat", "name: Flat\nexercise: false"))
    assert run(unexercised, observe(unexercised, mode=Mode.OFF), overdue)[1].exercise is None


def test_an_exercise_runs_one_pump_at_a_time_and_skips_what_it_cannot_run() -> None:
    plant = _plant(HEAT_PUMP)
    everything = _overdue(plant, *plant.outputs())
    overdue = State(live=True, last_mode=Mode.HEAT, idle_since=everything)
    state, desired, _ = run(plant, observe(plant, mode=Mode.OFF), overdue)
    assert state.exercise == ExerciseState("hp", NOW)
    assert targets(desired, "switch.a_ceiling", "switch.b_ceiling", "switch.c_floor") == [
        ON,
        ON,
        OFF,
    ], "the source-driven pump's valves open first, and alone"
    assert not desired.source_request

    unarmed = [entity for entity in plant.outputs() if entity != "switch.floor_pump"]
    valves_only = replace(overdue, idle_since=_overdue(plant, "switch.c_floor"))
    state, desired, _ = run(plant, observe(plant, mode=Mode.OFF, armed=unarmed), valves_only)
    assert state.exercise == ExerciseState("floor", NOW)
    ready = observe(plant, mode=Mode.OFF, armed=unarmed, on=["switch.c_floor"])
    state, desired, _ = run(plant, ready, state)
    assert desired.outputs["switch.floor_pump"] == OFF, "an unarmed pump is never run"
    assert state.exercise is None, "its valve alone is exercised, once it is ready"
    assert state.exercise_ended == {"floor": NOW}


def test_an_exercise_after_cooling_passes_only_cooling_loops_whose_guard_permits() -> None:
    plant = _plant(HEAT_PUMP)
    overdue = State(live=True, last_mode=Mode.COOL, idle_since=_overdue(plant, *plant.outputs()))
    state, desired, _ = run(plant, observe(plant, mode=Mode.OFF), overdue)
    assert state.exercise == ExerciseState("hp", NOW), "the heat-only floor and towel wait"
    assert targets(desired, "switch.a_ceiling", "switch.b_ceiling") == [ON, ON]
    assert state.last_mode is Mode.COOL

    stale = {"sensor.supply": Reading(20.0, NOW - 7200)}
    state, desired, _ = run(plant, observe(plant, mode=Mode.OFF, sensors=stale), overdue)
    assert state.exercise is None, "a blocked condensation guard passes no exercise"
    assert all(target == OFF for target in desired.outputs.values())


# Two pumps: one with a floor and a wall loop, the other with a radiator.
TWO_PUMPS = """
hydronicus: 2
name: Two
pumps:
  a: {switch: switch.a, overrun: 0}
  b: {switch: switch.b, overrun: 0}
zones:
  room:
    temperature: [sensor.room]
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      floor: {valves: [switch.floor], pump: a}
      wall: {valves: [switch.wall], pump: a}
      radiator: {valves: [switch.radiator], pump: b}
"""


def test_the_exercise_grace_is_the_reconcilers_travel_grace() -> None:
    assert EXERCISE_GRACE == TRAVEL_GRACE


def test_an_exercise_gives_up_on_a_valve_that_never_opens_and_the_next_pump_goes_first() -> None:
    plant = _plant(TWO_PUMPS)
    overdue = State(live=True, idle_since=_overdue(plant, *plant.outputs()))
    state, desired, _ = run(plant, observe(plant, mode=Mode.OFF), overdue)
    assert state.exercise == ExerciseState("a", NOW)
    assert targets(desired, "switch.floor", "switch.wall", "switch.a") == [ON, ON, OFF]

    # The wall valve's relay no longer responds, and the floor is ready at once.
    floor = observe(plant, mode=Mode.OFF, on=["switch.floor"])
    state, desired, _ = run(plant, floor, state, NOW + 5)
    assert desired.outputs["switch.a"] == ON, "the pump runs once one of its loops is ready"
    running = observe(plant, mode=Mode.OFF, on=["switch.floor", "switch.a"])
    state, _, _ = run(plant, running, state, NOW + 10)
    assert state.exercise == ExerciseState("a", NOW, NOW + 10)

    give_up = NOW + 2 * 180 + 60 + EXERCISE_GRACE
    state, desired, due = run(plant, running, state, NOW + 70)
    assert desired.exercise == "a", "after its run time the pump waits for the wall valve"
    assert due == pytest.approx(give_up - (NOW + 70) + TICK)
    state, desired, _ = run(plant, running, state, give_up)
    assert state.exercise == ExerciseState("a", NOW, NOW + 10, done=True)
    assert state.exercise_ended == {"a": give_up}
    assert targets(desired, "switch.a", "switch.wall") == [OFF, OFF]

    stopped = observe(plant, mode=Mode.OFF, on=["switch.floor"])
    state, desired, _ = run(plant, stopped, state, give_up + 5)
    assert state.exercise == ExerciseState("b", give_up + 5), "not pump a again at once"
    assert state.exercise_ended == {"a": give_up}


def test_an_exercise_skips_a_pump_whose_switch_is_not_observed_and_never_waits_for_it() -> None:
    plant = _plant(TWO_PUMPS)
    overdue = State(live=True, idle_since=_overdue(plant, *plant.outputs()))
    lost = observe(plant, mode=Mode.OFF, unavailable=["switch.a"])
    state, desired, _ = run(plant, lost, overdue)
    assert state.exercise == ExerciseState("b", NOW), "pump a may be running unseen"
    assert targets(desired, "switch.floor", "switch.wall", "switch.radiator") == [OFF, OFF, ON]

    stopping = replace(overdue, exercise=ExerciseState("a", NOW - 300, NOW - 240, done=True))
    state, _, _ = run(plant, lost, stopping)
    assert state.exercise == ExerciseState("b", NOW), "a lost switch shows nothing to wait for"


def test_an_exercise_sets_no_mode_so_a_new_plant_cools_without_the_dwell() -> None:
    plant = _plant(COOLED_CEILING)

    def seen(mode: Mode, *on: str) -> Observations:
        base = cooling(plant, mode=mode)
        running = {entity: SwitchState(True, LONG_AGO) for entity in on}
        return replace(base, outputs={**base.outputs, **running})

    overdue = State(live=True, idle_since=_overdue(plant, *plant.outputs()))
    state, desired, _ = run(plant, seen(Mode.OFF), overdue)
    assert desired.exercise == "pump" and desired.outputs["switch.ceiling"] == ON
    state, desired, _ = run(plant, seen(Mode.OFF, "switch.ceiling"), state)
    assert desired.outputs["switch.pump"] == ON, "a new Plant exercises in heat"
    state, _, _ = run(plant, seen(Mode.OFF, "switch.ceiling", "switch.pump"), state)
    assert (state.last_mode, state.flowing, state.flow_ended) == (Mode.OFF, False, None)

    both = seen(Mode.COOL, "switch.ceiling", "switch.pump")
    state, desired, _ = run(plant, both, state, NOW + 5)
    assert desired.mode is Mode.OFF
    assert desired.reasons["mode"] == "stopping the exercise before cool"
    assert desired.outputs["switch.pump"] == OFF and desired.exercise is None
    state, desired, _ = run(plant, seen(Mode.COOL, "switch.ceiling"), state, NOW + 10)
    assert desired.mode is Mode.COOL, "the first mode of a new Plant needs no dwell"
    assert desired.outputs["switch.ceiling"] == ON


def test_an_exercise_after_cooling_needs_only_the_checks_against_condensation() -> None:
    plant = _plant(COOLED_CEILING)
    # 19 °C at 30 % has a dew point of 0.9 °C, so only the surface minimum blocks cooling.
    cold = {"sensor.supply": 24.0, "sensor.room": 19.0, "sensor.room_rh": 30.0}
    cold["sensor.surface"] = 19.5
    wet = {**DRY, "binary_sensor.ceiling_dew": True}
    idle = _overdue(plant, *plant.outputs())
    for mode in (Mode.OFF, Mode.COOL):
        after = State(live=True, mode=mode, last_mode=Mode.COOL, idle_since=idle)
        quiet = cooling(plant, sensors=cold, mode=mode)
        state, desired, _ = run(plant, quiet, after)
        assert state.guards["room.ceiling"].blocked, "the guard blocks cooling"
        assert state.exercise == ExerciseState("pump", NOW), "no chilled water flows"
        opened = {**quiet.outputs, "switch.ceiling": SwitchState(True, LONG_AGO)}
        _, desired, _ = run(plant, replace(quiet, outputs=opened), state)
        assert targets(desired, "switch.ceiling", "switch.pump") == [ON, ON]

        state, _, _ = run(plant, cooling(plant, sensors=cold, mode=mode, switches=wet), after)
        assert state.exercise is None, "a condensation switch still stops it"


def test_idle_clocks_stand_still_in_dry_run_and_an_exercise_follows_control_on() -> None:
    plant = _plant(RADIATOR)
    overdue = State(idle_since=_overdue(plant, "switch.pump"))
    state, desired, _ = run(plant, observe(plant, mode=Mode.OFF, control=False), overdue)
    assert desired.exercise == "pump", "the exercise is proposed in Dry run"

    both = ["switch.valve", "switch.pump"]
    proposed = observe(plant, mode=Mode.OFF, control=False, on=both)
    state, _, _ = run(plant, proposed, state, NOW + 10)
    state, desired, _ = run(plant, proposed, state, NOW + 70)
    assert desired.outputs["switch.pump"] == OFF and state.exercise_ended == {"pump": NOW + 70}
    stopped = observe(
        plant, mode=Mode.OFF, control=False, on=["switch.valve"], since={"switch.pump": NOW + 75}
    )
    state, desired, _ = run(plant, stopped, state, NOW + 80)
    assert state.exercise is None, "a proposal counts as done"
    assert state.idle_since == overdue.idle_since, "but never moves the clocks"

    state, desired, _ = run(plant, observe(plant, mode=Mode.OFF), state, NOW + 90)
    assert state.exercise == ExerciseState("pump", NOW + 90) and state.exercise_ended == {}
    assert desired.outputs["switch.valve"] == ON, "the equipment is exercised once it is live"


def test_a_new_condensation_guard_blocks_until_every_check_releases() -> None:
    plant = _plant(COOLED_CEILING)
    fresh = cooling(plant, switched=NOW - 10)
    state, desired, _ = run(plant, fresh)
    assert state.guards["room.ceiling"] == GuardState(True, NOW)
    assert desired.reasons["room.ceiling.guard"] == (
        "condensation guard blocks: condensation switch binary_sensor.supply_dew off for less "
        "than 300 s; condensation switch binary_sensor.ceiling_dew off for less than 300 s"
    )
    assert desired.outputs["switch.ceiling"] == OFF
    released, desired, _ = run(plant, fresh, state, NOW + GUARD_MIN_BLOCKED)
    assert not released.guards["room.ceiling"].blocked
    assert desired.outputs["switch.ceiling"] == ON


def test_the_desired_state_names_the_unusable_condensation_inputs_in_any_mode() -> None:
    plant = _plant(COOLED_CEILING)
    lost = cooling(
        plant,
        switches={"binary_sensor.ceiling_dew": None},
        sensors={"sensor.supply": 24.0, "sensor.room_rh": 50.0},
    )
    inputs = ("sensor.surface", "binary_sensor.supply_dew", "binary_sensor.ceiling_dew")
    for mode in (Mode.OFF, Mode.HEAT, Mode.COOL):
        _, desired, _ = run(plant, replace(lost, mode=mode))
        assert desired.blocking_condensation_inputs == {"room.ceiling": inputs}

    stale = cooling(plant, sensors={"sensor.surface": 24.0, "sensor.room_rh": 50.0})
    aged = Reading(24.0, NOW - GUARD_REFERENCE_MAX_AGE - 1)
    _, desired, _ = run(plant, replace(stale, sensors={**stale.sensors, "sensor.supply": aged}))
    assert desired.blocking_condensation_inputs == {"room.ceiling": ("sensor.supply",)}
    assert run(plant, cooling(plant))[1].blocking_condensation_inputs == {}


# A zone with no loop of its own, which a plant loop heats.
SHARED = """
hydronicus: 2
name: Shared
pumps:
  pump: {switch: switch.pump, overrun: 0}
loops:
  floor: {valves: [switch.floor], pump: pump, runs: {with_zones: [room]}}
zones:
  room:
    temperature: [sensor.room]
    thermostat: {digital: {min_on: 0, min_off: 0}}
"""


def test_frost_protection_heats_only_a_zone_that_a_loop_heats() -> None:
    cool_only = _plant(COOLED_CEILING.replace("modes: [heat, cool]", "modes: [cool]"))
    frosty = observe(cool_only, mode=Mode.OFF, temperatures={"room": 3.0})
    _, desired, _ = run(cool_only, frosty, State(live=True))
    assert desired.frost_protection == () and desired.mode is Mode.OFF

    shared = _plant(SHARED)
    frosty = observe(shared, mode=Mode.OFF, temperatures={"room": 3.0})
    _, desired, _ = run(shared, frosty, State(live=True))
    assert desired.frost_protection == ("room",), "a plant loop that runs with it heats it"
    assert desired.outputs["switch.floor"] == ON


def test_source_minimum_off_time_begins_when_the_request_really_stops() -> None:
    plant = _plant(RADIATOR)
    on = observe(plant, temperatures={"room": 19.0}, on=plant.outputs())
    running, _, _ = run(plant, on, now=NOW)
    warm = replace(on, thermostats={"room": DigitalThermostatState(Mode.OFF, 21.0)})
    released, desired, _ = run(plant, warm, running, NOW + 610)
    assert not desired.source_request
    # A stop ignored for longer than min_off must not use up the actual off time.
    ignored, _, _ = run(plant, warm, released, NOW + 1220)
    stopped = replace(on, outputs={**on.outputs, "switch.boiler": SwitchState(False, NOW + 1220)})
    off, desired, _ = run(plant, stopped, ignored, NOW + 1220)
    assert not desired.source_request
    assert "minimum off time" in desired.reasons["source"]
    assert run(plant, stopped, off, NOW + 1519)[1].source_request is False
    assert run(plant, stopped, off, NOW + 1520)[1].source_request is True


def test_dry_run_handover_waits_for_real_flow_to_stop_and_full_dwell() -> None:
    plant = _plant(HEAT_PUMP)
    simulated = State(live=False, mode=Mode.COOL, last_mode=Mode.COOL, dry_run=True)
    real = observe(plant, mode=Mode.COOL, on=["switch.c_floor", "switch.floor_pump"])
    stopping, desired, _ = run(plant, real, simulated)
    assert not desired.source_request
    assert desired.outputs["switch.floor_pump"] == OFF
    assert desired.mode is Mode.OFF
    stopped = replace(
        real, outputs={**real.outputs, "switch.floor_pump": SwitchState(False, NOW + 1)}
    )
    waiting, desired, _ = run(plant, stopped, stopping, NOW + 1)
    assert desired.mode is Mode.OFF
    # Off does not allow an exercise to bypass the unfinished physical dwell.
    off = replace(stopped, mode=Mode.OFF)
    assert run(plant, off, waiting, NOW + 300)[1].exercise is None
    assert run(plant, stopped, waiting, NOW + 600)[1].mode is Mode.OFF
    assert run(plant, stopped, waiting, NOW + 601)[1].mode is Mode.COOL


def test_source_minimum_on_time_begins_when_delayed_start_is_observed() -> None:
    plant = _plant(RADIATOR)
    ready = observe(plant, temperatures={"room": 19.0}, on=["switch.valve", "switch.pump"])
    starting, desired, _ = run(plant, ready)
    assert desired.source_request
    # Repeated start decisions never consume the physical minimum on period.
    starting, desired, _ = run(plant, ready, starting, NOW + 610)
    assert desired.source_request
    warm = observe(
        plant,
        temperatures={"room": 22.0},
        on=plant.outputs(),
        since={"switch.boiler": NOW + 610},
    )
    running, desired, _ = run(plant, warm, starting, NOW + 610)
    assert desired.source_request
    assert run(plant, warm, running, NOW + 909)[1].source_request
    assert not run(plant, warm, running, NOW + 910)[1].source_request


def test_switched_pump_starts_before_flow_proof_and_source_waits_for_proof() -> None:
    plant = _plant(RADIATOR.replace("overrun: 120", "overrun: 0, flow_sensor: binary_sensor.flow"))
    ready = observe(
        plant,
        temperatures={"room": 19.0},
        on=["switch.valve"],
        readiness={"binary_sensor.flow": False},
    )
    _, desired, _ = run(plant, ready)
    assert desired.outputs["switch.pump"] == ON
    assert not desired.source_request
    pump_on = replace(ready, outputs={**ready.outputs, "switch.pump": SwitchState(True, NOW)})
    assert not run(plant, pump_on)[1].source_request
    proved = replace(pump_on, readiness={"binary_sensor.flow": SwitchState(True, NOW)})
    assert run(plant, proved)[1].source_request
    missing = replace(ready, readiness={})
    assert run(plant, missing)[1].outputs["switch.pump"] == OFF


def test_running_feedback_preserves_a_path_after_pump_switch_stops() -> None:
    plant = _plant(
        RADIATOR.replace("overrun: 120", "overrun: 0, running_sensor: binary_sensor.running")
    )
    on = observe(plant, on=["switch.valve"], readiness={"binary_sensor.running": True})
    for proof in (True, None):
        observed = replace(on, readiness={"binary_sensor.running": SwitchState(proof, NOW)})
        assert run(plant, observed)[1].outputs["switch.valve"] == ON
    stopped = replace(on, readiness={"binary_sensor.running": SwitchState(False, NOW)})
    assert run(plant, stopped)[1].outputs["switch.valve"] == OFF


def test_source_driven_flow_proof_has_bounded_startup_grace_without_deadlock() -> None:
    plant = _plant(
        HEAT_PUMP.replace(
            "driven_by: source,", "driven_by: source, flow_sensor: binary_sensor.flow,"
        )
    )
    ready = observe(
        plant,
        temperatures={"a": 19.0},
        on=["switch.a_ceiling"],
        readiness={"binary_sensor.flow": False},
    )
    started, desired, _ = run(plant, ready)
    assert desired.source_request
    running = replace(ready, outputs={**ready.outputs, "switch.hp": SwitchState(True, NOW)})
    started, desired, _ = run(plant, running, started, NOW + 1)
    assert desired.source_request
    assert not run(plant, running, started, NOW + 300)[1].source_request
    confirmed = replace(running, readiness={"binary_sensor.flow": SwitchState(True, NOW + 1)})
    assert run(plant, confirmed, started, NOW + 300)[1].source_request
    assert not run(plant, replace(ready, readiness={}))[1].source_request


def test_source_running_proof_keeps_switched_flow_after_request_stops() -> None:
    plant = _plant(
        RADIATOR.replace(
            "post_run: 60", "post_run: 0, running_sensor: binary_sensor.source_running"
        )
    )
    observed = observe(
        plant, on=["switch.valve", "switch.pump"], readiness={"binary_sensor.source_running": True}
    )
    state = State(live=True, mode=Mode.HEAT, last_mode=Mode.HEAT, overruns={"pump": LONG_AGO})
    desired = run(plant, observed, state)[1]
    assert desired.outputs["switch.pump"] == ON
    assert desired.outputs["switch.valve"] == ON
    stopped = replace(observed, readiness={"binary_sensor.source_running": SwitchState(False, NOW)})
    assert run(plant, stopped, state)[1].outputs["switch.pump"] == OFF


def test_numeric_supply_must_be_armed_confirmed_and_fresh_before_source_runs() -> None:
    from custom_components.hydronicus.core.model import NumericTarget
    from custom_components.hydronicus.core.step import NumericState

    plant = _plant(
        RADIATOR.replace(
            "request: switch.boiler,",
            "request: switch.boiler, supply: {entity: number.supply, "
            "outdoor_sensor: sensor.outdoor, max_age: 60},",
        )
    )
    ready = observe(plant, temperatures={"room": 19.0}, on=["switch.valve", "switch.pump"])
    ready = replace(
        ready,
        outputs={**ready.outputs, "number.supply": NumericState(30, NOW)},
        sensors={**ready.sensors, "sensor.outdoor": Reading(5, NOW)},
    )
    _, desired, due = run(plant, ready)
    assert desired.outputs["number.supply"] == NumericTarget(35, 0.5)
    assert not desired.source_request
    assert due == pytest.approx(60 + TICK)
    matched = replace(ready, outputs={**ready.outputs, "number.supply": NumericState(34.5, NOW)})
    assert run(plant, matched)[1].source_request
    assert not run(plant, replace(matched, armed=matched.armed - {"number.supply"}))[
        1
    ].source_request
    assert not run(
        plant,
        replace(
            matched, outputs={**matched.outputs, "number.supply": NumericState(float("nan"), NOW)}
        ),
    )[1].source_request
    _, stale, _ = run(plant, matched, now=NOW + 60)
    assert not stale.source_request
    assert "number.supply" not in stale.outputs
    assert "stale" in stale.reasons["source"]


def test_cooling_supply_target_protects_full_confirmation_band_above_dew_point() -> None:
    from custom_components.hydronicus.core.model import NumericTarget
    from custom_components.hydronicus.core.step import NumericState

    plant = _plant(
        HEAT_PUMP.replace(
            "request: switch.hp",
            "request: switch.hp\n  supply: {entity: number.supply, "
            "cool_temperature: 5, maximum: 60}",
        )
    )
    ready = observe(
        plant,
        mode=Mode.COOL,
        temperatures={"a": 26.0},
        sensors={"sensor.a_rh": Reading(40, NOW), "sensor.supply": Reading(25, NOW)},
        on=["switch.a_ceiling"],
        option="Cool",
    )
    ready = replace(ready, outputs={**ready.outputs, "number.supply": NumericState(5, NOW)})
    desired = run(plant, ready)[1]
    target = desired.outputs["number.supply"]
    assert isinstance(target, NumericTarget)
    assert target.value > 14
    assert not desired.source_request
    confirmed = replace(
        ready, outputs={**ready.outputs, "number.supply": NumericState(target.value, NOW)}
    )
    assert run(plant, confirmed)[1].source_request
    assert plant.source is not None and plant.source.supply is not None
    impossible = replace(
        plant, source=replace(plant.source, supply=replace(plant.source.supply, maximum=10))
    )
    desired = run(impossible, confirmed)[1]
    assert not desired.source_request
    assert "exceeds" in desired.reasons["source"]


def test_running_heating_source_keeps_running_during_safe_curve_adjustment() -> None:
    from custom_components.hydronicus.core.model import NumericTarget
    from custom_components.hydronicus.core.step import NumericState

    plant = _plant(
        RADIATOR.replace(
            "request: switch.boiler,",
            "request: switch.boiler, supply: {entity: number.supply, "
            "outdoor_sensor: sensor.outdoor},",
        )
    )
    observed = observe(plant, temperatures={"room": 19.0}, on=plant.outputs())
    observed = replace(
        observed,
        outputs={**observed.outputs, "number.supply": NumericState(35, NOW)},
        sensors={**observed.sensors, "sensor.outdoor": Reading(5, NOW)},
    )
    running, desired, _ = run(plant, observed)
    assert desired.source_request
    warming = replace(observed, sensors={**observed.sensors, "sensor.outdoor": Reading(7, NOW)})
    desired = run(plant, warming, running, NOW + 10)[1]
    assert desired.source_request
    assert desired.outputs["number.supply"] == NumericTarget(pytest.approx(33.66666667), 0.5)
    # The configured absolute limits override the normal numeric tolerance.
    assert plant.source is not None and plant.source.supply is not None
    bounded = replace(
        plant, source=replace(plant.source, supply=replace(plant.source.supply, maximum=35))
    )
    too_high = replace(
        observed, outputs={**observed.outputs, "number.supply": NumericState(35.1, NOW)}
    )
    assert not run(bounded, too_high)[1].source_request
    assert not run(bounded, too_high, running)[1].source_request


def test_cooling_supply_covers_idle_valveless_branches_and_min_flow_paths() -> None:
    from custom_components.hydronicus.core.demand import dew_point
    from custom_components.hydronicus.core.model import NumericTarget
    from custom_components.hydronicus.core.step import NumericState

    base = """
hydronicus: 2
name: Exposed cooling
source:
  request: switch.source
  min_on: 0
  min_off: 0
  supply: {entity: number.supply, cool_temperature: 10}
pumps:
  pump: {switch: switch.pump, supply_temperature: sensor.supply, overrun: 0}
zones:
  dry:
    temperature: [sensor.dry]
    humidity: [sensor.dry_rh]
    loops: {ceiling: {pump: pump, modes: [cool]}}
  humid:
    temperature: [sensor.humid]
    humidity: [sensor.humid_rh]
    loops: {ceiling: {pump: pump, modes: [cool]}}
"""
    for text in (
        base,
        base.replace(
            "pump: {switch: switch.pump, supply_temperature: sensor.supply, overrun: 0}",
            "pump: {driven_by: source, supply_temperature: sensor.supply, "
            "min_flow_loops: [humid.ceiling]}",
        ).replace(
            "ceiling: {pump: pump, modes: [cool]}",
            "ceiling: {pump: pump, modes: [cool], valves: [switch.humid]}",
            1,
        ),
    ):
        plant = _plant(text)
        observed = observe(
            plant,
            mode=Mode.COOL,
            temperatures={"dry": 27, "humid": 25},
            on=plant.outputs(),
            sensors={
                "sensor.dry_rh": Reading(20, NOW),
                "sensor.humid_rh": Reading(60, NOW),
                "sensor.supply": Reading(28, NOW),
            },
        )
        observed = replace(
            observed,
            thermostats={
                "dry": DigitalThermostatState(Mode.COOL, 21),
                "humid": DigitalThermostatState(Mode.OFF, 21),
            },
            outputs={**observed.outputs, "number.supply": NumericState(10, NOW)},
        )
        desired = run(plant, observed)[1]
        target = desired.outputs["number.supply"]
        assert isinstance(target, NumericTarget)
        point = dew_point(25, 60)
        assert point is not None
        assert target.value - target.tolerance >= point + 3
        assert not desired.source_request
