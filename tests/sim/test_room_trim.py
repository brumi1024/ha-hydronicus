"""The room trim against a slow room: a floor heated through a curve that is set off.

The room is first order with a time constant of about six hours, behind a screed
that takes about an hour and a half to warm, and it loses heat to a steady 2 °C
outdoors. Its heat comes only while the floor loop flows and the heat pump is
requested, at the supply setpoint Hydronicus writes in whole degrees. At its
target of 21 °C the room needs exactly what the curve's line gives at 2 °C,
37 °C, so a line shifted down by some kelvin leaves a steady shortfall that the
room trim has to find and remove, without overshooting, without oscillating,
and with few setpoint writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import pytest

from custom_components.hydronicus.core.model import Mode
from tests.sim.harness import Sim
from tests.sim.plants import plant

DAY: Final = 86400.0
STEP: Final = 60.0
TARGET: Final = 21.0
OUTDOOR: Final = 2.0
SUPPLY: Final = "number.slow_supply"
REQUEST: Final = "switch.slow_heat_pump"
ROOM: Final = "sensor.slow_floor_temperature"

# Conductances in kW/K and capacities in kJ/K: water to screed, screed to room,
# and room to outdoors, chosen so the room at 21 °C needs 37 °C water at 2 °C.
WATER: Final = 0.4
SCREED: Final = 0.6
SERIES: Final = 1 / (1 / WATER + 1 / SCREED)
LOSS: Final = SERIES * (37.0 - TARGET) / (TARGET - OUTDOOR)
SCREED_CAPACITY: Final = 5400.0
ROOM_CAPACITY: Final = 17280.0


def slow_plant(low: float, learn_rate: float = 0.3) -> str:
    """A heat pump on Hydronicus's curve, its line ``low`` kelvin below what the room needs."""
    return f"""
hydronicus: 2
name: Slow
source:
  request: {REQUEST}
  post_run: 0
  min_on: 0
  min_off: 0
  supply:
    entity: {SUPPLY}
    outdoor_sensor: sensor.slow_outdoor
    step: 1
    minimum: 20
    maximum: 50
    heat_cold: {45 - low}
    heat_warm: {25 - low}
    room_influence: {{zones: [floor], learn_rate: {learn_rate}}}
pumps:
  floor: {{switch: switch.slow_floor_pump, overrun: 0}}
zones:
  floor:
    temperature: [{ROOM}]
    thermostat: {{digital: {{target: {TARGET}}}}}
    loops:
      screed: {{valves: [switch.slow_floor_valve], pump: floor}}
"""


@dataclass
class SlowRoom:
    """The room and its screed, advanced every minute from what the Plant does."""

    sim: Sim
    room: float = 20.0
    screed: float = 20.0
    # Heat the sun adds to the room from 11:00 to 15:00, in kW.
    gain: float = 0.0
    log: list[tuple[float, float, float]] = field(default_factory=list)

    def advance(self) -> None:
        world = self.sim.world
        heating = world.requested and self.sim.flowing("floor.screed")
        water = WATER * (world.number(SUPPLY) - self.screed) if heating else 0.0
        released = SCREED * (self.screed - self.room)
        sun = self.gain if 11 <= (self.sim.t % DAY) / 3600 < 15 else 0.0
        self.screed += STEP * (water - released) / SCREED_CAPACITY
        self.room += STEP * (released + sun - LOSS * (self.room - OUTDOOR)) / ROOM_CAPACITY
        self.sim.set_sensor(ROOM, round(self.room, 2))
        self.log.append((self.sim.t, self.room, world.number(SUPPLY)))
        self.sim.schedule(self.sim.t + STEP, self.advance)


def heat(
    low: float,
    days: float,
    learn_rate: float = 0.3,
    *,
    start: tuple[float, float] = (20.0, 20.0),
    gain: float = 0.0,
    setback: float = 0.0,
) -> tuple[Sim, SlowRoom]:
    """Heat the slow room for ``days`` from ``start``, the room's and the screed's temperature.

    ``gain`` is the sun's daily heat, and ``setback`` lowers the target from 22:00 to 06:00.
    """
    sim = Sim(plant(slow_plant(low, learn_rate)), mode=Mode.HEAT)
    sim.world.seed_number(SUPPLY, 30.0)
    sim.set_sensor("sensor.slow_outdoor", OUTDOOR)
    room = SlowRoom(sim, *start, gain=gain)
    sim.set_sensor(ROOM, room.room)
    sim.start()
    sim.schedule(STEP, room.advance)
    if setback:
        for day in range(int(days) + 1):
            sim.schedule(day * DAY + 22 * 3600, lambda: sim.set_target("floor", TARGET - setback))
            sim.schedule((day + 1) * DAY + 6 * 3600, lambda: sim.set_target("floor", TARGET))
    sim.run_for(days * DAY)
    return sim, room


def last_days(room: SlowRoom, days: float) -> list[tuple[float, float, float]]:
    end = room.log[-1][0]
    return [entry for entry in room.log if entry[0] >= end - days * DAY]


@pytest.mark.parametrize("low", [1.0, 1.5, 2.0])
def test_the_room_trim_removes_the_shortfall_of_a_curve_set_too_low(low: float) -> None:
    sim, room = heat(low, 10)
    settled = last_days(room, 3)
    temperatures = [temperature for _, temperature, _ in settled]
    # It ends at the target: the trim makes up what the curve's line misses.
    assert sum(temperatures) / len(temperatures) == pytest.approx(TARGET, abs=0.1)
    # It never overshoots by more than a few tenths.
    assert max(temperature for _, temperature, _ in room.log) < TARGET + 0.3
    # It settles: the room holds still and the setpoint stays put.
    assert max(temperatures) - min(temperatures) < 0.1
    assert len({setpoint for _, _, setpoint in settled}) == 1
    trim = sim.state.room_trim
    assert trim.learned > low - 0.7
    # Few writes over the whole run, far within a bridge's daily budget.
    assert len(sim.calls_to(SUPPLY)) <= 15


def test_without_learning_the_shortfall_stays() -> None:
    _, room = heat(1.5, 4, learn_rate=0)
    settled = last_days(room, 1)
    mean = sum(temperature for _, temperature, _ in settled) / len(settled)
    assert mean < TARGET - 0.25


def test_a_curve_set_too_high_is_lowered_until_the_floor_stops_cycling() -> None:
    sim, room = heat(-1.0, 10)
    # The first warm-up from 20 °C teaches it a little; the pauses of a
    # satisfied floor unlearn that and then the curve's excess.
    assert sim.state.room_trim.learned < 0.0
    assert max(temperature for _, temperature, _ in room.log) < TARGET + 0.3
    settled = [temperature for _, temperature, _ in last_days(room, 1)]
    assert max(settled) - min(settled) < 0.1


# Near its steady state: the room just below its target, the screed warm.
NEAR: Final = (20.8, 24.0)
# The sun's daily gain, in kW.
SUN: Final = 0.3


@pytest.mark.parametrize("low", [0.0, 1.5, -1.0])
@pytest.mark.parametrize("gain", [0.0, SUN])
def test_the_learned_part_settles_at_the_curve_s_shortfall(low: float, gain: float) -> None:
    """What the weekly brief would fold into the line is what the line misses."""
    sim, _ = heat(low, 14, start=NEAR, gain=gain)
    assert sim.state.room_trim.learned == pytest.approx(low, abs=0.2)


@pytest.mark.parametrize("setback", [0.5, 1.0])
def test_a_night_setback_teaches_a_correct_curve_nothing(setback: float) -> None:
    sim, room = heat(0.0, 14, start=NEAR, setback=setback)
    assert sim.state.room_trim.learned == pytest.approx(0.0, abs=0.2)
    # The proportional part may add a degree while the room recovers, no more.
    assert max(setpoint for _, _, setpoint in last_days(room, 3)) <= 38.0
