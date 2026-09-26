"""Shared builders for the Home Assistant integration tests.

``Actuators`` stands in for the devices behind the Plant's outputs: it records
every call to them and changes their state as a device would, unless the test
makes one ignore its calls. The reference plant of the redesign plan gets its areas and
sensors from ``reference_world``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.hydronicus.const import DOMAIN, OPTION_ARMED_OUTPUTS, OPTION_CONTROL
from custom_components.hydronicus.core.plant_file import read_plant_file

FIXTURES = Path(__file__).parents[1] / "fixtures"
REFERENCE_PLANT = (FIXTURES / "reference_plant.yaml").read_text(encoding="utf-8")
REFERENCE_PLANT_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
REFERENCE_AREAS = {
    "basement": "Basement",
    "workshop": "Workshop",
    "main_bedroom": "Main bedroom",
    "lilla_bedroom": "Lilla bedroom",
    "living_room": "Living room",
    "dining_room": "Dining room",
    "kitchen": "Kitchen",
    "hallway": "Hallway",
}
REFERENCE_ZONES = {
    "basement": ("basement", "workshop"),
    "bedroom_area": ("main_bedroom", "lilla_bedroom"),
    "living_area": ("living_room", "dining_room", "kitchen", "hallway"),
}
SOURCE_REQUEST = "switch.heat_pump_heat_request"
SOURCE_MODE = "select.heat_pump_mode"
FLOOR_PUMP = "switch.home_underfloor_heating_pump"
TOWEL_PUMP = "switch.home_bathrooms_towel_dryer_pump"
LIVING_CEILING = "switch.home_living_area_ceiling_heating_valve"
LIVING_FLOOR = "switch.home_living_area_floor_heating_valve"
BASEMENT_CEILING = "switch.home_basement_ceiling_heating_valve"
BEDROOM_CEILING = "switch.home_bedroom_area_ceiling_heating_valve"
SUPPLY = "sensor.ceiling_supply_temperature"
REFERENCE_OUTPUTS = tuple(read_plant_file(REFERENCE_PLANT).outputs())


@dataclass(frozen=True, slots=True)
class Call:
    """One service call an actuator received."""

    domain: str
    service: str
    entity_id: str
    data: Mapping[str, Any] = field(default_factory=dict)
    # When it was made, as a POSIX timestamp.
    at: float = 0.0

    @property
    def short(self) -> str:
        """The call as ``entity:on``, ``entity:off``, or ``entity:=option``."""
        if "option" in self.data:
            return f"{self.entity_id}:={self.data['option']}"
        on = self.service in ("turn_on", "open_valve")
        return f"{self.entity_id}:{'on' if on else 'off'}"


class Actuators:
    """Devices behind the Plant's outputs, which follow the service calls they receive.

    The outputs are plain states without entity objects, so the real switch and
    select services, which the Plant's own entities load, find nothing to act on.
    Every call is seen as it is made, recorded, and applied to the state, as a
    device would apply it, unless the test makes the output ignore its calls.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.calls: list[Call] = []
        # Entities whose calls return without acting.
        self.ignoring: set[str] = set()
        hass.bus.async_listen(EVENT_CALL_SERVICE, self._handle)

    @callback
    def _handle(self, event: Event[Any]) -> None:
        domain, service = event.data["domain"], event.data["service"]
        if domain not in ("switch", "valve", "select"):
            return
        entity_ids = event.data["service_data"].get("entity_id", [])
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        registry = er.async_get(self.hass)
        for entity_id in entity_ids:
            if registry.async_get(entity_id) is not None:
                continue
            data = {k: v for k, v in event.data["service_data"].items() if k != "entity_id"}
            self.calls.append(Call(domain, service, entity_id, data, dt_util.utcnow().timestamp()))
            if entity_id in self.ignoring:
                continue
            current = self.hass.states.get(entity_id)
            attributes = dict(current.attributes) if current is not None else {}
            match service:
                case "turn_on":
                    state = "on"
                case "turn_off":
                    state = "off"
                case "open_valve":
                    state = "open"
                case "close_valve":
                    state = "closed"
                case _:
                    state = str(data["option"])
            self.hass.states.async_set(entity_id, state, attributes)

    def to(self, entity_id: str) -> list[Call]:
        return [call for call in self.calls if call.entity_id == entity_id]

    def shorts(self) -> list[str]:
        return [call.short for call in self.calls]

    def clear(self) -> None:
        self.calls.clear()


def set_temperature(hass: HomeAssistant, entity_id: str, value: float) -> None:
    hass.states.async_set(
        entity_id,
        str(value),
        {"device_class": "temperature", "unit_of_measurement": "°C"},
        force_update=True,
    )


def set_humidity(hass: HomeAssistant, entity_id: str, value: float) -> None:
    hass.states.async_set(
        entity_id,
        str(value),
        {"device_class": "humidity", "unit_of_measurement": "%"},
        force_update=True,
    )


def create_area(
    hass: HomeAssistant, name: str, *, temperature: str | None = None, humidity: str | None = None
) -> ar.AreaEntry:
    return ar.async_get(hass).async_create(
        name, temperature_entity_id=temperature, humidity_entity_id=humidity
    )


def reference_world(
    hass: HomeAssistant,
    *,
    temperature: float = 21.0,
    on: Iterable[str] = (),
    mode_option: str = "Heat",
) -> None:
    """Create the reference plant's areas, sensors, and outputs; outputs are off unless ``on``."""
    for area_id, name in REFERENCE_AREAS.items():
        set_temperature(hass, f"sensor.{area_id}_temperature", temperature)
        set_humidity(hass, f"sensor.{area_id}_humidity", 50.0)
        create_area(
            hass,
            name,
            temperature=f"sensor.{area_id}_temperature",
            humidity=f"sensor.{area_id}_humidity",
        )
    set_temperature(hass, SUPPLY, 35.0)
    running = set(on)
    for entity_id in REFERENCE_OUTPUTS:
        if entity_id == SOURCE_MODE:
            hass.states.async_set(entity_id, mode_option, {"options": ["Heat", "Cool"]})
        else:
            hass.states.async_set(entity_id, "on" if entity_id in running else "off")


def set_zone_temperature(hass: HomeAssistant, zone: str, value: float) -> None:
    for area_id in REFERENCE_ZONES[zone]:
        set_temperature(hass, f"sensor.{area_id}_temperature", value)


async def async_submit(manager: Any, result: Mapping[str, Any], data: Any = None) -> Any:
    """Submit a flow's form, with nothing when ``data`` is None."""
    assert result["type"] is FlowResultType.FORM, result
    return await manager.async_configure(result["flow_id"], {} if data is None else data)


async def async_choose(manager: Any, result: Mapping[str, Any], option: str) -> Any:
    """Choose an option of a flow's menu."""
    assert result["type"] is FlowResultType.MENU, result
    assert option in result["menu_options"], (option, result["menu_options"])
    return await manager.async_configure(result["flow_id"], {"next_step_id": option})


def suggested(result: Mapping[str, Any], field: str) -> Any:
    """Return what a form shows in a field: its suggested value, or its default."""
    for key in result["data_schema"].schema:
        if str(key) != field:
            continue
        description = getattr(key, "description", None)
        if isinstance(description, Mapping) and "suggested_value" in description:
            return description["suggested_value"]
        default = getattr(key, "default", None)
        return default() if callable(default) else None
    raise AssertionError(f"{field} is not a field of {result.get('step_id')}")


def fields(result: Mapping[str, Any]) -> set[str]:
    """Return the fields a form shows."""
    return {str(key) for key in result["data_schema"].schema}


async def async_import(hass: HomeAssistant, text: str) -> ConfigEntry:
    """Create a Plant through the config flow from plant file text and wait for it."""
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": "user"})
    result = await async_choose(flow, result, "import_plant")
    result = await async_submit(flow, result, {"plant_file": text})
    assert result.get("step_id") == "review", result.get("errors")
    result = await async_submit(flow, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY, result.get("errors")
    await hass.async_block_till_done()
    entry = result["result"]
    assert isinstance(entry, ConfigEntry)
    return entry


def zone_subentry_id(entry: ConfigEntry, slug: str) -> str:
    """Return the ID of a zone's subentry."""
    for subentry in entry.subentries.values():
        if subentry.unique_id == slug:
            return subentry.subentry_id
    raise AssertionError(f"no zone {slug}")


def stored(entry: ConfigEntry) -> tuple[dict[str, Any], dict[str, tuple[str, dict[str, Any]]]]:
    """Return a Plant as stored: its entry data and each zone's title and data by slug."""
    return dict(entry.data), {
        str(subentry.unique_id): (subentry.title, dict(subentry.data))
        for subentry in entry.subentries.values()
    }


async def async_set_options(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    armed: Iterable[str] | None = None,
    control: bool | None = None,
) -> None:
    """Arm outputs and switch Control equipment, as Plant settings will."""
    options = dict(entry.options)
    if armed is not None:
        options[OPTION_ARMED_OUTPUTS] = list(armed)
    if control is not None:
        options[OPTION_CONTROL] = control
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.async_block_till_done()


async def async_call(hass: HomeAssistant, domain: str, service: str, **data: Any) -> None:
    await hass.services.async_call(domain, service, data, blocking=True)
    await hass.async_block_till_done()


async def async_advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float, step: float = 1.0
) -> None:
    """Let ``seconds`` pass in steps, running every timer and evaluation that falls due."""
    remaining = seconds
    while remaining > 1e-9:
        delta = min(step, remaining)
        freezer.tick(timedelta(seconds=delta))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        remaining -= delta


def entity_id_of(hass: HomeAssistant, domain: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return entity_id


def plant_entities(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str]:
    """Return every registered entity of a Plant, by unique ID."""
    registry = er.async_get(hass)
    return {
        str(entity.unique_id): entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


RUNNING = {LIVING_CEILING, LIVING_FLOOR, FLOOR_PUMP, SOURCE_REQUEST, TOWEL_PUMP}


async def async_heat_living_area(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, text: str = REFERENCE_PLANT
) -> ConfigEntry:
    """Set the reference plant up and let the living area heat until everything runs."""
    reference_world(hass)
    entry = await async_import(hass, text)
    await async_set_options(hass, entry, armed=read_plant_file(text).outputs(), control=True)
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
    assert {e for e in REFERENCE_OUTPUTS if hass.states.get(e).state == "on"} == RUNNING
    return entry


def restart_states(hass: HomeAssistant, entity_ids: set[str]) -> None:
    """Write every state again as a Home Assistant restart does, which resets last_changed."""
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        hass.states.async_remove(entity_id)
        hass.states.async_set(entity_id, state.state, dict(state.attributes))
