"""Independent thermal physics for testing recovery predictions.

The emitter and room each store energy, exchanging it through a conductance.
Water adds heat only after transport delay and while circulation and an external
heat supply are both present. Room heat loss follows outdoor temperature, while
passive gains and imperfect sensors remain independent of the controller.
No production prediction equation or learner parameter enters these dynamics.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sin


@dataclass(frozen=True, slots=True)
class ThermalFabric:
    """Capacities in kJ/K, conductances in kW/K, and transport delay in seconds."""

    emitter_capacity: float
    room_capacity: float
    water_conductance: float
    room_conductance: float
    heat_loss: float
    water_temperature: float
    transport_delay: float


FLOOR = ThermalFabric(1800.0, 4200.0, 0.40, 0.32, 0.055, 35.0, 480.0)
RADIATOR = ThermalFabric(90.0, 3000.0, 0.28, 0.40, 0.060, 42.0, 60.0)


class ThermalRoom:
    """A room and emitter advanced by small explicit energy-balance steps."""

    def __init__(
        self,
        fabric: ThermalFabric,
        temperature: float,
        *,
        outdoor: float = 7.0,
        passive_gain: float = 0.25,
        noise: float = 0.018,
        quantization: float = 0.05,
    ) -> None:
        self.fabric = fabric
        self.temperature = temperature
        self.emitter_temperature = temperature
        self.outdoor = outdoor
        self.passive_gain = passive_gain
        self.noise = noise
        self.quantization = quantization
        self.heat_available = True
        self.t = 0.0
        self.delivered_energy = 0.0
        self._circulating_since: float | None = None

    @property
    def measured_temperature(self) -> float:
        """Repeatable sensor noise and quantization, separate from physical state."""
        noisy = self.temperature + self.noise * sin(self.t / 113.0)
        return round(noisy / self.quantization) * self.quantization

    def advance(self, seconds: float, *, circulating: bool) -> None:
        """Integrate physical heat transfer with at most ten seconds per step."""
        if circulating:
            if self._circulating_since is None:
                self._circulating_since = self.t
        else:
            self._circulating_since = None
        end = self.t + seconds
        f = self.fabric
        while self.t < end:
            dt = min(10.0, end - self.t)
            heated_water = (
                self.heat_available
                and self._circulating_since is not None
                and self.t - self._circulating_since >= f.transport_delay
            )
            from_water = (
                f.water_conductance * (f.water_temperature - self.emitter_temperature)
                if heated_water
                else 0.0
            )
            to_room = f.room_conductance * (self.emitter_temperature - self.temperature)
            to_outside = f.heat_loss * (self.temperature - self.outdoor)
            self.emitter_temperature += dt * (from_water - to_room) / f.emitter_capacity
            self.temperature += dt * (to_room - to_outside + self.passive_gain) / f.room_capacity
            self.delivered_energy += dt * from_water
            self.t += dt

    def recover(self, target: float, *, limit: float = 12 * 3600.0) -> float | None:
        """Observe recovery at one-minute intervals, as a room sensor might report."""
        start = self.t
        while self.t - start < limit:
            self.advance(60.0, circulating=True)
            if self.measured_temperature >= target:
                return self.t - start
        return None


class AutonomousWaterRoom(ThermalRoom):
    """A water-controlled heat source that receives no thermostat or request input.

    The return-water proxy cools toward the emitter when the circuit circulates.
    The autonomous source starts below 30 C and stops above 34 C, warming the
    proxy toward 35 C while running. These temperatures and the two time
    constants are illustrative simulation assumptions, not equipment settings.
    Only the parent room's circulation input connects this source to the Plant.
    """

    START_RETURN = 30.0
    STOP_RETURN = 34.0
    WATER_TARGET = 35.0
    RETURN_COOLING_SECONDS = 2400.0
    RETURN_WARMING_SECONDS = 900.0

    def __init__(self, fabric: ThermalFabric, temperature: float) -> None:
        super().__init__(fabric, temperature)
        self.heat_available = False
        self.return_temperature = self.WATER_TARGET
        self.source_transitions: list[tuple[float, bool, float]] = []

    def advance(self, seconds: float, *, circulating: bool) -> None:
        end = self.t + seconds
        while self.t < end:
            dt = min(10.0, end - self.t)
            if self.heat_available:
                equilibrium = self.WATER_TARGET
                tau = self.RETURN_WARMING_SECONDS
            elif circulating:
                equilibrium = self.emitter_temperature
                tau = self.RETURN_COOLING_SECONDS
            else:
                equilibrium = self.return_temperature
                tau = self.RETURN_COOLING_SECONDS
            self.return_temperature += dt * (equilibrium - self.return_temperature) / tau
            super().advance(dt, circulating=circulating)
            running = self.heat_available
            if running and self.return_temperature >= self.STOP_RETURN:
                self.heat_available = False
            elif not running and self.return_temperature <= self.START_RETURN:
                self.heat_available = True
            if running != self.heat_available:
                self.source_transitions.append(
                    (self.t, self.heat_available, self.return_temperature)
                )
