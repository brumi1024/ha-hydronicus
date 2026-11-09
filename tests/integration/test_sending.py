"""The calls the runtime sends: their services, their order, their deadlines, and stopping.

The valves here are ``valve`` entities, whose services the test registers, so a
call can be made to fail, to hang, or to wait until the test releases it. The
actuators still see every call as it is made and follow it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir

from custom_components.hydronicus.const import DOMAIN, OPTION_CONTROL
from custom_components.hydronicus.core.plant_file import read_plant_file
from custom_components.hydronicus.issues import IssueKind
from tests.integration.helpers import (
    REFERENCE_PLANT,
    SOURCE_MODE,
    SOURCE_REQUEST,
    Actuators,
    async_advance,
    async_call,
    async_heat_living_area,
    async_import,
    async_set_options,
    set_temperature,
    set_zone_temperature,
)

VALVES = """
hydronicus: 2
name: Flat
pumps:
  pump: {switch: switch.pump, overrun: 0}
zones:
  den:
    temperature: [sensor.den]
    loops:
      radiator: {valves: [valve.den], pump: pump}
  study:
    temperature: [sensor.study]
    loops:
      radiator: {valves: [valve.study], pump: pump}
  office:
    temperature: [sensor.office]
    loops:
      radiator: {valves: [valve.office], pump: pump}
"""
ZONES = ("den", "study", "office")


class ValveServices:
    """The valve services: a held valve's call waits until released, a failing one raises."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.failing: set[str] = set()
        self._held: dict[str, asyncio.Event] = {}
        # The valves whose call is waiting now.
        self.waiting: set[str] = set()
        for service in ("open_valve", "close_valve"):
            hass.services.async_register("valve", service, self._handle)

    def hold(self, entity_id: str) -> None:
        """Make the valve's calls wait until ``release``."""
        self._held[entity_id] = asyncio.Event()

    def release(self, entity_id: str) -> None:
        self._held.pop(entity_id).set()

    async def _handle(self, call: ServiceCall) -> None:
        entity_id = str(call.data["entity_id"])
        if entity_id in self.failing:
            raise HomeAssistantError(f"{entity_id} is unreachable")
        if (held := self._held.get(entity_id)) is not None:
            self.waiting.add(entity_id)
            try:
                await held.wait()
            finally:
                self.waiting.discard(entity_id)


@pytest.fixture
def valves(hass: HomeAssistant) -> ValveServices:
    return ValveServices(hass)


async def async_until(predicate: Callable[[], object]) -> None:
    """Let the event loop run until ``predicate`` holds, without waiting for held calls."""
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("the condition never held")


async def async_flat(hass: HomeAssistant, *calling: str) -> ConfigEntry:
    """Set the Plant up armed in Dry run, with ``calling`` zones asking for heat."""
    hass.states.async_set("switch.pump", "off")
    for zone in ZONES:
        set_temperature(hass, f"sensor.{zone}", 18.0)
        hass.states.async_set(f"valve.{zone}", "closed")
    entry = await async_import(hass, VALVES)
    await async_set_options(hass, entry, armed=read_plant_file(VALVES).outputs())
    await async_call(hass, "select", "select_option", entity_id="select.flat_mode", option="heat")
    for zone in calling:
        await async_call(
            hass, "climate", "set_hvac_mode", entity_id=f"climate.{zone}", hvac_mode="heat"
        )
    return entry


def control_on(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Turn Control equipment on without waiting, since a held call would never let it settle."""
    hass.config_entries.async_update_entry(entry, options={**entry.options, OPTION_CONTROL: True})


async def test_valves_are_opened_and_closed_through_the_valve_services(
    hass: HomeAssistant, actuators: Actuators, valves: ValveServices, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_flat(hass, "den")
    await async_set_options(hass, entry, control=True)
    await async_advance(hass, freezer, 200, step=5)
    assert actuators.shorts() == ["valve.den:on", "switch.pump:on"]
    assert [call.service for call in actuators.to("valve.den")] == ["open_valve"]
    assert hass.states.get("valve.den").state == "open"

    # The den's thermostat holds its demand for its minimum on time, 600 seconds.
    set_temperature(hass, "sensor.den", 22.0)
    await async_advance(hass, freezer, 420, step=5)

    assert actuators.shorts()[2:] == ["switch.pump:off", "valve.den:off"]
    assert [call.service for call in actuators.to("valve.den")] == ["open_valve", "close_valve"]
    assert hass.states.get("valve.den").state == "closed"


async def test_unloading_while_a_call_hangs_sends_nothing_after_it(
    hass: HomeAssistant, actuators: Actuators, valves: ValveServices
) -> None:
    """Stopping cancels the call in progress and every batch behind it, never commands."""
    entry = await async_flat(hass, "den", "study")
    valves.hold("valve.den")
    control_on(hass, entry)
    # One batch opens both valves; the den's call hangs with the study's behind it.
    await async_until(lambda: valves.waiting)
    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": "climate.office", "hvac_mode": "heat"}
    )
    # A second batch, for the office, queues behind the first.
    await async_until(lambda: "valve.office" in entry.runtime_data.reconcile_state.attempts)
    assert actuators.shorts() == ["valve.den:on"]

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not valves.waiting, "the call in progress is cancelled"
    valves.release("valve.den")
    await hass.async_block_till_done()

    assert actuators.shorts() == ["valve.den:on"]


async def test_a_call_not_sent_before_its_deadline_is_skipped_and_retried(
    hass: HomeAssistant,
    actuators: Actuators,
    valves: ValveServices,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    entry = await async_flat(hass, "den", "study")
    valves.hold("valve.den")
    control_on(hass, entry)
    await async_until(lambda: valves.waiting)

    # The den's call returns only after the study's call may no longer act.
    freezer.tick(timedelta(seconds=11))
    valves.release("valve.den")
    await hass.async_block_till_done()

    assert "did not send SwitchTarget(on=True) to valve.study in time" in caplog.text
    await async_advance(hass, freezer, 30, step=5)
    assert actuators.shorts() == ["valve.den:on", "valve.study:on"], "only the retry is sent"


async def test_a_call_that_does_not_return_in_time_is_abandoned(
    hass: HomeAssistant,
    actuators: Actuators,
    valves: ValveServices,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    entry = await async_flat(hass, "den", "study")
    valves.hold("valve.den")
    control_on(hass, entry)
    await async_until(lambda: valves.waiting)

    # The study's call starts with a tenth of a second left before its deadline, and hangs.
    valves.hold("valve.study")
    freezer.tick(timedelta(seconds=9.9))
    valves.release("valve.den")
    await async_until(lambda: "valve.study" in valves.waiting)
    freezer.tick(timedelta(seconds=0.2))
    with caplog.at_level(logging.WARNING):
        await hass.async_block_till_done()

    assert "valve.open_valve for valve.study did not return in time" in caplog.text
    assert actuators.shorts() == ["valve.den:on", "valve.study:on"]
    assert not valves.waiting, "the call is abandoned"


async def test_a_call_that_fails_is_retried_and_raises_a_repair(
    hass: HomeAssistant,
    actuators: Actuators,
    valves: ValveServices,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    entry = await async_flat(hass, "den")
    valves.failing.add("valve.den")
    actuators.ignoring.add("valve.den")
    await async_set_options(hass, entry, control=True)

    assert "valve.open_valve for valve.den failed: valve.den is unreachable" in caplog.text
    await async_advance(hass, freezer, 120, step=5)

    assert len(actuators.to("valve.den")) >= 3
    (issue,) = [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == IssueKind.OUTPUT_NOT_RESPONDING
    ]
    assert issue.translation_placeholders["entity_id"] == "valve.den"
    assert hass.states.get("sensor.flat_status").state == "degraded"


def not_responding(hass: HomeAssistant) -> list[str]:
    return [
        issue.translation_placeholders["entity_id"]
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == IssueKind.OUTPUT_NOT_RESPONDING
    ]


async def test_a_valve_that_shows_opening_is_waited_for_and_reported_if_it_never_arrives(
    hass: HomeAssistant, actuators: Actuators, valves: ValveServices, freezer: FrozenDateTimeFactory
) -> None:
    entry = await async_flat(hass, "den", "study")
    actuators.ignoring.update({"valve.den", "valve.study"})
    await async_set_options(hass, entry, control=True)
    assert sorted(actuators.shorts()) == ["valve.den:on", "valve.study:on"]
    hass.states.async_set("valve.den", "opening")
    hass.states.async_set("valve.study", "opening")
    await hass.async_block_till_done()
    actuators.clear()

    await async_advance(hass, freezer, 150, step=5)
    hass.states.async_set("valve.study", "open")
    await async_advance(hass, freezer, 90, step=5)
    assert actuators.calls == [], "no valve is asked again while it opens"
    assert not_responding(hass) == [], "nor reported while its opening time and retries last"

    await async_advance(hass, freezer, 20, step=5)
    assert actuators.shorts() == ["valve.den:on"], "the valve that never arrives is retried"
    assert not_responding(hass) == ["valve.den"]
    assert hass.states.get("switch.pump").state == "off", (
        "the pump waits for the opening time after the study valve shows open"
    )
    await async_advance(hass, freezer, 100, step=5)
    assert "switch.pump:on" in actuators.shorts()

    hass.states.async_set("valve.den", "open")
    await hass.async_block_till_done()
    assert not_responding(hass) == [], "the Repair clears once the valve arrives"


async def test_a_changeover_sets_the_source_mode_before_the_request(
    hass: HomeAssistant, actuators: Actuators, freezer: FrozenDateTimeFactory
) -> None:
    """The source's mode select shows Heat while heating, so cooling first selects Cool."""
    plant = REFERENCE_PLANT.replace("mode_dwell: 3600", "mode_dwell: 60")
    await async_heat_living_area(hass, freezer, plant)
    assert hass.states.get(SOURCE_MODE).state == "Heat"
    actuators.clear()

    await async_call(hass, "select", "select_option", entity_id="select.home_mode", option="cool")
    await async_call(
        hass, "climate", "set_hvac_mode", entity_id="climate.living_area", hvac_mode="cool"
    )
    set_zone_temperature(hass, "living_area", 26.0)
    set_temperature(hass, "sensor.ceiling_supply_temperature", 20.0)
    await async_advance(hass, freezer, 200, step=5)
    assert hass.states.get("sensor.home_status").state == "changing_over"
    # The request is held for its minimum on time, then the post-run and the dwell pass.
    await async_advance(hass, freezer, 1000, step=5)

    shorts = actuators.shorts()
    assert [call.data for call in actuators.to(SOURCE_MODE)] == [{"option": "Cool"}]
    assert hass.states.get(SOURCE_MODE).state == "Cool"
    assert shorts.index(f"{SOURCE_MODE}:=Cool") < shorts.index(f"{SOURCE_REQUEST}:on")
    assert hass.states.get("sensor.home_status").state == "cooling"


@pytest.mark.parametrize(
    ("unit", "minimum", "maximum", "expected"),
    [("°C", 5.0, 60.0, 35.0), ("°F", 41.0, 140.0, 95.0), ("K", 278.15, 333.15, 308.15)],
)
def test_temperature_setpoint_service_uses_the_number_unit(
    unit: str, minimum: float, maximum: float, expected: float
) -> None:
    from homeassistant.core import State

    from custom_components.hydronicus.core.model import NumericTarget
    from custom_components.hydronicus.core.reconcile import Action
    from custom_components.hydronicus.dispatch import service_call

    state = State(
        "number.supply", "25", {"unit_of_measurement": unit, "min": minimum, "max": maximum}
    )
    domain, service, data = service_call(Action("number.supply", NumericTarget(35.0)), state)
    assert (domain, service) == ("number", "set_value")
    assert data == {"entity_id": "number.supply", "value": pytest.approx(expected)}


@pytest.mark.parametrize(
    "attributes",
    [
        {},
        {"unit_of_measurement": "W", "min": 0, "max": 100},
        {"unit_of_measurement": ["°C"], "min": 0, "max": 100},
        {"unit_of_measurement": "°C", "min": 5, "max": 30},
        {"unit_of_measurement": "°C", "min": "invalid", "max": 60},
        {"unit_of_measurement": "°C", "min": 5, "max": float("inf")},
    ],
)
def test_temperature_setpoint_refuses_unknown_or_incompatible_bounds(
    attributes: dict[str, object],
) -> None:
    from homeassistant.core import State

    from custom_components.hydronicus.core.model import NumericTarget
    from custom_components.hydronicus.core.reconcile import Action
    from custom_components.hydronicus.dispatch import service_call

    action = Action("number.supply", NumericTarget(35.0))
    with pytest.raises(ValueError):
        service_call(action, State("number.supply", "25", attributes))
    with pytest.raises(ValueError):
        service_call(action)


async def test_disarm_is_checked_before_send_even_before_the_next_evaluation(
    hass: HomeAssistant, actuators: Actuators, valves: ValveServices
) -> None:
    from custom_components.hydronicus.const import OPTION_ARMED_OUTPUTS

    entry = await async_flat(hass, "den", "study")
    valves.hold("valve.den")
    control_on(hass, entry)
    await async_until(lambda: valves.waiting)
    armed = set(entry.options[OPTION_ARMED_OUTPUTS]) - {"valve.study"}
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, OPTION_ARMED_OUTPUTS: sorted(armed)}
    )
    valves.release("valve.den")
    await hass.async_block_till_done()
    assert "valve.study:on" not in actuators.shorts()


async def test_control_off_drops_an_obsolete_queued_start(
    hass: HomeAssistant, actuators: Actuators, valves: ValveServices
) -> None:
    """Orderly shutdown must not send a queued start that the new safe plan no longer wants."""
    from custom_components.hydronicus.core.model import SwitchTarget

    entry = await async_flat(hass, "den", "study")
    valves.hold("valve.den")
    control_on(hass, entry)
    await async_until(lambda: valves.waiting)
    hass.config_entries.async_update_entry(entry, options={**entry.options, OPTION_CONTROL: False})
    await async_until(
        lambda: entry.runtime_data.view.desired.outputs["valve.study"] == SwitchTarget(False)
    )
    valves.release("valve.den")
    await hass.async_block_till_done()
    assert "valve.study:on" not in actuators.shorts()
