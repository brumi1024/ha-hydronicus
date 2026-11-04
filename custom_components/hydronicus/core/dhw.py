"""The source's domestic hot water: owned settings, adoption, hard limits, and a boost.

Hydronicus owns the DHW switch and setpoint of a source that has them, and
publishes them as its own entities. A change it did not command, such as one
made on the source's own controller, is adopted: it becomes Hydronicus's value
and is never written back. A boost raises the setpoint for a bounded time and
then restores the owned value; its end is persisted, so a restart restores it
on time, and a setpoint that is unavailable at the end is restored once it is
back. ``dhw_step`` is pure: ``step()`` calls it with the physical outputs, the
reconciler's calls in flight, and the owner's last command.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from math import isfinite
from typing import Any

from .model import DISINFECT_RETRY, Dhw, NumericTarget, OutputTarget, SwitchTarget

__all__ = ["DhwCommand", "DhwResult", "DhwSchedule", "DhwState", "dhw_step"]


@dataclass(frozen=True, slots=True)
class DhwCommand:
    """What the owner last asked of the DHW through Hydronicus, stamped when asked."""

    at: float
    on: bool | None = None
    target: float | None = None
    # A boost to this temperature for ``boost_for`` seconds, bounded by ``Dhw.max_boost``.
    boost: float | None = None
    boost_for: float | None = None
    end_boost: bool = False


@dataclass(frozen=True, slots=True)
class DhwState:
    """The owned DHW settings and what was last seen of them, persisted with the State."""

    on: bool | None = None
    target: float | None = None
    # The last usable observed values, so that only a change of value is adopted,
    # not an output that becomes available again.
    seen_on: bool | None = None
    seen_target: float | None = None
    boost: float | None = None
    boost_until: float | None = None
    # When the last applied command was asked, so that each applies once.
    command_at: float | None = None
    # The disinfection cycle: when the last one succeeded, or when its clock began
    # for a tank that has had none; when the one in progress started, since when
    # its tank has held the temperature, and when the last one timed out.
    disinfect_last: float | None = None
    disinfect_started: float | None = None
    disinfect_held: float | None = None
    disinfect_failed: float | None = None
    # When a disinfection cycle last held its temperature, which a new tank lacks.
    disinfect_done: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "disinfect_last": self.disinfect_last,
            "disinfect_started": self.disinfect_started,
            "disinfect_held": self.disinfect_held,
            "disinfect_failed": self.disinfect_failed,
            "disinfect_done": self.disinfect_done,
            "on": self.on,
            "target": self.target,
            "seen_on": self.seen_on,
            "seen_target": self.seen_target,
            "boost": self.boost,
            "boost_until": self.boost_until,
            "command_at": self.command_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DhwState:
        def number(key: str) -> float | None:
            value = data.get(key)
            return None if value is None else float(value)

        def flag(key: str) -> bool | None:
            value = data.get(key)
            return None if value is None else bool(value)

        return cls(
            on=flag("on"),
            target=number("target"),
            seen_on=flag("seen_on"),
            seen_target=number("seen_target"),
            boost=number("boost"),
            boost_until=number("boost_until"),
            command_at=number("command_at"),
            disinfect_last=number("disinfect_last"),
            disinfect_started=number("disinfect_started"),
            disinfect_held=number("disinfect_held"),
            disinfect_failed=number("disinfect_failed"),
            disinfect_done=number("disinfect_done"),
        )


@dataclass(frozen=True, slots=True)
class DhwSchedule:
    """The DHW schedule helper now: whether a block runs, and the target its data names."""

    active: bool | None
    target: float | None = None


@dataclass(frozen=True, slots=True)
class DhwResult:
    state: DhwState
    # The targets of the DHW outputs; empty while Hydronicus must not command them.
    targets: Mapping[str, OutputTarget] = field(default_factory=dict)
    reason: str = ""
    # What changed that the owner should hear about: adoptions, clamps, and boosts.
    events: tuple[str, ...] = ()


def dhw_step(
    config: Dhw,
    switch: bool | None,
    setpoint: float | None,
    ours: Callable[[str], bool],
    state: DhwState,
    command: DhwCommand | None,
    now: float,
    reached: Callable[[float], bool],
    *,
    commands: bool,
    schedule: DhwSchedule | None = None,
    tank: float | None = None,
    window: bool | None = None,
) -> DhwResult:
    """Adopt changes made elsewhere, apply the owner's command, and choose the targets.

    ``switch`` and ``setpoint`` are the physical outputs' usable values, None
    while unknown. ``ours(entity)`` says whether a value an output shows is one
    of Hydronicus's calls landing. ``commands`` is false while Hydronicus must
    not command the source, such as during a handover or the off sequence; the
    owned values then still follow what is seen.

    A running block of ``schedule`` that names a target holds it instead of the
    owned target; a boost still wins. A due disinfection cycle wins over both,
    beyond the DHW maximum, while ``tank`` shows how hot the tank is and
    ``window`` whether it may start.
    """
    events: list[str] = []

    def own(value: float, what: str) -> float | None:
        """A new owned value within the hard limits, logged when it was outside them."""
        clamped = _clamp(config, value)
        if clamped is not None and clamped != value:
            events.append(f"{what} {value:g} °C is outside its limits; using {clamped:g} °C")
        return clamped

    on, target, boost, boost_until = state.on, state.target, state.boost, state.boost_until
    seen_on, seen_target = state.seen_on, state.seen_target
    scheduled = (
        schedule.target
        if schedule is not None and schedule.active and schedule.target is not None
        else None
    )

    if config.switch is not None and switch is not None and switch != seen_on:
        if on is not None and switch != on and not ours(config.switch):
            events.append(f"DHW was turned {'on' if switch else 'off'} elsewhere; adopted")
            on = switch
        elif on is None:
            on = switch
        seen_on = switch
    if config.setpoint is not None and setpoint is not None and setpoint != seen_target:
        shown = (
            config.disinfect.temperature
            if config.disinfect is not None and state.disinfect_started is not None
            else _clamp(
                config,
                boost
                if boost_until is not None
                else scheduled
                if scheduled is not None
                else target,
            )
        )
        if target is not None and setpoint != shown and not ours(config.setpoint):
            events.append(f"DHW target changed elsewhere to {setpoint:g} °C; adopted")
            target = own(setpoint, "DHW target")
            if boost_until is not None:
                events.append("the DHW boost ends without restoring, since a value was chosen")
                boost = boost_until = None
        elif target is None:
            target = own(setpoint, "DHW target")
        seen_target = setpoint

    command_at = state.command_at
    if command is not None and (command_at is None or command.at > command_at):
        command_at = command.at
        if command.on is not None:
            on = command.on
        if command.target is not None:
            target = own(command.target, "DHW target")
        if command.end_boost and boost_until is not None:
            boost = boost_until = None
            events.append("the DHW boost was ended")
        if command.boost is not None and (boost := own(command.boost, "DHW boost")) is not None:
            duration = min(command.boost_for or config.max_boost, config.max_boost)
            boost_until = now + duration
            events.append(f"the DHW boost raises the target to {boost:g} °C")
    if boost_until is not None and reached(boost_until):
        events.append(f"the DHW boost ended; restoring {_clamp(config, target):g} °C")
        boost = boost_until = None

    wanted = _clamp(
        config,
        boost if boost_until is not None else scheduled if scheduled is not None else target,
    )
    cycle = _disinfect(config, state, on, tank, window, now, reached, commands, events)
    if cycle.running and config.disinfect is not None:
        wanted = config.disinfect.temperature
    targets: dict[str, OutputTarget] = {}
    if commands:
        if config.switch is not None and on is not None:
            targets[config.switch] = SwitchTarget(on)
        if config.setpoint is not None and wanted is not None:
            targets[config.setpoint] = NumericTarget(wanted, config.tolerance)
    if wanted is None:
        reason = "on" if on else "off" if on is not None else "unknown"
    elif cycle.running:
        reason = f"on, disinfection cycle at {wanted:g} °C"
    elif boost_until is not None:
        reason = f"{'on' if on is not False else 'off'}, boosted to {wanted:g} °C"
    elif scheduled is not None:
        reason = f"{'on' if on is not False else 'off'}, scheduled {wanted:g} °C"
    else:
        reason = f"{'on' if on is not False else 'off'}, {wanted:g} °C"
    next_state = replace(
        state,
        on=on,
        target=target,
        seen_on=seen_on,
        seen_target=seen_target,
        boost=boost,
        boost_until=boost_until,
        command_at=command_at,
        disinfect_last=cycle.last,
        disinfect_started=cycle.started,
        disinfect_held=cycle.held,
        disinfect_failed=cycle.failed,
        disinfect_done=cycle.done if cycle.done is not None else state.disinfect_done,
    )
    return DhwResult(next_state, targets, reason, tuple(events))


@dataclass(frozen=True, slots=True)
class _Cycle:
    last: float | None
    started: float | None = None
    held: float | None = None
    failed: float | None = None
    done: float | None = None

    @property
    def running(self) -> bool:
        return self.started is not None


def _disinfect(
    config: Dhw,
    state: DhwState,
    on: bool | None,
    tank: float | None,
    window: bool | None,
    now: float,
    reached: Callable[[float], bool],
    commands: bool,
    events: list[str],
) -> _Cycle:
    """Start, prove, finish, or give up the disinfection cycle.

    Its clock starts when it is first seen, so a new tank is not heated at once.
    It runs only while the DHW is on and Hydronicus may command the source, and
    a missing tank reading neither proves nor resets the hold.
    """
    cycle = config.disinfect
    if cycle is None:
        return _Cycle(None)
    last = state.disinfect_last if state.disinfect_last is not None else now
    started, held, failed = state.disinfect_started, state.disinfect_held, state.disinfect_failed
    if started is not None and (on is False or not commands):
        events.append("the disinfection cycle stopped, since the DHW may not run")
        return _Cycle(last, failed=failed)
    if started is None:
        due = last + cycle.interval
        if not reached(due) or on is False or not commands or window is False:
            return _Cycle(last, failed=failed)
        events.append(f"the disinfection cycle starts, to {cycle.temperature:g} °C")
        started, held = now, None
    if tank is not None:
        if tank >= cycle.temperature - config.tolerance:
            held = now if held is None else held
        else:
            held = None
    if held is not None and reached(held + cycle.hold):
        events.append("the disinfection cycle held its temperature and is done")
        return _Cycle(now, failed=failed, done=now)
    if reached(started + cycle.timeout):
        events.append(
            f"the disinfection cycle did not hold {cycle.temperature:g} °C within its timeout"
        )
        # Try again a day later rather than after a whole interval.
        return _Cycle(now - cycle.interval + DISINFECT_RETRY, failed=now)
    return _Cycle(last, started, held, failed)


def _clamp(config: Dhw, value: float | None) -> float | None:
    """The setpoint within the hard limits, at the setpoint's resolution."""
    if value is None or not isfinite(value):
        return None
    if config.step is not None:
        value = config.step * round(value / config.step)
    return min(config.maximum, max(config.minimum, value))
