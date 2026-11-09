"""The heating supply strategy: who owns the heating supply temperature, and adoption."""

from __future__ import annotations

from dataclasses import replace

import pytest

from custom_components.hydronicus.core.heating_supply import (
    HeatingSupplyState,
    SupplyCommand,
    clamp_fixed,
    heating_supply_step,
)
from custom_components.hydronicus.core.model import (
    HeatingSupply,
    Mode,
    NumericTarget,
    Plant,
    Source,
    SwitchTarget,
)
from custom_components.hydronicus.core.step import (
    NumericState,
    Observations,
    OptionState,
    Reading,
    Sent,
    State,
    SwitchState,
)

from .test_step import HEAT_PUMP, NOW, OFF, ON, _plant, observe, run

CURVE = "switch.curve"
SUPPLY = "number.supply"
REQUEST = "switch.hp"
HEATING = ["switch.c_floor", "switch.floor_pump", "switch.a_ceiling"]


def plant(*, supply: str | None = "", outdoor: bool = False, curve: bool = True) -> Plant:
    """The heat pump Plant with a weather curve switch and a supply number."""
    lines = []
    if curve:
        lines.append(f"  weather_curve: {{switch: {CURVE}}}")
    if supply is not None:
        extra = ", outdoor_sensor: sensor.outdoor" if outdoor else ""
        lines.append(
            f"  supply: {{entity: {SUPPLY}, heat_temperature: 33, minimum: 16, maximum: 50, "
            f"step: 1{extra}{', ' + supply if supply else ''}}}"
        )
    return _plant(
        HEAT_PUMP.replace("request: switch.hp", "request: switch.hp\n" + "\n".join(lines))
    )


def source(value: Plant) -> Source:
    assert value.source is not None
    return value.source


def heating(
    value: Plant,
    *,
    curve: bool | None,
    setpoint: float | None = 30.0,
    mode: Mode = Mode.HEAT,
    sent: dict[str, Sent] | None = None,
    outdoor: float | None = 5.0,
) -> Observations:
    """Zone c calls for heat with its floor loop ready, and the source shows ``curve``."""
    observations = observe(
        value,
        mode=mode,
        temperatures={"c": 19.0} if mode is Mode.HEAT else {"a": 26.0},
        on=HEATING if mode is Mode.HEAT else ["switch.a_ceiling"],
        option="Heat" if mode is Mode.HEAT else "Cool",
        sent=sent,
    )
    outputs = dict(observations.outputs)
    if value.source is not None and value.source.weather_curve is not None:
        outputs[CURVE] = SwitchState(curve, NOW - 60)
    if value.source is not None and value.source.supply is not None:
        outputs[SUPPLY] = NumericState(setpoint, NOW - 60)
    sensors = dict(observations.sensors)
    if outdoor is not None:
        sensors["sensor.outdoor"] = Reading(outdoor, NOW)
    return replace(observations, outputs=outputs, sensors=sensors)


def chosen(strategy: HeatingSupply, **kwargs: float | bool | None) -> State:
    """A heating State whose owner chose ``strategy`` and has seen the outputs."""
    return State(
        live=True,
        mode=Mode.HEAT,
        heating_supply=HeatingSupplyState(strategy=strategy, **kwargs),  # type: ignore[arg-type]
    )


# Strategies in heating


def test_the_source_curve_turns_the_curve_on_and_sends_no_setpoint() -> None:
    value = plant()
    state, desired, _ = run(value, heating(value, curve=True), chosen(HeatingSupply.SOURCE_CURVE))
    assert desired.outputs[CURVE] == ON
    assert SUPPLY not in desired.outputs
    assert desired.source_request
    assert desired.reasons["source_supply"] == "kept by the source's own weather curve"
    assert desired.reasons["heating_supply"] == "the source's own weather curve"
    assert state.heating_supply.strategy is HeatingSupply.SOURCE_CURVE


def test_heating_never_waits_for_the_weather_curve_switch() -> None:
    """The 2026-11-09 fault: a curve switch on its way dropped the heating request."""
    value = plant()
    for strategy, shown in ((HeatingSupply.SOURCE_CURVE, False), (HeatingSupply.FIXED, True)):
        pending = {CURVE: Sent(SwitchTarget(not shown), NOW - 10)}
        _, desired, _ = run(
            value,
            heating(value, curve=shown, sent=pending),
            chosen(strategy, seen_curve=shown),
        )
        assert desired.source_request, strategy
        assert desired.reasons["source"] == "requested"


def test_a_fixed_supply_turns_the_curve_off_then_sets_its_temperature() -> None:
    value = plant()
    state = chosen(HeatingSupply.FIXED, seen_curve=True)
    _, desired, _ = run(value, heating(value, curve=True), state)
    assert desired.outputs[CURVE] == OFF
    assert SUPPLY not in desired.outputs
    assert desired.reasons["source_supply"] == "waiting for the weather curve to turn off"

    _, desired, _ = run(value, heating(value, curve=False, setpoint=30), state)
    assert desired.outputs[SUPPLY] == NumericTarget(33.0, 0.5)
    assert desired.reasons["source_supply"] == "fixed supply target 33.0 °C"
    assert not desired.source_request, "a source not yet running waits for its setpoint"

    next_state, desired, _ = run(value, heating(value, curve=False, setpoint=33), state)
    assert desired.source_request
    assert next_state.heating_supply.last_target == 33.0


def test_a_fixed_supply_without_a_supply_number_is_the_source_s_own() -> None:
    value = plant(supply=None)
    assert source(value).heating_supplies == (HeatingSupply.SOURCE_CURVE, HeatingSupply.FIXED)
    _, desired, _ = run(value, heating(value, curve=False), chosen(HeatingSupply.FIXED))
    assert desired.outputs[CURVE] == OFF
    assert desired.source_request
    assert desired.heating_supply is not None and desired.heating_supply.fixed is None


def test_hydronicus_s_curve_turns_the_curve_off_and_sets_the_curve_temperature() -> None:
    value = plant(outdoor=True)
    state = chosen(HeatingSupply.CURVE, seen_curve=False)
    # 45 °C at -10 °C and 25 °C at 20 °C is 35 °C at 5 °C.
    _, desired, _ = run(value, heating(value, curve=False), state)
    assert desired.outputs[CURVE] == OFF
    assert desired.outputs[SUPPLY] == NumericTarget(35.0, 0.5)
    assert desired.reasons["heating_supply"] == "Hydronicus's heating curve"


def test_a_lost_outdoor_reading_blocks_only_the_curve_strategy() -> None:
    value = plant(outdoor=True)
    for strategy, requested in ((HeatingSupply.CURVE, False), (HeatingSupply.FIXED, True)):
        _, desired, _ = run(
            value,
            heating(value, curve=False, setpoint=33, outdoor=None),
            chosen(strategy, seen_curve=False),
        )
        assert desired.source_request is requested, strategy


# Adopting a change made elsewhere


def test_the_curve_turned_off_elsewhere_is_adopted_as_a_fixed_supply() -> None:
    value = plant()
    state = chosen(HeatingSupply.SOURCE_CURVE, seen_curve=True)
    next_state, desired, _ = run(value, heating(value, curve=False, setpoint=34), state)
    assert next_state.heating_supply.strategy is HeatingSupply.FIXED
    assert next_state.heating_supply.fixed == 34, "the source's own fixed setpoint stays"
    assert desired.outputs[SUPPLY] == NumericTarget(34.0, 0.5)
    assert desired.outputs[CURVE] == OFF, "the owner's change is never reverted"
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "the weather curve was turned off elsewhere; heating now uses a fixed supply temperature",
    )
    assert desired.source_request


def test_the_curve_turned_on_elsewhere_is_adopted_as_the_source_curve() -> None:
    value = plant()
    state = chosen(HeatingSupply.FIXED, seen_curve=False)
    next_state, desired, _ = run(value, heating(value, curve=True), state)
    assert next_state.heating_supply.strategy is HeatingSupply.SOURCE_CURVE
    assert desired.outputs[CURVE] == ON
    assert SUPPLY not in desired.outputs


def test_hydronicus_s_own_curve_change_landing_is_not_an_adoption() -> None:
    value = plant()
    state = chosen(HeatingSupply.FIXED, seen_curve=True)
    landing = {CURVE: Sent(OFF, NOW - 5)}
    next_state, desired, _ = run(value, heating(value, curve=False, sent=landing), state)
    assert next_state.heating_supply.strategy is HeatingSupply.FIXED
    assert desired.heating_supply is not None and desired.heating_supply.events == ()


def test_a_setpoint_set_elsewhere_becomes_the_fixed_temperature() -> None:
    value = plant()
    state = chosen(HeatingSupply.FIXED, seen_curve=False, seen_setpoint=33, last_target=33)
    next_state, desired, _ = run(value, heating(value, curve=False, setpoint=35), state)
    assert next_state.heating_supply.fixed == 35
    assert desired.outputs[SUPPLY] == NumericTarget(35.0, 0.5)
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == (
        "the fixed supply temperature was set elsewhere to 35 °C",
    )


def test_a_setpoint_set_elsewhere_overrides_hydronicus_s_curve_with_a_fixed_supply() -> None:
    value = plant(outdoor=True)
    state = chosen(HeatingSupply.CURVE, seen_curve=False, seen_setpoint=35, last_target=35)
    next_state, desired, _ = run(value, heating(value, curve=False, setpoint=38), state)
    assert next_state.heating_supply.strategy is HeatingSupply.FIXED
    assert next_state.heating_supply.fixed == 38
    assert desired.outputs[SUPPLY] == NumericTarget(38.0, 0.5)


def test_hydronicus_s_own_setpoint_landing_is_not_an_adoption() -> None:
    value = plant(outdoor=True)
    # The curve moved from 35 to 36 °C; the new value lands.
    state = chosen(HeatingSupply.CURVE, seen_curve=False, seen_setpoint=35, last_target=36)
    next_state, _, _ = run(value, heating(value, curve=False, setpoint=36), state)
    assert next_state.heating_supply.strategy is HeatingSupply.CURVE
    landing = {SUPPLY: Sent(NumericTarget(37, 0.5), NOW - 5)}
    next_state, _, _ = run(value, heating(value, curve=False, setpoint=37, sent=landing), state)
    assert next_state.heating_supply.strategy is HeatingSupply.CURVE


def test_a_setpoint_change_is_ignored_while_the_source_curve_owns_heating() -> None:
    value = plant()
    state = chosen(HeatingSupply.SOURCE_CURVE, seen_curve=True, seen_setpoint=30)
    next_state, desired, _ = run(value, heating(value, curve=True, setpoint=40), state)
    assert next_state.heating_supply.strategy is HeatingSupply.SOURCE_CURVE
    assert next_state.heating_supply.fixed is None
    assert next_state.heating_supply.seen_setpoint == 40
    assert SUPPLY not in desired.outputs


def test_the_first_sighting_takes_over_what_the_source_does() -> None:
    value = plant()
    for shown, expected in ((True, HeatingSupply.SOURCE_CURVE), (False, HeatingSupply.FIXED)):
        next_state, desired, _ = run(value, heating(value, curve=shown), State(live=True))
        assert next_state.heating_supply.strategy is expected
        assert desired.outputs[CURVE] == SwitchTarget(shown)
        assert desired.heating_supply is not None and desired.heating_supply.events == ()


def test_an_unknown_curve_uses_the_default_until_it_is_seen() -> None:
    value = plant()
    next_state, desired, _ = run(value, heating(value, curve=None), State(live=True))
    assert next_state.heating_supply.strategy is None
    assert desired.heating_supply is not None
    assert desired.heating_supply.strategy is HeatingSupply.SOURCE_CURVE


def test_a_change_during_a_handover_is_adopted_and_nothing_is_sent() -> None:
    value = plant()
    value = replace(
        value,
        source=replace(source(value), handover_sensor="binary_sensor.handover"),
    )
    observations = heating(value, curve=False)
    observations = replace(
        observations,
        readiness={**observations.readiness, "binary_sensor.handover": SwitchState(True, NOW)},
    )
    state = chosen(HeatingSupply.SOURCE_CURVE, seen_curve=True)
    next_state, desired, _ = run(value, observations, state)
    assert next_state.heating_supply.strategy is HeatingSupply.FIXED
    assert CURVE not in desired.outputs and SUPPLY not in desired.outputs


def test_dry_run_judges_changes_on_the_physical_outputs() -> None:
    value = plant()
    observations = heating(value, curve=False)
    observations = replace(
        observations,
        control=False,
        physical_outputs=observations.outputs,
        outputs={**observations.outputs, CURVE: SwitchState(True, NOW)},
    )
    state = replace(chosen(HeatingSupply.SOURCE_CURVE, seen_curve=True), live=False)
    next_state, _, _ = run(value, observations, state)
    assert next_state.heating_supply.strategy is HeatingSupply.FIXED


# Cooling


def test_cooling_turns_the_curve_off_waits_for_it_and_adopts_nothing() -> None:
    value = plant()
    state = State(
        live=True,
        mode=Mode.COOL,
        last_mode=Mode.COOL,
        heating_supply=HeatingSupplyState(HeatingSupply.FIXED, seen_curve=False),
    )
    observations = heating(value, curve=True, mode=Mode.COOL)
    observations = replace(
        observations,
        outputs={**observations.outputs, "select.hp": OptionState("Cool", NOW)},
        sensors={**observations.sensors, "sensor.a_rh": Reading(55, NOW)},
    )
    next_state, desired, _ = run(value, observations, state)
    assert desired.outputs[CURVE] == OFF, "the source's own cooling knows no dew point"
    assert not desired.source_request
    assert desired.reasons["source_supply"] == "waiting for the weather curve to turn off"
    assert next_state.heating_supply.strategy is HeatingSupply.FIXED
    assert next_state.heating_supply.seen_curve is True

    off = replace(observations, outputs={**observations.outputs, CURVE: SwitchState(False, NOW)})
    _, desired, _ = run(value, off, next_state)
    # 55 % at 26 °C is a dew point of 16.4 °C; 16.4 + 2 + 1 + 0.5 rounds up to 20.
    assert desired.outputs[SUPPLY] == NumericTarget(20.0, 0.5)


def test_the_plant_off_leaves_the_curve_as_it_is() -> None:
    value = plant()
    observations = heating(value, curve=True, mode=Mode.OFF)
    _, desired, _ = run(value, observations, chosen(HeatingSupply.FIXED, seen_curve=True))
    assert CURVE not in desired.outputs


# The owner's commands and the State


def test_the_owner_chooses_a_strategy_and_a_fixed_temperature() -> None:
    value = plant()
    command = SupplyCommand(NOW, HeatingSupply.FIXED, 34.4)
    observations = replace(heating(value, curve=True), supply_command=command)
    next_state, desired, _ = run(
        value, observations, chosen(HeatingSupply.SOURCE_CURVE, seen_curve=True)
    )
    assert next_state.heating_supply.strategy is HeatingSupply.FIXED
    assert next_state.heating_supply.fixed == 34, "rounded to the setpoint's step"
    assert next_state.heating_supply.command_at == NOW
    assert desired.outputs[CURVE] == OFF
    assert desired.heating_supply is not None
    assert desired.heating_supply.events == ("heating now uses a fixed supply temperature",)

    again, _, _ = run(
        value,
        observations,
        replace(
            next_state,
            heating_supply=replace(next_state.heating_supply, strategy=HeatingSupply.SOURCE_CURVE),
        ),
    )
    assert again.heating_supply.strategy is HeatingSupply.SOURCE_CURVE, "each command applies once"


def test_a_strategy_the_source_does_not_offer_is_refused() -> None:
    value = plant()
    command = SupplyCommand(NOW, HeatingSupply.CURVE)
    observations = replace(heating(value, curve=True), supply_command=command)
    next_state, _, _ = run(value, observations, chosen(HeatingSupply.SOURCE_CURVE, seen_curve=True))
    assert next_state.heating_supply.strategy is HeatingSupply.SOURCE_CURVE


def test_a_stored_strategy_the_source_no_longer_offers_falls_back_to_its_default() -> None:
    value = plant(outdoor=False)
    next_state, desired, _ = run(
        value, heating(value, curve=True), chosen(HeatingSupply.CURVE, seen_curve=True)
    )
    assert desired.heating_supply is not None
    assert desired.heating_supply.strategy is HeatingSupply.SOURCE_CURVE
    assert next_state.heating_supply.strategy is None


def test_the_heating_supply_survives_a_restart() -> None:
    state = chosen(
        HeatingSupply.FIXED,
        fixed=34.0,
        seen_curve=False,
        seen_setpoint=34.0,
        last_target=34.0,
        command_at=NOW,
    )
    assert State.from_dict(state.to_dict()) == state
    assert State.from_dict({}).heating_supply == HeatingSupplyState()


def test_a_source_without_a_curve_or_a_supply_has_no_heating_supply() -> None:
    value = plant(supply=None, curve=False)
    assert (
        heating_supply_step(
            source(value), Mode.HEAT, None, None, lambda _: False, HeatingSupplyState(), None
        )
        is None
    )
    _, desired, _ = run(value, heating(value, curve=None))
    assert desired.heating_supply is None


@pytest.mark.parametrize(
    ("value", "expected"), [(34.4, 34.0), (60.0, 50.0), (10.0, 16.0), (float("nan"), None)]
)
def test_a_fixed_temperature_keeps_the_supply_s_limits_and_step(
    value: float, expected: float | None
) -> None:
    assert clamp_fixed(source(plant()), value) == expected
    assert clamp_fixed(source(plant(supply=None)), value) is None
