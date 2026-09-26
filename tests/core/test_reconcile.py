"""The reconciler: call order, one call in flight, backoff, Repairs, and Dry run."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pytest
from hydronicus_core.model import Desired, Mode, OptionTarget, OutputTarget, Plant, SwitchTarget
from hydronicus_core.plant_file import read_plant_file
from hydronicus_core.reconcile import (
    BACKOFF_MAX,
    CALL_TIMEOUT,
    REPAIR_AFTER,
    Action,
    Attempt,
    Reconciled,
    ReconcileState,
    backoff,
    reconcile,
)
from hydronicus_core.step import TICK, OptionState, OutputState, SwitchState

NOW = 1_800_000_000.0
ON = SwitchTarget(True)
OFF = SwitchTarget(False)

PLANT = """
hydronicus: 2
name: Home
source:
  request: switch.hp
  mode: {entity: select.hp, heat: Heat, cool: Cool}
pumps:
  hp: {driven_by: source, min_flow: guaranteed}
  floor: {switch: switch.floor_pump}
zones:
  room:
    temperature: [sensor.room]
    loops:
      floor: {valves: [switch.floor_valve], pump: floor}
      ceiling: {valves: [switch.ceiling_valve], pump: hp}
"""


@pytest.fixture
def plant() -> Plant:
    return read_plant_file(PLANT)


def _desired(targets: Mapping[str, OutputTarget]) -> Desired:
    return Desired(
        outputs=targets, source_request=False, mode=Mode.HEAT, flow_setpoint=None, reasons={}
    )


def _observed(on: Iterable[str] = (), option: str | None = "Heat") -> dict[str, OutputState]:
    on = set(on)
    outputs: dict[str, OutputState] = {
        entity: SwitchState(entity in on, NOW - 100)
        for entity in (
            "switch.hp",
            "switch.floor_pump",
            "switch.floor_valve",
            "switch.ceiling_valve",
        )
    }
    outputs["select.hp"] = OptionState(option, NOW - 100)
    return outputs


def _run(
    plant: Plant,
    targets: Mapping[str, OutputTarget],
    observed: Mapping[str, OutputState],
    state: ReconcileState | None = None,
    now: float = NOW,
    *,
    armed: Iterable[str] | None = None,
    live: bool = True,
) -> Reconciled:
    return reconcile(
        plant,
        _desired(targets),
        observed,
        state or ReconcileState(),
        now,
        armed=frozenset(plant.outputs() if armed is None else armed),
        live=live,
    )


def test_starting_opens_valves_before_pumps_before_the_source(plant: Plant) -> None:
    targets = {
        "switch.hp": ON,
        "select.hp": OptionTarget("Cool"),
        "switch.floor_pump": ON,
        "switch.floor_valve": ON,
        "switch.ceiling_valve": OFF,
    }
    result = _run(plant, targets, _observed(on=["switch.ceiling_valve"]))
    assert [action.entity for action in result.send] == [
        "switch.floor_valve",
        "switch.ceiling_valve",
        "switch.floor_pump",
        "select.hp",
        "switch.hp",
    ]
    assert result.retry_at == pytest.approx(NOW + CALL_TIMEOUT + TICK)
    assert result.state.attempts["switch.hp"] == Attempt(ON, 1, NOW)


def test_stopping_releases_the_source_before_pumps_before_valves(plant: Plant) -> None:
    targets = {"switch.hp": OFF, "switch.floor_pump": OFF, "switch.floor_valve": OFF}
    running = _observed(on=["switch.hp", "switch.floor_pump", "switch.floor_valve"])
    result = _run(plant, targets, running)
    assert result.send == (
        Action("switch.hp", OFF),
        Action("switch.floor_pump", OFF),
        Action("switch.floor_valve", OFF),
    )


def test_a_call_in_flight_blocks_another_until_it_is_observed_or_times_out(
    plant: Plant,
) -> None:
    sent = ReconcileState(attempts={"switch.floor_pump": Attempt(ON, 1, NOW - 2)})
    # The target flipped while the start is in flight: wait for it.
    result = _run(plant, {"switch.floor_pump": OFF}, _observed(), sent)
    assert result.send == ()
    assert result.retry_at == pytest.approx(NOW + 8 + TICK)
    assert result.state == sent
    # Observed: confirmed, and the new target goes out.
    result = _run(plant, {"switch.floor_pump": OFF}, _observed(on=["switch.floor_pump"]), sent)
    assert result.send == (Action("switch.floor_pump", OFF),)
    assert result.state.attempts["switch.floor_pump"] == Attempt(OFF, 1, NOW)
    # Timed out and no longer wanted: nothing to send, nothing kept.
    later = NOW + CALL_TIMEOUT
    result = _run(plant, {"switch.floor_pump": OFF}, _observed(), sent, later)
    assert result.send == () and result.state.attempts == {}


def test_an_unmet_target_is_retried_with_doubling_backoff_and_then_repaired(
    plant: Plant,
) -> None:
    assert [backoff(count) for count in range(1, 8)] == [10, 20, 40, 80, 160, 300, 300]
    state, now, sends = ReconcileState(), NOW, []
    for _ in range(40):
        result = _run(plant, {"switch.floor_valve": ON}, _observed(), state, now)
        sends.extend(now for _ in result.send)
        if len(sends) == REPAIR_AFTER and not result.send:
            assert "switch.floor_valve" in result.repairs
        state = result.state
        assert result.retry_at is not None
        now = result.retry_at
    offsets = [round(sent - NOW) for sent in sends[:7]]
    assert offsets == [0, 10, 30, 70, 150, 310, 610]
    assert sends[7] - sends[6] == pytest.approx(BACKOFF_MAX, abs=0.01)
    # The target changed: a new count, and no Repair.
    result = _run(
        plant, {"switch.floor_valve": OFF}, _observed(on=["switch.floor_valve"]), state, now
    )
    assert result.repairs == frozenset()
    assert result.state.attempts["switch.floor_valve"].count == 1


def test_a_repair_is_reported_while_the_next_retry_is_in_flight(plant: Plant) -> None:
    state = ReconcileState(attempts={"switch.floor_valve": Attempt(ON, REPAIR_AFTER + 1, NOW)})
    assert _run(plant, {"switch.floor_valve": ON}, _observed(), state).repairs == {
        "switch.floor_valve"
    }


def test_a_new_target_after_a_failed_call_starts_a_new_count(plant: Plant) -> None:
    failed = ReconcileState(attempts={"switch.floor_pump": Attempt(ON, 5, NOW - 60)})
    result = _run(plant, {"switch.floor_pump": OFF}, _observed(on=["switch.floor_pump"]), failed)
    assert result.send == (Action("switch.floor_pump", OFF),)
    assert result.state.attempts["switch.floor_pump"] == Attempt(OFF, 1, NOW)
    assert result.repairs == frozenset()
    # Also when the output is unavailable: the old count goes, and nothing is sent.
    observed = _observed()
    observed["switch.floor_pump"] = SwitchState(None, NOW)
    result = _run(plant, {"switch.floor_pump": OFF}, observed, failed)
    assert result.send == () and result.state.attempts == {}


def test_unarmed_and_unavailable_outputs_are_never_sent_anything(plant: Plant) -> None:
    targets = {"switch.floor_valve": ON, "switch.ceiling_valve": ON}
    observed = _observed()
    observed["switch.ceiling_valve"] = SwitchState(None, NOW)
    failing = ReconcileState(attempts={"switch.ceiling_valve": Attempt(ON, 2, NOW - 60)})
    result = _run(plant, targets, observed, failing, armed=["switch.ceiling_valve"])
    assert result.send == ()
    assert result.state.attempts == failing.attempts, "the count survives the outage"
    assert _run(plant, {"switch.floor_valve": ON}, {}, None).send == ()


def test_dry_run_proposes_and_counts_each_proposal_as_observed(plant: Plant) -> None:
    targets = {
        "switch.floor_valve": ON,
        "switch.floor_pump": OFF,
        "select.hp": OptionTarget("Cool"),
    }
    result = _run(plant, targets, _observed(), live=False)
    assert result.send == ()
    assert result.proposed == (
        Action("switch.floor_valve", ON),
        Action("select.hp", OptionTarget("Cool")),
    )
    assert result.state.dry_run == {
        "switch.floor_valve": SwitchState(True, NOW),
        "select.hp": OptionState("Cool", NOW),
    }
    assert result.retry_at is None
    # Proposed once: not again.
    again = _run(plant, targets, _observed(), result.state, NOW + 5, live=False)
    assert again.proposed == () and again.state == result.state
    # A proposal the real output now shows is dropped, and going live clears the rest.
    real = _observed(on=["switch.floor_valve"])
    assert _run(plant, targets, real, result.state, live=False).state.dry_run == {
        "select.hp": OptionState("Cool", NOW)
    }
    assert _run(plant, {}, real, result.state).state == ReconcileState()
