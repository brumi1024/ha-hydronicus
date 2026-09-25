"""The documented trial kit: a synthetic package and a plant file bound to it.

These tests load ``docs/examples/trial/package.yaml`` through the real Home
Assistant helper and template integrations, import ``plant.yaml`` through the
config flow exactly as the README describes, and drive heating demand. Every
actuator is a template switch backed by an ``input_boolean``, so any command
Hydronicus sent would show up as a service call and a changed helper state.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.setup import async_setup_component

from custom_components.hydronicus.const import DOMAIN

TRIAL_KIT = Path(__file__).parents[2] / "docs" / "examples" / "trial"
PACKAGE_DOMAINS = ("input_number", "input_boolean", "template")
# Every service domain that could move a valve, a pump, or their backing helpers.
ACTUATOR_DOMAINS = frozenset({"switch", "valve", "input_boolean", "homeassistant"})
TRIAL_HELPERS = (
    "input_boolean.hydronicus_trial_living_room_valve",
    "input_boolean.hydronicus_trial_bedroom_valve",
    "input_boolean.hydronicus_trial_pump",
)


def trial_file(name: str) -> dict[str, Any]:
    """Return one parsed file of the trial kit."""
    return yaml.safe_load((TRIAL_KIT / name).read_text(encoding="utf-8"))


async def async_setup_trial_package(hass: HomeAssistant) -> None:
    """Set up the trial package with the integrations it configures."""
    package = trial_file("package.yaml")
    assert set(package) == set(PACKAGE_DOMAINS)
    for domain in PACKAGE_DOMAINS:
        assert await async_setup_component(hass, domain, {domain: package[domain]})
    await hass.async_block_till_done()


def record_actuator_calls(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Record every service call that could reach an actuator or its helper."""
    calls: list[dict[str, Any]] = []

    @callback
    def record(event: Event) -> None:
        if event.data.get("domain") in ACTUATOR_DOMAINS:
            calls.append(dict(event.data))

    hass.bus.async_listen(EVENT_CALL_SERVICE, record)
    return calls


def assert_helpers_untouched(hass: HomeAssistant) -> None:
    """Assert that no trial valve or pump helper was switched."""
    for entity_id in TRIAL_HELPERS:
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state == "off", entity_id


def state_of(hass: HomeAssistant) -> Callable[[str], str]:
    def read(entity_id: str) -> str:
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        return state.state

    return read


async def test_trial_package_provides_the_documented_entities(hass) -> None:
    """The package creates the sensors and switches the plant file binds."""
    await async_setup_trial_package(hass)
    state = state_of(hass)

    for zone in ("living_room", "bedroom"):
        temperature = hass.states.get(f"sensor.hydronicus_trial_{zone}_temperature")
        assert temperature is not None
        assert temperature.state == "21.0"
        assert temperature.attributes["device_class"] == "temperature"
        assert temperature.attributes["unit_of_measurement"] == "°C"
        assert state(f"switch.hydronicus_trial_{zone}_valve") == "off"
    assert state("switch.hydronicus_trial_pump") == "off"

    bound = {
        "sensor.hydronicus_trial_living_room_temperature",
        "sensor.hydronicus_trial_bedroom_temperature",
        "switch.hydronicus_trial_living_room_valve",
        "switch.hydronicus_trial_bedroom_valve",
        "switch.hydronicus_trial_pump",
    }
    assert bound <= set(hass.states.async_entity_ids())


async def test_trial_plant_file_imports_and_heats_in_dry_run(hass) -> None:
    """Importing plant.yaml and heating Bedroom requests only Bedroom's path, in Dry run."""
    await async_setup_trial_package(hass)
    calls = record_actuator_calls(hass)
    state = state_of(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "import_plant"}
    )
    assert result["step_id"] == "import_plant"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"document": trial_file("plant.yaml")}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "import_review"
    placeholders = result["description_placeholders"]
    assert placeholders["name"] == "Trial plant"
    assert "- Bedroom is heated by Bedroom loop." in placeholders["logic"]
    assert (
        "- Bedroom loop opens Bedroom loop valve, then starts Circulation pump."
        in placeholders["logic"]
    )
    # The shared pump is listed under Warnings only, not repeated under How it connects.
    assert "is shared by" not in placeholders["logic"]
    # The README tells the user to expect this one warning and to confirm it.
    # The loops are listed in file order, so the text is the same on every import.
    assert placeholders["warnings"] == (
        "- Pump Circulation pump is shared by loops Living room loop, Bedroom loop; separate "
        "zone thermostats cannot independently control heating and cooling through the same pump."
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})
    assert result["errors"] == {"base": "confirm_required"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"confirm": True}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    entry = hass.config_entries.async_get_entry(result["result"].entry_id)
    assert entry is not None
    assert entry.data["dry_run"] is True
    assert sorted(subentry.title for subentry in entry.subentries.values()) == [
        "Bedroom",
        "Living room",
    ]
    assert state("sensor.trial_plant_topology_preview") == "2 zones, 2 loops"

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.bedroom", "hvac_mode": "heat"},
        blocking=True,
    )
    await hass.services.async_call(
        "input_number",
        "set_value",
        {"entity_id": "input_number.hydronicus_trial_bedroom_temperature", "value": 18},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert state("binary_sensor.bedroom_heating_demand") == "on"
    assert state("binary_sensor.living_room_heating_demand") == "off"
    assert state("binary_sensor.bedroom_loop_valve_requested") == "on"
    assert state("binary_sensor.living_room_loop_valve_requested") == "off"
    # The pump waits for the valve's 30 second default opening time.
    assert state("binary_sensor.circulation_pump_requested") == "off"

    assert entry.runtime_data.dry_run is True
    assert calls == []
    assert_helpers_untouched(hass)
    for entity_id in (
        "switch.hydronicus_trial_living_room_valve",
        "switch.hydronicus_trial_bedroom_valve",
        "switch.hydronicus_trial_pump",
    ):
        assert state(entity_id) == "off"


async def test_trial_areas_plant_file_follows_the_areas_with_the_same_entity_ids(hass) -> None:
    """plant-areas.yaml builds the same Plant from the README's two areas."""
    await async_setup_trial_package(hass)
    areas = ar.async_get(hass)
    for name, zone in (("Living room", "living_room"), ("Bedroom", "bedroom")):
        areas.async_create(
            name, temperature_entity_id=f"sensor.hydronicus_trial_{zone}_temperature"
        )
    calls = record_actuator_calls(hass)
    state = state_of(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "import_plant"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"document": trial_file("plant-areas.yaml")}
    )
    assert result["step_id"] == "import_review"
    # The same one warning as plant.yaml: the areas exist and name their sensors.
    assert result["description_placeholders"]["warnings"] == (
        "- Pump Circulation pump is shared by loops Living room loop, Bedroom loop; separate "
        "zone thermostats cannot independently control heating and cooling through the same pump."
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"confirm": True}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    combined = hass.states.get("sensor.bedroom_combined_temperature")
    assert combined is not None
    assert combined.attributes["usable_sensor_ids"] == [
        "sensor.hydronicus_trial_bedroom_temperature"
    ]
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.bedroom", "hvac_mode": "heat"},
        blocking=True,
    )
    await hass.services.async_call(
        "input_number",
        "set_value",
        {"entity_id": "input_number.hydronicus_trial_bedroom_temperature", "value": 18},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert state("binary_sensor.bedroom_heating_demand") == "on"
    assert state("binary_sensor.living_room_heating_demand") == "off"
    assert calls == []
    assert_helpers_untouched(hass)
