"""Outputs that leave a running Plant are stopped in order before the new Plant runs.

Deleting a zone, a reconfigure, or a replace from a plant file can remove outputs
that are on. The runtime persists the last valid Plant with the outputs it was
commanding, and at setup runs the off sequence of that Plant until its outputs
are observed off, then switches to the new configuration.
"""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.diagnostics import async_get_config_entry_diagnostics
from tests.integration.helpers import (
    BASEMENT_CEILING,
    FLOOR_PUMP,
    LIVING_CEILING,
    LIVING_FLOOR,
    REFERENCE_OUTPUTS,
    REFERENCE_PLANT,
    SOURCE_MODE,
    SOURCE_REQUEST,
    SUPPLY,
    TOWEL_PUMP,
    Actuators,
    async_advance,
    async_call,
    async_choose,
    async_heat_living_area,
    async_import,
    async_set_options,
    async_submit,
    reference_world,
    restart_states,
    set_zone_temperature,
    zone_subentry_id,
)

# The reference plant with a second min-flow loop, so the living area can go.
TWO_MIN_FLOW_LOOPS = REFERENCE_PLANT.replace(
    "min_flow_loops: [living_area.ceiling]",
    "min_flow_loops: [basement.ceiling, living_area.ceiling]",
)
POST_RUN = 180
OVERRUN = 180


def status(hass: HomeAssistant) -> Any:
    state = hass.states.get("sensor.home_status")
    assert state is not None
    return state


def off_times(actuators: Actuators) -> dict[str, float]:
    """When each output was first asked to turn off."""
    times: dict[str, float] = {}
    for call in actuators.calls:
        if call.short.endswith(":off"):
            times.setdefault(call.entity_id, call.at)
    return times


def assert_stopped_in_order(actuators: Actuators, *, floor: bool = True) -> dict[str, float]:
    """The source first, then the pumps after their overrun, then each valve after its pump."""
    at = off_times(actuators)
    assert actuators.calls[0].short == f"{SOURCE_REQUEST}:off", actuators.shorts()
    if floor:
        assert at[FLOOR_PUMP] >= at[SOURCE_REQUEST] + OVERRUN, "the floor pump overruns"
        assert at[LIVING_FLOOR] >= at[FLOOR_PUMP], "the floor valve closes after its pump"
    assert at[LIVING_CEILING] >= at[SOURCE_REQUEST] + POST_RUN, (
        "the heat pump's path stays open through the post-run"
    )
    assert TOWEL_PUMP in at
    return at


def assert_all_off(hass: HomeAssistant, entities: set[str] | None = None) -> None:
    for entity_id in entities or set(REFERENCE_OUTPUTS) - {SOURCE_MODE}:
        assert hass.states.get(entity_id).state == "off", entity_id


async def async_remove_zone(hass: HomeAssistant, entry: ConfigEntry, slug: str) -> None:
    hass.config_entries.async_remove_subentry(entry, zone_subentry_id(entry, slug))
    await hass.async_block_till_done()


async def test_deleting_a_heating_zone_stops_its_valves_after_their_pumps(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_heat_living_area(hass, freezer, TWO_MIN_FLOW_LOOPS)
    actuators.clear()

    await async_remove_zone(hass, entry, "living_area")

    assert entry.state is ConfigEntryState.LOADED
    assert [zone.slug for zone in entry.runtime_data.plant.zones] == ["basement", "bedroom_area"]
    stopping = status(hass)
    assert stopping.state == "stopping"
    assert {LIVING_CEILING, LIVING_FLOOR} <= set(stopping.attributes["stopping_outputs"])
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["stopping"] is not None
    assert LIVING_FLOOR in diagnostics["stopping"]["outputs"]

    await async_advance(hass, freezer, 600, step=5)

    assert_stopped_in_order(actuators)
    assert_all_off(hass)
    assert status(hass).state == "idle", "the new Plant runs once the old one has stopped"
    assert status(hass).attributes["stopping_outputs"] == []
    assert (await async_get_config_entry_diagnostics(hass, entry))["stopping"] is None
    actuators.clear()
    await async_advance(hass, freezer, 600, step=10)
    assert actuators.calls == []


async def test_replacing_the_plant_without_the_floor_pump_stops_it_then_heats_again(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_heat_living_area(hass, freezer)
    actuators.clear()
    replacement = REFERENCE_PLANT.replace(
        "  floor:\n    switch: switch.home_underfloor_heating_pump\n    overrun: 180\n", ""
    ).replace(
        "      floor:\n        valves: [switch.home_living_area_floor_heating_valve]\n"
        "        pump: floor\n        modes: [heat]\n",
        "",
    )
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    result = await async_choose(flow, result, "replace")
    result = await async_submit(flow, result, {"plant_file": replacement})
    assert result["step_id"] == "save"
    result = await async_submit(flow, result)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert status(hass).state == "stopping"

    await async_advance(hass, freezer, 400, step=5)

    at = assert_stopped_in_order(actuators)
    assert hass.states.get(FLOOR_PUMP).state == "off"
    assert hass.states.get(LIVING_FLOOR).state == "off"
    assert status(hass).state == "heating", "the living area calls, so the new Plant heats"
    await async_advance(hass, freezer, 900, step=10)
    restarted = [call for call in actuators.to(SOURCE_REQUEST) if call.short.endswith(":on")]
    assert restarted and restarted[0].at >= at[SOURCE_REQUEST] + 600, "after its minimum off"
    assert [call.short for call in actuators.to(FLOOR_PUMP)] == [f"{FLOOR_PUMP}:off"]
    assert [call.short for call in actuators.to(LIVING_FLOOR)] == [f"{LIVING_FLOOR}:off"]


async def test_a_removed_output_that_was_never_armed_gets_no_call(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    reference_world(hass)
    entry = await async_import(hass, TWO_MIN_FLOW_LOOPS)
    armed = [entity for entity in REFERENCE_OUTPUTS if entity != LIVING_FLOOR]
    await async_set_options(hass, entry, armed=armed, control=True)
    await async_call(hass, "select", "select_option", entity_id="select.home_mode", option="heat")
    await async_call(
        hass, "climate", "set_temperature", entity_id="climate.living_area", temperature=22.0
    )
    await async_call(
        hass, "climate", "set_hvac_mode", entity_id="climate.living_area", hvac_mode="heat"
    )
    set_zone_temperature(hass, "living_area", 20.0)
    await hass.async_block_till_done()
    await async_advance(hass, freezer, 200, step=5)
    assert hass.states.get(SOURCE_REQUEST).state == "on"
    # Someone opened the unarmed floor valve by hand.
    hass.states.async_set(LIVING_FLOOR, "on")
    await hass.async_block_till_done()
    actuators.clear()

    await async_remove_zone(hass, entry, "living_area")
    await async_advance(hass, freezer, 600, step=5)

    assert actuators.to(LIVING_FLOOR) == []
    assert hass.states.get(LIVING_FLOOR).state == "on"
    assert_stopped_in_order(actuators, floor=False)
    assert status(hass).state == "idle"


async def test_a_restart_in_the_middle_of_stopping_resumes_the_sequence(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_heat_living_area(hass, freezer, TWO_MIN_FLOW_LOOPS)
    actuators.clear()
    await async_remove_zone(hass, entry, "living_area")
    await async_advance(hass, freezer, 60, step=5)
    assert actuators.shorts() == [f"{SOURCE_REQUEST}:off"]
    assert hass.states.get(FLOOR_PUMP).state == "on", "the floor pump overruns"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await async_advance(hass, freezer, 10)
    sensors = {f"sensor.{area}_temperature" for area in ("living_room", "kitchen")} | {SUPPLY}
    restart_states(hass, set(REFERENCE_OUTPUTS) | sensors)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert status(hass).state == "stopping"
    await async_advance(hass, freezer, 600, step=5)

    at = assert_stopped_in_order(actuators)
    assert at[FLOOR_PUMP] <= at[SOURCE_REQUEST] + OVERRUN + 10, "the overrun is not restarted"
    assert len(actuators.to(SOURCE_REQUEST)) == 1
    assert actuators.to(BASEMENT_CEILING) == []
    assert_all_off(hass)
    assert status(hass).state == "idle"
