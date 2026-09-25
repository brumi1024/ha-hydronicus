"""Zones follow what their areas name on every evaluation, without a reload (decision 12)."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.hydronicus.areas import area_review_warnings, area_warnings_to_confirm
from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.core.plant_file import read_plant_file
from custom_components.hydronicus.issues import IssueKind
from tests.integration.helpers import (
    Actuators,
    async_advance,
    async_call,
    async_import,
    async_set_options,
    create_area,
    set_temperature,
)

FLAT = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump, overrun: 0}
zones:
  study:
    areas: [study]
    loops:
      radiator: {valves: [switch.study_valve], pump: pump}
"""


def issue_keys(hass: HomeAssistant) -> dict[str, ir.IssueEntry]:
    return {
        str(issue.translation_key): issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN
    }


async def async_flat(hass: HomeAssistant, *, heat: bool = True):
    hass.states.async_set("switch.pump", "off")
    hass.states.async_set("switch.study_valve", "off")
    entry = await async_import(hass, FLAT)
    await async_set_options(hass, entry, armed=["switch.pump", "switch.study_valve"], control=True)
    if heat:
        await async_call(
            hass, "select", "select_option", entity_id="select.flat_mode", option="heat"
        )
        await async_call(
            hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat"
        )
    return entry


async def test_a_changed_area_sensor_is_followed_without_a_reload(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    set_temperature(hass, "sensor.study_a", 19.0)
    set_temperature(hass, "sensor.study_b", 23.0)
    area = create_area(hass, "Study", temperature="sensor.study_a")
    entry = await async_flat(hass)
    runtime = entry.runtime_data
    assert actuators.shorts() == ["switch.study_valve:on"]
    assert hass.states.get("sensor.study_combined_temperature").state == "19.0"
    actuators.clear()

    ar.async_get(hass).async_update(area.id, temperature_entity_id="sensor.study_b")
    await hass.async_block_till_done()

    assert entry.runtime_data is runtime, "the Plant was not reloaded"
    assert actuators.shorts() == ["switch.study_valve:off"]
    temperature = hass.states.get("sensor.study_combined_temperature")
    assert temperature.state == "23.0"
    assert temperature.attributes["areas"]["study"]["temperature_sensor"] == "sensor.study_b"
    actuators.clear()

    # The state listener follows the new sensor, and no longer the old one.
    set_temperature(hass, "sensor.study_a", 15.0)
    await hass.async_block_till_done()
    assert actuators.calls == []
    set_temperature(hass, "sensor.study_b", 19.0)
    await hass.async_block_till_done()
    assert actuators.shorts() == ["switch.study_valve:on"]
    await async_advance(hass, freezer, 5)
    assert entry.runtime_data is runtime


async def test_a_hydronicus_sensor_named_by_an_area_is_ignored_and_repaired(
    hass: HomeAssistant, actuators: Actuators
) -> None:
    set_temperature(hass, "sensor.study_a", 19.0)
    area = create_area(hass, "Study", temperature="sensor.study_a")
    entry = await async_flat(hass)
    actuators.clear()

    ar.async_get(hass).async_update(
        area.id, temperature_entity_id="sensor.study_combined_temperature"
    )
    await hass.async_block_till_done()

    issues = issue_keys(hass)
    assert issues[IssueKind.ZONE_AREA_SELF_FEED].translation_placeholders["entity_ids"] == (
        "sensor.study_combined_temperature"
    )
    assert IssueKind.ZONE_WITHOUT_TEMPERATURE_SOURCE in issues
    assert actuators.shorts() == ["switch.study_valve:off"], "no temperature, no demand"
    assert entry.runtime_data.areas.self_provided == {
        "study": ("sensor.study_combined_temperature",)
    }


async def test_a_missing_area_is_repaired_and_followed_once_it_exists(
    hass: HomeAssistant, actuators: Actuators
) -> None:
    set_temperature(hass, "sensor.study_a", 19.0)
    entry = await async_flat(hass)
    runtime = entry.runtime_data
    issues = issue_keys(hass)
    assert issues[IssueKind.ZONE_AREA_MISSING].translation_placeholders["recreate_name"] == "Study"
    assert actuators.calls == []

    create_area(hass, "Study", temperature="sensor.study_a")
    await hass.async_block_till_done()

    assert IssueKind.ZONE_AREA_MISSING not in issue_keys(hass)
    assert actuators.shorts() == ["switch.study_valve:on"]
    assert entry.runtime_data is runtime


async def test_an_area_naming_a_missing_sensor_raises_a_repair(hass: HomeAssistant) -> None:
    """Home Assistant does not follow a renamed or removed sensor into the area settings."""
    set_temperature(hass, "sensor.renamed_away", 19.0)
    create_area(hass, "Study", temperature="sensor.renamed_away")
    await async_flat(hass, heat=False)
    assert IssueKind.MISSING_AREA_SENSOR not in issue_keys(hass)

    hass.states.async_remove("sensor.renamed_away")
    await hass.async_block_till_done()

    issue = issue_keys(hass)[IssueKind.MISSING_AREA_SENSOR]
    assert issue.translation_placeholders["entity_id"] == "sensor.renamed_away"
    assert issue.translation_placeholders["area"] == "Study"
    assert hass.states.get("sensor.flat_status").state == "degraded"


async def test_only_the_climate_entity_of_a_single_area_zone_goes_in_its_area(
    hass: HomeAssistant,
) -> None:
    set_temperature(hass, "sensor.study_a", 19.0)
    create_area(hass, "Study", temperature="sensor.study_a")
    await async_flat(hass, heat=False)

    registry = er.async_get(hass)
    climate = registry.async_get("climate.study")
    assert climate.area_id == "study"
    assert registry.async_get("sensor.study_combined_temperature").area_id is None
    device = dr.async_get(hass).async_get(climate.device_id)
    assert device.area_id is None


async def test_the_area_review_warns_about_missing_areas_and_shared_areas(
    hass: HomeAssistant,
) -> None:
    create_area(hass, "Study")
    plant = read_plant_file(
        FLAT.replace("areas: [study]", "areas: [study, attic]")
        + "  den:\n    areas: [study]\n    thermostat: {external: climate.den}\n"
    )

    warnings = area_review_warnings(hass, plant)

    assert {(w.code, w.area_id) for w in warnings} == {
        ("area_missing", "attic"),
        ("area_without_temperature_sensor", "study"),
        ("area_in_several_zones", "study"),
    }
    assert [w.code for w in area_warnings_to_confirm(warnings)] == ["area_missing"]
