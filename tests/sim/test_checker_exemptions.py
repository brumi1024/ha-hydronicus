"""Exemptions of the invariant checker that random traces reach only rarely."""

from __future__ import annotations

from custom_components.hydronicus.core.model import (
    DigitalThermostat,
    Loop,
    LoopRef,
    LoopRun,
    Mode,
    Plant,
    Pump,
    RunKind,
    Sensor,
    Valve,
    Zone,
)
from custom_components.hydronicus.core.step import DigitalThermostatState
from tests.sim.strategies import SetMode, SpontaneousOff, Trace, run

_VALVES = ("switch.shared_valve_0", "switch.shared_valve_1")
_PLANT = Plant(
    id="checker",
    name="Checker",
    pumps=(Pump("p0", "switch.p0_pump", overrun=0.0),),
    loops=(
        Loop(
            ref=LoopRef(None, "shared"),
            valves=tuple(Valve(entity, opening_time=30.0) for entity in _VALVES),
            pump="p0",
            modes=frozenset({Mode.HEAT}),
            runs=LoopRun(RunKind.WITH_ZONES, ("z0",)),
        ),
    ),
    zones=(
        Zone(
            slug="z0",
            temperature=(Sensor("sensor.z0_temperature"),),
            thermostat=DigitalThermostat(min_on=0.0, min_off=0.0),
        ),
    ),
)


def test_a_pump_with_no_loop_that_could_open_again_is_beyond_control() -> None:
    """Both valves close by themselves under an unarmed pump, and only one valve is armed.

    Opening the armed valve again cannot give the pump a path while the unarmed
    one stays shut, so invariant 2 is exempt although one closed valve is commandable.
    """
    run(
        _PLANT,
        Trace(
            mode=Mode.HEAT,
            control=True,
            armed=frozenset({_VALVES[0]}),
            running=("shared",),
            sensors=(("sensor.z0_temperature", 18.0),),
            thermostats=(("z0", DigitalThermostatState(Mode.HEAT, 21.0)),),
            events=(
                (1.0, SpontaneousOff(_VALVES[0])),
                (2.0, SpontaneousOff(_VALVES[1])),
                (3.0, SetMode(Mode.OFF, False)),
                (60.0, SetMode(Mode.HEAT, False)),
            ),
        ),
    )
