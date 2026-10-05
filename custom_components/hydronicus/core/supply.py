"""Bounded source supply targets, independent of actuation and hydraulic sequencing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

from .demand import Reading
from .model import Mode, SupplyControl


@dataclass(frozen=True, slots=True)
class SupplyTarget:
    """A proposed supply temperature in Celsius, or why no target can be chosen."""

    target: float | None
    reason: str | None = None


def supply_target(
    config: SupplyControl,
    mode: Mode,
    sensors: Mapping[str, Reading],
    now: float,
) -> SupplyTarget:
    """Choose a bounded fixed target or a clamped linear heating curve.

    The caller schedules the outdoor reading's freshness deadline, confirms
    the numeric output, and applies condensation and hydraulic interlocks.
    Cooling never depends on an outdoor reading. An invalid heating reading
    never falls back to an unrequested fixed target.
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
        reading = sensors.get(config.outdoor_sensor)
        if reading is None or reading.value is None:
            return SupplyTarget(None, "outdoor temperature unavailable")
        if not isfinite(reading.value) or not isfinite(reading.updated):
            return SupplyTarget(None, "outdoor temperature invalid")
        if now >= reading.updated + config.max_age:
            return SupplyTarget(None, "outdoor temperature stale")
        endpoints = (config.outdoor_cold, config.outdoor_warm, config.heat_cold, config.heat_warm)
        if (
            not all(isfinite(value) for value in endpoints)
            or config.outdoor_cold >= config.outdoor_warm
        ):
            return SupplyTarget(None, "invalid outdoor compensation curve")
        fraction = min(
            1.0,
            max(
                0.0,
                (reading.value - config.outdoor_cold) / (config.outdoor_warm - config.outdoor_cold),
            ),
        )
        target = config.heat_cold + fraction * (config.heat_warm - config.heat_cold)
    if not isfinite(target):
        return SupplyTarget(None, "supply temperature invalid")
    return SupplyTarget(min(config.maximum, max(config.minimum, target)))
