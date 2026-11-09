"""The response check, which reports a served zone whose temperature does not respond."""

from __future__ import annotations

import json

import pytest

from custom_components.hydronicus.core.model import Mode, ResponseCheck
from custom_components.hydronicus.core.response import ZoneResponse, check_response

NOW = 1_800_000_000.0
HOUR = 3600.0
CHECK = ResponseCheck(duration=3 * HOUR, progress=0.2)


def advance(
    state: ZoneResponse | None,
    offset: float,
    temperature: float | None,
    *,
    mode: Mode = Mode.HEAT,
    calling: bool = True,
    served: bool = True,
) -> tuple[ZoneResponse | None, float | None]:
    return check_response(
        CHECK,
        state,
        mode,
        calling=calling,
        served=served,
        temperature=temperature,
        now=NOW + offset,
    )


def test_a_served_zone_that_does_not_warm_fails_after_the_duration() -> None:
    state, due = advance(None, 0, 19.0)
    assert state == ZoneResponse(Mode.HEAT, 19.0, 0.0, NOW)
    assert due == NOW + 3 * HOUR
    state, due = advance(state, HOUR, 19.1)
    assert state is not None and state.served == HOUR and due == NOW + 3 * HOUR
    state, due = advance(state, 3 * HOUR, 19.1)
    assert state is not None and state.failed_at == NOW + 3 * HOUR and due is None
    # It stays failed until the temperature responds.
    state, _ = advance(state, 4 * HOUR, 19.15)
    assert state is not None and state.failed_at == NOW + 3 * HOUR
    state, due = advance(state, 5 * HOUR, 19.2)
    assert state == ZoneResponse(Mode.HEAT, 19.2, 0.0, NOW + 5 * HOUR)
    assert due == NOW + 8 * HOUR


def test_progress_counts_from_the_coldest_reading_so_a_slab_lag_is_no_failure() -> None:
    state, _ = advance(None, 0, 19.5)
    state, _ = advance(state, HOUR, 19.2)
    assert state is not None and state.reference == 19.2 and state.served == HOUR
    state, _ = advance(state, 2 * HOUR, 19.4)
    assert state is not None and state.served == 0.0 and state.reference == 19.4


def test_only_served_time_counts_and_a_pause_does_not_start_over() -> None:
    state, _ = advance(None, 0, 19.0)
    state, due = advance(state, HOUR, 19.0, served=False)
    assert state is not None and state.served == HOUR and state.served_at is None
    assert due is None, "nothing counts toward a failure while the zone is not served"
    # Hot water for two hours adds nothing.
    state, due = advance(state, 3 * HOUR, 19.0)
    assert state is not None and state.served == HOUR and due == NOW + 5 * HOUR
    state, _ = advance(state, 5 * HOUR, 19.0)
    assert state is not None and state.failed_at == NOW + 5 * HOUR


def test_cooling_responds_to_a_fall_and_a_mode_change_or_the_end_of_a_call_resets() -> None:
    state, _ = advance(None, 0, 26.0, mode=Mode.COOL)
    state, _ = advance(state, HOUR, 26.3, mode=Mode.COOL)
    assert state is not None and state.reference == 26.3 and state.served == HOUR
    state, _ = advance(state, 2 * HOUR, 26.1, mode=Mode.COOL)
    assert state is not None and state.served == 0.0

    assert advance(state, 2 * HOUR, 26.1, calling=False) == (None, None)
    assert advance(state, 2 * HOUR, 26.1, mode=Mode.OFF) == (None, None)
    heating, _ = advance(state, 2 * HOUR, 26.1)
    assert heating == ZoneResponse(Mode.HEAT, 26.1, 0.0, NOW + 2 * HOUR)


def test_a_missing_temperature_keeps_counting_but_never_responds() -> None:
    state, _ = advance(None, 0, None)
    assert state is not None and state.reference is None
    state, _ = advance(state, 3 * HOUR, None)
    assert state is not None and state.failed_at == NOW + 3 * HOUR


@pytest.mark.parametrize(
    "state",
    [ZoneResponse(Mode.COOL), ZoneResponse(Mode.HEAT, 19.2, 1800.0, NOW, NOW - 60)],
)
def test_the_response_round_trips_through_json(state: ZoneResponse) -> None:
    assert ZoneResponse.from_dict(json.loads(json.dumps(state.to_dict()))) == state
