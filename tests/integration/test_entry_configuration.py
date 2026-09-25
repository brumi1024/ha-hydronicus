"""Tests for the version 4 Plant graph, its edit API, and output authorization."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_OUTPUT_AUTHORIZATION,
    CONF_SUBENTRY_OBJECTS,
    CONF_ZONE_OBJECTS,
)
from custom_components.hydronicus.core.configuration import StoredTopologyError
from custom_components.hydronicus.core.ownership import OwnershipError, PlantOwnership
from custom_components.hydronicus.core.topology import TopologyValidationError
from custom_components.hydronicus.entry_configuration import (
    EquipmentInUseError,
    SubentrySync,
    ZoneDraft,
    authorize_outputs,
    data_with_plant,
    data_with_pump,
    data_with_zone,
    effective_plant,
    effective_plant_from_data,
    invalidate_output_authorization,
    new_plant_data,
    output_authorization,
    output_authorization_is_valid,
    reconcile_removed_subentries,
    runtime_configuration_fingerprint,
    subentries_for,
    subentry_sync,
    zone_draft,
)
from custom_components.hydronicus.flows.common import async_persist_entry_data
from tests.integration.plant_fixtures import (
    MANIFOLD_PUMP_ID,
    PLANT_ID,
    manifold_entry,
    manifold_topology,
    manifold_zones,
    plant_data,
    plant_entry,
    subentry_id_for,
)

LIVING, BEDROOM = manifold_zones(("Living room", "Bedroom"))
SOURCE_ID = "00000000-0000-4000-8000-000000000007"
OFFICE_ZONE = "00000000-0000-4000-8000-0000000000a1"
OFFICE_LOOP = "00000000-0000-4000-8000-0000000000a2"
OFFICE_VALVE = "00000000-0000-4000-8000-0000000000a3"
OFFICE_ROUTE = "00000000-0000-4000-8000-0000000000a4"
SECOND_PUMP = "00000000-0000-4000-8000-0000000000b1"
BOILER = {
    "id": SOURCE_ID,
    "name": "Boiler",
    "source_type": "external",
    "source_demand_entity": "switch.boiler_demand",
}


def _data(**kwargs: Any) -> dict[str, Any]:
    return plant_data(manifold_topology(sources=[BOILER]), **kwargs)


def _office() -> ZoneDraft:
    return ZoneDraft(
        zone={
            "id": OFFICE_ZONE,
            "name": "Office",
            "thermostat": {"kind": "hydronicus", "initial_target_temperature": 20.0},
            "temperature_sensor_metadata": [{"entity_id": "sensor.office_temperature"}],
        },
        circuits=[
            {
                "id": OFFICE_LOOP,
                "name": "Office loop",
                "valve_ids": [OFFICE_VALVE],
                "pump_id": MANIFOLD_PUMP_ID,
            }
        ],
        valves=[{"id": OFFICE_VALVE, "name": "Office valve", "entity_id": "switch.office_valve"}],
        routes=[{"id": OFFICE_ROUTE, "zone_id": OFFICE_ZONE, "circuit_id": OFFICE_LOOP}],
    )


def _kitchen_topology() -> tuple[Any, dict[str, Any]]:
    """Return a third zone, alone on the manifold pump, with the boiler."""
    names = ("Living room", "Bedroom", "Kitchen")
    kitchen = manifold_zones(names)[2]
    topology = manifold_topology(names, sources=[BOILER])
    kept = {kitchen.zone_id, kitchen.circuit_id, kitchen.valve_id, kitchen.route_id}
    for collection in ("zones", "circuits", "valves", "routes"):
        topology[collection] = [record for record in topology[collection] if record["id"] in kept]
    return kitchen, topology


def _ids(data: dict[str, Any], collection: str) -> list[str]:
    return [record["id"] for record in data["topology"][collection]]


def test_output_authorization_is_bound_to_the_exact_graph_and_outputs() -> None:
    """Any physical binding change invalidates the stored activation grant."""
    data = _data()
    authorization = output_authorization(data)

    assert authorization["outputs"] == [
        {"kind": "pump", "id": MANIFOLD_PUMP_ID, "entity_id": "switch.manifold_pump"},
        {"kind": "source_demand", "id": SOURCE_ID, "entity_id": "switch.boiler_demand"},
        {"kind": "valve", "id": LIVING.valve_id, "entity_id": LIVING.valve_entity},
        {"kind": "valve", "id": BEDROOM.valve_id, "entity_id": BEDROOM.valve_entity},
    ]
    active = authorize_outputs(data)
    assert active[CONF_DRY_RUN] is False
    assert output_authorization_is_valid(active)
    changed = deepcopy(active)
    changed["topology"]["valves"][0]["entity_id"] = "switch.other_valve"
    assert not output_authorization_is_valid(changed)


def test_new_plant_data_gives_every_zone_and_source_a_handle() -> None:
    """New Plant data is version 4 data in Dry run with its zone ownership."""
    data = _data()

    assert data[CONF_DRY_RUN] is True
    assert CONF_OUTPUT_AUTHORIZATION not in data
    assert data[CONF_SUBENTRY_OBJECTS] == {
        LIVING.zone_id: "zone",
        BEDROOM.zone_id: "zone",
        SOURCE_ID: "source",
    }
    assert data[CONF_ZONE_OBJECTS] == {
        LIVING.circuit_id: LIVING.zone_id,
        BEDROOM.circuit_id: BEDROOM.zone_id,
        LIVING.valve_id: LIVING.zone_id,
        BEDROOM.valve_id: BEDROOM.zone_id,
    }
    assert subentries_for(data) == [
        {
            "data": {"id": LIVING.zone_id},
            "subentry_type": "zone",
            "title": "Living room",
            "unique_id": LIVING.zone_id,
        },
        {
            "data": {"id": BEDROOM.zone_id},
            "subentry_type": "zone",
            "title": "Bedroom",
            "unique_id": BEDROOM.zone_id,
        },
        {
            "data": {"id": SOURCE_ID},
            "subentry_type": "source",
            "title": "Boiler",
            "unique_id": SOURCE_ID,
        },
    ]


def test_new_plant_data_rejects_ownership_that_is_not_deletion_closed() -> None:
    """A zone cannot own a loop another zone routes to."""
    topology = manifold_topology()
    topology["routes"].append(
        {
            "id": "00000000-0000-4000-8000-0000000000c1",
            "zone_id": BEDROOM.zone_id,
            "circuit_id": LIVING.circuit_id,
        }
    )
    ownership = PlantOwnership(zone_objects={LIVING.circuit_id: LIVING.zone_id})

    with pytest.raises(OwnershipError) as error:
        new_plant_data(name="Plant", plant_id=PLANT_ID, topology=topology, ownership=ownership)

    assert LIVING.circuit_id in error.value.object_ids


def test_effective_plant_maps_zone_objects_to_their_zone_subentry() -> None:
    """Zones, private loops and valves, and sources resolve to their handle subentry."""
    entry = plant_entry(_data())

    plant = effective_plant(entry)

    living = subentry_id_for(LIVING.zone_id)
    assert plant.object_subentry_ids == {
        LIVING.zone_id: living,
        LIVING.circuit_id: living,
        LIVING.valve_id: living,
        BEDROOM.zone_id: subentry_id_for(BEDROOM.zone_id),
        BEDROOM.circuit_id: subentry_id_for(BEDROOM.zone_id),
        BEDROOM.valve_id: subentry_id_for(BEDROOM.zone_id),
        SOURCE_ID: subentry_id_for(SOURCE_ID),
    }
    assert set(plant.compiled.zones) == {LIVING.zone_id, BEDROOM.zone_id}
    assert effective_plant_from_data(entry.data).object_subentry_ids == {}


def test_a_plant_owned_source_needs_no_subentry() -> None:
    """A source without a handle belongs to the Plant and stays valid."""
    data = _data()
    del data[CONF_SUBENTRY_OBJECTS][SOURCE_ID]
    entry = plant_entry(data)
    assert len(entry.subentries) == 2

    plant = effective_plant(entry)

    assert SOURCE_ID in plant.compiled.sources
    assert SOURCE_ID not in plant.object_subentry_ids


@pytest.mark.parametrize(
    ("change", "message"),
    [
        pytest.param(
            lambda data: data[CONF_SUBENTRY_OBJECTS].pop(BEDROOM.zone_id),
            "Zones without a zone handle",
            id="zone_without_handle",
        ),
        pytest.param(
            lambda data: data[CONF_SUBENTRY_OBJECTS].update({LIVING.valve_id: "zone"}),
            "does not name a stored zone",
            id="zone_handle_on_valve",
        ),
        pytest.param(
            lambda data: data[CONF_SUBENTRY_OBJECTS].update({BEDROOM.zone_id: "room"}),
            "unsupported type 'room'",
            id="unsupported_handle_type",
        ),
    ],
)
def test_readers_reject_inconsistent_handles(change, message: str) -> None:
    """Every zone has exactly one zone handle, and only zone and source handles exist."""
    data = _data()
    change(data)

    with pytest.raises(StoredTopologyError, match=message):
        effective_plant_from_data(data)


def test_effective_plant_rejects_a_handle_without_its_subentry() -> None:
    """Outside reconciliation, a recorded handle must have its subentry."""
    entry = plant_entry(_data())
    subentries = {
        subentry_id: subentry
        for subentry_id, subentry in entry.subentries.items()
        if subentry.unique_id != BEDROOM.zone_id
    }

    with pytest.raises(StoredTopologyError, match="without a config subentry"):
        effective_plant(SimpleNamespace(data=entry.data, subentries=subentries))


def test_zone_draft_round_trips_and_edits_a_zone_in_place() -> None:
    """A zone replaces exactly its own records and keeps the order of the rest."""
    data = authorize_outputs(_data())
    draft = zone_draft(data, BEDROOM.zone_id)

    assert draft.zone["name"] == "Bedroom"
    assert [circuit["id"] for circuit in draft.circuits] == [BEDROOM.circuit_id]
    assert [valve["id"] for valve in draft.valves] == [BEDROOM.valve_id]
    assert [route["id"] for route in draft.routes] == [BEDROOM.route_id]
    assert data_with_zone(data, draft) == invalidate_output_authorization(data)

    renamed = replace(draft, zone={**draft.zone, "name": "Guest room"})
    extra_valve = {"id": OFFICE_VALVE, "name": "Second valve", "entity_id": "switch.second"}
    edited = replace(
        renamed,
        valves=[*draft.valves, extra_valve],
        circuits=[{**draft.circuits[0], "valve_ids": [BEDROOM.valve_id, OFFICE_VALVE]}],
    )
    updated = data_with_zone(data, edited)

    assert updated[CONF_DRY_RUN] is True
    assert CONF_OUTPUT_AUTHORIZATION not in updated
    assert _ids(updated, "zones") == [LIVING.zone_id, BEDROOM.zone_id]
    assert updated["topology"]["zones"][1]["name"] == "Guest room"
    assert _ids(updated, "valves") == [LIVING.valve_id, BEDROOM.valve_id, OFFICE_VALVE]
    assert updated[CONF_ZONE_OBJECTS][OFFICE_VALVE] == BEDROOM.zone_id


def test_data_with_zone_drops_private_objects_the_zone_no_longer_has() -> None:
    """A zone that switches to a shared loop takes its private loop and valve with it."""
    ownership = PlantOwnership(
        zone_objects={BEDROOM.circuit_id: BEDROOM.zone_id, BEDROOM.valve_id: BEDROOM.zone_id}
    )
    data = new_plant_data(
        name="Plant", plant_id=PLANT_ID, topology=manifold_topology(), ownership=ownership
    )
    draft = zone_draft(data, BEDROOM.zone_id)
    shared_route = {**draft.routes[0], "circuit_id": LIVING.circuit_id}

    updated = data_with_zone(data, replace(draft, circuits=[], valves=[], routes=[shared_route]))

    assert _ids(updated, "circuits") == [LIVING.circuit_id]
    assert _ids(updated, "valves") == [LIVING.valve_id]
    assert updated["topology"]["routes"][1] == shared_route
    assert updated[CONF_ZONE_OBJECTS] == {}


def test_data_with_zone_inserts_a_new_zone() -> None:
    """A new zone id adds a zone with its private loop and valve."""
    updated = data_with_zone(_data(), _office())

    assert _ids(updated, "zones")[-1] == OFFICE_ZONE
    assert updated[CONF_SUBENTRY_OBJECTS][OFFICE_ZONE] == "zone"
    assert updated[CONF_ZONE_OBJECTS][OFFICE_LOOP] == OFFICE_ZONE
    assert updated[CONF_ZONE_OBJECTS][OFFICE_VALVE] == OFFICE_ZONE
    assert subentries_for(updated)[-1]["title"] == "Office"


@pytest.mark.parametrize(
    ("edit", "error"),
    [
        pytest.param(
            lambda draft: replace(
                draft,
                routes=[{**draft.routes[0], "zone_id": LIVING.zone_id}],
            ),
            StoredTopologyError,
            id="route_from_another_zone",
        ),
        pytest.param(
            lambda draft: replace(
                draft,
                circuits=[{**draft.circuits[0], "id": LIVING.circuit_id}],
                routes=[{**draft.routes[0], "circuit_id": LIVING.circuit_id}],
            ),
            StoredTopologyError,
            id="takes_another_zones_loop",
        ),
        pytest.param(
            lambda draft: replace(
                draft,
                circuits=[{**draft.circuits[0], "valve_ids": [LIVING.valve_id]}],
                valves=[],
            ),
            OwnershipError,
            id="uses_another_zones_valve",
        ),
        pytest.param(
            lambda draft: replace(draft, routes=[]),
            OwnershipError,
            id="private_loop_without_route",
        ),
        pytest.param(
            lambda draft: replace(
                draft,
                circuits=[{**draft.circuits[0], "pump_id": SECOND_PUMP}],
            ),
            TopologyValidationError,
            id="unknown_pump",
        ),
    ],
)
def test_data_with_zone_rejects_invalid_zones(edit, error: type[Exception]) -> None:
    """A zone edit is validated against ownership and compiled before it is returned."""
    with pytest.raises(error):
        data_with_zone(_data(), edit(_office()))


def test_data_with_pump_adds_replaces_and_removes_plant_pumps() -> None:
    """Pumps are Plant equipment; one in use cannot be removed."""
    data = authorize_outputs(_data())
    pump = {"name": "Second pump", "entity_id": "switch.second_pump"}

    added = data_with_pump(data, SECOND_PUMP, pump)
    assert _ids(added, "pumps") == [MANIFOLD_PUMP_ID, SECOND_PUMP]
    assert added[CONF_DRY_RUN] is True
    assert CONF_OUTPUT_AUTHORIZATION not in added
    renamed = data_with_pump(added, SECOND_PUMP, {**pump, "name": "Spare pump"})
    assert renamed["topology"]["pumps"][1] == {"id": SECOND_PUMP, **pump, "name": "Spare pump"}
    assert _ids(data_with_pump(renamed, SECOND_PUMP, None), "pumps") == [MANIFOLD_PUMP_ID]

    with pytest.raises(EquipmentInUseError) as in_use:
        data_with_pump(added, MANIFOLD_PUMP_ID, None)
    assert in_use.value.users == ("Living room loop", "Bedroom loop")
    with pytest.raises(StoredTopologyError):
        data_with_pump(added, SECOND_PUMP, {"id": MANIFOLD_PUMP_ID, **pump})


@dataclass(frozen=True)
class _Imported:
    name: str
    topology: dict[str, Any]
    ownership: PlantOwnership


def test_data_with_plant_replaces_the_graph_and_gives_every_object_a_handle() -> None:
    """A plant file replaces name, topology, and ownership, and keeps the Plant id."""
    data = authorize_outputs(_data())
    kitchen, topology = _kitchen_topology()
    imported = _Imported(
        name="Imported",
        topology=topology,
        ownership=PlantOwnership(zone_objects={kitchen.circuit_id: kitchen.zone_id}),
    )

    updated = data_with_plant(data, imported)

    assert updated["name"] == "Imported"
    assert updated["plant_id"] == PLANT_ID
    assert updated["topology"]["zones"] == topology["zones"]
    assert updated[CONF_ZONE_OBJECTS] == {kitchen.circuit_id: kitchen.zone_id}
    assert updated[CONF_SUBENTRY_OBJECTS] == {kitchen.zone_id: "zone", SOURCE_ID: "source"}
    assert updated[CONF_DRY_RUN] is True
    assert CONF_OUTPUT_AUTHORIZATION not in updated


def test_subentry_sync_adds_and_retitles_handles() -> None:
    """A new zone gets a handle and a renamed zone gets its new title."""
    entry = plant_entry(_data())
    draft = zone_draft(entry.data, LIVING.zone_id)
    data = data_with_zone(entry.data, replace(draft, zone={**draft.zone, "name": "Lounge"}))
    data = data_with_zone(data, _office())

    assert subentry_sync(entry, data) == SubentrySync(
        add=[
            {
                "data": {"id": OFFICE_ZONE},
                "subentry_type": "zone",
                "title": "Office",
                "unique_id": OFFICE_ZONE,
            }
        ],
        remove=[],
        retitle=[(subentry_id_for(LIVING.zone_id), "Lounge")],
    )


def test_subentry_sync_matches_a_replaced_plant() -> None:
    """Zones that disappear are removed and new ones are added."""
    entry = plant_entry(_data())
    kitchen, topology = _kitchen_topology()
    imported = _Imported(
        name="Imported",
        topology=topology,
        ownership=PlantOwnership(zone_objects={}),
    )

    sync = subentry_sync(entry, data_with_plant(entry.data, imported))

    assert sync.add == [
        {
            "data": {"id": kitchen.zone_id},
            "subentry_type": "zone",
            "title": "Kitchen",
            "unique_id": kitchen.zone_id,
        }
    ]
    assert sorted(sync.remove) == sorted(
        [subentry_id_for(LIVING.zone_id), subentry_id_for(BEDROOM.zone_id)]
    )
    assert sync.retitle == []


def test_runtime_fingerprint_includes_zone_ownership() -> None:
    """Moving a loop between a zone and the Plant rebuilds the runtime."""
    entry = plant_entry(_data())
    moved = dict(entry.data)
    moved[CONF_ZONE_OBJECTS] = {
        key: value for key, value in entry.data[CONF_ZONE_OBJECTS].items() if key != LIVING.valve_id
    }

    assert runtime_configuration_fingerprint(entry) != runtime_configuration_fingerprint(
        SimpleNamespace(data=moved, subentries=entry.subentries)
    )


def test_reconciliation_removes_the_closure_of_a_deleted_zone() -> None:
    """A vanished zone handle removes its zone, routes, and private loops and valves."""
    entry = plant_entry(authorize_outputs(_data()))
    assert reconcile_removed_subentries(entry) is None
    remaining = {
        subentry_id: subentry
        for subentry_id, subentry in entry.subentries.items()
        if subentry.unique_id not in {BEDROOM.zone_id, SOURCE_ID}
    }

    data = reconcile_removed_subentries(SimpleNamespace(data=entry.data, subentries=remaining))

    assert data is not None
    assert _ids(data, "zones") == [LIVING.zone_id]
    assert _ids(data, "circuits") == [LIVING.circuit_id]
    assert _ids(data, "valves") == [LIVING.valve_id]
    assert _ids(data, "routes") == [LIVING.route_id]
    assert _ids(data, "pumps") == [MANIFOLD_PUMP_ID]
    assert _ids(data, "sources") == []
    assert data[CONF_SUBENTRY_OBJECTS] == {LIVING.zone_id: "zone"}
    assert data[CONF_ZONE_OBJECTS] == {
        LIVING.circuit_id: LIVING.zone_id,
        LIVING.valve_id: LIVING.zone_id,
    }
    assert data[CONF_DRY_RUN] is True
    assert CONF_OUTPUT_AUTHORIZATION not in data


async def test_persisting_data_aborts_when_safe_shutdown_cannot_finish(hass) -> None:
    """A failed transition to Dry run leaves the parent graph byte-for-byte unchanged."""
    entry = manifold_entry(dry_run=False)
    entry.add_to_hass(hass)
    runtime = SimpleNamespace(async_set_dry_run=AsyncMock(return_value=False))
    entry.runtime_data = runtime
    original = deepcopy(dict(entry.data))

    persisted = await async_persist_entry_data(
        SimpleNamespace(hass=hass), entry, lambda data: data_with_zone(data, _office())
    )

    assert persisted is False
    runtime.async_set_dry_run.assert_awaited_once_with(True, hass=hass)
    assert dict(entry.data) == original


async def test_persisting_data_reaches_dry_run_then_stores(hass) -> None:
    """A live Plant reaches Dry run through its runtime before the data is stored."""
    entry = manifold_entry(dry_run=False)
    entry.add_to_hass(hass)
    runtime = SimpleNamespace(async_set_dry_run=AsyncMock(return_value=True))
    entry.runtime_data = runtime
    data = data_with_zone(entry.data, _office())

    assert await async_persist_entry_data(
        SimpleNamespace(hass=hass), entry, lambda current: data_with_zone(current, _office())
    )

    runtime.async_set_dry_run.assert_awaited_once_with(True, hass=hass)
    assert dict(entry.data) == data


async def test_persisting_data_builds_on_what_another_edit_stored_meanwhile(hass) -> None:
    """The edit applies to the data stored while the safe shutdown waited, with no await after."""
    entry = manifold_entry(dry_run=False)
    entry.add_to_hass(hass)
    renamed = deepcopy(dict(entry.data))
    renamed["name"] = "Renamed meanwhile"
    stored: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def shutdown(dry_run: bool, *, hass: Any) -> bool:
        # Another flow stores its edit while this one waits for the shutdown.
        hass.config_entries.async_update_entry(entry, data=renamed)
        return True

    entry.runtime_data = SimpleNamespace(async_set_dry_run=shutdown)

    assert await async_persist_entry_data(
        SimpleNamespace(hass=hass),
        entry,
        lambda current: data_with_zone(current, _office()),
        on_stored=lambda previous, data: stored.append((dict(previous), dict(data))),
    )

    assert entry.data["name"] == "Renamed meanwhile"
    assert entry.data == data_with_zone(renamed, _office())
    assert stored == [(renamed, dict(entry.data))]


async def test_persisting_data_stores_nothing_when_the_edit_no_longer_fits(hass) -> None:
    """A graph edit error of the late build reaches the caller and stores nothing."""
    entry = manifold_entry(dry_run=True)
    entry.add_to_hass(hass)
    original = deepcopy(dict(entry.data))

    def build(current: Any) -> dict[str, Any]:
        raise StoredTopologyError("The Plant changed meanwhile.")

    with pytest.raises(StoredTopologyError):
        await async_persist_entry_data(SimpleNamespace(hass=hass), entry, build)

    assert dict(entry.data) == original


def test_plant_entry_builder_matches_the_contract() -> None:
    """The shared fixture builds exactly one handle per zone and source."""
    entry = plant_entry(_data())

    assert isinstance(entry, MockConfigEntry)
    assert (entry.version, entry.minor_version) == (4, 0)
    assert sorted(subentry.unique_id for subentry in entry.subentries.values()) == sorted(
        [LIVING.zone_id, BEDROOM.zone_id, SOURCE_ID]
    )
