"""Bounded source supply targets, independent of actuation and hydraulic sequencing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import exp, isfinite

from .demand import Reading
from .model import HEATING_LIMIT_RELEASE, Mode, SupplyControl


@dataclass(frozen=True, slots=True)
class SupplyTarget:
    """A proposed supply temperature in Celsius, or why no target can be chosen."""

    target: float | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DampedOutdoor:
    """The filtered outdoor temperature and when it was last updated, persisted with the State."""

    value: float
    at: float


@dataclass(frozen=True, slots=True)
class Outdoor:
    """The outdoor temperature the heating curve and the heating limit use now.

    ``value`` is the damped reading, or the configured fallback while the reading
    is not usable, or None when neither exists, with ``reason`` saying why.
    ``damped`` is what the State keeps for the next evaluation.
    """

    value: float | None
    damped: DampedOutdoor | None = None
    fallback: bool = False
    reason: str | None = None


def outdoor_temperature(
    config: SupplyControl,
    sensors: Mapping[str, Reading],
    now: float,
    previous: DampedOutdoor | None,
) -> Outdoor | None:
    """Filter the outdoor reading, or fall back to the configured temperature.

    The filter is first order with ``outdoor_damping`` as its time constant, so a
    building that reacts over hours does not follow every gust. It starts again
    from the reading after a gap longer than the reading's ``max_age``, or when the
    clock steps backwards. None when the supply control reads no outdoor sensor.
    """
    if config.outdoor_sensor is None:
        return None
    reading = sensors.get(config.outdoor_sensor)
    problem: str | None = None
    if reading is None or reading.value is None:
        problem = "outdoor temperature unavailable"
    elif not isfinite(reading.value) or not isfinite(reading.updated):
        problem = "outdoor temperature invalid"
    elif now >= reading.updated + config.max_age:
        problem = "outdoor temperature stale"
    if problem is not None or reading is None or reading.value is None:
        if config.outdoor_fallback is None:
            return Outdoor(None, previous, reason=problem)
        fallback = config.outdoor_fallback
        return Outdoor(
            fallback,
            previous,
            fallback=True,
            reason=f"{problem}, curve at its fallback of {fallback:.1f} °C outdoors",
        )
    value = reading.value
    if (
        config.outdoor_damping > 0
        and previous is not None
        and previous.at <= now <= previous.at + config.max_age
    ):
        weight = 1.0 - exp(-(now - previous.at) / config.outdoor_damping)
        value = previous.value + weight * (reading.value - previous.value)
    return Outdoor(value, DampedOutdoor(value, now))


def warm_weather(config: SupplyControl, outdoor: Outdoor | None, active: bool) -> bool:
    """Whether the heating limit keeps the source from heating now.

    It starts at the limit and ends ``HEATING_LIMIT_RELEASE`` below it. A fallback
    or a missing reading never starts or keeps it, so a lost sensor heats.
    """
    if config.heating_limit is None or outdoor is None or outdoor.value is None:
        return False
    if outdoor.fallback:
        return False
    if active:
        return outdoor.value > config.heating_limit - HEATING_LIMIT_RELEASE
    return outdoor.value >= config.heating_limit


def curve_temperature(config: SupplyControl, outdoor: float) -> float:
    """The unclamped heating curve: linear between its endpoints, flat beyond them."""
    fraction = min(
        1.0,
        max(0.0, (outdoor - config.outdoor_cold) / (config.outdoor_warm - config.outdoor_cold)),
    )
    return config.heat_cold + fraction * (config.heat_warm - config.heat_cold)


def supply_target(
    config: SupplyControl,
    mode: Mode,
    sensors: Mapping[str, Reading],
    now: float,
    *,
    outdoor: Outdoor | None = None,
    offset: float | None = None,
    room_shift: float = 0.0,
    frost_outdoor: float | None = None,
) -> SupplyTarget:
    """Choose a bounded fixed target or a clamped linear heating curve.

    The caller schedules the outdoor reading's freshness deadline, confirms
    the numeric output, and applies condensation and hydraulic interlocks.
    Cooling never depends on an outdoor reading. Without a usable reading or a
    fallback, heating gets no target, unless ``frost_outdoor`` gives the
    temperature to assume while frost protection heats. ``offset``, the owner's
    shift, replaces the configured one, and ``room_shift`` adds the lead zone's.
    Both apply in heating only and stay inside the bounds.
    """
    if mode is Mode.OFF:
        return SupplyTarget(None)
    if (
        not isfinite(config.minimum)
        or not isfinite(config.maximum)
        or config.minimum >= config.maximum
    ):
        return SupplyTarget(None, "invalid supply temperature bounds")

    target = config.cool_temperature if mode is Mode.COOL else config.heat_temperature
    if mode is Mode.HEAT and config.outdoor_sensor is not None:
        if outdoor is None:
            outdoor = outdoor_temperature(config, sensors, now, None)
        value = None if outdoor is None else outdoor.value
        if value is None:
            if frost_outdoor is None:
                return SupplyTarget(
                    None,
                    (outdoor.reason if outdoor is not None else None)
                    or "outdoor temperature unavailable",
                )
            value = frost_outdoor
        endpoints = (config.outdoor_cold, config.outdoor_warm, config.heat_cold, config.heat_warm)
        if (
            not all(isfinite(point) for point in endpoints)
            or config.outdoor_cold >= config.outdoor_warm
        ):
            return SupplyTarget(None, "invalid outdoor compensation curve")
        target = curve_temperature(config, value)
    if mode is Mode.HEAT:
        shift = (config.offset if offset is None else offset) + room_shift
        if not isfinite(shift):
            return SupplyTarget(None, "supply temperature invalid")
        target += shift
    if not isfinite(target):
        return SupplyTarget(None, "supply temperature invalid")
    return SupplyTarget(min(config.maximum, max(config.minimum, target)))


def room_shift(config: SupplyControl, target: float | None, temperature: float | None) -> float:
    """The lead zone's shift of the heating curve, zero without its target or reading."""
    influence = config.room_influence
    if influence is None or target is None or temperature is None:
        return 0.0
    shift = influence.factor * (target - temperature)
    if not isfinite(shift):
        return 0.0
    return min(influence.limit, max(-influence.limit, shift))
