"""Tests for serving and auto-registering the Hydronicus Plant card."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.setup import async_setup_component

from custom_components.hydronicus import frontend
from custom_components.hydronicus.const import DOMAIN
from custom_components.hydronicus.presentation import PRESENTATION_SCHEMA_VERSION

MANIFEST = Path(frontend.__file__).parent / "manifest.json"
REPOSITORY_ROOT = Path(__file__).parents[2]


async def test_card_is_registered_with_a_versioned_cached_url(hass, hass_client) -> None:
    """C10: the card loads without a manual resource and is cached per version."""
    assert await async_setup_component(hass, "frontend", {})
    urls = hass.data[DATA_EXTRA_MODULE_URL]
    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]

    module_url = await frontend.async_register_frontend(hass)

    assert module_url.startswith(f"/hydronicus/{version}/hydronicus-plant-card.js?v=")
    assert module_url in urls.urls
    client = await hass_client()
    bundle = frontend.FRONTEND_FILE.read_bytes()

    versioned = await client.get(module_url)
    assert versioned.status == 200
    assert await versioned.read() == bundle
    assert "max-age" in versioned.headers.get("Cache-Control", "")

    # A leftover manual resource keeps loading the current bundle, uncached.
    legacy = await client.get(frontend.LEGACY_FRONTEND_URL_PATH)
    assert legacy.status == 200
    assert await legacy.read() == bundle
    assert "max-age" not in legacy.headers.get("Cache-Control", "")


def test_rebuilt_bundle_changes_the_module_url(tmp_path, monkeypatch) -> None:
    """A rebuilt bundle under the same version must bypass the long cache."""
    bundle = tmp_path / frontend.FRONTEND_FILE_NAME
    bundle.write_text("export {};\n", encoding="utf-8")
    monkeypatch.setattr(frontend, "FRONTEND_FILE", bundle)
    first = frontend._bundle_digest()
    bundle.write_text("export const changed = true;\n", encoding="utf-8")
    assert frontend._bundle_digest() != first


async def test_integration_setup_registers_the_card(hass) -> None:
    """Setting up the integration sets up the frontend and adds the card module."""
    assert await async_setup_component(hass, DOMAIN, {})
    urls = hass.data[DATA_EXTRA_MODULE_URL]

    assert [url for url in urls.urls if "hydronicus-plant-card.js" in url]


def test_card_and_backend_share_the_presentation_schema_version() -> None:
    """The card rejects snapshots from any other schema version."""
    logic = (REPOSITORY_ROOT / "frontend" / "src" / "logic.ts").read_text(encoding="utf-8")

    assert f"export const PRESENTATION_SCHEMA_VERSION = {PRESENTATION_SCHEMA_VERSION};" in logic


def test_manifest_describes_a_calculating_integration_that_depends_on_the_frontend() -> None:
    """M1 and C10 manifest contract."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["iot_class"] == "calculated"
    assert {"frontend", "http"} <= set(manifest["dependencies"])
