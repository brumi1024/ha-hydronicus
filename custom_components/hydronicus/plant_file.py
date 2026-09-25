"""Render, parse, and check plant files at the Home Assistant boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import dump

from .const import CONF_NAME, CONF_PLANT_ID
from .core.plant_document import ImportedPlant, PlantDocumentError, export_plant_document
from .entry_configuration import plant_ownership, topology_copy
from .flows.common import is_hydronicus_owned

# The object selector's editor submits no value while it is empty or holds YAML
# it cannot parse, and marks the line of the YAML problem itself.
EMPTY_PLANT_FILE_ERROR: Final = (
    "The plant file is empty or not valid YAML. The editor marks the line with the problem."
)


def plant_file(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical plant file of stored Plant data.

    Raise ``ValueError`` when the stored graph does not decode or breaks
    ownership, because such a Plant has no faithful plant file.
    """
    return export_plant_document(
        name=str(data.get(CONF_NAME, "")),
        plant_id=str(data.get(CONF_PLANT_ID, "")),
        topology=topology_copy(data),
        ownership=plant_ownership(data),
    )


def plant_file_yaml(document: Mapping[str, Any]) -> str:
    """Render a plant file as YAML, keeping the canonical key order."""
    return str(dump(dict(document)))


def parsed_plant_file(document: Any) -> Any:
    """Return a submitted plant file, parsing it when it arrives as YAML text.

    A missing or empty document raises ``PlantDocumentError`` at the top level.
    """
    if isinstance(document, str):
        try:
            document = yaml.safe_load(document)
        except yaml.YAMLError as error:
            raise PlantDocumentError("", f"The plant file is not valid YAML: {error}") from error
    if document is None or document == "":
        raise PlantDocumentError("", EMPTY_PLANT_FILE_ERROR)
    return document


def first_own_entity(hass: HomeAssistant, imported: ImportedPlant) -> tuple[str, str] | None:
    """Return the path and entity ID of the first Hydronicus entity the file binds."""
    for entity_id, path in imported.entity_paths.items():
        if is_hydronicus_owned(hass, entity_id):
            return path, entity_id
    return None
