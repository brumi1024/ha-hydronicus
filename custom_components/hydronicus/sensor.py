"""The Plant status, each zone's readings and duty cycle, and each loop's runtime (contract K7)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HydronicusConfigEntry
from .core.model import Loop, Mode, Zone
from .core.reconcile import target_to_dict
from .core.step import value_of
from .entity import (
    HydronicusEntity,
    ZoneEntity,
    async_add_plant_entities,
    loop_device,
    loop_unique_id,
    plant_device,
    plant_unique_id,
)
from .flow_history import HOUR
from .runtime import PlantRuntime
from .view import pump_operation, source_operation

PARALLEL_UPDATES = 0

STATUSES = [
    "off",
    "idle",
    "heating",
    "cooling",
    "exercising",
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
    _unrecorded_attributes = frozenset(
        {
            "reasons",
            "holds",
            "proposed",
            "sensor_health",
            "pending_commands",
            "evaluation_age_seconds",
        }
    )

    def __init__(self, runtime: PlantRuntime) -> None:
        super().__init__(
            runtime, plant_unique_id(runtime.plant.id, "status"), plant_device(runtime.plant)
        )

    @property
    def available(self) -> bool:
        return self.runtime.view is not None or self.runtime.evaluation_error is not None

    @property
    def native_value(self) -> str | None:
        if self.runtime.evaluation_error is not None:
            return "degraded"
        view = self.runtime.view
        return None if view is None else view.status()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        runtime, view = self.runtime, self.runtime.view
        now = dt_util.utcnow().timestamp()
        health: dict[str, Any] = {
            "evaluation_error": runtime.evaluation_error,
            "blocking_reason": runtime.evaluation_error
            or (None if view is None else view.blocking_reason()),
            "evaluated_at": None
            if view is None
            else dt_util.utc_from_timestamp(view.at).isoformat(),
            "evaluation_age_seconds": None if view is None else round(max(0.0, now - view.at), 1),
            "next_evaluation_at": None
            if runtime.next_evaluation_at is None
            else dt_util.utc_from_timestamp(runtime.next_evaluation_at).isoformat(),
            "pending_commands": {
                entity: {
                    "target": target_to_dict(attempt.target),
                    "age_seconds": round(max(0.0, now - attempt.sent_at), 1),
                    "attempts": attempt.count,
                }
                for entity, attempt in sorted(runtime.reconcile_state.attempts.items())
            },
        }
        if view is None:
            return health
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
            "frost_protection": list(view.desired.frost_protection),
            "exercising": view.desired.exercise,
            "sensor_health": view.sensor_health(now),
            "pump_operation": {
                pump.slug: {
                    **pump_operation(
                        plant,
                        pump,
                        view.observations,
                        now,
                        source_winding=view.source_winding and view.live,
                    ).attributes(),
                    "reason": None
                    if pump.switch is None
                    else view.desired.reasons.get(pump.switch),
                    "holds": view.holds(pump.switch or "source"),
                }
                for pump in plant.pumps
            },
            "source_operation": source_operation(plant, view.observations).attributes(),
            "observed_flow": {
                str(loop.ref): view.loop_operation(loop, observed=True).attributes()
                for loop in plant.all_loops
            },
            "idle_since": {
                entity: None if since is None else dt_util.utc_from_timestamp(since).isoformat()
                for entity, since in sorted(runtime.state.idle_since.items())
            },
            "reasons": dict(view.desired.reasons),
            "holds": view.holds(),
            **health,
        }
        if not runtime.state.live:
            attributes["proposed"] = {
                entity: value_of(state)
                for entity, state in sorted(runtime.reconcile_state.dry_run.items())
            }
        return attributes


class ZoneTemperatureSensor(ZoneEntity, SensorEntity):
    """A zone's combined temperature, with each area's sensor and reading."""

    _attr_translation_key = "combined_temperature"
    _unrecorded_attributes = frozenset({"areas", "sensors", "sensor_health"})
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, runtime: PlantRuntime, zone: Zone) -> None:
        super().__init__(runtime, zone, "temperature")

    @property
    def native_value(self) -> float | None:
        return self._readings.temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        readings = self._readings
        return {
            "areas": {area: dict(values) for area, values in readings.areas.items()},
            "sensors": dict(readings.sensors),
            "sensor_health": {
                entity: dict(health) for entity, health in readings.sensor_health.items()
            },
        }


class ZoneDewPointSensor(ZoneEntity, SensorEntity):
    """A cooling zone's worst-case dew point, from its warmest and most humid readings."""

    _attr_translation_key = "dew_point"
    _unrecorded_attributes = frozenset({"humidity"})
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, runtime: PlantRuntime, zone: Zone) -> None:
        super().__init__(runtime, zone, "dew_point")

    @property
    def native_value(self) -> float | None:
        dew_point = self._readings.dew_point
        return None if dew_point is None else round(dew_point, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"humidity": self._readings.humidity}


class ZoneDutyCycleSensor(ZoneEntity, SensorEntity):
    """The share of the last day in which a loop that serves the zone passed flow."""

    _attr_translation_key = "duty_cycle"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 0

    def __init__(self, runtime: PlantRuntime, zone: Zone) -> None:
        super().__init__(runtime, zone, "duty_cycle")

    @property
    def native_value(self) -> float | None:
        duty_cycle = self.runtime.flow.duty_cycle(self._zone)
        return None if duty_cycle is None else round(duty_cycle, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "basis": "Loop flow inferred from equipment feedback while control is live",
            "window_hours": 24,
            "includes_current_hour": False,
        }


class LoopRuntimeSensor(HydronicusEntity, SensorEntity):
    """How long a loop has passed flow while the Plant was live."""

    _attr_translation_key = "loop_runtime"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 1

    def __init__(self, runtime: PlantRuntime, loop: Loop) -> None:
        super().__init__(
            runtime,
            loop_unique_id(runtime.plant.id, loop.ref, "runtime"),
            loop_device(runtime, loop),
        )
        self._attr_translation_placeholders = {"loop": loop.title}
        self._loop = str(loop.ref)

    @property
    def native_value(self) -> float:
        return round(self.runtime.flow.runtime(self._loop) / HOUR, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"basis": "Loop flow inferred from equipment feedback while control is live"}


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
        if Mode.COOL in runtime.plant.zone_modes(zone.slug):
            entities.append((zone.slug, ZoneDewPointSensor(runtime, zone)))
        if runtime.plant.zone_loops(zone.slug):
            entities.append((zone.slug, ZoneDutyCycleSensor(runtime, zone)))
    entities.extend(
        (loop.zone, LoopRuntimeSensor(runtime, loop)) for loop in runtime.plant.all_loops
    )
    async_add_plant_entities(runtime, "sensor", async_add_entities, entities)
