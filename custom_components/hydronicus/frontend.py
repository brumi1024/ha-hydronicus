"""Serve the bundled Hydronicus Lovelace card and load it automatically."""

from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

FRONTEND_FILE_NAME = "hydronicus-plant-card.js"
FRONTEND_FILE = Path(__file__).parent / "frontend" / FRONTEND_FILE_NAME
# Kept for dashboards that still list the card as a manual resource. It is
# served without long-lived cache headers, so such a resource always loads
# the installed bundle, whose element guard makes the second load harmless.
LEGACY_FRONTEND_URL_PATH = f"/{DOMAIN}/{FRONTEND_FILE_NAME}"


def versioned_url_path(version: str) -> str:
    """Return the cacheable bundle path for one integration version."""
    return f"/{DOMAIN}/{version}/{FRONTEND_FILE_NAME}"


def _bundle_digest() -> str:
    """Hash the bundle so a rebuilt file under the same version is refetched."""
    return hashlib.sha256(FRONTEND_FILE.read_bytes()).hexdigest()[:12]


async def async_register_frontend(hass: HomeAssistant) -> str:
    """Serve the card bundle and register it as a frontend module.

    Returns the module URL added to the frontend. The manifest depends on the
    frontend, so the HTTP server and the frontend are always set up first.
    """
    version = str((await async_get_integration(hass, DOMAIN)).version)
    digest = await hass.async_add_executor_job(_bundle_digest)
    url_path = versioned_url_path(version)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(url_path, str(FRONTEND_FILE), cache_headers=True),
            StaticPathConfig(LEGACY_FRONTEND_URL_PATH, str(FRONTEND_FILE), cache_headers=False),
        ]
    )
    module_url = f"{url_path}?v={digest}"
    add_extra_js_url(hass, module_url)
    return module_url
