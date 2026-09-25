"""Room subentry flow.

A room is one zone with its routes and its private loops and valves. This stub
keeps the ``room`` subentry type registered until the room flow replaces it.
"""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries

from .common import OwnEntityPickerMixin


class RoomSubentryFlowHandler(OwnEntityPickerMixin, config_entries.ConfigSubentryFlow):
    """Add or edit one room."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Rooms cannot be added from the UI yet."""
        return self.async_abort(reason="room_flow_pending")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Rooms cannot be edited from the UI yet."""
        return self.async_abort(reason="room_flow_pending")
