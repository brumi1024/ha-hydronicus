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
zones have called for ``learn_after`` without a moment when none of them called,
and the lead zone's filtered error has stayed within ``SETTLE_STEP`` for
``SETTLE_TIME``: a room that still gets closer to its target is warming up, and
one that stopped short of it has a curve that is too low. While no lead zone
calls, the learned part falls as if the room were the deadband above its
target, because a satisfied zone got enough.

The lead zones are one witness, not one each: the curve heats them all, so
their calls together, not the current lead's own, measure how long the house
has been short. The lead moves between them whenever another calls colder, and
each pauses on its own thermostat while another keeps calling; counting from
the lead's own call would restart the wait at every such switch, which in a
house of two slow zones leaves the learned part almost never free to rise,
while it falls in every hour that none calls. Counted over the zones together,
the rising side waits for exactly what the falling side acts on, a moment when
no lead zone calls, so what mild weather taught it is unlearned once the cold
leaves the rooms short, without a reset. A zone that just resumed and still
warms is held by its error, which still shrinks.

A change of the lead zone's own target, a setback or its end, and its first
reading, start a settling: the room is on its way to a new target, which says
nothing about the curve, so the learned part keeps its value until both the
reading and the filtered error are within the deadband of the target, or the
filtered error is still as above, which a curve that is off leaves it. A
satisfied zone does not lower it until ``learn_after`` after that arrival
either, since a lowered target or the end of a recovery satisfies a zone by
itself. Beyond ``LEARN_BAND`` from the target it learns nothing.

While the lead zone calls and its filtered error stays still within the
deadband, the learned part moves toward the shift that the setpoint written
last delivers beyond the curve, the offset, and the proportional part. A
whole-degree setpoint hides a learned part up to half a degree off, which
nothing in the room would show, so this is what settles it at the curve's real
shortfall rather than wherever its last rise left it.

It also holds its value whenever the heating curve cannot act on it: hot water
or a warm-up has the source, the request is held off, or the Plant does not
heat on Hydronicus's curve; while the rooms are not at the comfort the curve is
set for, because the Plant is away or the lead zone holds its away level; and
while the trim, or the supply target it shifts, is at its bound in the direction
it would move, so it never winds up beyond what it can deliver. The caller
decides these holds and passes them as ``held``; the filter, the proportional
part, and the settling go on through them.

The filter starts again from the reading after a gap longer than ``gap`` or a
clock that stepped backwards, as the damped outdoor temperature does, and that
evaluation learns nothing. A change of lead zone keeps both the filter and the
learned part: the filter smooths the step between the two zones' errors, and
what was learned belongs to the curve, not to a zone. Nor does it start a
settling: each lead zone's target is remembered from when it last led, and only
a zone that leads with another target than then settles. Zones with targets of
their own, such as 22 °C in the living room and 21.5 °C in a bedroom, take turns
to lead every few hours, and a settling at every turn would hold the learned
part for most of a cold day. A zone whose target changed while another led
settles once it leads; one whose setback came and went meanwhile is back where
it was, and is held only while it is far from its target or still gets closer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from math import exp, inf, isfinite
from typing import Any, Final

from .model import RoomInfluence

__all__ = ["LEARN_BAND", "SETTLE_STEP", "SETTLE_TIME", "RoomTrim", "RoomTrimState", "room_trim"]

# The learned part's rate is configured per hour.
_HOUR: Final = 3600.0
# The learned part learns only while the filtered error is within this many
# kelvin: a larger one is a recovery or a setback, not a curve to correct.
LEARN_BAND: Final = 1.0
# A settling room still gets closer to its target while its filtered error
# shrinks by this many kelvin within this many seconds.
SETTLE_STEP: Final = 0.05
SETTLE_TIME: Final = 7200.0


@dataclass(frozen=True, slots=True)
class RoomTrimState:
    """The filter, the learned part, and the settling after a target change, persisted."""

    # The lead zone's filtered error in K, None before the first reading.
    error: float | None = None
    at: float | None = None
    # The learned part in K.
    learned: float = 0.0
    # Each lead zone's target when it last led, whether the lead zone still
    # settles after its target changed, and when it last arrived.
    targets: Mapping[str, float] = field(default_factory=dict)
    settling: bool = False
    arrived: float | None = None
    # The filtered error when it last moved by ``SETTLE_STEP``, and when.
    moved: float | None = None
    moved_at: float | None = None
    # Since when one lead zone or another has called without a moment when none
    # did, None while none calls.
    calling_since: float | None = None

    def steady(self, now: float) -> bool:
        """Whether the filtered error has not moved for ``SETTLE_TIME``."""
        return self.moved_at is not None and self.moved_at <= now - SETTLE_TIME

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.error,
            "at": self.at,
            "learned": self.learned,
            "targets": dict(self.targets),
            "settling": self.settling,
            "arrived": self.arrived,
            "moved": self.moved,
            "moved_at": self.moved_at,
            "calling_since": self.calling_since,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RoomTrimState:
        def number(key: str) -> float | None:
            value = data.get(key)
            return None if value is None or not isfinite(float(value)) else float(value)

        error, at, learned = number("error"), number("at"), number("learned")
        if error is None or at is None:
            error, at = None, None
        moved, moved_at = number("moved"), number("moved_at")
        if moved is None or moved_at is None:
            moved, moved_at = None, None
        stored = data.get("targets")
        targets = {
            str(slug): float(value)
            for slug, value in (stored.items() if isinstance(stored, Mapping) else ())
            if value is not None and isfinite(float(value))
        }
        return cls(
            error,
            at,
            0.0 if learned is None else learned,
            targets,
            bool(data.get("settling", False)),
            number("arrived"),
            moved,
            moved_at,
            number("calling_since"),
        )


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


def _settle(
    previous: RoomTrimState,
    lead: str | None,
    target: float | None,
    error: float,
    filtered: float,
    now: float,
    deadband: float,
) -> RoomTrimState:
    """Follow the target and how the filtered error moves: everything but the error and learned."""
    moved, moved_at = previous.moved, previous.moved_at
    if moved is None or moved_at is None or now < moved_at or abs(filtered - moved) > SETTLE_STEP:
        moved, moved_at = filtered, now
    settling, targets = previous.settling, previous.targets
    if lead is not None and target is not None:
        before = targets.get(lead)
        if before is None or abs(target - before) > 1e-6:
            settling = True
        targets = {**targets, lead: target}
    state = RoomTrimState(
        targets=targets,
        settling=settling,
        arrived=previous.arrived,
        moved=moved,
        moved_at=moved_at,
    )
    if settling and ((abs(error) <= deadband and abs(filtered) <= deadband) or state.steady(now)):
        # Within the deadband, both the reading and the filtered error, which
        # lags behind a new target, or still: the room has arrived where it goes.
        state = replace(state, settling=False, arrived=now)
    return state


def _calling_since(
    previous: RoomTrimState, now: float, calling: float | None, gap: float
) -> float | None:
    """Since when the lead zones have called without a moment when none did.

    The run the State recorded goes on while some lead zone still calls, unless
    the last evaluation is older than ``gap`` or ahead of ``now``: a pause may
    have passed unseen, so only the current calls count.
    """
    if calling is None:
        return None
    since, at = previous.calling_since, previous.at
    if since is None or at is None or now < at or now > at + gap:
        return calling
    return min(since, calling)


def room_trim(
    influence: RoomInfluence,
    previous: RoomTrimState,
    now: float,
    lead: str | None,
    error: float | None,
    *,
    gap: float,
    calling: float | None,
    target: float | None = None,
    delivered: float | None = None,
    held: str | None = None,
    headroom: tuple[float, float] = (-inf, inf),
    reset: bool = False,
) -> RoomTrim:
    """Step the room trim to ``now`` from the lead zone's ``error``.

    ``error`` is the lead zone's target minus its temperature, None while no
    lead zone reads, and ``target`` is that target. ``calling`` is when the
    longest of the lead zones' current calls for heat began, None while none
    calls; the State joins it to the calls before, so the wait before the
    learned part rises goes on across a change of lead zone and across one
    zone's pause while another calls.
    ``delivered`` is the shift beyond the curve and the offset that the setpoint
    written last gives, None without one. ``held`` says why the learned part may
    not change now, and ``headroom`` is how far down and up a shift still moves
    the supply target before its bounds clamp it. ``reset`` forgets the learned
    part first.
    """
    learning = influence.learn_rate > 0
    learned = _clamp(0.0 if reset or not learning else previous.learned, influence.learn_limit)
    calling_since = _calling_since(previous, now, calling, gap)
    if error is None or not isfinite(error):
        # Nothing to filter: the filter waits for the next reading, which the
        # gap rule restarts it from when it comes too late.
        why = (held or "no lead zone reads its temperature") if learning else None
        state = replace(previous, learned=learned, calling_since=calling_since)
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
    followed = _settle(previous, lead, target, error, filtered, now, deadband)
    if learning and held is None:
        mean = (_outside(before, deadband) + _outside(filtered, deadband)) / 2
        arrived = followed.arrived
        recent = followed.settling or arrived is None or now - arrived < influence.learn_after
        pulling = (
            calling_since is not None
            and mean == 0
            and delivered is not None
            and followed.steady(now)
        )
        if calling_since is None and not recent:
            # A satisfied zone got enough heat, so it counts as at least the
            # deadband above its target; but not soon after a target change,
            # when a lowered target, or the end of a recovery, satisfies it.
            mean = min(mean, -deadband)
        elif pulling and delivered is not None:
            # Calling and still within the deadband: what the setpoint delivers
            # is what the room needs.
            mean = delivered - proportional - learned
        rising = mean > 0 and not pulling
        low, high = headroom
        shift = proportional + learned
        if elapsed <= 0:
            held = "the room trim starts again from the reading"
        elif previous.settling or followed.settling:
            held = "the lead zone settles after a change of its target"
        elif abs(filtered) > LEARN_BAND:
            held = "the lead zone is far from its target"
        elif rising and (calling_since is None or now - calling_since < influence.learn_after):
            held = "the lead zones have not called long enough"
        elif rising and not followed.steady(now):
            held = "the lead zone still gets closer to its target"
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
        replace(followed, error=filtered, at=now, learned=learned, calling_since=calling_since),
    )
