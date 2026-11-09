"""The heating supply in Home Assistant: its select, its fixed temperature, and adoption."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.hydronicus.const import DOMAIN
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    entity_id_of,
    plant_entities,
)

CURVE = "switch.heat_pump_weather_curve"
SUPPLY = "number.heat_pump_supply"
REQUEST = "switch.heat_pump"
FLAT = f"""
hydronicus: 2
name: Flat
source:
  request: {REQUEST}
  name: Heat pump
  min_on: 0
  min_off: 0
  weather_curve: {{switch: {CURVE}}}
  supply:
    entity: {SUPPLY}
    outdoor_sensor: sensor.outdoor
    heat_temperature: 33
    minimum: 20
    maximum: 50
    step: 1
    max_age: 900
pumps:
  pump: {{switch: switch.pump}}
zones:
  flat:
    temperature: [sensor.flat]
    thermostat: {{digital: {{min_on: 0, min_off: 0}}}}
    loops:
      radiator: {{valves: [switch.valve], pump: pump}}
"""
CELSIUS = {"unit_of_measurement": "°C"}


async def _flat(hass: HomeAssistant) -> tuple[Actuators, str, str, str]:
    actuators = Actuators(hass)
    for entity in (REQUEST, "switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set(CURVE, "on")
    hass.states.async_set(SUPPLY, "30", {**CELSIUS, "min": 20, "max": 60, "step": 1})
    hass.states.async_set("sensor.flat", "21", CELSIUS)
    hass.states.async_set("sensor.outdoor", "5", CELSIUS)
    entry = await async_import(hass, FLAT)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    plant_id = entry.runtime_data.plant.id
    mode = entity_id_of(hass, "select", f"{plant_id}_mode")
    await async_call(hass, "select", "select_option", entity_id=mode, option="heat")
    return (
        actuators,
        entity_id_of(hass, "select", f"{plant_id}_heating_supply"),
        entity_id_of(hass, "number", f"{plant_id}_heating_supply_temperature"),
        entity_id_of(hass, "number", f"{plant_id}_heating_curve_offset"),
    )


async def test_the_select_offers_the_strategies_and_starts_from_what_the_source_does(
    hass: HomeAssistant,
) -> None:
    _, select, fixed, offset = await _flat(hass)
    state = hass.states.get(select)
    assert state.state == "source_curve"
    assert state.attributes["options"] == ["source_curve", "fixed", "curve"]
    assert hass.states.get(fixed).state == "unavailable"
    assert hass.states.get(offset).state == "unavailable"


async def test_a_fixed_temperature_chosen_in_home_assistant_survives_a_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    actuators, select, fixed, _ = await _flat(hass)
    await async_call(hass, "select", "select_option", entity_id=select, option="fixed")
    await async_advance(hass, freezer, 5)
    assert hass.states.get(select).state == "fixed"
    assert hass.states.get(CURVE).state == "off"
    assert hass.states.get(fixed).state == "33.0"

    await async_call(hass, "number", "set_value", entity_id=fixed, value=34.6)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(fixed).state == "35.0", "rounded to the setpoint's step"
    assert hass.states.get(SUPPLY).state == "35.0"
    assert any(call.entity_id == SUPPLY for call in actuators.calls)

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(select).state == "fixed"
    assert hass.states.get(fixed).state == "35.0"


async def test_the_curve_turned_off_elsewhere_is_adopted_and_not_turned_on_again(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    actuators, select, fixed, _ = await _flat(hass)
    hass.states.async_set(SUPPLY, "34", {**CELSIUS, "min": 20, "max": 60, "step": 1})
    hass.states.async_set(CURVE, "off")
    await async_advance(hass, freezer, 60)
    assert hass.states.get(select).state == "fixed"
    assert hass.states.get(fixed).state == "34.0"
    assert hass.states.get(CURVE).state == "off"
    assert not [call for call in actuators.calls if call.entity_id in (CURVE, SUPPLY)]

    hass.states.async_set(CURVE, "on")
    await async_advance(hass, freezer, 60)
    assert hass.states.get(select).state == "source_curve"
    assert not [call for call in actuators.calls if call.entity_id == CURVE]


NUMBER = "number.heat_pump_curve_number"


async def _with_curve_number(hass: HomeAssistant) -> tuple[str, str, str]:
    """The flat with its curve number at 6: its entry ID, Warm-up switch, and curve number."""
    Actuators(hass)
    for entity in (REQUEST, "switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set(CURVE, "on")
    hass.states.async_set(NUMBER, "6", {"min": 1, "max": 9, "step": 1})
    hass.states.async_set(SUPPLY, "30", {**CELSIUS, "min": 20, "max": 60, "step": 1})
    hass.states.async_set("sensor.flat", "19", CELSIUS)
    hass.states.async_set("sensor.outdoor", "5", CELSIUS)
    text = FLAT.replace(
        f"weather_curve: {{switch: {CURVE}}}",
        f"weather_curve: {{switch: {CURVE}, curve_number: {{entity: {NUMBER}}}}}",
    )
    entry = await async_import(hass, text)
    await async_set_options(hass, entry, armed=entry.runtime_data.plant.outputs(), control=True)
    plant_id = entry.runtime_data.plant.id
    mode = entity_id_of(hass, "select", f"{plant_id}_mode")
    await async_call(hass, "select", "select_option", entity_id=mode, option="heat")
    return (
        entry.entry_id,
        entity_id_of(hass, "switch", f"{plant_id}_warm_up"),
        entity_id_of(hass, "number", f"{plant_id}_weather_curve_number"),
    )


async def test_the_curve_number_entity_sets_and_adopts_the_number(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    _, _, number = await _with_curve_number(hass)
    assert hass.states.get(number).state == "6.0"

    await async_call(hass, "number", "set_value", entity_id=number, value=4)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(NUMBER).state == "4.0"
    assert hass.states.get(number).state == "4.0"

    # Set on the controller: adopted as Hydronicus's value and never written back.
    hass.states.async_set(NUMBER, "3", {"min": 1, "max": 9, "step": 1})
    await async_advance(hass, freezer, 60)
    assert hass.states.get(number).state == "3.0"
    assert hass.states.get(NUMBER).state == "3"


async def test_the_warm_up_switch_holds_its_temperature_and_the_action_ends_it(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry_id, warm_up, number = await _with_curve_number(hass)
    plant_id = hass.config_entries.async_get_entry(entry_id).runtime_data.plant.id
    select = entity_id_of(hass, "select", f"{plant_id}_heating_supply")
    temperature = entity_id_of(hass, "number", f"{plant_id}_warm_up_temperature")
    assert hass.states.get(warm_up).state == "off"
    assert hass.states.get(warm_up).attributes["temperature"] is None
    assert temperature == "number.heat_pump_warm_up_temperature"
    assert hass.states.get(temperature).state == "40.0"

    await async_call(hass, "switch", "turn_on", entity_id=warm_up)
    await async_advance(hass, freezer, 5)
    await async_advance(hass, freezer, 5)
    state = hass.states.get(warm_up)
    assert state.state == "on"
    assert state.attributes["temperature"] == 40.0
    assert state.attributes["zones"] == [], "no zone calls, so it runs its time"
    assert state.attributes["until"] is not None
    assert hass.states.get(CURVE).state == "off", "the curve is off for the warm-up"
    assert hass.states.get(SUPPLY).state == "40.0"
    assert hass.states.get(select).state == "source_curve"
    assert hass.states.get(number).state == "6.0", "the curve number is not touched"
    assert hass.states.get(NUMBER).state == "6"

    # The owner's Warm-up temperature applies to the running warm-up at once.
    await async_call(hass, "number", "set_value", entity_id=temperature, value=42)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(SUPPLY).state == "42.0"
    assert hass.states.get(warm_up).attributes["temperature"] == 42.0

    await async_call(hass, DOMAIN, "end_warm_up", config_entry_id=entry_id)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(warm_up).state == "off"
    assert hass.states.get(warm_up).attributes["until"] is None
    assert hass.states.get(CURVE).state == "on", "the curve is back on"
    assert hass.states.get(select).state == "source_curve"


async def test_the_warm_up_action_s_temperature_is_for_that_warm_up_only(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry_id, warm_up, _ = await _with_curve_number(hass)
    plant_id = hass.config_entries.async_get_entry(entry_id).runtime_data.plant.id
    temperature = entity_id_of(hass, "number", f"{plant_id}_warm_up_temperature")

    await async_call(
        hass,
        DOMAIN,
        "warm_up",
        config_entry_id=entry_id,
        duration={"minutes": 30},
        temperature=45,
    )
    await async_advance(hass, freezer, 5)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(warm_up).attributes["temperature"] == 45.0
    assert hass.states.get(SUPPLY).state == "45.0"
    assert hass.states.get(temperature).state == "40.0", "the setting stays"

    await async_advance(hass, freezer, 1800, step=60)
    assert hass.states.get(warm_up).state == "off"
    assert hass.states.get(CURVE).state == "on"

    await async_call(hass, "switch", "turn_on", entity_id=warm_up)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(warm_up).attributes["temperature"] == 40.0


async def test_the_warm_up_temperature_survives_a_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry_id, _, _ = await _with_curve_number(hass)
    plant_id = hass.config_entries.async_get_entry(entry_id).runtime_data.plant.id
    temperature = entity_id_of(hass, "number", f"{plant_id}_warm_up_temperature")
    state = hass.states.get(temperature)
    assert (state.attributes["min"], state.attributes["max"], state.attributes["step"]) == (
        20,
        50,
        1,
    )
    await async_call(hass, "number", "set_value", entity_id=temperature, value=43.4)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(temperature).state == "43.0", "rounded to the setpoint's step"

    assert await hass.config_entries.async_reload(entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(temperature).state == "43.0"


async def test_a_warm_up_without_a_supply_setpoint_is_refused(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    Actuators(hass)
    for entity in (REQUEST, "switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set(CURVE, "on")
    hass.states.async_set("sensor.flat", "19", CELSIUS)
    supply = FLAT[FLAT.index("  supply:") : FLAT.index("pumps:")]
    entry = await async_import(hass, FLAT.replace(supply, ""))
    plant_id = entry.runtime_data.plant.id
    warm_up = entity_id_of(hass, "switch", f"{plant_id}_warm_up")
    assert f"{plant_id}_warm_up_temperature" not in plant_entities(hass, entry)
    await async_advance(hass, freezer, 5)

    with pytest.raises(ServiceValidationError) as error:
        await async_call(hass, DOMAIN, "warm_up", config_entry_id=entry.entry_id)
    assert error.value.translation_key == "warm_up_no_supply"
    with pytest.raises(ServiceValidationError):
        await async_call(hass, "switch", "turn_on", entity_id=warm_up)
    await async_advance(hass, freezer, 5)
    assert hass.states.get(warm_up).state == "off"


async def test_the_warm_up_actions_need_a_heating_supply(hass: HomeAssistant) -> None:
    for entity in ("switch.boiler", "switch.pump", "switch.valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set("sensor.flat", "21", CELSIUS)
    entry = await async_import(
        hass,
        """
hydronicus: 2
name: Plain
source: {request: switch.boiler}
pumps:
  pump: {switch: switch.pump}
zones:
  flat:
    temperature: [sensor.flat]
    loops:
      radiator: {valves: [switch.valve], pump: pump}
""",
    )
    for action in ("warm_up", "end_warm_up"):
        with pytest.raises(ServiceValidationError) as error:
            await async_call(hass, DOMAIN, action, config_entry_id=entry.entry_id)
        assert error.value.translation_key == "no_heating_supply"
