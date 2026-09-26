"""The Control equipment switch (decision 15).

Turning it on lets the Plant command its armed outputs. Turning it off runs the
off-mode sequence and then only observes, which is Dry run.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HydronicusConfigEntry
from .entity import HydronicusEntity, async_add_plant_entities, plant_device, plant_unique_id

PARALLEL_UPDATES = 0


class ControlEquipmentSwitch(HydronicusEntity, SwitchEntity):
    """Whether the Plant commands its armed outputs."""

    _attr_translation_key = "control"

    def __init__(self, entry: HydronicusConfigEntry) -> None:
        runtime = entry.runtime_data
        super().__init__(
            runtime, plant_unique_id(runtime.plant.id, "control"), plant_device(runtime.plant)
        )

    @property
    def is_on(self) -> bool:
        return self.runtime.control

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Control stays live after it is turned off until the off-mode sequence ends.
        return {"live": self.runtime.state.live}

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.runtime.set_control(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.runtime.set_control(False)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_plant_entities(
        entry.runtime_data, "switch", async_add_entities, [(None, ControlEquipmentSwitch(entry))]
    )
