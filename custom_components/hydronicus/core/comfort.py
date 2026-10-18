"""Bounded comfort planning, with no access to equipment or hydraulic decisions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import isfinite

from .model import DigitalThermostat, LearningMode, Mode, Preset
from .thermal import RecoveryEstimate

# The keys of a schedule block's data that choose its level; other keys are the owner's.
LEVEL_PRESET = "preset"
LEVEL_HEAT_TARGET = "heat_target"
LEVEL_COOL_TARGET = "cool_target"
LEVEL_KEYS = (LEVEL_PRESET, LEVEL_HEAT_TARGET, LEVEL_COOL_TARGET)
BLOCK_PRESETS = (Preset.COMFORT, Preset.ECO, Preset.AWAY)
MIN_TARGET = 5.0
MAX_TARGET = 35.0


@dataclass(frozen=True, slots=True)
class BlockLevel:
    """What one schedule block's data asks for; empty means the manual comfort target."""

    preset: Preset | None = None
    heat_target: float | None = None
    cool_target: float | None = None
    # Why the block's data cannot be used, which then falls back to manual comfort.
    error: str | None = None


def block_level(data: Mapping[str, object] | None) -> BlockLevel:
    """Read the level keys of a block's data, ignoring every other key."""
    if not data:
        return BlockLevel()
    preset = data.get(LEVEL_PRESET)
    targets: dict[str, float] = {}
    for key in (LEVEL_HEAT_TARGET, LEVEL_COOL_TARGET):
        if key not in data:
            continue
        value = data[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not isfinite(value)
            or not MIN_TARGET <= value <= MAX_TARGET
        ):
            return BlockLevel(
                error=f"{key} must be a number from {MIN_TARGET:g} to {MAX_TARGET:g} °C"
            )
        targets[key] = float(value)
    if preset is None:
        return BlockLevel(
            heat_target=targets.get(LEVEL_HEAT_TARGET), cool_target=targets.get(LEVEL_COOL_TARGET)
        )
    if targets:
        return BlockLevel(error="a block names a preset or a target, not both")
    if not isinstance(preset, str) or preset not in {p.value for p in BLOCK_PRESETS}:
        return BlockLevel(
            error=f"preset must be one of {', '.join(p.value for p in BLOCK_PRESETS)}"
        )
    return BlockLevel(preset=Preset(preset))


@dataclass(frozen=True, slots=True)
class ScheduleState:
    """A schedule helper's active period, its next transition, and the levels around it.

    ``next_active`` says whether a block runs after ``next_event``; None means the
    week could not be read, so the period after the transition is unknown.
    """

    active: bool | None
    next_event: float | None = None
    level: BlockLevel = BlockLevel()
    next_active: bool | None = None
    next_level: BlockLevel = BlockLevel()


@dataclass(frozen=True, slots=True)
class Setbacks:
    """How far outside a comfort period the heating and cooling targets move, in K."""

    heat: float
    cool: float


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
    # comfort, eco, away, target, or setback while a schedule is followed.
    schedule_level: str | None = None


@dataclass(frozen=True, slots=True)
class _Period:
    target: float
    level: str
    reason: str


def _level_period(
    config: DigitalThermostat, mode: Mode, manual_target: float, level: BlockLevel
) -> _Period:
    """The target a block holds in the current mode, or manual comfort with the reason."""
    verb = "heating" if mode is Mode.HEAT else "cooling"
    if level.error is not None:
        return _Period(manual_target, "comfort", f"invalid schedule block: {level.error}")
    if level.preset is not None:
        target = config.presets_for(mode).get(level.preset)
        if target is None:
            return _Period(
                manual_target,
                "comfort",
                f"scheduled {level.preset.value} is not a {verb} preset",
            )
        return _Period(target, level.preset.value, f"scheduled {level.preset.value}")
    explicit = level.heat_target if mode is Mode.HEAT else level.cool_target
    if explicit is not None:
        return _Period(explicit, "target", "scheduled target")
    if level.heat_target is not None or level.cool_target is not None:
        return _Period(manual_target, "comfort", f"scheduled block has no {verb} target")
    return _Period(manual_target, "comfort", "scheduled comfort")


def _setback(mode: Mode, manual_target: float, setbacks: Setbacks) -> float:
    if mode is Mode.HEAT:
        return max(MIN_TARGET, manual_target - setbacks.heat)
    return min(MAX_TARGET, manual_target + setbacks.cool)


def _setbacks(config: DigitalThermostat, setbacks: Setbacks | None) -> Setbacks:
    if setbacks is not None:
        return setbacks
    assert config.schedule is not None
    return Setbacks(config.schedule.heat_setback, config.schedule.cool_setback)


def next_period_target(
    config: DigitalThermostat,
    mode: Mode,
    manual_target: float,
    schedule: ScheduleState,
    setbacks: Setbacks | None = None,
) -> float | None:
    """The target of the period that starts at the schedule's next transition.

    An unknown week assumes a comfort period follows an off period, as a helper
    without block data always does, and nothing to recover towards otherwise.
    """
    if config.schedule is None or mode is Mode.OFF:
        return None
    following = schedule.next_active
    if following is None:
        return manual_target if schedule.active is False else None
    if not following:
        return _setback(mode, manual_target, _setbacks(config, setbacks))
    return _level_period(config, mode, manual_target, schedule.next_level).target


def _warmer(mode: Mode, candidate: float, current: float) -> bool:
    """Whether reaching ``candidate`` from ``current`` is a recovery in this mode."""
    return candidate > current if mode is Mode.HEAT else candidate < current


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
    setbacks: Setbacks | None = None,
) -> ComfortTarget:
    """Choose a mode-specific preset, a scheduled level or setback, or a bounded early start.

    A block's data may choose a preset or an explicit target; anything it cannot
    use falls back to the manual comfort target and says why. Early start
    recovers towards the next period's target, from an off period or a lower
    block alike, using the explicitly configured warming or cooling rate. It
    never starts earlier than ``max_early_start``, never changes modes, and
    remains disabled by default. Missing schedule data falls back to the
    owner's manual comfort target.
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
    settings = config.schedule
    if schedule.active:
        current = _level_period(config, mode, manual_target, schedule.level)
        status = "invalid_block" if schedule.level.error is not None else "comfort"
    else:
        current = _Period(
            _setback(mode, manual_target, _setbacks(config, setbacks)),
            "setback",
            "scheduled setback",
        )
        status = "setback"
    held = ComfortTarget(
        current.target, current.reason, schedule_status=status, schedule_level=current.level
    )
    following = (
        next_period_target(config, mode, manual_target, schedule, setbacks) if future else None
    )
    if following is None or not _warmer(mode, following, current.target):
        return held
    assert event is not None
    next_level = (
        "comfort"
        if schedule.next_active is None
        else _level_period(config, mode, manual_target, schedule.next_level).level
    )
    if early_start_event == event and event - now <= settings.max_early_start:
        return ComfortTarget(
            following,
            "early start for the next scheduled period",
            True,
            "early_start",
            event,
            recovery_method="latched",
            schedule_level=next_level,
        )
    if settings.max_early_start <= 0 or temperature is None or not isfinite(temperature):
        return held
    error = following - temperature if mode is Mode.HEAT else temperature - following
    if error <= 0:
        return held
    rate = settings.heating_rate if mode is Mode.HEAT else settings.cooling_rate
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
            following,
            "early start for the next scheduled period",
            True,
            "early_start",
            event,
            seconds,
            method,
            next_level,
        )
    return ComfortTarget(
        current.target,
        current.reason,
        schedule_status=status,
        recovery_seconds=seconds,
        recovery_method=method,
        schedule_level=current.level,
    )
