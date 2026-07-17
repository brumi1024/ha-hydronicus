"""Home Assistant runtime boundary for a hydronic plant.

Hardware observation and service execution will be added here in later milestones.
The initial vertical slice is intentionally shadow-only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_NAME, CONF_PLANT_ID, CONF_SHADOW_MODE
from .core.configuration import plant_configuration_from_entry_data
from .core.controller import evaluate
from .core.model import (
    CompiledPlant,
    Evaluation,
    PlantSnapshot,
    RuntimeState,
    TemperatureObservation,
)
from .core.topology import compile_topology


@dataclass(slots=True)
class HydronicRuntime:
    """Runtime data retained for one configured plant."""

    plant_id: str
    name: str
    shadow_mode: bool
    plant: CompiledPlant
    runtime_state: RuntimeState = field(default_factory=RuntimeState)
    evaluation: Evaluation | None = None
    snapshot: PlantSnapshot | None = None
    _hass: HomeAssistant | None = None
    _remove_state_listener: Callable[[], None] | None = None
    _listeners: set[Callable[[], None]] = field(default_factory=set)

    @classmethod
    def from_entry(cls, entry: Any) -> HydronicRuntime:
        """Construct safe runtime data from a config entry."""
        plant = compile_topology(plant_configuration_from_entry_data(entry.data))
        return cls(
            plant_id=str(entry.data.get(CONF_PLANT_ID, getattr(entry, "entry_id", "plant"))),
            name=str(entry.data.get(CONF_NAME, getattr(entry, "title", "Hydronic plant"))),
            shadow_mode=bool(entry.data.get(CONF_SHADOW_MODE, True)),
            plant=plant,
        )

    async def async_start(self, hass: HomeAssistant) -> None:
        """Observe configured sensors and evaluate the shadow plan without service calls."""
        self._hass = hass
        await self.async_refresh(hass)
        sensor_ids = [zone.temperature_sensor for zone in self.plant.zones.values()]
        self._remove_state_listener = async_track_state_change_event(
            hass, sensor_ids, self._async_handle_state_change
        )

    async def async_stop(self) -> None:
        """Remove runtime listeners without changing any physical equipment."""
        if self._remove_state_listener is not None:
            self._remove_state_listener()
            self._remove_state_listener = None
        self._hass = None

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register an entity update callback."""
        self._listeners.add(listener)

        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener

    @callback
    def _async_handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Re-evaluate after a configured temperature sensor changes."""
        if self._hass is not None:
            self._hass.async_create_task(self.async_refresh(self._hass))

    async def async_refresh(self, hass: HomeAssistant) -> None:
        """Read sensor states, evaluate the controller, and notify shadow entities."""
        observations: dict[str, TemperatureObservation] = {}
        for zone in self.plant.zones.values():
            state = hass.states.get(zone.temperature_sensor)
            value: float | None
            try:
                value = float(state.state) if state is not None else None
            except ValueError:
                value = None
            observations[zone.temperature_sensor] = TemperatureObservation(
                value=value,
                observed_at=state.last_updated if state is not None else None,
            )
        self.snapshot = PlantSnapshot(observations)
        result = evaluate(self.plant, self.snapshot, self.runtime_state, datetime.now(UTC))
        self.runtime_state = result.next_runtime
        self.evaluation = result
        for listener in self._listeners:
            listener()
