"""One pure evaluation: from configuration, observations, and state to the desired state.

``step()`` is the whole control policy. It reads a snapshot of what the runtime
observed, the State persisted by the previous evaluation, and the time, and
returns the next State, the desired state of every output, and the seconds until
the next evaluation is due. It never talks to Home Assistant; the runtime builds
``Observations`` from entity states, and the reconciler in ``reconcile`` drives
the outputs to the desired state.

Times are POSIX timestamps in seconds from the wall clock, the same clock that
stamps each observation. The clock may step backwards, so an observation can
carry a time later than ``now``; ``step()`` must treat such an interval as not
yet elapsed rather than as negative.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from .model import (
    Desired,
    Mode,
    OutputRole,
    Plant,
    Preset,
    SwitchTarget,
)

# The guard blocks a cooling loop below the worst-case dew point plus this margin, in kelvin.
CONDENSATION_MARGIN: Final = 2.0
# A blocked guard releases only this far above the blocking threshold, in kelvin.
GUARD_RELEASE: Final = 1.0


# Observations


@dataclass(frozen=True, slots=True)
class Reading:
    """A numeric sensor as observed."""

    # None while the sensor is unavailable, unknown, or not a number.
    value: float | None
    # When the sensor last reported, changed or not; a reading older than its
    # ``max_age`` is stale.
    updated: float


@dataclass(frozen=True, slots=True)
class AreaSensors:
    """The temperature and humidity sensor an area currently names, if any."""

    temperature: str | None = None
    humidity: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalThermostatState:
    """A digital thermostat's restored climate entity."""

    hvac_mode: Mode
    # The manual target; a preset the zone's thermostat defines overrides it.
    target: float
    preset: Preset | None = None


@dataclass(frozen=True, slots=True)
class ExternalThermostatState:
    """An external thermostat's normalized ``hvac_action``."""

    # HEAT for heating or preheating, COOL for cooling, OFF for idle or off, and
    # None while the entity is unavailable or reports anything else.
    action: Mode | None


type ThermostatState = DigitalThermostatState | ExternalThermostatState


@dataclass(frozen=True, slots=True)
class SwitchState:
    """A switch, valve, or binary sensor as observed."""

    # None while the entity is unavailable or unknown.
    on: bool | None
    # When the observed state last changed (``last_changed``), including a
    # change to or from unavailable.
    since: float


@dataclass(frozen=True, slots=True)
class OptionState:
    """A select as observed."""

    option: str | None
    since: float


@dataclass(frozen=True, slots=True)
class ValueState:
    """A number as observed; used by the setpoint strategy from iteration 2."""

    value: float | None
    since: float


type OutputState = SwitchState | OptionState | ValueState


@dataclass(frozen=True, slots=True)
class Observations:
    """One snapshot of everything ``step()`` reads, taken by the runtime."""

    # The Plant mode the mode select requests.
    mode: Mode
    # The Control equipment switch.
    control: bool
    # The output entities the owner has confirmed Hydronicus may command.
    armed: frozenset[str]
    # Every output of ``Plant.outputs()``; a missing entity counts as unavailable.
    outputs: Mapping[str, OutputState] = field(default_factory=dict)
    # Every valve readiness binary sensor.
    readiness: Mapping[str, SwitchState] = field(default_factory=dict)
    # Every numeric sensor the Plant reads: zone temperature and humidity,
    # explicit or named by an area, pump supply, and loop surface temperatures.
    sensors: Mapping[str, Reading] = field(default_factory=dict)
    # Each covered area's current sensors, resolved by the runtime on every evaluation.
    areas: Mapping[str, AreaSensors] = field(default_factory=dict)
    # Each zone's thermostat, by zone slug.
    thermostats: Mapping[str, ThermostatState] = field(default_factory=dict)


# State


@dataclass(frozen=True, slots=True)
class DemandState:
    """A zone's demand decision and when it last changed, for the minimum durations."""

    on: bool
    since: float


@dataclass(frozen=True, slots=True)
class GuardState:
    """A cooling loop's condensation guard and when it last changed, for its minimum time."""

    blocked: bool
    since: float


@dataclass(frozen=True, slots=True)
class State:
    """What ``step()`` carries from one evaluation to the next.

    The runtime persists it with ``to_dict`` after every evaluation that changes
    it and restores it with ``from_dict`` before the first evaluation, so a
    reload or restart continues every timer. The runtime reads only ``live``;
    the other fields belong to ``step()``.
    """

    # Outputs are commanded: Control equipment is on, or it was turned off and
    # the off-mode sequence has not finished. False is Dry run.
    live: bool = False
    # The mode the Plant runs in now, which lags the requested mode during a changeover.
    mode: Mode = Mode.OFF
    # The last heat or cool mode that ran, and when its last loop stopped; the
    # opposite mode starts only ``mode_dwell`` after that.
    last_mode: Mode = Mode.OFF
    last_mode_ended: float | None = None
    # The source request of the previous evaluation, which ``with_source`` loops
    # follow, and when it last changed, for min_on, min_off, and post-run.
    source_request: bool = False
    source_changed: float | None = None
    # Each zone's demand, by zone slug.
    demands: Mapping[str, DemandState] = field(default_factory=dict)
    # Each cooling loop's condensation guard, by ``str(LoopRef)``.
    guards: Mapping[str, GuardState] = field(default_factory=dict)
    # When each switched pump's overrun started, by pump slug.
    overruns: Mapping[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-friendly data that ``from_dict`` reads back."""
        return {
            "live": self.live,
            "mode": self.mode.value,
            "last_mode": self.last_mode.value,
            "last_mode_ended": self.last_mode_ended,
            "source_request": self.source_request,
            "source_changed": self.source_changed,
            "demands": {
                slug: {"on": demand.on, "since": demand.since}
                for slug, demand in self.demands.items()
            },
            "guards": {
                ref: {"blocked": guard.blocked, "since": guard.since}
                for ref, guard in self.guards.items()
            },
            "overruns": dict(self.overruns),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> State:
        """Read persisted data; a missing key takes its initial value."""
        return cls(
            live=bool(data.get("live", False)),
            mode=Mode(data.get("mode", Mode.OFF)),
            last_mode=Mode(data.get("last_mode", Mode.OFF)),
            last_mode_ended=_optional_float(data.get("last_mode_ended")),
            source_request=bool(data.get("source_request", False)),
            source_changed=_optional_float(data.get("source_changed")),
            demands={
                slug: DemandState(bool(value["on"]), float(value["since"]))
                for slug, value in data.get("demands", {}).items()
            },
            guards={
                ref: GuardState(bool(value["blocked"]), float(value["since"]))
                for ref, value in data.get("guards", {}).items()
            },
            overruns={slug: float(value) for slug, value in data.get("overruns", {}).items()},
        )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


# Evaluation


def step(
    plant: Plant, observations: Observations, state: State, now: float
) -> tuple[State, Desired, float | None]:
    """Return the next State, the desired state, and the seconds until the next evaluation.

    The seconds are None when only a change of observation needs a new
    evaluation. Safe shutdown is this same evaluation with the Plant mode
    forced to off.

    This is a stub until phase R3: it returns the initial State and desires
    every switch off, so the simulator's scenarios and properties fail.
    """
    del observations, state, now
    outputs = {
        entity: SwitchTarget(on=False)
        for entity, role in plant.outputs().items()
        if role is not OutputRole.SOURCE_MODE
    }
    desired = Desired(
        outputs=outputs, source_request=False, mode=Mode.OFF, flow_setpoint=None, reasons={}
    )
    return State(), desired, None
