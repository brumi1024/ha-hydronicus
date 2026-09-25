"""One physical output belongs to one live Plant.

Two config entries that command the same valve, pump, or source demand switch
fight each other, and either one's safe shutdown can stop equipment the other
needs. These tests pin the cross-entry guards: leaving Dry run is refused while
another live Plant shares an output, a stored live Plant that reaches its claim
second is held in a runtime-only Dry run without sending a command and without
losing its stored authorization, it resumes by itself once the conflict is gone,
and every flow warns before such a binding exists.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_DRY_RUN_CONFIRMATION,
    CONF_NAME,
    CONF_PLANT_ID,
    CONF_PUMP_ENTITY,
    CONF_PUMP_OVERRUN,
    CONF_SOURCE_DEMAND_ENTITY,
    CONF_SOURCE_HYSTERESIS,
    CONF_SOURCE_MAXIMUM_AGE,
    CONF_SOURCE_MINIMUM_TEMPERATURE,
    CONF_SOURCE_PRIORITY,
    CONF_SOURCE_TYPE,
    CONF_TEMPERATURE_SENSORS,
    CONF_VALVE_ENTITY,
    CONF_VALVE_OPENING_TIME,
    DOMAIN,
    SUBENTRY_TYPE_SOURCE,
)
from custom_components.hydronicus.core.model import ThermostatHvacMode
from custom_components.hydronicus.diagnostics import async_get_config_entry_diagnostics
from custom_components.hydronicus.entry_configuration import (
    authorize_outputs,
    output_authorization,
)
from custom_components.hydronicus.runtime import HydronicRuntime
from tests.integration.plant_fixtures import plant_entry

SHARED_VALVE = "switch.valve_living"
SHARED_PUMP = "switch.pump"
SHARED_SOURCE = "switch.source_boiler"
OUTPUTS = (SHARED_VALVE, SHARED_PUMP, SHARED_SOURCE)
# A runaway fight toggles without end; the recorder stops mirroring state after this.
CALL_LIMIT = 40


def _ids(n: int) -> list[str]:
    return [f"00000000-0000-4000-8000-0000000{n}000{index}" for index in range(8)]


def _plant_data(
    n: int,
    *,
    sensor: str,
    valve: str = SHARED_VALVE,
    pump: str = SHARED_PUMP,
    source: str | None = SHARED_SOURCE,
    live: bool = True,
    selector: str | None = None,
) -> dict[str, Any]:
    """Return one stored single-zone Plant, authorized for its outputs when live."""
    plant, zone, valve_id, pump_id, circuit, route, source_id, selector_id = _ids(n)
    topology: dict[str, Any] = {
        "zones": [
            {
                "id": zone,
                "name": f"Zone {n}",
                "thermostat": {"kind": "hydronicus", "initial_target_temperature": 21.0},
                "temperature_sensor_metadata": [{"entity_id": sensor}],
            }
        ],
        "valves": [
            {"id": valve_id, "name": "Valve", "entity_id": valve, "opening_time_seconds": 0}
        ],
        "pumps": [{"id": pump_id, "name": "Pump", "entity_id": pump, "overrun_seconds": 0}],
        "circuits": [{"id": circuit, "name": "Loop", "valve_ids": [valve_id], "pump_id": pump_id}],
        "routes": [{"id": route, "zone_id": zone, "circuit_id": circuit}],
        "sources": (
            [{"id": source_id, "name": "Boiler", "source_demand_entity": source}]
            if source is not None
            else []
        ),
    }
    if selector is not None:
        topology["source_selector"] = {"id": selector_id, "name": "Selector", "entity_id": selector}
    data = {CONF_NAME: f"Plant {n}", CONF_PLANT_ID: plant, CONF_DRY_RUN: True, "topology": topology}
    return authorize_outputs(data) if live else data


def _entry(data: dict[str, Any]) -> MockConfigEntry:
    return plant_entry(data, title=data[CONF_NAME])


def _zone_id(entry: MockConfigEntry) -> str:
    return entry.data["topology"]["zones"][0]["id"]


def _record_switch_calls(hass: HomeAssistant) -> list[tuple[str, str]]:
    """Record every switch command and mirror it into state, like a real switch."""
    calls: list[tuple[str, str]] = []

    async def record(call: ServiceCall) -> None:
        calls.append((call.service, call.data["entity_id"]))
        if len(calls) <= CALL_LIMIT:
            hass.states.async_set(
                call.data["entity_id"], "on" if call.service == "turn_on" else "off"
            )

    for service in ("turn_on", "turn_off"):
        hass.services.async_register("switch", service, record)
    for entity_id in (*OUTPUTS, "switch.other_valve", "switch.other_pump", "switch.other_boiler"):
        hass.states.async_set(entity_id, "off")
    hass.states.async_set("sensor.cold_room", "17.0")
    hass.states.async_set("sensor.warm_room", "25.0")
    return calls


def _conflict_issues(hass: HomeAssistant) -> dict[str, ir.IssueEntry]:
    return {
        issue_id: issue
        for (domain, issue_id), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == "output_conflict"
    }


async def _set_up_one_by_one(hass: HomeAssistant, *datas: dict[str, Any]) -> list[MockConfigEntry]:
    entries = []
    for data in datas:
        entry = _entry(data)
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entries.append(entry)
    return entries


async def test_two_live_plants_sharing_outputs_do_not_fight(hass: HomeAssistant) -> None:
    """The second live Plant yields instead of toggling the shared valve without end."""
    calls = _record_switch_calls(hass)
    first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(2, sensor="sensor.warm_room"),
    )

    for entry in (first, second):
        await entry.runtime_data.async_set_zone_hvac_mode(
            _zone_id(entry), ThermostatHvacMode.HEAT, hass=hass
        )
        await hass.async_block_till_done()
    hass.states.async_set("sensor.cold_room", "17.1")
    await hass.async_block_till_done()

    assert len(calls) < CALL_LIMIT, f"shared outputs were toggled {len(calls)} times"
    assert first.runtime_data.dry_run is False
    assert second.runtime_data.dry_run is True
    # Only the live Plant commands, and nothing ever switches the heating path back off.
    assert ("turn_off", SHARED_VALVE) not in calls
    assert hass.states.get(SHARED_VALVE).state == "on"


async def test_leaving_dry_run_is_refused_while_another_live_plant_shares_outputs(
    hass: HomeAssistant,
) -> None:
    """The runtime guard names the live Plant and leaves the Dry run Plant untouched."""
    calls = _record_switch_calls(hass)
    first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(2, sensor="sensor.warm_room", source="switch.other_boiler", live=False),
    )

    with pytest.raises(ServiceValidationError) as raised:
        await second.runtime_data.async_set_dry_run(
            False, hass=hass, authorization=output_authorization(second.data)
        )

    assert raised.value.translation_key == "output_conflict"
    assert raised.value.translation_placeholders["plant"] == "Plant 2"
    assert raised.value.translation_placeholders["other_plant"] == "Plant 1"
    assert raised.value.translation_placeholders["entities"] == f"{SHARED_PUMP}, {SHARED_VALVE}"
    assert second.runtime_data.dry_run is True
    assert second.data[CONF_DRY_RUN] is True
    assert "output_authorization" not in second.data
    assert calls == []


async def test_reconfigure_confirmation_shows_the_output_conflict(hass: HomeAssistant) -> None:
    """The Dry run confirmation reports the conflict as a form error, not a crash."""
    _record_switch_calls(hass)
    _first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(2, sensor="sensor.warm_room", live=False),
    )

    result = await second.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "dry_run"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DRY_RUN: False}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DRY_RUN_CONFIRMATION: True}
    )

    assert result["step_id"] == "dry_run_confirmation"
    assert result["errors"] == {"base": "output_conflict"}
    assert result["description_placeholders"]["other_plant"] == "Plant 1"
    assert SHARED_VALVE in result["description_placeholders"]["entities"]
    assert second.data[CONF_DRY_RUN] is True


async def test_second_live_plant_at_startup_yields_without_commands(hass: HomeAssistant) -> None:
    """Two stored live Plants start together; the one set up second yields to Dry run."""
    calls = _record_switch_calls(hass)
    # Heating state that a live Plant would release with commands if it saw it.
    for entity_id in OUTPUTS:
        hass.states.async_set(entity_id, "on")
    first = _entry(_plant_data(1, sensor="sensor.cold_room"))
    second = _entry(_plant_data(2, sensor="sensor.warm_room"))
    first.add_to_hass(hass)
    second.add_to_hass(hass)
    setup_order: list[str] = []
    original = hass.config_entries.async_update_entry

    def spy(entry: config_entries.ConfigEntry, **kwargs: Any) -> bool:
        if kwargs.get("data", {}).get(CONF_DRY_RUN) is True:
            setup_order.append(entry.entry_id)
        return original(entry, **kwargs)

    hass.config_entries.async_update_entry = spy  # type: ignore[method-assign]
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    live = [entry for entry in (first, second) if not entry.runtime_data.dry_run]
    yielded = [entry for entry in (first, second) if entry.runtime_data.dry_run]
    assert len(live) == 1
    assert len(yielded) == 1
    # Here the first entry reaches its claim first, so the second one is held.
    assert yielded == [second]
    # The hold is runtime-only: nothing rewrote either Plant's stored Dry run
    # setting or output authorization.
    assert setup_order == []
    for entry in (first, second):
        assert entry.data[CONF_DRY_RUN] is False
        assert entry.data["output_authorization"] == output_authorization(entry.data)
    # The yielded Plant is command-free; the live one had no demand to act on either.
    assert [call for call in calls if call[0] == "turn_on"] == []
    issues = _conflict_issues(hass)
    assert list(issues) == [f"output_conflict_{yielded[0].entry_id}"]
    issue = issues[f"output_conflict_{yielded[0].entry_id}"]
    assert issue.is_fixable is False
    assert issue.translation_placeholders == {
        "plant": yielded[0].title,
        "other_plant": live[0].title,
        "entities": f"{SHARED_PUMP}, {SHARED_SOURCE}, {SHARED_VALVE}",
    }


async def test_second_live_plant_setup_sends_no_command_before_yielding(
    hass: HomeAssistant,
) -> None:
    """Setting up a conflicting live Plant never commands the shared outputs."""
    calls = _record_switch_calls(hass)
    (first,) = await _set_up_one_by_one(hass, _plant_data(1, sensor="sensor.cold_room"))
    await first.runtime_data.async_set_zone_hvac_mode(
        _zone_id(first), ThermostatHvacMode.HEAT, hass=hass
    )
    await hass.async_block_till_done()
    before = list(calls)
    assert ("turn_on", SHARED_VALVE) in before

    # Plant 2 has no demand, so a live Plant 2 would switch the shared path off.
    (second,) = await _set_up_one_by_one(hass, _plant_data(2, sensor="sensor.warm_room"))

    assert second.runtime_data.dry_run is True
    assert calls == before
    assert hass.states.get(SHARED_VALVE).state == "on"
    assert f"output_conflict_{second.entry_id}" in _conflict_issues(hass)


@pytest.mark.parametrize(
    "resolve",
    [
        pytest.param(
            lambda hass, live: live.runtime_data.async_set_dry_run(True, hass=hass),
            id="live-plant-enters-dry-run",
        ),
        pytest.param(
            lambda hass, live: hass.config_entries.async_remove(live.entry_id),
            id="live-plant-removed",
        ),
        pytest.param(
            lambda hass, live: hass.config_entries.async_unload(live.entry_id),
            id="live-plant-unloaded",
        ),
    ],
)
async def test_held_plant_resumes_when_the_conflict_is_gone(
    hass: HomeAssistant, resolve: Callable[[HomeAssistant, MockConfigEntry], Any]
) -> None:
    """The repair stays while the live Plant owns the outputs; then the held Plant resumes."""
    calls = _record_switch_calls(hass)
    first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(2, sensor="sensor.warm_room"),
    )
    stored = dict(second.data)
    assert f"output_conflict_{second.entry_id}" in _conflict_issues(hass)

    # A reload of the held Plant keeps the hold and the repair: the conflict still exists.
    assert await hass.config_entries.async_reload(second.entry_id)
    await hass.async_block_till_done()
    assert second.runtime_data.dry_run is True
    assert f"output_conflict_{second.entry_id}" in _conflict_issues(hass)

    assert calls == []
    await resolve(hass, first)
    # Only the live owner's own safe shutdown may command, when it enters Dry run.
    owner_shutdown = list(calls)
    assert all(service == "turn_off" for service, _entity in owner_shutdown)
    await hass.async_block_till_done()

    assert _conflict_issues(hass) == {}
    assert second.state is ConfigEntryState.LOADED
    assert second.runtime_data.dry_run is False
    assert second.runtime_data.output_hold is None
    assert dict(second.data) == stored
    # Resuming through the normal startup path sent nothing: no demand, all off.
    assert calls == owner_shutdown


async def test_owner_that_fails_setup_hands_its_outputs_to_the_held_plant(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A claim that ends in a failed setup must not strand the Plant it held back.

    The failed owner can then be retried, and it is held in its turn.
    """
    calls = _record_switch_calls(hass)
    first = _entry(_plant_data(1, sensor="sensor.cold_room"))
    second = _entry(_plant_data(2, sensor="sensor.warm_room"))
    first.add_to_hass(hass)
    second.add_to_hass(hass)
    stored = {entry.entry_id: dict(entry.data) for entry in (first, second)}
    release = asyncio.Event()
    failures = [RuntimeError("transient failure after the claim")]
    original = HydronicRuntime.async_finish_start

    async def finish_start(self: HydronicRuntime, *args: Any, **kwargs: Any) -> None:
        if self._entry is first and failures:
            await release.wait()
            raise failures.pop()
        await original(self, *args, **kwargs)

    monkeypatch.setattr(HydronicRuntime, "async_finish_start", finish_start)
    setup = hass.async_create_task(async_setup_component(hass, DOMAIN, {}))
    for _ in range(200):
        await asyncio.sleep(0)
        if second.state is ConfigEntryState.LOADED:
            break
    # The first Plant has claimed the outputs, so the second one is held.
    assert second.state is ConfigEntryState.LOADED
    assert second.runtime_data.dry_run is True
    assert list(_conflict_issues(hass)) == [f"output_conflict_{second.entry_id}"]

    release.set()
    await setup
    await hass.async_block_till_done()

    assert first.state is ConfigEntryState.SETUP_ERROR
    assert second.state is ConfigEntryState.LOADED
    assert second.runtime_data.dry_run is False
    assert second.runtime_data.output_hold is None
    assert _conflict_issues(hass) == {}

    # Retrying the failed owner works, and it is now the Plant that is held.
    assert await hass.config_entries.async_reload(first.entry_id)
    await hass.async_block_till_done()
    assert first.state is ConfigEntryState.LOADED
    assert first.runtime_data.dry_run is True
    assert second.runtime_data.dry_run is False
    assert list(_conflict_issues(hass)) == [f"output_conflict_{first.entry_id}"]
    assert {entry.entry_id: dict(entry.data) for entry in (first, second)} == stored
    assert calls == []


async def test_failed_setup_can_be_retried(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A setup that fails after forwarding its platforms unloads them, so a retry works."""
    _record_switch_calls(hass)
    entry = _entry(_plant_data(1, sensor="sensor.cold_room", live=False))
    entry.add_to_hass(hass)
    failures = [RuntimeError("transient failure after forwarding platforms")]
    original = HydronicRuntime.async_finish_start

    async def finish_start(self: HydronicRuntime, *args: Any, **kwargs: Any) -> None:
        if failures:
            raise failures.pop()
        await original(self, *args, **kwargs)

    monkeypatch.setattr(HydronicRuntime, "async_finish_start", finish_start)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    dry_run_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{entry.data[CONF_PLANT_ID]}_dry_run"
    )
    # The failed attempt leaves no entity bound to its discarded runtime.
    assert dry_run_id is not None
    state = hass.states.get(dry_run_id)
    assert state is None or state.state == "unavailable"
    caplog.clear()

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert "has already been setup" not in caplog.text
    state = hass.states.get(dry_run_id)
    assert state is not None
    assert state.state == "on"


async def test_reloading_the_owner_keeps_its_outputs(hass: HomeAssistant) -> None:
    """A reload of the live Plant is not a hand-over: the held Plant stays held."""
    calls = _record_switch_calls(hass)
    first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(2, sensor="sensor.warm_room"),
    )

    assert await hass.config_entries.async_reload(first.entry_id)
    await hass.async_block_till_done()

    assert first.runtime_data.dry_run is False
    assert second.runtime_data.dry_run is True
    assert list(_conflict_issues(hass)) == [f"output_conflict_{second.entry_id}"]
    assert calls == []


async def test_only_one_of_several_held_plants_resumes(hass: HomeAssistant) -> None:
    """When the owner leaves, exactly one held Plant claims; the other stays held."""
    calls = _record_switch_calls(hass)
    first, second, third = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(2, sensor="sensor.warm_room"),
        _plant_data(3, sensor="sensor.warm_room"),
    )
    stored = {entry.entry_id: dict(entry.data) for entry in (second, third)}
    assert second.runtime_data.dry_run is True
    assert third.runtime_data.dry_run is True

    assert await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()

    assert second.runtime_data.dry_run is False
    assert third.runtime_data.dry_run is True
    issues = _conflict_issues(hass)
    assert list(issues) == [f"output_conflict_{third.entry_id}"]
    placeholders = issues[f"output_conflict_{third.entry_id}"].translation_placeholders
    assert placeholders["other_plant"] == "Plant 2"
    assert {entry.entry_id: dict(entry.data) for entry in (second, third)} == stored
    assert calls == []


async def test_held_plant_runtime_never_starts_live(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The held runtime is in Dry run from construction, before it can send anything."""
    _record_switch_calls(hass)
    started: list[tuple[str, bool, bool]] = []
    original = HydronicRuntime.async_start

    async def start(self: HydronicRuntime, *args: Any, **kwargs: Any) -> None:
        started.append((self.name, self.dry_run, self.executor.dry_run))
        await original(self, *args, **kwargs)

    monkeypatch.setattr(HydronicRuntime, "async_start", start)
    _first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(2, sensor="sensor.warm_room"),
    )
    assert await hass.config_entries.async_reload(second.entry_id)
    await hass.async_block_till_done()

    assert started == [
        ("Plant 1", False, False),
        ("Plant 2", True, True),
        ("Plant 2", True, True),
    ]


async def test_dry_run_sensor_explains_a_held_plant(hass: HomeAssistant) -> None:
    """The UI shows the held Plant in Dry run and says why, instead of claiming it is live."""
    _record_switch_calls(hass)
    first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(2, sensor="sensor.warm_room"),
    )
    registry = er.async_get(hass)
    held_id = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{second.data[CONF_PLANT_ID]}_dry_run"
    )
    live_id = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{first.data[CONF_PLANT_ID]}_dry_run"
    )
    assert held_id is not None
    assert live_id is not None

    held = hass.states.get(held_id)
    assert held is not None
    assert held.state == "on"
    assert held.attributes["held_by_output_conflict"] is True
    assert held.attributes["held_by_plant"] == "Plant 1"
    live = hass.states.get(live_id)
    assert live is not None
    assert live.state == "off"
    assert live.attributes["held_by_output_conflict"] is False
    assert live.attributes["held_by_plant"] is None
    diagnostics = json.dumps(await async_get_config_entry_diagnostics(hass, second))
    assert '"held_by_output_conflict": true' in diagnostics
    boundary = second.runtime_data.presentation_snapshot(hass)["plant"]["execution_boundary"]
    assert boundary["dry_run"] is True
    assert "held because another Plant is using the same outputs" in boundary["message"]

    assert await first.runtime_data.async_set_dry_run(True, hass=hass)
    await hass.async_block_till_done()
    resumed = hass.states.get(held_id)
    assert resumed is not None
    assert resumed.state == "off"
    assert resumed.attributes["held_by_output_conflict"] is False


async def test_turning_on_dry_run_for_a_held_plant_is_stored(hass: HomeAssistant) -> None:
    """Asking a held Plant for Dry run stores it, so the Plant does not resume later."""
    calls = _record_switch_calls(hass)
    first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(2, sensor="sensor.warm_room"),
    )

    assert await second.runtime_data.async_set_dry_run(True, hass=hass)
    await hass.async_block_till_done()
    assert second.data[CONF_DRY_RUN] is True
    assert "output_authorization" not in second.data
    assert second.runtime_data.output_hold is None
    assert _conflict_issues(hass) == {}

    assert await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()
    assert second.runtime_data.dry_run is True
    assert calls == []


async def test_reconfigure_shows_a_held_plant_in_dry_run(hass: HomeAssistant) -> None:
    """Reconfigure offers the held Plant's effective Dry run and reports the conflict."""
    _record_switch_calls(hass)
    _first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(2, sensor="sensor.warm_room"),
    )

    result = await second.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "dry_run"}
    )
    (dry_run_key,) = [key for key in result["data_schema"].schema if key == CONF_DRY_RUN]
    assert dry_run_key.default() is True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DRY_RUN: False}
    )
    assert result["step_id"] == "dry_run_confirmation"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DRY_RUN_CONFIRMATION: True}
    )

    assert result["errors"] == {"base": "output_conflict"}
    assert result["description_placeholders"]["other_plant"] == "Plant 1"
    assert second.runtime_data.dry_run is True


async def test_removing_the_yielded_plant_clears_its_repair(hass: HomeAssistant) -> None:
    """A removed Plant leaves no repair behind."""
    _record_switch_calls(hass)
    _first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(2, sensor="sensor.warm_room"),
    )

    assert await hass.config_entries.async_remove(second.entry_id)
    await hass.async_block_till_done()

    assert _conflict_issues(hass) == {}


async def test_live_plants_without_shared_outputs_are_unaffected(hass: HomeAssistant) -> None:
    """Separate outputs keep both Plants live, with no repair and no refusal."""
    _record_switch_calls(hass)
    first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room"),
        _plant_data(
            2,
            sensor="sensor.warm_room",
            valve="switch.other_valve",
            pump="switch.other_pump",
            source="switch.other_boiler",
            live=False,
        ),
    )

    assert await second.runtime_data.async_set_dry_run(
        False, hass=hass, authorization=output_authorization(second.data)
    )

    assert first.runtime_data.dry_run is False
    assert second.runtime_data.dry_run is False
    assert _conflict_issues(hass) == {}


async def test_dry_run_plants_may_share_outputs(hass: HomeAssistant) -> None:
    """Sharing is only dangerous when both Plants command the outputs."""
    calls = _record_switch_calls(hass)
    first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room", live=False),
        _plant_data(2, sensor="sensor.warm_room", live=False),
    )

    assert first.runtime_data.dry_run is True
    assert second.runtime_data.dry_run is True
    assert _conflict_issues(hass) == {}
    assert calls == []


def test_exclusive_outputs_are_the_authorized_outputs() -> None:
    """The source selector is never commanded, so it is not an exclusive output."""
    from custom_components.hydronicus.entry_configuration import exclusive_output_entity_ids

    data = _plant_data(1, sensor="sensor.cold_room", selector="select.heat_source")

    assert exclusive_output_entity_ids(data) == frozenset(OUTPUTS)


async def _dry_run_pair(hass: HomeAssistant) -> MockConfigEntry:
    """Set up Plant 1 bound to the shared outputs and Plant 2 on separate ones."""
    _record_switch_calls(hass)
    _first, second = await _set_up_one_by_one(
        hass,
        _plant_data(1, sensor="sensor.cold_room", live=False),
        _plant_data(
            2,
            sensor="sensor.warm_room",
            valve="switch.other_valve",
            pump="switch.other_pump",
            source=None,
            live=False,
        ),
    )
    return second


async def test_source_flow_warns_about_a_demand_entity_bound_by_another_plant(
    hass: HomeAssistant,
) -> None:
    """A source demand switch that another Plant binds is a reviewed warning."""
    second = await _dry_run_pair(hass)
    handles = len(second.subentries)

    result = await hass.config_entries.subentries.async_init(
        (second.entry_id, SUBENTRY_TYPE_SOURCE),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Boiler",
            CONF_SOURCE_TYPE: "external",
            CONF_SOURCE_PRIORITY: 1,
            CONF_SOURCE_DEMAND_ENTITY: SHARED_SOURCE,
            CONF_SOURCE_MINIMUM_TEMPERATURE: 0.0,
            CONF_SOURCE_MAXIMUM_AGE: 300.0,
            CONF_SOURCE_HYSTERESIS: 0.5,
        },
    )

    assert result["step_id"] == "review"
    assert not result.get("errors")
    warnings = result["description_placeholders"]["warnings"]
    assert SHARED_SOURCE in warnings
    assert "Plant 1" in warnings
    assert len(second.subentries) == handles

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input={"confirm": False}
    )
    assert result["errors"] == {"base": "confirm_required"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], user_input={"confirm": True}
    )

    assert result["type"] == "create_entry"
    assert len(second.subentries) == handles + 1


async def test_initial_setup_warns_about_equipment_bound_by_another_plant(
    hass: HomeAssistant,
) -> None:
    """The initial review lists a valve or pump that another Plant binds, and still saves."""
    _record_switch_calls(hass)
    await _set_up_one_by_one(hass, _plant_data(1, sensor="sensor.cold_room", live=False))

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"name": "Second plant"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Study", CONF_TEMPERATURE_SENSORS: ["sensor.warm_room"]},
    )
    assert result["step_id"] == "circuit"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "name": "Study loop",
            CONF_VALVE_ENTITY: "switch.other_valve",
            CONF_PUMP_ENTITY: SHARED_PUMP,
            CONF_VALVE_OPENING_TIME: 0,
            CONF_PUMP_OVERRUN: 0,
        },
    )

    assert result["step_id"] == "review"
    assert not result.get("errors")
    warnings = result["description_placeholders"]["warnings"]
    assert SHARED_PUMP in warnings
    assert "Plant 1" in warnings
    assert "switch.other_valve" not in warnings

    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={})

    assert result["type"] == "create_entry"
    assert result["data"][CONF_DRY_RUN] is True
