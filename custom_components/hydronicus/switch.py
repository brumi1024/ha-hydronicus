"""The Control equipment switch, the Away switch, and the source's DHW and Warm-up switches.

Turning Control equipment on lets the Plant command its armed outputs. Turning
it off runs the off-mode sequence and then only observes, which is Dry run.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

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


class AwaySwitch(HydronicusEntity, SwitchEntity):
    """Whether the Plant is away: every digital thermostat holds its away level."""

    _attr_translation_key = "away"

    def __init__(self, runtime: PlantRuntime) -> None:
        super().__init__(
            runtime, plant_unique_id(runtime.plant.id, "away"), plant_device(runtime.plant)
        )

    @property
    def is_on(self) -> bool:
        return self.runtime.away is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        away = self.runtime.away
        until = None if away is None else away.until
        return {"until": None if until is None else dt_util.utc_from_timestamp(until).isoformat()}

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.runtime.set_away(None)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.runtime.end_away()


class WarmUpSwitch(HydronicusEntity, SwitchEntity):
    """Whether a warm-up raises the heating supply; on starts the configured one."""

    _attr_translation_key = "warm_up"

    def __init__(self, runtime: PlantRuntime) -> None:
        super().__init__(
            runtime, plant_unique_id(runtime.plant.id, "warm_up"), source_device(runtime)
        )

    @property
    def available(self) -> bool:
        return self.runtime.heating_supply is not None

    @property
    def is_on(self) -> bool:
        result = self.runtime.heating_supply
        return result is not None and result.state.warming

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self.runtime.heating_supply
        state = None if result is None else result.state
        if state is None or state.warm_until is None:
            return {"until": None, "shift": None, "curve_steps": None, "zones": None}
        return {
            "until": dt_util.utc_from_timestamp(state.warm_until).isoformat(),
            "shift": state.warm_shift,
            "curve_steps": state.warm_steps,
            "zones": list(state.warm_zones),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.runtime.start_warm_up()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.runtime.command_supply(warm_up=False)


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
    entities: list[tuple[str | None, Entity]] = [
        (None, ControlEquipmentSwitch(entry)),
        (None, AwaySwitch(runtime)),
    ]
    source = runtime.plant.source
    if source is not None and source.dhw is not None and source.dhw.switch is not None:
        entities.append((None, DhwSwitch(runtime)))
    if source is not None and source.heating_supplies:
        entities.append((None, WarmUpSwitch(runtime)))
    async_add_plant_entities(runtime, "switch", async_add_entities, entities)
