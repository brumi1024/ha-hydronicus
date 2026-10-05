"""Public weather actions, bounded caching, quality failures, and cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from math import inf, nan
from typing import Any
from unittest.mock import Mock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.hydronicus import forecast as forecast_module
from custom_components.hydronicus.core.model import WeatherConfig
from custom_components.hydronicus.forecast import WeatherForecast

ENTITY = "weather.forecast_home"


def rows(now: float, values: tuple[float, ...] = (10, 12, 14, 16, 18)) -> list[dict[str, Any]]:
    return [
        {
            "datetime": datetime.fromtimestamp(now + 3600 * index, UTC).isoformat(),
            "temperature": value,
        }
        for index, value in enumerate(values)
    ]


class Provider:
    """A weather service exposing Home Assistant's actual response contract."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.now = dt_util.utcnow().timestamp()
        self.response: Any = {ENTITY: {"forecast": rows(self.now)}}
        self.calls: list[ServiceCall] = []
        self.effect: Callable[[], Awaitable[None]] | None = None
        hass.services.async_register(
            "weather", "get_forecasts", self.retrieve, supports_response=SupportsResponse.ONLY
        )
        self.report()

    def report(self, unit: str = "°C", features: int = 2, temperature: Any = 9) -> None:
        self.hass.states.async_set(
            ENTITY,
            "cloudy",
            {"temperature_unit": unit, "supported_features": features, "temperature": temperature},
        )

    async def retrieve(self, call: ServiceCall) -> dict[str, Any]:
        self.calls.append(call)
        if self.effect is not None:
            await self.effect()
        return self.response


async def settled(hass: HomeAssistant) -> None:
    await hass.async_block_till_done(wait_background_tasks=True)


async def advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await settled(hass)


@pytest.mark.parametrize("unit,values", [("°C", (10, 12, 14)), ("°F", (50, 53.6, 57.2))])
async def test_public_hourly_response_is_normalized_and_published(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, unit: str, values: tuple[float, ...]
) -> None:
    provider = Provider(hass)
    provider.report(unit=unit)
    provider.response[ENTITY]["forecast"] = rows(provider.now, values)
    updated = Mock()
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), updated)
    cache.async_start()
    cache.async_start()
    assert provider.calls == []
    await settled(hass)
    assert len(provider.calls) == 1
    assert provider.calls[0].data == {"entity_id": ENTITY, "type": "hourly"}
    assert cache.snapshot is not None
    assert cache.snapshot.temperature_between(provider.now, provider.now + 7200, provider.now) == 12
    assert cache.snapshot.issued_at is None
    assert cache.diagnostics(provider.now)["quality"] == "issue_time_unknown"
    assert cache.status == "available"
    updated.assert_called_once_with()
    await cache.async_stop()
    cache.async_start()
    await advance(hass, freezer, 3600)
    assert len(provider.calls) == 1


@pytest.mark.parametrize("features", [0, 1, 4, "2", None])
async def test_missing_hourly_capability_never_fabricates_daily_points(
    hass: HomeAssistant, features: Any
) -> None:
    provider = Provider(hass)
    provider.report(features=features)
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert provider.calls == []
    assert cache.snapshot is None
    assert cache.reason == "weather source does not support hourly forecasts"
    await cache.async_stop()


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {ENTITY: None},
        {ENTITY: {}},
        {ENTITY: {"forecast": []}},
        {ENTITY: {"forecast": [None, {}]}},
    ],
)
async def test_missing_empty_and_malformed_responses_are_optional_failures(
    hass: HomeAssistant, response: Any
) -> None:
    provider = Provider(hass)
    provider.response = response
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert cache.snapshot is None
    assert cache.status == "unavailable"
    assert cache.reason
    await cache.async_stop()


@pytest.mark.parametrize("unit", [None, "", "K", "F", "banana"])
async def test_units_must_be_explicit_celsius_or_fahrenheit(hass: HomeAssistant, unit: Any) -> None:
    provider = Provider(hass)
    provider.report(unit=unit)
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert cache.snapshot is None
    assert cache.reason == "unsupported temperature value or unit"
    await cache.async_stop()


@pytest.mark.parametrize("value", [None, "12", True, nan, inf, -91, 66])
async def test_missing_non_numeric_nonfinite_and_implausible_temperatures(
    hass: HomeAssistant, value: Any
) -> None:
    provider = Provider(hass)
    provider.response[ENTITY]["forecast"][1]["temperature"] = value
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert cache.snapshot is None
    await cache.async_stop()


@pytest.mark.parametrize("timestamp", [None, 123, "nonsense", "2026-10-25T02:30:00"])
async def test_ambiguous_or_malformed_timestamp_is_rejected(
    hass: HomeAssistant, timestamp: Any
) -> None:
    provider = Provider(hass)
    provider.response[ENTITY]["forecast"][1]["datetime"] = timestamp
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert cache.snapshot is None
    await cache.async_stop()


@pytest.mark.parametrize("change", ["duplicate", "unordered", "gap", "past", "excessive"])
async def test_coverage_and_size_are_validated(hass: HomeAssistant, change: str) -> None:
    provider = Provider(hass)
    data = provider.response[ENTITY]["forecast"]
    if change == "duplicate":
        data[1]["datetime"] = data[0]["datetime"]
    elif change == "unordered":
        data.reverse()
    elif change == "gap":
        del data[1]
    elif change == "past":
        provider.response[ENTITY]["forecast"] = rows(provider.now - 36000)
    else:
        provider.response[ENTITY]["forecast"] = rows(provider.now, (0,) * 513)
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert cache.snapshot is None
    await cache.async_stop()


async def test_explicit_offsets_normalize_across_dst_and_horizon_is_bounded(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-10-25T00:00:00+00:00")
    provider = Provider(hass)
    provider.response[ENTITY]["forecast"] = rows(provider.now, (10,) * 240)
    provider.response[ENTITY]["forecast"][0]["datetime"] = "2026-10-25T02:00:00+02:00"
    provider.response[ENTITY]["forecast"][1]["datetime"] = "2026-10-25T02:00:00+01:00"
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert cache.snapshot is not None
    assert len(cache.snapshot.points) == 169
    assert cache.snapshot.coverage_end - cache.snapshot.coverage_start == 7 * 86400
    await cache.async_stop()


async def test_rereading_unchanged_content_cannot_extend_its_expiry(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    provider = Provider(hass)
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert cache.snapshot is not None
    expiry = cache.snapshot.expires_at
    await advance(hass, freezer, 3600)
    assert len(provider.calls) == 2
    assert cache.snapshot is not None
    assert cache.snapshot.received_at == provider.now + 3600
    assert cache.snapshot.content_updated_at == provider.now
    assert cache.snapshot.expires_at == expiry
    assert cache.diagnostics(expiry)["status"] == "stale"
    # Even a new weather-state report and removal of expired rows are not a new forecast.
    provider.report()
    del provider.response[ENTITY]["forecast"][0]
    await advance(hass, freezer, 3600)
    assert cache.snapshot is None
    assert cache.reason == "forecast content stale"
    assert cache.diagnostics(provider.now + 7200)["content_updated_at"] == provider.now
    await cache.async_stop()


async def test_fresh_revised_forecast_recovers_after_failure_with_bounded_backoff(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(forecast_module, "uniform", lambda _low, _high: 1.0)
    provider = Provider(hass)
    provider.response = {}
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    await advance(hass, freezer, 59)
    assert len(provider.calls) == 1
    await advance(hass, freezer, 1)
    assert len(provider.calls) == 2
    provider.response = {ENTITY: {"forecast": rows(dt_util.utcnow().timestamp())}}
    await advance(hass, freezer, 119)
    assert len(provider.calls) == 2
    await advance(hass, freezer, 1)
    assert len(provider.calls) == 3
    assert cache.status == "available"
    assert cache.diagnostics(dt_util.utcnow().timestamp())["failures"] == 0
    await cache.async_stop()


async def test_sliding_the_bounded_horizon_does_not_refresh_unchanged_long_response(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    provider = Provider(hass)
    provider.response[ENTITY]["forecast"] = rows(provider.now, (10,) * 240)
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    await advance(hass, freezer, 3600)
    provider.report()
    await advance(hass, freezer, 3600)
    assert cache.snapshot is None
    assert cache.reason == "forecast content stale"
    await cache.async_stop()


async def test_a_real_content_revision_receives_a_new_content_deadline(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    provider = Provider(hass)
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    await advance(hass, freezer, 1800)
    provider.report()
    provider.response[ENTITY]["forecast"][2]["temperature"] = 20
    await advance(hass, freezer, 1800)
    assert cache.snapshot is not None
    assert cache.snapshot.content_updated_at == provider.now + 3600
    # A new forecast cannot override an older source-health deadline.
    assert cache.snapshot.expires_at == provider.now + 1800 + 7200
    await cache.async_stop()


@pytest.mark.parametrize("state", ["missing", "unavailable", "unknown", "stale", "future"])
async def test_unhealthy_weather_state_blocks_optional_retrieval(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, state: str
) -> None:
    provider = Provider(hass)
    if state == "missing":
        hass.states.async_remove(ENTITY)
    elif state in ("unavailable", "unknown"):
        hass.states.async_set(ENTITY, state)
    else:
        freezer.tick(timedelta(seconds=7200 if state == "stale" else -1))
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert provider.calls == []
    assert cache.snapshot is None
    await cache.async_stop()


async def test_unit_change_during_service_call_is_rejected(hass: HomeAssistant) -> None:
    provider = Provider(hass)

    async def change_unit() -> None:
        provider.report(unit="°F")

    provider.effect = change_unit
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert cache.snapshot is None
    assert cache.reason == "weather temperature unit changed during retrieval"
    await cache.async_stop()


async def test_timeout_is_optional_and_does_not_leave_an_inflight_request(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(forecast_module, "REQUEST_TIMEOUT", 0.001)
    provider = Provider(hass)
    blocked = asyncio.Event()
    provider.effect = blocked.wait
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert cache.snapshot is None
    assert cache.reason == "weather request timed out"
    assert len(provider.calls) == 1
    await cache.async_stop()


async def test_catching_provider_cancellation_does_not_turn_timeout_into_success(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(forecast_module, "REQUEST_TIMEOUT", 0.001)
    provider = Provider(hass)

    async def suppress_timeout() -> None:
        with suppress(asyncio.CancelledError):
            await asyncio.Event().wait()

    provider.effect = suppress_timeout
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    cache.async_start()
    await settled(hass)
    assert cache.snapshot is None
    assert cache.reason == "weather request timed out"
    await cache.async_stop()


@pytest.mark.parametrize("stop_from_ha", [False, True])
async def test_stop_cancels_work_and_disallows_late_publish(
    hass: HomeAssistant, stop_from_ha: bool
) -> None:
    provider = Provider(hass)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow() -> None:
        entered.set()
        # A faulty provider may swallow cancellation, but cannot publish afterward.
        with suppress(asyncio.CancelledError):
            await release.wait()

    provider.effect = slow
    updated = Mock()
    cache = WeatherForecast(hass, WeatherConfig(ENTITY), updated)
    cache.async_start()
    await entered.wait()
    cache.async_start()
    assert len(provider.calls) == 1
    if stop_from_ha:
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
        await hass.async_block_till_done()
    else:
        cache.stop()
    await cache.async_stop()
    release.set()
    await settled(hass)
    assert len(provider.calls) == 1
    assert cache.snapshot is None
    updated.assert_not_called()


async def test_weather_report_is_not_confused_with_a_measured_outdoor_sensor(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    provider = Provider(hass)
    weather = WeatherForecast(hass, WeatherConfig(ENTITY), Mock())
    sensor = WeatherForecast(hass, WeatherConfig(ENTITY, "sensor.outdoor"), Mock())
    observation = weather.outdoor_observation(provider.now)
    assert observation is not None
    assert observation.temperature == 9
    assert observation.quality == "weather_reported"
    assert observation.reported_at == provider.now
    assert sensor.outdoor_observation(provider.now) is None
    hass.states.async_set("sensor.outdoor", "50", {"unit_of_measurement": "°F"})
    observation = sensor.outdoor_observation(provider.now)
    assert observation is not None
    assert observation.temperature == 10
    assert observation.quality == "sensor_reported"
    assert observation.source == "sensor.outdoor"
    await advance(hass, freezer, 7200)
    assert weather.outdoor_observation(dt_util.utcnow().timestamp()) is None
    assert sensor.outdoor_observation(dt_util.utcnow().timestamp()) is None


@pytest.mark.parametrize(
    "value,unit", [("unavailable", "°C"), ("nan", "°C"), ("10", None), ("bad", "°C")]
)
async def test_bad_outdoor_sensor_never_silently_uses_weather(
    hass: HomeAssistant, value: str, unit: str | None
) -> None:
    provider = Provider(hass)
    hass.states.async_set("sensor.outdoor", value, {"unit_of_measurement": unit})
    cache = WeatherForecast(hass, WeatherConfig(ENTITY, "sensor.outdoor"), Mock())
    assert cache.outdoor_observation(provider.now) is None
    assert cache.outdoor_observation(nan) is None
