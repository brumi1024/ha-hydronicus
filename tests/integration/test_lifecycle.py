"""Setup, reload, restart, zone removal, and export never send a command on their own.

A running reference plant with 180 second actuators is reloaded and restarted
with nothing changed, and its first evaluations must send nothing and must not
cycle a pump (invariant 8, defect 7).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.json import json_bytes
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus import runtime as runtime_module
from custom_components.hydronicus.const import DOMAIN, OPTION_ARMED_OUTPUTS
from custom_components.hydronicus.core.model import Mode
from custom_components.hydronicus.core.plant_file import read_plant_file, write_plant_file
from custom_components.hydronicus.core.step import DigitalThermostatState, State
from custom_components.hydronicus.storage import new_entry, stored_document
from tests.integration.helpers import (
    BASEMENT_CEILING,
    FLOOR_PUMP,
    LIVING_FLOOR,
    REFERENCE_OUTPUTS,
    REFERENCE_PLANT,
    RUNNING,
    SUPPLY,
    Actuators,
    async_advance,
    async_call,
    async_heat_living_area,
    async_import,
    async_set_options,
    plant_entities,
    reference_world,
    restart_states,
    set_zone_temperature,
)


async def test_a_reload_with_slow_actuators_sends_no_command_and_keeps_pumps_running(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_heat_living_area(hass, freezer)
    actuators.clear()

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    await async_advance(hass, freezer, 600, step=5)

    assert actuators.calls == []
    assert hass.states.get(FLOOR_PUMP).state == "on"


async def test_a_reload_while_valves_open_starts_the_pump_once_at_their_opening_time(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    """Defect 7: a reload 90 seconds into opening must not restart the valves' 180 seconds."""
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    await async_set_options(hass, entry, armed=REFERENCE_OUTPUTS, control=True)
    await async_call(hass, "select", "select_option", entity_id="select.home_mode", option="heat")
    await async_call(
        hass, "climate", "set_hvac_mode", entity_id="climate.living_area", hvac_mode="heat"
    )
    set_zone_temperature(hass, "living_area", 19.0)
    await hass.async_block_till_done()
    opened_at = actuators.to(LIVING_FLOOR)[0].at
    await async_advance(hass, freezer, 90, step=5)
    actuators.clear()

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert actuators.calls == []
    await async_advance(hass, freezer, 300, step=5)

    pump = actuators.to(FLOOR_PUMP)
    assert [call.short for call in pump] == [f"{FLOOR_PUMP}:on"]
    assert opened_at + 180 <= pump[0].at <= opened_at + 185


async def test_a_home_assistant_restart_with_slow_actuators_sends_no_command(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    """A restart resets every last_changed; the persisted output memory keeps the valves ready."""
    entry = await async_heat_living_area(hass, freezer)
    actuators.clear()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await async_advance(hass, freezer, 30)
    sensors = {f"sensor.{area}_temperature" for area in ("living_room", "kitchen")} | {SUPPLY}
    restart_states(hass, set(REFERENCE_OUTPUTS) | sensors)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert actuators.calls == []
    await async_advance(hass, freezer, 600, step=5)

    assert actuators.calls == []
    assert {e for e in REFERENCE_OUTPUTS if hass.states.get(e).state == "on"} == RUNNING


async def test_the_first_evaluation_sees_restored_thermostats_and_persisted_state(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    actuators: Actuators,
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = await async_heat_living_area(hass, freezer)
    actuators.clear()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    stored = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]
    assert set(stored) == {"state", "reconcile", "outputs", "mode", "commanding"}
    assert stored["commanding"]["plant"]["id"] == entry.unique_id
    assert sorted(stored["commanding"]["outputs"]) == sorted(REFERENCE_OUTPUTS)
    assert stored["mode"] == "heat" and stored["state"]["live"] is True
    assert stored["outputs"][LIVING_FLOOR]["value"] is True

    seen: list[tuple[Any, State]] = []
    real_step = runtime_module.step

    def spy(plant: Any, observations: Any, state: State, now: float) -> Any:
        seen.append((observations, state))
        return real_step(plant, observations, state, now)

    monkeypatch.setattr(runtime_module, "step", spy)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    observations, state = seen[0]
    assert state == State.from_dict(stored["state"])
    assert observations.mode is Mode.HEAT
    assert observations.thermostats["living_area"] == DigitalThermostatState(Mode.HEAT, 22.0)
    assert observations.thermostats["basement"] == DigitalThermostatState(Mode.OFF, 21.0)
    assert actuators.calls == []


async def test_an_entry_of_an_earlier_version_is_refused(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, version=4, minor_version=0, title="Old", data={"topology": {}}
    )
    entry.add_to_hass(hass)
    with caplog.at_level(logging.ERROR):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR
    assert "cannot be migrated" in caplog.text and "set the Plant up again" in caplog.text


# Zone removal

SHARED = REFERENCE_PLANT.replace(
    "min_flow_loops: [living_area.ceiling]",
    "min_flow_loops: [basement.ceiling, living_area.ceiling]",
).replace(
    "loops:\n  towel_dryer:",
    "loops:\n  hall:\n    valves: [switch.hall_radiator_valve]\n    pump: floor\n"
    "    runs: {with_zones: [basement, living_area]}\n  towel_dryer:",
)


def zone_subentry(entry: ConfigEntry, slug: str) -> str:
    return next(s.subentry_id for s in entry.subentries.values() if s.unique_id == slug)


async def test_removing_a_zone_prunes_references_to_it_and_keeps_the_plant_running(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set("switch.hall_radiator_valve", "off")
    entry = await async_heat_living_area(hass, freezer, SHARED)
    assert "switch.hall_radiator_valve" in entry.options[OPTION_ARMED_OUTPUTS]
    actuators.clear()

    hass.config_entries.async_remove_subentry(entry, zone_subentry(entry, "basement"))
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert stored_document(entry)["pumps"]["heat_pump"]["min_flow_loops"] == ["living_area.ceiling"]
    assert stored_document(entry)["loops"]["hall"]["runs"] == {"with_zones": ["living_area"]}
    assert BASEMENT_CEILING not in entry.options[OPTION_ARMED_OUTPUTS]
    assert entry.runtime_data.plant.zones[0].slug == "bedroom_area"
    assert not any(e.startswith("climate.basement") for e in plant_entities(hass, entry).values())
    await async_advance(hass, freezer, 300, step=5)
    assert actuators.calls == []


# Export


async def test_exporting_and_importing_a_plant_reproduces_its_entity_ids(
    hass: HomeAssistant,
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    before = plant_entities(hass, entry)
    response = await hass.services.async_call(
        DOMAIN,
        "export_plant",
        {"config_entry_id": entry.entry_id},
        blocking=True,
        return_response=True,
    )
    assert response is not None
    assert response["document"]["id"] == entry.unique_id
    assert read_plant_file(str(response["yaml"])) == entry.runtime_data.plant

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    again = await async_import(hass, str(response["yaml"]))

    assert plant_entities(hass, again) == before


async def test_a_plant_keeps_the_order_of_its_pumps_and_loops_across_a_restart(
    hass: HomeAssistant,
) -> None:
    """Home Assistant stores config entries with sorted keys, which must not reorder the Plant.

    The entry is written as Home Assistant's config entry store writes it, then
    set up again from what was written, as a restart would.
    """
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    exported = write_plant_file(entry.runtime_data.plant)
    assert [pump.slug for pump in entry.runtime_data.plant.pumps] == [
        "heat_pump",
        "floor",
        "towel_dryer",
    ]
    stored_entry = json.loads(json_bytes(entry.as_storage_fragment))
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    restarted = MockConfigEntry(
        domain=DOMAIN,
        entry_id=stored_entry["entry_id"],
        title=stored_entry["title"],
        data=stored_entry["data"],
        options=stored_entry["options"],
        subentries_data=stored_entry["subentries"],
        unique_id=stored_entry["unique_id"],
        version=stored_entry["version"],
        minor_version=stored_entry["minor_version"],
    )
    restarted.add_to_hass(hass)
    assert await hass.config_entries.async_setup(restarted.entry_id)
    await hass.async_block_till_done()

    assert write_plant_file(restarted.runtime_data.plant) == exported
    flow = hass.config_entries.flow
    result = await flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": restarted.entry_id}
    )
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "pump_pick"})
    picker = next(v for k, v in result["data_schema"].schema.items() if str(k) == "pump")
    options = picker.serialize()["selector"]["select"]["options"]
    assert [option["value"] for option in options][:3] == ["heat_pump", "floor", "towel_dryer"]


async def test_a_stored_plant_matches_the_plant_file_split(hass: HomeAssistant) -> None:
    """The entry data and zone subentries are the plant file split by ``to_storage``."""
    plant = read_plant_file(REFERENCE_PLANT)
    data, subentries = new_entry(plant)
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)

    assert dict(entry.data) == data
    assert sorted(
        (s.unique_id, s.title, dict(s.data)) for s in entry.subentries.values()
    ) == sorted((s["unique_id"], s["title"], s["data"]) for s in subentries)
