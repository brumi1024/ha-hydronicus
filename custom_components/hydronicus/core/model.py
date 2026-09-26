"""The Plant: an optional source, its pumps, its zones, and its loops.

Every type is a frozen, slotted value. A Plant is built by ``plant_file`` from a
plant file or from stored data, and ``plant_file.validate_plant`` checks the
relationships between its objects. Objects are addressed by slugs, which never
change and form unique IDs with the Plant ID; names are separate and optional,
and a missing name reads as the slug in words.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final


class Mode(StrEnum):
    """The Plant mode, which a select chooses."""

    OFF = "off"
    HEAT = "heat"
    COOL = "cool"


class MinFlow(StrEnum):
    """How a pump is protected against running without flow."""

    # The pump needs an open loop while it runs.
    PATH = "path"
    # A separator, buffer, or bypass gives the pump a path whatever the loops do.
    GUARANTEED = "guaranteed"


class Aggregation(StrEnum):
    """How a zone combines its temperature readings."""

    MEAN = "mean"
    MIN = "min"
    MAX = "max"


class Preset(StrEnum):
    """A digital thermostat preset with its own target."""

    COMFORT = "comfort"
    ECO = "eco"
    AWAY = "away"


class RunKind(StrEnum):
    """What makes a loop wanted."""

    # A zone loop runs when its zone demands in the current mode.
    ZONE = "zone"
    # A plant loop that runs while the source is requested.
    WITH_SOURCE = "with_source"
    # A plant loop that runs while any of a set of zones demands.
    WITH_ZONES = "with_zones"


class OutputRole(StrEnum):
    """The one role an output entity has in a Plant."""

    SOURCE_REQUEST = "source_request"
    SOURCE_MODE = "source_mode"
    PUMP = "pump"
    VALVE = "valve"


DEFAULT_MODE_DWELL: Final = 3600.0
DEFAULT_POST_RUN: Final = 180.0
DEFAULT_MIN_ON: Final = 600.0
DEFAULT_MIN_OFF: Final = 600.0
# A digital thermostat holds each demand decision this long, in seconds, so a
# short dip does not open a slow thermoelectric valve, which takes about three
# minutes, and close it again before its pump ever starts.
DEFAULT_DEMAND_MIN_ON: Final = 600.0
DEFAULT_DEMAND_MIN_OFF: Final = 600.0
DEFAULT_OVERRUN: Final = 180.0
DEFAULT_OPENING_TIME: Final = 180.0
# A zone or area sensor's reading is stale this long after its last report. Many
# battery sensors report only on change, with a heartbeat about once an hour.
DEFAULT_MAX_AGE: Final = 3600.0
DEFAULT_SOURCE_TITLE: Final = "Heat source"
# While cooling, a loop's surface stays at or above this, in °C: the comfortable
# floor minimum of ISO 7730 and REHVA. A ceiling may run colder.
DEFAULT_SURFACE_MINIMUM: Final = 20.0
# While cooling, a zone's highest humidity stays at or below this, in percent.
DEFAULT_MAX_HUMIDITY: Final = 70.0
# A window counts as open once it has read open this long, and as closed once
# every window of the zone has read closed this long, in seconds.
DEFAULT_WINDOW_OPEN_DELAY: Final = 60.0
DEFAULT_WINDOW_CLOSE_DELAY: Final = 60.0
# An idle switched pump or valve is exercised once it has not been seen on for a
# week, and an exercised pump runs for a minute, so neither seizes.
DEFAULT_EXERCISE_INTERVAL: Final = 604800.0
DEFAULT_EXERCISE_RUN: Final = 60.0
# A zone whose coldest reading falls below this, in °C, is heated whatever its thermostat says.
DEFAULT_FROST_PROTECTION: Final = 5.0
# Frost protection heats until the coldest reading is this far above its temperature, in kelvin.
FROST_PROTECTION_RELEASE: Final = 1.0


def title_from_slug(slug: str) -> str:
    """Return the name a slug reads as, such as ``Living area`` for ``living_area``."""
    return slug.replace("_", " ").capitalize()


@dataclass(frozen=True, slots=True)
class LoopRef:
    """The address of a loop: its zone's slug, or None for a plant loop, and its slug."""

    zone: str | None
    loop: str

    def __str__(self) -> str:
        return self.loop if self.zone is None else f"{self.zone}.{self.loop}"

    @classmethod
    def parse(cls, text: str) -> LoopRef:
        """Read ``<zone>.<loop>`` or a plant loop's slug; raise ``ValueError`` otherwise."""
        parts = text.split(".")
        if len(parts) > 2 or not all(parts):
            raise ValueError(f"Not a loop reference: {text!r}")
        return cls(None, parts[0]) if len(parts) == 1 else cls(parts[0], parts[1])


@dataclass(frozen=True, slots=True)
class LoopRun:
    """When a loop runs; ``zones`` is set only for ``WITH_ZONES``."""

    kind: RunKind
    zones: tuple[str, ...] = ()


RUNS_WITH_ZONE: Final = LoopRun(RunKind.ZONE)
RUNS_WITH_SOURCE: Final = LoopRun(RunKind.WITH_SOURCE)


@dataclass(frozen=True, slots=True)
class Valve:
    """A valve that Hydronicus opens and closes as part of a loop."""

    entity: str
    opening_time: float = DEFAULT_OPENING_TIME
    # A binary sensor that confirms the valve is open, instead of its opening time.
    readiness: str | None = None


@dataclass(frozen=True, slots=True)
class Pump:
    """A circulator that Hydronicus switches, or that the source drives."""

    slug: str
    # None when the source drives the pump and Hydronicus never commands it.
    switch: str | None
    overrun: float = DEFAULT_OVERRUN
    min_flow: MinFlow = MinFlow.PATH
    # Loops held open for a source-driven ``path`` pump while it may run.
    min_flow_loops: tuple[LoopRef, ...] = ()
    supply_temperature: str | None = None
    name: str | None = None
    # A binary sensor on the pump's supply pipe that reads on at condensation; it
    # blocks the cooling of every loop of the pump.
    condensation_switch: str | None = None

    @property
    def driven_by_source(self) -> bool:
        return self.switch is None

    @property
    def title(self) -> str:
        return self.name or title_from_slug(self.slug)


@dataclass(frozen=True, slots=True)
class Loop:
    """A flow path: zero or more valves that open together, and exactly one pump."""

    ref: LoopRef
    valves: tuple[Valve, ...]
    pump: str
    modes: frozenset[Mode]
    runs: LoopRun
    # The loop's own condensation reference, besides its pump's supply sensor.
    surface_temperature: str | None = None
    name: str | None = None
    # A binary sensor that reads on at condensation, besides its pump's.
    condensation_switch: str | None = None
    # The lowest surface temperature while cooling, in °C; None turns it off. It
    # needs ``surface_temperature``.
    surface_minimum: float | None = DEFAULT_SURFACE_MINIMUM

    @property
    def slug(self) -> str:
        return self.ref.loop

    @property
    def zone(self) -> str | None:
        return self.ref.zone

    @property
    def cools(self) -> bool:
        return Mode.COOL in self.modes

    @property
    def title(self) -> str:
        return self.name or title_from_slug(self.slug)


@dataclass(frozen=True, slots=True)
class SourceModeSelect:
    """A select entity that switches the source between heating and cooling."""

    entity: str
    heat: str
    cool: str

    def option(self, mode: Mode) -> str | None:
        """Return the option for a Plant mode, or None for off."""
        return {Mode.HEAT: self.heat, Mode.COOL: self.cool}.get(mode)


@dataclass(frozen=True, slots=True)
class Source:
    """The generator Hydronicus asks for heat or cooling; at most one per Plant."""

    request: str
    mode: SourceModeSelect | None = None
    post_run: float = DEFAULT_POST_RUN
    min_on: float = DEFAULT_MIN_ON
    min_off: float = DEFAULT_MIN_OFF
    name: str | None = None

    @property
    def title(self) -> str:
        return self.name or DEFAULT_SOURCE_TITLE


@dataclass(frozen=True, slots=True)
class Sensor:
    """An explicit temperature or humidity sensor of a zone."""

    entity: str
    required: bool = True
    max_age: float = DEFAULT_MAX_AGE


@dataclass(frozen=True, slots=True)
class ZoneArea:
    """A Home Assistant area that a zone covers, with the settings of its sensors."""

    area: str
    required: bool = False
    max_age: float = DEFAULT_MAX_AGE


@dataclass(frozen=True, slots=True)
class DigitalThermostat:
    """A Hydronicus climate entity that owns a zone's target and demand."""

    target: float = 21.0
    # Preset targets in the order of ``Preset``.
    presets: tuple[tuple[Preset, float], ...] = ()
    heat_start_delta: float = 0.3
    heat_stop_delta: float = 0.1
    cool_start_delta: float = 0.3
    cool_stop_delta: float = 0.1
    min_on: float = DEFAULT_DEMAND_MIN_ON
    min_off: float = DEFAULT_DEMAND_MIN_OFF

    @property
    def preset_targets(self) -> Mapping[Preset, float]:
        return dict(self.presets)


@dataclass(frozen=True, slots=True)
class ExternalThermostat:
    """An existing climate entity whose ``hvac_action`` is a zone's demand; never commanded."""

    entity: str


type Thermostat = DigitalThermostat | ExternalThermostat


@dataclass(frozen=True, slots=True)
class Zone:
    """The space one thermostat controls, with its areas, sensors, and loops."""

    slug: str
    loops: tuple[Loop, ...] = ()
    areas: tuple[ZoneArea, ...] = ()
    temperature: tuple[Sensor, ...] = ()
    humidity: tuple[Sensor, ...] = ()
    aggregation: Aggregation = Aggregation.MEAN
    thermostat: Thermostat = DigitalThermostat()
    name: str | None = None
    # Binary sensors that read on while a window is open; an open window turns
    # the zone's demand off.
    windows: tuple[str, ...] = ()
    window_open_delay: float = DEFAULT_WINDOW_OPEN_DELAY
    window_close_delay: float = DEFAULT_WINDOW_CLOSE_DELAY
    # The highest humidity at which the loops that read the zone's dew point may
    # cool, in percent; None turns the cutoff off.
    max_humidity: float | None = DEFAULT_MAX_HUMIDITY

    @property
    def cools(self) -> bool:
        return any(loop.cools for loop in self.loops)

    @property
    def title(self) -> str:
        return self.name or title_from_slug(self.slug)


@dataclass(frozen=True, slots=True)
class Exercise:
    """How often an idle pump or valve is exercised so it does not seize."""

    # Seconds a switched pump or a valve may stay unseen on before it is exercised.
    interval: float = DEFAULT_EXERCISE_INTERVAL
    # Seconds an exercised switched pump runs.
    run: float = DEFAULT_EXERCISE_RUN


DEFAULT_EXERCISE: Final = Exercise()


@dataclass(frozen=True, slots=True)
class Plant:
    """One config entry: an optional source, its pumps, its zones, and its plant loops."""

    id: str
    name: str
    mode_dwell: float = DEFAULT_MODE_DWELL
    source: Source | None = None
    pumps: tuple[Pump, ...] = ()
    # Plant loops, which no zone owns.
    loops: tuple[Loop, ...] = ()
    zones: tuple[Zone, ...] = ()
    # None turns the exercise of idle pumps and valves off.
    exercise: Exercise | None = DEFAULT_EXERCISE
    # The frost protection temperature in °C, or None to turn frost protection off.
    frost_protection: float | None = DEFAULT_FROST_PROTECTION

    @property
    def all_loops(self) -> tuple[Loop, ...]:
        """Return the plant loops, then each zone's loops."""
        return (*self.loops, *(loop for zone in self.zones for loop in zone.loops))

    def pump(self, slug: str) -> Pump:
        return _find(self.pumps, lambda pump: pump.slug == slug, slug)

    def zone(self, slug: str) -> Zone:
        return _find(self.zones, lambda zone: zone.slug == slug, slug)

    def loop(self, ref: LoopRef) -> Loop:
        return _find(self.all_loops, lambda loop: loop.ref == ref, str(ref))

    def dew_point_zones(self, loop: Loop) -> tuple[Zone, ...]:
        """Return the zones whose worst-case dew point guards a loop while it cools.

        A zone loop cools its own zone, a plant loop that runs with zones cools
        those, and one that runs with the source may cool while any zone calls.
        """
        match loop.runs.kind:
            case RunKind.ZONE:
                return tuple(zone for zone in self.zones if zone.slug == loop.zone)
            case RunKind.WITH_ZONES:
                return tuple(zone for zone in self.zones if zone.slug in loop.runs.zones)
            case _:
                return self.zones

    def pump_loops(self, slug: str) -> tuple[Loop, ...]:
        """Return every loop that a pump drives."""
        return tuple(loop for loop in self.all_loops if loop.pump == slug)

    def outputs(self) -> dict[str, OutputRole]:
        """Return every entity Hydronicus commands, with its role, in dependency order."""
        outputs: dict[str, OutputRole] = {}
        if self.source is not None:
            outputs.setdefault(self.source.request, OutputRole.SOURCE_REQUEST)
            if self.source.mode is not None:
                outputs.setdefault(self.source.mode.entity, OutputRole.SOURCE_MODE)
        for pump in self.pumps:
            if pump.switch is not None:
                outputs.setdefault(pump.switch, OutputRole.PUMP)
        for loop in self.all_loops:
            for valve in loop.valves:
                outputs.setdefault(valve.entity, OutputRole.VALVE)
        return outputs


def _find[T](items: tuple[T, ...], match: Callable[[T], bool], key: str) -> T:
    for item in items:
        if match(item):
            return item
    raise KeyError(key)


# Desired state


@dataclass(frozen=True, slots=True)
class SwitchTarget:
    """A switch or valve that should be on or off."""

    on: bool


@dataclass(frozen=True, slots=True)
class OptionTarget:
    """A select that should show an option."""

    option: str


type OutputTarget = SwitchTarget | OptionTarget


@dataclass(frozen=True, slots=True)
class Demand:
    """A zone's request: on or off in a thermostat mode."""

    mode: Mode
    on: bool
    reason: str


@dataclass(frozen=True, slots=True)
class Desired:
    """What every output should be now, computed by each evaluation."""

    outputs: Mapping[str, OutputTarget]
    source_request: bool
    # The mode the outputs run in now: during a changeover it stays the old mode
    # until the old mode's loops have stopped, and it is off during the dwell.
    mode: Mode
    # Why, per zone, loop, and output.
    reasons: Mapping[str, str]
    # Each zone's demand, by zone slug, which the entities publish.
    demands: Mapping[str, Demand] = field(default_factory=dict)
    # By zone slug, the required sensors whose readings are not usable, among the
    # readings the zone needs; the zone fails closed until they report again.
    blocking_sensors: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    # By loop that cools, ``str(LoopRef)``, its condensation inputs that are not
    # usable, in any mode: its pump's and its own condensation switch while
    # unavailable, unknown, or missing, and its pump's supply and its own surface
    # temperature while missing, stale, or not plausible. Its guard blocks until
    # they report again.
    blocking_condensation_inputs: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    # The zones that frost protection heats, whatever their thermostats say.
    frost_protection: tuple[str, ...] = ()
    # The slug of the pump whose idle switch or valves are being exercised, if any.
    exercise: str | None = None
