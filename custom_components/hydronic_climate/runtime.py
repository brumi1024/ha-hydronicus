"""Home Assistant runtime boundary for a hydronic plant.

Hardware observation and service execution will be added here in later milestones.
The initial vertical slice is intentionally shadow-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import CONF_NAME, CONF_PLANT_ID, CONF_SHADOW_MODE


@dataclass(frozen=True, slots=True)
class HydronicRuntime:
    """Runtime data retained for one configured plant."""

    plant_id: str
    name: str
    shadow_mode: bool

    @classmethod
    def from_entry(cls, entry: Any) -> HydronicRuntime:
        """Construct safe runtime data from a config entry."""
        return cls(
            plant_id=str(entry.data.get(CONF_PLANT_ID, getattr(entry, "entry_id", "plant"))),
            name=str(entry.data.get(CONF_NAME, getattr(entry, "title", "Hydronic plant"))),
            shadow_mode=bool(entry.data.get(CONF_SHADOW_MODE, True)),
        )
