"""End-to-end public-beta setup and shadow simulation checks."""

from __future__ import annotations

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import (
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
)
from tests.integration.test_trial_kit import (
    assert_helpers_untouched,
    async_setup_trial_package,
    record_actuator_calls,
)


async def test_public_documentation_path_creates_and_exercises_shadow_plant(hass) -> None:
    """The README trial path works with the trial kit's disposable entities only.

    It follows "First simulated Plant": load the trial package, build the same
    two zones as ``plant.yaml`` with guided setup, confirm the shared pump
    warning, and exercise heating demand in Dry run.
    """
    await async_setup_trial_package(hass)
    calls = record_actuator_calls(hass)
    living_temperature = "input_number.hydronicus_trial_living_room_temperature"

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "guided"}
    )
    assert result["step_id"] == "guided"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Trial plant", "pump_entity": "switch.hydronicus_trial_pump"},
    )
    assert result["step_id"] == "zoning"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "zoning_grouped"}
    )
    assert result["step_id"] == "zone"
    assert "target_temperature" not in {str(key.schema) for key in result["data_schema"].schema}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Living room",
            "temperature_sensors": ["sensor.hydronicus_trial_living_room_temperature"],
            "valves": ["switch.hydronicus_trial_living_room_valve"],
            "add_another": True,
        },
    )
    assert result["step_id"] == "zone"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Bedroom",
            "temperature_sensors": ["sensor.hydronicus_trial_bedroom_temperature"],
            "valves": ["switch.hydronicus_trial_bedroom_valve"],
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "review"
    assert result["description_placeholders"]["zones"] == "- Living room\n- Bedroom"
    assert result["description_placeholders"]["warnings"].startswith(
        "- Pump Circulation pump is shared by loops Living room loop, Bedroom loop; "
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"confirm": True}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = next(
        entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.title == "Trial plant"
    )
    assert entry.data["dry_run"] is True
    await hass.async_block_till_done()
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.living_room", "hvac_mode": "heat"},
        blocking=True,
    )
    await hass.services.async_call(
        "input_number",
        "set_value",
        {"entity_id": living_temperature, "value": 18},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert entry.runtime_data.dry_run is True
    demand_state = hass.states.get("binary_sensor.living_room_heating_demand")
    topology_state = hass.states.get("sensor.trial_plant_topology_preview")
    valve_request = hass.states.get("binary_sensor.living_room_loop_valve_requested")
    assert demand_state is not None and demand_state.state == "on"
    assert topology_state is not None and topology_state.state == "2 zones, 2 loops"
    assert valve_request is not None and valve_request.state == "on"

    await hass.services.async_call(
        "input_number",
        "set_value",
        {"entity_id": living_temperature, "value": 22},
        blocking=True,
    )
    await hass.async_block_till_done()
    demand_state = hass.states.get("binary_sensor.living_room_heating_demand")
    assert demand_state is not None and demand_state.state == "off"
    assert calls == []
    assert_helpers_untouched(hass)


async def test_public_beta_fresh_entry_can_reload_without_changing_domain(hass) -> None:
    """A fresh package entry remains a Hydronicus entry across a reload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        title="Fresh package plant",
        data={
            "name": "Fresh package plant",
            "plant_id": "00000000-0000-4000-8000-000000000001",
            "dry_run": True,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.domain == DOMAIN
    assert await hass.config_entries.async_reload(entry.entry_id)
    assert entry.domain == DOMAIN
