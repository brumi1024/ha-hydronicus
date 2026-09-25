"""The reference plant of the redesign plan, set up from its plant file and run end to end."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.hydronicus.const import SUBENTRY_TYPE_ZONE
from tests.integration.helpers import (
    BASEMENT_CEILING,
    BEDROOM_CEILING,
    FLOOR_PUMP,
    LIVING_CEILING,
    LIVING_FLOOR,
    REFERENCE_OUTPUTS,
    REFERENCE_PLANT,
    REFERENCE_PLANT_ID,
    SOURCE_REQUEST,
    TOWEL_PUMP,
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    plant_entities,
    reference_world,
    set_zone_temperature,
)

# The entity contract of the reference plant (contract K7): 24 entities.
REFERENCE_ENTITIES = {
    "select.home_mode",
    "switch.home_control_equipment",
    "sensor.home_status",
    "binary_sensor.home_towel_dryer_flowing",
    "binary_sensor.heat_pump_requested",
    *(
        entity
        for zone in ("basement", "bedroom_area", "living_area")
        for entity in (
            f"climate.{zone}",
            f"binary_sensor.{zone}_heating_demand",
            f"binary_sensor.{zone}_cooling_demand",
            f"sensor.{zone}_combined_temperature",
            f"sensor.{zone}_dew_point",
            f"binary_sensor.{zone}_ceiling_flowing",
        )
    ),
    "binary_sensor.living_area_floor_flowing",
}


async def test_the_reference_plant_publishes_about_25_entities(hass: HomeAssistant) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == REFERENCE_PLANT_ID
    assert entry.options == {"armed_outputs": [], "control": False}
    assert "zones" not in entry.data
    assert {
        subentry.unique_id: subentry.title
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_ZONE
    } == {"basement": "Basement", "bedroom_area": "Bedroom area", "living_area": "Living area"}
    entities = plant_entities(hass, entry)
    assert set(entities.values()) == REFERENCE_ENTITIES
    assert len(entities) == 24
    assert all(unique_id.startswith(REFERENCE_PLANT_ID) for unique_id in entities)
    # Zone entities belong to their zone's subentry, the rest to the Plant.
    registry = er.async_get(hass)
    subentry_of = {s.unique_id: s.subentry_id for s in entry.subentries.values()}
    assert registry.async_get("climate.basement").config_subentry_id == subentry_of["basement"]
    assert registry.async_get("select.home_mode").config_subentry_id is None
    device = dr.async_get(hass).async_get(registry.async_get("climate.living_area").device_id)
    assert device.name == "Living area"
    # A zone over several areas puts nothing in an area.
    assert registry.async_get("climate.living_area").area_id is None
    status = hass.states.get("sensor.home_status")
    assert status.state == "off"
    assert status.attributes["unarmed_outputs"] == sorted(REFERENCE_OUTPUTS)


async def test_the_reference_plant_heats_a_zone_end_to_end(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    """Valves open, then the floor pump runs, then the heat pump is asked; then all stops."""
    reference_world(hass, temperature=21.0)
    entry = await async_import(hass, REFERENCE_PLANT)
    await async_set_options(hass, entry, armed=REFERENCE_OUTPUTS, control=True)
    await async_call(hass, "select", "select_option", entity_id="select.home_mode", option="heat")
    await async_call(
        hass, "climate", "set_temperature", entity_id="climate.living_area", temperature=22.0
    )
    assert actuators.calls == []

    await async_call(
        hass, "climate", "set_hvac_mode", entity_id="climate.living_area", hvac_mode="heat"
    )
    set_zone_temperature(hass, "living_area", 20.0)
    await hass.async_block_till_done()
    assert sorted(actuators.shorts()) == [f"{LIVING_CEILING}:on", f"{LIVING_FLOOR}:on"]
    demand = hass.states.get("binary_sensor.living_area_heating_demand")
    assert demand.state == "on" and demand.attributes["level"] == 1.0
    assert hass.states.get("climate.living_area").attributes["hvac_action"] == "heating"
    actuators.clear()

    await async_advance(hass, freezer, 179, step=5)
    assert actuators.calls == [], "nothing runs before the valves have had their opening time"
    await async_advance(hass, freezer, 2)
    assert actuators.shorts()[:2] == [f"{FLOOR_PUMP}:on", f"{SOURCE_REQUEST}:on"]
    assert actuators.shorts()[2:] == [f"{TOWEL_PUMP}:on"], "the towel dryer runs with the source"
    assert hass.states.get("binary_sensor.heat_pump_requested").state == "on"
    assert hass.states.get("binary_sensor.living_area_floor_flowing").state == "on"
    assert hass.states.get("sensor.home_status").state == "heating"
    assert not actuators.to(BASEMENT_CEILING) and not actuators.to(BEDROOM_CEILING)
    requested_at = actuators.to(SOURCE_REQUEST)[0].at
    actuators.clear()
    actuators.clear()

    satisfied_at = requested_at + 60
    await async_advance(hass, freezer, 60, step=5)
    set_zone_temperature(hass, "living_area", 22.5)
    await hass.async_block_till_done()
    await async_advance(hass, freezer, 1200, step=5)
    order = actuators.shorts()
    assert order == [
        f"{FLOOR_PUMP}:off",
        f"{LIVING_FLOOR}:off",
        f"{SOURCE_REQUEST}:off",
        f"{TOWEL_PUMP}:off",
        f"{LIVING_CEILING}:off",
    ]
    at = {call.short: call.at for call in actuators.calls}
    assert at[f"{FLOOR_PUMP}:off"] >= satisfied_at + 180, "the floor pump overruns"
    assert at[f"{SOURCE_REQUEST}:off"] >= requested_at + 600, "the source keeps its minimum on"
    assert at[f"{TOWEL_PUMP}:off"] < at[f"{SOURCE_REQUEST}:off"] + 120 + 10
    assert at[f"{LIVING_CEILING}:off"] >= at[f"{SOURCE_REQUEST}:off"] + 180, (
        "the heat pump's path stays open through the post-run"
    )
    for entity_id in REFERENCE_OUTPUTS:
        if entity_id != "select.heat_pump_mode":
            assert hass.states.get(entity_id).state == "off", entity_id
    assert hass.states.get("sensor.home_status").state == "idle"
