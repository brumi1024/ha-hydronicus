"""The compressor history behind the source's diagnostic sensors."""

from __future__ import annotations

from custom_components.hydronicus.compressor import DAY, HOUR, CompressorHistory

NOW = 1_800_000_000.0


def test_starts_and_runs_are_counted_within_their_windows() -> None:
    history = CompressorHistory()
    history.observe(NOW, True)
    history.observe(NOW + 600, None)
    history.observe(NOW + 1200, False)
    history.observe(NOW + 1800, True)
    history.observe(NOW + 3000, False)

    assert history.starts_within_hour(NOW + 3000) == 2
    assert history.mean_run(NOW + 3000) == (1200 + 1200) / 2
    assert history.starts_within_hour(NOW + HOUR + 1) == 1
    assert history.mean_run(NOW + 1200 + DAY + 1) == 1200
    history.observe(NOW + 3000 + DAY, False)
    assert history.mean_run(NOW + 3000 + DAY) is None
    assert history.starts == [] and history.runs == []


def test_an_unknown_reading_neither_starts_nor_ends_a_run_and_the_history_persists() -> None:
    history = CompressorHistory()
    history.observe(NOW, None)
    assert history.running_since is None
    history.observe(NOW + 60, True)

    restored = CompressorHistory.from_dict(history.to_dict())
    assert restored == history
    assert CompressorHistory.from_dict({}) == CompressorHistory()
