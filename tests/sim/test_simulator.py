"""The simulator itself: physics, service calls, persistence, and the invariant checks.

These pass against the stub ``step()``. The checks are exercised with a scripted
controller that sends exactly the calls a test gives it, so each invariant is
shown to catch the violation it names.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace

import pytest
from hydronicus_core.model import (
    Desired,
    Mode,
    OptionTarget,
    OutputTarget,
    Plant,
    SwitchTarget,
    ValueTarget,
)
from hydronicus_core.reconcile import (
    CALL_TIMEOUT,
    Action,
    Attempt,
    Reconciled,
    ReconcileState,
    dry_run_view,
)
from hydronicus_core.step import (
    DemandState,
    GuardState,
    Observations,
    OptionState,
    OutputState,
    State,
    SwitchState,
    ValueState,
)

from tests.sim import harness
from tests.sim.harness import Sim
from tests.sim.invariants import InvariantViolation, dew_point
from tests.sim.plants import BOILER, SMALL, TWO_CEILINGS, plant, reference_plant
from tests.sim.world import LATENCY, Fault, FaultKind, Outcome, World

ON = SwitchTarget(True)
OFF = SwitchTarget(False)


# The physical world under direct calls


def _world(text: str = SMALL) -> World:
    world = World(plant(text))
    world.armed = frozenset(world.plant.outputs())
    return world


def _send(world: World, entity: str, target: OutputTarget) -> None:
    world.dispatch(Action(entity, target))


def test_a_valve_passes_flow_only_once_fully_open_and_until_fully_closed() -> None:
    world = _world()
    valve = "switch.room_floor_valve"
    _send(world, valve, ON)
    world.advance_to(LATENCY)
    assert world.is_on(valve)
    world.advance_to(LATENCY + 179.0)
    assert not world.valve_passes(valve)
    world.advance_to(LATENCY + 180.0)
    assert world.valve_passes(valve)

    _send(world, valve, OFF)
    world.advance_to(world.t + LATENCY + 90.0)
    assert not world.is_on(valve)
    assert world.valve_passes(valve), "a closing valve passes flow until fully closed"
    assert world.valves[valve].position(world.t) == pytest.approx(0.5)

    # Reversing halfway keeps it passing and opens it fully in half the travel.
    _send(world, valve, ON)
    world.advance_to(world.t + LATENCY + 89.0)
    assert world.valve_passes(valve)
    assert world.valves[valve].position(world.t) == pytest.approx(1.0 - 1.5 / 180.0)
    world.advance_to(world.t + 1.5)
    assert world.valves[valve].fully_open

    _send(world, valve, OFF)
    world.advance_to(world.t + LATENCY + 180.0)
    assert not world.valve_passes(valve)


def test_a_readiness_sensor_confirms_a_fully_open_valve() -> None:
    world = _world()
    valve, readiness = "switch.room_ceiling_valve", "binary_sensor.room_ceiling_open"
    _send(world, valve, ON)
    world.advance_to(LATENCY + 59.0)
    assert world.observe().readiness[readiness].on is False
    world.advance_to(LATENCY + 60.0)
    observed = world.observe().readiness[readiness]
    assert observed.on is True
    assert observed.since == pytest.approx(world.wall(LATENCY + 60.0))
    _send(world, valve, OFF)
    world.advance_to(world.t + LATENCY)
    assert world.observe().readiness[readiness].on is False


def test_pumps_run_when_switched_or_with_the_source_and_its_post_run() -> None:
    world = _world()
    plant_ = world.plant
    floor, primary = plant_.pump("floor"), plant_.pump("primary")
    _send(world, "switch.floor_pump", ON)
    _send(world, "switch.source_request", ON)
    world.advance_to(LATENCY)
    assert world.pump_running(floor)
    assert world.pump_running(primary)
    assert world.requested

    _send(world, "switch.source_request", OFF)
    world.advance_to(world.t + LATENCY)
    assert not world.requested
    assert world.post_running
    world.advance_to(world.t + 119.0)
    assert world.pump_running(primary)
    world.advance_to(world.t + 1.0)
    assert not world.pump_running(primary)
    assert world.pump_running(floor)


def test_calls_are_delayed_rejected_timed_out_and_dropped() -> None:
    world = _world()
    world.faults.append(_fault("switch.floor_pump", FaultKind.REJECT))
    world.faults.append(_fault("switch.room_floor_valve", FaultKind.TIMEOUT))
    world.faults.append(_fault("switch.source_request", FaultKind.DELAY, delay=8.0))
    _send(world, "switch.floor_pump", ON)
    _send(world, "switch.room_floor_valve", ON)
    _send(world, "switch.source_request", ON)
    # A later call to the same entity acts after the delayed one, never before.
    _send(world, "switch.source_request", OFF)
    world.advance_to(CALL_TIMEOUT)
    outcomes = [call.outcome for call in world.calls]
    assert outcomes == [Outcome.REJECTED, Outcome.TIMED_OUT, Outcome.LANDED, Outcome.LANDED]
    assert [call.lands_at for call in world.calls[2:]] == [8.0, 8.0]
    assert world.switched("switch.source_request") == [(8.0, True), (8.0, False)]
    assert not world.is_on("switch.floor_pump")
    assert not world.is_on("switch.room_floor_valve")

    world.set_available("switch.room_floor_valve", False)
    world.faults.clear()
    _send(world, "switch.room_floor_valve", ON)
    assert world.calls[-1].outcome is Outcome.REJECTED
    assert world.observe().outputs["switch.room_floor_valve"] == SwitchState(None, world.wall())


def test_sensors_go_stale_and_come_back() -> None:
    world = _world()
    world.advance_to(100.0)
    world.set_sensor_state("sensor.room_temperature", stale=True)
    world.advance_to(200.0)
    world.set_sensor("sensor.room_temperature", 25.0)
    stale = world.reading("sensor.room_temperature")
    assert stale.value == 21.0
    assert stale.updated == world.wall(100.0)
    world.set_sensor_state("sensor.room_temperature", stale=False)
    assert world.reading("sensor.room_temperature").value == 25.0
    assert world.reading("sensor.room_temperature").updated == world.wall()


def _fault(entity: str, kind: FaultKind, delay: float = 0.0) -> Fault:
    return Fault(entity, 0.0, 1000.0, kind, delay)


# The runtime loop and persistence


def test_the_stub_runs_under_the_harness_and_persists_json() -> None:
    sim = Sim(reference_plant(), mode=Mode.HEAT)
    sim.run_for(60.0)
    evaluations = sim.evaluations
    sim.set_zone_temperature("living_area", 19.0)
    sim.run_for(1.0)
    assert sim.evaluations == evaluations + 1, "a change of observation triggers one evaluation"
    assert State.from_dict(json.loads(sim.store["state"])) == sim.state
    assert sim.restart() == []
    assert sim.world.calls == []


def test_step_and_reconcile_states_round_trip_through_json() -> None:
    state = State(
        live=True,
        mode=Mode.COOL,
        last_mode=Mode.HEAT,
        last_mode_ended=12.5,
        source_request=True,
        source_changed=10.0,
        demands={"living_area": DemandState(True, 3.0)},
        guards={"living_area.ceiling": GuardState(False, 4.0)},
        overruns={"floor": 5.0},
    )
    assert State.from_dict(json.loads(json.dumps(state.to_dict()))) == state
    assert State.from_dict({}) == State()
    dry: Mapping[str, OutputState] = {
        "switch.a": SwitchState(True, 1.0),
        "switch.b": SwitchState(None, 2.0),
        "select.c": OptionState("Heat", 3.0),
        "select.d": OptionState(None, 3.5),
        "number.e": ValueState(35.0, 4.0),
        "number.f": ValueState(None, 5.0),
    }
    reconciled = ReconcileState(
        attempts={
            "switch.a": Attempt(ON, 2, 6.0),
            "select.c": Attempt(OptionTarget("Cool"), 1, 7.0),
            "number.e": Attempt(ValueTarget(35.0), 1, 8.0),
        },
        dry_run=dry,
    )
    assert ReconcileState.from_dict(json.loads(json.dumps(reconciled.to_dict()))) == reconciled
    assert ReconcileState.from_dict({}) == ReconcileState()


def test_dry_run_view_shows_proposed_outputs_only_while_control_is_off() -> None:
    real = SwitchState(False, 1.0)
    proposed = SwitchState(True, 2.0)
    observations = Observations(
        mode=Mode.HEAT, control=False, armed=frozenset(), outputs={"switch.a": real}
    )
    state = ReconcileState(dry_run={"switch.a": proposed})
    assert dry_run_view(observations, state).outputs["switch.a"] == proposed
    live = replace(observations, control=True)
    assert dry_run_view(live, state) is live
    assert dry_run_view(observations, ReconcileState()) is observations


# The invariant checks, driven by a scripted controller


@dataclass
class Scripted:
    """A controller that sends what a test queues and declares ``mode``."""

    mode: Mode = Mode.HEAT
    live: bool = True
    outputs: dict[str, OutputTarget] = field(default_factory=dict)
    pending: list[Action] = field(default_factory=list)
    repairs: frozenset[str] = frozenset()

    def step(
        self, plant: Plant, observations: Observations, state: State, now: float
    ) -> tuple[State, Desired, float | None]:
        desired = Desired(
            outputs=dict(self.outputs),
            source_request=False,
            mode=self.mode,
            flow_setpoint=None,
            reasons={},
        )
        return replace(state, live=self.live), desired, None

    def reconcile(
        self,
        plant: Plant,
        desired: Desired,
        outputs: Mapping[str, OutputState],
        state: ReconcileState,
        now: float,
        *,
        armed: frozenset[str],
        live: bool,
    ) -> Reconciled:
        send, self.pending = tuple(self.pending), []
        return Reconciled(state=state, send=send, repairs=self.repairs)

    def send(self, sim: Sim, entity: str, target: OutputTarget) -> None:
        self.pending.append(Action(entity, target))
        sim.world.changed()


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch) -> Iterator[Scripted]:
    controller = Scripted()
    monkeypatch.setattr(harness, "step", controller.step)
    monkeypatch.setattr(harness, "reconcile", controller.reconcile)
    yield controller


def _violation(number: int | str) -> pytest.RaisesExc[InvariantViolation]:
    return pytest.raises(InvariantViolation, match=f"^Invariant {number} ")


def test_invariant_1_catches_a_call_to_an_unarmed_output(scripted: Scripted) -> None:
    sim = Sim(plant(SMALL), mode=Mode.HEAT, armed=["switch.room_floor_valve"])
    sim.start()
    scripted.send(sim, "switch.floor_pump", ON)
    with _violation(1):
        sim.run_for(1.0)


def test_invariant_1_catches_a_call_in_dry_run(scripted: Scripted) -> None:
    sim = Sim(plant(SMALL), mode=Mode.HEAT, control=False)
    sim.start()
    scripted.send(sim, "switch.room_floor_valve", ON)
    with _violation(1):
        sim.run_for(1.0)


def test_invariant_1_allows_the_off_sequence_after_control_turns_off(scripted: Scripted) -> None:
    sim = Sim(plant(SMALL), mode=Mode.HEAT)
    sim.seed_running("room.floor")
    sim.start()
    sim.set_control(False)
    scripted.send(sim, "switch.floor_pump", OFF)
    sim.run_for(1.0)
    scripted.send(sim, "switch.room_floor_valve", OFF)
    sim.run_for(1.0)
    assert sim.checker.dry
    scripted.send(sim, "switch.room_floor_valve", OFF)
    with _violation(1):
        sim.run_for(1.0)


def test_invariant_2_catches_a_pump_started_before_its_valve_is_open(scripted: Scripted) -> None:
    sim = Sim(plant(SMALL), mode=Mode.HEAT)
    sim.start()
    scripted.send(sim, "switch.room_floor_valve", ON)
    sim.run_for(1.0)
    scripted.send(sim, "switch.floor_pump", ON)
    with _violation(2):
        sim.run_for(1.0)


def test_invariant_2_catches_a_valve_closed_under_a_running_pump(scripted: Scripted) -> None:
    sim = Sim(plant(SMALL), mode=Mode.HEAT)
    sim.seed_running("room.floor")
    sim.start()
    scripted.send(sim, "switch.room_floor_valve", OFF)
    sim.run_for(180.0)
    with _violation(2):
        sim.run_for(1.0)


def test_invariant_4_catches_a_post_run_without_a_path(scripted: Scripted) -> None:
    sim = Sim(plant(SMALL), mode=Mode.HEAT)
    sim.seed_running("room.ceiling")
    sim.seed_on("switch.source_request")
    sim.start()
    scripted.send(sim, "switch.source_request", OFF)
    sim.run_for(1.0)
    scripted.send(sim, "switch.room_ceiling_valve", OFF)
    sim.run_for(60.0)
    with _violation(4):
        sim.run_for(1.0)


def test_invariant_3_catches_a_request_without_a_running_pump(scripted: Scripted) -> None:
    sim = Sim(plant(BOILER), mode=Mode.HEAT)
    sim.seed_on("switch.flat_radiator_valve")
    sim.start()
    scripted.send(sim, "switch.boiler_request", ON)
    with _violation(3):
        sim.run_for(1.0)


def test_invariant_3_exempts_a_spontaneous_change_for_one_reaction(scripted: Scripted) -> None:
    sim = Sim(plant(BOILER), mode=Mode.HEAT)
    sim.seed_running("flat.radiators")
    sim.seed_on("switch.boiler_request")
    sim.start()
    sim.spontaneous_off("switch.circulator_pump")
    sim.run_for(15.0)
    with _violation(3):
        sim.run_for(10.0)


def test_invariant_5_catches_cooling_while_heating_flows(scripted: Scripted) -> None:
    sim = Sim(plant(TWO_CEILINGS), mode=Mode.HEAT)
    sim.seed_running("office.ceiling")
    sim.start()
    scripted.mode = Mode.COOL
    scripted.send(sim, "switch.den_ceiling_valve", ON)
    sim.run_for(181.0)
    scripted.send(sim, "switch.den_pump", ON)
    with _violation(5):
        sim.run_for(1.0)


def test_invariant_5_catches_a_mode_change_inside_the_dwell(scripted: Scripted) -> None:
    sim = Sim(plant(TWO_CEILINGS), mode=Mode.HEAT)
    sim.seed_running("office.ceiling")
    sim.start()
    scripted.send(sim, "switch.office_pump", OFF)
    sim.run_for(1.0)
    scripted.mode = Mode.COOL
    sim.run_for(3000.0)
    scripted.send(sim, "switch.office_pump", ON)
    with _violation(5):
        sim.run_for(1.0)


def test_invariant_6_catches_cooling_on_after_the_guard_blocks(scripted: Scripted) -> None:
    sim = Sim(plant(TWO_CEILINGS), mode=Mode.COOL)
    for zone in ("office", "den"):
        sim.seed_running(f"{zone}.ceiling")
        sim.set_zone_temperature(zone, 26.0)
        sim.set_sensor(f"sensor.{zone}_supply", 18.0)
    sim.start()
    sim.run_for(60.0)
    sim.set_sensor("sensor.office_supply", 15.0)
    sim.run_for(191.0)
    with _violation(6):
        sim.run_for(1.0)


def test_invariant_7_catches_an_unreported_failure(scripted: Scripted) -> None:
    sim = _failing_circulator(scripted)
    sim.run_for(49.0)
    with _violation(7):
        sim.run_for(1.0)


def test_invariant_7_accepts_a_reported_failure(scripted: Scripted) -> None:
    scripted.repairs = frozenset({"switch.circulator_pump"})
    sim = _failing_circulator(scripted)
    sim.run_for(600.0)


def _failing_circulator(controller: Scripted) -> Sim:
    """Three rejected calls to stop the circulator, the last one 10 s before the end."""
    sim = Sim(plant(BOILER), mode=Mode.HEAT)
    sim.seed_running("flat.radiators")
    controller.outputs = {"switch.circulator_pump": OFF}
    sim.start()
    sim.fault("switch.circulator_pump", FaultKind.REJECT, 1000.0)
    for _ in range(3):
        controller.send(sim, "switch.circulator_pump", OFF)
        sim.run_for(10.0)
    return sim


def test_invariant_7_catches_a_difference_left_after_settling(scripted: Scripted) -> None:
    sim = Sim(plant(BOILER), mode=Mode.HEAT)
    sim.seed_running("flat.radiators")
    scripted.outputs = {"switch.circulator_pump": OFF}
    with _violation(7):
        sim.settle(10.0)


def test_invariant_8_catches_a_restart_that_sends(scripted: Scripted) -> None:
    sim = Sim(plant(BOILER), mode=Mode.HEAT)
    sim.start()
    sim.run_for(10.0)
    scripted.pending.append(Action("switch.flat_radiator_valve", ON))
    with _violation(8):
        sim.restart()


def test_progress_catches_a_demanding_zone_left_cold() -> None:
    sim = Sim(plant(BOILER), mode=Mode.HEAT)
    sim.set_zone_temperature("flat", 19.0)
    with pytest.raises(InvariantViolation, match="^Invariant progress "):
        sim.settle(60.0)


def test_a_correct_sequence_passes_every_check(scripted: Scripted) -> None:
    """Heat, stop, wait out the dwell, and cool with a guard block, without a violation."""
    sim = Sim(plant(SMALL), mode=Mode.HEAT)
    sim.set_zone_temperature("room", 26.0)
    sim.set_sensor("sensor.floor_supply", 18.0)
    valves = ("switch.room_ceiling_valve", "switch.room_floor_valve")
    scripted.outputs = {entity: ON for entity in (*valves, "switch.floor_pump")}
    sim.start()
    for valve in valves:
        scripted.send(sim, valve, ON)
    sim.run_for(181.0)
    scripted.send(sim, "switch.floor_pump", ON)
    scripted.send(sim, "switch.source_request", ON)
    sim.run_for(600.0)
    assert {str(ref) for ref in sim.checker.flows} == {"room.ceiling", "room.floor"}

    # Stop: the source first, then the switched pump, then its valve; the
    # source-driven pump keeps its path through the post-run.
    scripted.outputs = {}
    scripted.send(sim, "switch.source_request", OFF)
    sim.run_for(1.0)
    scripted.send(sim, "switch.floor_pump", OFF)
    sim.run_for(1.0)
    scripted.send(sim, "switch.room_floor_valve", OFF)
    sim.run_for(120.0)
    assert not sim.pump_running("primary")
    scripted.send(sim, "switch.room_ceiling_valve", OFF)
    sim.run_for(200.0)
    assert not sim.checker.flows
    heat_ended = max(flow.end or 0.0 for flow in sim.checker.flow_log)

    # Cool on the floor loop once the dwell has passed, then block its guard.
    scripted.mode = Mode.COOL
    sim.set_mode(Mode.COOL)
    sim.run_until(heat_ended + sim.plant.mode_dwell)
    scripted.send(sim, "switch.room_floor_valve", ON)
    sim.run_for(181.0)
    scripted.send(sim, "switch.floor_pump", ON)
    sim.run_for(60.0)
    assert sim.flowing("room.floor")
    sim.set_sensor("sensor.floor_supply", 15.0)
    sim.run_for(1.0)
    scripted.send(sim, "switch.floor_pump", OFF)
    sim.run_for(1.0)
    scripted.send(sim, "switch.room_floor_valve", OFF)
    sim.run_for(600.0)
    sim.settle(60.0)


def test_the_dew_point_matches_the_magnus_formula() -> None:
    point = dew_point(26.0, 50.0)
    assert point == pytest.approx(14.77, abs=0.01)
    assert dew_point(20.0, 0.0) is None
