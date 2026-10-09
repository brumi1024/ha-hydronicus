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
    loop_device,
    loop_unique_id,
    plant_unique_id,
    source_device,
)
from .runtime import PlantRuntime
from .view import pump_operation, source_operation

PARALLEL_UPDATES = 0


class ZoneDemandSensor(ZoneEntity, BinarySensorEntity):
    """Whether a zone demands heating, or cooling, and why."""

    _unrecorded_attributes = frozenset({"reason", "holds"})

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
        if view is None or demand is None:
            return {}
        return {"reason": demand.reason, "holds": view.holds(self._zone)}


class LoopFlowingSensor(HydronicusEntity, BinarySensorEntity):
    """Whether a loop passes flow: its valves are open and its pump runs."""

    _attr_translation_key = "loop_flowing"
    _unrecorded_attributes = frozenset({"reason", "pump_reason", "holds"})
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, runtime: PlantRuntime, loop: Loop) -> None:
        super().__init__(
            runtime,
            loop_unique_id(runtime.plant.id, loop.ref, "flowing"),
            loop_device(runtime, loop),
        )
        self._attr_translation_placeholders = {"loop": loop.title}
        self._loop = loop

    @property
    def available(self) -> bool:
        return self.runtime.view is not None

    @property
    def is_on(self) -> bool | None:
        view = self.runtime.view
        return None if view is None else view.loop_operation(self._loop).active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        runtime, loop = self.runtime, self._loop
        view = runtime.view
        outputs = {} if view is None else view.seen.outputs

        def shown(entity: str) -> Any:
            state = outputs.get(entity)
            return None if state is None else value_of(state)

        pump = runtime.plant.pump(loop.pump)
        operation = (
            None
            if view is None
            else pump_operation(
                runtime.plant, pump, view.seen, view.at, source_winding=view.source_winding
            )
        )
        return {
            "valves": {valve.entity: shown(valve.entity) for valve in loop.valves},
            "pump": pump.slug,
            "pump_running": None if operation is None else operation.active,
            "pump_running_basis": None if operation is None else operation.basis,
            "flow_basis": None if view is None else view.loop_operation(loop).basis,
            "flow_sensor": pump.flow_sensor,
            "dry_run": not runtime.state.live,
            "observed_flow": None
            if view is None
            else view.loop_operation(loop, observed=True).active,
            "reason": None if view is None else view.desired.reasons.get(str(loop.ref)),
            "pump_reason": None
            if view is None or pump.switch is None
            else view.desired.reasons.get(pump.switch),
            "holds": [] if view is None else view.holds(*view.loop_hold_targets(loop)),
        }


class SourceRequestedSensor(HydronicusEntity, BinarySensorEntity):
    """Whether the Plant asks its source for heat or cooling."""

    _attr_translation_key = "source_requested"
    _unrecorded_attributes = frozenset({"reason", "holds"})
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
            "running": None
            if view is None
            else source_operation(runtime.plant, view.observations).active,
            "running_basis": None
            if view is None
            else source_operation(runtime.plant, view.observations).basis,
            "running_sensor": source.running_sensor,
            "reason": None if view is None else view.desired.reasons.get("source"),
            "holds": [] if view is None else view.holds("source"),
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
        if Mode.COOL in plant.zone_modes(zone.slug):
            entities.append((zone.slug, ZoneDemandSensor(runtime, zone, Mode.COOL)))
        entities.extend((zone.slug, LoopFlowingSensor(runtime, loop)) for loop in zone.loops)
    async_add_plant_entities(runtime, "binary_sensor", async_add_entities, entities)
