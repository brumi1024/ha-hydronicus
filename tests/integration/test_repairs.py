"""Repairs with fix flows: each leads to the step that fixes it (contract K8).

Outputs awaiting confirmation arm the new outputs in the fix flow itself. An
invalid Plant opens the entry's reconfigure flow, and a zone's area and binding
problems open that zone's reconfigure flow, through the fix flow's
``next_flow``. Output faults, missing area sensors, and self-feeding areas are
fixed outside Hydronicus, so they stay informational.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.core.model import MinFlow
from custom_components.hydronicus.issues import IssueKind
from tests.integration.helpers import (
    FLOOR_PUMP,
    LIVING_CEILING,
    REFERENCE_PLANT,
    TOWEL_PUMP,
    async_choose,
    async_import,
    async_set_options,
    async_submit,
    create_area,
    reference_world,
    set_temperature,
    suggested,
    zone_subentry_id,
)

FLAT = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump}
zones:
  study:
    areas: [study]
    loops:
      radiator: {valves: [switch.study_valve], pump: pump}
"""


@pytest.fixture(autouse=True)
async def repairs(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "repairs", {})


def issue_of(hass: HomeAssistant, kind: IssueKind) -> ir.IssueEntry:
    (issue,) = [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == kind
    ]
    return issue


async def async_fix(hass: HomeAssistant, kind: IssueKind) -> dict[str, Any]:
    issue = issue_of(hass, kind)
    assert issue.is_fixable
    manager = repairs_flow_manager(hass)
    assert manager is not None
    return await manager.async_init(DOMAIN, data={"issue_id": issue.issue_id})


async def test_outputs_awaiting_confirmation_arm_only_the_unarmed_outputs(
    hass: HomeAssistant,
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    await async_set_options(hass, entry, armed=[TOWEL_PUMP], control=True)

    result = await async_fix(hass, IssueKind.OUTPUTS_AWAITING_CONFIRMATION)

    assert result["step_id"] == "arm"
    (key,) = result["data_schema"].schema
    options = result["data_schema"].schema[key].serialize()["selector"]["select"]["options"]
    values = [option["value"] for option in options]
    assert TOWEL_PUMP not in values and FLOOR_PUMP in values
    assert suggested(result, "outputs") is None, "nothing is confirmed until checked"
    manager = repairs_flow_manager(hass)
    assert manager is not None
    result = await manager.async_configure(
        result["flow_id"], {"outputs": [LIVING_CEILING, FLOOR_PUMP]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.options["armed_outputs"] == [FLOOR_PUMP, TOWEL_PUMP, LIVING_CEILING]
    assert entry.options["control"] is True
    remaining = issue_of(hass, IssueKind.OUTPUTS_AWAITING_CONFIRMATION)
    assert LIVING_CEILING not in remaining.translation_placeholders["entity_ids"]


async def test_an_invalid_plant_opens_the_entry_reconfigure_flow(hass: HomeAssistant) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    hass.config_entries.async_remove_subentry(entry, zone_subentry_id(entry, "living_area"))
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.problem is not None

    result = await async_fix(hass, IssueKind.INVALID_PLANT)
    assert result["step_id"] == "confirm"
    manager = repairs_flow_manager(hass)
    assert manager is not None
    result = await manager.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_opened"
    flow_type, flow_id = result["next_flow"]
    assert flow_type == "config_flow"
    flow = hass.config_entries.flow
    # The frontend shows a flow it is handed by asking for its current step.
    reconfigure = await flow.async_configure(flow_id)
    assert reconfigure["step_id"] == "reconfigure"
    assert "min_flow_loops" in reconfigure["description_placeholders"]["status"]
    result = await async_choose(flow, reconfigure, "pump_pick")
    result = await async_submit(flow, result, {"pump": "heat_pump"})
    result = await async_submit(
        flow,
        result,
        {
            "name": "Heat pump",
            "min_flow": "guaranteed",
            "supply_temperature": "sensor.ceiling_supply_temperature",
        },
    )
    result = await async_choose(flow, result, "save")
    result = await async_submit(flow, result)
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.plant.pump("heat_pump").min_flow is MinFlow.GUARANTEED
    assert not [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == IssueKind.INVALID_PLANT
    ]


@pytest.mark.parametrize(
    ("kind", "area"),
    [(IssueKind.ZONE_AREA_MISSING, False), (IssueKind.ZONE_WITHOUT_TEMPERATURE_SOURCE, True)],
)
async def test_a_zone_area_problem_opens_the_zone_reconfigure_flow(
    hass: HomeAssistant, kind: IssueKind, area: bool
) -> None:
    if area:
        create_area(hass, "Study")
    entry = await async_import(hass, FLAT)

    result = await async_fix(hass, kind)
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"]["zone"] == "Study"
    manager = repairs_flow_manager(hass)
    assert manager is not None
    result = await manager.async_configure(result["flow_id"], {})

    assert result["reason"] == "zone_opened"
    flow_type, flow_id = result["next_flow"]
    assert flow_type == "config_subentries_flow"
    zone = await hass.config_entries.subentries.async_configure(flow_id)
    assert zone["step_id"] == "zone"
    assert zone["handler"] == (entry.entry_id, "zone")
    assert suggested(zone, "areas") == ["study"]


async def test_a_missing_binding_opens_the_flow_that_binds_it(hass: HomeAssistant) -> None:
    set_temperature(hass, "sensor.study_temperature", 20.0)
    create_area(hass, "Study", temperature="sensor.study_temperature")
    hass.states.async_set("switch.study_valve", "off")
    entry = await async_import(hass, FLAT)
    manager = repairs_flow_manager(hass)
    assert manager is not None
    issues = [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == IssueKind.MISSING_BINDING
    ]
    assert [issue.translation_placeholders["entity_id"] for issue in issues] == ["switch.pump"]

    result = await manager.async_init(DOMAIN, data={"issue_id": issues[0].issue_id})
    result = await manager.async_configure(result["flow_id"], {})
    assert result["reason"] == "reconfigure_opened"
    assert result["next_flow"][0] == "config_flow"

    hass.states.async_set("switch.pump", "off")
    hass.states.async_remove("switch.study_valve")
    await hass.async_block_till_done()
    (issue,) = [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == IssueKind.MISSING_BINDING
    ]
    assert issue.translation_placeholders["entity_id"] == "switch.study_valve"
    result = await manager.async_init(DOMAIN, data={"issue_id": issue.issue_id})
    assert result["description_placeholders"]["path"] == "Zone Study, loop Radiator, valve 1"
    result = await manager.async_configure(result["flow_id"], {})
    assert result["reason"] == "zone_opened"
    zone = await hass.config_entries.subentries.async_configure(result["next_flow"][1])
    assert zone["handler"] == (entry.entry_id, "zone")
    assert suggested(zone, "name") == "Study"


async def test_problems_fixed_outside_hydronicus_have_no_fix_flow(hass: HomeAssistant) -> None:
    set_temperature(hass, "sensor.renamed_away", 19.0)
    create_area(hass, "Study", temperature="sensor.renamed_away")
    await async_import(hass, FLAT)
    hass.states.async_remove("sensor.renamed_away")
    await hass.async_block_till_done()

    issue = issue_of(hass, IssueKind.MISSING_AREA_SENSOR)
    assert not issue.is_fixable
