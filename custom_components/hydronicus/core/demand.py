"""Zone demand and the condensation guard's inputs: readings, dew point, and thermostats.

These are the parts of ``step()`` that read sensors and thermostats, carried
over from the v0.1 controller: fail-closed aggregation of fresh readings, the
Magnus dew point and the worst-case dew point from the warmest and most humid
readings, digital thermostat hysteresis with minimum durations, and the
normalization of an external thermostat's ``hvac_action``.

Every time-based decision goes through a ``reached`` callback, which answers
whether a deadline has passed and otherwise records it, so the evaluation can
return when it is next due.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from math import fsum, isfinite, log
from typing import Final

from .model import Aggregation, Demand, DigitalThermostat, Mode, Preset, Zone

type Reached = Callable[[float], bool]

_DEW_POINT_A: Final = 17.62
_DEW_POINT_B: Final = 243.12


@dataclass(frozen=True, slots=True)
class Reading:
    """A numeric sensor as observed."""

    # None while the sensor is unavailable, unknown, or not a number.
    value: float | None
    # When the sensor last reported, changed or not; a reading older than its
    # ``max_age`` is stale.
    updated: float


@dataclass(frozen=True, slots=True)
class AreaSensors:
    """The temperature and humidity sensor an area currently names, if any."""

    temperature: str | None = None
    humidity: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalThermostatState:
    """A digital thermostat's restored climate entity."""

    hvac_mode: Mode
    # The manual target; a preset the zone's thermostat defines overrides it.
    target: float
    preset: Preset | None = None


@dataclass(frozen=True, slots=True)
class ExternalThermostatState:
    """An external thermostat's normalized ``hvac_action``, see ``external_action``."""

    # HEAT for heating or preheating, COOL for cooling, OFF for idle or off, and
    # None while the entity is unavailable or reports anything else.
    action: Mode | None


type ThermostatState = DigitalThermostatState | ExternalThermostatState


@dataclass(frozen=True, slots=True)
class DemandState:
    """A zone's demand decision, the thermostat mode it is for, and when it last changed."""

    mode: Mode
    on: bool
    since: float


def external_action(hvac_action: str | None, hvac_mode: str | None) -> Mode | None:
    """Normalize an external climate entity's ``hvac_action`` and ``hvac_mode``.

    Heating and preheating are heat and cooling is cool, unless the entity's own
    mode contradicts it; idle and off are off; anything else is None, which
    blocks the zone.
    """
    match hvac_action:
        case "heating" | "preheating" if hvac_mode not in ("off", "cool"):
            return Mode.HEAT
        case "cooling" if hvac_mode not in ("off", "heat"):
            return Mode.COOL
        case "idle" | "off":
            return Mode.OFF
        case _:
            return None


# Readings


def fresh(reading: Reading | None, max_age: float, reached: Reached) -> float | None:
    """Return a reading's value while it is usable: present, finite, and not stale."""
    if reading is None or reading.value is None or not isfinite(reading.value):
        return None
    if reached(reading.updated + max_age):
        return None
    return reading.value


def _zone_sensors(
    zone: Zone, areas: Mapping[str, AreaSensors], humidity: bool
) -> Iterator[tuple[str, bool, float]]:
    """Each sensor of a zone with its ``required`` and ``max_age``, explicit ones first."""
    for sensor in zone.humidity if humidity else zone.temperature:
        yield sensor.entity, sensor.required, sensor.max_age
    for area in zone.areas:
        names = areas.get(area.area)
        entity = None if names is None else names.humidity if humidity else names.temperature
        if entity is not None:
            yield entity, area.required, area.max_age


def zone_values(
    zone: Zone,
    areas: Mapping[str, AreaSensors],
    sensors: Mapping[str, Reading],
    reached: Reached,
    *,
    humidity: bool = False,
) -> list[float] | None:
    """Return a zone's usable temperatures or humidities; None fails closed.

    A required sensor that is not usable blocks the zone; an optional one is left
    out. An area that is missing or names no sensor contributes nothing.
    """
    values: list[float] = []
    for entity, required, max_age in _zone_sensors(zone, areas, humidity):
        value = fresh(sensors.get(entity), max_age, reached)
        if value is None:
            if required:
                return None
            continue
        values.append(value)
    return values or None


def aggregate(values: list[float], aggregation: Aggregation) -> float:
    match aggregation:
        case Aggregation.MIN:
            return min(values)
        case Aggregation.MAX:
            return max(values)
        case _:
            return fsum(values) / len(values)


def dew_point(temperature: float, humidity: float) -> float | None:
    """Return the Magnus dew point in °C, or None outside the formula's range."""
    if not isfinite(temperature) or not isfinite(humidity):
        return None
    if humidity <= 0 or humidity > 100 or temperature <= -_DEW_POINT_B:
        return None
    gamma = log(humidity / 100.0) + _DEW_POINT_A * temperature / (_DEW_POINT_B + temperature)
    result = _DEW_POINT_B * gamma / (_DEW_POINT_A - gamma)
    return result if isfinite(result) else None


def worst_dew_point(
    zone: Zone, areas: Mapping[str, AreaSensors], sensors: Mapping[str, Reading], reached: Reached
) -> float | None:
    """Return the dew point of a zone's warmest and most humid readings.

    A zone can span several spaces, and without pairing each temperature with its
    humidity their highest values bound the dew point of every one of them.
    """
    temperatures = zone_values(zone, areas, sensors, reached)
    humidities = zone_values(zone, areas, sensors, reached, humidity=True)
    if temperatures is None or humidities is None:
        return None
    return dew_point(max(temperatures), max(humidities))


# Thermostats


def zone_demand(
    zone: Zone,
    thermostat: ThermostatState | None,
    temperature: float | None,
    previous: DemandState | None,
    now: float,
    reached: Reached,
) -> tuple[DemandState, Demand]:
    """Evaluate a zone's thermostat into its next DemandState and its Demand."""
    if isinstance(thermostat, ExternalThermostatState):
        action = thermostat.action
        if action is None:
            return _settle(previous, Mode.OFF, False, now), _off(Mode.OFF, "thermostat unavailable")
        on = action is not Mode.OFF
        reason = f"thermostat {action.value}" if on else "thermostat idle"
        return _settle(previous, action, on, now), Demand(action, on, 1.0 if on else 0.0, reason)
    config = zone.thermostat
    if not isinstance(thermostat, DigitalThermostatState) or not isinstance(
        config, DigitalThermostat
    ):
        return _settle(previous, Mode.OFF, False, now), _off(Mode.OFF, "thermostat not restored")
    mode = thermostat.hvac_mode
    if mode is Mode.OFF:
        return _settle(previous, mode, False, now), _off(mode, "thermostat off")
    if temperature is None:
        return _settle(previous, mode, False, now), _off(mode, "no usable temperature")
    target = thermostat.target
    if thermostat.preset is not None:
        target = config.preset_targets.get(thermostat.preset, target)
    # The distance to target in the direction the mode drives the room.
    below = target - temperature if mode is Mode.HEAT else temperature - target
    start, stop = (
        (config.heat_start_delta, config.heat_stop_delta)
        if mode is Mode.HEAT
        else (config.cool_start_delta, config.cool_stop_delta)
    )
    was_on = previous is not None and previous.mode is mode and previous.on
    requested = below >= start or (was_on and below > -stop)
    state = _apply_timing(previous, mode, requested, config, now, reached)
    level = min(1.0, max(0.0, below / config.proportional_band)) if state.on else 0.0
    verb = "heat" if mode is Mode.HEAT else "cool"
    reason = f"{verb} to {target:.1f} °C from {temperature:.1f} °C"
    if state.on != requested:
        reason += ", held for its minimum " + ("on" if state.on else "off") + " time"
    return state, Demand(mode, state.on, level, reason)


def _apply_timing(
    previous: DemandState | None,
    mode: Mode,
    requested: bool,
    config: DigitalThermostat,
    now: float,
    reached: Reached,
) -> DemandState:
    """Hold a decision for its minimum on or off time after hysteresis."""
    if previous is None or previous.mode is not mode:
        return DemandState(mode, requested, now)
    if requested == previous.on:
        return previous
    duration = config.min_on if previous.on else config.min_off
    if duration > 0 and not reached(previous.since + duration):
        return previous
    return DemandState(mode, requested, now)


def _settle(previous: DemandState | None, mode: Mode, on: bool, now: float) -> DemandState:
    """A decision without minimum durations, keeping the time of the last change."""
    if previous is not None and previous.mode is mode and previous.on == on:
        return previous
    return DemandState(mode, on, now)


def _off(mode: Mode, reason: str) -> Demand:
    return Demand(mode, False, 0.0, reason)
