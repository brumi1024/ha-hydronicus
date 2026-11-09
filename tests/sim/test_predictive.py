"""Recovery learning against independent physical dynamics and hydraulic control."""

from __future__ import annotations

from dataclasses import replace
from math import sin

import pytest

from custom_components.hydronicus.core.comfort import ScheduleState
from custom_components.hydronicus.core.model import (
    RUNS_WITH_ZONE,
    DigitalThermostat,
    LearningMode,
    Loop,
    LoopRef,
    Mode,
    Plant,
    Preset,
    Pump,
    Schedule,
    Sensor,
    Valve,
    Zone,
)
from custom_components.hydronicus.core.step import DigitalThermostatState, Observations
from custom_components.hydronicus.core.thermal import (
    RecoveryEpisode,
    RecoveryEstimate,
    ThermalModel,
    estimate,
    record_episode,
)
from tests.sim.harness import Sim
from tests.sim.invariants import Checker
from tests.sim.thermal_world import (
    FLOOR,
    RADIATOR,
    AutonomousWaterRoom,
    ThermalFabric,
    ThermalRoom,
)
from tests.sim.world import WALL_BASE, World

DAY = 86400.0
TARGET = 21.0
CONFIGURED_RATE = 2.0


def _training_history(fabric: ThermalFabric) -> ThermalModel:
    """Observe separate daily recoveries with varied starts and modest disturbances."""
    model = ThermalModel()
    for day in range(16):
        deficit = (0.5, 1.0, 1.5, 2.0)[day % 4]
        outdoor = 7.0 + 0.8 * sin(day * 1.9)
        room = ThermalRoom(
            fabric,
            TARGET - deficit,
            outdoor=outdoor,
            passive_gain=0.25 + 0.04 * sin(day * 2.3),
        )
        elapsed = room.recover(TARGET)
        assert elapsed is not None, "the independent physical room must actually recover"
        start = WALL_BASE + day * DAY
        prediction = estimate(model, Mode.HEAT, deficit, start)
        episode = RecoveryEpisode(
            Mode.HEAT,
            start,
            start + elapsed,
            deficit,
            "reached",
            outdoor_temperature=outdoor,
            predicted_seconds=prediction.seconds,
        )
        model = record_episode(model, episode, start + elapsed)
    return model


@pytest.mark.parametrize("fabric", [FLOOR, RADIATOR], ids=["slow-floor", "faster-radiator"])
def test_learned_recovery_beats_configured_rate_on_independent_thermal_physics(
    fabric: ThermalFabric,
) -> None:
    model = _training_history(fabric)
    # This deficit was absent from training. Its actual recovery is held out too.
    deficit = 1.25
    prediction = estimate(model, Mode.HEAT, deficit, WALL_BASE + 16 * DAY)
    assert prediction.confidence, prediction.reason
    assert prediction.seconds is not None
    assert prediction.validation_count >= 3
    actual = ThermalRoom(fabric, TARGET - deficit, outdoor=7.3, passive_gain=0.23).recover(TARGET)
    assert actual is not None
    configured = 3600 * deficit / CONFIGURED_RATE
    assert abs(prediction.seconds - actual) < abs(configured - actual) * 0.5
    assert abs(prediction.seconds - actual) < actual * 0.15
    if fabric is FLOOR:
        assert prediction.startup_delay_seconds is not None
        assert prediction.startup_delay_seconds > 15 * 60


def test_pump_flow_without_heat_fails_recovery_and_withdraws_learned_confidence() -> None:
    model = _training_history(FLOOR)
    start = WALL_BASE + 16 * DAY
    assert estimate(model, Mode.HEAT, 1.0, start).confidence
    room = ThermalRoom(FLOOR, TARGET - 1.0)
    room.heat_available = False
    assert room.recover(TARGET, limit=6 * 3600) is None
    assert room.delivered_energy == 0
    assert room.temperature < TARGET - 1.0
    episode = RecoveryEpisode(
        Mode.HEAT,
        start,
        start + room.t,
        1.0,
        "failed",
        reason="circulation did not establish comfort",
    )
    model = record_episode(model, episode, episode.ended_at)
    prediction = estimate(model, Mode.HEAT, 1.0, episode.ended_at)
    assert not prediction.confidence
    assert "failed" in prediction.reason


def test_weather_conditioned_estimates_improve_independent_cold_and_mild_recoveries() -> None:
    model = ThermalModel()
    # Two outdoor regimes contain independent repetitions of every starting
    # deficit. The simulator's heat loss, rather than the learner, creates the
    # longer cold-weather recovery and the shorter mild-weather recovery.
    for day in range(28):
        outdoor = (-5.0, 15.0)[day % 2]
        deficit = (0.5, 1.0, 1.5, 2.0)[(day // 2) % 4]
        room = ThermalRoom(FLOOR, TARGET - deficit, outdoor=outdoor)
        elapsed = room.recover(TARGET)
        assert elapsed is not None
        start = WALL_BASE + day * DAY
        model = record_episode(
            model,
            RecoveryEpisode(Mode.HEAT, start, start + elapsed, deficit, "reached", outdoor),
            start + elapsed,
        )
    now = WALL_BASE + 28 * DAY
    baseline = estimate(model, Mode.HEAT, 1.25, now)
    assert baseline.seconds is not None
    for outdoor in (-5.0, 15.0):
        prediction = estimate(model, Mode.HEAT, 1.25, now, outdoor)
        actual = ThermalRoom(FLOOR, TARGET - 1.25, outdoor=outdoor).recover(TARGET)
        assert actual is not None
        assert prediction.confidence, prediction.reason
        assert prediction.weather_adjusted
        assert prediction.seconds is not None
        assert abs(prediction.seconds - actual) < abs(baseline.seconds - actual) * 0.25
        assert abs(prediction.seconds - actual) < 300
    # There is no historical support for an extremely cold forecast. It must
    # not manufacture a high-confidence weather prediction by extrapolation.
    unsupported = estimate(model, Mode.HEAT, 1.25, now, -25)
    assert not unsupported.weather_adjusted
    assert unsupported.seconds == baseline.seconds


def test_emitter_stores_heat_and_room_continues_warming_after_circulation_stops() -> None:
    room = ThermalRoom(FLOOR, 19.5)
    room.advance(480.0, circulating=True)
    assert room.delivered_energy == 0, "the transport delay precedes heat delivery"
    room.advance(7200.0, circulating=True)
    before = room.temperature
    delivered = room.delivered_energy
    room.advance(600.0, circulating=False)
    assert room.delivered_energy == delivered
    assert room.temperature > before, "the warm floor keeps releasing stored energy"


PUMP = "switch.heating_pump"
VALVE = "switch.floor_valve"
TEMPERATURE = "sensor.room_temperature"
WINDOW = "binary_sensor.room_window"
SCHEDULE = "schedule.room"
LOOP = LoopRef("room", "floor")


def _source_less_plant(learning: LearningMode, *, max_lead: float = 7200) -> Plant:
    return Plant(
        "thermal-house",
        "Thermal house",
        pumps=(Pump("heating", PUMP, overrun=60),),
        zones=(
            Zone(
                "room",
                loops=(
                    Loop(
                        LOOP,
                        (Valve(VALVE, 120),),
                        "heating",
                        frozenset({Mode.HEAT}),
                        RUNS_WITH_ZONE,
                    ),
                ),
                temperature=(Sensor(TEMPERATURE, required=True),),
                windows=(WINDOW,),
                thermostat=DigitalThermostat(
                    min_on=60,
                    min_off=60,
                    schedule=Schedule(
                        SCHEDULE,
                        heat_setback=4,
                        max_early_start=max_lead,
                        heating_rate=CONFIGURED_RATE,
                    ),
                    learning=learning,
                ),
            ),
        ),
        exercise=None,
    )


class _RecoveryWorld(World):
    """Physical hydraulics plus the independent room, with explicit planning inputs."""

    def __init__(
        self, plant: Plant, model: ThermalModel, event: float, room: ThermalRoom | None = None
    ) -> None:
        super().__init__(plant)
        self.wall_offset = 16 * DAY
        self.room = room or ThermalRoom(FLOOR, 20.0)
        self.model = model
        self.event = event
        self.prediction_override: RecoveryEstimate | None = None
        self.mode = Mode.HEAT
        self.control = True
        self.armed = frozenset(plant.outputs())
        self.set_thermostat("room", DigitalThermostatState(Mode.HEAT, TARGET, Preset.SCHEDULE))
        self.set_sensor(TEMPERATURE, self.room.measured_temperature)
        self.at(60.0, self._report)
        self.at(event, self.changed)

    def _report(self) -> None:
        self.set_sensor(TEMPERATURE, self.room.measured_temperature)
        self.at(self.t + 60, self._report)

    def advance_to(self, t: float) -> None:
        # Split integration at every actuator event, so actual physical flow,
        # rather than either a requested output or coarse sampling, heats the room.
        while (event := self.next_time()) is not None and event <= t:
            self.room.advance(
                max(0.0, event - self.t), circulating=self.flowing(self.plant.loop(LOOP))
            )
            super().advance_to(event)
        self.room.advance(max(0.0, t - self.t), circulating=self.flowing(self.plant.loop(LOOP)))
        super().advance_to(t)

    def observe(self) -> Observations:
        observations = super().observe()
        thermostat = self.thermostats["room"]
        assert isinstance(thermostat, DigitalThermostatState)
        prediction = self.prediction_override or estimate(
            self.model,
            Mode.HEAT,
            thermostat.target - self.room.measured_temperature,
            self.wall(),
        )
        return replace(
            observations,
            schedules={
                SCHEDULE: ScheduleState(self.t >= self.event, self.wall(self.event)),
            },
            recovery={"room": prediction},
        )


def _closed_loop(
    learning: LearningMode = LearningMode.ASSIST,
    *,
    model: ThermalModel | None = None,
    event: float = 10800,
    max_lead: float = 7200,
    room: ThermalRoom | None = None,
) -> tuple[Sim, _RecoveryWorld]:
    plant = _source_less_plant(learning, max_lead=max_lead)
    sim = Sim(plant, mode=Mode.HEAT)
    world = _RecoveryWorld(plant, model or _training_history(FLOOR), event, room)
    sim.world = world
    sim.checker = Checker(world, sim.repairs)
    return sim, world


def test_recovery_includes_autonomous_source_start_after_return_water_cools() -> None:
    model = ThermalModel()
    for day in range(16):
        deficit = (0.5, 1.0, 1.5, 2.0)[day % 4]
        room = AutonomousWaterRoom(FLOOR, TARGET - deficit)
        elapsed = room.recover(TARGET)
        assert elapsed is not None
        # Timing starts when circulation is possible, before the water-side
        # controller starts its source. None of this wait is removed from learning.
        start = WALL_BASE + day * DAY
        model = record_episode(
            model,
            RecoveryEpisode(Mode.HEAT, start, start + elapsed, deficit, "reached"),
            start + elapsed,
        )
    prediction = estimate(model, Mode.HEAT, 1.25, WALL_BASE + 16 * DAY)
    assert prediction.confidence, prediction.reason
    assert prediction.seconds is not None

    room = AutonomousWaterRoom(FLOOR, TARGET - 1.25)
    sim, world = _closed_loop(model=model, event=0, room=room)
    circuit_ready = sim.run_until_true(
        lambda: sim.flowing(str(LOOP)), 180, "valve and pump establish circulation"
    )
    sim.run_for(300)
    assert not room.heat_available
    assert room.delivered_energy == 0
    assert not room.source_transitions
    sim.run_until_true(
        lambda: room.heat_available, 1800, "return water starts the autonomous source"
    )
    source_started, running, return_temperature = room.source_transitions[0]
    assert running
    assert return_temperature <= room.START_RETURN
    assert source_started - circuit_ready > 600

    reached = sim.run_until_true(
        lambda: room.measured_temperature >= TARGET, 12 * 3600, "the room reaches comfort"
    )
    elapsed = reached - circuit_ready
    assert abs(prediction.seconds - elapsed) < elapsed * 0.1
    always_available = ThermalRoom(FLOOR, TARGET - 1.25).recover(TARGET)
    assert always_available is not None
    assert prediction.seconds > always_available + 1800
    assert len(room.source_transitions) >= 3, "the water controller cycles autonomously"
    for _, running, temperature in room.source_transitions:
        assert temperature <= room.START_RETURN if running else temperature >= room.STOP_RETURN
    assert {call.entity for call in world.calls} == {PUMP, VALVE}
    assert not sim.desired.source_request
    assert sim.plant.source is None


def test_learned_schedule_recovers_source_less_house_earlier_than_configured_rate() -> None:
    assisted, world = _closed_loop()
    fixed, fixed_world = _closed_loop(LearningMode.OBSERVE)
    assisted.run_until(world.event)
    fixed.run_until(fixed_world.event)
    assert world.room.temperature > fixed_world.room.temperature + 0.5
    assert abs(world.room.temperature - TARGET) < 0.3
    first_valve_on = next(t for t, on in assisted.switched(VALVE) if on)
    assert first_valve_on >= world.event - 7200
    assert first_valve_on < next(t for t, on in fixed.switched(VALVE) if on)
    assert {call.entity for call in world.calls} == {PUMP, VALVE}
    assert assisted.plant.source is None
    assert not assisted.desired.source_request
    assert assisted.desired.comfort["room"].schedule_status == "comfort"


def test_observation_mode_keeps_the_same_physical_control_as_configured_recovery() -> None:
    observed, world = _closed_loop(LearningMode.OBSERVE)
    configured, configured_world = _closed_loop(LearningMode.OFF, model=ThermalModel())
    observed.run_until(world.event)
    configured.run_until(configured_world.event)
    assert world.switch_log == configured_world.switch_log
    assert world.room.temperature == configured_world.room.temperature


def test_early_recovery_survives_restart_and_manual_target_immediately_exits_schedule() -> None:
    sim, world = _closed_loop()
    sim.run_until_true(
        lambda: sim.flowing(str(LOOP)), 10800, "learned early recovery starts circulation"
    )
    assert sim.desired.comfort["room"].early_start
    assert sim.restart() == []
    assert sim.desired.comfort["room"].early_start
    sim.set_target("room", 18.0)
    sim.run_for(300)
    assert not sim.pump_running("heating")
    assert not sim.is_on(VALVE)
    assert sim.desired.comfort["room"].schedule_status == "manual"
    assert not sim.desired.comfort["room"].early_start
    assert sim.state.demands["room"].early_start_event is None
    assert not world.requested


def test_learned_recovery_cannot_exceed_owner_early_start_bound() -> None:
    sim, world = _closed_loop(event=3600, max_lead=900)
    world.prediction_override = RecoveryEstimate(
        8 * 3600,
        True,
        "ready",
        "synthetic long recovery prediction",
        valid_until=world.wall() + DAY,
    )
    sim.run_until(2699)
    assert not world.calls
    sim.run_until(2850)
    assert sim.pump_running("heating")
    assert all(call.t >= 2700 for call in world.calls)


@pytest.mark.parametrize("blocker", ["window", "sensor", "dry-run", "unarmed"])
def test_predictive_early_start_preserves_existing_safety_gates(blocker: str) -> None:
    sim, world = _closed_loop(event=900, max_lead=900)
    if blocker == "window":
        sim.set_contact(WINDOW, True)
    elif blocker == "sensor":
        sim.set_sensor_available(TEMPERATURE, False)
    elif blocker == "dry-run":
        sim.set_control(False)
    else:
        sim.set_armed([])
    sim.run_for(1800)
    assert not sim.pump_running("heating")
    assert world.room.delivered_energy == 0
    if blocker in ("dry-run", "unarmed"):
        assert not world.calls
