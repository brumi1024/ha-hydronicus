"""The room trim: filter, deadband, clamps, learning, its holds, and anti-windup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from math import exp, inf, nan, pi, sin

import pytest

from custom_components.hydronicus.core.model import RoomInfluence
from custom_components.hydronicus.core.room_trim import (
    LEARN_BAND,
    SETTLE_TIME,
    RoomTrim,
    RoomTrimState,
    room_trim,
)

NOW = 1_800_000_000.0
HOUR = 3600.0
INFLUENCE = RoomInfluence(("room",))
TARGET = 21.0
FRESH = RoomTrimState()
# Called long enough for the learned part to rise, and arrived at the target.
LONG_AGO = NOW - 2 * INFLUENCE.learn_after


def trim(
    error: float | None,
    previous: RoomTrimState = FRESH,
    now: float = NOW,
    influence: RoomInfluence = INFLUENCE,
    **kwargs: object,
) -> RoomTrim:
    options: dict[str, object] = {"gap": HOUR, "calling": LONG_AGO, "target": TARGET}
    options |= kwargs
    return room_trim(influence, previous, now, "room", error, **options)  # type: ignore[arg-type]


def still(error: float, learned: float = 0.0, at: float = NOW - HOUR) -> RoomTrimState:
    """A room long arrived at its target whose filtered error has held ``error`` since long ago."""
    return RoomTrimState(
        error,
        at,
        learned,
        targets={"room": TARGET},
        arrived=LONG_AGO,
        moved=error,
        moved_at=LONG_AGO,
    )


def settled(error: float, learned: float = 0.0) -> RoomTrimState:
    """As ``still``, updated a minute ago."""
    return still(error, learned, NOW - 60)


def test_the_first_reading_starts_the_filter_and_learns_nothing() -> None:
    result = trim(1.0)
    assert result.error == 1.0
    assert result.proportional == pytest.approx(0.8)
    assert result.learned == 0.0
    assert result.held == "the room trim starts again from the reading"
    assert result.state == RoomTrimState(
        1.0,
        NOW,
        0.0,
        targets={"room": TARGET},
        settling=True,
        moved=1.0,
        moved_at=NOW,
        calling_since=LONG_AGO,
    )


def test_the_filter_follows_a_step_with_its_time_constant() -> None:
    result = trim(1.0, still(0.0))
    assert result.error == pytest.approx(1 - exp(-1))
    instant = trim(1.0, RoomTrimState(0.0, NOW - 60), influence=replace(INFLUENCE, smoothing=0))
    assert instant.error == 1.0


@pytest.mark.parametrize(
    ("error", "proportional"),
    [(0.0, 0.0), (0.2, 0.0), (-0.2, 0.0), (0.5, 0.3), (-0.5, -0.3), (5.0, 2.0), (-5.0, -2.0)],
)
def test_the_deadband_counts_only_the_error_beyond_it_and_the_limit_caps_it(
    error: float, proportional: float
) -> None:
    result = trim(error, settled(error))
    assert result.proportional == pytest.approx(proportional)


def test_the_factor_scales_the_proportional_part() -> None:
    result = trim(0.7, settled(0.7), influence=replace(INFLUENCE, factor=2))
    assert result.proportional == pytest.approx(1.0)


def test_the_learned_part_integrates_the_error_beyond_the_deadband() -> None:
    result = trim(0.7, still(0.7))
    # 0.5 K beyond the deadband for an hour at 0.3 K per hour per K.
    assert result.learned == pytest.approx(0.15)
    assert result.held is None
    assert result.total == pytest.approx(0.5 + 0.15)
    assert result.state.learned == pytest.approx(0.15) and result.state.at == NOW


def test_inside_the_deadband_nothing_is_learned() -> None:
    result = trim(0.1, still(0.1, 0.4))
    assert result.learned == 0.4
    assert result.held is None


def test_the_learned_part_stays_within_its_limit() -> None:
    result = trim(
        0.9,
        still(0.9, 1.95),
        influence=replace(INFLUENCE, limit=5),
    )
    assert result.learned == INFLUENCE.learn_limit


def test_the_total_stays_within_the_limit() -> None:
    result = trim(1.0, settled(1.0, 1.9))
    assert result.proportional == pytest.approx(0.8)
    assert result.total == INFLUENCE.limit


def test_a_lowered_learn_limit_clamps_what_was_learned() -> None:
    result = trim(0.0, settled(0.0, 1.8), influence=replace(INFLUENCE, learn_limit=1))
    assert result.learned == 1.0


def test_a_learn_rate_of_zero_turns_the_learned_part_off() -> None:
    result = trim(0.9, settled(0.9, 1.5), influence=replace(INFLUENCE, learn_rate=0))
    assert result.learned == 0.0
    assert result.held is None
    assert result.total == pytest.approx(0.7)


# Holding the learned part


def test_a_hold_keeps_the_learned_part() -> None:
    result = trim(0.9, still(0.9, 0.5), held="a warm-up holds the supply")
    assert result.learned == 0.5
    assert result.held == "a warm-up holds the supply"
    assert result.proportional == pytest.approx(0.7)
    # The filter keeps following the room meanwhile.
    assert result.state.at == NOW


def test_a_zone_far_from_its_target_teaches_nothing() -> None:
    error = LEARN_BAND + 0.5
    result = trim(error, still(error, 0.5))
    assert result.learned == 0.5
    assert result.held == "the lead zone is far from its target"
    below = trim(-error, still(-error, 0.5), calling=None)
    assert below.learned == 0.5


def test_the_learned_part_rises_only_once_the_zone_called_long_enough() -> None:
    previous = still(0.7, 0.5)
    recent = trim(0.7, previous, calling=NOW - INFLUENCE.learn_after + 60)
    assert recent.learned == 0.5
    assert recent.held == "the lead zones have not called long enough"
    long = trim(0.7, previous, calling=NOW - INFLUENCE.learn_after)
    assert long.learned == pytest.approx(0.65)


def test_a_satisfied_zone_lowers_the_learned_part_as_if_the_deadband_above_its_target() -> None:
    result = trim(0.5, still(0.5, 0.5), calling=None)
    assert result.learned == pytest.approx(0.5 - 0.3 * 0.2)
    above = trim(-0.7, still(-0.7, 0.5), calling=None)
    # Its own error counts once it is the larger.
    assert above.learned == pytest.approx(0.5 - 0.3 * 0.5)
    without = trim(
        0.5,
        still(0.5, 0.5),
        calling=None,
        influence=replace(INFLUENCE, deadband=0),
    )
    assert without.learned == 0.5


def test_a_room_above_its_target_lowers_the_learned_part_while_calling() -> None:
    result = trim(-0.5, still(-0.5, 0.5), calling=NOW - 60)
    assert result.learned == pytest.approx(0.5 - 0.3 * 0.3)


@pytest.mark.parametrize(("error", "learned"), [(0.9, 1.3), (-0.9, -1.3)])
def test_a_trim_at_its_limit_does_not_wind_up(error: float, learned: float) -> None:
    result = trim(error, still(error, learned))
    assert result.learned == learned
    assert result.held == "the room trim is at its limit"
    assert result.total == pytest.approx(2.0 if error > 0 else -2.0)


def test_a_trim_at_its_limit_still_unwinds() -> None:
    result = trim(-0.5, still(-0.5, 1.9))
    assert result.learned == pytest.approx(1.9 - 0.09)


@pytest.mark.parametrize(("error", "headroom"), [(0.7, (-inf, 0.4)), (-0.7, (-0.4, inf))])
def test_a_supply_target_at_its_bound_does_not_wind_up(
    error: float, headroom: tuple[float, float]
) -> None:
    result = trim(error, still(error, 0.0), headroom=headroom)
    assert result.learned == 0.0
    assert result.held == "the room trim is at its limit"


def test_a_reset_forgets_the_learned_part_but_not_the_filter() -> None:
    result = trim(0.1, settled(0.1, 1.5), reset=True)
    assert result.learned == 0.0
    assert result.error == pytest.approx(0.1)


# Gaps, clocks, and lost readings


@pytest.mark.parametrize("at", [NOW - HOUR - 1, NOW + 60])
def test_a_gap_or_a_clock_step_restarts_the_filter_and_learns_nothing(at: float) -> None:
    result = trim(0.9, RoomTrimState(0.0, at, 0.5))
    assert result.error == 0.9
    assert result.learned == 0.5
    assert result.held == "the room trim starts again from the reading"


@pytest.mark.parametrize("error", [None, nan])
def test_without_a_lead_reading_only_the_learned_part_trims(error: float | None) -> None:
    previous = settled(0.4, 0.6)
    result = trim(error, previous)
    assert result.total == 0.6
    assert result.proportional == 0.0
    assert result.lead is None and result.error is None
    assert result.held == "no lead zone reads its temperature"
    # The calls go on counting meanwhile.
    assert result.state == replace(previous, calling_since=LONG_AGO)
    held = trim(None, previous, held="hot water has the source")
    assert held.held == "hot water has the source"
    off = trim(None, previous, influence=replace(INFLUENCE, learn_rate=0))
    assert off.held is None and off.total == 0.0


def test_the_state_survives_a_round_trip() -> None:
    state = RoomTrimState(0.42, NOW, 1.25, {"room": 21.0}, True, NOW - 60, 0.4, NOW - 600)
    assert RoomTrimState.from_dict(state.to_dict()) == state
    assert RoomTrimState.from_dict({}) == RoomTrimState()
    assert RoomTrimState.from_dict({"error": 0.4, "learned": 0.5}) == RoomTrimState(None, None, 0.5)
    assert RoomTrimState.from_dict({"learned": nan}) == RoomTrimState()
    assert RoomTrimState.from_dict({"targets": {"room": 21.0, "hall": nan, "attic": None}}) == (
        RoomTrimState(targets={"room": 21.0})
    )
    assert RoomTrimState.from_dict({"targets": 21.0}) == RoomTrimState()


# Target changes, a still room, and what the setpoint delivers


@pytest.mark.parametrize(("target", "error"), [(TARGET - 0.5, -0.5), (TARGET + 0.5, 0.8)])
def test_a_target_change_holds_the_learned_part_while_the_room_settles(
    target: float, error: float
) -> None:
    result = trim(error, still(0.3, 0.5), target=target, calling=None)
    assert result.learned == 0.5
    assert result.held == "the lead zone settles after a change of its target"
    assert result.state.settling
    calling = trim(error, result.state, NOW + 600, target=target)
    assert calling.learned == 0.5 and calling.state.settling


def test_a_change_of_lead_zone_with_another_target_does_not_settle() -> None:
    previous = replace(still(0.4, 0.5), targets={"room": TARGET, "hall": TARGET - 0.5})
    hall = room_trim(
        INFLUENCE, previous, NOW, "hall", 0.4, gap=HOUR, calling=LONG_AGO, target=TARGET - 0.5
    )
    # The hall led at its target before, so the switch says nothing of a new one.
    assert not hall.state.settling and hall.state.arrived == LONG_AGO
    assert hall.learned == pytest.approx(0.5 + 0.3 * 0.2)
    back = trim(0.4, hall.state, NOW + 600)
    assert not back.state.settling and back.state.targets == {"room": TARGET, "hall": TARGET - 0.5}
    # A target that changed while another zone led settles once it leads, here
    # at once since the room holds still, and that arrival starts again.
    raised = room_trim(
        INFLUENCE, previous, NOW, "hall", 0.4, gap=HOUR, calling=LONG_AGO, target=TARGET
    )
    assert raised.state.arrived == NOW
    moving = replace(previous, moved_at=NOW - 60)
    raised = room_trim(INFLUENCE, moving, NOW, "hall", 0.4, gap=HOUR, calling=None, target=TARGET)
    assert raised.state.settling
    assert raised.held == "the lead zone settles after a change of its target"
    # So does a zone that never led before.
    new = room_trim(INFLUENCE, moving, NOW, "attic", 0.4, gap=HOUR, calling=None, target=20.0)
    assert new.state.settling


def test_the_settling_ends_once_reading_and_filter_are_within_the_deadband() -> None:
    settling = replace(still(0.15, 0.5), settling=True)
    lagging = trim(0.1, replace(settling, error=0.4))
    assert lagging.state.settling
    arrived = trim(0.1, settling)
    assert not arrived.state.settling and arrived.state.arrived == NOW


def test_the_settling_ends_once_the_room_is_still_short_of_its_target() -> None:
    settling = replace(still(0.6, 0.5), settling=True, moved_at=NOW - SETTLE_TIME)
    result = trim(0.6, settling)
    assert not result.state.settling
    moving = trim(0.6, replace(settling, moved_at=NOW - SETTLE_TIME + 60))
    assert moving.state.settling


def test_a_room_that_still_gets_closer_to_its_target_teaches_nothing() -> None:
    result = trim(0.6, still(0.7, 0.5))
    assert result.learned == 0.5
    assert result.held == "the lead zone still gets closer to its target"
    assert result.state.moved == pytest.approx(result.error) and result.state.moved_at == NOW


def test_a_satisfied_zone_soon_after_arriving_lowers_nothing() -> None:
    previous = replace(still(0.1, 0.5), arrived=NOW - INFLUENCE.learn_after + 60)
    result = trim(0.1, previous, calling=None)
    assert result.learned == 0.5


def test_a_still_room_within_the_deadband_moves_toward_what_the_setpoint_delivers() -> None:
    # The setpoint gives 1.5 K beyond the curve, the learned part claims 1.8 K.
    result = trim(0.1, still(0.1, 1.8), delivered=1.5)
    assert result.learned == pytest.approx(1.8 - 0.3 * 0.3)
    up = trim(0.1, still(0.1, 0.0), delivered=1.0)
    assert up.learned == pytest.approx(0.3)
    moving = trim(0.1, replace(still(0.1, 1.8), moved_at=NOW - 60), delivered=1.5)
    assert moving.learned == 1.8
    satisfied = trim(0.1, still(0.1, 1.8), delivered=1.5, calling=None)
    assert satisfied.learned == pytest.approx(1.8 - 0.3 * 0.2)


def test_the_calls_of_the_lead_zones_count_together() -> None:
    previous = replace(still(0.7, 0.5), calling_since=NOW - INFLUENCE.learn_after)
    # The lead zone that calls now began a minute ago, but another called before.
    joined = trim(0.7, previous, calling=NOW - 60)
    assert joined.learned == pytest.approx(0.65)
    assert joined.state.calling_since == NOW - INFLUENCE.learn_after
    # A moment when none called ends the run.
    paused = trim(0.7, replace(previous, calling_since=None), calling=NOW - 60)
    assert paused.held == "the lead zones have not called long enough"
    assert trim(0.7, previous, calling=None).state.calling_since is None
    # So does an evaluation too long ago to have seen a pause.
    stale = trim(0.7, replace(previous, at=NOW - 2 * HOUR), calling=NOW - 60)
    assert stale.state.calling_since == NOW - 60
    assert RoomTrimState.from_dict(joined.state.to_dict()) == joined.state


# Five minutes between evaluations, as a still room's own deadline gives.
TICK = 300.0
DAY = 24 * HOUR


def replay(
    state: RoomTrimState,
    start: float,
    hours: float,
    zones: Callable[[float], dict[str, tuple[float, float, float | None]]],
) -> tuple[RoomTrimState, int]:
    """Step the trim through ``hours`` of two lead zones, as ``step()`` leads them.

    ``zones`` gives each zone's target, error and since when it calls at a time.
    Return the State and how often the lead changed.
    """
    lead, switches = None, 0
    for tick in range(int(hours * HOUR / TICK)):
        now = start + tick * TICK
        rooms = zones(now)
        calls = {slug: room for slug, room in rooms.items() if room[2] is not None}
        slug, (target, error, _) = max((calls or rooms).items(), key=lambda item: item[1][1])
        switches += lead is not None and slug != lead
        lead = slug
        since = [room[2] for room in calls.values() if room[2] is not None]
        result = room_trim(
            INFLUENCE,
            state,
            now,
            slug,
            error,
            gap=HOUR,
            calling=min(since, default=None),
            target=target,
        )
        state = result.state
    return state, switches


def test_a_curve_learned_low_in_mild_weather_climbs_back_when_it_turns_cold() -> None:
    """The mild week, then the cold spell, that ``home`` saw at the end of November 2026.

    A mild week satisfies both lead zones, ``living`` at 22 °C and ``bedroom`` at
    21.5 °C, all but two hours each morning, so the learned part falls to its
    limit. Then the cold leaves both 0.3 to 0.6 K below their targets: each
    still pauses for twenty minutes every five hours, the two out of step, and
    the colder of the two changes every hour and a half, so no one zone's call
    lasts ``learn_after`` and the lead keeps moving between them.
    """
    start = NOW - 30 * DAY

    def mild(now: float) -> dict[str, tuple[float, float, float | None]]:
        hour = (now - start) % DAY / HOUR
        morning = now - (now - start) % DAY + 6 * HOUR
        calling = 6 <= hour < 8
        error = 0.3 if calling else -0.1
        since = morning if calling else None
        return {"living": (22.0, error, since), "bedroom": (21.5, error - 0.05, since)}

    state, _ = replay(RoomTrimState(), start, 7 * 24, mild)
    assert state.learned == -INFLUENCE.learn_limit

    cold = start + 7 * DAY

    def frosty(now: float) -> dict[str, tuple[float, float, float | None]]:
        rooms: dict[str, tuple[float, float, float | None]] = {}
        for slug, target, shift, phase in (("living", 22.0, 0.0, 0.0), ("bedroom", 21.5, pi, 2.5)):
            error = 0.45 + 0.15 * sin(2 * pi * (now - cold) / (3 * HOUR) + shift)
            # Each pauses twenty minutes every five hours, out of step with the other.
            into = (now - cold - phase * HOUR) % (5 * HOUR)
            since = None if into < 1200 else now - into + 1200
            rooms[slug] = (target, error, since)
        return rooms

    after_a_day, switches = replay(state, cold, 24, frosty)
    assert switches >= 12
    # It climbs back from its limit within a day, and most of the way in two.
    assert after_a_day.learned > -1.5
    after_two, _ = replay(after_a_day, cold + DAY, 24, frosty)
    assert after_two.learned > -0.5
