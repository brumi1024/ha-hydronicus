"""The Control equipment switch (decision 15), and the source's DHW switch.

Turning Control equipment on lets the Plant command its armed outputs. Turning
it off runs the off-mode sequence and then only observes, which is Dry run.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HydronicusConfigEntry
from .entity import (
    HydronicusEntity,
    async_add_plant_entities,
    plant_device,
    plant_unique_id,
    source_device,
)
from .runtime import PlantRuntime

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


class DhwSwitch(HydronicusEntity, SwitchEntity):
    """Whether the source heats its DHW: the owned value, which a change elsewhere sets too."""

    _attr_translation_key = "dhw"

    def __init__(self, runtime: PlantRuntime) -> None:
        super().__init__(runtime, plant_unique_id(runtime.plant.id, "dhw"), source_device(runtime))

    @property
    def available(self) -> bool:
        dhw = self.runtime.dhw
        return dhw is not None and dhw.on is not None

    @property
    def is_on(self) -> bool | None:
        dhw = self.runtime.dhw
        return None if dhw is None else dhw.on

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.runtime.command_dhw(on=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.runtime.command_dhw(on=False)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    entities: list[tuple[str | None, Entity]] = [(None, ControlEquipmentSwitch(entry))]
    source = runtime.plant.source
    if source is not None and source.dhw is not None and source.dhw.switch is not None:
        entities.append((None, DhwSwitch(runtime)))
    async_add_plant_entities(runtime, "switch", async_add_entities, entities)
