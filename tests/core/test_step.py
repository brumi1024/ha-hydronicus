"""The step pipeline, stage by stage, on small Plants with hand-built observations."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import replace

import pytest
from hydronicus_core.model import (
    Desired,
    Mode,
    OptionTarget,
    OutputRole,
    OutputTarget,
    Plant,
    SwitchTarget,
    ValueTarget,
)
from hydronicus_core.plant_file import read_plant_file
from hydronicus_core.step import (
    CALL_TIMEOUT,
    GUARD_MIN_BLOCKED,
    TICK,
    DemandState,
    DigitalThermostatState,
    ExternalThermostatState,
    GuardState,
    Observations,
    OptionState,
    Reading,
    Sent,
    State,
    SwitchState,
    ValueState,
    satisfies,
    step,
    value_of,
)

NOW = 1_800_000_000.0
LONG_AGO = NOW - 3600.0
ON = SwitchTarget(True)
OFF = SwitchTarget(False)

# A boiler, a circulator, and one radiator zone.
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
    assert satisfies(ValueState(35.0, NOW), ValueTarget(35.0))
    assert not satisfies(OptionState("Heat", NOW), ON)
    assert not satisfies(None, ON)
    assert [value_of(SwitchState(True, 0)), value_of(OptionState("x", 0))] == [True, "x"]
    assert value_of(ValueState(None, 0)) is None


def test_state_round_trips_through_json_and_defaults_every_field() -> None:
    state = State(
        live=True,
        mode=Mode.HEAT,
        last_mode=Mode.HEAT,
        flowing=True,
        flow_ended=NOW,
        source_request=True,
        source_changed=NOW - 5,
        demands={"room": DemandState(Mode.HEAT, True, NOW)},
        guards={"room.radiator": GuardState(True, NOW)},
        overruns={"pump": NOW},
        ready={"switch.valve": LONG_AGO},
        winding=frozenset({"switch.valve", "switch.boiler"}),
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
    assert due == pytest.approx(1800.0 + TICK)
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


def test_the_desired_state_reports_each_zone_demand_with_its_level() -> None:
    plant = _plant(RADIATOR)
    _, desired, _ = run(plant, observe(plant, temperatures={"room": 20.5}))
    demand = desired.demands["room"]
    assert demand.on and demand.mode is Mode.HEAT
    assert demand.level == pytest.approx(0.5)
    _, desired, _ = run(plant, observe(plant))
    assert not desired.demands["room"].on and desired.demands["room"].level == 0.0


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
        plant, temperatures={"room": 22.0}, on=["switch.valve", "switch.pump", "switch.boiler"]
    )
    held_state, desired, due = run(plant, warm, state, NOW + 100)
    assert desired.source_request and desired.reasons["source"] == "held for its minimum on time"
    assert due == pytest.approx(120.0 + TICK), "the pump's overrun ends before the minimum on time"
    released, desired, _ = run(plant, warm, held_state, NOW + 300)
    assert not desired.source_request and released.source_changed == NOW + 300
    _, desired, _ = run(plant, running, released, NOW + 400)
    assert (
        not desired.source_request
        and desired.reasons["source"] == "held off for its minimum off time"
    )
    assert run(plant, running, released, NOW + 600)[1].source_request

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
        "condensation guard blocks: reference 18.0 °C, held for its minimum blocked time"
    )
    assert not run(plant, ready_clear, blocked, later)[0].guards["a.ceiling"].blocked

    stale = {"sensor.supply": Reading(20.0, NOW - 1801)}
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
        changed = observe(plant, mode=mode, temperatures={"room": 19.0}, on=on)
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
        RADIATOR.replace("temperature: [sensor.room]", "thermostat: {external: climate.room}")
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
