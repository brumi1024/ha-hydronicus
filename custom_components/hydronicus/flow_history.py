"""How long the loops of a Plant have passed flow, for the runtime and duty cycle sensors.

The runtime updates ``FlowHistory`` after every evaluation with the loops that
pass flow and the zones they serve, which is only observed flow while the Plant
is live, and once a minute while a loop flows. The time since the last update
counts as flowing as that update said, so time before the first update after
loading, such as while Home Assistant was stopped, never counts.

Each loop keeps its total, and each zone keeps how long it had flow in each
clock hour, back to ``WINDOW_HOURS`` before the current one, which bounds the
history whatever the loops do. The runtime persists it with its State.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

HOUR: Final = 3600
# The duty cycle covers this many whole hours before the current one.
WINDOW_HOURS: Final = 24
# How often the sensors are refreshed while a loop flows, in seconds.
REFRESH: Final = 60.0


class FlowHistory:
    """Each loop's total flow time, and each zone's flow time by clock hour."""

    def __init__(
        self,
        totals: Mapping[str, float] | None = None,
        hours: Mapping[str, Mapping[int, float]] | None = None,
    ) -> None:
        # Seconds of flow, by ``str(LoopRef)``.
        self._totals: dict[str, float] = dict(totals or {})
        # Seconds of flow by hour, counted from the epoch, by zone slug.
        self._hours: dict[str, dict[int, float]] = {
            zone: dict(by_hour) for zone, by_hour in (hours or {}).items() if by_hour
        }
        # The last update since loading, and what flowed then; None counts nothing.
        self._at: float | None = None
        self._loops: frozenset[str] = frozenset()
        self._zones: frozenset[str] = frozenset()

    def update(
        self,
        now: float,
        loops: Iterable[str] | None = None,
        zones: Iterable[str] | None = None,
    ) -> None:
        """Count the time since the last update as it flowed then, then take what flows now.

        ``loops`` and ``zones`` are what passes flow from now on; None keeps what
        flowed. A clock that went back counts nothing.
        """
        start = self._at
        if start is not None and now > start:
            for loop in self._loops:
                self._totals[loop] = self._totals.get(loop, 0.0) + now - start
            for zone in self._zones:
                self._count(zone, start, now)
        self._at = now
        if loops is not None:
            self._loops = frozenset(loops)
        if zones is not None:
            self._zones = frozenset(zones)
        # The current hour and the window before it are kept.
        oldest = _hour(now) - WINDOW_HOURS
        for zone in tuple(self._hours):
            by_hour = {hour: time for hour, time in self._hours[zone].items() if hour >= oldest}
            if by_hour:
                self._hours[zone] = by_hour
            else:
                del self._hours[zone]

    def pause(self, now: float) -> None:
        """Count up to now, and nothing more until the next update with what flows."""
        self.update(now, (), ())
        self._at = None

    def _count(self, zone: str, start: float, end: float) -> None:
        by_hour = self._hours.setdefault(zone, {})
        # Time before the oldest hour kept is dropped anyway, however far the clock jumped.
        start = max(start, float((_hour(end) - WINDOW_HOURS) * HOUR))
        while start < end:
            hour = _hour(start)
            stop = min(end, float((hour + 1) * HOUR))
            by_hour[hour] = by_hour.get(hour, 0.0) + stop - start
            start = stop

    def runtime(self, loop: str) -> float:
        """How long a loop has passed flow, in seconds, up to the last update."""
        return self._totals.get(loop, 0.0)

    def duty_cycle(self, zone: str) -> float | None:
        """The share of time a zone had flow, in percent, or None before the first update.

        It covers the ``WINDOW_HOURS`` whole hours before the hour of the last
        update, so it changes only when a new hour begins.
        """
        if self._at is None:
            return None
        current = _hour(self._at)
        flowed = sum(
            time
            for hour, time in self._hours.get(zone, {}).items()
            if current - WINDOW_HOURS <= hour < current
        )
        return 100.0 * flowed / (WINDOW_HOURS * HOUR)

    def next_refresh(self, now: float) -> float | None:
        """When the sensors change next without an evaluation, if they do.

        While a loop flows, that is every ``REFRESH``; while a zone's hours still
        hold flow, the next hour, which moves the duty cycle's window.
        """
        times: list[float] = []
        if self._loops:
            times.append(now + REFRESH)
        if self._hours:
            times.append(float((_hour(now) + 1) * HOUR))
        return min(times, default=None)

    def forget_except(self, loops: set[str], zones: set[str]) -> None:
        """Drop the loops and zones the Plant no longer has."""
        self._totals = {loop: time for loop, time in self._totals.items() if loop in loops}
        self._hours = {zone: hours for zone, hours in self._hours.items() if zone in zones}

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtimes": dict(sorted(self._totals.items())),
            "hours": {
                zone: {str(hour): time for hour, time in sorted(by_hour.items())}
                for zone, by_hour in sorted(self._hours.items())
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FlowHistory:
        return cls(
            {loop: float(time) for loop, time in data.get("runtimes", {}).items()},
            {
                zone: {int(hour): float(time) for hour, time in by_hour.items()}
                for zone, by_hour in data.get("hours", {}).items()
            },
        )


def _hour(timestamp: float) -> int:
    return int(timestamp // HOUR)
