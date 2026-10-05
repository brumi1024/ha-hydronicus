"""Read the public hourly weather action outside Plant evaluation.

Home Assistant 2026.9.3 supplies converted temperatures but no provider issue
timestamp. Source health, first-seen content age, and future coverage bound
usefulness; a successful reread alone cannot extend content expiry.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from math import isfinite
from random import uniform
from typing import Any

from homeassistant.components.weather import SERVICE_GET_FORECASTS
from homeassistant.components.weather.const import (
    ATTR_WEATHER_TEMPERATURE,
    ATTR_WEATHER_TEMPERATURE_UNIT,
    DOMAIN,
    WeatherEntityFeature,
)
from homeassistant.const import (
    ATTR_SUPPORTED_FEATURES,
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_HOMEASSISTANT_STOP,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .core.forecast import (
    MAX_FORECAST_HORIZON,
    MAX_FORECAST_POINTS,
    ForecastPoint,
    ForecastSnapshot,
    OutdoorObservation,
)
from .core.model import WeatherConfig

REFRESH_SECONDS = 3600
REQUEST_TIMEOUT = 30.0
MAX_RESPONSE_ROWS = 512
_MISSING = frozenset({STATE_UNAVAILABLE, STATE_UNKNOWN})


def _celsius(value: object, unit: object) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or unit not in (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT)
    ):
        raise ValueError("unsupported temperature value or unit")
    result = TemperatureConverter.convert(float(value), str(unit), UnitOfTemperature.CELSIUS)
    if not isfinite(result) or not -90 <= result <= 65:
        raise ValueError("invalid outdoor temperature")
    return result


def _timestamp(value: object) -> float:
    if not isinstance(value, str):
        raise ValueError("forecast timestamp is not an ISO string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("invalid forecast timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("forecast timestamp has no UTC offset")
    return parsed.timestamp()


def _points(
    response: object, entity: str, unit: object, now: float
) -> tuple[tuple[ForecastPoint, ...], tuple[ForecastPoint, ...]]:
    if not isinstance(response, Mapping) or not isinstance(response.get(entity), Mapping):
        raise ValueError("missing forecast response")
    rows = response[entity].get("forecast")
    if not isinstance(rows, list) or not 2 <= len(rows) <= MAX_RESPONSE_ROWS:
        raise ValueError("empty or excessive forecast response")
    points: list[ForecastPoint] = []
    content: list[ForecastPoint] = []
    previous: ForecastPoint | None = None
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("invalid forecast row")
        point = ForecastPoint(
            _timestamp(row.get("datetime")), _celsius(row.get("temperature"), unit)
        )
        if previous is not None and point.at <= previous.at:
            raise ValueError("duplicate or unordered forecast points")
        previous = point
        content.append(point)
        if now - 3600 <= point.at <= now + MAX_FORECAST_HORIZON:
            points.append(point)
    if len(points) < 2 or points[-1].at <= now:
        raise ValueError("forecast has no future coverage")
    return tuple(points[:MAX_FORECAST_POINTS]), tuple(content)


class WeatherForecast:
    """One bounded asynchronous cache per Plant, without actuator access."""

    def __init__(
        self, hass: HomeAssistant, config: WeatherConfig, on_update: Callable[[], None]
    ) -> None:
        self.hass = hass
        self.config = config
        self._on_update = on_update
        self.snapshot: ForecastSnapshot | None = None
        self.status = "pending"
        self.reason: str | None = None
        self._content_points: tuple[ForecastPoint, ...] = ()
        self._content_updated_at: float | None = None
        self._timer: Callable[[], None] | None = None
        self._stop_listener: Callable[[], None] | None = None
        self._task: asyncio.Task[None] | None = None
        self._started = False
        self._stopped = False
        self._failures = 0

    @callback
    def async_start(self) -> None:
        """Queue initial retrieval without waiting for a provider during setup."""
        if self._started or self._stopped:
            return
        self._started = True
        self._stop_listener = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._on_stop
        )
        self._request_refresh()

    @callback
    def _on_stop(self, _event: Event) -> None:
        self.stop()

    @callback
    def stop(self) -> None:
        """Invalidate publication synchronously before cancelling pending work."""
        self._stopped = True
        for cancel in (self._timer, self._stop_listener):
            if cancel is not None:
                cancel()
        self._timer = self._stop_listener = None
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def async_stop(self) -> None:
        """Drain ordinary cancellation without hanging on a misbehaving provider."""
        self.stop()
        if self._task is not None and not self._task.done():
            await asyncio.wait((self._task,), timeout=1.0)

    @callback
    def _request_refresh(self, _at: datetime | None = None) -> None:
        if self._stopped or (self._task is not None and not self._task.done()):
            return
        self._timer = None
        self._task = self.hass.async_create_background_task(
            self._async_refresh(), "Hydronicus hourly weather forecast", eager_start=False
        )

    def _source(self, now: float) -> State:
        state = self.hass.states.get(self.config.entity)
        if state is None or state.state in _MISSING:
            raise ValueError("weather source unavailable")
        features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
        if not isinstance(features, int) or not features & WeatherEntityFeature.FORECAST_HOURLY:
            raise ValueError("weather source does not support hourly forecasts")
        if not 0 <= now - state.last_reported_timestamp < self.config.max_age:
            raise ValueError("weather source report stale or in the future")
        return state

    async def _async_refresh(self) -> None:
        delay = float(REFRESH_SECONDS)
        try:
            state = self._source(dt_util.utcnow().timestamp())
            unit = state.attributes.get(ATTR_WEATHER_TEMPERATURE_UNIT)
            async with asyncio.timeout(REQUEST_TIMEOUT) as timeout:
                response = await self.hass.services.async_call(
                    DOMAIN,
                    SERVICE_GET_FORECASTS,
                    {"entity_id": self.config.entity, "type": "hourly"},
                    blocking=True,
                    return_response=True,
                )
            if self._stopped:
                return
            if timeout.expired():
                raise TimeoutError
            now = dt_util.utcnow().timestamp()
            state = self._source(now)
            if unit != state.attributes.get(ATTR_WEATHER_TEMPERATURE_UNIT):
                raise ValueError("weather temperature unit changed during retrieval")
            points, content = _points(response, self.config.entity, unit, now)
            old_points = {point.at: point.temperature for point in self._content_points}
            changed = any(old_points.get(point.at) != point.temperature for point in content)
            content_at = self._content_updated_at
            if changed or content_at is None:
                content_at = now
            snapshot = ForecastSnapshot(
                source=self.config.entity,
                points=points,
                received_at=now,
                content_updated_at=content_at,
                expires_at=min(
                    content_at + self.config.max_age,
                    state.last_reported_timestamp + self.config.max_age,
                    points[-1].at,
                ),
            )
            # Remember first-seen content even when its remaining horizon expires.
            self._content_points = content
            self._content_updated_at = content_at
            if now >= snapshot.expires_at:
                raise ValueError("forecast content stale")
            self.snapshot = snapshot
            self.status, self.reason = "available", None
            self._failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if self._stopped:
                return
            self.snapshot = None
            self.status = "unavailable"
            self.reason = (
                "weather request timed out" if isinstance(error, TimeoutError) else str(error)
            )
            self._failures = min(self._failures + 1, 7)
            delay = min(REFRESH_SECONDS, 60 * 2 ** (self._failures - 1)) * uniform(0.8, 1.0)
        if not self._stopped:
            self._timer = async_track_point_in_utc_time(
                self.hass, self._request_refresh, dt_util.utcnow() + timedelta(seconds=delay)
            )
            self._on_update()

    def outdoor_observation(self, now: float) -> OutdoorObservation | None:
        """Read current reported outdoor data; forecast points are never observations.

        A configured sensor is authoritative and does not silently fall back to
        the weather entity. Weather temperature may be modeled by its provider,
        so its quality does not claim a physical measurement at this home.
        """
        entity = self.config.outdoor_sensor or self.config.entity
        state = self.hass.states.get(entity)
        if state is None or state.state in _MISSING:
            return None
        reported = state.last_reported_timestamp
        if not isfinite(now) or not 0 <= now - reported < self.config.max_age:
            return None
        try:
            if self.config.outdoor_sensor is not None:
                value = _celsius(float(state.state), state.attributes.get(ATTR_UNIT_OF_MEASUREMENT))
                quality = "sensor_reported"
            else:
                value = _celsius(
                    state.attributes.get(ATTR_WEATHER_TEMPERATURE),
                    state.attributes.get(ATTR_WEATHER_TEMPERATURE_UNIT),
                )
                quality = "weather_reported"
        except TypeError, ValueError:
            return None
        return OutdoorObservation(value, reported, entity, quality)

    def diagnostics(self, now: float) -> dict[str, Any]:
        """Describe source and freshness without treating retrieval as issue time."""
        snapshot = self.snapshot
        expired = snapshot is not None and now >= snapshot.expires_at
        return {
            "entity": self.config.entity,
            "status": "stale" if expired else self.status,
            "reason": "forecast content expired" if expired else self.reason,
            "quality": "issue_time_unknown",
            "received_at": snapshot.received_at if snapshot else None,
            "content_updated_at": self._content_updated_at,
            "issued_at": None,
            "expires_at": snapshot.expires_at if snapshot else None,
            "coverage_start": snapshot.coverage_start if snapshot else None,
            "coverage_end": snapshot.coverage_end if snapshot else None,
            "points": len(snapshot.points) if snapshot else 0,
            "failures": self._failures,
        }
