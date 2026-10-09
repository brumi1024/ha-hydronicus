"""What the last evaluation of a Plant shows, as its entities and diagnostics read it.

The runtime builds a ``PlantView`` after every evaluation. It is a snapshot:
the entities derive their states from it, and nothing in it changes until the
next evaluation replaces it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from .areas import AreaResolution
from .core.demand import aggregate, dew_point, zone_values
from .core.model import Desired, Loop, Mode, Plant, Pump, SwitchTarget, Zone
from .core.reconcile import Reconciled
from .core.step import GUARD_REFERENCE_MAX_AGE, Observations, OutputState, Reading, SwitchState
from .previous import Commanding

# A zone whose demand is off for one of these reasons cannot get what it asks for.
# Frost protection overrides an open window, so a zone it heats has another reason.
_BLOCKING_REASONS: Final = frozenset(
    {"thermostat unavailable", "thermostat not restored", "no usable temperature", "window open"}
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
    sensor_health: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Operation:
    """An operating state and the evidence behind it; unknown is never confirmed off."""

    active: bool | None
    basis: str
    sensor: str | None = None

    def attributes(self) -> dict[str, Any]:
        return {"active": self.active, "basis": self.basis, "sensor": self.sensor}


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
    # Post-run is estimated only after this sequence has seen the source run.
    source_winding: bool = False
    live: bool = False

    @property
    def running_mode(self) -> Mode:
        return self.desired.mode

    def holds(self, *targets: str) -> list[dict[str, Any]]:
        """The timers holding these targets, or every one with none given, soonest end first."""
        return [
            {
                "target": hold.target,
                "kind": hold.kind.value,
                "until": None
                if hold.until is None
                else datetime.fromtimestamp(hold.until, UTC).isoformat(),
            }
            for hold in self.desired.holds
            if not targets or hold.target in targets
        ]

    def loop_hold_targets(self, loop: Loop) -> tuple[str, ...]:
        """What holds a loop as it is: the loop, its valves, and its pump, or its source."""
        pump = self.plant.pump(loop.pump)
        return (
            str(loop.ref),
            *(valve.entity for valve in loop.valves),
            pump.switch or "source",
        )

    def readings(self, zone: str) -> ZoneReadings:
        return self.zones.get(zone, ZoneReadings())

    def loop_flowing(self, loop: Loop) -> bool:
        """Whether a loop passes flow as ``step()`` saw it, including Dry run proposals."""
        return self.loop_operation(loop).active is True

    def loop_operation(self, loop: Loop, *, observed: bool = False) -> Operation:
        """The evidence for a loop's flow, optionally excluding all Dry run proposals."""
        return loop_operation(
            self.plant,
            loop,
            self.observations if observed else self.seen,
            self.at,
            source_winding=self.source_winding and (self.live or not observed),
        )

    def sensor_health(self, now: float | None = None) -> dict[str, dict[str, Any]]:
        """Every numeric input's age and quality against its strictest configured use."""
        limits: dict[str, float] = {}
        for zone in self.plant.zones:
            for entity, maximum in _zone_sensor_limits(zone, self.observations):
                limits[entity] = min(limits.get(entity, maximum), maximum)
        for pump in self.plant.pumps:
            if pump.supply_temperature:
                limits[pump.supply_temperature] = min(
                    limits.get(pump.supply_temperature, GUARD_REFERENCE_MAX_AGE),
                    GUARD_REFERENCE_MAX_AGE,
                )
        for loop in self.plant.all_loops:
            if loop.surface_temperature:
                limits[loop.surface_temperature] = min(
                    limits.get(loop.surface_temperature, GUARD_REFERENCE_MAX_AGE),
                    GUARD_REFERENCE_MAX_AGE,
                )
        source = self.plant.source
        if source and source.supply and source.supply.outdoor_sensor:
            entity, maximum = source.supply.outdoor_sensor, source.supply.max_age
            limits[entity] = min(limits.get(entity, maximum), maximum)
        return {
            entity: reading_health(
                self.observations.sensors.get(entity), maximum, self.at if now is None else now
            )
            for entity, maximum in sorted(limits.items())
        }

    def status(self) -> str:
        """Off, idle, heating, cooling, exercising, changing over, degraded, stopping, invalid."""
        desired = self.desired
        if self.stopping is not None:
            return "stopping"
        if self.problem is not None:
            return "invalid"
        if self.reconciled.repairs or self.missing:
            return "degraded"
        if "mode" in desired.reasons:
            return "changing_over"
        if desired.exercise is not None:
            return "exercising"
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
        loops = self.plant.zone_loops(zone)
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
            and (state.on is not False or state.moving)
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
                for loop in self.plant.zone_loops(zone.slug)
                if (reason := desired.reasons.get(str(loop.ref), "")).startswith("dropped")
            ]
            if demand.on and dropped:
                blocked[zone.slug] = dropped[0]
            elif not demand.on and demand.reason in _BLOCKING_REASONS:
                blocked[zone.slug] = demand.reason
        return blocked

    def blocking_reason(self) -> str | None:
        """The most immediate reason operation cannot continue as requested."""
        if self.problem:
            return self.problem
        if self.stopping is not None:
            return "Waiting for equipment from the previous configuration to stop"
        if self.missing:
            return "A configured entity is missing"
        if self.reconciled.repairs:
            return "Equipment has not confirmed its requested state"
        if reason := self.desired.reasons.get("mode"):
            return reason
        if blocked := self.blocked_zones():
            slug, reason = next(iter(blocked.items()))
            return f"{self.plant.zone(slug).title}: {reason}"
        supply = self.desired.reasons.get("source_supply", "")
        if supply and not supply.startswith("supply target "):
            return supply
        source = self.desired.reasons.get("source", "")
        return (
            source
            if source.startswith("waiting") or "blocks" in source or "did not confirm" in source
            else None
        )


def observed_flow(
    plant: Plant, observations: Observations, now: float, *, source_winding: bool = False
) -> tuple[frozenset[str], frozenset[str]]:
    """The loops whose observed feedback indicates flow, and the zones they serve.

    Unlike the loop flowing sensors, this leaves out the Dry run proposals and
    the calls in flight. Without a flow sensor this remains an inference from
    outputs, running feedback, and the configured source post-run.
    """
    flowing = [
        loop
        for loop in plant.all_loops
        if loop_operation(plant, loop, observations, now, source_winding=source_winding).active
        is True
    ]
    zones = frozenset(
        zone.slug
        for zone in plant.zones
        if any(loop in flowing for loop in plant.zone_loops(zone.slug))
    )
    return frozenset(str(loop.ref) for loop in flowing), zones


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
        sensor_health={
            entity: reading_health(sensors.get(entity), maximum, now)
            for entity, maximum in _zone_sensor_limits(zone, observations)
        },
    )


def _zone_sensor_limits(zone: Zone, observations: Observations) -> list[tuple[str, float]]:
    limits = [(sensor.entity, sensor.max_age) for sensor in (*zone.temperature, *zone.humidity)]
    for area in zone.areas:
        if (named := observations.areas.get(area.area)) is not None:
            limits.extend(
                (entity, area.max_age)
                for entity in (named.temperature, named.humidity)
                if entity is not None
            )
    return limits


def reading_health(reading: Reading | None, maximum: float, now: float) -> dict[str, Any]:
    """Explain freshness without presenting an invalid value as a measurement."""
    age = None if reading is None else max(0.0, now - reading.updated)
    quality = (
        "unavailable or invalid"
        if reading is None or reading.value is None
        else "stale"
        if age is not None and age >= maximum
        else "fresh"
    )
    return {
        "quality": quality,
        "age_seconds": None if age is None else round(age, 1),
        "max_age_seconds": maximum,
        "value": _value(reading),
    }


def _binary(state: OutputState | None) -> bool | None:
    if not isinstance(state, SwitchState) or state.on is None or state.moving:
        return None
    return state.on


def source_operation(plant: Plant, observations: Observations) -> Operation:
    """Separate generator running feedback from its request output."""
    source = plant.source
    if source is None:
        return Operation(False, "No source configured")
    if source.running_sensor:
        return Operation(
            _binary(observations.readiness.get(source.running_sensor)),
            "Running sensor",
            source.running_sensor,
        )
    return Operation(
        _binary(observations.outputs.get(source.request)),
        "Inferred from source request",
        source.request,
    )


def pump_operation(
    plant: Plant,
    pump: Pump,
    observations: Observations,
    now: float,
    *,
    source_winding: bool = False,
) -> Operation:
    """Prefer independent running feedback, otherwise label the operating estimate."""
    if pump.running_sensor:
        return Operation(
            _binary(observations.readiness.get(pump.running_sensor)),
            "Running sensor",
            pump.running_sensor,
        )
    if pump.switch:
        return Operation(
            _binary(observations.outputs.get(pump.switch)), "Inferred from pump switch", pump.switch
        )
    source = plant.source
    if source is None:
        return Operation(None, "No source configured")
    state = observations.outputs.get(source.request)
    running = source_operation(plant, observations)
    if running.active is True:
        return Operation(True, "Inferred from source operation", running.sensor)
    if (
        source_winding
        and isinstance(state, SwitchState)
        and state.on is False
        and now < state.since + source.post_run
    ):
        return Operation(True, "Estimated source post-run", source.request)
    if source.running_sensor and running.active is None:
        return Operation(None, "Source running feedback unavailable", source.running_sensor)
    return Operation(_binary(state), "Inferred from source request", source.request)


def loop_operation(
    plant: Plant,
    loop: Loop,
    observations: Observations,
    now: float,
    *,
    source_winding: bool = False,
) -> Operation:
    """Explain inferred branch flow; pump flow feedback cannot measure each branch."""
    valves = [_binary(observations.outputs.get(valve.entity)) for valve in loop.valves]
    if False in valves:
        return Operation(False, "Valve closed")
    if None in valves:
        return Operation(None, "Valve position unavailable")
    pump = plant.pump(loop.pump)
    if pump.flow_sensor:
        return Operation(
            _binary(observations.readiness.get(pump.flow_sensor)),
            "Pump flow sensor; loop path inferred",
            pump.flow_sensor,
        )
    running = pump_operation(plant, pump, observations, now, source_winding=source_winding)
    return Operation(running.active, f"Estimated flow: {running.basis.lower()}", running.sensor)


def _value(reading: Reading | None) -> float | None:
    return None if reading is None else reading.value
