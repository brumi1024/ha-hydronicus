"""The Plant model: a source, pumps, zones, and loops, and how to navigate them."""

from __future__ import annotations

import pytest
from hydronicus_core.model import (
    Desired,
    DigitalThermostat,
    ExternalThermostat,
    LoopRef,
    Mode,
    OptionTarget,
    OutputRole,
    Plant,
    Preset,
    SwitchTarget,
    ValueTarget,
    title_from_slug,
)
from hydronicus_core.plant_file import read_plant_file

from tests.core.plant_files import REFERENCE_PLANT


@pytest.fixture
def plant() -> Plant:
    return read_plant_file(REFERENCE_PLANT.read_text(encoding="utf-8"))


def test_loop_refs_read_as_the_plant_file_writes_them() -> None:
    assert str(LoopRef("living_area", "ceiling")) == "living_area.ceiling"
    assert str(LoopRef(None, "towel_dryer")) == "towel_dryer"
    assert LoopRef.parse("living_area.ceiling") == LoopRef("living_area", "ceiling")
    assert LoopRef.parse("towel_dryer") == LoopRef(None, "towel_dryer")
    for text in ("", "a.b.c", ".b", "a."):
        with pytest.raises(ValueError):
            LoopRef.parse(text)


def test_titles_derive_from_slugs_until_a_name_is_given(plant: Plant) -> None:
    assert title_from_slug("living_area") == "Living area"
    assert plant.zone("living_area").title == "Living area"
    assert plant.pump("floor").title == "Floor"
    assert plant.loop(LoopRef("living_area", "floor")).title == "Floor"
    assert plant.source is not None
    assert plant.source.title == "Heat pump"


def test_plant_navigation(plant: Plant) -> None:
    assert [str(loop.ref) for loop in plant.all_loops] == [
        "towel_dryer",
        "basement.ceiling",
        "bedroom_area.ceiling",
        "living_area.ceiling",
        "living_area.floor",
    ]
    assert [str(loop.ref) for loop in plant.pump_loops("heat_pump")] == [
        "basement.ceiling",
        "bedroom_area.ceiling",
        "living_area.ceiling",
    ]
    assert plant.pump("heat_pump").driven_by_source
    assert not plant.pump("floor").driven_by_source
    assert plant.zone("basement").cools
    assert not plant.loop(LoopRef(None, "towel_dryer")).cools
    assert plant.loop(LoopRef("living_area", "ceiling")).zone == "living_area"
    assert plant.loop(LoopRef("living_area", "ceiling")).slug == "ceiling"
    for missing in (
        lambda: plant.zone("attic"),
        lambda: plant.pump("boiler"),
        lambda: plant.loop(LoopRef("attic", "floor")),
    ):
        with pytest.raises(KeyError):
            missing()


def test_outputs_list_every_commanded_entity_with_its_role(plant: Plant) -> None:
    assert plant.outputs() == {
        "switch.heat_pump_heat_request": OutputRole.SOURCE_REQUEST,
        "select.heat_pump_mode": OutputRole.SOURCE_MODE,
        "switch.home_underfloor_heating_pump": OutputRole.PUMP,
        "switch.home_bathrooms_towel_dryer_pump": OutputRole.PUMP,
        "switch.home_basement_ceiling_heating_valve": OutputRole.VALVE,
        "switch.home_bedroom_area_ceiling_heating_valve": OutputRole.VALVE,
        "switch.home_living_area_ceiling_heating_valve": OutputRole.VALVE,
        "switch.home_living_area_floor_heating_valve": OutputRole.VALVE,
    }


def test_source_mode_options_follow_the_plant_mode(plant: Plant) -> None:
    assert plant.source is not None
    assert plant.source.mode is not None
    assert plant.source.mode.option(Mode.HEAT) == "Heat"
    assert plant.source.mode.option(Mode.COOL) == "Cool"
    assert plant.source.mode.option(Mode.OFF) is None


def test_thermostats(plant: Plant) -> None:
    basement = plant.zone("basement").thermostat
    assert isinstance(basement, DigitalThermostat)
    assert basement.preset_targets == {Preset.COMFORT: 21, Preset.ECO: 19, Preset.AWAY: 16}
    assert plant.zone("living_area").thermostat == DigitalThermostat()
    assert ExternalThermostat("climate.study").entity == "climate.study"


def test_desired_state_holds_one_target_per_output() -> None:
    desired = Desired(
        outputs={
            "switch.valve": SwitchTarget(on=True),
            "select.heat_pump_mode": OptionTarget("Heat"),
            "number.flow_setpoint": ValueTarget(35.0),
        },
        source_request=True,
        mode=Mode.HEAT,
        flow_setpoint=None,
        reasons={"living_area": "Heating demand."},
    )
    assert desired.outputs["switch.valve"] == SwitchTarget(True)
    assert desired.flow_setpoint is None
