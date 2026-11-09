"""Recovery confidence requires independent, later observations, not sample volume."""

from dataclasses import FrozenInstanceError, replace
from math import inf, nan

import pytest

from custom_components.hydronicus.core.model import Mode
from custom_components.hydronicus.core.thermal import (
    DAY,
    MAX_EPISODES,
    MAX_IDLE_SECONDS,
    RETENTION_SECONDS,
    RecoveryEpisode,
    ThermalModel,
    estimate,
    record_episode,
    recovery_deficit,
)

START = 100 * DAY


def episode(
    index: int,
    *,
    mode: Mode = Mode.HEAT,
    deficit: float = 1,
    elapsed: float = 3600,
    outcome: str = "reached",
    outdoor: float | None = None,
) -> RecoveryEpisode:
    assert outcome in ("reached", "failed", "censored")
    return RecoveryEpisode(
        mode,
        START + index * DAY,
        START + index * DAY + elapsed,
        deficit,
        outcome,
        outdoor,
    )


def history(
    count: int = 12,
    *,
    delay: float = 0,
    rate: float = 1,
    mode: Mode = Mode.HEAT,
    varying: bool = False,
) -> ThermalModel:
    model = ThermalModel()
    for index in range(count):
        deficit = (0.5, 1.0, 1.5, 2.0)[index % 4] if varying else 1.0
        item = episode(index, mode=mode, deficit=deficit, elapsed=delay + 3600 * deficit / rate)
        model = record_episode(model, item, item.ended_at)
    return model


def latest(model: ThermalModel) -> float:
    return model.episodes[-1].ended_at


@pytest.mark.parametrize(
    "mode,target,temperature,expected",
    [
        (Mode.HEAT, 21, 20, 1),
        (Mode.COOL, 21, 23, 2),
        (Mode.HEAT, 21, 23, 0),
        (Mode.COOL, 21, 20, 0),
        (Mode.OFF, 21, 20, 0),
        (Mode.HEAT, nan, 20, 0),
        (Mode.COOL, 21, inf, 0),
    ],
)
def test_directional_deficit(
    mode: Mode, target: float, temperature: float, expected: float
) -> None:
    assert recovery_deficit(mode, target, temperature) == expected


def test_model_and_episodes_are_immutable_values() -> None:
    model = ThermalModel()
    item = episode(0)
    result = record_episode(model, item, item.ended_at)
    assert not model.episodes
    assert len(result.episodes) == 1
    with pytest.raises(FrozenInstanceError):
        item.deficit = 2  # type: ignore[misc]


def test_a_repeatable_rate_requires_real_independent_validation() -> None:
    model = history()
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert result.seconds == 3600
    assert result.confidence
    assert result.status == "ready"
    assert result.episode_count == 12
    assert result.validation_count == 9
    assert result.error_seconds == 0
    assert result.rate_celsius_per_hour == 1
    assert result.startup_delay_seconds == 0
    assert result.valid_until == latest(model) + MAX_IDLE_SECONDS
    assert not result.weather_adjusted
    assert estimate(model, Mode.COOL, 1, latest(model)).seconds is None


def test_delay_is_identified_only_from_distinct_deficits() -> None:
    model = history(delay=1800, rate=0.5, varying=True)
    result = estimate(model, Mode.HEAT, 1.25, latest(model))
    assert result.confidence
    assert result.seconds == pytest.approx(10800)
    assert result.startup_delay_seconds == pytest.approx(1800)
    assert result.rate_celsius_per_hour == pytest.approx(0.5)
    single_deficit = history(delay=1800, rate=0.5)
    result = estimate(single_deficit, Mode.HEAT, 1, latest(single_deficit))
    assert result.confidence
    assert result.seconds == 9000
    assert result.startup_delay_seconds == 0


def test_sparse_evidence_produces_only_shadow_predictions() -> None:
    empty = estimate(ThermalModel(), Mode.HEAT, 1, START)
    assert empty.seconds is None
    model = history(2)
    assert estimate(model, Mode.HEAT, 1, latest(model)).seconds is None
    model = history(6)
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert result.seconds == 3600
    assert not result.confidence
    assert "10 independent" in result.reason


def test_many_same_day_episodes_do_not_replace_a_week_of_evidence() -> None:
    model = ThermalModel()
    for index in range(12):
        start = START + index * 6 * 3600
        item = RecoveryEpisode(Mode.HEAT, start, start + 3600, 1, "reached")
        model = record_episode(model, item, item.ended_at)
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert result.episode_count == 12
    assert not result.confidence
    assert "7 days" in result.reason


def test_repeated_overlapping_episodes_do_not_boost_confidence() -> None:
    model = ThermalModel()
    for index in range(30):
        start = START + index * 60
        item = RecoveryEpisode(Mode.HEAT, start, start + 3600, 1, "reached")
        model = record_episode(model, item, item.ended_at)
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert result.episode_count == 1
    assert not result.confidence
    item = episode(0, elapsed=3600)
    original = record_episode(ThermalModel(), item, item.ended_at)
    assert record_episode(original, replace(item, outcome="failed"), item.ended_at) == original


def test_a_long_running_episode_cannot_overlap_an_independent_episode() -> None:
    first = episode(0, elapsed=12 * 3600)
    second = replace(
        episode(1), started_at=first.started_at + 8 * 3600, ended_at=first.ended_at + 1
    )
    model = record_episode(ThermalModel(), first, first.ended_at)
    model = record_episode(model, second, second.ended_at)
    assert estimate(model, Mode.HEAT, 1, latest(model)).episode_count == 1


@pytest.mark.parametrize("outcome", ["failed", "censored"])
def test_failed_and_censored_outcomes_are_retained_and_reduce_confidence(outcome: str) -> None:
    model = history()
    item = episode(12, elapsed=6 * 3600, outcome=outcome)
    model = record_episode(model, item, item.ended_at)
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert len(model.episodes) == 13
    assert result.episode_count == 12
    assert not result.confidence
    assert "failed or censored" in result.reason
    assert result.seconds == 3600
    for index in range(13, 16):
        item = episode(index)
        model = record_episode(model, item, item.ended_at)
    assert estimate(model, Mode.HEAT, 1, latest(model)).confidence


def test_persistent_unsuccessful_recoveries_do_not_disappear_after_three_successes() -> None:
    model = history(12)
    for index in range(12, 22):
        item = episode(index, outcome="failed" if index < 19 else "reached")
        model = record_episode(model, item, item.ended_at)
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert not result.confidence
    assert "failed or censored" in result.reason


def test_an_outlier_does_not_set_the_fitted_rate_but_counts_in_prediction_error() -> None:
    model = history()
    item = episode(12, elapsed=7200)
    model = record_episode(model, item, item.ended_at)
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert result.seconds == 3600
    assert result.error_seconds == pytest.approx(360)
    assert result.confidence


def test_future_outcomes_cannot_make_a_bad_prior_prediction_look_accurate() -> None:
    model = history(10)
    for index in range(10, 16):
        item = episode(index, elapsed=10800)
        model = record_episode(model, item, item.ended_at)
    # A fit on the entire final dataset can fit the recent outcomes, but its
    # forecasts made without those outcomes were wrong and must stay wrong.
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert result.validation_count == 13
    assert not result.confidence
    assert "prediction error" in result.reason
    assert model.episodes[10].baseline_predicted_seconds == 3600


def test_a_new_deficit_cannot_validate_itself_or_force_extrapolation() -> None:
    model = ThermalModel()
    for index in range(12):
        deficit = 0.3 + index * 0.1
        item = episode(index, deficit=deficit, elapsed=3600 * deficit)
        model = record_episode(model, item, item.ended_at)
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert result.seconds == pytest.approx(3600)
    assert not result.confidence
    assert result.validation_count == 0
    assert "prior-heldout" in result.reason
    outside = estimate(model, Mode.HEAT, 3, latest(model))
    assert outside.seconds is None
    assert outside.status == "out_of_range"


def test_caller_supplied_validation_predictions_are_overwritten() -> None:
    model = history(4)
    item = replace(
        episode(4, elapsed=7200),
        baseline_predicted_seconds=7200,
        weather_predicted_seconds=7200,
        predicted_seconds=4000,
    )
    model = record_episode(model, item, item.ended_at)
    stored = model.episodes[-1]
    assert stored.baseline_predicted_seconds == 3600
    assert stored.weather_predicted_seconds is None
    assert stored.predicted_seconds == 4000


def test_an_expired_candidate_cannot_claim_a_heldout_forecast_after_a_gap() -> None:
    model = history(10)
    item = episode(18)
    model = record_episode(model, item, item.ended_at)
    assert model.episodes[-1].baseline_predicted_seconds is None


def test_expiry_and_oldest_evidence_are_explicit() -> None:
    model = history()
    assert estimate(model, Mode.HEAT, 1, latest(model) + MAX_IDLE_SECONDS).seconds is None
    item = episode(29)
    model = record_episode(model, item, item.ended_at)
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert result.valid_until == model.episodes[0].ended_at + RETENTION_SECONDS
    expired = estimate(model, Mode.HEAT, 1, START + 60 * DAY)
    assert expired.seconds is None
    assert not expired.confidence


def test_history_retention_and_size_are_bounded() -> None:
    model = history(40)
    assert len(model.episodes) == 30
    for index in range(MAX_EPISODES + 10):
        start = START + 41 * DAY + index * 60
        item = RecoveryEpisode(Mode.HEAT, start, start + 300, 1, "reached")
        model = record_episode(model, item, item.ended_at)
    assert len(model.episodes) == MAX_EPISODES
    assert all(item.ended_at > latest(model) - RETENTION_SECONDS for item in model.episodes)


@pytest.mark.parametrize(
    "changed",
    [
        {"mode": Mode.OFF},
        {"deficit": nan},
        {"deficit": 0.1},
        {"deficit": 11},
        {"ended_at": START},
        {"ended_at": START + 2 * DAY},
        {"outdoor_temperature": inf},
        {"outdoor_temperature": 61},
    ],
)
def test_invalid_optional_episode_data_is_discarded(changed: dict[str, object]) -> None:
    item = replace(episode(0), **changed)
    assert not record_episode(ThermalModel(), item, START + 3 * DAY).episodes


def test_future_and_expired_episodes_are_discarded_and_invalid_time_is_harmless() -> None:
    item = episode(0)
    empty = ThermalModel()
    assert record_episode(empty, item, nan) is empty
    assert not record_episode(empty, item, START).episodes
    assert not record_episode(empty, item, START + 31 * DAY).episodes
    for mode, deficit, now in ((Mode.OFF, 1, START), (Mode.HEAT, nan, START), (Mode.HEAT, 1, inf)):
        assert estimate(empty, mode, deficit, now).status == "unavailable"
    assert estimate(empty, Mode.HEAT, 0, START).seconds == 0


def test_impossible_rate_never_produces_a_learned_estimate() -> None:
    model = history(12, rate=20)
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert result.seconds is None
    assert not result.confidence
    model = history(12, rate=0.045)
    result = estimate(model, Mode.HEAT, 1, latest(model))
    assert result.seconds is None


def weather_history(*, dependent: bool) -> ThermalModel:
    model = ThermalModel()
    for index in range(28):
        cold = index % 2 == 0
        elapsed = 7200 if cold and dependent else 3600
        item = episode(index, outdoor=0 if cold else 15, elapsed=elapsed)
        model = record_episode(model, item, item.ended_at)
    return model


def test_weather_requires_independent_benefit_and_stays_within_observed_conditions() -> None:
    model = weather_history(dependent=True)
    cold = estimate(model, Mode.HEAT, 1, latest(model), outdoor_temperature=0)
    assert cold.confidence
    assert cold.weather_adjusted
    assert cold.seconds == 7200
    warm = estimate(model, Mode.HEAT, 1, latest(model), outdoor_temperature=15)
    assert warm.confidence
    assert warm.weather_adjusted
    assert warm.seconds == 3600
    for temperature in (None, nan, inf, -10, 7):
        fallback = estimate(model, Mode.HEAT, 1, latest(model), outdoor_temperature=temperature)
        assert not fallback.weather_adjusted
        assert not fallback.confidence


def test_weather_without_demonstrated_improvement_and_sparse_weather_use_learned_baseline() -> None:
    model = weather_history(dependent=False)
    for temperature in (0, 15, 7, nan, None):
        result = estimate(model, Mode.HEAT, 1, latest(model), outdoor_temperature=temperature)
        assert result.confidence
        assert result.seconds == 3600
        assert not result.weather_adjusted
    model = history()
    item = episode(12, outdoor=0)
    model = record_episode(model, item, item.ended_at)
    result = estimate(model, Mode.HEAT, 1, latest(model), outdoor_temperature=0)
    assert result.confidence
    assert not result.weather_adjusted


def test_modes_keep_separate_rates_and_validation() -> None:
    model = history()
    for index in range(12):
        item = replace(
            episode(index, mode=Mode.COOL, elapsed=7200),
            started_at=START + index * DAY + 4000,
            ended_at=START + index * DAY + 11200,
        )
        model = record_episode(model, item, START + 12 * DAY)
    heating = estimate(model, Mode.HEAT, 1, START + 12 * DAY)
    cooling = estimate(model, Mode.COOL, 1, START + 12 * DAY)
    assert heating.confidence and cooling.confidence
    assert heating.seconds == 3600
    assert cooling.seconds == 7200
