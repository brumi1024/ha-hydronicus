"""A heat pump on its own weather curve, and the house it heats, for the simulator.

The world in ``world.py`` knows only switches and valves. This module adds the
physics behind them for the maintainer's house: a heat pump whose space heating
the source request switches, its internal pump on the primary side of a plate
heat exchanger, the secondary water the switched heating pump carries to the
loops, each loop's emitter, and each zone's room.

The heat pump follows what the owner measured on the Midea unit:

- Space heating on runs the internal pump, and the compressor then holds its
  leaving water on the weather curve: it modulates between its minimum and
  maximum output, stops once the water is ``stop_above`` over the curve, and
  starts again once it is ``start_below`` under it, never sooner than
  ``restart_delay`` after it stopped.
- Space heating off stops the compressor and the internal pump at once.
- An internal pump that starts from standstill may fault with E8, water flow
  failure, ``e8_delay`` later; the heat pump then stops heating and its pump
  for ``e8_duration``, and three E8 within an hour latch it as E0.

Every number here is an illustrative assumption sized for the house, not a
measurement, except the restart delay and the E8 delay. The scenarios compare
control strategies against each other on the same physics; they do not predict
the house's absolute energy use.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from math import cos, pi
from typing import Final

from custom_components.hydronicus.core.model import LoopRef, Plant
from tests.sim.harness import Sim
from tests.sim.world import SwitchBody

# Seconds per physics step.
DT: Final = 5.0
# Seconds between sensor reports the zones see.
REPORT: Final = 30.0
# A zone sensor reports in steps of this, in °C.
RESOLUTION: Final = 0.1


@dataclass(frozen=True, slots=True)
class HeatPumpSettings:
    """Outputs in kW, conductances in kW/K, capacities in kJ/K, times in seconds."""

    q_min: float = 5.0
    q_max: float = 12.0
    # Extra output per kelvin the leaving water is under the curve plus a kelvin.
    gain: float = 2.5
    stop_above: float = 2.0
    start_below: float = 2.0
    restart_delay: float = 180.0
    primary_capacity: float = 170.0
    exchanger: float = 2.0
    # The internal pump stops while the compressor rests on its curve; unmeasured.
    pump_stops_in_thermo_off: bool = False
    # An internal pump start after a standstill shorter than this faults E8; None never.
    e8_standstill: float | None = None
    e8_delay: float = 240.0
    e8_duration: float = 2700.0

    def curve(self, outdoor: float) -> float:
        """The leaving water target of the weather curve, about curve 5 of the Midea."""
        return min(45.0, max(28.0, 35.0 - 0.6 * (outdoor - 7.0)))


@dataclass(frozen=True, slots=True)
class Emitter:
    capacity: float
    water: float
    room: float


@dataclass(frozen=True, slots=True)
class Room:
    capacity: float
    loss: float
    gain: float


CEILING: Final = Emitter(250.0, 0.30, 0.40)
LIVING_CEILING: Final = Emitter(350.0, 0.40, 0.55)
FLOOR: Final = Emitter(4000.0, 0.60, 0.50)
ROOMS: Final = {
    "basement": Room(6000.0, 0.07, 0.15),
    "bedroom_area": Room(6000.0, 0.09, 0.15),
    "living_area": Room(10000.0, 0.13, 0.30),
}
EMITTERS: Final = {
    "basement.ceiling": CEILING,
    "bedroom_area.ceiling": CEILING,
    "living_area.ceiling": LIVING_CEILING,
    "living_area.floor": FLOOR,
}
SECONDARY_CAPACITY: Final = 150.0


@dataclass(slots=True)
class Metrics:
    """What one run counts, all times in seconds of simulated time."""

    request_starts: list[float] = field(default_factory=list)
    # Starts of the internal pump from standstill, each with its standstill.
    pump_starts: list[tuple[float, float]] = field(default_factory=list)
    compressor_starts: list[float] = field(default_factory=list)
    compressor_runs: list[float] = field(default_factory=list)
    # The compressor runs while no loop carries the secondary water away.
    sink_violation: float = 0.0
    faults: list[tuple[float, str]] = field(default_factory=list)
    # By zone, kelvin-hours below the target minus 0.5 K and above it plus 0.5 K.
    cold: dict[str, float] = field(default_factory=dict)
    warm: dict[str, float] = field(default_factory=dict)
    peak: dict[str, float] = field(default_factory=dict)
    heat: float = 0.0
    seconds: float = 0.0

    def per_day(self, count: int) -> float:
        return count * 86400.0 / self.seconds if self.seconds else 0.0

    def mean_run(self) -> float:
        return (
            sum(self.compressor_runs) / len(self.compressor_runs) if self.compressor_runs else 0.0
        )


class HeatPumpHouse:
    """The heat pump, its exchanger, and the house, advanced beside a ``Sim``."""

    def __init__(
        self,
        sim: Sim,
        *,
        settings: HeatPumpSettings | None = None,
        outdoor: Callable[[float], float] | float = 7.0,
        target: float = 21.0,
        temperature: float = 21.0,
        internal_pump: str = "heat_pump",
        secondary_pump: str = "heating",
        alarm: str | None = None,
    ) -> None:
        self.sim = sim
        self.settings = settings or HeatPumpSettings()
        self._outdoor = outdoor if callable(outdoor) else (lambda _t, value=outdoor: value)
        self.target = target
        self.internal_pump = internal_pump
        self.secondary_pump = secondary_pump
        self.alarm = alarm
        self.room = dict.fromkeys(ROOMS, temperature)
        self.emitter = dict.fromkeys(EMITTERS, temperature)
        self.primary = 30.0
        self.secondary = 25.0
        self.compressor = False
        self.output = 0.0
        self.pump = False
        self.stopped_at = -1e9
        self.pump_stopped_at = -1e9
        self.compressor_started_at = 0.0
        self.fault_until: float | None = None
        self.fault_at: float | None = None
        self.latched = False
        self.e8_times: list[float] = []
        self.metrics = Metrics(
            cold=dict.fromkeys(ROOMS, 0.0),
            warm=dict.fromkeys(ROOMS, 0.0),
            peak=dict.fromkeys(ROOMS, temperature),
        )
        self._heating = False
        self._report()

    # Inputs from the controlled plant

    @property
    def plant(self) -> Plant:
        return self.sim.plant

    def outdoor(self, t: float | None = None) -> float:
        return self._outdoor(self.sim.t if t is None else t)

    def heating_on(self) -> bool:
        """Space heating, as the source request switches it, or always on without a source."""
        source = self.plant.source
        return source is None or self.sim.is_on(source.request)

    def flowing(self) -> list[str]:
        """The loops that carry the secondary water now."""
        return [ref for ref in EMITTERS if self.sim.flowing(ref)]

    def faulted(self) -> bool:
        return self.latched or self.fault_until is not None

    # Running

    def run_for(self, seconds: float) -> None:
        end = self.sim.t + seconds
        while self.sim.t < end - 1e-9:
            span = min(REPORT, end - self.sim.t)
            self._advance(span)
            self._report()
            self.sim.run_for(span)

    def _advance(self, seconds: float) -> None:
        t, end = self.sim.t, self.sim.t + seconds
        while t < end - 1e-9:
            dt = min(DT, end - t)
            self._physics(t, dt)
            t += dt

    def _physics(self, t: float, dt: float) -> None:
        settings = self.settings
        heating = self.heating_on()
        if heating and not self._heating:
            self.metrics.request_starts.append(t)
        self._heating = heating
        self._faults(t)
        target = settings.curve(self.outdoor(t))
        if (
            not heating
            or self.faulted()
            or (self.compressor and self.primary > target + settings.stop_above)
        ):
            self._stop_compressor(t)
        elif (
            not self.compressor
            and self.primary < target - settings.start_below
            and t >= self.stopped_at + settings.restart_delay
        ):
            self.compressor = True
            self.compressor_started_at = t
            self.metrics.compressor_starts.append(t)
        pump = heating and not self.faulted()
        if settings.pump_stops_in_thermo_off and not self.compressor:
            pump = False
        self._set_pump(t, pump)

        self.output = 0.0
        if self.compressor:
            demand = settings.q_min + settings.gain * (target + 1.0 - self.primary)
            self.output = min(settings.q_max, max(settings.q_min, demand))
        flowing = self.flowing()
        secondary_runs = bool(flowing) and self.sim.pump_running(self.secondary_pump)
        exchanged = (
            settings.exchanger * (self.primary - self.secondary)
            if self.pump and secondary_runs
            else 0.0
        )
        if self.compressor and not secondary_runs:
            self.metrics.sink_violation += dt
        self.primary += (
            dt
            * (self.output - exchanged - 0.02 * (self.primary - 15.0))
            / (settings.primary_capacity)
        )
        to_loops = 0.0
        for ref, emitter in EMITTERS.items():
            zone = LoopRef.parse(ref).zone
            assert zone is not None
            gained = (
                emitter.water * (self.secondary - self.emitter[ref])
                if ref in flowing and secondary_runs
                else 0.0
            )
            given = emitter.room * (self.emitter[ref] - self.room[zone])
            self.emitter[ref] += dt * (gained - given) / emitter.capacity
            to_loops += gained
        self.secondary += (
            dt * (exchanged - to_loops - 0.02 * (self.secondary - 15.0)) / (SECONDARY_CAPACITY)
        )
        outdoor = self.outdoor(t)
        for zone, room in ROOMS.items():
            given = sum(
                EMITTERS[ref].room * (self.emitter[ref] - self.room[zone])
                for ref in EMITTERS
                if ref.startswith(f"{zone}.")
            )
            lost = room.loss * (self.room[zone] - outdoor)
            self.room[zone] += dt * (given - lost + room.gain) / room.capacity
            self._comfort(zone, dt)
        self.metrics.heat += dt * self.output / 3600.0
        self.metrics.seconds += dt

    def _comfort(self, zone: str, dt: float) -> None:
        metrics, temperature = self.metrics, self.room[zone]
        metrics.cold[zone] += max(0.0, self.target - 0.5 - temperature) * dt / 3600.0
        metrics.warm[zone] += max(0.0, temperature - self.target - 0.5) * dt / 3600.0
        metrics.peak[zone] = max(metrics.peak[zone], temperature)

    def _stop_compressor(self, t: float) -> None:
        if self.compressor:
            self.compressor = False
            self.stopped_at = t
            self.metrics.compressor_runs.append(t - self.compressor_started_at)

    def _set_pump(self, t: float, running: bool) -> None:
        if running and not self.pump:
            standstill = t - self.pump_stopped_at
            self.metrics.pump_starts.append((t, standstill))
            limit = self.settings.e8_standstill
            if limit is not None and standstill < limit and self.fault_at is None:
                self.fault_at = t + self.settings.e8_delay
        if not running and self.pump:
            self.pump_stopped_at = t
        self.pump = running
        world = self.sim.world
        if self.internal_pump in {pump.slug for pump in self.plant.pumps}:
            # The world runs a source-driven pump with the request; only a fault
            # or a rest on the curve stops it otherwise.
            override = None if running == self.heating_on() else running
            if world.pump_running_overrides.get(self.internal_pump) != override:
                world.set_pump_running(self.internal_pump, override)

    def _faults(self, t: float) -> None:
        if self.fault_at is not None and t >= self.fault_at:
            self.fault_at = None
            self.e8_times = [time for time in self.e8_times if time > t - 3600.0] + [t]
            if len(self.e8_times) >= 3:
                self.latched = True
                self.metrics.faults.append((t, "E0"))
            else:
                self.fault_until = t + self.settings.e8_duration
                self.metrics.faults.append((t, "E8"))
            self._show_alarm(True)
        if self.fault_until is not None and t >= self.fault_until and not self.latched:
            self.fault_until = None
            self._show_alarm(False)

    def _show_alarm(self, on: bool) -> None:
        if self.alarm is not None:
            self.sim.world.contacts.setdefault(
                self.alarm, SwitchBody(changed=self.sim.world.wall())
            )
            self.sim.set_contact(self.alarm, on)

    def _report(self) -> None:
        for zone, temperature in self.room.items():
            self.sim.set_zone_temperature(zone, round(temperature / RESOLUTION) * RESOLUTION)


def daily(mean: float, swing: float = 3.0) -> Callable[[float], float]:
    """An outdoor temperature with its minimum at 05:00 and maximum at 17:00, from midnight."""
    return lambda t: mean - swing * cos(2 * pi * (t - 5 * 3600.0) / 86400.0)
