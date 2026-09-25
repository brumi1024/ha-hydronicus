"""Arming is per output, Control equipment runs the off sequence, and Dry run only proposes.

Contract K6 and decision 15: a new Plant has nothing armed and control off, an
unarmed output receives no call, and editing a zone never changes arming.
"""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.diagnostics import async_get_config_entry_diagnostics
from custom_components.hydronicus.issues import IssueKind
from tests.integration.helpers import (
    FLOOR_PUMP,
    LIVING_CEILING,
    LIVING_FLOOR,
    REFERENCE_OUTPUTS,
    REFERENCE_PLANT,
    SOURCE_REQUEST,
    TOWEL_PUMP,
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    reference_world,
    set_zone_temperature,
)
from tests.integration.test_lifecycle import RUNNING, async_heat_living_area


def issues_of(hass: HomeAssistant, kind: IssueKind) -> list[ir.IssueEntry]:
    return [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == kind
    ]


async def async_call_for_heat(hass: HomeAssistant) -> None:
    await async_call(hass, "select", "select_option", entity_id="select.home_mode", option="heat")
    await async_call(
        hass, "climate", "set_hvac_mode", entity_id="climate.living_area", hvac_mode="heat"
    )
    set_zone_temperature(hass, "living_area", 19.0)
    await hass.async_block_till_done()


async def test_unarmed_outputs_receive_no_call_and_their_loops_do_not_run(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    await async_set_options(hass, entry, armed=[LIVING_FLOOR, FLOOR_PUMP], control=True)
    await async_call_for_heat(hass)
    await async_advance(hass, freezer, 400, step=5)

    assert actuators.shorts() == [f"{LIVING_FLOOR}:on", f"{FLOOR_PUMP}:on"]
    status = hass.states.get("sensor.home_status").attributes
    assert status["reasons"]["living_area.ceiling"].startswith("dropped")
    assert LIVING_CEILING in status["unarmed_outputs"]
    (issue,) = issues_of(hass, IssueKind.OUTPUTS_AWAITING_CONFIRMATION)
    assert LIVING_CEILING in issue.translation_placeholders["entity_ids"]
    assert FLOOR_PUMP not in issue.translation_placeholders["entity_ids"]


async def test_a_new_plant_has_nothing_armed_and_raises_no_confirmation_repair(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    await async_call_for_heat(hass)
    await async_advance(hass, freezer, 400, step=10)

    assert entry.options == {"armed_outputs": [], "control": False}
    assert actuators.calls == []
    assert issues_of(hass, IssueKind.OUTPUTS_AWAITING_CONFIRMATION) == []
    assert hass.states.get("switch.home_control_equipment").state == "off"


async def test_control_off_runs_the_off_sequence_then_only_observes(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_heat_living_area(hass, freezer)
    actuators.clear()

    await async_call(hass, "switch", "turn_off", entity_id="switch.home_control_equipment")
    assert entry.options["control"] is False
    await async_advance(hass, freezer, 600, step=5)

    order = actuators.shorts()
    assert order[0] == f"{SOURCE_REQUEST}:off"
    assert set(order) == {f"{entity}:off" for entity in RUNNING}
    assert order.index(f"{FLOOR_PUMP}:off") < order.index(f"{LIVING_FLOOR}:off")
    assert all(hass.states.get(entity).state == "off" for entity in RUNNING)
    assert hass.states.get("switch.home_control_equipment").attributes["live"] is False
    actuators.clear()

    # Observing only: more demand proposes, and sends nothing.
    await async_call(
        hass, "climate", "set_hvac_mode", entity_id="climate.basement", hvac_mode="heat"
    )
    set_zone_temperature(hass, "basement", 18.0)
    await hass.async_block_till_done()
    await async_advance(hass, freezer, 400, step=10)
    assert actuators.calls == []
    proposed = hass.states.get("sensor.home_status").attributes["proposed"]
    assert proposed["switch.home_basement_ceiling_heating_valve"] is True


async def test_dry_run_records_proposals_and_advances_them_as_if_live(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    await async_set_options(hass, entry, armed=REFERENCE_OUTPUTS, control=False)
    await async_call_for_heat(hass)
    await async_advance(hass, freezer, 200, step=5)

    assert actuators.calls == []
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    proposals = [(p["entity"], p["target"]) for p in diagnostics["proposals"]]
    assert proposals[:2] == [(LIVING_CEILING, {"on": True}), (LIVING_FLOOR, {"on": True})]
    assert proposals[2:] == [
        (FLOOR_PUMP, {"on": True}),
        (SOURCE_REQUEST, {"on": True}),
        (TOWEL_PUMP, {"on": True}),
    ]
    status = hass.states.get("sensor.home_status")
    assert status.state == "heating" and status.attributes["live"] is False
    assert hass.states.get("binary_sensor.living_area_floor_flowing").state == "on"
    assert all(hass.states.get(entity).state == "off" for entity in RUNNING)


async def test_editing_a_zone_never_changes_arming(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_heat_living_area(hass, freezer)
    options = dict(entry.options)
    actuators.clear()
    living = next(s for s in entry.subentries.values() if s.unique_id == "living_area")
    basement = next(s for s in entry.subentries.values() if s.unique_id == "basement")

    hass.states.async_set("sensor.extra_temperature", "20.0", {"unit_of_measurement": "°C"})
    hass.config_entries.async_update_subentry(
        entry,
        living,
        title="Living",
        data={**living.data, "name": "Living", "temperature": ["sensor.extra_temperature"]},
    )
    await hass.async_block_till_done()
    thermostat = {"digital": {"presets": {"comfort": 22, "eco": 18}, "min_on": 300}}
    hass.config_entries.async_update_subentry(
        entry, basement, data={**basement.data, "thermostat": thermostat}
    )
    await hass.async_block_till_done()
    await async_advance(hass, freezer, 300, step=5)

    assert entry.runtime_data.plant.zone("living_area").name == "Living"
    assert dict(entry.options) == options
    assert actuators.calls == []
    assert {e for e in REFERENCE_OUTPUTS if hass.states.get(e).state == "on"} == RUNNING


async def test_an_output_that_never_follows_is_retried_and_raises_a_repair(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    reference_world(hass)
    entry = await async_import(hass, REFERENCE_PLANT)
    await async_set_options(hass, entry, armed=REFERENCE_OUTPUTS, control=True)
    actuators.ignoring.add(LIVING_FLOOR)
    await async_call_for_heat(hass)
    await async_advance(hass, freezer, 120, step=2)

    attempts = [call.at for call in actuators.to(LIVING_FLOOR)]
    assert len(attempts) >= 4
    assert [round(b - a) for a, b in zip(attempts, attempts[1:], strict=False)][:3] == [
        10,
        20,
        40,
    ], "each retry waits a backoff that doubles from 10 seconds"
    (issue,) = issues_of(hass, IssueKind.OUTPUT_NOT_RESPONDING)
    assert issue.translation_placeholders["entity_id"] == LIVING_FLOOR
    assert hass.states.get("sensor.home_status").state == "degraded"
    assert not actuators.to(FLOOR_PUMP), "a valve whose open is not observed keeps its loop out"

    actuators.ignoring.clear()
    await async_advance(hass, freezer, 400, step=5)
    assert issues_of(hass, IssueKind.OUTPUT_NOT_RESPONDING) == []
