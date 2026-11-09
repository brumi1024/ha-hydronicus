"""The source's curve number, which Hydronicus owns like the DHW target."""

from __future__ import annotations

from dataclasses import replace

import pytest

from custom_components.hydronicus.core.heating_supply import HeatingSupplyState, SupplyCommand
from custom_components.hydronicus.core.model import (
    CurveNumber,
    HeatingSupply,
    Mode,
    NumericTarget,
    OutputRole,
    Plant,
)
from custom_components.hydronicus.core.plant_file import (
    PlantFileError,
    export_plant,
    load_yaml,
    parse_plant,
    read_plant_file,
    write_plant_file,
)
from custom_components.hydronicus.core.step import NumericState, Observations, Sent, State

from .test_heating_supply import CURVE, SUPPLY, heating, source
from .test_step import HEAT_PUMP, NOW, _plant, run

NUMBER = "number.curve_number"


def plant() -> Plant:
    """The heat pump Plant with a weather curve, its curve number, and a supply number."""
    lines = [
        f"  weather_curve: {{switch: {CURVE}, curve_number: "
        f"{{entity: {NUMBER}, minimum: 1, maximum: 8}}}}",
        f"  supply: {{entity: {SUPPLY}, heat_temperature: 33, minimum: 16, maximum: 50, step: 1}}",
    ]
    return _plant(
        HEAT_PUMP.replace("request: switch.hp", "request: switch.hp\n" + "\n".join(lines))
    )


def observe_curve(value: Plant, *, number: float | None = 6.0, **kwargs: object) -> Observations:
    observations = heating(value, curve=True, **kwargs)  # type: ignore[arg-type]
    return replace(
        observations,
        outputs={**observations.outputs, NUMBER: NumericState(number, NOW - 60)},
    )


def state(**kwargs: object) -> State:
    defaults: dict[str, object] = {
        "strategy": HeatingSupply.SOURCE_CURVE,
        "seen_curve": True,
        "curve_number": 6.0,
        "seen_number": 6.0,
        "last_number": 6.0,
    }
    return State(
        live=True,
        mode=Mode.HEAT,
        heating_supply=HeatingSupplyState(**{**defaults, **kwargs}),  # type: ignore[arg-type]
    )


def test_the_curve_number_is_taken_as_found() -> None:
    value = plant()
    next_state, desired, _ = run(value, observe_curve(value), State(live=True))
    assert next_state.heating_supply.curve_number == 6.0
    assert desired.outputs[NUMBER] == NumericTarget(6.0, 0.5)
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ()
    assert value.outputs()[NUMBER] is OutputRole.SOURCE_CURVE_NUMBER


def test_nothing_is_written_before_the_curve_number_is_known() -> None:
    value = plant()
    next_state, desired, _ = run(value, observe_curve(value, number=None), State(live=True))
    assert next_state.heating_supply.curve_number is None
    assert NUMBER not in desired.outputs


def test_a_curve_number_set_elsewhere_is_adopted() -> None:
    value = plant()
    next_state, desired, _ = run(value, observe_curve(value, number=4.0), state())
    assert next_state.heating_supply.curve_number == 4.0
    assert desired.outputs[NUMBER] == NumericTarget(4.0, 0.5)
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ("the curve number was set elsewhere to 4; adopted",)


def test_hydronicus_s_own_curve_number_landing_is_not_adopted_again() -> None:
    value = plant()
    # The source showed 5, Hydronicus asked for 6, and 6 now lands.
    next_state, desired, _ = run(value, observe_curve(value), state(seen_number=5.0))
    assert next_state.heating_supply.curve_number == 6.0
    assert next_state.heating_supply.seen_number == 6.0
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ()


def test_an_in_flight_curve_number_call_is_not_adopted() -> None:
    value = plant()
    sent = {NUMBER: Sent(NumericTarget(4.0, 0.5), NOW - 5)}
    observations = observe_curve(value, number=4.0, sent=sent)
    next_state, _, _ = run(value, observations, state(last_number=5.0))
    assert next_state.heating_supply.curve_number == 6.0


def test_the_owner_sets_the_curve_number_within_its_range() -> None:
    value = plant()
    for asked, expected in ((3.4, 3.0), (0.0, 1.0), (12.0, 8.0), (float("nan"), 6.0)):
        observations = replace(
            observe_curve(value), supply_command=SupplyCommand(NOW, curve_number=asked)
        )
        next_state, desired, _ = run(value, observations, state())
        assert next_state.heating_supply.curve_number == expected
        assert next_state.heating_supply.last_number == expected
        assert desired.outputs[NUMBER] == NumericTarget(expected, 0.5)


def test_a_handover_sends_the_curve_number_nothing() -> None:
    value = plant()
    value = replace(value, source=replace(source(value), handover_sensor="binary_sensor.handover"))
    observations = observe_curve(value)
    observations = replace(
        observations,
        readiness={
            **observations.readiness,
            "binary_sensor.handover": replace(observations.outputs[CURVE], on=True),  # type: ignore[arg-type]
        },
    )
    _, desired, _ = run(value, observations, state())
    assert NUMBER not in desired.outputs


def test_a_source_forced_off_sends_the_curve_number_nothing() -> None:
    value = plant()
    observations = replace(
        observe_curve(value), supply_command=SupplyCommand(NOW, curve_number=3.0)
    )
    _, desired, _ = run(value, replace(observations, control=False), state())
    assert NUMBER not in desired.outputs


def test_the_curve_number_survives_a_restart() -> None:
    value = plant()
    next_state, _, _ = run(value, observe_curve(value, number=4.0), state())
    assert State.from_dict(next_state.to_dict()) == next_state


def test_a_curve_number_clamps_to_a_whole_number_within_its_range() -> None:
    number = CurveNumber(NUMBER, 1, 8)
    assert number.clamp(5.6) == 6.0
    assert number.clamp(-3.0) == 1.0
    assert number.clamp(9.0) == 8.0


def _document(**source: object) -> dict[str, object]:
    document = load_yaml(HEAT_PUMP)
    document["source"].update(source)
    return document


def test_the_curve_number_roundtrips() -> None:
    value = plant()
    assert source(value).curve_number == CurveNumber(NUMBER, 1, 8)
    exported = export_plant(value)["source"]
    assert exported["weather_curve"]["curve_number"] == {
        "entity": NUMBER,
        "maximum": 8,
    }
    assert read_plant_file(write_plant_file(value)) == value
    defaults = parse_plant(
        _document(weather_curve={"switch": CURVE, "curve_number": {"entity": NUMBER}})
    )
    assert source(defaults).curve_number == CurveNumber(NUMBER, 1, 9)


@pytest.mark.parametrize(
    ("curve_number", "path", "message"),
    [
        ({}, "source.weather_curve.curve_number.entity", "required"),
        ({"entity": "switch.x"}, "source.weather_curve.curve_number.entity", "number"),
        ({"entity": NUMBER, "hotter": "lower"}, "source.weather_curve.curve_number.hotter", ""),
        (
            {"entity": NUMBER, "maximum": 1},
            "source.weather_curve.curve_number.maximum",
            "greater",
        ),
        (
            {"entity": NUMBER, "minimum": 1.5},
            "source.weather_curve.curve_number.minimum",
            "whole",
        ),
    ],
)
def test_the_curve_number_rejects_invalid_values(
    curve_number: dict[str, object], path: str, message: str
) -> None:
    with pytest.raises(PlantFileError) as error:
        parse_plant(_document(weather_curve={"switch": CURVE, "curve_number": curve_number}))
    assert error.value.path == path
    assert message in str(error.value)
