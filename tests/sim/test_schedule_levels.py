"""Schedule block levels against the simulated house: the invariants hold through edits."""

from __future__ import annotations

from dataclasses import replace

from custom_components.hydronicus.core.comfort import BlockLevel, ScheduleState
from custom_components.hydronicus.core.model import LearningMode, Mode, Plant
from custom_components.hydronicus.core.step import Observations
from custom_components.hydronicus.core.thermal import ThermalModel
from tests.sim.harness import Sim
from tests.sim.invariants import Checker
from tests.sim.test_predictive import (
    LOOP,
    SCHEDULE,
    VALVE,
    _RecoveryWorld,
    _source_less_plant,
)
from tests.sim.thermal_world import FLOOR, ThermalRoom

EVENT = 10800.0
EDIT = 1800.0


class _LevelWorld(_RecoveryWorld):
    """A helper whose active block holds 17 °C until ``EVENT``, then a higher block.

    At ``EDIT`` the owner raises the later block from 21 to 22 °C, which changes
    nothing the helper's state shows, only the week.
    """

    def __init__(self, plant: Plant, room: ThermalRoom) -> None:
        super().__init__(plant, ThermalModel(), EVENT, room)
        self.later = BlockLevel(heat_target=21.0)
        self.at(EDIT, self._edit)

    def _edit(self) -> None:
        self.later = BlockLevel(heat_target=22.0)
        self.changed()

    def observe(self) -> Observations:
        observations = super().observe()
        before = self.t < self.event
        return replace(
            observations,
            schedules={
                SCHEDULE: ScheduleState(
                    True,
                    self.wall(self.event) if before else None,
                    BlockLevel(heat_target=17.0) if before else self.later,
                    True if before else None,
                    self.later if before else BlockLevel(),
                )
            },
        )


def _level_loop() -> tuple[Sim, _LevelWorld]:
    plant = _source_less_plant(LearningMode.OFF, max_lead=7200)
    sim = Sim(plant, mode=Mode.HEAT)
    world = _LevelWorld(plant, ThermalRoom(FLOOR, 18.0))
    sim.world = world
    sim.checker = Checker(world, sim.repairs)
    return sim, world


def test_an_edited_later_block_moves_early_start_and_the_invariants_hold() -> None:
    sim, world = _level_loop()
    sim.run_until(EDIT - 1)
    comfort = sim.desired.comfort["room"]
    assert comfort.target == 17.0 and comfort.schedule_level == "target"
    assert not comfort.early_start

    # 4 K at the configured 2 K/h is two hours, the owner's whole bound.
    sim.run_until(EVENT - 7200 - 1)
    assert not sim.desired.comfort["room"].early_start
    assert not sim.is_on(VALVE)
    sim.run_until_true(
        lambda: sim.flowing(str(LOOP)), 600, "early start towards the edited level circulates"
    )
    early = sim.desired.comfort["room"]
    assert early.early_start and early.target == 22.0

    sim.run_until(EVENT + 60)
    comfort = sim.desired.comfort["room"]
    assert comfort.schedule_status == "comfort" and comfort.target == 22.0
    first_valve_on = next(t for t, on in sim.switched(VALVE) if on)
    assert EVENT - 7200 <= first_valve_on < EVENT
    assert world.room.temperature > 18.0
