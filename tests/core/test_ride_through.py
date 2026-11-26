"""An output unavailable for a moment keeps its last known state for ``RIDE_THROUGH``.

The scenes replay what ``home`` showed on 2026-11-26 at 14:08:16: the Pro 4PM
that switches the living and bedroom valves, the circulation pump, and the towel
dryer pump went unavailable for 0.65 s while every zone called, and the heat
pump's request was released and then sat out its twelve minutes off.
"""

from __future__ import annotations

from dataclasses import replace

from custom_components.hydronicus.core.step import (
    RIDE_THROUGH,
    KnownOutput,
    Observations,
    State,
    SwitchState,
    step,
)

from .test_step import NOW, OFF, ON, _plant, observe, targets

# A heat pump, a circulation pump serving four ceiling loops, each behind one
# valve, and a towel dryer pump that runs with the source, kept off for twelve
# minutes once released, as on home.
HOUSE = """
hydronicus: 2
name: House
source: {request: switch.hp, post_run: 120, min_on: 600, min_off: 720}
pumps:
  circulation: {switch: switch.circulation_pump, overrun: 180}
  towel: {switch: switch.towel_pump, overrun: 0}
loops:
  towel: {pump: towel, runs: with_source}
zones:
  living:
    temperature: [sensor.living]
    humidity: [sensor.living_rh]
    loops:
      ceiling: {valves: [switch.living_valve], pump: circulation}
  bedroom:
    temperature: [sensor.bedroom]
    humidity: [sensor.bedroom_rh]
    loops:
      ceiling: {valves: [switch.bedroom_valve], pump: circulation}
  basement:
    temperature: [sensor.basement]
    humidity: [sensor.basement_rh]
    loops:
      ceiling: {valves: [switch.basement_valve], pump: circulation}
  office:
    temperature: [sensor.office]
    humidity: [sensor.office_rh]
    loops:
      ceiling: {valves: [switch.office_valve], pump: circulation}
"""
PLANT = _plant(HOUSE)
VALVES = tuple(f"switch.{zone}_valve" for zone in ("living", "bedroom", "basement", "office"))
PUMPS = ("switch.circulation_pump", "switch.towel_pump")
OUTPUTS = (*VALVES, *PUMPS, "switch.hp")
# What the Pro 4PM switches: two valves and both pumps.
PRO_4PM = ("switch.living_valve", "switch.bedroom_valve", *PUMPS)
# Every zone calls, every valve has long been open, and the heat pump has run for an hour.
COLD = {zone.slug: 20.0 for zone in PLANT.zones}
SINCE = NOW - 3600.0
# The blip: the 4PM goes unavailable at 14:08:16.486 and is back at 14:08:17.132.
LOST = NOW + 0.486
BACK = NOW + 1.132


def heating(*, unavailable: tuple[str, ...] = (), lost: float = LOST) -> Observations:
    """Every zone calling with everything on, and ``unavailable`` gone since ``lost``."""
    return observe(
        PLANT,
        temperatures=COLD,
        on=OUTPUTS,
        since=dict.fromkeys(OUTPUTS, SINCE) | dict.fromkeys(unavailable, lost),
        unavailable=unavailable,
    )


def running() -> State:
    """The State of a house that has heated steadily for an hour."""
    state = State()
    for at in (NOW - 1200.0, NOW - 600.0, NOW):
        state, desired, _ = step(PLANT, heating(), state, at)
    assert targets(desired, *OUTPUTS) == [ON] * len(OUTPUTS)
    assert desired.source_request is True
    return state


def test_a_blip_of_the_pro_4pm_keeps_the_heat_pump_running() -> None:
    state = running()
    gone, desired, due = step(PLANT, heating(unavailable=PRO_4PM), state, LOST)
    assert desired.source_request is True
    assert targets(desired, *OUTPUTS) == [ON] * len(OUTPUTS)
    assert all(desired.reasons[f"{zone.slug}.ceiling"] == "wanted" for zone in PLANT.zones)
    assert "unavailable, kept as last seen" in desired.reasons["ride_through"]
    assert due is not None and due >= LOST + RIDE_THROUGH - LOST
    assert gone.source_observed is True
    assert gone.known_outputs["switch.living_valve"] == KnownOutput(True, SINCE, LOST)
    assert gone.known_outputs["switch.circulation_pump"] == KnownOutput(True, SINCE, LOST)

    # Home Assistant's output memory gives the returning outputs their old since.
    back, desired, _ = step(PLANT, heating(), gone, BACK)
    assert desired.source_request is True
    assert targets(desired, *OUTPUTS) == [ON] * len(OUTPUTS)
    assert "ride_through" not in desired.reasons
    assert back.ready == state.ready
    assert back.source_observed_changed == state.source_observed_changed
    assert back.known_outputs["switch.living_valve"] == KnownOutput(True, SINCE)


def test_a_blip_of_the_request_switch_keeps_the_request() -> None:
    state = running()
    gone, desired, _ = step(PLANT, heating(unavailable=("switch.hp",)), state, LOST)
    assert desired.source_request is True
    assert gone.source_request is True
    assert gone.source_observed is True
    _, desired, _ = step(PLANT, heating(), gone, LOST + 2.0)
    assert desired.source_request is True
    assert desired.reasons["source"] == "requested"


def test_an_outage_past_the_grace_releases_the_heat_pump() -> None:
    """A 90 s outage of the 4PM is kept for a minute; then the request goes."""
    state = running()
    state, desired, due = step(PLANT, heating(unavailable=PRO_4PM), state, LOST)
    assert desired.source_request is True
    assert due is not None
    state, desired, _ = step(PLANT, heating(unavailable=PRO_4PM), state, LOST + due)
    assert "ride_through" not in desired.reasons
    assert desired.source_request is False
    assert desired.outputs["switch.hp"] == OFF
    assert set(state.known_outputs) == set(OUTPUTS) - set(PRO_4PM)
    # The 4PM's return 90 s on is a return from a real outage, not part of a blip.
    _, desired, _ = step(PLANT, heating(), state, LOST + 90.0)
    assert desired.source_request is False


def test_a_pump_lost_past_the_grace_releases_the_heat_pump() -> None:
    state = running()
    pump = ("switch.circulation_pump",)
    state, desired, due = step(PLANT, heating(unavailable=pump), state, LOST)
    assert desired.source_request is True
    assert due is not None
    _, desired, _ = step(PLANT, heating(unavailable=pump), state, LOST + due)
    assert desired.source_request is False


def test_only_the_dead_valve_loses_its_loop() -> None:
    state = running()
    dead = ("switch.office_valve",)
    state, _, due = step(PLANT, heating(unavailable=dead), state, LOST)
    assert due is not None
    _, desired, _ = step(PLANT, heating(unavailable=dead), state, LOST + due)
    assert desired.reasons["office.ceiling"] != "wanted"
    assert desired.reasons["living.ceiling"] == "wanted"
    assert desired.source_request is True


def test_the_grace_counts_from_when_the_output_was_first_seen_gone() -> None:
    """An entity that keeps reporting a fresh time while gone is not kept forever."""
    state = running()
    state, _, _ = step(PLANT, heating(unavailable=PRO_4PM, lost=LOST), state, LOST)
    later = LOST + RIDE_THROUGH + 1.0
    _, desired, _ = step(PLANT, heating(unavailable=PRO_4PM, lost=later), state, later)
    assert "ride_through" not in desired.reasons
    assert desired.source_request is False


def test_a_valve_that_returns_closed_is_a_change() -> None:
    state = running()
    state, _, _ = step(PLANT, heating(unavailable=PRO_4PM), state, LOST)
    observations = heating()
    outputs = dict(observations.outputs)
    outputs["switch.living_valve"] = SwitchState(False, BACK)
    state, desired, _ = step(PLANT, replace(observations, outputs=outputs), state, BACK)
    assert state.known_outputs["switch.living_valve"] == KnownOutput(False, BACK)
    assert "switch.living_valve" not in state.ready
    assert desired.reasons["bedroom.ceiling"] == "wanted"


def test_nothing_is_kept_for_an_output_never_seen() -> None:
    _, desired, _ = step(PLANT, heating(unavailable=PRO_4PM), State(), LOST)
    assert "ride_through" not in desired.reasons
    assert desired.source_request is False


def test_known_outputs_persist() -> None:
    state = running()
    state, _, _ = step(PLANT, heating(unavailable=PRO_4PM), state, LOST)
    assert State.from_dict(state.to_dict()).known_outputs == state.known_outputs
    assert State.from_dict({"known_outputs": {"switch.x": {"value": [1]}}}).known_outputs == {}
