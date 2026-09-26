"""Zone demand, loop flow, and the source request (contract K7)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HydronicusConfigEntry
from .core.model import Loop, Mode, Zone
from .core.step import value_of
from .entity import (
    HydronicusEntity,
    ZoneEntity,
    async_add_plant_entities,
    loop_unique_id,
    plant_device,
    plant_unique_id,
    source_device,
    zone_device,
)
from .runtime import PlantRuntime

PARALLEL_UPDATES = 0


class ZoneDemandSensor(ZoneEntity, BinarySensorEntity):
    """Whether a zone demands heating, or cooling, and why."""

    _unrecorded_attributes = frozenset({"reason"})

    def __init__(self, runtime: PlantRuntime, zone: Zone, mode: Mode) -> None:
        kind = "heating" if mode is Mode.HEAT else "cooling"
        super().__init__(runtime, zone, f"{kind}_demand")
        self._attr_translation_key = f"{kind}_demand"
        self._mode = mode

    @property
    def available(self) -> bool:
        return self.runtime.view is not None

    @property
    def is_on(self) -> bool:
        view = self.runtime.view
        demand = None if view is None else view.desired.demands.get(self._zone)
        return demand is not None and demand.on and demand.mode is self._mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        view = self.runtime.view
        demand = None if view is None else view.desired.demands.get(self._zone)
        if demand is None:
            return {}
        return {"reason": demand.reason}


class LoopFlowingSensor(HydronicusEntity, BinarySensorEntity):
    """Whether a loop passes flow: its valves are open and its pump runs."""

    _attr_translation_key = "loop_flowing"
    _unrecorded_attributes = frozenset({"reason"})
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, runtime: PlantRuntime, loop: Loop) -> None:
        plant = runtime.plant
        device = (
            plant_device(plant)
            if loop.zone is None
            else zone_device(runtime, plant.zone(loop.zone))
        )
        super().__init__(runtime, loop_unique_id(plant.id, loop.ref, "flowing"), device)
        self._attr_translation_placeholders = {"loop": loop.title}
        self._loop = loop

    @property
    def available(self) -> bool:
        return self.runtime.view is not None

    @property
    def is_on(self) -> bool:
        view = self.runtime.view
        return view is not None and view.loop_flowing(self._loop)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        runtime, loop = self.runtime, self._loop
        view = runtime.view
        outputs = {} if view is None else view.seen.outputs

        def shown(entity: str) -> Any:
            state = outputs.get(entity)
            return None if state is None else value_of(state)

        pump = runtime.plant.pump(loop.pump)
        source = runtime.plant.source
        pump_entity = pump.switch or (None if source is None else source.request)
        return {
            "valves": {valve.entity: shown(valve.entity) for valve in loop.valves},
            "pump": pump.slug,
            "pump_running": None if pump_entity is None else shown(pump_entity),
            "reason": None if view is None else view.desired.reasons.get(str(loop.ref)),
        }


class SourceRequestedSensor(HydronicusEntity, BinarySensorEntity):
    """Whether the Plant asks its source for heat or cooling."""

    _attr_translation_key = "source_requested"
    _unrecorded_attributes = frozenset({"reason"})
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, runtime: PlantRuntime) -> None:
        super().__init__(
            runtime,
            plant_unique_id(runtime.plant.id, "source_requested"),
            source_device(runtime),
        )

    @property
    def available(self) -> bool:
        return self.runtime.view is not None

    @property
    def is_on(self) -> bool:
        view = self.runtime.view
        return view is not None and view.desired.source_request

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        runtime = self.runtime
        view = runtime.view
        source = runtime.plant.source
        assert source is not None
        observed = None if view is None else view.observations.outputs.get(source.request)
        return {
            "observed": None if observed is None else value_of(observed),
            "reason": None if view is None else view.desired.reasons.get("source"),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    plant = runtime.plant
    entities: list[tuple[str | None, Entity]] = []
    if plant.source is not None:
        entities.append((None, SourceRequestedSensor(runtime)))
    for loop in plant.loops:
        entities.append((None, LoopFlowingSensor(runtime, loop)))
    for zone in plant.zones:
        entities.append((zone.slug, ZoneDemandSensor(runtime, zone, Mode.HEAT)))
        if zone.cools:
            entities.append((zone.slug, ZoneDemandSensor(runtime, zone, Mode.COOL)))
        entities.extend((zone.slug, LoopFlowingSensor(runtime, loop)) for loop in zone.loops)
    async_add_plant_entities(runtime, "binary_sensor", async_add_entities, entities)
