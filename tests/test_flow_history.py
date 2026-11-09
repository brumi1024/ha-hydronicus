"""The flow counters behind the loop runtime and zone duty cycle sensors."""

from __future__ import annotations

import pytest

from custom_components.hydronicus.flow_history import HOUR, REFRESH, WINDOW_HOURS, FlowHistory

# Midnight, as a whole number of hours since 1970.
MIDNIGHT = 490_000 * HOUR


def test_nothing_counts_before_the_first_update_or_after_a_pause() -> None:
    history = FlowHistory()
    assert history.duty_cycle("study") is None
    history.update(MIDNIGHT, {"study.radiator"}, {"study"})
    history.update(MIDNIGHT + 600)
    history.pause(MIDNIGHT + 900)
    history.update(MIDNIGHT + 5000, {"study.radiator"}, {"study"})
    history.update(MIDNIGHT + 5100)

    assert history.runtime("study.radiator") == 1000.0
    assert history.to_dict()["hours"] == {
        "study": {str(MIDNIGHT // HOUR): 900.0, str(MIDNIGHT // HOUR + 1): 100.0}
    }


def test_flow_across_hours_is_split_and_only_whole_hours_count() -> None:
    history = FlowHistory()
    history.update(MIDNIGHT + 1800, {"study.radiator"}, {"study"})
    history.update(MIDNIGHT + 2 * HOUR + 1800, (), ())

    assert history.runtime("study.radiator") == 2 * HOUR
    assert history.duty_cycle("study") == pytest.approx(100 * 1.5 / WINDOW_HOURS)
    history.update(MIDNIGHT + 3 * HOUR)
    assert history.duty_cycle("study") == pytest.approx(100 * 2 / WINDOW_HOURS)


def test_a_clock_jump_keeps_only_the_window_and_a_clock_going_back_counts_nothing() -> None:
    history = FlowHistory()
    history.update(MIDNIGHT, {"study.radiator"}, {"study"})
    history.update(MIDNIGHT + 100 * HOUR + 1800)

    assert history.runtime("study.radiator") == 100 * HOUR + 1800
    assert history.duty_cycle("study") == 100.0
    assert len(history.to_dict()["hours"]["study"]) == WINDOW_HOURS + 1

    history.update(MIDNIGHT + 99 * HOUR)
    assert history.runtime("study.radiator") == 100 * HOUR + 1800


def test_refreshes_come_each_minute_while_flowing_then_hourly_until_the_window_empties() -> None:
    history = FlowHistory()
    history.update(MIDNIGHT, {"study.radiator"}, {"study"})
    assert history.next_refresh(MIDNIGHT) == MIDNIGHT + REFRESH

    history.update(MIDNIGHT + 1000, (), ())
    assert history.next_refresh(MIDNIGHT + 1000) == MIDNIGHT + HOUR
    history.update(MIDNIGHT + (WINDOW_HOURS + 1) * HOUR)
    assert history.next_refresh(MIDNIGHT + (WINDOW_HOURS + 1) * HOUR) is None


def test_the_counters_round_trip_and_forget_removed_loops_and_zones() -> None:
    history = FlowHistory()
    history.update(MIDNIGHT, {"study.radiator", "towel_dryer"}, {"study"})
    history.update(MIDNIGHT + 600)

    restored = FlowHistory.from_dict(history.to_dict())
    assert restored.to_dict() == history.to_dict()
    restored.forget_except({"towel_dryer"}, set())
    assert restored.to_dict() == {"runtimes": {"towel_dryer": 600.0}, "hours": {}}
