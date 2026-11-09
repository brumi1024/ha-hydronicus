"""Immutable hourly outdoor temperatures, with explicit coverage and freshness."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

MAX_FORECAST_POINTS = 169
MAX_FORECAST_HORIZON = 7 * 24 * 3600
MAX_POINT_INTERVAL = 3600.0


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    """An instantaneous outdoor temperature in Celsius at a UTC epoch second."""

    at: float
    temperature: float

    def __post_init__(self) -> None:
        if not isfinite(self.at) or not isfinite(self.temperature):
            raise ValueError("forecast point is not finite")
        if not -90 <= self.temperature <= 65:
            raise ValueError("forecast temperature is implausible")


@dataclass(frozen=True, slots=True)
class ForecastSnapshot:
    """A bounded forecast whose retrieval never implies a provider issue time.

    ``content_updated_at`` is the first local observation of this content, not
    the time its provider produced it. The adapter also bounds expiry by source
    health and horizon. Unknown issue time remains explicit in ``quality``.
    """

    source: str
    points: tuple[ForecastPoint, ...]
    received_at: float
    content_updated_at: float
    expires_at: float
    issued_at: float | None = None
    quality: str = "issue_time_unknown"

    def __post_init__(self) -> None:
        if not isinstance(self.points, tuple) or not 2 <= len(self.points) <= MAX_FORECAST_POINTS:
            raise ValueError("forecast needs bounded immutable points")
        times = (self.received_at, self.content_updated_at, self.expires_at)
        if not all(isfinite(value) for value in times):
            raise ValueError("forecast freshness is not finite")
        if self.content_updated_at > self.received_at or (
            self.issued_at is not None
            and (not isfinite(self.issued_at) or self.issued_at > self.received_at)
        ):
            raise ValueError("forecast freshness is in the future")
        if any(
            not 0 < right.at - left.at <= MAX_POINT_INTERVAL
            for left, right in zip(self.points, self.points[1:], strict=False)
        ):
            raise ValueError("forecast points are unordered, duplicated, or have gaps")

    @property
    def coverage_start(self) -> float:
        """First instant supported without extrapolation."""
        return self.points[0].at

    @property
    def coverage_end(self) -> float:
        """Last instant supported without extrapolation."""
        return self.points[-1].at

    def temperature_between(self, start: float, end: float, now: float) -> float | None:
        """Time-weight hourly points only over a fully covered, unexpired interval.

        Linear interpolation treats points as instantaneous temperatures. It
        never extends the first or last point into an unsupported interval.
        """
        if (
            not all(isfinite(value) for value in (start, end, now))
            or start >= end
            or not self.content_updated_at <= now < self.expires_at
            or start < self.coverage_start
            or end > self.coverage_end
        ):
            return None
        integral = 0.0
        for left, right in zip(self.points, self.points[1:], strict=False):
            lo, hi = max(start, left.at), min(end, right.at)
            if lo >= hi:
                continue
            slope = (right.temperature - left.temperature) / (right.at - left.at)
            integral += (left.temperature + slope * ((lo + hi) / 2 - left.at)) * (hi - lo)
        return integral / (end - start)


@dataclass(frozen=True, slots=True)
class OutdoorObservation:
    """A current reported temperature, kept separate from forecast points."""

    temperature: float
    reported_at: float
    source: str
    quality: str
