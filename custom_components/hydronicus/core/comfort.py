"""Bounded comfort planning, with no access to equipment or hydraulic decisions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite

from .model import DigitalThermostat, LearningMode, Mode, Preset
from .thermal import RecoveryEstimate


@dataclass(frozen=True, slots=True)
class ScheduleState:
    """The schedule helper's active period and next transition as a UTC timestamp."""

    active: bool | None
    next_event: float | None = None


@dataclass(frozen=True, slots=True)
class ComfortTarget:
    """A target proposal; thermostat and hydraulic safety still decide demand and flow."""

    target: float
    reason: str | None = None
    early_start: bool = False
    schedule_status: str = "manual"
    early_start_event: float | None = None
    recovery_seconds: float | None = None
    recovery_method: str = "configured"


def comfort_target(
    config: DigitalThermostat,
    mode: Mode,
    manual_target: float,
    preset: Preset | None,
    temperature: float | None,
    schedule: ScheduleState | None,
    now: float,
    reached: Callable[[float], bool],
    early_start_event: float | None = None,
    recovery: RecoveryEstimate | None = None,
) -> ComfortTarget:
    """Choose a mode-specific preset, scheduled setback, or bounded early start.

    Early start estimates time to comfort from the current temperature and the
    explicitly configured warming or cooling rate. It never starts earlier than
    ``max_early_start``, never changes modes, and remains disabled by default.
    Missing schedule data falls back to the owner's manual comfort target.
    """
    if preset is not Preset.SCHEDULE or config.schedule is None:
        target = (
            manual_target if preset is None else config.presets_for(mode).get(preset, manual_target)
        )
        return ComfortTarget(target)
    if mode is Mode.OFF:
        return ComfortTarget(manual_target, schedule_status="off")
    if schedule is None or schedule.active is None:
        return ComfortTarget(manual_target, "schedule unavailable", schedule_status="unavailable")
    event = schedule.next_event
    future = event is not None and isfinite(event) and event > now
    if future:
        assert event is not None
        reached(event)
    if schedule.active:
        return ComfortTarget(manual_target, "scheduled comfort", schedule_status="comfort")
    settings = config.schedule
    setback = (
        max(5.0, manual_target - settings.heat_setback)
        if mode is Mode.HEAT
        else min(35.0, manual_target + settings.cool_setback)
    )
    if (
        future
        and event is not None
        and early_start_event == event
        and event - now <= settings.max_early_start
    ):
        return ComfortTarget(
            manual_target,
            "early start for scheduled comfort",
            True,
            "early_start",
            event,
            recovery_method="latched",
        )
    if (
        future
        and settings.max_early_start > 0
        and temperature is not None
        and isfinite(temperature)
    ):
        assert event is not None
        error = manual_target - temperature if mode is Mode.HEAT else temperature - manual_target
        rate = settings.heating_rate if mode is Mode.HEAT else settings.cooling_rate
        if error > 0:
            seconds = 3600.0 * error / rate
            method = "configured"
            if (
                config.learning is LearningMode.ASSIST
                and recovery is not None
                and recovery.confidence
                and recovery.seconds is not None
                and isfinite(recovery.seconds)
                and recovery.seconds >= 0
                and recovery.valid_until is not None
                and isfinite(recovery.valid_until)
                and not reached(recovery.valid_until)
                and (not recovery.weather_adjusted or config.weather_aware)
            ):
                seconds = recovery.seconds
                method = "weather" if recovery.weather_adjusted else "learned"
            lead = min(settings.max_early_start, seconds)
            if reached(event - lead):
                return ComfortTarget(
                    manual_target,
                    "early start for scheduled comfort",
                    True,
                    "early_start",
                    event,
                    seconds,
                    method,
                )
            return ComfortTarget(
                setback,
                "scheduled setback",
                schedule_status="setback",
                recovery_seconds=seconds,
                recovery_method=method,
            )
    return ComfortTarget(setback, "scheduled setback", schedule_status="setback")
