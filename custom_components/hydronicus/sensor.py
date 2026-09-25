"""Read-only explanations for shadow controller decisions."""

from __future__ import annotations

from typing import Any, cast

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HydronicConfigEntry
from .const import (
    MAX_RECONCILIATION_INTERVAL_SECONDS,
    MIN_RECONCILIATION_INTERVAL_SECONDS,
    RECONCILIATION_INTERVAL_SECONDS,
)
from .core.model import PlantMode, SourceSelectionPhase
from .entity_device import plant_device_info, topology_device_info
from .entity_registration import async_add_plant_entities
from .runtime import HydronicRuntime

# Entities render one atomic runtime evaluation and never poll or call out.
PARALLEL_UPDATES = 0

_MAX_STATE_LENGTH = 255

# Raw enum states are part of the entity contract and never change; only their
# display is translated through the entity section of strings.json.
PLANT_MODE_OPTIONS = [mode.value for mode in PlantMode]
CONTROLLER_STATUS_OPTIONS = [
    "stopped",
    "safe_shutdown",
    "initializing",
    "blocked",
    *PLANT_MODE_OPTIONS,
]
RECONCILIATION_STATUS_OPTIONS = ["not_started", "changed", "unchanged"]
SOURCE_CHANGEOVER_OPTIONS = [phase.value for phase in SourceSelectionPhase]

# Prose, per-evaluation lists, deadlines, and countdowns change on almost every
# evaluation, so recording them would bloat history without adding value.
VOLATILE_ATTRIBUTES = frozenset(
    {
        "operations",
        "logic_summary",
        "warnings",
        "explanation",
        "aggregation_explanation",
        "deadline",
        "changeover_deadline",
        "dwell_remaining_seconds",
        "interlocks",
        "execution_failure",
        "stale_feedback",
    }
)


class _HydronicSensor(SensorEntity):
    """Keep runtime lookup, device binding, and updates consistent for all sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _unrecorded_attributes = VOLATILE_ATTRIBUTES
    _listen_for_runtime_updates = True

    def __init__(self, entry: HydronicConfigEntry) -> None:
        self._entry = entry
        runtime = self._runtime
        self._attr_device_info = plant_device_info(runtime)

    @property
    def _runtime(self) -> HydronicRuntime:
        """Resolve the current runtime after a config-entry reload."""
        return cast(HydronicRuntime, self._entry.runtime_data)

    async def async_added_to_hass(self) -> None:
        """Subscribe dynamic sensors to atomic runtime updates."""
        if self._listen_for_runtime_updates:
            self.async_on_remove(self._runtime.async_add_listener(self.async_write_ha_state))


class ControllerStatusSensor(_HydronicSensor):
    """Expose one low-cardinality plant status for Recorder and dashboards."""

    _attr_translation_key = "controller_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = CONTROLLER_STATUS_OPTIONS

    def __init__(self, entry: HydronicConfigEntry) -> None:
        """Bind the status to one plant runtime."""
        super().__init__(entry)
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_controller_status"

    @property
    def native_value(self) -> str:
        """Return a bounded, low-cardinality controller status."""
        return self._runtime.operational_status()

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the latest operation decisions beside the bounded status."""
        return {
            "dry_run": self._runtime.dry_run,
            "safe_shutdown_phase": self._runtime.runtime_state.safe_shutdown_phase.value,
            "operations": self._runtime.execution_summary(),
        }


class ReconciliationStatusSensor(_HydronicSensor):
    """Expose bounded reconciliation status without high-cardinality attributes."""

    _attr_translation_key = "reconciliation_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = RECONCILIATION_STATUS_OPTIONS

    def __init__(self, entry: HydronicConfigEntry) -> None:
        """Bind reconciliation telemetry to one plant runtime."""
        super().__init__(entry)
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_reconciliation_status"

    @property
    def native_value(self) -> str:
        """Return the latest bounded reconciliation outcome."""
        return self._runtime.last_reconciliation_status

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose only static scheduling policy, keeping Recorder cardinality low."""
        interval = min(
            max(float(RECONCILIATION_INTERVAL_SECONDS), MIN_RECONCILIATION_INTERVAL_SECONDS),
            MAX_RECONCILIATION_INTERVAL_SECONDS,
        )
        return {"interval_seconds": interval, "bounded": True}


class TopologyPreviewSensor(_HydronicSensor):
    """Expose the compiled plant graph in a persistent diagnostic entity."""

    _attr_translation_key = "topology_preview"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _listen_for_runtime_updates = False

    def __init__(self, entry: HydronicConfigEntry) -> None:
        """Bind the preview to one compiled plant runtime."""
        super().__init__(entry)
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_topology_preview"

    @property
    def native_value(self) -> str:
        """Summarize the graph size in zones and loops, within the state length limit."""
        zone_count = len(self._runtime.plant.zones)
        loop_count = len(self._runtime.plant.circuits)
        zone_noun = "zone" if zone_count == 1 else "zones"
        loop_noun = "loop" if loop_count == 1 else "loops"
        return f"{zone_count} {zone_noun}, {loop_count} {loop_noun}"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return every human-readable compiler decision as structured data."""
        return {
            "logic_summary": list(self._runtime.plant.logic_summary),
            "warnings": [
                {
                    "code": warning.code,
                    "message": warning.message,
                    "valve_id": warning.valve_id,
                    "circuit_ids": list(warning.circuit_ids),
                    "zone_ids": list(warning.zone_ids),
                }
                for warning in self._runtime.plant.warnings
            ],
            "routes": len(self._runtime.plant.routes),
            "valves": len(self._runtime.plant.valves),
            "pumps": len(self._runtime.plant.pumps),
        }


class ZoneExplanationSensor(_HydronicSensor):
    """Expose the last controller explanation for a comfort zone."""

    _attr_translation_key = "zone_explanation"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HydronicConfigEntry, zone_id: str, name: str) -> None:
        """Bind a diagnostic entity to one zone."""
        super().__init__(entry)
        self._zone_id = zone_id
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_{zone_id}_explanation"
        self._attr_device_info = topology_device_info(runtime, "zone", zone_id, name)

    @property
    def native_value(self) -> str | None:
        """Return the cached human-readable controller explanation."""
        if self._runtime.evaluation is None:
            return None
        return self._runtime.evaluation.diagnostics.zone_reasons.get(self._zone_id)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose structured controller status alongside the display explanation."""
        return _zone_diagnostic_attributes(self._runtime, self._zone_id)


class ZoneAggregateTemperatureSensor(_HydronicSensor):
    """Expose the temperature aggregate used by the controller."""

    _attr_translation_key = "zone_aggregate_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    # Unit conversion leaves float noise such as 18.000000000000004.
    _attr_suggested_display_precision = 1

    def __init__(self, entry: HydronicConfigEntry, zone_id: str, name: str) -> None:
        """Bind the aggregate to one comfort zone."""
        super().__init__(entry)
        self._zone_id = zone_id
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_{zone_id}_aggregate_temperature"
        self._attr_device_info = topology_device_info(runtime, "zone", zone_id, name)

    @property
    def native_value(self) -> float | None:
        """Return the aggregate from the last atomic evaluation."""
        return self._runtime.zone_current_temperature(self._zone_id)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose sensor-health details, and the sensors each covered area resolves to."""
        attributes = _zone_diagnostic_attributes(self._runtime, self._zone_id)
        if areas := self._runtime.zone_area_sensors(self._zone_id):
            attributes["areas"] = areas
        return attributes


class ZoneBlockedReasonSensor(_HydronicSensor):
    """Expose the structured sensor-health reason for one zone."""

    _attr_translation_key = "zone_blocked_reason"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HydronicConfigEntry, zone_id: str, name: str) -> None:
        """Bind the blocked reason to one comfort zone."""
        super().__init__(entry)
        self._zone_id = zone_id
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_{zone_id}_blocked_reason"
        self._attr_device_info = topology_device_info(runtime, "zone", zone_id, name)

    @property
    def native_value(self) -> str:
        """Return a stable sentinel when the zone is not blocked."""
        reason = self._runtime.zone_blocked_reason(self._zone_id) or "none"
        return reason[:_MAX_STATE_LENGTH]

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the structured block details."""
        return _zone_diagnostic_attributes(self._runtime, self._zone_id)


class RecommendedSourceSensor(_HydronicSensor):
    """Expose the current deterministic shadow source recommendation."""

    _attr_translation_key = "recommended_source"

    def __init__(self, entry: HydronicConfigEntry) -> None:
        """Bind the plant-level recommendation to the current runtime."""
        super().__init__(entry)
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_recommended_source"

    @property
    def native_value(self) -> str:
        """Return the stable source ID or an explicit no-source sentinel."""
        recommendation = self._runtime.source_recommendation()
        return recommendation.source_id if recommendation and recommendation.source_id else "none"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose source names, eligibility, and the human-readable explanation."""
        recommendation = self._runtime.source_recommendation()
        if recommendation is None:
            return {"eligible_source_ids": [], "explanation": "No source configured."}
        source = self._runtime.plant.sources.get(recommendation.source_id or "")
        return {
            "source_name": source.name if source is not None else None,
            "eligible_source_ids": list(recommendation.eligible_source_ids),
            "explanation": recommendation.explanation,
        }


class SourceRecommendationExplanationSensor(_HydronicSensor):
    """Expose the explanation for the source recommendation."""

    _attr_translation_key = "source_recommendation"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HydronicConfigEntry) -> None:
        """Bind the explanation to the current runtime."""
        super().__init__(entry)
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_source_recommendation"

    @property
    def native_value(self) -> str:
        """Return the current explanation, bounded for Home Assistant state storage."""
        recommendation = self._runtime.source_recommendation()
        if recommendation is None:
            return "No source configured."
        return recommendation.explanation[:_MAX_STATE_LENGTH]

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the stable recommendation ID and eligible IDs."""
        recommendation = self._runtime.source_recommendation()
        if recommendation is None:
            return {"source_id": None, "eligible_source_ids": []}
        return {
            "source_id": recommendation.source_id,
            "eligible_source_ids": list(recommendation.eligible_source_ids),
        }


class ActiveSourceSensor(_HydronicSensor):
    """Expose the source owning the latest guarded heating demand."""

    _attr_translation_key = "active_source"

    def __init__(self, entry: HydronicConfigEntry) -> None:
        super().__init__(entry)
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_active_source"

    @property
    def native_value(self) -> str:
        return self._runtime.runtime_state.selected_source_id or "none"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        selection = self._runtime.source_selection_diagnostic()
        recommendation = self._runtime.source_recommendation()
        return {
            "recommended_source_id": recommendation.source_id if recommendation else None,
            "target_source_id": getattr(selection, "target_source_id", None),
            "phase": getattr(getattr(selection, "phase", None), "value", None),
            "dwell_remaining_seconds": getattr(selection, "dwell_remaining_seconds", 0.0),
            "hydraulically_safe": getattr(selection, "hydraulically_safe", False),
            "explanation": getattr(selection, "explanation", None),
        }


class SourceChangeoverSensor(_HydronicSensor):
    """Expose the deterministic source selection phase and guard."""

    _attr_translation_key = "source_changeover"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = SOURCE_CHANGEOVER_OPTIONS

    def __init__(self, entry: HydronicConfigEntry) -> None:
        super().__init__(entry)
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_source_changeover"

    @property
    def native_value(self) -> str:
        selection = self._runtime.source_selection_diagnostic()
        return getattr(getattr(selection, "phase", None), "value", "idle")

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        selection = self._runtime.source_selection_diagnostic()
        recommendation = self._runtime.source_recommendation()
        return {
            "active_source_id": getattr(selection, "active_source_id", None),
            "target_source_id": getattr(selection, "target_source_id", None),
            "recommended_source_id": recommendation.source_id if recommendation else None,
            "dwell_remaining_seconds": getattr(selection, "dwell_remaining_seconds", 0.0),
            "hydraulically_safe": getattr(selection, "hydraulically_safe", False),
            "dry_run": self._runtime.dry_run,
            "explanation": getattr(selection, "explanation", None),
        }


class SourceDwellSensor(_HydronicSensor):
    """Expose remaining source minimum dwell time from the atomic evaluation."""

    _attr_translation_key = "source_dwell"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_display_precision = 0

    def __init__(self, entry: HydronicConfigEntry) -> None:
        super().__init__(entry)
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_source_dwell"

    @property
    def native_value(self) -> float:
        selection = self._runtime.source_selection_diagnostic()
        return float(getattr(selection, "dwell_remaining_seconds", 0.0))


class SourceBlockedReasonSensor(_HydronicSensor):
    """Expose a bounded source-specific block explanation."""

    _attr_translation_key = "source_blocked_reason"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HydronicConfigEntry, source_id: str, name: str) -> None:
        super().__init__(entry)
        self._source_id = source_id
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_{source_id}_blocked_reason"
        self._attr_device_info = topology_device_info(runtime, "source", source_id, name)

    @property
    def native_value(self) -> str:
        diagnostic = self._runtime.source_diagnostic(self._source_id)
        return str(getattr(diagnostic, "reason", "No source diagnostic."))[:_MAX_STATE_LENGTH]

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        diagnostic = self._runtime.source_diagnostic(self._source_id)
        return {
            "available": getattr(diagnostic, "available", None),
            "eligible": getattr(diagnostic, "eligible", False),
            "recommended": getattr(diagnostic, "recommended", False),
            "active": getattr(diagnostic, "active", False),
            "demand_requested": getattr(diagnostic, "demand_requested", False),
            "demand_permitted": getattr(diagnostic, "demand_permitted", False),
            "blocked": getattr(diagnostic, "blocked", False),
        }


class ZoneCoolingBlockedReasonSensor(_HydronicSensor):
    """Expose the cooling interlock explanation for one comfort zone."""

    _attr_translation_key = "zone_cooling_blocked_reason"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HydronicConfigEntry, zone_id: str, name: str) -> None:
        """Bind the cooling explanation to one comfort zone."""
        super().__init__(entry)
        self._zone_id = zone_id
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_{zone_id}_cooling_blocked_reason"
        self._attr_device_info = topology_device_info(runtime, "zone", zone_id, name)

    @property
    def native_value(self) -> str:
        """Return a stable sentinel when cooling is not blocked."""
        reason = self._runtime.cooling_zone_blocked_reason(self._zone_id) or "none"
        return reason[:_MAX_STATE_LENGTH]

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose structured cooling safety details."""
        return _cooling_diagnostic_attributes(self._runtime, self._zone_id)


class ZoneDewPointSensor(_HydronicSensor):
    """Expose the calculated zone dew point used by cooling safety."""

    _attr_translation_key = "zone_cooling_dew_point"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    # Unit conversion leaves float noise such as 18.000000000000004.
    _attr_suggested_display_precision = 1

    def __init__(self, entry: HydronicConfigEntry, zone_id: str, name: str) -> None:
        """Bind the dew-point diagnostic to one zone."""
        super().__init__(entry)
        self._zone_id = zone_id
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_{zone_id}_dew_point"
        self._attr_device_info = topology_device_info(runtime, "zone", zone_id, name)

    @property
    def native_value(self) -> float | None:
        """Return the latest calculated dew point."""
        return self._runtime.zone_dew_point(self._zone_id)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose cooling interlock diagnostics alongside the dew point."""
        return _cooling_diagnostic_attributes(self._runtime, self._zone_id)


class ZoneCondensationMarginSensor(_HydronicSensor):
    """Expose the lowest configured reference margin for a zone."""

    _attr_translation_key = "zone_cooling_condensation_margin"
    # A margin is a difference between two temperatures, so unit conversion
    # must scale it without the absolute-scale offset.
    _attr_device_class = SensorDeviceClass.TEMPERATURE_DELTA
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    # Unit conversion leaves float noise such as 18.000000000000004.
    _attr_suggested_display_precision = 1

    def __init__(self, entry: HydronicConfigEntry, zone_id: str, name: str) -> None:
        """Bind the condensation margin diagnostic to one zone."""
        super().__init__(entry)
        self._zone_id = zone_id
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_{zone_id}_condensation_margin"
        self._attr_device_info = topology_device_info(runtime, "zone", zone_id, name)

    @property
    def suggested_unit_of_measurement(self) -> str | None:
        """Suggest the unit system's temperature unit for a newly registered margin.

        Home Assistant converts absolute temperatures to the unit system on its own,
        but has no unit-system rule for temperature deltas. The registry stores this
        suggestion once, the first time it sees the entity. An entity registered
        before the delta class keeps its stored unit, because the sensor platform
        pins the previously registered unit when the device class changes.
        """
        if self.hass is None:
            return None
        return self.hass.config.units.temperature_unit

    @property
    def native_value(self) -> float | None:
        """Return the lowest usable reference margin."""
        return self._runtime.zone_condensation_margin(self._zone_id)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the configured and calculated safety state."""
        return _cooling_diagnostic_attributes(self._runtime, self._zone_id)


class ActuatorFeedbackReasonSensor(_HydronicSensor):
    """Expose the structured feedback or manual-intervention explanation."""

    _attr_translation_key = "actuator_feedback_reason"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HydronicConfigEntry, actuator_id: str, name: str) -> None:
        """Bind one diagnostic state to an actuator."""
        super().__init__(entry)
        self._actuator_id = actuator_id
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_{actuator_id}_feedback_reason"
        kind = "valve" if actuator_id in runtime.plant.valves else "pump"
        self._attr_device_info = topology_device_info(runtime, kind, actuator_id, name)

    @property
    def native_value(self) -> str:
        """Return a stable bounded diagnostic explanation."""
        failure = self._runtime.actuator_execution_failure(self._actuator_id)
        if failure is not None:
            return f"{failure.kind.value}: {failure.explanation}"[:_MAX_STATE_LENGTH]
        diagnostic = self._runtime.actuator_diagnostic(self._actuator_id)
        reason = str(getattr(diagnostic, "reason", "No actuator feedback diagnostic."))
        return reason[:_MAX_STATE_LENGTH]

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose structured mismatch and fail-closed details."""
        diagnostic = self._runtime.actuator_diagnostic(self._actuator_id)
        failure = self._runtime.actuator_execution_failure(self._actuator_id)
        return {
            "status": getattr(getattr(diagnostic, "status", None), "value", None),
            "mismatch": getattr(diagnostic, "mismatch", False),
            "blocked": getattr(diagnostic, "blocked", False),
            "expected": getattr(diagnostic, "expected", None),
            "observed": getattr(diagnostic, "observed", None),
            "stale_feedback": list(getattr(diagnostic, "stale_feedback", ())),
            "execution_failure_kind": getattr(getattr(failure, "kind", None), "value", None),
            "execution_failure": getattr(failure, "explanation", None),
        }


def _zone_diagnostic_attributes(runtime: Any, zone_id: str) -> dict[str, object]:
    """Build common structured attributes for all zone explanation entities."""
    aggregation = runtime.zone_aggregation(zone_id)
    decision = runtime.zone_decision(zone_id)
    attributes: dict[str, object] = {
        "blocked": runtime.zone_is_blocked(zone_id),
    }
    if aggregation is not None:
        attributes.update(
            {
                "usable_sensor_ids": list(aggregation.usable_sensor_ids),
                "excluded_optional_sensor_ids": list(aggregation.excluded_optional_sensor_ids),
                "blocking_required_sensor_ids": list(aggregation.blocking_required_sensor_ids),
                "aggregation_explanation": aggregation.explanation,
            }
        )
    if decision is not None:
        status = getattr(decision.status, "value", decision.status)
        attributes.update(
            {
                "decision_status": status,
                "demand": decision.demand,
                "deadline": (
                    decision.deadline.isoformat() if decision.deadline is not None else None
                ),
            }
        )
    return attributes


class PlantModeSensor(_HydronicSensor):
    """Expose the mode currently permitted to use shared equipment."""

    _attr_translation_key = "operating_mode"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = PLANT_MODE_OPTIONS

    def __init__(self, entry: HydronicConfigEntry) -> None:
        """Bind the active mode to the plant runtime."""
        super().__init__(entry)
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_operating_mode"

    @property
    def native_value(self) -> str:
        """Return the active, safety-permitted operating mode."""
        return self._runtime.active_mode().value

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose requested mode and transition state without prose parsing."""
        state = self._runtime.runtime_state
        return {
            "requested_mode": state.requested_mode.value,
            "changeover_phase": state.changeover_phase.value,
            "changeover_target_mode": (
                state.changeover_target_mode.value
                if state.changeover_target_mode is not None
                else None
            ),
            "changeover_deadline": (
                state.changeover_deadline.isoformat()
                if state.changeover_deadline is not None
                else None
            ),
            "explanation": self._runtime.mode_explanation(),
        }


class ModeChangeoverExplanationSensor(_HydronicSensor):
    """Explain why a requested mode is active, idle, or locked."""

    _attr_translation_key = "mode_changeover_explanation"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HydronicConfigEntry) -> None:
        """Bind the explanation to the plant runtime."""
        super().__init__(entry)
        runtime = self._runtime
        self._attr_unique_id = f"{runtime.plant_id}_mode_changeover_explanation"

    @property
    def native_value(self) -> str:
        """Return the bounded changeover explanation."""
        return self._runtime.mode_explanation()[:_MAX_STATE_LENGTH]

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the complete structured mode lockout."""
        state = self._runtime.runtime_state
        return {
            "requested_mode": state.requested_mode.value,
            "active_mode": state.plant_mode.value,
            "changeover_phase": state.changeover_phase.value,
            "changeover_target_mode": (
                state.changeover_target_mode.value
                if state.changeover_target_mode is not None
                else None
            ),
            "deadline": (
                state.changeover_deadline.isoformat()
                if state.changeover_deadline is not None
                else None
            ),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add read-only explanations for all configured zones."""
    runtime = entry.runtime_data
    parent_entities: list[SensorEntity] = [
        ControllerStatusSensor(entry),
        ReconciliationStatusSensor(entry),
        TopologyPreviewSensor(entry),
        PlantModeSensor(entry),
        ModeChangeoverExplanationSensor(entry),
    ]
    # Source selection has nothing to report on a Plant without a source.
    if runtime.plant.sources:
        parent_entities.extend(
            (
                ActiveSourceSensor(entry),
                SourceChangeoverSensor(entry),
                SourceDwellSensor(entry),
                RecommendedSourceSensor(entry),
                SourceRecommendationExplanationSensor(entry),
            )
        )
    subentry_entities: dict[str, list[SensorEntity]] = {}
    for source in runtime.plant.sources.values():
        entity = SourceBlockedReasonSensor(entry, source.id, source.name)
        if subentry_id := runtime.subentry_id_for(source.id):
            subentry_entities.setdefault(subentry_id, []).append(entity)
        else:
            parent_entities.append(entity)
    for zone in runtime.plant.zones.values():
        entities: list[SensorEntity] = [
            ZoneExplanationSensor(entry, zone.id, zone.name),
            ZoneAggregateTemperatureSensor(entry, zone.id, zone.name),
            ZoneBlockedReasonSensor(entry, zone.id, zone.name),
        ]
        if runtime.plant.zone_can_cool(zone.id):
            entities.extend(
                (
                    ZoneCoolingBlockedReasonSensor(entry, zone.id, zone.name),
                    ZoneDewPointSensor(entry, zone.id, zone.name),
                    ZoneCondensationMarginSensor(entry, zone.id, zone.name),
                )
            )
        if subentry_id := runtime.subentry_id_for(zone.id):
            subentry_entities.setdefault(subentry_id, []).extend(entities)
        else:
            parent_entities.extend(entities)
    if runtime.diagnostics_include_actuator_details:
        for valve in runtime.plant.valves.values():
            entity = ActuatorFeedbackReasonSensor(entry, valve.id, valve.name)
            if subentry_id := runtime.subentry_id_for(valve.id):
                subentry_entities.setdefault(subentry_id, []).append(entity)
            else:
                parent_entities.append(entity)
        # Pumps are Plant equipment, so their entities always belong to the parent.
        parent_entities.extend(
            ActuatorFeedbackReasonSensor(entry, pump.id, pump.name)
            for pump in runtime.plant.pumps.values()
        )
    async_add_plant_entities(
        runtime, "sensor", async_add_entities, parent_entities, subentry_entities
    )


def _cooling_diagnostic_attributes(runtime: HydronicRuntime, zone_id: str) -> dict[str, object]:
    """Build structured cooling diagnostics without parsing explanation text."""
    decision = runtime.cooling_zone_decision(zone_id)
    if decision is None:
        return {"cooling_blocked": False}
    return {
        "cooling_blocked": runtime.cooling_zone_is_blocked(zone_id),
        "cooling_demand": decision.demand,
        "cooling_decision_status": getattr(decision.status, "value", decision.status),
        "dew_point": decision.dew_point,
        "condensation_margin": decision.condensation_margin,
        "humidity_usable_sensor_ids": (
            list(decision.humidity_aggregation.usable_sensor_ids)
            if decision.humidity_aggregation is not None
            else []
        ),
        "humidity_blocking_required_sensor_ids": (
            list(decision.humidity_aggregation.blocking_required_sensor_ids)
            if decision.humidity_aggregation is not None
            else []
        ),
        "interlocks": [
            {
                "id": interlock.interlock_id,
                "status": interlock.status.value,
                "reason": interlock.reason,
            }
            for interlock in decision.interlocks
        ],
    }
