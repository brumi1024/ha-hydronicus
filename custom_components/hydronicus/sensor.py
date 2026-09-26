"""The Plant status and each zone's combined temperature and dew point (contract K7)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HydronicusConfigEntry
from .core.model import Zone
from .core.step import value_of
from .entity import (
    HydronicusEntity,
    async_add_plant_entities,
    plant_device,
    plant_unique_id,
    zone_device,
    zone_unique_id,
)
from .runtime import PlantRuntime
from .view import ZoneReadings

PARALLEL_UPDATES = 0

STATUSES = [
    "off",
    "idle",
    "heating",
    "cooling",
    "changing_over",
    "degraded",
    "stopping",
    "invalid",
]


class PlantStatusSensor(HydronicusEntity, SensorEntity):
    """What the Plant does now, with what blocks it."""

    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES
    # Reasons quote readings and change with every one; the recorder keeps the rest.
    _unrecorded_attributes = frozenset({"reasons", "proposed"})

    def __init__(self, runtime: PlantRuntime) -> None:
        super().__init__(
            runtime, plant_unique_id(runtime.plant.id, "status"), plant_device(runtime.plant)
        )

    @property
    def available(self) -> bool:
        return self.runtime.view is not None

    @property
    def native_value(self) -> str | None:
        view = self.runtime.view
        return None if view is None else view.status()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        runtime, view = self.runtime, self.runtime.view
        if view is None:
            return {}
        plant = runtime.plant
        attributes: dict[str, Any] = {
            "requested_mode": runtime.requested_mode.value,
            "running_mode": view.running_mode.value,
            "live": runtime.state.live,
            "active_loops": [str(loop.ref) for loop in plant.all_loops if view.loop_flowing(loop)],
            "blocked_zones": view.blocked_zones(),
            "unarmed_outputs": sorted(set(plant.outputs()) - runtime.armed),
            "source_requested": view.desired.source_request,
            "outputs_not_responding": sorted(view.reconciled.repairs),
            "missing_entities": sorted(view.missing),
            "stopping_outputs": view.stopping_outputs(),
            "configuration_problem": runtime.problem,
            "reasons": dict(view.desired.reasons),
        }
        if not runtime.state.live:
            attributes["proposed"] = {
                entity: value_of(state)
                for entity, state in sorted(runtime.reconcile_state.dry_run.items())
            }
        return attributes


class ZoneTemperatureSensor(HydronicusEntity, SensorEntity):
    """A zone's combined temperature, with each area's sensor and reading."""

    _attr_translation_key = "combined_temperature"
    _unrecorded_attributes = frozenset({"areas", "sensors"})
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, runtime: PlantRuntime, zone: Zone) -> None:
        super().__init__(
            runtime,
            zone_unique_id(runtime.plant.id, zone.slug, "temperature"),
            zone_device(runtime, zone),
        )
        self._zone = zone.slug

    @property
    def _readings(self) -> ZoneReadings:
        view = self.runtime.view
        return ZoneReadings() if view is None else view.readings(self._zone)

    @property
    def native_value(self) -> float | None:
        return self._readings.temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        readings = self._readings
        return {
            "areas": {area: dict(values) for area, values in readings.areas.items()},
            "sensors": dict(readings.sensors),
        }


class ZoneDewPointSensor(HydronicusEntity, SensorEntity):
    """A cooling zone's worst-case dew point, from its warmest and most humid readings."""

    _attr_translation_key = "dew_point"
    _unrecorded_attributes = frozenset({"humidity"})
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, runtime: PlantRuntime, zone: Zone) -> None:
        super().__init__(
            runtime,
            zone_unique_id(runtime.plant.id, zone.slug, "dew_point"),
            zone_device(runtime, zone),
        )
        self._zone = zone.slug

    @property
    def native_value(self) -> float | None:
        view = self.runtime.view
        readings = ZoneReadings() if view is None else view.readings(self._zone)
        return None if readings.dew_point is None else round(readings.dew_point, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        view = self.runtime.view
        readings = ZoneReadings() if view is None else view.readings(self._zone)
        return {"humidity": readings.humidity}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    entities: list[tuple[str | None, Entity]] = [(None, PlantStatusSensor(runtime))]
    for zone in runtime.plant.zones:
        if zone.temperature or zone.areas:
            entities.append((zone.slug, ZoneTemperatureSensor(runtime, zone)))
        if zone.cools:
            entities.append((zone.slug, ZoneDewPointSensor(runtime, zone)))
    async_add_plant_entities(runtime, "sensor", async_add_entities, entities)
