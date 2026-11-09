"""The timed warm-up of the heating supply."""

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
    CurveNumber,
    HeatingSupply,
    Hotter,
    Mode,
    NumericTarget,
    Plant,
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
from custom_components.hydronicus.core.step import NumericState, Observations, Reading, State

from .test_heating_supply import CURVE, SUPPLY, heating, source
from .test_step import HEAT_PUMP, NOW, _plant, run

NUMBER = "number.curve_number"


def plant(
    *, supply: bool = True, outdoor: bool = False, number: bool = True, extra: str = ""
) -> Plant:
    """The heat pump Plant with a weather curve, its curve number, and a supply number."""
    curve_number = (
        f", curve_number: {{entity: {NUMBER}, hotter: lower, minimum: 1, maximum: 8}}"
        if number
        else ""
    )
    lines = [f"  weather_curve: {{switch: {CURVE}{curve_number}}}"]
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


def observe_curve(
    value: Plant, *, curve: bool = True, number: float | None = 6.0, **kwargs: object
) -> Observations:
    observations = heating(value, curve=curve, **kwargs)  # type: ignore[arg-type]
    if value.source is None or value.source.curve_number is None:
        return observations
    return replace(
        observations,
        outputs={**observations.outputs, NUMBER: NumericState(number, NOW - 60)},
    )


def state(strategy: HeatingSupply, **kwargs: object) -> State:
    defaults: dict[str, object] = {
        "strategy": strategy,
        "seen_curve": strategy is HeatingSupply.SOURCE_CURVE,
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


def started_on_the_source_curve(value: Plant) -> State:
    started, _, _ = run(value, warm_up(observe_curve(value)), state(HeatingSupply.SOURCE_CURVE))
    assert started.heating_supply.warming
    return started


# Raising the supply


@pytest.mark.parametrize(
    ("hotter", "expected", "edge"), [(Hotter.LOWER, 4.0, 1.0), (Hotter.HIGHER, 8.0, 4.0)]
)
def test_a_curve_number_steps_hotter_within_its_range(
    hotter: Hotter, expected: float, edge: float
) -> None:
    number = CurveNumber(NUMBER, hotter, 1, 8)
    assert number.step(6.0, 2) == expected
    assert number.step(1.0, 3) == edge


def test_a_warm_up_steps_the_source_curve_hotter_and_restores_it_after_its_time() -> None:
    value = plant()
    observations = warm_up(observe_curve(value))
    started, desired, due = run(value, observations, state(HeatingSupply.SOURCE_CURVE))
    supply = started.heating_supply
    assert supply.warm_until == NOW + 7200 and supply.warm_zones == ("c",)
    assert desired.outputs[NUMBER] == NumericTarget(5.0, 0.5), "one step hotter: lower"
    assert supply.curve_number == 6.0, "the owned curve number stays"
    assert supply.last_number == 5.0, "the stepped number is the one asked for"
    assert desired.reasons["warm_up"] == "warming up by 1 curve step"
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ("a warm-up raises the heating supply for 120 min",)
    assert due is not None and due <= 7200 + 1

    # The stepped number landing is Hydronicus's own, not a change to adopt.
    landed = observe_curve(value, number=5.0)
    running, _, _ = run(value, landed, started, NOW + 60)
    assert running.heating_supply.curve_number == 6.0 and running.heating_supply.warming

    ended, desired, _ = run(value, landed, running, NOW + 7200)
    assert not ended.heating_supply.warming
    assert desired.outputs[NUMBER] == NumericTarget(6.0, 0.5)
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ("the warm-up ended after its time",)
    assert "warm_up" not in desired.reasons


def test_a_warm_up_shifts_a_fixed_supply_temperature() -> None:
    value = plant()
    observations = warm_up(observe_curve(value, curve=False), warm_shift=2)
    started, desired, _ = run(value, observations, state(HeatingSupply.FIXED, fixed=33.0))
    assert desired.outputs[SUPPLY] == NumericTarget(35.0, 0.5)
    assert desired.outputs[NUMBER] == NumericTarget(6.0, 0.5), "the curve number is not used"
    assert desired.reasons["warm_up"] == "warming up by 2 K"
    assert started.heating_supply.fixed == 33.0

    # Its own raised setpoint landing is not adopted as a new fixed temperature.
    landed = observe_curve(value, curve=False, setpoint=35.0)
    later, _, _ = run(value, landed, started, NOW + 60)
    assert later.heating_supply.fixed == 33.0


def test_a_shifted_fixed_supply_temperature_keeps_its_step_and_maximum() -> None:
    value = plant()
    observations = warm_up(observe_curve(value, curve=False), warm_shift=2.5)
    _, desired, _ = run(value, observations, state(HeatingSupply.FIXED, fixed=49.0))
    assert desired.outputs[SUPPLY] == NumericTarget(50.0, 0.5)


def test_a_warm_up_shifts_hydronicus_s_curve() -> None:
    value = plant(outdoor=True)
    observations = warm_up(observe_curve(value, curve=False))
    _, desired, _ = run(value, observations, state(HeatingSupply.CURVE))
    # 35 °C at 5 °C outdoors, plus the default 3 K.
    assert desired.outputs[SUPPLY] == NumericTarget(38.0, 0.5)


def test_a_warm_up_is_bounded() -> None:
    value = plant()
    observations = warm_up(observe_curve(value), warm_for=99 * 3600, warm_shift=50)
    started, _, _ = run(value, observations, state(HeatingSupply.SOURCE_CURVE))
    assert started.heating_supply.warm_until == NOW + 12 * 3600
    assert started.heating_supply.warm_shift == 10


def test_the_warm_up_survives_a_restart() -> None:
    started = started_on_the_source_curve(plant())
    assert State.from_dict(started.to_dict()) == started


# Ending it


def test_a_warm_up_ends_once_its_zones_reach_their_targets() -> None:
    value = plant()
    started = started_on_the_source_curve(value)
    warm = observe_curve(value)
    warm = replace(warm, sensors={**warm.sensors, "sensor.c": Reading(21.0, NOW)})
    ended, desired, _ = run(value, warm, started, NOW + 600)
    assert not ended.heating_supply.warming
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "the warm-up ended since its zones reached their targets",
    )


def test_a_warm_up_without_calling_zones_runs_its_time() -> None:
    value = plant()
    quiet = observe_curve(value)
    quiet = replace(quiet, sensors={**quiet.sensors, "sensor.c": Reading(21.0, NOW)})
    started, _, _ = run(value, warm_up(quiet), state(HeatingSupply.SOURCE_CURVE))
    assert started.heating_supply.warming and started.heating_supply.warm_zones == ()
    later, _, _ = run(value, quiet, started, NOW + 600)
    assert later.heating_supply.warming


def test_the_owner_ends_a_warm_up_early() -> None:
    value = plant()
    started = started_on_the_source_curve(value)
    ending = replace(observe_curve(value), supply_command=SupplyCommand(NOW + 60, warm_up=False))
    ended, desired, _ = run(value, ending, started, NOW + 60)
    assert not ended.heating_supply.warming
    assert desired.outputs[NUMBER] == NumericTarget(6.0, 0.5)
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ("the warm-up ended early",)


def test_a_curve_number_set_elsewhere_ends_a_warm_up_without_restoring() -> None:
    value = plant()
    started = started_on_the_source_curve(value)
    changed, desired, _ = run(value, observe_curve(value, number=3.0), started, NOW + 60)
    assert not changed.heating_supply.warming
    assert changed.heating_supply.curve_number == 3.0
    assert desired.outputs[NUMBER] == NumericTarget(3.0, 0.5)
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "the curve number was set elsewhere to 3; adopted",
        "the warm-up ended without restoring, since a curve number was chosen",
    )


def test_changing_the_heating_supply_strategy_ends_a_warm_up() -> None:
    value = plant()
    started = started_on_the_source_curve(value)
    choosing = replace(
        observe_curve(value, number=5.0),
        supply_command=SupplyCommand(NOW + 60, strategy=HeatingSupply.FIXED),
    )
    ended, desired, _ = run(value, choosing, started, NOW + 60)
    assert not ended.heating_supply.warming
    assert desired.outputs[NUMBER] == NumericTarget(6.0, 0.5)
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "heating now uses a fixed supply temperature",
        "the warm-up ended since the heating supply strategy changed",
    )


def test_a_warm_up_ends_when_the_plant_cools() -> None:
    value = plant()
    started = started_on_the_source_curve(value)
    cooling = observe_curve(value, mode=Mode.COOL)
    ended, desired, _ = run(value, cooling, replace(started, mode=Mode.COOL), NOW + 60)
    assert not ended.heating_supply.warming
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ("the warm-up ended since the Plant cools",)


# Refusing one that would raise nothing


def test_a_warm_up_is_refused_while_cooling() -> None:
    value = plant()
    cooling = observe_curve(value, mode=Mode.COOL)
    refused, desired, _ = run(
        value, warm_up(cooling), replace(state(HeatingSupply.SOURCE_CURVE), mode=Mode.COOL)
    )
    assert not refused.heating_supply.warming
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "a warm-up only heats, so it was not started while cooling",
    )


def test_a_warm_up_is_refused_on_the_source_curve_without_a_curve_number() -> None:
    value = plant(number=False)
    refused, desired, _ = run(
        value, warm_up(observe_curve(value)), state(HeatingSupply.SOURCE_CURVE)
    )
    assert not refused.heating_supply.warming
    assert "warm_up" not in desired.reasons
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "a warm-up was not started: the source's own curve has no curve number to step",
    )


def test_a_warm_up_is_refused_on_the_source_s_own_fixed_setpoint() -> None:
    value = plant(supply=False)
    refused, desired, _ = run(
        value, warm_up(observe_curve(value, curve=False)), state(HeatingSupply.FIXED)
    )
    assert not refused.heating_supply.warming
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "a warm-up was not started: the source's own fixed setpoint cannot be raised",
    )


def test_a_warm_up_refusal_names_why() -> None:
    no_number, no_supply = source(plant(number=False)), source(plant(supply=False))
    assert warm_up_refusal(no_number, HeatingSupply.SOURCE_CURVE, cooling=False) is (
        WarmUpRefusal.NO_CURVE_NUMBER
    )
    assert warm_up_refusal(no_supply, HeatingSupply.FIXED, cooling=False) is (
        WarmUpRefusal.NO_SUPPLY
    )
    assert warm_up_refusal(no_number, HeatingSupply.FIXED, cooling=True) is WarmUpRefusal.COOLING
    assert warm_up_refusal(no_number, HeatingSupply.FIXED, cooling=False) is None


# The plant file


def _document(**source: object) -> dict[str, object]:
    document = load_yaml(HEAT_PUMP)
    document["source"].update(source)
    return document


def test_the_warm_up_roundtrips() -> None:
    value = plant(extra="  warm_up: {shift: 2, curve_steps: 2, duration: 3600}")
    assert source(value).warm_up == WarmUp(2.0, 2, 3600.0)
    exported = export_plant(value)["source"]
    assert exported["warm_up"] == {"shift": 2, "curve_steps": 2, "duration": 3600}
    assert "warm_up" not in export_plant(plant())["source"]
    assert read_plant_file(write_plant_file(value)) == value


@pytest.mark.parametrize(
    ("warm_up", "path", "message"),
    [
        ({"shift": 11}, "source.warm_up.shift", "at most 10"),
        ({"shift": 0}, "source.warm_up.shift", ""),
        ({"curve_steps": 0}, "source.warm_up.curve_steps", "at least 1"),
        ({"curve_steps": 1.5}, "source.warm_up.curve_steps", "whole number"),
        ({"duration": 50000}, "source.warm_up.duration", "at most 43200"),
        ({"hours": 2}, "source.warm_up.hours", ""),
    ],
)
def test_the_warm_up_rejects_invalid_values(
    warm_up: dict[str, object], path: str, message: str
) -> None:
    with pytest.raises(PlantFileError) as error:
        parse_plant(_document(warm_up=warm_up))
    assert error.value.path == path
    assert message in str(error.value)
