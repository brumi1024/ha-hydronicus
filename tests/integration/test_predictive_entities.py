"""Learning controls and the comfort decision Home Assistant actually displays."""

from dataclasses import replace
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from custom_components.hydronicus.core.model import DigitalThermostat, LearningMode, Mode
from custom_components.hydronicus.core.thermal import (
    RecoveryEpisode,
    RecoveryEstimate,
    ThermalModel,
)
from custom_components.hydronicus.diagnostics import async_get_config_entry_diagnostics
from custom_components.hydronicus.storage import async_store_plant
from tests.integration.helpers import async_call, async_import, set_temperature, zone_subentry_id

PLANT = """
hydronicus: 2
name: Circuit control
pumps:
  floor: {switch: switch.floor_pump}
zones:
  study:
    temperature: [sensor.study]
    thermostat:
      digital:
        learning: assist
        target: 21
        min_on: 0
        min_off: 0
        schedule:
          entity: schedule.study
          max_early_start: 7200
          heating_rate: 3
    loops:
      floor: {valves: [switch.study_valve], pump: floor}
  other:
    temperature: [sensor.other]
    thermostat: {digital: {learning: observe}}
  plain:
    temperature: [sensor.plain]
  external:
    thermostat: {external: climate.existing}
"""


def prepare(hass: HomeAssistant) -> float:
    now = dt_util.utcnow().timestamp()
    for entity in ("sensor.study", "sensor.other", "sensor.plain"):
        set_temperature(hass, entity, 20)
    for entity in ("switch.floor_pump", "switch.study_valve"):
        hass.states.async_set(entity, "off")
    hass.states.async_set("climate.existing", "off", {"hvac_action": "off"})
    hass.states.async_set(
        "schedule.study", "off", {"next_event": dt_util.utc_from_timestamp(now + 3600)}
    )
    return now


async def follow_schedule(hass: HomeAssistant) -> None:
    await async_call(
        hass, "select", "select_option", entity_id="select.circuit_control_mode", option="heat"
    )
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="heat")
    await async_call(
        hass, "climate", "set_preset_mode", entity_id="climate.study", preset_mode="schedule"
    )


async def test_accepted_recovery_displays_the_same_proposal_as_demand_and_manual_changes_win(
    hass: HomeAssistant,
) -> None:
    now = prepare(hass)
    entry = await async_import(hass, PLANT)
    runtime = entry.runtime_data
    recovery = RecoveryEstimate(
        5400,
        True,
        "ready",
        "validated independent recovery history",
        episode_count=12,
        validation_count=5,
        valid_until=now + 86400,
    )
    with patch.object(runtime.learning, "estimate", return_value=recovery):
        await follow_schedule(hass)
        view = runtime.view
        assert view is not None
        proposal = view.desired.comfort["study"]
        state = hass.states.get("climate.study")
        assert state is not None
        assert state.attributes["temperature"] == proposal.target == 21
        assert state.attributes["effective_target"] == proposal.target
        assert state.attributes["early_start"] is proposal.early_start is True
        assert state.attributes["recovery_method"] == proposal.recovery_method == "learned"
        assert state.attributes["learning_mode"] == "assist"
        assert state.attributes["learning_episode_count"] == 12
        assert state.attributes["learning_confidence"] is True
        assert state.attributes["estimated_recovery_seconds"] == 5400
        # Room recovery starts with circulation, after the valve's opening wait.
        assert state.attributes["planned_recovery_seconds"] == 5400 + 180
        assert view.desired.demands["study"].on is True
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)
        assert diagnostics["desired"]["comfort"]["study"]["target"] == 21
        assert diagnostics["observations"]["recovery"]["study"]["confidence"] is True
        assert diagnostics["forecast"] is None
        evidence = diagnostics["learning"]["zones"]["study"]
        assert evidence["evidence"] == "inferred_circulation"
        assert evidence["heat_delivery_measured"] is False

        with patch.object(runtime, "request_evaluation"):
            await async_call(
                hass, "climate", "set_temperature", entity_id="climate.study", temperature=22
            )
            state = hass.states.get("climate.study")
            assert state is not None
            assert state.attributes["temperature"] == 22
            assert state.attributes["preset_mode"] == "none"
            assert state.attributes["early_start"] is False
            assert runtime.view is view, "the new manual target must precede reevaluation"
        runtime.request_evaluation()
        await hass.async_block_till_done()
        assert hass.states.get("climate.study").attributes["temperature"] == 22


async def test_observation_predictions_do_not_change_the_configured_rate(
    hass: HomeAssistant,
) -> None:
    now = prepare(hass)
    entry = await async_import(hass, PLANT.replace("learning: assist", "learning: observe"))
    recovery = RecoveryEstimate(5400, True, "ready", "validated", valid_until=now + 86400)
    with patch.object(entry.runtime_data.learning, "estimate", return_value=recovery):
        await follow_schedule(hass)
    state = hass.states.get("climate.study")
    assert state is not None
    assert state.attributes["temperature"] == 19
    assert state.attributes["early_start"] is False
    assert state.attributes["recovery_method"] == "configured"
    assert state.attributes["planned_recovery_seconds"] == 1200
    assert state.attributes["estimated_recovery_seconds"] == 5400


async def test_reset_button_is_scoped_to_its_zone_and_preserves_controls(
    hass: HomeAssistant,
) -> None:
    now = prepare(hass)
    entry = await async_import(hass, PLANT)
    runtime = entry.runtime_data
    registry = er.async_get(hass)
    button = registry.async_get("button.study_reset_recovery_learning")
    assert button is not None
    assert button.unique_id == f"{runtime.plant.id}_zone_study_reset_learning"
    assert button.config_subentry_id == zone_subentry_id(entry, "study")
    assert button.entity_category is EntityCategory.CONFIG
    assert hass.states.get("button.plain_reset_recovery_learning") is None
    assert hass.states.get("button.external_reset_recovery_learning") is None
    model = ThermalModel((RecoveryEpisode(Mode.HEAT, now - 1800, now - 300, 1, "reached"),))
    for slug in ("study", "other"):
        runtime.learning.sampler.zones[slug].models[Mode.HEAT] = model
    safety = runtime.state.to_dict()
    thermostats = dict(runtime.thermostats)
    options = dict(entry.options)

    await async_call(hass, "button", "press", entity_id=button.entity_id)

    assert runtime.learning.sampler.zones["study"].models == {}
    assert runtime.learning.sampler.zones["other"].models[Mode.HEAT] == model
    assert runtime.state.to_dict() == safety
    assert runtime.thermostats == thermostats
    assert dict(entry.options) == options

    zone = runtime.plant.zone("study")
    assert isinstance(zone.thermostat, DigitalThermostat)
    updated = replace(zone, thermostat=replace(zone.thermostat, learning=LearningMode.OFF))
    async_store_plant(
        hass,
        entry,
        replace(
            runtime.plant,
            zones=tuple(
                updated if item.slug == zone.slug else item for item in runtime.plant.zones
            ),
        ),
    )
    await hass.async_block_till_done()
    assert registry.async_get(button.entity_id) is None


async def test_a_cooling_preset_keeps_its_last_active_mode_while_switched_off(
    hass: HomeAssistant,
) -> None:
    from tests.integration.helpers import set_humidity
    from tests.integration.test_entities import COOLING

    set_temperature(hass, "sensor.study", 26)
    set_temperature(hass, "sensor.supply", 22)
    set_humidity(hass, "sensor.study_rh", 50)
    hass.states.async_set("switch.pump", "off")
    hass.states.async_set("switch.study_valve", "off")
    await async_import(hass, COOLING)
    await async_call(hass, "climate", "set_hvac_mode", entity_id="climate.study", hvac_mode="cool")
    await async_call(
        hass, "climate", "set_preset_mode", entity_id="climate.study", preset_mode="eco"
    )
    await async_call(hass, "climate", "turn_off", entity_id="climate.study")
    state = hass.states.get("climate.study")
    assert state is not None
    assert state.state == "off"
    assert state.attributes["temperature"] == 27
    await async_call(hass, "climate", "turn_on", entity_id="climate.study")
    state = hass.states.get("climate.study")
    assert state is not None
    assert state.state == "cool"
    assert state.attributes["temperature"] == 27
