"""The timed warm-up: the heating supply held at least at a warm-up temperature."""

from __future__ import annotations

from dataclasses import replace

import pytest

from custom_components.hydronicus.core.heating_supply import (
    HeatingSupplyState,
    SupplyCommand,
    WarmUpRefusal,
    warm_up_refusal,
)
from custom_components.hydronicus.core.model import (
    HeatingSupply,
    Mode,
    NumericTarget,
    Plant,
    SwitchTarget,
    WarmUp,
)
from custom_components.hydronicus.core.plant_file import (
    PlantFileError,
    export_plant,
    load_yaml,
    parse_plant,
    read_plant_file,
    write_plant_file,
)
from custom_components.hydronicus.core.step import (
    NumericState,
    Observations,
    Reading,
    Sent,
    State,
    SwitchState,
)

from .test_heating_supply import CURVE, SUPPLY, heating, source
from .test_step import HEAT_PUMP, NOW, _plant, run

NUMBER = "number.curve_number"
HANDOVER = "binary_sensor.handover"


def plant(*, supply: bool = True, outdoor: bool = False, extra: str = "") -> Plant:
    """The heat pump Plant with a weather curve, its curve number, and a supply number."""
    lines = [
        f"  weather_curve: {{switch: {CURVE}, curve_number: {{entity: {NUMBER}, maximum: 8}}}}"
    ]
    if supply:
        lines.append(
            f"  supply: {{entity: {SUPPLY}, heat_temperature: 33, minimum: 16, maximum: 50, "
            f"step: 1{', outdoor_sensor: sensor.outdoor' if outdoor else ''}}}"
        )
    if extra:
        lines.append(extra)
    return _plant(
        HEAT_PUMP.replace("request: switch.hp", "request: switch.hp\n" + "\n".join(lines))
    )


def observe(value: Plant, *, curve: bool = True, **kwargs: object) -> Observations:
    """Zone c calls for heat, the curve number reads 6, and the source shows ``curve``."""
    observations = heating(value, curve=curve, **kwargs)  # type: ignore[arg-type]
    return replace(
        observations,
        outputs={**observations.outputs, NUMBER: NumericState(6.0, NOW - 60)},
    )


def state(strategy: HeatingSupply, **kwargs: object) -> State:
    defaults: dict[str, object] = {
        "strategy": strategy,
        "seen_curve": strategy is HeatingSupply.SOURCE_CURVE,
        "seen_setpoint": 30.0,
        "curve_number": 6.0,
        "seen_number": 6.0,
        "last_number": 6.0,
    }
    return State(
        live=True,
        mode=Mode.HEAT,
        heating_supply=HeatingSupplyState(**{**defaults, **kwargs}),  # type: ignore[arg-type]
    )


def warm_up(observations: Observations, at: float = NOW, **command: object) -> Observations:
    return replace(
        observations,
        supply_command=SupplyCommand(at, warm_up=True, **command),  # type: ignore[arg-type]
    )


def landed(value: Plant, *, curve: bool, setpoint: float = 30.0) -> Observations:
    """The curve and the setpoint as Hydronicus asked, its calls landed a moment ago."""
    sent = {
        CURVE: Sent(SwitchTarget(curve), NOW - 5),
        SUPPLY: Sent(NumericTarget(setpoint, 0.5), NOW - 5),
    }
    return observe(value, curve=curve, setpoint=setpoint, sent=sent)


def started_on_the_source_curve(value: Plant, **command: object) -> State:
    started, _, _ = run(
        value, warm_up(observe(value), **command), state(HeatingSupply.SOURCE_CURVE)
    )
    assert started.heating_supply.warming
    return started


def held_on_the_source_curve(value: Plant) -> State:
    """A warm-up on the source's own curve, with the curve off and 40 °C landed."""
    started = started_on_the_source_curve(value)
    held, _, _ = run(value, landed(value, curve=False), started, NOW + 30)
    held, _, _ = run(value, landed(value, curve=False, setpoint=40.0), held, NOW + 60)
    assert held.heating_supply.warming
    return held


# Holding the supply at the warm-up temperature


def test_a_warm_up_on_the_source_curve_turns_it_off_then_holds_the_temperature() -> None:
    value = plant()
    started, desired, due = run(value, warm_up(observe(value)), state(HeatingSupply.SOURCE_CURVE))
    supply = started.heating_supply
    assert supply.warm_until == NOW + 7200 and supply.warm_zones == ("c",)
    assert supply.strategy is HeatingSupply.SOURCE_CURVE
    assert desired.outputs[CURVE] == SwitchTarget(False), "the curve goes off first"
    assert SUPPLY not in desired.outputs, "the setpoint waits for the curve to show off"
    assert desired.outputs[NUMBER] == NumericTarget(6.0, 0.5), "the curve number is untouched"
    assert desired.reasons["warm_up"] == "warming up to 40 °C"
    assert desired.heating_supply is not None
    assert desired.heating_supply.strategy is HeatingSupply.SOURCE_CURVE
    assert desired.heating_supply.warm_up == 40.0
    assert desired.heating_supply.events == (
        "a warm-up raises the heating supply to at least 40 °C for 120 min",
    )
    assert due is not None and due <= 7200 + 1

    # Its own curve-off landing is not adopted as a fixed temperature.
    off, desired, _ = run(value, landed(value, curve=False), started, NOW + 30)
    assert off.heating_supply.strategy is HeatingSupply.SOURCE_CURVE
    assert off.heating_supply.warming and off.heating_supply.fixed is None
    assert desired.outputs[CURVE] == SwitchTarget(False)
    assert desired.outputs[SUPPLY] == NumericTarget(40.0, 0.5)
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ()

    # Nor is its own setpoint landing.
    held, desired, _ = run(value, landed(value, curve=False, setpoint=40.0), off, NOW + 60)
    assert held.heating_supply.strategy is HeatingSupply.SOURCE_CURVE
    assert held.heating_supply.fixed is None
    assert desired.heating_supply is not None and desired.heating_supply.events == ()

    # After its time the curve goes back on and the setpoint is left alone.
    ended, desired, _ = run(value, landed(value, curve=False, setpoint=40.0), held, NOW + 7200)
    assert not ended.heating_supply.warming
    assert desired.outputs[CURVE] == SwitchTarget(True)
    assert SUPPLY not in desired.outputs
    assert "warm_up" not in desired.reasons
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ("the warm-up ended after its time",)

    # Its own curve-on landing is not adopted either.
    back, desired, _ = run(value, landed(value, curve=True, setpoint=40.0), ended, NOW + 7230)
    assert back.heating_supply.strategy is HeatingSupply.SOURCE_CURVE
    assert desired.outputs[CURVE] == SwitchTarget(True)
    assert desired.heating_supply is not None and desired.heating_supply.events == ()


def test_the_curve_turned_on_elsewhere_ends_a_warm_up_on_the_source_curve() -> None:
    value = plant()
    held = held_on_the_source_curve(value)
    ended, desired, _ = run(value, observe(value, curve=True, setpoint=40.0), held, NOW + 600)
    assert not ended.heating_supply.warming
    assert ended.heating_supply.strategy is HeatingSupply.SOURCE_CURVE
    assert desired.outputs[CURVE] == SwitchTarget(True), "the curve stays on"
    assert SUPPLY not in desired.outputs
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "the warm-up ended since the weather curve was turned on elsewhere",
    )


def test_a_warm_up_raises_a_fixed_supply_temperature_to_its_own() -> None:
    value = plant()
    observations = warm_up(observe(value, curve=False))
    started, desired, _ = run(value, observations, state(HeatingSupply.FIXED, fixed=33.0))
    assert desired.outputs[SUPPLY] == NumericTarget(40.0, 0.5)
    assert desired.outputs[CURVE] == SwitchTarget(False)
    assert desired.reasons["warm_up"] == "warming up to 40 °C"
    assert started.heating_supply.fixed == 33.0

    # Its own raised setpoint landing is not adopted as a new fixed temperature.
    later, _, _ = run(value, observe(value, curve=False, setpoint=40.0), started, NOW + 60)
    assert later.heating_supply.fixed == 33.0 and later.heating_supply.warming


def test_a_hotter_fixed_supply_temperature_stays() -> None:
    value = plant()
    observations = warm_up(observe(value, curve=False))
    _, desired, _ = run(value, observations, state(HeatingSupply.FIXED, fixed=45.0))
    assert desired.outputs[SUPPLY] == NumericTarget(45.0, 0.5)


def test_a_warm_up_raises_hydronicus_s_curve_to_its_temperature() -> None:
    value = plant(outdoor=True)
    observations = warm_up(observe(value, curve=False))
    _, desired, _ = run(value, observations, state(HeatingSupply.CURVE))
    assert desired.outputs[SUPPLY] == NumericTarget(40.0, 0.5)


def test_a_hotter_curve_target_stays() -> None:
    value = plant(outdoor=True)
    # 35 °C at 5 °C outdoors is hotter than a warm-up to 30 °C.
    observations = warm_up(observe(value, curve=False), warm_to=30.0)
    _, desired, _ = run(value, observations, state(HeatingSupply.CURVE))
    assert desired.outputs[SUPPLY] == NumericTarget(35.0, 0.5)


@pytest.mark.parametrize(("asked", "expected"), [(37.4, 37.0), (60.0, 50.0), (5.0, 16.0)])
def test_the_warm_up_temperature_keeps_the_supply_s_step_and_limits(
    asked: float, expected: float
) -> None:
    value = plant()
    observations = warm_up(observe(value, curve=False), warm_to=asked)
    started, desired, _ = run(value, observations, state(HeatingSupply.FIXED, fixed=16.0))
    assert desired.outputs[SUPPLY] == NumericTarget(expected, 0.5)
    assert started.heating_supply.warm_to == expected


def test_a_warm_up_is_bounded() -> None:
    value = plant()
    started = started_on_the_source_curve(value, warm_for=99 * 3600)
    assert started.heating_supply.warm_until == NOW + 12 * 3600


def test_the_warm_up_survives_a_restart() -> None:
    started = started_on_the_source_curve(plant(), warm_to=44.0)
    assert State.from_dict(started.to_dict()) == started


def test_a_handover_or_control_off_sends_a_warm_up_nothing() -> None:
    value = plant()
    held = held_on_the_source_curve(value)
    observations = landed(value, curve=False, setpoint=40.0)
    _, desired, _ = run(value, replace(observations, control=False), held, NOW + 90)
    assert CURVE not in desired.outputs and SUPPLY not in desired.outputs

    handed = replace(value, source=replace(source(value), handover_sensor=HANDOVER))
    observations = replace(
        observations, readiness={**observations.readiness, HANDOVER: SwitchState(True, NOW)}
    )
    _, desired, _ = run(handed, observations, held, NOW + 90)
    assert CURVE not in desired.outputs and SUPPLY not in desired.outputs


# The Warm-up temperature setting


def test_the_warm_up_temperature_starts_from_the_plant_file() -> None:
    value = plant(extra="  warm_up: {temperature: 38}")
    _, desired, _ = run(value, observe(value), state(HeatingSupply.SOURCE_CURVE))
    assert desired.heating_supply is not None
    assert desired.heating_supply.warm_temperature == 38.0
    assert desired.heating_supply.warm_up is None


def test_the_owner_sets_the_warm_up_temperature_and_it_survives_a_restart() -> None:
    value = plant()
    setting = replace(observe(value), supply_command=SupplyCommand(NOW, warm_temperature=44.6))
    chosen, desired, _ = run(value, setting, state(HeatingSupply.SOURCE_CURVE))
    assert chosen.heating_supply.warm_temperature == 45.0, "rounded to the setpoint's step"
    assert desired.heating_supply is not None
    assert desired.heating_supply.warm_temperature == 45.0
    assert State.from_dict(chosen.to_dict()) == chosen

    started, desired, _ = run(value, warm_up(observe(value), NOW + 60), chosen, NOW + 60)
    assert started.heating_supply.warming
    assert desired.reasons["warm_up"] == "warming up to 45 °C"


def test_changing_the_warm_up_temperature_applies_to_the_running_warm_up() -> None:
    value = plant()
    started = started_on_the_source_curve(value, warm_to=44.0)
    changing = replace(
        landed(value, curve=False), supply_command=SupplyCommand(NOW + 60, warm_temperature=42.0)
    )
    changed, desired, _ = run(value, changing, started, NOW + 60)
    assert changed.heating_supply.warming
    assert desired.outputs[SUPPLY] == NumericTarget(42.0, 0.5)
    assert desired.reasons["warm_up"] == "warming up to 42 °C"


def test_an_action_s_temperature_applies_to_its_warm_up_only() -> None:
    value = plant()
    started = started_on_the_source_curve(value, warm_to=46.0)
    _, desired, _ = run(value, landed(value, curve=False), started, NOW + 30)
    assert desired.outputs[SUPPLY] == NumericTarget(46.0, 0.5)
    assert started.heating_supply.warm_temperature is None

    ending = replace(observe(value), supply_command=SupplyCommand(NOW + 60, warm_up=False))
    ended, _, _ = run(value, ending, started, NOW + 60)
    again, desired, _ = run(value, warm_up(observe(value), NOW + 120), ended, NOW + 120)
    assert again.heating_supply.warming
    assert desired.reasons["warm_up"] == "warming up to 40 °C"


# Ending it


def test_a_warm_up_ends_once_its_zones_reach_their_targets() -> None:
    value = plant()
    started = started_on_the_source_curve(value)
    warm = observe(value)
    warm = replace(warm, sensors={**warm.sensors, "sensor.c": Reading(21.0, NOW)})
    ended, desired, _ = run(value, warm, started, NOW + 600)
    assert not ended.heating_supply.warming
    assert desired.outputs[CURVE] == SwitchTarget(True)
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "the warm-up ended since its zones reached their targets",
    )


def test_a_warm_up_without_calling_zones_runs_its_time() -> None:
    value = plant()
    quiet = observe(value)
    quiet = replace(quiet, sensors={**quiet.sensors, "sensor.c": Reading(21.0, NOW)})
    started, _, _ = run(value, warm_up(quiet), state(HeatingSupply.SOURCE_CURVE))
    assert started.heating_supply.warming and started.heating_supply.warm_zones == ()
    later, _, _ = run(value, quiet, started, NOW + 600)
    assert later.heating_supply.warming


def test_the_owner_ends_a_warm_up_early() -> None:
    value = plant()
    held = held_on_the_source_curve(value)
    ending = replace(
        landed(value, curve=False, setpoint=40.0),
        supply_command=SupplyCommand(NOW + 120, warm_up=False),
    )
    ended, desired, _ = run(value, ending, held, NOW + 120)
    assert not ended.heating_supply.warming
    assert desired.outputs[CURVE] == SwitchTarget(True)
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ("the warm-up ended early",)


def test_changing_the_heating_supply_strategy_ends_a_warm_up() -> None:
    value = plant()
    held = held_on_the_source_curve(value)
    choosing = replace(
        landed(value, curve=False, setpoint=40.0),
        supply_command=SupplyCommand(NOW + 120, strategy=HeatingSupply.FIXED),
    )
    ended, desired, _ = run(value, choosing, held, NOW + 120)
    assert not ended.heating_supply.warming
    assert desired.outputs[SUPPLY] == NumericTarget(33.0, 0.5)
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "heating now uses a fixed supply temperature",
        "the warm-up ended since the heating supply strategy changed",
    )


def test_a_warm_up_ends_when_the_plant_cools() -> None:
    value = plant()
    started = started_on_the_source_curve(value)
    cooling = observe(value, mode=Mode.COOL)
    ended, desired, _ = run(value, cooling, replace(started, mode=Mode.COOL), NOW + 60)
    assert not ended.heating_supply.warming
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ("the warm-up ended since the Plant cools",)


def test_a_warm_up_ends_once_the_plant_has_no_supply_setpoint() -> None:
    started = started_on_the_source_curve(plant())
    value = plant(supply=False)
    ended, desired, _ = run(value, observe(value, curve=False), started, NOW + 60)
    assert not ended.heating_supply.warming
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "the warm-up ended since the source has no supply setpoint",
    )


# Refusing one that cannot raise the supply


def test_a_warm_up_is_refused_while_cooling() -> None:
    value = plant()
    cooling = observe(value, mode=Mode.COOL)
    refused, desired, _ = run(
        value, warm_up(cooling), replace(state(HeatingSupply.SOURCE_CURVE), mode=Mode.COOL)
    )
    assert not refused.heating_supply.warming
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "a warm-up only heats, so it was not started while cooling",
    )


@pytest.mark.parametrize("strategy", [HeatingSupply.SOURCE_CURVE, HeatingSupply.FIXED])
def test_a_warm_up_is_refused_without_a_supply_setpoint(strategy: HeatingSupply) -> None:
    value = plant(supply=False)
    curve = strategy is HeatingSupply.SOURCE_CURVE
    refused, desired, _ = run(value, warm_up(observe(value, curve=curve)), state(strategy))
    assert not refused.heating_supply.warming
    assert "warm_up" not in desired.reasons
    assert desired.heating_supply is not None
    assert desired.heating_supply.warm_temperature is None
    assert desired.heating_supply.events == (
        "a warm-up was not started: the source has no supply setpoint to hold",
    )


def test_a_warm_up_refusal_names_why() -> None:
    with_supply, without = source(plant()), source(plant(supply=False))
    assert warm_up_refusal(without, cooling=False) is WarmUpRefusal.NO_SUPPLY
    assert warm_up_refusal(with_supply, cooling=True) is WarmUpRefusal.COOLING
    assert warm_up_refusal(with_supply, cooling=False) is None


# The plant file


def _document(**source: object) -> dict[str, object]:
    document = load_yaml(HEAT_PUMP)
    document["source"].update(source)
    return document


SUPPLY_DOCUMENT = {"entity": SUPPLY, "minimum": 16, "maximum": 50}


def test_the_warm_up_roundtrips() -> None:
    value = plant(extra="  warm_up: {temperature: 45, duration: 3600}")
    assert source(value).warm_up == WarmUp(45.0, 3600.0)
    exported = export_plant(value)["source"]
    assert exported["warm_up"] == {"temperature": 45, "duration": 3600}
    assert "warm_up" not in export_plant(plant())["source"]
    assert read_plant_file(write_plant_file(value)) == value
    assert source(plant()).warm_up == WarmUp(40.0, 7200.0)


@pytest.mark.parametrize(
    ("warm_up", "path", "message"),
    [
        ({"temperature": 51}, "source.warm_up.temperature", "at most 50"),
        ({"temperature": 15}, "source.warm_up.temperature", "at least 16"),
        ({"temperature": "hot"}, "source.warm_up.temperature", "number"),
        ({"duration": 50000}, "source.warm_up.duration", "at most 43200"),
        ({"duration": 0}, "source.warm_up.duration", "positive"),
        ({"shift": 3}, "source.warm_up.shift", ""),
        ({"curve_steps": 1}, "source.warm_up.curve_steps", ""),
    ],
)
def test_the_warm_up_rejects_invalid_values(
    warm_up: dict[str, object], path: str, message: str
) -> None:
    with pytest.raises(PlantFileError) as error:
        parse_plant(_document(supply=SUPPLY_DOCUMENT, warm_up=warm_up))
    assert error.value.path == path
    assert message in str(error.value)


def test_a_warm_up_temperature_needs_a_supply() -> None:
    with pytest.raises(PlantFileError) as error:
        parse_plant(_document(warm_up={"temperature": 40}))
    assert error.value.path == "source.warm_up.temperature"
    assert "supply" in str(error.value)
