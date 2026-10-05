"""Forecasts are immutable Celsius points, never extrapolated or silently renewed."""

from dataclasses import FrozenInstanceError, replace
from math import inf, nan

import pytest

from custom_components.hydronicus.core.forecast import ForecastPoint, ForecastSnapshot


def forecast() -> ForecastSnapshot:
    return ForecastSnapshot(
        "weather.home",
        (ForecastPoint(1000, 0), ForecastPoint(4600, 10), ForecastPoint(8200, 0)),
        received_at=1000,
        content_updated_at=1000,
        expires_at=8200,
    )


def test_full_and_partial_intervals_use_time_weighted_interpolation() -> None:
    snapshot = forecast()
    assert snapshot.temperature_between(1000, 8200, 1000) == 5
    assert snapshot.temperature_between(1000, 2800, 1000) == 2.5
    assert snapshot.temperature_between(2800, 6400, 1000) == 7.5
    assert snapshot.temperature_between(4600, 8200, 1000) == 5
    assert snapshot.quality == "issue_time_unknown"
    assert snapshot.issued_at is None
    with pytest.raises(FrozenInstanceError):
        snapshot.received_at = 8200  # type: ignore[misc]


@pytest.mark.parametrize(
    "start,end,now",
    [
        (0, 4600, 1000),
        (1000, 8201, 1000),
        (1000, 4600, 999),
        (1000, 4600, 8200),
        (1000, 1000, 1000),
        (4600, 1000, 1000),
        (nan, 4600, 1000),
        (1000, inf, 1000),
        (1000, 4600, nan),
    ],
)
def test_missing_coverage_invalid_times_and_expiry_disable_a_proposal(
    start: float, end: float, now: float
) -> None:
    assert forecast().temperature_between(start, end, now) is None


@pytest.mark.parametrize("at,temperature", [(nan, 0), (0, inf), (0, -91), (0, 66)])
def test_invalid_points_are_rejected(at: float, temperature: float) -> None:
    with pytest.raises(ValueError):
        ForecastPoint(at, temperature)


@pytest.mark.parametrize(
    "changes",
    [
        {"points": ()},
        {"points": (ForecastPoint(1000, 0),)},
        {"points": (ForecastPoint(1000, 0),) * 170},
        {"points": [ForecastPoint(1000, 0), ForecastPoint(4600, 0)]},
        {"points": (ForecastPoint(1000, 0), ForecastPoint(4601, 0))},
        {"points": (ForecastPoint(1000, 0), ForecastPoint(1000, 0))},
        {"points": (ForecastPoint(1000, 0), ForecastPoint(0, 0))},
        {"received_at": inf},
        {"content_updated_at": 1001},
        {"expires_at": nan},
        {"issued_at": inf},
        {"issued_at": 1001},
    ],
)
def test_invalid_snapshots_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(forecast(), **changes)  # type: ignore[arg-type]


def test_known_issue_time_is_preserved_without_changing_interpolation() -> None:
    snapshot = replace(forecast(), issued_at=900, quality="provider_issued")
    assert snapshot.issued_at == 900
    assert snapshot.temperature_between(1000, 8200, 1000) == 5
