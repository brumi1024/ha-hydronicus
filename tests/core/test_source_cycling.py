"""The source's cycling limits in ``step()``: starts per hour, start threshold, and health."""

from __future__ import annotations

from dataclasses import replace

from custom_components.hydronicus.core.model import Plant
from custom_components.hydronicus.core.step import START_WINDOW, State
from tests.core.test_step import (
    LONG_AGO,
    NOW,
    OFF,
    ON,
    RADIATOR,
    _plant,
    observe,
    run,
    targets,
)

RUNNING = ["switch.valve", "switch.pump"]
COLD = {"room": 19.0}


def _with(**settings: object) -> Plant:
    plant = _plant(RADIATOR)
    assert plant.source is not None
    return replace(plant, source=replace(plant.source, **settings))


def test_an_observed_start_is_counted_once_and_forgotten_after_the_window() -> None:
    plant = _with(max_starts_per_hour=2)
    off = State(live=True, source_observed=False, source_observed_changed=LONG_AGO)
    started = observe(
        plant, temperatures=COLD, on=[*RUNNING, "switch.boiler"], since={"switch.boiler": NOW - 10}
    )

    state, _, _ = run(plant, started, off)
    assert state.source_starts == (NOW - 10,)
    assert run(plant, started, state, NOW + 60)[0].source_starts == (NOW - 10,)
    later = run(plant, started, state, NOW - 10 + START_WINDOW + 1)[0]
    assert later.source_starts == ()


def test_a_clock_stepping_back_keeps_a_start_that_seems_ahead() -> None:
    plant = _with(max_starts_per_hour=2)
    state = State(live=True, source_starts=(NOW + 300,))

    assert run(plant, observe(plant), state)[0].source_starts == (NOW + 300,)


def test_the_last_allowed_start_holds_the_next_until_the_oldest_leaves_the_window() -> None:
    plant = _with(max_starts_per_hour=2, min_off=0)
    starts = (NOW - 3000, NOW - 1000)
    state = State(
        live=True, source_observed=False, source_observed_changed=NOW - 500, source_starts=starts
    )
    ready = observe(plant, temperatures=COLD, on=RUNNING, since={"switch.boiler": NOW - 500})

    _, desired, due = run(plant, ready, state)
    assert not desired.source_request
    assert desired.reasons["source"] == "held off: 2 starts within the last hour"
    assert due is not None and NOW + due >= starts[0] + START_WINDOW
    assert run(plant, ready, state, starts[0] + START_WINDOW + 1)[1].source_request


def test_a_start_threshold_gates_only_the_start() -> None:
    plant = _with(start_threshold=1.5)
    ready = observe(plant, temperatures=COLD, on=RUNNING)

    _, desired, _ = run(plant, ready)
    assert not desired.source_request
    assert desired.reasons["source"] == "demand 1 below the start threshold 1.5"
    heavy = replace(
        plant,
        zones=tuple(
            replace(zone, loops=tuple(replace(loop, weight=2.0) for loop in zone.loops))
            for zone in plant.zones
        ),
    )
    assert run(heavy, ready)[1].source_request

    running = observe(
        plant, temperatures=COLD, on=[*RUNNING, "switch.boiler"], since={"switch.boiler": NOW - 60}
    )
    held = State(
        live=True, source_request=True, source_observed=True, source_observed_changed=NOW - 60
    )
    assert run(plant, running, held)[1].source_request, "a running request is never cut short"


def test_an_unhealthy_or_unknown_source_is_never_requested_and_released_at_once() -> None:
    plant = _with(health_sensor="binary_sensor.healthy")
    ready = observe(plant, temperatures=COLD, on=RUNNING, readiness={"binary_sensor.healthy": True})
    assert run(plant, ready)[1].source_request

    unknown = observe(plant, temperatures=COLD, on=RUNNING)
    _, desired, _ = run(plant, unknown)
    assert not desired.source_request
    assert desired.source_fault == "source health sensor binary_sensor.healthy is unavailable"

    running = observe(
        plant,
        temperatures=COLD,
        on=[*RUNNING, "switch.boiler"],
        since={"switch.boiler": NOW - 10},
        readiness={"binary_sensor.healthy": False},
    )
    held = State(
        live=True, source_request=True, source_observed=True, source_observed_changed=NOW - 10
    )
    _, desired, _ = run(plant, running, held)
    assert targets(desired, "switch.boiler", "switch.pump", "switch.valve") == [OFF, ON, ON]
    assert desired.reasons["source"] == "source health sensor binary_sensor.healthy reports a fault"


def test_a_request_found_on_without_an_open_path_is_reported_and_released() -> None:
    plant = _plant(RADIATOR)
    held = State(
        live=True, source_request=True, source_observed=True, source_observed_changed=NOW - 100
    )
    stranded = observe(plant, on=["switch.boiler"], since={"switch.boiler": NOW - 100})

    _, desired, _ = run(plant, stranded, held)
    assert desired.source_without_path
    assert desired.outputs["switch.boiler"] == OFF

    running = observe(
        plant, temperatures=COLD, on=[*RUNNING, "switch.boiler"], since={"switch.boiler": NOW - 100}
    )
    _, desired, _ = run(plant, running, held)
    assert not desired.source_without_path and desired.source_request


def test_a_separator_gives_flow_but_no_sink_so_a_closed_plant_is_still_reported() -> None:
    plant = _plant(
        RADIATOR.replace(
            "  pump: {switch: switch.pump, overrun: 120}",
            "  pump: {switch: switch.pump, overrun: 120}\n"
            "  primary: {driven_by: source, min_flow: guaranteed}",
        )
    )
    held = State(
        live=True, source_request=True, source_observed=True, source_observed_changed=NOW - 100
    )
    stranded = observe(plant, on=["switch.boiler"], since={"switch.boiler": NOW - 100})

    _, desired, _ = run(plant, stranded, held)
    assert desired.source_without_path
    assert desired.outputs["switch.boiler"] == OFF


def test_a_handover_sends_the_source_nothing_and_opens_its_heat_sink() -> None:
    radiator = _plant(RADIATOR).all_loops[0]
    plant = _with(handover_sensor="binary_sensor.handover", heat_sink_loops=(radiator.ref,))
    handed = observe(
        plant,
        on=["switch.boiler"],
        since={"switch.boiler": NOW - 10},
        readiness={"binary_sensor.handover": True},
    )

    state, desired, _ = run(plant, handed)
    assert desired.source_handover
    assert "switch.boiler" not in desired.outputs
    assert desired.outputs["switch.valve"] == ON
    assert desired.reasons["source"] == "handed over: the source's own controller runs it"
    assert not desired.source_without_path
    assert state.source_request, "Hydronicus takes over from the request it finds"

    resting = observe(plant, readiness={"binary_sensor.handover": True})
    _, desired, _ = run(plant, resting)
    assert "switch.boiler" not in desired.outputs
    assert desired.outputs["switch.valve"] == OFF, "a source seen off needs no heat sink"

    back = observe(
        plant,
        on=["switch.boiler"],
        since={"switch.boiler": NOW - 10},
        readiness={"binary_sensor.handover": False},
    )
    _, desired, _ = run(plant, back, state)
    assert not desired.source_handover
    assert desired.outputs["switch.boiler"] == OFF, "no zone needs the source it took back"


def test_arming_a_request_found_running_takes_it_over_without_a_stop() -> None:
    plant = _plant(RADIATOR)
    unarmed = set(plant.outputs()) - {"switch.boiler"}
    found = {"switch.boiler": NOW - 3600}
    running = [*RUNNING, "switch.boiler"]

    state, _, _ = run(
        plant, observe(plant, temperatures=COLD, on=running, since=found, armed=unarmed)
    )
    assert state.source_request, "Hydronicus takes over from the request it finds"

    _, desired, _ = run(plant, observe(plant, temperatures=COLD, on=running, since=found), state)
    assert desired.outputs["switch.boiler"] == ON
    assert desired.reasons["source"] == "requested"

    warm = observe(plant, temperatures={"room": 23.0}, on=running, since=found)
    _, desired, _ = run(plant, warm, state)
    assert desired.outputs["switch.boiler"] == OFF, "a request found without demand is released"
