"""Conditional entities, their registry cleanup, and device naming."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import patch

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import CONF_TOPOLOGY, DOMAIN
from tests.integration.plant_fixtures import (
    MANIFOLD_PUMP_ENTITY,
    MANIFOLD_PUMP_ID,
    PLANT_ID,
    manifold_rooms,
    manifold_topology,
    plant_data,
    plant_entry,
    room_subentry,
)

LIVING, BEDROOM = manifold_rooms(("Living room", "Bedroom"))
LIVING_HUMIDITY = "sensor.living_room_humidity"
LIVING_SUPPLY = "sensor.living_room_supply"

ROOM_COOLING_ENTITIES = (
    ("binary_sensor", "cooling_demand"),
    ("binary_sensor", "cooling_blocked"),
    ("sensor", "cooling_blocked_reason"),
    ("sensor", "dew_point"),
    ("sensor", "condensation_margin"),
)
ROOM_HEATING_ENTITIES = (
    ("climate", "climate"),
    ("binary_sensor", "demand"),
    ("binary_sensor", "blocked"),
    ("sensor", "explanation"),
    ("sensor", "aggregate_temperature"),
    ("sensor", "blocked_reason"),
)
PLANT_SOURCE_ENTITIES = (
    "active_source",
    "recommended_source",
    "source_changeover",
    "source_dwell",
    "source_recommendation",
)


def _topology(*, living_cools: bool) -> dict[str, Any]:
    """Return the manifold with an optional cooling loop for the living room."""
    topology = manifold_topology(("Living room", "Bedroom"))
    topology["zones"][0]["humidity_sensor_metadata"] = [{"entity_id": LIVING_HUMIDITY}]
    circuit = topology["circuits"][0]
    circuit["supply_temperature_sensor"] = LIVING_SUPPLY
    circuit["cooling_enabled"] = living_cools
    return topology


def _set_states(hass) -> None:
    for room in (LIVING, BEDROOM):
        hass.states.async_set(room.temperature_sensor, "22.0")
        hass.states.async_set(room.valve_entity, "off")
    hass.states.async_set(LIVING_HUMIDITY, "50.0")
    hass.states.async_set(LIVING_SUPPLY, "18.0")
    hass.states.async_set(MANIFOLD_PUMP_ENTITY, "off")


async def _setup(hass, *, living_cools: bool = True) -> MockConfigEntry:
    _set_states(hass)
    entry = plant_entry(plant_data(_topology(living_cools=living_cools)))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _registered(hass, domain: str, unique_id: str) -> er.RegistryEntry | None:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    return registry.async_get(entity_id) if entity_id is not None else None


def _room_entities(zone_id: str, entities: tuple[tuple[str, str], ...]) -> list[tuple[str, str]]:
    return [(domain, f"{PLANT_ID}_{zone_id}_{suffix}") for domain, suffix in entities]


async def _set_living_cooling(hass, entry: MockConfigEntry, *, enabled: bool) -> None:
    """Store a graph edit that turns the living room loop's cooling on or off."""
    data = deepcopy(dict(entry.data))
    data[CONF_TOPOLOGY]["circuits"][0]["cooling_enabled"] = enabled
    hass.config_entries.async_update_entry(entry, data=data)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_cooling_entities_exist_only_for_rooms_that_can_cool(hass) -> None:
    """A room gets cooling entities exactly when its thermostat offers cool modes."""
    await _setup(hass)

    for domain, unique_id in _room_entities(LIVING.zone_id, ROOM_COOLING_ENTITIES):
        assert _registered(hass, domain, unique_id) is not None, unique_id
    for domain, unique_id in _room_entities(BEDROOM.zone_id, ROOM_COOLING_ENTITIES):
        assert _registered(hass, domain, unique_id) is None, unique_id
    for zone_id in (LIVING.zone_id, BEDROOM.zone_id):
        for domain, unique_id in _room_entities(zone_id, ROOM_HEATING_ENTITIES):
            assert _registered(hass, domain, unique_id) is not None, unique_id

    assert HVACMode.COOL in hass.states.get("climate.living_room").attributes["hvac_modes"]
    assert hass.states.get("climate.bedroom").attributes["hvac_modes"] == [
        HVACMode.OFF,
        HVACMode.HEAT,
    ]


async def test_source_entities_exist_only_for_a_plant_with_a_source(hass) -> None:
    """A Plant without a source has no source selection entities to show."""
    await _setup(hass)

    for suffix in PLANT_SOURCE_ENTITIES:
        assert _registered(hass, "sensor", f"{PLANT_ID}_{suffix}") is None, suffix
    assert _registered(hass, "sensor", f"{PLANT_ID}_operating_mode") is not None


async def test_topology_devices_take_the_object_name_alone(hass) -> None:
    """Room and equipment devices drop the Plant name, and the Plant device keeps it."""
    entry = await _setup(hass)
    devices = dr.async_get(hass)

    def name(identifier: str) -> str | None:
        device = devices.async_get_device_by_identifier((DOMAIN, identifier), entry.entry_id)
        assert device is not None, identifier
        return device.name

    assert name(PLANT_ID) == "Hydronic plant"
    assert name(f"{PLANT_ID}:zone:{LIVING.zone_id}") == "Living room"
    assert name(f"{PLANT_ID}:pump:{MANIFOLD_PUMP_ID}") == "Manifold pump"
    assert name(f"{PLANT_ID}:valve:{LIVING.valve_id}") == "Living room loop valve"
    assert hass.states.get("climate.living_room").name == "Living room"
    assert hass.states.get("binary_sensor.bedroom_heating_demand").name == "Bedroom Heating demand"


async def test_turning_cooling_off_removes_only_the_cooling_entities(hass) -> None:
    """A reload removes the entities nothing provides and keeps every other registration."""
    entry = await _setup(hass)
    registry = er.async_get(hass)
    living_subentry = room_subentry(entry, LIVING.zone_id).subentry_id
    # A user customization on a room entity that stays must survive the cleanup.
    demand = _registered(hass, "binary_sensor", f"{PLANT_ID}_{LIVING.zone_id}_demand")
    assert demand is not None
    registry.async_update_entity(demand.entity_id, name="Living heat call")
    kept = {
        registry_entry.entity_id: registry_entry.id
        for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
        if not registry_entry.unique_id.endswith(
            tuple(f"_{suffix}" for _domain, suffix in ROOM_COOLING_ENTITIES)
        )
    }
    cooling = [
        _registered(hass, domain, unique_id)
        for domain, unique_id in _room_entities(LIVING.zone_id, ROOM_COOLING_ENTITIES)
    ]
    assert all(
        registry_entry is not None and registry_entry.config_subentry_id == living_subentry
        for registry_entry in cooling
    )

    await _set_living_cooling(hass, entry, enabled=False)

    for registry_entry in cooling:
        assert registry_entry is not None
        assert registry.async_get(registry_entry.entity_id) is None, registry_entry.entity_id
        assert hass.states.get(registry_entry.entity_id) is None, registry_entry.entity_id
    remaining = {
        registry_entry.entity_id: registry_entry.id
        for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert remaining == kept
    demand = registry.async_get(demand.entity_id)
    assert demand is not None
    assert (demand.name, demand.config_subentry_id) == ("Living heat call", living_subentry)
    assert hass.states.get("climate.living_room").attributes["hvac_modes"] == [
        HVACMode.OFF,
        HVACMode.HEAT,
    ]

    # Turning cooling back on provides the cooling entities again.
    await _set_living_cooling(hass, entry, enabled=True)
    for domain, unique_id in _room_entities(LIVING.zone_id, ROOM_COOLING_ENTITIES):
        registry_entry = _registered(hass, domain, unique_id)
        assert registry_entry is not None, unique_id
        assert registry_entry.config_subentry_id == living_subentry


async def test_setup_removes_stale_entries_of_the_parent_and_of_room_subentries(hass) -> None:
    """Stale registrations from an earlier graph go at setup, wherever they were owned."""
    _set_states(hass)
    entry = plant_entry(plant_data(_topology(living_cools=False)))
    entry.add_to_hass(hass)
    other = MockConfigEntry(domain=DOMAIN, title="Other plant", data={})
    other.add_to_hass(hass)
    registry = er.async_get(hass)
    stale_room = registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{PLANT_ID}_{BEDROOM.zone_id}_cooling_demand",
        config_entry=entry,
        config_subentry_id=room_subentry(entry, BEDROOM.zone_id).subentry_id,
    )
    stale_plant = registry.async_get_or_create(
        "sensor", DOMAIN, f"{PLANT_ID}_source_dwell", config_entry=entry
    )
    foreign = registry.async_get_or_create(
        "sensor", DOMAIN, "other_plant_source_dwell", config_entry=other
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get(stale_room.entity_id) is None
    assert registry.async_get(stale_plant.entity_id) is None
    assert registry.async_get(foreign.entity_id) is not None


async def test_a_disabled_entity_still_counts_as_provided(hass) -> None:
    """Disabling an entity is a registry choice that a reload keeps."""
    entry = await _setup(hass)
    registry = er.async_get(hass)
    dew_point = _registered(hass, "sensor", f"{PLANT_ID}_{LIVING.zone_id}_dew_point")
    assert dew_point is not None
    registry.async_update_entity(dew_point.entity_id, disabled_by=er.RegistryEntryDisabler.USER)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    kept = registry.async_get(dew_point.entity_id)
    assert kept is not None
    assert kept.disabled_by is er.RegistryEntryDisabler.USER


async def test_a_platform_that_fails_to_set_up_keeps_its_registrations(hass) -> None:
    """Only platforms that provided their entities in this setup are cleaned."""
    _set_states(hass)
    entry = plant_entry(plant_data(_topology(living_cools=False)))
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "sensor", DOMAIN, f"{PLANT_ID}_source_dwell", config_entry=entry
    )

    async def fail(*_args: Any) -> None:
        raise RuntimeError("sensor platform failed")

    with patch("custom_components.hydronicus.sensor.async_setup_entry", fail):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert registry.async_get(stale.entity_id) is not None
    # The other platforms were still cleaned against what they provided.
    assert hass.states.get("climate.living_room") is not None


async def test_a_room_never_reads_its_own_entity_as_an_observation(hass) -> None:
    """A room Temperature that takes a missing sensor's entity ID is not read back."""
    for room in (LIVING, BEDROOM):
        hass.states.async_set(room.valve_entity, "off")
    hass.states.async_set(BEDROOM.temperature_sensor, "22.0")
    hass.states.async_set(MANIFOLD_PUMP_ENTITY, "off")
    entry = plant_entry(plant_data(manifold_topology(("Living room", "Bedroom"))))
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # The room sensor did not exist, so the room's own Temperature took its entity ID.
    own = _registered(hass, "sensor", f"{PLANT_ID}_{LIVING.zone_id}_aggregate_temperature")
    assert own is not None
    assert own.entity_id == LIVING.temperature_sensor
    runtime = entry.runtime_data
    assert runtime.zone_is_blocked(LIVING.zone_id)
    assert LIVING.temperature_sensor in runtime.unavailable_entity_ids
    assert any(
        issue.translation_key == "missing_sensor_binding_fixable"
        for issue in ir.async_get(hass).issues.values()
        if issue.domain == DOMAIN
    )
