"""Control strategies for the maintainer's heat pump, compared on the same simulated house.

Run ``uv run python -m tests.sim.heat_pump_strategies`` for the table that
``docs/plans/midea-source.md`` quotes. Each strategy is a Plant: the house of
``plants.HOME_HEAT_PUMP`` with realistic thermostats and valve travel, run for
two days after a six-hour warm-up at a daily outdoor swing of 3 K.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Final

from custom_components.hydronicus.core.model import Mode, Plant
from tests.sim.harness import Sim
from tests.sim.heat_pump import ROOMS, HeatPumpHouse, HeatPumpSettings, Metrics, daily
from tests.sim.plants import plant

WARM_UP: Final = 6 * 3600.0
DAYS: Final = 2

_ZONES: Final = """
pumps:
  heat_pump: {driven_by: source, min_flow: guaranteed}
  heating: {switch: switch.home_underfloor_heating_pump, overrun: 240}
zones:
  basement:
    temperature: [sensor.basement_temperature]
    loops:
      ceiling: {valves: [switch.home_basement_ceiling_heating_valve], pump: heating}
  bedroom_area:
    temperature: [sensor.bedroom_area_temperature]
    loops:
      ceiling: {valves: [switch.home_bedroom_area_ceiling_heating_valve], pump: heating}
  living_area:
    temperature: [sensor.living_area_temperature]
    loops:
      ceiling: {valves: [switch.home_living_area_ceiling_heating_valve], pump: heating}
      floor: {valves: [switch.home_living_area_floor_heating_valve], pump: heating}
"""
FLOOR: Final = "[living_area.floor]"
ALL: Final = "[living_area.floor, living_area.ceiling, basement.ceiling, bedroom_area.ceiling]"


def today() -> Plant:
    """The house as it runs now: no source, so the heat pump heats on its curve by itself."""
    return plant(
        "hydronicus: 2\nname: Home\n"
        + _ZONES.replace("  heat_pump: {driven_by: source, min_flow: guaranteed}\n", "")
    )


def strategy(
    *,
    hold: float | None = None,
    overshoot: float | None = None,
    sinks: str = FLOOR,
    min_off: float = 720.0,
    starts: int = 3,
) -> Plant:
    """The heat pump as the source, released per call or held after demand."""
    lines = [
        "hydronicus: 2",
        "name: Home",
        "source:",
        "  request: switch.home_heat_pump_heating",
        "  post_run: 0",
        "  min_on: 1500",
        f"  min_off: {min_off:g}",
        f"  max_starts_per_hour: {starts}",
        f"  heat_sink_loops: {sinks}",
        "  health_sensor: binary_sensor.home_heat_pump_modbus_healthy",
    ]
    if hold is not None:
        lines.append(f"  hold_after_demand: {hold:g}")
    if overshoot is not None:
        lines.append(f"  heat_sink_overshoot: {overshoot:g}")
    return plant("\n".join(lines) + _ZONES)


@dataclass(frozen=True, slots=True)
class Strategy:
    name: str
    plant: Plant
    settings: HeatPumpSettings = HeatPumpSettings()


STRATEGIES: Final = (
    Strategy("today: no source", today()),
    Strategy("a: request per call", strategy()),
    Strategy("a: rest 30 min, 2 starts/h", strategy(min_off=1800.0, starts=2)),
    Strategy("b: always on, floor sink", strategy(hold=604800.0, overshoot=99.0)),
    Strategy("c: hold 4 h, floor, +0.5 K", strategy(hold=14400.0, overshoot=0.5)),
    Strategy("c: hold 4 h, all loops, +0.5 K", strategy(hold=14400.0, overshoot=0.5, sinks=ALL)),
)
PUMP_STOPS: Final = HeatPumpSettings(pump_stops_in_thermo_off=True)
SENSITIVITY: Final = (
    Strategy("a, pump stops in thermo-off", strategy(), PUMP_STOPS),
    Strategy(
        "c floor, pump stops in thermo-off", strategy(hold=14400.0, overshoot=0.5), PUMP_STOPS
    ),
)


def run(item: Strategy, outdoor: float, days: int = DAYS) -> Metrics:
    """Run one strategy for ``days`` after the warm-up and return what it counted."""
    sim = Sim(item.plant, mode=Mode.HEAT)
    house = HeatPumpHouse(sim, settings=item.settings, outdoor=daily(outdoor))
    sim.start()
    house.run_for(WARM_UP)
    house.metrics = Metrics(
        cold=dict.fromkeys(ROOMS, 0.0), warm=dict.fromkeys(ROOMS, 0.0), peak=dict(house.room)
    )
    house.run_for(days * 86400.0)
    return house.metrics


def row(item: Strategy, outdoor: float, metrics: Metrics) -> str:
    peak = max(metrics.peak.values())
    warm = sum(metrics.warm.values()) / DAYS
    return (
        f"| {item.name} | {outdoor:g} | {metrics.per_day(len(metrics.request_starts)):.1f} "
        f"| {metrics.per_day(len(metrics.pump_starts)):.1f} "
        f"| {metrics.per_day(len(metrics.compressor_starts)):.1f} "
        f"| {metrics.mean_run() / 60:.0f} | {metrics.sink_violation / 60 / DAYS:.0f} "
        f"| {warm:.1f} | {peak:.1f} |"
    )


def main(temperatures: list[float]) -> None:
    print(
        "| Strategy | Outdoor °C | Requests/day | Pump starts/day | Compressor starts/day "
        "| Mean run, min | Heating into closed valves, min/day | Overheat, K h/day "
        "| Warmest room, °C |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for outdoor in temperatures:
        for item in (*STRATEGIES, *SENSITIVITY):
            print(row(item, outdoor, run(item, outdoor)), flush=True)


if __name__ == "__main__":
    main([float(value) for value in sys.argv[1:]] or [-3.0, 7.0, 12.0])
