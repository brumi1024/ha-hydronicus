"""The heating curve in ``step()``: heating limit, fallback, frost path, offset, lead zone."""

from __future__ import annotations

from dataclasses import replace

import pytest

from custom_components.hydronicus.core.model import Mode, NumericTarget
from custom_components.hydronicus.core.plant_file import (
    PlantFileError,
    export_plant,
    read_plant_file,
)
from custom_components.hydronicus.core.step import NumericState, Observations, Reading, State
from custom_components.hydronicus.core.supply import DampedOutdoor

from .test_step import NOW, OFF, ON, RADIATOR, _plant, observe, run, targets

OUTPUTS = ("switch.valve", "switch.pump", "switch.boiler")


def curve_plant(**supply: object) -> str:
    settings = ", ".join(f"{key}: {value}" for key, value in supply.items())
    return RADIATOR.replace(
        "request: switch.boiler,",
        "request: switch.boiler, supply: {entity: number.supply, "
        f"outdoor_sensor: sensor.outdoor{', ' + settings if settings else ''}}},",
    )


def calling(
    plant_text: str, outdoor: float | None, setpoint: float, **kwargs: object
) -> Observations:
    """A cold room whose loop is ready, with the setpoint showing ``setpoint``."""
    plant = _plant(plant_text)
    observations = observe(
        plant,
        temperatures={"room": 19.0},
        on=["switch.valve", "switch.pump"],
        **kwargs,  # type: ignore[arg-type]
    )
    sensors = dict(observations.sensors)
    if outdoor is not None:
        sensors["sensor.outdoor"] = Reading(outdoor, NOW)
    return replace(
        observations,
        outputs={**observations.outputs, "number.supply": NumericState(setpoint, NOW)},
        sensors=sensors,
    )


# Heating limit


def test_above_the_heating_limit_the_zone_circulates_but_the_source_does_not_heat() -> None:
    text = curve_plant(heating_limit=16)
    state, desired, _ = run(_plant(text), calling(text, 17.0, 25.0))
    assert targets(desired, *OUTPUTS) == [ON, ON, OFF]
    assert desired.reasons["source"] == "warm weather: 17.0 °C outdoors, heating limit 16.0 °C"
    assert state.warm_weather is True
    assert desired.heating_curve is not None and desired.heating_curve.warm_weather


def test_the_heating_limit_holds_until_one_kelvin_below_it() -> None:
    text = curve_plant(heating_limit=16)
    plant = _plant(text)
    state, _, _ = run(plant, calling(text, 17.0, 25.0))
    held, desired, _ = run(plant, calling(text, 15.5, 25.6), state, NOW)
    assert held.warm_weather and not desired.source_request
    released, desired, _ = run(plant, calling(text, 15.0, 45 - 25 / 30 * 20), held, NOW)
    assert not released.warm_weather
    assert desired.source_request


def test_the_heating_limit_releases_a_running_source_after_its_minimum_on_time() -> None:
    text = curve_plant(heating_limit=16)
    plant = _plant(text)
    running = State(
        live=True,
        mode=Mode.HEAT,
        last_mode=Mode.HEAT,
        flowing=True,
        source_request=True,
        source_observed=True,
        source_observed_changed=NOW - 60,
    )
    observations = calling(text, 17.0, 25.0)
    observations = replace(
        observations,
        outputs={
            **observations.outputs,
            "switch.boiler": replace(
                observations.outputs["switch.boiler"], on=True, since=NOW - 60
            ),
        },
    )
    _, desired, _ = run(plant, observations, running)
    assert desired.reasons["source"] == "held for its minimum on time"
    _, desired, _ = run(plant, observations, running, NOW + 240)
    assert desired.reasons["source"] == "warm weather: 17.0 °C outdoors, heating limit 16.0 °C"


def test_frost_protection_heats_above_the_heating_limit() -> None:
    text = curve_plant(heating_limit=16)
    plant = _plant(text)
    frozen = calling(text, 17.0, 27.0, mode=Mode.OFF)
    frozen = replace(
        frozen,
        sensors={"sensor.room": Reading(4.0, NOW), "sensor.outdoor": Reading(17.0, NOW)},
    )
    _, desired, _ = run(plant, frozen, State(live=True))
    assert desired.frost_protection == ("room",)
    assert desired.source_request


# A lost outdoor reading


def test_without_a_fallback_a_lost_outdoor_reading_blocks_ordinary_heating() -> None:
    text = curve_plant()
    _, desired, _ = run(_plant(text), calling(text, None, 35.0))
    assert not desired.source_request
    assert desired.reasons["source"] == "outdoor temperature unavailable"
    assert desired.heating_curve is not None and desired.heating_curve.outdoor is None


def test_a_fallback_keeps_heating_on_its_curve_while_the_reading_is_lost() -> None:
    text = curve_plant(outdoor_fallback=0)
    expected = 45 - 10 / 30 * 20
    _, desired, _ = run(_plant(text), calling(text, None, expected))
    assert desired.outputs["number.supply"] == NumericTarget(pytest.approx(expected), 0.5)
    assert desired.source_request
    assert desired.heating_curve is not None and desired.heating_curve.fallback


def test_frost_protection_heats_without_an_outdoor_reading_or_fallback() -> None:
    text = curve_plant()
    plant = _plant(text)
    expected = 45 - 10 / 30 * 20
    frozen = calling(text, None, expected, mode=Mode.OFF)
    frozen = replace(frozen, sensors={"sensor.room": Reading(4.0, NOW)})
    _, desired, _ = run(plant, frozen, State(live=True))
    assert desired.frost_protection == ("room",)
    assert desired.outputs["number.supply"] == NumericTarget(pytest.approx(expected), 0.5)
    assert desired.source_request


# Offset, damping, and the lead zone


def test_the_owners_offset_replaces_the_configured_one() -> None:
    text = curve_plant(offset=2)
    plant = _plant(text)
    observations = calling(text, 5.0, 37.0)
    assert run(plant, observations)[1].outputs["number.supply"] == NumericTarget(37, 0.5)
    shifted = replace(observations, curve_offset=-1.0)
    _, desired, _ = run(plant, shifted)
    assert desired.outputs["number.supply"] == NumericTarget(34, 0.5)
    assert desired.heating_curve is not None and desired.heating_curve.offset == -1.0


def test_the_damped_outdoor_temperature_is_kept_in_the_state() -> None:
    text = curve_plant(outdoor_damping=3600)
    plant = _plant(text)
    state, _, _ = run(plant, calling(text, 5.0, 35.0))
    assert state.outdoor_damped == DampedOutdoor(5.0, NOW)
    assert State.from_dict(state.to_dict()).outdoor_damped == state.outdoor_damped
    later, _, _ = run(plant, calling(text, 15.0, 35.0), state, NOW + 600)
    assert later.outdoor_damped is not None
    assert 5.0 < later.outdoor_damped.value < 15.0


def test_a_cold_lead_zone_raises_the_curve() -> None:
    text = curve_plant(room_influence="{zone: room, factor: 1.5}")
    _, desired, _ = run(_plant(text), calling(text, 5.0, 38.0))
    # 21 °C target, 19 °C reading: 3 K, at the default limit of 3 K.
    assert desired.outputs["number.supply"] == NumericTarget(38, 0.5)
    assert desired.heating_curve is not None and desired.heating_curve.room_shift == 3.0


# Plant file


def test_the_curve_settings_survive_an_export() -> None:
    text = curve_plant(
        offset=1.5,
        outdoor_damping=10800,
        outdoor_fallback=-2,
        heating_limit=16,
        room_influence="{zone: room, factor: 0.5}",
    )
    plant = _plant(text)
    supply = export_plant(plant)["source"]["supply"]
    assert supply["offset"] == 1.5 and supply["outdoor_damping"] == 10800
    assert supply["outdoor_fallback"] == -2 and supply["heating_limit"] == 16
    assert supply["room_influence"] == {"zone": "room", "factor": 0.5}
    assert read_plant_file(_dump(export_plant(plant))) == plant


def _dump(document: object) -> str:
    import yaml

    return yaml.safe_dump(document)


@pytest.mark.parametrize(
    ("text", "path"),
    [
        (
            RADIATOR.replace(
                "request: switch.boiler,",
                "request: switch.boiler, supply: {entity: number.supply, heating_limit: 16},",
            ),
            "source.supply.heating_limit",
        ),
        (curve_plant(offset=6), "source.supply.offset"),
        (curve_plant(room_influence="{zone: attic}"), "source.supply.room_influence.zone"),
        (
            curve_plant(room_influence="{zone: room, factor: 0}"),
            "source.supply.room_influence.factor",
        ),
    ],
)
def test_curve_settings_are_checked(text: str, path: str) -> None:
    with pytest.raises(PlantFileError) as error:
        read_plant_file(text)
    assert error.value.path == path
