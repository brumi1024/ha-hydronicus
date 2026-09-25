"""Plant settings: the Configure menu, pumps, the plant file dialog, and plant file edits."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import UUID, uuid5

import pytest
import voluptuous as vol
import yaml
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.hydronicus.const import (
    CONF_DRY_RUN,
    CONF_OUTPUT_AUTHORIZATION,
    CONF_ROOM_OBJECTS,
    DOMAIN,
    SUBENTRY_TYPE_ROOM,
)
from custom_components.hydronicus.core.plant_document import export_plant_document
from custom_components.hydronicus.entry_configuration import (
    data_with_pump,
    effective_plant,
    output_authorization,
    plant_ownership,
    topology_copy,
)
from custom_components.hydronicus.runtime import HydronicRuntime
from tests.integration.plant_fixtures import (
    MANIFOLD_PUMP_ENTITY,
    MANIFOLD_PUMP_ID,
    PLANT_ID,
    manifold_entry,
    manifold_rooms,
    manifold_topology,
    plant_data,
    plant_entry,
    room_subentry,
)

LIVING, BEDROOM = manifold_rooms(("Living room", "Bedroom"))
SPARE_PUMP_ENTITY = "switch.spare_pump"
KITCHEN_SENSOR = "sensor.kitchen_temperature"
KITCHEN_VALVE = "switch.kitchen_valve"
NEW_BEDROOM_VALVE = "switch.bedroom_valve_new"


def _set_states(hass) -> None:
    for room in (LIVING, BEDROOM):
        hass.states.async_set(room.temperature_sensor, "18.0")
        hass.states.async_set(room.valve_entity, "off")
    for entity_id in (MANIFOLD_PUMP_ENTITY, SPARE_PUMP_ENTITY, KITCHEN_VALVE, NEW_BEDROOM_VALVE):
        hass.states.async_set(entity_id, "off")
    hass.states.async_set(KITCHEN_SENSOR, "18.0")


async def _loaded_manifold(hass, *, dry_run: bool = True):
    _set_states(hass)
    entry = manifold_entry(dry_run=dry_run)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _open(hass, entry, option: str) -> dict[str, Any]:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": option}
    )


async def _submit(hass, result, user_input) -> dict[str, Any]:
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input)
    await hass.async_block_till_done()
    return result


def _export(entry) -> dict[str, Any]:
    return export_plant_document(
        name=entry.data["name"],
        plant_id=entry.data["plant_id"],
        topology=topology_copy(entry.data),
        ownership=plant_ownership(entry.data),
    )


def _schema_keys(result) -> dict[str, Any]:
    return {str(key): key for key in result["data_schema"].schema}


def _registrations(hass, entry) -> dict[str, tuple[str, str | None]]:
    """Map every entity unique ID to its entity ID and owning subentry."""
    return {
        registry_entry.unique_id: (registry_entry.entity_id, registry_entry.config_subentry_id)
        for registry_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }


def _devices(hass, entry) -> dict[str, str | None]:
    """Map every device identifier to its owning subentry."""
    devices = {}
    for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id):
        ((_domain, identifier),) = device.identifiers
        devices[identifier] = device.config_subentry_id
    return devices


def _object_registrations(registrations, object_id: str) -> dict[str, tuple[str, str | None]]:
    return {
        unique_id: value for unique_id, value in registrations.items() if object_id in unique_id
    }


def _derived_id(kind: str, slug: str) -> str:
    return str(uuid5(UUID(PLANT_ID), f"{kind}:{slug}"))


# --------------------------------------------------------------------------
# Menu and Dry run
# --------------------------------------------------------------------------


async def test_configure_opens_the_plant_settings_menu(hass) -> None:
    """Plant settings are one menu over Dry run, pumps, and the plant file.

    They are the entry's options flow, so the Plant row shows a Configure button,
    and there is no second Reconfigure entry point to the same menu.
    """
    entry = await _loaded_manifold(hass)
    assert entry.supports_options is True
    assert entry.supports_reconfigure is False

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"
    assert list(result["menu_options"]) == [
        "dry_run",
        "add_pump",
        "edit_pump",
        "export_plant",
        "edit_plant",
    ]
    # A menu opened from a repair names the Plant it edits.
    assert result["description_placeholders"] == {"plant": "Hydronic plant"}


async def test_menu_hides_pump_editing_without_pumps(hass) -> None:
    """A Plant without pumps offers no pump to edit."""
    entry = plant_entry(plant_data({}))
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert "edit_pump" not in result["menu_options"]
    assert "add_pump" in result["menu_options"]


async def test_dry_run_step_keeps_the_confirmation(hass) -> None:
    """Leaving Dry run still goes through the output confirmation."""
    entry = await _loaded_manifold(hass)

    result = await _open(hass, entry, "dry_run")
    assert result["step_id"] == "dry_run"
    result = await _submit(hass, result, {CONF_DRY_RUN: False})
    assert result["step_id"] == "dry_run_confirmation"
    assert MANIFOLD_PUMP_ENTITY in result["description_placeholders"]["outputs"]
    result = await _submit(hass, result, {"dry_run_confirmation": True})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "settings_saved"
    assert entry.data[CONF_DRY_RUN] is False


# --------------------------------------------------------------------------
# Pumps
# --------------------------------------------------------------------------


async def test_pumps_can_be_added_edited_and_removed(hass) -> None:
    """A new pump is Plant equipment; unused, it is edited and removed again."""
    entry = await _loaded_manifold(hass, dry_run=False)
    assert CONF_OUTPUT_AUTHORIZATION in entry.data

    result = await _open(hass, entry, "add_pump")
    assert result["step_id"] == "pump"
    assert "remove_pump" not in _schema_keys(result)
    result = await _submit(
        hass,
        result,
        {
            "name": " Spare pump ",
            "entity_id": SPARE_PUMP_ENTITY,
            "overrun_seconds": 60.0,
            "feedback": {"power_feedback_entity": "sensor.spare_pump_power"},
        },
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "settings_saved"
    (spare,) = [
        pump for pump in entry.data["topology"]["pumps"] if pump["entity_id"] == SPARE_PUMP_ENTITY
    ]
    assert spare["name"] == "Spare pump"
    assert spare["overrun_seconds"] == 60.0
    assert spare["power_feedback_entity"] == "sensor.spare_pump_power"
    assert "flow_feedback_entity" not in spare
    # Every graph change returns to Dry run.
    assert entry.data[CONF_DRY_RUN] is True
    assert CONF_OUTPUT_AUTHORIZATION not in entry.data
    assert entry.runtime_data.plant.pumps[spare["id"]].entity_id == SPARE_PUMP_ENTITY

    result = await _open(hass, entry, "edit_pump")
    assert result["step_id"] == "edit_pump"
    result = await _submit(hass, result, {"pump": spare["id"]})
    assert result["step_id"] == "pump"
    keys = _schema_keys(result)
    assert keys["name"].default() == "Spare pump"
    assert "remove_pump" in keys
    result = await _submit(
        hass,
        result,
        {"name": "Reserve pump", "entity_id": SPARE_PUMP_ENTITY, "overrun_seconds": 30.0},
    )
    assert result["reason"] == "settings_saved"
    (reserve,) = [pump for pump in entry.data["topology"]["pumps"] if pump["id"] == spare["id"]]
    assert reserve["name"] == "Reserve pump"
    assert reserve["overrun_seconds"] == 30.0
    # Feedback bindings survive an edit that leaves the section untouched.
    assert reserve["power_feedback_entity"] == "sensor.spare_pump_power"

    result = await _open(hass, entry, "edit_pump")
    result = await _submit(hass, result, {"pump": spare["id"]})
    result = await _submit(
        hass,
        result,
        {
            "name": "Reserve pump",
            "entity_id": SPARE_PUMP_ENTITY,
            "overrun_seconds": 30.0,
            "remove_pump": True,
        },
    )
    assert result["reason"] == "settings_saved"
    assert [pump["id"] for pump in entry.data["topology"]["pumps"]] == [MANIFOLD_PUMP_ID]
    assert spare["id"] not in entry.runtime_data.plant.pumps
    # The removed pump leaves no orphaned entities or device behind.
    assert _object_registrations(_registrations(hass, entry), spare["id"]) == {}
    assert not any(spare["id"] in identifier for identifier in _devices(hass, entry))


async def test_removing_a_pump_in_use_names_its_loops(hass) -> None:
    """A pump that loops still use cannot be removed."""
    entry = await _loaded_manifold(hass)
    data = deepcopy(dict(entry.data))

    result = await _open(hass, entry, "edit_pump")
    result = await _submit(hass, result, {"pump": MANIFOLD_PUMP_ID})
    result = await _submit(
        hass,
        result,
        {
            "name": "Manifold pump",
            "entity_id": MANIFOLD_PUMP_ENTITY,
            "overrun_seconds": 0.0,
            "remove_pump": True,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pump"
    assert result["errors"] == {"remove_pump": "equipment_in_use"}
    assert result["description_placeholders"]["users"] == "Living room loop, Bedroom loop"
    assert dict(entry.data) == data


async def test_pump_form_keeps_the_flow_conventions(hass) -> None:
    """Names, actuator reuse, and Hydronicus entities are rejected where the user fixes them."""
    entry = await _loaded_manifold(hass)
    own_entity = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{PLANT_ID}_dry_run"
    )
    assert own_entity is not None
    data = deepcopy(dict(entry.data))

    result = await _open(hass, entry, "add_pump")
    # Entity pickers hide Hydronicus entities.
    entity_selector = _schema_keys(result)
    assert own_entity in result["data_schema"].schema[entity_selector["entity_id"]].config.get(
        "exclude_entities", []
    )

    base = {"name": "Spare pump", "entity_id": SPARE_PUMP_ENTITY, "overrun_seconds": 0.0}
    result = await _submit(hass, result, {**base, "name": "  "})
    assert result["errors"] == {"name": "name_required"}
    # A rejected form is shown again with the submitted values.
    suggested = _schema_keys(result)["entity_id"].description["suggested_value"]
    assert suggested == SPARE_PUMP_ENTITY

    result = await _submit(hass, result, {**base, "entity_id": LIVING.valve_entity})
    assert result["errors"] == {"entity_id": "actuator_entity_in_use"}

    assert dict(entry.data) == data

    # A stored Hydronicus binding stays visible, so the submit check rejects it,
    # on the form because the field sits inside the feedback section.
    data["topology"]["pumps"][0]["fault_feedback_entity"] = own_entity
    hass.config_entries.async_update_entry(entry, data=data)
    await hass.async_block_till_done()
    result = await _open(hass, entry, "edit_pump")
    result = await _submit(hass, result, {"pump": MANIFOLD_PUMP_ID})
    result = await _submit(
        hass,
        result,
        {
            "name": "Manifold pump",
            "entity_id": MANIFOLD_PUMP_ENTITY,
            "overrun_seconds": 0.0,
            "feedback": {"fault_feedback_entity": own_entity},
        },
    )
    assert result["errors"] == {"base": "own_entity"}
    assert dict(entry.data) == data


OTHER_PLANT_ID = "00000000-0000-4000-8000-00000000f001"
OTHER_PLANT_OUTPUT = "switch.office_valve"


def _other_plant_binding_an_output(hass) -> None:
    """Store another Plant whose Office valve is ``OTHER_PLANT_OUTPUT``."""
    other = plant_entry(
        plant_data(manifold_topology(("Office",)), plant_id=OTHER_PLANT_ID), title="Plant 1"
    )
    other.add_to_hass(hass)
    hass.states.async_set(OTHER_PLANT_OUTPUT, "off")


async def _stored_spare_pump(hass, entry, entity_id: str = SPARE_PUMP_ENTITY) -> str:
    """Add an unused spare pump through the pump form and return its id."""
    result = await _open(hass, entry, "add_pump")
    result = await _submit(
        hass, result, {"name": "Spare pump", "entity_id": entity_id, "overrun_seconds": 0.0}
    )
    if result["type"] == FlowResultType.FORM and result["step_id"] == "pump_review":
        result = await _submit(hass, result, {"confirm": True})
    assert result["reason"] == "settings_saved"
    (spare,) = [pump for pump in entry.data["topology"]["pumps"] if pump["entity_id"] == entity_id]
    return str(spare["id"])


async def test_a_pump_bound_by_another_plant_is_a_reviewed_warning(hass) -> None:
    """A pump entity another Plant binds is confirmed before the pump is saved."""
    _other_plant_binding_an_output(hass)
    entry = await _loaded_manifold(hass)
    data = deepcopy(dict(entry.data))

    result = await _open(hass, entry, "add_pump")
    result = await _submit(
        hass,
        result,
        {"name": "Spare pump", "entity_id": OTHER_PLANT_OUTPUT, "overrun_seconds": 0.0},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pump_review"
    assert not result.get("errors")
    warnings = result["description_placeholders"]["warnings"]
    assert OTHER_PLANT_OUTPUT in warnings
    assert "Plant 1" in warnings
    assert dict(entry.data) == data
    result = await _submit(hass, result, {"confirm": False})
    assert result["step_id"] == "pump_review"
    assert result["errors"] == {"base": "confirm_required"}
    assert dict(entry.data) == data
    result = await _submit(hass, result, {"confirm": True})
    assert result["reason"] == "settings_saved"
    assert [pump["entity_id"] for pump in entry.data["topology"]["pumps"]] == [
        MANIFOLD_PUMP_ENTITY,
        OTHER_PLANT_OUTPUT,
    ]

    # The shared output is confirmed on every edit, not only when it first appears.
    spare_id = entry.data["topology"]["pumps"][1]["id"]
    result = await _open(hass, entry, "edit_pump")
    result = await _submit(hass, result, {"pump": spare_id})
    result = await _submit(
        hass,
        result,
        {"name": "Reserve pump", "entity_id": OTHER_PLANT_OUTPUT, "overrun_seconds": 0.0},
    )
    assert result["step_id"] == "pump_review"
    result = await _submit(hass, result, {"confirm": True})
    assert result["reason"] == "settings_saved"
    assert entry.data["topology"]["pumps"][1]["name"] == "Reserve pump"


async def test_a_pump_change_that_introduces_a_warning_is_reviewed(hass, monkeypatch) -> None:
    """A compiler warning the pump change introduces needs a confirmation too."""
    entry = await _loaded_manifold(hass)
    introduced: list[tuple[Any, Any]] = []

    def one_new_warning(compiled, before):
        introduced.append((compiled, before))
        return compiled.warnings[:1]

    monkeypatch.setattr(
        "custom_components.hydronicus.flows.plant.warnings_to_confirm", one_new_warning
    )
    result = await _open(hass, entry, "add_pump")
    result = await _submit(
        hass,
        result,
        {"name": "Spare pump", "entity_id": SPARE_PUMP_ENTITY, "overrun_seconds": 0.0},
    )

    assert result["step_id"] == "pump_review"
    # The proposed Plant is compared with the stored one.
    ((compiled, before),) = introduced
    assert before is not None
    assert len(compiled.logic_summary) >= len(before.logic_summary)
    assert "Manifold pump" in result["description_placeholders"]["warnings"]
    assert SPARE_PUMP_ENTITY not in [pump["entity_id"] for pump in entry.data["topology"]["pumps"]]


async def test_a_pump_change_without_new_warnings_saves_directly(hass) -> None:
    """A warning the Plant already had, such as the shared manifold pump, is not asked again."""
    entry = await _loaded_manifold(hass)
    assert "shared_pump_limits_independent_control" in {
        warning.code for warning in effective_plant(entry).compiled.warnings
    }

    result = await _open(hass, entry, "edit_pump")
    result = await _submit(hass, result, {"pump": MANIFOLD_PUMP_ID})
    result = await _submit(
        hass,
        result,
        {"name": "Main pump", "entity_id": MANIFOLD_PUMP_ENTITY, "overrun_seconds": 0.0},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "settings_saved"
    assert entry.data["topology"]["pumps"][0]["name"] == "Main pump"


async def test_editing_a_pump_removed_meanwhile_is_an_invalid_pump(hass) -> None:
    """A pump another flow removed is not brought back by an open pump form."""
    entry = await _loaded_manifold(hass)
    spare_id = await _stored_spare_pump(hass, entry)
    result = await _open(hass, entry, "edit_pump")
    result = await _submit(hass, result, {"pump": spare_id})
    hass.config_entries.async_update_entry(entry, data=data_with_pump(entry.data, spare_id, None))
    await hass.async_block_till_done()
    data = deepcopy(dict(entry.data))

    result = await _submit(
        hass,
        result,
        {"name": "Spare pump", "entity_id": SPARE_PUMP_ENTITY, "overrun_seconds": 0.0},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pump"
    assert result["errors"] == {"base": "invalid_pump"}
    assert "removed meanwhile" in result["description_placeholders"]["error"]
    assert dict(entry.data) == data


async def test_a_pump_review_confirmed_after_the_pump_was_removed_returns_to_the_form(
    hass,
) -> None:
    """A save-time graph error on the review is reported on the pump form."""
    _other_plant_binding_an_output(hass)
    entry = await _loaded_manifold(hass)
    spare_id = await _stored_spare_pump(hass, entry, OTHER_PLANT_OUTPUT)
    result = await _open(hass, entry, "edit_pump")
    result = await _submit(hass, result, {"pump": spare_id})
    result = await _submit(
        hass,
        result,
        {"name": "Reserve pump", "entity_id": OTHER_PLANT_OUTPUT, "overrun_seconds": 0.0},
    )
    assert result["step_id"] == "pump_review"
    hass.config_entries.async_update_entry(entry, data=data_with_pump(entry.data, spare_id, None))
    await hass.async_block_till_done()
    data = deepcopy(dict(entry.data))

    result = await _submit(hass, result, {"confirm": True})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pump"
    assert result["errors"] == {"base": "invalid_pump"}
    assert dict(entry.data) == data


async def test_a_pump_review_waits_for_a_live_plant_to_reach_dry_run(hass, monkeypatch) -> None:
    """A confirmed pump that cannot reach Dry run yet is not saved."""
    _other_plant_binding_an_output(hass)
    entry = await _loaded_manifold(hass, dry_run=False)
    data = deepcopy(dict(entry.data))

    async def shutdown_pending(self, dry_run, **kwargs) -> bool:
        return False

    monkeypatch.setattr(HydronicRuntime, "async_set_dry_run", shutdown_pending)
    result = await _open(hass, entry, "add_pump")
    result = await _submit(
        hass,
        result,
        {"name": "Spare pump", "entity_id": OTHER_PLANT_OUTPUT, "overrun_seconds": 0.0},
    )
    assert result["step_id"] == "pump_review"
    result = await _submit(hass, result, {"confirm": True})

    assert result["step_id"] == "pump_review"
    assert result["errors"] == {"base": "dry_run_shutdown_in_progress"}
    assert dict(entry.data) == data

    monkeypatch.undo()
    result = await _submit(hass, result, {"confirm": True})
    assert result["reason"] == "settings_saved"
    assert entry.data[CONF_DRY_RUN] is True
    assert OTHER_PLANT_OUTPUT in [pump["entity_id"] for pump in entry.data["topology"]["pumps"]]


# --------------------------------------------------------------------------
# Export dialog
# --------------------------------------------------------------------------


async def test_export_dialog_shows_the_plant_file(hass) -> None:
    """The dialog shows the canonical plant file as YAML."""
    entry = await _loaded_manifold(hass)

    result = await _open(hass, entry, "export_plant")

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "plant_exported"
    document = result["description_placeholders"]["document"]
    assert document.startswith("```yaml\n")
    assert document.endswith("\n```")
    assert yaml.safe_load(document.removeprefix("```yaml\n").removesuffix("```")) == _export(entry)


# --------------------------------------------------------------------------
# Plant file editing
# --------------------------------------------------------------------------


async def _edit(hass, entry, document) -> dict[str, Any]:
    result = await _open(hass, entry, "edit_plant")
    assert result["step_id"] == "edit_plant"
    return await _submit(hass, result, {"document": document})


async def _apply(hass, entry, document) -> dict[str, Any]:
    result = await _edit(hass, entry, document)
    assert result["type"] == FlowResultType.FORM, result
    assert result["step_id"] == "edit_plant_review"
    confirm = {"confirm": True} if "confirm" in _schema_keys(result) else {}
    result = await _submit(hass, result, confirm)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "settings_saved"
    await hass.async_block_till_done()
    return result


async def test_edit_form_is_prefilled_with_the_current_plant_file(hass) -> None:
    """The object selector starts from the current export."""
    entry = await _loaded_manifold(hass)

    result = await _open(hass, entry, "edit_plant")

    key = _schema_keys(result)["document"]
    assert key.description["suggested_value"] == _export(entry)


async def test_unchanged_plant_file_aborts_without_touching_dry_run(hass) -> None:
    """Saving the current file changes nothing, not even Dry run or authorization."""
    entry = await _loaded_manifold(hass, dry_run=False)
    data = deepcopy(dict(entry.data))
    subentries = dict(entry.subentries)

    result = await _edit(hass, entry, _export(entry))

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_changes"
    assert dict(entry.data) == data
    assert entry.data[CONF_DRY_RUN] is False
    assert entry.data[CONF_OUTPUT_AUTHORIZATION] == output_authorization(entry.data)
    assert dict(entry.subentries) == subentries


async def test_unchanged_plant_file_written_as_yaml_text_aborts(hass) -> None:
    """A document submitted as YAML text is parsed like the object it spells."""
    entry = await _loaded_manifold(hass)

    result = await _edit(hass, entry, yaml.safe_dump(_export(entry)))

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_changes"


async def test_plant_file_of_another_plant_is_refused(hass) -> None:
    """A file carrying another Plant's id would rebuild a different Plant."""
    entry = await _loaded_manifold(hass)
    document = _export(entry)
    document["id"] = "00000000-0000-4000-8000-00000000ffff"

    result = await _edit(hass, entry, document)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "edit_plant"
    assert result["errors"] == {"base": "plant_id_mismatch"}


@pytest.mark.parametrize(
    ("change", "path", "error"),
    [
        pytest.param(
            lambda document: document["rooms"]["bedroom"].update(colour="blue"),
            "rooms.bedroom.colour",
            "Unknown key 'colour'.",
            id="unknown_key",
        ),
        pytest.param(
            lambda document: document["rooms"]["bedroom"]["loops"]["bedroom_loop"].update(
                pump="missing_pump"
            ),
            "rooms.bedroom.loops.bedroom_loop.pump",
            None,
            id="unknown_reference",
        ),
        pytest.param(lambda document: document.pop("hydronicus"), "hydronicus", None, id="format"),
        pytest.param(lambda document: document.clear(), "hydronicus", None, id="empty"),
    ],
)
async def test_invalid_plant_file_shows_its_path(hass, change, path, error) -> None:
    """Import errors point at the key to fix, and the form keeps the submitted file."""
    entry = await _loaded_manifold(hass)
    data = deepcopy(dict(entry.data))
    document = _export(entry)
    change(document)

    result = await _edit(hass, entry, document)

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_document"}
    assert result["description_placeholders"]["path"] == path
    if error is not None:
        assert result["description_placeholders"]["error"] == error
    assert _schema_keys(result)["document"].description["suggested_value"] == document
    assert dict(entry.data) == data


async def test_yaml_syntax_error_is_an_invalid_document(hass) -> None:
    """Broken YAML text is reported instead of crashing the flow."""
    entry = await _loaded_manifold(hass)

    result = await _edit(hass, entry, "hydronicus: [1\nname: Broken")

    assert result["errors"] == {"base": "invalid_document"}
    assert result["description_placeholders"]["path"] == "the top level"


async def test_emptied_plant_file_editor_is_explained(hass) -> None:
    """The editor field is optional, so an emptied or unparseable file reaches the flow."""
    entry = await _loaded_manifold(hass)
    result = await _open(hass, entry, "edit_plant")
    assert isinstance(_schema_keys(result)["document"], vol.Optional)

    result = await _submit(hass, result, {})

    assert result["errors"] == {"base": "invalid_document"}
    assert result["description_placeholders"] == {
        "path": "the top level",
        "error": (
            "The plant file is empty or not valid YAML. The editor marks the line with the problem."
        ),
    }


async def test_plant_file_binding_a_hydronicus_entity_is_refused(hass) -> None:
    """A Hydronicus entity bound in the file is reported with its path."""
    entry = await _loaded_manifold(hass)
    own_entity = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{PLANT_ID}_dry_run"
    )
    document = _export(entry)
    document["pumps"]["manifold_pump"]["fault_feedback_entity"] = own_entity

    result = await _edit(hass, entry, document)

    assert result["errors"] == {"base": "document_own_entity"}
    assert result["description_placeholders"] == {
        "path": "pumps.manifold_pump.fault_feedback_entity",
        "entity_id": own_entity,
    }


async def test_review_lists_changes_and_requires_confirmation_of_warnings(hass) -> None:
    """The review names every change and asks to confirm blocking warnings."""
    entry = await _loaded_manifold(hass)
    data = deepcopy(dict(entry.data))
    document = _export(entry)
    document["name"] = "Home"
    document["rooms"]["living_room"]["name"] = "Lounge"
    del document["rooms"]["bedroom"]
    document["pumps"]["spare_pump"] = SPARE_PUMP_ENTITY

    result = await _edit(hass, entry, document)

    assert result["step_id"] == "edit_plant_review"
    placeholders = result["description_placeholders"]
    changes = placeholders["changes"].splitlines()
    assert "- Renames the Plant from Hydronic plant to Home" in changes
    assert "- Renames room Living room to Lounge" in changes
    assert "- Removes room Bedroom" in changes
    assert "- Removes loop Bedroom loop" in changes
    assert "- Removes valve Bedroom loop valve" in changes
    assert "- Adds pump Spare pump" in changes
    assert "Lounge is heated by Living room loop." in placeholders["logic"]
    assert "Spare pump" in placeholders["warnings"]

    # Only an unused pump is left to warn about, which never blocks a save.
    assert "confirm" not in _schema_keys(result)

    document["pumps"].pop("spare_pump")
    document["rooms"]["bedroom"] = _export(entry)["rooms"]["bedroom"]
    document["valves"] = {"shared_valve": "switch.shared_valve"}
    for room in document["rooms"].values():
        for loop in room["loops"].values():
            loop["valves"].append("shared_valve")
    result = await _edit(hass, entry, document)
    # The shared pump warning was already confirmed, but a newly shared valve needs a confirmation.
    assert "confirm" in _schema_keys(result)
    result = await _submit(hass, result, {"confirm": False})
    assert result["errors"] == {"base": "confirm_required"}
    assert dict(entry.data) == data


async def test_applying_a_plant_file_to_a_live_plant_returns_to_dry_run(hass) -> None:
    """A plant file edit is a graph change, so it invalidates the output authorization."""
    entry = await _loaded_manifold(hass, dry_run=False)
    document = _export(entry)
    document["rooms"]["living_room"]["name"] = "Lounge"

    await _apply(hass, entry, document)

    assert entry.data[CONF_DRY_RUN] is True
    assert CONF_OUTPUT_AUTHORIZATION not in entry.data
    assert entry.runtime_data.dry_run is True


async def test_plant_file_adds_a_room(hass) -> None:
    """A new room gets its own subentry, which owns its entities and devices."""
    entry = await _loaded_manifold(hass)
    before = _registrations(hass, entry)
    document = _export(entry)
    document["rooms"]["kitchen"] = {
        "temperature_sensors": [KITCHEN_SENSOR],
        "loops": {"kitchen_loop": {"valves": [KITCHEN_VALVE], "pump": "manifold_pump"}},
    }

    await _apply(hass, entry, document)

    kitchen_zone = _derived_id("zone", "kitchen")
    kitchen_valve = _derived_id("valve", "kitchen_loop_valve")
    kitchen = room_subentry(entry, kitchen_zone)
    assert kitchen.title == "Kitchen"
    assert kitchen.data == {"id": kitchen_zone}
    assert entry.data[CONF_ROOM_OBJECTS][kitchen_valve] == kitchen_zone
    after = _registrations(hass, entry)
    zone_entities = _object_registrations(after, kitchen_zone)
    valve_entities = _object_registrations(after, kitchen_valve)
    assert zone_entities
    assert valve_entities
    assert {owner for _entity_id, owner in (*zone_entities.values(), *valve_entities.values())} == {
        kitchen.subentry_id
    }
    devices = _devices(hass, entry)
    assert devices[f"{PLANT_ID}:zone:{kitchen_zone}"] == kitchen.subentry_id
    assert devices[f"{PLANT_ID}:valve:{kitchen_valve}"] == kitchen.subentry_id
    # Every existing entity keeps its entity ID and owner.
    assert {unique_id: after[unique_id] for unique_id in before} == before


async def test_plant_file_removes_a_room(hass) -> None:
    """Removing a room removes its subentry, entities, and devices, and nothing else."""
    entry = await _loaded_manifold(hass)
    before = _registrations(hass, entry)
    bedroom_subentry = room_subentry(entry, BEDROOM.zone_id).subentry_id
    document = _export(entry)
    del document["rooms"]["bedroom"]

    await _apply(hass, entry, document)

    assert bedroom_subentry not in entry.subentries
    assert BEDROOM.zone_id not in entry.runtime_data.plant.zones
    after = _registrations(hass, entry)
    for object_id in (BEDROOM.zone_id, BEDROOM.valve_id, BEDROOM.circuit_id):
        assert _object_registrations(after, object_id) == {}
        assert not any(object_id in identifier for identifier in _devices(hass, entry))
    kept = {
        unique_id: value
        for unique_id, value in before.items()
        if not any(
            object_id in unique_id
            for object_id in (BEDROOM.zone_id, BEDROOM.valve_id, BEDROOM.circuit_id)
        )
    }
    assert {unique_id: after[unique_id] for unique_id in kept} == kept


async def test_plant_file_renames_a_room(hass) -> None:
    """Renaming a room retitles its subentry and keeps every entity ID."""
    entry = await _loaded_manifold(hass)
    before = _registrations(hass, entry)
    document = _export(entry)
    document["rooms"]["living_room"]["name"] = "Lounge"

    await _apply(hass, entry, document)

    living = room_subentry(entry, LIVING.zone_id)
    assert living.title == "Lounge"
    assert entry.runtime_data.plant.zones[LIVING.zone_id].name == "Lounge"
    assert _registrations(hass, entry) == before


async def test_plant_file_moves_a_private_loop_to_the_plant(hass) -> None:
    """A loop and valve that become Plant equipment move their entities to the Plant."""
    entry = await _loaded_manifold(hass)
    before = _registrations(hass, entry)
    document = _export(entry)
    living = document["rooms"]["living_room"]
    loop = living.pop("loops")["living_room_loop"]
    valve = living.pop("valves")["living_room_loop_valve"]
    route_id = loop.pop("route_id")
    document["valves"] = {"living_room_loop_valve": valve}
    document["loops"] = {"living_room_loop": loop}
    living["shared_loops"] = [{"loop": "living_room_loop", "route_id": route_id}]

    result = await _edit(hass, entry, document)
    changes = result["description_placeholders"]["changes"].splitlines()
    assert "- Moves loop Living room loop from Living room to the Plant" in changes
    assert "- Moves valve Living room loop valve from Living room to the Plant" in changes
    # Moving a loop introduces no warning, so nothing needs a confirmation.
    assert "confirm" not in _schema_keys(result)
    await _submit(hass, result, {})
    await hass.async_block_till_done()

    assert LIVING.circuit_id not in entry.data[CONF_ROOM_OBJECTS]
    assert LIVING.valve_id not in entry.data[CONF_ROOM_OBJECTS]
    assert entry.runtime_data.subentry_id_for(LIVING.valve_id) is None
    after = _registrations(hass, entry)
    valve_entities = _object_registrations(after, LIVING.valve_id)
    assert valve_entities
    for unique_id, (entity_id, owner) in valve_entities.items():
        assert entity_id == before[unique_id][0]
        assert owner is None
    assert _devices(hass, entry)[f"{PLANT_ID}:valve:{LIVING.valve_id}"] is None
    # Everything else keeps its entity ID and owner.
    assert {
        unique_id: value for unique_id, value in after.items() if unique_id not in valve_entities
    } == {
        unique_id: value for unique_id, value in before.items() if unique_id not in valve_entities
    }


async def test_plant_file_changes_a_valve_entity(hass) -> None:
    """Rebinding a valve keeps its id, so its entities, devices, and owner stay."""
    entry = await _loaded_manifold(hass)
    before = _registrations(hass, entry)
    devices = _devices(hass, entry)
    document = _export(entry)
    document["rooms"]["bedroom"]["valves"]["bedroom_loop_valve"]["entity_id"] = NEW_BEDROOM_VALVE

    await _apply(hass, entry, document)

    assert entry.runtime_data.plant.valves[BEDROOM.valve_id].entity_id == NEW_BEDROOM_VALVE
    assert _registrations(hass, entry) == before
    assert _devices(hass, entry) == devices
    assert entry.runtime_data.subentry_id_for(BEDROOM.valve_id) == (
        room_subentry(entry, BEDROOM.zone_id).subentry_id
    )


async def test_plant_file_edit_keeps_room_handles_consistent(hass) -> None:
    """Room subentries match the edited graph one to one after the reload."""
    entry = await _loaded_manifold(hass)
    document = _export(entry)
    del document["rooms"]["living_room"]
    document["rooms"]["kitchen"] = {
        "temperature_sensors": [KITCHEN_SENSOR],
        "loops": {"kitchen_loop": {"valves": [KITCHEN_VALVE], "pump": "manifold_pump"}},
    }

    await _apply(hass, entry, document)

    rooms = sorted(
        subentry.unique_id
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_ROOM
    )
    assert rooms == sorted([BEDROOM.zone_id, _derived_id("zone", "kitchen")])
    assert entry.state is ConfigEntryState.LOADED
    assert set(entry.runtime_data.plant.zones) == set(rooms)


BOILER_ID = "00000000-0000-4000-8000-0000000b0001"


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(lambda document: document.pop("sources"), id="removed-source"),
        pytest.param(lambda document: None, id="kept-source"),
    ],
)
async def test_plant_file_giving_an_object_the_id_of_another_kind_is_refused(hass, change) -> None:
    """An id keeps its kind, and room and source handles never share a unique ID."""
    _set_states(hass)
    entry = manifold_entry(
        sources=[{"id": BOILER_ID, "name": "Boiler", "source_type": "external", "priority": 1}]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    data = deepcopy(dict(entry.data))
    document = _export(entry)
    change(document)
    document["rooms"]["kitchen"] = {
        "id": BOILER_ID,
        "temperature_sensors": [KITCHEN_SENSOR],
        "loops": {"kitchen_loop": {"valves": [KITCHEN_VALVE], "pump": "manifold_pump"}},
    }

    result = await _edit(hass, entry, document)

    assert result["step_id"] == "edit_plant"
    assert result["errors"] == {"base": "invalid_document"}
    assert BOILER_ID in result["description_placeholders"]["error"]
    assert dict(entry.data) == data
    assert entry.state is ConfigEntryState.LOADED


async def test_plant_file_review_confirmed_after_the_plant_changed_is_shown_again(
    hass,
) -> None:
    """The review lists changes against one Plant, so a changed Plant is reviewed again."""
    entry = await _loaded_manifold(hass)
    document = _export(entry)
    document["rooms"]["living_room"]["name"] = "Lounge"
    review = await _edit(hass, entry, document)
    assert review["step_id"] == "edit_plant_review"
    pump = await _open(hass, entry, "add_pump")
    pump = await _submit(
        hass,
        pump,
        {"name": "Spare pump", "entity_id": SPARE_PUMP_ENTITY, "overrun_seconds": 0.0},
    )
    assert pump["reason"] == "settings_saved"
    data = deepcopy(dict(entry.data))

    result = await _submit(hass, review, {})

    assert result["step_id"] == "edit_plant_review"
    assert result["errors"] == {"base": "plant_changed"}
    assert "- Removes pump Spare pump" in result["description_placeholders"]["changes"]
    assert dict(entry.data) == data

    result = await _submit(hass, result, {})

    assert result["reason"] == "settings_saved"
    await hass.async_block_till_done()
    assert [pump["name"] for pump in entry.data["topology"]["pumps"]] == ["Manifold pump"]
    assert room_subentry(entry, LIVING.zone_id).title == "Lounge"


async def test_export_dialog_of_an_unreadable_plant_explains_why(hass) -> None:
    """A Plant whose stored graph is invalid cannot be exported, and the dialog says why."""
    data = deepcopy(dict(manifold_entry().data))
    data["topology"]["routes"][0]["circuit_id"] = "00000000-0000-4000-8000-00000000dead"
    entry = plant_entry(data)
    entry.add_to_hass(hass)

    result = await _open(hass, entry, "export_plant")

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "plant_file_unavailable"
    assert result["description_placeholders"]["error"]
