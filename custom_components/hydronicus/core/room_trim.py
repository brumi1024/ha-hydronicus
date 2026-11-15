"""The room trim: a small, slow, self-correcting shift of the heating curve.

The lead zone's error, its heating target minus its temperature, passes through
a first-order filter, so slow emitters do not make the supply swing with every
reading. Inside the deadband the filtered error counts as zero, and beyond it
only its part outside the band counts, so the trim never jumps at its edge.

The trim has two parts. The proportional part is that error times ``factor``.
The learned part integrates it at ``learn_rate``, so a curve that is set too low
or too high is corrected over days without the room staying off its target.
Both together, clamped to ``limit``, are what the heating curve receives.

A zone with an on and off thermostat is a poor witness of its curve: after
every pause its slow emitters need hours to warm again, and the room dips below
its target whatever the curve. So the learned part rises only once the lead
zone has called for ``learn_after`` without a pause, which a curve that is too
low makes it do, and while no lead zone calls it falls as if the room were the
deadband above its target, because a satisfied zone got enough. Beyond
``LEARN_BAND`` from the target, a setback or a recovery, it learns nothing.

It also holds its value whenever the heating curve cannot act on it: hot water
or a warm-up has the source, the request is held off, or the Plant does not
heat on Hydronicus's curve; and while the trim, or the supply target it shifts,
is at its bound in the direction it would move, so it never winds up beyond
what it can deliver.

The filter starts again from the reading after a gap longer than ``gap`` or a
clock that stepped backwards, as the damped outdoor temperature does, and that
evaluation learns nothing. A change of lead zone keeps both the filter and the
learned part: the filter smooths the step between the two zones' errors, and
what was learned belongs to the curve, not to a zone.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import exp, inf, isfinite
from typing import Any, Final

from .model import RoomInfluence

__all__ = ["LEARN_BAND", "RoomTrim", "RoomTrimState", "room_trim"]

# The learned part's rate is configured per hour.
_HOUR: Final = 3600.0
# The learned part learns only while the filtered error is within this many
# kelvin: a larger one is a recovery or a setback, not a curve to correct.
LEARN_BAND: Final = 1.0


@dataclass(frozen=True, slots=True)
class RoomTrimState:
    """The filtered error, when it was last updated, and the learned part, persisted."""

    # The lead zone's filtered error in K, None before the first reading.
    error: float | None = None
    at: float | None = None
    # The learned part in K.
    learned: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.error, "at": self.at, "learned": self.learned}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RoomTrimState:
        def number(key: str) -> float | None:
            value = data.get(key)
            return None if value is None else float(value)

        error, at, learned = number("error"), number("at"), number("learned")
        if error is None or at is None:
            error, at = None, None
        return cls(error, at, 0.0 if learned is None or not isfinite(learned) else learned)


@dataclass(frozen=True, slots=True)
class RoomTrim:
    """This evaluation's room trim, its parts, and what the State keeps for the next one."""

    # The total, which shifts the heating curve, and its two parts, in K.
    total: float
    proportional: float
    learned: float
    # The lead zone and its filtered error, None while no lead zone reads.
    lead: str | None
    error: float | None
    # Why the learned part keeps its value now, None while it learns or is off.
    held: str | None
    state: RoomTrimState


def _outside(error: float, deadband: float) -> float:
    """The part of the error beyond the deadband, zero inside it."""
    if error > deadband:
        return error - deadband
    if error < -deadband:
        return error + deadband
    return 0.0


def _clamp(value: float, limit: float) -> float:
    return min(limit, max(-limit, value))


def room_trim(
    influence: RoomInfluence,
    previous: RoomTrimState,
    now: float,
    lead: str | None,
    error: float | None,
    *,
    gap: float,
    calling_since: float | None,
    held: str | None = None,
    headroom: tuple[float, float] = (-inf, inf),
    reset: bool = False,
) -> RoomTrim:
    """Step the room trim to ``now`` from the lead zone's ``error``.

    ``error`` is the lead zone's target minus its temperature, None while no
    lead zone reads, and ``calling_since`` is since when it has called for heat
    without a pause, None while it does not call. ``held`` says why the learned
    part may not change now, and ``headroom`` is how far down and up a shift
    still moves the supply target before its bounds clamp it. ``reset`` forgets
    the learned part first.
    """
    learning = influence.learn_rate > 0
    learned = _clamp(0.0 if reset or not learning else previous.learned, influence.learn_limit)
    if error is None or not isfinite(error):
        # Nothing to filter: the filter waits for the next reading, which the
        # gap rule restarts it from when it comes too late.
        why = (held or "no lead zone reads its temperature") if learning else None
        state = RoomTrimState(previous.error, previous.at, learned)
        return RoomTrim(_clamp(learned, influence.limit), 0.0, learned, None, None, why, state)

    if (
        previous.error is None
        or previous.at is None
        or now < previous.at
        or now > previous.at + gap
    ):
        filtered, before, elapsed = error, error, 0.0
    else:
        before, elapsed = previous.error, now - previous.at
        weight = 1.0 if influence.smoothing <= 0 else 1.0 - exp(-elapsed / influence.smoothing)
        filtered = before + weight * (error - before)

    deadband = influence.deadband
    proportional = _clamp(influence.factor * _outside(filtered, deadband), influence.limit)
    if learning and held is None:
        mean = (_outside(before, deadband) + _outside(filtered, deadband)) / 2
        if calling_since is None:
            # A satisfied zone got enough heat, so it counts as at least the
            # deadband above its target.
            mean = min(mean, -deadband)
        low, high = headroom
        shift = proportional + learned
        if elapsed <= 0:
            held = "the room trim starts again from the reading"
        elif abs(filtered) > LEARN_BAND:
            held = "the lead zone is far from its target"
        elif mean > 0 and (calling_since is None or now - calling_since < influence.learn_after):
            held = "the lead zone has not called long enough"
        elif (mean > 0 and shift >= min(influence.limit, high)) or (
            mean < 0 and shift <= max(-influence.limit, low)
        ):
            held = "the room trim is at its limit"
        else:
            change = influence.learn_rate / _HOUR * mean * elapsed
            learned = _clamp(learned + change, influence.learn_limit)
    total = _clamp(proportional + learned, influence.limit)
    return RoomTrim(
        total,
        proportional,
        learned,
        lead,
        filtered,
        held if learning else None,
        RoomTrimState(filtered, now, learned),
    )
