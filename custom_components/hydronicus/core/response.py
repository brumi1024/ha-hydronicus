"""The response check: whether a zone's temperature moves toward its target while it is served.

A zone is served while it calls, a loop serving it is observed passing flow,
and the source, when the Plant has one, is observed running. Only that time
counts, so a pause for hot water, a defrost, or a mode dwell neither fails a
zone nor starts its clock over. The zone responds each time its temperature
moves ``ResponseCheck.progress`` toward the target from the furthest reading
since it last responded, so the lag of a slab, which keeps cooling for a while
after its pump starts, is no failure. The check only reports; it never changes
what any output does.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Final

from .model import Mode, ResponseCheck

# Readings come in steps such as 0.1 K, whose differences floats do not hit exactly.
_TOLERANCE: Final = 1e-6


@dataclass(frozen=True, slots=True)
class ZoneResponse:
    """What the response check carries for one calling zone between evaluations."""

    mode: Mode
    # The reading furthest from the target since the zone last responded, which
    # the temperature must move ``progress`` beyond; None until one is usable.
    reference: float | None = None
    # Seconds the zone has been served since it last responded.
    served: float = 0.0
    # When the zone was last seen served, from which the next evaluation counts on.
    served_at: float | None = None
    # When the served time reached the check's duration, until the zone responds.
    failed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "reference": self.reference,
            "served": self.served,
            "served_at": self.served_at,
            "failed_at": self.failed_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ZoneResponse:
        def number(key: str) -> float | None:
            value = data.get(key)
            return None if value is None else float(value)

        return cls(
            Mode(data["mode"]),
            number("reference"),
            float(data.get("served", 0.0)),
            number("served_at"),
            number("failed_at"),
        )


def check_response(
    config: ResponseCheck,
    previous: ZoneResponse | None,
    mode: Mode,
    *,
    calling: bool,
    served: bool,
    temperature: float | None,
    now: float,
) -> tuple[ZoneResponse | None, float | None]:
    """Advance a zone's response check by one evaluation.

    Returns the next state, None while the zone does not call in heat or cool,
    and when the check fails at the earliest if nothing changes, or None while
    it is not counting toward a failure.
    """
    if not calling or mode is Mode.OFF:
        return None, None
    state = previous if previous is not None and previous.mode is mode else ZoneResponse(mode)
    elapsed = state.served
    if state.served_at is not None and now > state.served_at:
        elapsed += now - state.served_at
    state = replace(state, served=elapsed, served_at=now if served else None)
    if temperature is not None:
        # The sign that turns a move toward the target positive.
        toward = 1.0 if mode is Mode.HEAT else -1.0
        reference = state.reference
        if reference is None or (temperature - reference) * toward < 0:
            state = replace(state, reference=temperature)
        elif (temperature - reference) * toward >= config.progress - _TOLERANCE:
            state = replace(state, reference=temperature, served=0.0, failed_at=None)
    if state.failed_at is None and state.served >= config.duration:
        state = replace(state, failed_at=now)
    if state.failed_at is not None or not served:
        return state, None
    return state, now + config.duration - state.served
