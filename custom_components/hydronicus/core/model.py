"""The Plant: an optional source, its pumps, its zones, and its loops.

Every type is a frozen, slotted value. A Plant is built by ``plant_file`` from a
plant file or from stored data, and ``plant_file.validate_plant`` checks the
relationships between its objects. Objects are addressed by slugs, which never
change and form unique IDs with the Plant ID; names are separate and optional,
and a missing name reads as the slug in words.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
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


class SourceStrategy(StrEnum):
    """How Hydronicus asks the source for heat or cooling."""

    # Ask for heat or cooling and let the source choose its flow temperature.
    REQUEST = "request"
    # Also write a flow setpoint; reserved for iteration 2.
    SETPOINT = "setpoint"


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
DEFAULT_OVERRUN: Final = 180.0
DEFAULT_OPENING_TIME: Final = 180.0
DEFAULT_MAX_AGE: Final = 1800.0
DEFAULT_SOURCE_TITLE: Final = "Heat source"


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
    strategy: SourceStrategy = SourceStrategy.REQUEST
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
    min_on: float = 0.0
    min_off: float = 0.0
    # The distance to target, in kelvin, over which the demand level rises from 0 to 1.
    proportional_band: float = 1.0

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

    @property
    def cools(self) -> bool:
        return any(loop.cools for loop in self.loops)

    @property
    def title(self) -> str:
        return self.name or title_from_slug(self.slug)


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


@dataclass(frozen=True, slots=True)
class ValueTarget:
    """A number that should hold a value."""

    value: float


type OutputTarget = SwitchTarget | OptionTarget | ValueTarget


@dataclass(frozen=True, slots=True)
class Desired:
    """What every output should be now, computed by each evaluation."""

    outputs: Mapping[str, OutputTarget]
    source_request: bool
    # The mode the outputs run in now: during a changeover it stays the old mode
    # until the old mode's loops have stopped, and it is off during the dwell.
    mode: Mode
    # Always None until the setpoint strategy arrives in iteration 2.
    flow_setpoint: float | None
    # Why, per zone, loop, and output.
    reasons: Mapping[str, str]
