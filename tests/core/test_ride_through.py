"""An output unavailable for a moment keeps its last known state for ``RIDE_THROUGH``.

The scenes replay what ``home`` showed on 2026-11-26 at 14:08:16: every zone
valve went unavailable for 0.65 s while every zone called, and the heat pump's
request was released and then sat out its twelve minutes off.
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

from .test_step import NOW, OFF, ON, RADIATOR, _plant, observe, targets

# A heat pump with its own pump and four ceiling loops, each behind one valve,
# kept off for twelve minutes once released, as on home.
HOUSE = """
hydronicus: 2
name: House
source: {request: switch.hp, post_run: 120, min_on: 600, min_off: 720}
pumps:
  hp: {driven_by: source, min_flow_loops: [living.ceiling]}
zones:
  living:
    temperature: [sensor.living]
    humidity: [sensor.living_rh]
    loops:
      ceiling: {valves: [switch.living_valve], pump: hp}
  bedroom:
    temperature: [sensor.bedroom]
    humidity: [sensor.bedroom_rh]
    loops:
      ceiling: {valves: [switch.bedroom_valve], pump: hp}
  basement:
    temperature: [sensor.basement]
    humidity: [sensor.basement_rh]
    loops:
      ceiling: {valves: [switch.basement_valve], pump: hp}
  office:
    temperature: [sensor.office]
    humidity: [sensor.office_rh]
    loops:
      ceiling: {valves: [switch.office_valve], pump: hp}
"""
PLANT = _plant(HOUSE)
VALVES = tuple(f"switch.{zone}_valve" for zone in ("living", "bedroom", "basement", "office"))
OUTPUTS = (*VALVES, "switch.hp")
# Every zone calls, every valve has long been open, and the heat pump has run for an hour.
COLD = {zone.slug: 20.0 for zone in PLANT.zones}
SINCE = NOW - 3600.0
# The blip: the valves go unavailable at 14:08:16.486 and are back at 14:08:17.132.
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
    state, desired, _ = step(PLANT, heating(), State(), NOW - 1200.0)
    state, desired, _ = step(PLANT, heating(), state, NOW - 600.0)
    state, desired, _ = step(PLANT, heating(), state, NOW)
    assert targets(desired, *OUTPUTS) == [ON] * 5
    assert desired.source_request is True
    return state


def test_a_blip_of_every_valve_keeps_the_heat_pump_running() -> None:
    state = running()
    gone, desired, due = step(PLANT, heating(unavailable=VALVES), state, LOST)
    assert desired.source_request is True
    assert targets(desired, *OUTPUTS) == [ON] * 5
    assert all(desired.reasons[f"{zone.slug}.ceiling"] == "wanted" for zone in PLANT.zones)
    assert "unavailable, kept as last seen" in desired.reasons["ride_through"]
    assert due is not None and LOST + due >= LOST + RIDE_THROUGH
    assert gone.source_observed is True
    assert gone.known_outputs["switch.living_valve"] == KnownOutput(True, SINCE, LOST)

    # Home Assistant's output memory gives the returning valves their old since.
    back, desired, _ = step(PLANT, heating(), gone, BACK)
    assert desired.source_request is True
    assert targets(desired, *OUTPUTS) == [ON] * 5
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


def test_a_valve_unavailable_past_the_grace_releases_the_heat_pump() -> None:
    """A 90 s outage is kept for a minute; then no loop has a path and the request goes."""
    state = running()
    state, desired, due = step(PLANT, heating(unavailable=VALVES), state, LOST)
    assert desired.source_request is True
    assert due is not None
    state, desired, _ = step(PLANT, heating(unavailable=VALVES), state, LOST + due)
    assert "ride_through" not in desired.reasons
    assert desired.source_request is False
    assert desired.outputs["switch.hp"] == OFF
    assert state.known_outputs == {"switch.hp": KnownOutput(True, SINCE)}
    # The valves' return 90 s on is a return from a real outage, not part of a blip.
    _, desired, _ = step(PLANT, heating(), state, LOST + 90.0)
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
    state, _, _ = step(PLANT, heating(unavailable=VALVES, lost=LOST), state, LOST)
    later = LOST + RIDE_THROUGH + 1.0
    _, desired, _ = step(PLANT, heating(unavailable=VALVES, lost=later), state, later)
    assert "ride_through" not in desired.reasons
    assert desired.source_request is False


def test_a_valve_that_returns_closed_is_a_change() -> None:
    state = running()
    state, _, _ = step(PLANT, heating(unavailable=VALVES), state, LOST)
    observations = heating()
    outputs = dict(observations.outputs)
    outputs["switch.office_valve"] = SwitchState(False, BACK)
    state, desired, _ = step(PLANT, replace(observations, outputs=outputs), state, BACK)
    assert state.known_outputs["switch.office_valve"] == KnownOutput(False, BACK)
    assert "switch.office_valve" not in state.ready
    assert desired.reasons["living.ceiling"] == "wanted"


def test_nothing_is_kept_for_an_output_never_seen() -> None:
    _, desired, _ = step(PLANT, heating(unavailable=VALVES), State(), LOST)
    assert "ride_through" not in desired.reasons
    assert desired.source_request is False


def test_known_outputs_persist() -> None:
    state = running()
    state, _, _ = step(PLANT, heating(unavailable=VALVES), state, LOST)
    assert State.from_dict(state.to_dict()).known_outputs == state.known_outputs
    assert State.from_dict({"known_outputs": {"switch.x": {"value": [1]}}}).known_outputs == {}


def test_a_lost_pump_gets_no_grace() -> None:
    """A switched pump carries the heat away from a source that may be firing."""
    plant = _plant(RADIATOR)
    pump = ("switch.valve", "switch.pump", "switch.boiler")
    state, _, _ = step(plant, observe(plant, temperatures={"room": 19.0}, on=pump), State(), NOW)
    lost = observe(plant, temperatures={"room": 19.0}, on=pump, unavailable=("switch.pump",))
    state, desired, _ = step(plant, lost, state, LOST)
    assert "switch.pump" not in state.known_outputs
    assert "ride_through" not in desired.reasons
    assert desired.source_request is False
