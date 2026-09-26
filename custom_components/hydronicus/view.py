"""What the last evaluation of a Plant shows, as its entities and diagnostics read it.

The runtime builds a ``PlantView`` after every evaluation. It is a snapshot:
the entities derive their states from it, and nothing in it changes until the
next evaluation replaces it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from .areas import AreaResolution
from .core.demand import aggregate, dew_point, zone_values
from .core.model import Desired, Loop, Mode, Plant, RunKind, SwitchTarget, Zone
from .core.reconcile import Reconciled
from .core.step import Observations, OutputState, Reading, SwitchState
from .previous import Commanding

# A zone whose demand is off for one of these reasons cannot get what it asks for.
_BLOCKING_REASONS: Final = frozenset(
    {"thermostat unavailable", "thermostat not restored", "no usable temperature"}
)


@dataclass(frozen=True, slots=True)
class ZoneReadings:
    """What a zone's sensors show now, for its entities."""

    temperature: float | None = None
    humidity: float | None = None
    dew_point: float | None = None
    # Each covered area with the sensors it names and their readings.
    areas: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    # Each explicit temperature sensor with its reading.
    sensors: Mapping[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlantView:
    """One evaluation: what was observed, what ``step()`` saw and decided, and what it means.

    ``plant`` is the configured Plant, whose entities read the view, while
    ``desired`` and ``reconciled`` are of the Plant the evaluation drove: the
    previous one while ``stopping``.
    """

    plant: Plant
    at: float
    observations: Observations
    # The observations as step() saw them: with the calls that may still act and
    # the Dry run proposals.
    seen: Observations
    desired: Desired
    reconciled: Reconciled
    zones: Mapping[str, ZoneReadings]
    # Each bound entity that does not exist, with where the Plant binds it.
    missing: Mapping[str, str]
    problem: str | None
    stopping: Commanding | None

    @property
    def running_mode(self) -> Mode:
        return self.desired.mode

    def readings(self, zone: str) -> ZoneReadings:
        return self.zones.get(zone, ZoneReadings())

    def loop_flowing(self, loop: Loop) -> bool:
        """Whether a loop passes flow as ``step()`` saw it, including Dry run proposals."""
        outputs = self.seen.outputs
        if not all(_on(outputs.get(valve.entity)) for valve in loop.valves):
            return False
        pump = self.plant.pump(loop.pump)
        if pump.switch is not None:
            return _on(outputs.get(pump.switch))
        source = self.plant.source
        return source is not None and _on(outputs.get(source.request))

    def status(self) -> str:
        """Off, idle, heating, cooling, changing over, degraded, stopping, or invalid."""
        desired = self.desired
        if self.stopping is not None:
            return "stopping"
        if self.problem is not None:
            return "invalid"
        if self.reconciled.repairs or self.missing:
            return "degraded"
        if "mode" in desired.reasons:
            return "changing_over"
        if desired.mode is Mode.OFF:
            return "off" if self.observations.mode is Mode.OFF else "idle"
        # Anything asked to run, from a valve opening to a pump's overrun, is work in the mode.
        if any(target == SwitchTarget(True) for target in desired.outputs.values()) or any(
            self.loop_flowing(loop) for loop in self.plant.all_loops
        ):
            return "heating" if desired.mode is Mode.HEAT else "cooling"
        return "idle"

    def zone_action(self, zone: str) -> str:
        """What the equipment does for a zone: heating, cooling, preheating, or idle.

        The zone is heated or cooled while it demands in the mode the outputs run
        in and one of its loops passes flow, which includes a plant loop that runs
        with it. It is preheating while it demands heat and a loop it wants does
        not pass flow yet, such as while its valves open. Anything else is idle.
        """
        desired = self.desired
        demand = desired.demands.get(zone)
        if demand is None or not demand.on or demand.mode is not desired.mode:
            return "idle"
        loops = [
            loop
            for loop in self.plant.all_loops
            if loop.zone == zone
            or (loop.runs.kind is RunKind.WITH_ZONES and zone in loop.runs.zones)
        ]
        if any(self.loop_flowing(loop) for loop in loops):
            return "heating" if desired.mode is Mode.HEAT else "cooling"
        if desired.mode is Mode.HEAT and any(
            desired.reasons.get(str(loop.ref)) == "wanted" for loop in loops
        ):
            return "preheating"
        return "idle"

    def stopping_outputs(self) -> list[str]:
        """The outputs of a stopping previous Plant that are not yet observed off."""
        if self.stopping is None:
            return []
        return sorted(
            entity
            for entity in self.stopping.outputs
            if isinstance(state := self.observations.outputs.get(entity), SwitchState)
            and state.on is not False
        )

    def blocked_zones(self) -> dict[str, str]:
        """Each zone that cannot get what its thermostat asks for, with the reason."""
        desired = self.desired
        blocked: dict[str, str] = {}
        for zone in self.plant.zones:
            demand = desired.demands.get(zone.slug)
            if demand is None:
                continue
            if demand.on and demand.mode is not desired.mode and desired.mode is not Mode.OFF:
                blocked[zone.slug] = (
                    f"thermostat asks to {demand.mode.value} while the Plant runs "
                    f"{desired.mode.value}"
                )
                continue
            dropped = [
                reason
                for loop in zone.loops
                if (reason := desired.reasons.get(str(loop.ref), "")).startswith("dropped")
            ]
            if demand.on and dropped:
                blocked[zone.slug] = dropped[0]
            elif not demand.on and demand.reason in _BLOCKING_REASONS:
                blocked[zone.slug] = demand.reason
        return blocked


def zone_readings(
    zone: Zone, observations: Observations, areas: AreaResolution, now: float
) -> ZoneReadings:
    """The combined temperature, the highest humidity, and the worst-case dew point of a zone."""

    def reached(deadline: float) -> bool:
        return now >= deadline

    sensors, names = observations.sensors, observations.areas
    temperatures = zone_values(zone, names, sensors, reached)
    humidities = zone_values(zone, names, sensors, reached, humidity=True)
    temperature = None if temperatures is None else aggregate(temperatures, zone.aggregation)
    humidity = None if humidities is None else max(humidities)
    worst = (
        None
        if temperatures is None or humidities is None
        else dew_point(max(temperatures), max(humidities))
    )
    breakdown: dict[str, dict[str, Any]] = {}
    for area in zone.areas:
        named = names.get(area.area)
        entry: dict[str, Any] = {"name": areas.name(area.area)}
        for key, entity in (
            ("temperature", None if named is None else named.temperature),
            ("humidity", None if named is None else named.humidity),
        ):
            entry[f"{key}_sensor"] = entity
            entry[key] = None if entity is None else _value(sensors.get(entity))
        breakdown[area.area] = entry
    return ZoneReadings(
        temperature=temperature,
        humidity=humidity,
        dew_point=worst,
        areas=breakdown,
        sensors={sensor.entity: _value(sensors.get(sensor.entity)) for sensor in zone.temperature},
    )


def _on(state: OutputState | None) -> bool:
    return isinstance(state, SwitchState) and state.on is True


def _value(reading: Reading | None) -> float | None:
    return None if reading is None else reading.value
