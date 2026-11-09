"""The source's DHW: owned settings, adoption of changes elsewhere, hard limits, and the boost."""

from __future__ import annotations

from collections.abc import Callable

from custom_components.hydronicus.core.dhw import DhwCommand, DhwResult, DhwState, dhw_step
from custom_components.hydronicus.core.model import Dhw, NumericTarget, SwitchTarget

NOW = 1_800_000_000.0
SWITCH = "switch.dhw"
SETPOINT = "number.dhw_setpoint"
CONFIG = Dhw(switch=SWITCH, setpoint=SETPOINT, step=1.0)
OWNED = DhwState(on=True, target=50.0, seen_on=True, seen_target=50.0)


def _step(
    switch: bool | None = True,
    setpoint: float | None = 50.0,
    state: DhwState = OWNED,
    command: DhwCommand | None = None,
    now: float = NOW,
    *,
    ours: Callable[[str], bool] = lambda _entity: False,
    commands: bool = True,
    config: Dhw = CONFIG,
) -> DhwResult:
    return dhw_step(
        config, switch, setpoint, ours, state, command, now, lambda at: now >= at, commands=commands
    )


def test_the_first_sight_is_adopted_silently_and_commands_nothing_new() -> None:
    result = _step(state=DhwState())

    assert (result.state.on, result.state.target) == (True, 50.0)
    assert result.targets == {SWITCH: SwitchTarget(True), SETPOINT: NumericTarget(50.0, 0.5)}
    assert result.events == ()
    assert result.reason == "on, 50 °C"


def test_a_change_elsewhere_is_adopted_and_never_written_back() -> None:
    result = _step(switch=False, setpoint=47.0)

    assert (result.state.on, result.state.target) == (False, 47.0)
    assert result.targets == {SWITCH: SwitchTarget(False), SETPOINT: NumericTarget(47.0, 0.5)}
    assert result.events == (
        "DHW was turned off elsewhere; adopted",
        "DHW target changed elsewhere to 47 °C; adopted",
    )


def test_a_call_of_hydronicus_landing_is_no_change_elsewhere() -> None:
    state = DhwState(on=False, target=52.0, seen_on=True, seen_target=50.0)
    result = _step(switch=False, setpoint=52.0, state=state, ours=lambda _entity: True)

    assert (result.state.on, result.state.target) == (False, 52.0)
    assert result.events == ()


def test_a_write_not_taken_is_no_change_and_is_not_adopted() -> None:
    state = DhwState(on=True, target=53.0, seen_on=True, seen_target=50.0)

    result = _step(state=state)
    assert result.state.target == 53.0
    assert result.targets[SETPOINT] == NumericTarget(53.0, 0.5)


def test_an_output_back_from_unavailable_is_not_a_change() -> None:
    lost = _step(switch=None, setpoint=None)
    assert lost.state == OWNED

    back = _step(state=lost.state)
    assert back.events == ()


def test_values_outside_the_hard_limits_are_clamped_and_logged() -> None:
    adopted = _step(setpoint=60.0)
    assert adopted.state.target == 55.0
    assert adopted.targets[SETPOINT] == NumericTarget(55.0, 0.5)
    assert adopted.events == (
        "DHW target changed elsewhere to 60 °C; adopted",
        "DHW target 60 °C is outside its limits; using 55 °C",
    )

    commanded = _step(command=DhwCommand(NOW, target=35.0))
    assert commanded.state.target == 40.0
    assert commanded.events == ("DHW target 35 °C is outside its limits; using 40 °C",)
    assert _step(command=DhwCommand(NOW, target=48.4)).state.target == 48.0, "whole degrees"


def test_a_command_applies_once() -> None:
    command = DhwCommand(NOW, on=False, target=45.0)
    applied = _step(command=command)
    assert (applied.state.on, applied.state.target, applied.state.command_at) == (False, 45.0, NOW)

    landed = _step(
        switch=False, setpoint=45.0, state=applied.state, command=command, ours=lambda _e: True
    )
    assert landed.events == ()
    adopted = _step(switch=True, setpoint=45.0, state=landed.state, command=command)
    assert adopted.state.on is True, "a later change elsewhere wins over a command applied before"


def test_a_boost_raises_the_target_for_its_bounded_time_and_restores_it() -> None:
    boosted = _step(command=DhwCommand(NOW, boost=58.0, boost_for=4 * 3600.0))
    assert boosted.state.boost == 55.0, "a boost keeps the limits too"
    assert boosted.state.boost_until == NOW + CONFIG.max_boost, "and its maximum time"
    assert boosted.targets[SETPOINT] == NumericTarget(55.0, 0.5)
    assert boosted.state.target == 50.0
    assert boosted.reason == "on, boosted to 55 °C"

    landed = _step(setpoint=55.0, state=boosted.state, now=NOW + 60, ours=lambda _e: True)
    assert landed.events == ()
    held = _step(setpoint=55.0, state=landed.state, now=NOW + 600)
    assert held.events == () and held.state.boost_until is not None, "its own value is no change"

    ended = _step(setpoint=55.0, state=held.state, now=NOW + CONFIG.max_boost)
    assert ended.state.boost_until is None
    assert ended.targets[SETPOINT] == NumericTarget(50.0, 0.5)
    assert ended.events == ("the DHW boost ended; restoring 50 °C",)


def test_a_boost_that_ends_while_the_setpoint_is_lost_restores_it_once_it_is_back() -> None:
    boosted = _step(command=DhwCommand(NOW, boost=55.0, boost_for=600.0))
    landed = _step(setpoint=55.0, state=boosted.state, now=NOW + 60, ours=lambda _e: True)

    lost = _step(setpoint=None, state=landed.state, now=NOW + 900)
    assert lost.state.boost_until is None
    back = _step(setpoint=55.0, state=lost.state, now=NOW + 1800)
    assert back.events == (), "the boosted value it shows again is no change elsewhere"
    assert back.targets[SETPOINT] == NumericTarget(50.0, 0.5)


def test_a_change_elsewhere_during_a_boost_ends_it_without_restoring() -> None:
    boosted = _step(command=DhwCommand(NOW, boost=55.0, boost_for=3600.0))
    landed = _step(setpoint=55.0, state=boosted.state, now=NOW + 60, ours=lambda _e: True)

    chosen = _step(setpoint=52.0, state=landed.state, now=NOW + 120)
    assert chosen.state.boost_until is None
    assert chosen.state.target == 52.0
    assert chosen.events == (
        "DHW target changed elsewhere to 52 °C; adopted",
        "the DHW boost ends without restoring, since a value was chosen",
    )


def test_a_boost_can_be_ended_early() -> None:
    boosted = _step(command=DhwCommand(NOW, boost=55.0))
    ended = _step(state=boosted.state, command=DhwCommand(NOW + 60, end_boost=True), now=NOW + 60)

    assert ended.state.boost_until is None
    assert ended.targets[SETPOINT] == NumericTarget(50.0, 0.5)
    assert ended.events == ("the DHW boost was ended",)


def test_nothing_is_commanded_while_hydronicus_must_not_but_changes_are_still_adopted() -> None:
    result = _step(switch=False, commands=False)

    assert result.targets == {}
    assert result.state.on is False


def test_a_switch_only_dhw_has_no_target() -> None:
    result = _step(setpoint=None, state=DhwState(), config=Dhw(switch=SWITCH))

    assert result.targets == {SWITCH: SwitchTarget(True)}
    assert result.reason == "on"


def test_the_state_survives_persistence() -> None:
    state = DhwState(True, 50.0, True, 50.0, 55.0, NOW + 60, NOW)

    assert DhwState.from_dict(state.to_dict()) == state
    assert DhwState.from_dict({}) == DhwState()
