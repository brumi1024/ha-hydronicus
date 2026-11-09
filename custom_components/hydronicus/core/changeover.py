"""Automatic heat and cool changeover from a slowly averaged outdoor temperature."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import exp, isfinite
from typing import Any

from .demand import Reading
from .model import Changeover, Mode


@dataclass(frozen=True, slots=True)
class ChangeoverState:
    """The averaged outdoor temperature, the mode it chose, and when that mode began.

    It is persisted with the State, so a restart neither forgets the average nor
    shortens the minimum time between two changes.
    """

    average: float | None = None
    averaged_at: float | None = None
    mode: Mode = Mode.HEAT
    changed: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "average": self.average,
            "averaged_at": self.averaged_at,
            "mode": self.mode.value,
            "changed": self.changed,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ChangeoverState:
        def optional(key: str) -> float | None:
            value = data.get(key)
            return None if value is None else float(value)

        mode = Mode(data.get("mode", Mode.HEAT))
        return cls(
            optional("average"),
            optional("averaged_at"),
            mode if mode is not Mode.OFF else Mode.HEAT,
            optional("changed"),
        )


@dataclass(frozen=True, slots=True)
class ChangeoverResult:
    """The next state, why its mode is what it is, and when to look again."""

    state: ChangeoverState
    reason: str
    # When the minimum time between changes ends for a change that waits for it.
    due: float | None = None


def changeover(
    config: Changeover,
    sensors: Mapping[str, Reading],
    now: float,
    previous: ChangeoverState,
) -> ChangeoverResult:
    """Choose heat or cool from the averaged outdoor temperature, with a neutral band.

    The average is a first-order filter with ``averaging`` as its time constant,
    started again from the reading after a gap longer than the reading's
    ``max_age``. It changes to cool at or above ``cool_above`` and to heat at or
    below ``heat_below``, at most once per ``min_dwell``; between them, and while
    the reading is not usable, the mode stays as it is.
    """
    reading = sensors.get(config.outdoor_sensor)
    if (
        reading is None
        or reading.value is None
        or not isfinite(reading.value)
        or not isfinite(reading.updated)
        or now >= reading.updated + config.max_age
    ):
        return ChangeoverResult(
            previous, f"auto: outdoor temperature not usable, staying in {previous.mode}"
        )
    average = reading.value
    if (
        previous.average is not None
        and previous.averaged_at is not None
        and previous.averaged_at <= now <= previous.averaged_at + config.max_age
    ):
        weight = 1.0 - exp(-(now - previous.averaged_at) / config.averaging)
        average = previous.average + weight * (reading.value - previous.average)
    wanted = previous.mode
    if average >= config.cool_above:
        wanted = Mode.COOL
    elif average <= config.heat_below:
        wanted = Mode.HEAT
    state = ChangeoverState(average, now, previous.mode, previous.changed)
    band = f"mean {average:.1f} °C, heat at or below {config.heat_below:g}, cool at or above "
    band += f"{config.cool_above:g}"
    if wanted is previous.mode:
        return ChangeoverResult(state, f"auto: {previous.mode}, {band}")
    if previous.changed is not None and now < previous.changed + config.min_dwell:
        until = previous.changed + config.min_dwell
        return ChangeoverResult(
            state, f"auto: {previous.mode} until its minimum time ends, {band}", until
        )
    return ChangeoverResult(ChangeoverState(average, now, wanted, now), f"auto: {wanted}, {band}")
