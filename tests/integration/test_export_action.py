"""The ``hydronicus.export_plant`` action returns the plant file of one Plant."""

from __future__ import annotations

import json

import pytest
import yaml
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydronicus.const import CONF_TOPOLOGY, DOMAIN
from custom_components.hydronicus.core.plant_document import import_plant_document
from custom_components.hydronicus.entry_configuration import (
    data_with_plant,
    subentries_for,
    topology_copy,
)
from tests.integration.plant_fixtures import (
    MANIFOLD_PUMP_ENTITY,
    PLANT_ID,
    manifold_entry,
    manifold_topology,
    manifold_zones,
    plant_data,
)

LIVING, BEDROOM = manifold_zones(("Living room", "Bedroom"))
SOURCE_ID = "00000000-0000-4000-8000-000600000001"
BOILER = {
    "id": SOURCE_ID,
    "name": "Boiler",
    "source_type": "external",
    "priority": 1,
}


async def _loaded(hass):
    for zone in (LIVING, BEDROOM):
        hass.states.async_set(zone.temperature_sensor, "18.0")
        hass.states.async_set(zone.valve_entity, "off")
    hass.states.async_set(MANIFOLD_PUMP_ENTITY, "off")
    entry = manifold_entry(sources=[BOILER])
    entry.add_to_hass(hass)
    # Setting up the integration registers the action and sets up the entry.
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert entry.runtime_data is not None
    return entry


async def _export(hass, entry_id: str, **kwargs):
    return await hass.services.async_call(
        DOMAIN,
        "export_plant",
        {"config_entry_id": entry_id},
        blocking=True,
        return_response=True,
        **kwargs,
    )


def _canonical(topology) -> dict:
    """Compare stored collections independent of record order."""
    return {
        collection: sorted(json.dumps(record, sort_keys=True) for record in records)
        if isinstance(records, list)
        else records
        for collection, records in topology_copy({CONF_TOPOLOGY: topology}).items()
    }


async def test_action_and_dialog_return_the_same_plant_file(hass) -> None:
    """The action response is the document the Plant settings dialog shows."""
    entry = await _loaded(hass)

    response = await _export(hass, entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "export_plant"}
    )
    shown = result["description_placeholders"]["document"]
    assert set(response) == {"document"}
    assert (
        yaml.safe_load(shown.removeprefix("```yaml\n").removesuffix("```")) == response["document"]
    )
    # The response is plain JSON data.
    assert json.loads(json.dumps(response)) == response


async def test_exported_plant_file_rebuilds_an_identical_plant(hass) -> None:
    """Importing the export reproduces topology, ownership, and zone and source handles."""
    entry = await _loaded(hass)

    document = (await _export(hass, entry.entry_id))["document"]
    imported = import_plant_document(document, plant_id="00000000-0000-4000-8000-00000000beef")
    rebuilt = data_with_plant(entry.data, imported)

    assert imported.plant_id == PLANT_ID
    assert rebuilt["name"] == entry.data["name"]
    assert _canonical(rebuilt[CONF_TOPOLOGY]) == _canonical(entry.data[CONF_TOPOLOGY])
    assert rebuilt["zone_objects"] == entry.data["zone_objects"]
    assert sorted(subentries_for(rebuilt), key=lambda handle: handle["unique_id"]) == sorted(
        (
            {
                "data": dict(subentry.data),
                "subentry_type": subentry.subentry_type,
                "title": subentry.title,
                "unique_id": subentry.unique_id,
            }
            for subentry in entry.subentries.values()
        ),
        key=lambda handle: handle["unique_id"],
    )


async def test_action_exports_an_unloaded_plant(hass) -> None:
    """The file comes from stored data, so a Plant that is not loaded exports too."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry = manifold_entry()
    entry.add_to_hass(hass)

    response = await _export(hass, entry.entry_id)

    assert response["document"]["name"] == "Hydronic plant"
    assert set(response["document"]["zones"]) == {"living_room", "bedroom"}


async def test_action_refuses_an_unknown_config_entry(hass) -> None:
    """An id that is not a Hydronicus Plant raises a translated validation error."""
    assert await async_setup_component(hass, DOMAIN, {})
    other = MockConfigEntry(domain="other_domain", data={})
    other.add_to_hass(hass)

    for entry_id in ("missing", other.entry_id):
        with pytest.raises(ServiceValidationError) as raised:
            await _export(hass, entry_id)
        assert raised.value.translation_domain == DOMAIN
        assert raised.value.translation_key == "plant_not_found"


async def test_action_refuses_a_non_admin_user(hass, hass_read_only_user) -> None:
    """Exporting reveals the whole Plant configuration, so only admins may call it."""
    entry = await _loaded(hass)

    with pytest.raises(Unauthorized):
        await _export(hass, entry.entry_id, context=Context(user_id=hass_read_only_user.id))


async def test_action_response_is_a_valid_plant_file_for_new_data(hass) -> None:
    """The exported document imports on its own, as a new instance would."""
    entry = await _loaded(hass)
    document = (await _export(hass, entry.entry_id))["document"]

    imported = import_plant_document(document, plant_id=PLANT_ID)

    expected = plant_data(manifold_topology(sources=[BOILER]))
    assert _canonical(imported.topology) == _canonical(expected[CONF_TOPOLOGY])
