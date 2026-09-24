"""Helpers that read flow forms the way the Home Assistant frontend does."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.helpers import config_validation as cv
from probatio import to_field_list


def form_fields(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return serialized fields by name; section fields are keyed "section.field"."""
    fields: dict[str, dict[str, Any]] = {}

    def collect(items: list[dict[str, Any]], prefix: str) -> None:
        for item in items:
            fields[prefix + item["name"]] = item
            if item.get("type") == "expandable":
                collect(item["schema"], f"{prefix}{item['name']}.")

    collect(
        to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer),
        "",
    )
    return fields


def frontend_submission(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return what the frontend submits when the user saves a form unchanged.

    A suggested value wins over a default, and sections submit a nested mapping.
    """

    def initial(items: list[dict[str, Any]]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for item in items:
            suggested = (item.get("description") or {}).get("suggested_value")
            if item.get("type") == "expandable":
                data[item["name"]] = initial(item["schema"])
            elif suggested is not None:
                data[item["name"]] = suggested
            elif "default" in item:
                data[item["name"]] = item["default"]
        return data

    return initial(to_field_list(result["data_schema"], custom_serializer=cv.custom_serializer))


def form_value(result: Mapping[str, Any], name: str) -> Any:
    """Return the value the frontend shows for one field, or None."""
    field = form_fields(result)[name]
    suggested = (field.get("description") or {}).get("suggested_value")
    return suggested if suggested is not None else field.get("default")
