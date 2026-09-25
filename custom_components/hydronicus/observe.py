"""Home Assistant states read as the observations that ``step()`` takes.

Everything here is a pure reading of ``State`` objects: output feedback,
readiness sensors, numeric sensors normalized by their unit, and external
thermostats. ``OutputMemory`` keeps when each output last changed across a
reload, a Home Assistant restart, and a spell of unavailability, which Home
Assistant's own ``last_changed`` does not.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Any, Final

from homeassistant.components.climate import ATTR_HVAC_ACTION
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import State
from homeassistant.util.unit_conversion import TemperatureConverter

from .core.demand import external_action
from .core.step import ExternalThermostatState, Reading

# A switch or valve is on while it shows one of these, and off while it shows one
# of the others. A valve that is opening was commanded open and one that is
# closing was commanded closed, as a switch would show.
_ON_STATES: Final = frozenset({"on", "open", "opening"})
_OFF_STATES: Final = frozenset({"off", "closed", "closing"})
_MISSING: Final = frozenset({STATE_UNAVAILABLE, STATE_UNKNOWN})


class SensorKind(StrEnum):
    """What a numeric sensor measures, which sets its unit policy and plausible range."""

    # Room air and heated or cooled surfaces.
    AIR = "air"
    # Supply water.
    WATER = "water"
    HUMIDITY = "humidity"


@dataclass(frozen=True, slots=True)
class _Plausible:
    """An inclusive band of physically plausible readings after unit normalization."""

    minimum: float
    maximum: float


# Wide enough for unheated spaces and saunas, and rejects sensor fault values such
# as 0 K or -127 °C. Pressurized water can run above 100 °C.
_PLAUSIBLE: Final = {
    SensorKind.AIR: _Plausible(-50.0, 100.0),
    SensorKind.WATER: _Plausible(-50.0, 150.0),
    SensorKind.HUMIDITY: _Plausible(0.0, 100.0),
}


def switch_value(state: State | None) -> bool | None:
    """Return whether a switch, valve, or binary sensor is on; None while it is not known."""
    if state is None:
        return None
    if state.state in _ON_STATES:
        return True
    if state.state in _OFF_STATES:
        return False
    return None


def option_value(state: State | None) -> str | None:
    """Return a select's option; None while it is unavailable or unknown."""
    if state is None or state.state in _MISSING:
        return None
    return state.state


def number_value(state: State | None) -> float | None:
    """Return a number entity's finite value, or None."""
    if state is None:
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    return value if isfinite(value) else None


def celsius_from_unit(value: float, unit: object) -> float | None:
    """Return a temperature in Celsius, or None in a unit that is not a temperature.

    A reading without a unit is taken as Celsius.
    """
    if unit is None or unit == "" or unit == UnitOfTemperature.CELSIUS:
        return value
    if unit not in TemperatureConverter.VALID_UNITS:
        return None
    return TemperatureConverter.convert(value, str(unit), UnitOfTemperature.CELSIUS)


def humidity_from_unit(value: float, unit: object) -> float | None:
    """Return a relative humidity in percent, or None in any other unit."""
    if unit is None or unit == "" or unit == PERCENTAGE:
        return value
    return None


def reading(state: State | None, kind: SensorKind, now: float) -> Reading:
    """Read a numeric sensor, normalized to Celsius or percent, when it last reported.

    A reading in an unsupported unit or outside the plausible band carries no
    value, so the zone or guard that needs it fails closed.
    """
    if state is None:
        return Reading(None, now)
    updated = state.last_reported_timestamp
    try:
        value = float(state.state)
    except ValueError:
        return Reading(None, updated)
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    normalize = humidity_from_unit if kind is SensorKind.HUMIDITY else celsius_from_unit
    normalized = normalize(value, unit)
    plausible = _PLAUSIBLE[kind]
    if (
        normalized is None
        or not isfinite(normalized)
        or not plausible.minimum <= normalized <= plausible.maximum
    ):
        return Reading(None, updated)
    return Reading(normalized, updated)


def external_thermostat(state: State | None) -> ExternalThermostatState:
    """Normalize an external climate entity's ``hvac_action``; unavailable blocks the zone."""
    if state is None or state.state in _MISSING:
        return ExternalThermostatState(None)
    action = state.attributes.get(ATTR_HVAC_ACTION)
    return ExternalThermostatState(
        external_action(None if action is None else str(action), state.state)
    )


@dataclass(frozen=True, slots=True)
class Remembered:
    """An output's last known value and when it took that value."""

    value: bool | str | float
    since: float


class OutputMemory:
    """When each output last changed its known value.

    Home Assistant resets ``last_changed`` when it restarts and when an entity
    returns from unavailable, which would make a valve open for hours look as if
    it had just opened and stop its pump (defect 7). The memory keeps an output's
    last known value with the time it took that value, and while the output
    shows the same value again, its ``since`` stays. The runtime updates it on
    every state change of an output and persists it with the step State.
    """

    def __init__(self, remembered: Mapping[str, Remembered] | None = None) -> None:
        self._remembered: dict[str, Remembered] = dict(remembered or {})

    def since(self, entity: str, value: bool | str | float | None, changed: float) -> float:
        """Record an observed value and return when the output took it.

        ``changed`` is Home Assistant's ``last_changed`` of the state. An unknown
        value leaves the memory as it was.
        """
        if value is None:
            return changed
        known = self._remembered.get(entity)
        if known is not None and known.value == value:
            return known.since
        self._remembered[entity] = Remembered(value, changed)
        return changed

    def forget_except(self, entities: set[str]) -> None:
        """Drop outputs the Plant no longer has."""
        for entity in set(self._remembered) - entities:
            del self._remembered[entity]

    def to_dict(self) -> dict[str, Any]:
        return {
            entity: {"value": known.value, "since": known.since}
            for entity, known in sorted(self._remembered.items())
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OutputMemory:
        remembered: dict[str, Remembered] = {}
        for entity, known in data.items():
            if not isinstance(known, Mapping):
                continue
            value, since = known.get("value"), known.get("since")
            if isinstance(value, bool | str | int | float) and isinstance(since, int | float):
                remembered[entity] = Remembered(value, float(since))
        return cls(remembered)
