"""The control defects reproduced in v0.1.0, translated to the new model.

Each scenario builds the situation of one defect in ``docs/redesign-plan.md``
and asserts the behaviour the defect violated. Every scenario also checks the
invariants after every event.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from hydronicus_core.model import (
    RUNS_WITH_ZONE,
    DigitalThermostat,
    Loop,
    LoopRef,
    Mode,
    Plant,
    Preset,
    Sensor,
    SwitchTarget,
    Valve,
    Zone,
    ZoneArea,
)
from hydronicus_core.plant_file import validate_plant
from hydronicus_core.reconcile import BACKOFF_MAX
from hydronicus_core.step import DigitalThermostatState

from tests.sim.harness import Sim
from tests.sim.plants import (
    BOILER,
    FLOOR_PUMP,
    FLOOR_VALVE,
    LIVING_CEILING,
    REQUEST,
    SHARED_PUMP,
    SOURCE_MODE,
    THREE_LOOPS,
    TOWEL_PUMP,
    TWO_CEILINGS,
    ZONES,
    plant,
    reference_plant,
)
from tests.sim.world import FaultKind

REACTION = 15.0
ON = SwitchTarget(True)
OFF = SwitchTarget(False)


def _stub(reason: str) -> pytest.MarkDecorator:
    """Red until R3 replaces the stub ``step()`` and ``reconcile()``, which never act."""
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"R2 stub: {reason}")


def _order(sim: Sim, first: str, then: str) -> None:
    """``then`` turned off only after ``first`` had turned off."""
    first_off = [t for t, on in sim.switched(first) if not on]
    then_off = [t for t, on in sim.switched(then) if not on]
    assert first_off and then_off, f"{first} and {then} both turn off"
    assert then_off[-1] > first_off[-1], f"{then} closed before {first} was observed off"


def _running_reference(*, living_demands: bool) -> Sim:
    """The reference plant heating the living area, as found when the runtime starts."""
    sim = Sim(reference_plant(), mode=Mode.HEAT)
    for zone in ZONES:
        sim.set_zone_temperature(zone, 21.5)
    if living_demands:
        sim.set_zone_temperature("living_area", 19.5)
    return sim


@_stub("the stub never stops the seeded pumps after Control equipment turns off")
def test_defect_1_safe_shutdown_stops_every_pump_before_closing_their_valves() -> None:
    """Two pumps in overrun: both stop, and no valve closes under a running pump."""
    sim = _running_reference(living_demands=False)
    sim.seed_running("living_area.floor")
    sim.seed_on(TOWEL_PUMP)
    sim.start()
    sim.run_for(5.0)
    sim.set_control(False)
    sim.run_until_true(
        lambda: not sim.is_on(TOWEL_PUMP) and not sim.is_on(FLOOR_PUMP),
        180.0 + 2 * REACTION,
        "safe shutdown stops both pumps after their overruns",
    )
    sim.run_until_true(
        lambda: not sim.is_on(FLOOR_VALVE), 2 * REACTION, "the floor valve closes after its pump"
    )
    _order(sim, FLOOR_PUMP, FLOOR_VALVE)
    calls = len(sim.world.calls)
    sim.run_for(600.0)
    assert len(sim.world.calls) == calls, "Dry run sends nothing once the Plant has stopped"


@_stub("the stub reconciler never sends, let alone retries, the pump stop")
def test_defect_2_a_rejected_pump_stop_keeps_its_valve_open_and_is_retried() -> None:
    sim = _running_reference(living_demands=False)
    sim.seed_running("living_area.floor")
    sim.start()
    sim.fault(FLOOR_PUMP, FaultKind.REJECT, 600.0)
    sim.always_for(
        lambda: sim.is_on(FLOOR_VALVE), 400.0, "the valve stays open under the running pump"
    )
    stops = [call for call in sim.calls_to(FLOOR_PUMP) if call.target == OFF]
    assert len(stops) >= 3, f"the pump stop is retried, but it was sent {len(stops)} times"
    assert FLOOR_PUMP in sim.repairs(), "the pump that does not stop is reported as a Repair"
    assert sim.is_on(FLOOR_VALVE)
    sim.run_until_true(
        lambda: not sim.is_on(FLOOR_PUMP),
        200.0 + BACKOFF_MAX + REACTION,
        "the retried stop takes effect once the pump accepts it",
    )
    sim.run_until_true(
        lambda: not sim.is_on(FLOOR_VALVE), 2 * REACTION, "then the floor valve closes"
    )


@_stub("the stub never stops the shared pump after its overrun")
def test_defect_3_a_failed_valve_open_does_not_drop_the_pump_stop() -> None:
    sim = Sim(plant(SHARED_PUMP), mode=Mode.HEAT)
    sim.set_zone_temperature("study", 21.5)
    sim.set_zone_temperature("lounge", 19.0)
    sim.seed_running("study.radiator")
    sim.start()
    sim.fault("switch.lounge_radiator_valve", FaultKind.REJECT, 3600.0)
    sim.run_until_true(
        lambda: not sim.is_on("switch.radiator_pump"),
        180.0 + 2 * REACTION,
        "the pump stops after its overrun although the lounge valve failed to open",
    )
    sim.run_until_true(
        lambda: not sim.is_on("switch.study_radiator_valve"),
        2 * REACTION,
        "the study valve closes after the pump",
    )
    sim.run_until_true(
        lambda: "switch.lounge_radiator_valve" in sim.repairs(),
        600.0,
        "the lounge valve that never opens is reported as a Repair",
    )


@_stub("the stub never drops the boiler request after the circulator is lost")
def test_defect_4_the_source_request_drops_when_its_pump_is_lost() -> None:
    sim = Sim(plant(BOILER), mode=Mode.HEAT)
    sim.set_zone_temperature("flat", 19.0)
    sim.seed_running("flat.radiators")
    sim.seed_on("switch.boiler_request")
    sim.start()
    sim.always_for(lambda: sim.world.requested, 60.0, "the boiler runs while the flat calls")
    sim.spontaneous_off("switch.circulator_pump")
    sim.unavailable("switch.circulator_pump")
    sim.run_until_true(
        lambda: not sim.world.requested,
        REACTION,
        "the boiler request drops once the circulator is lost",
    )
    sim.always_for(lambda: not sim.world.requested, 600.0, "and stays off without the pump")


@_stub("the stub opens no valve, so the healthy floor loop never runs")
def test_defect_5_a_dropped_loop_neither_opens_nor_runs() -> None:
    sim = Sim(
        plant(THREE_LOOPS),
        mode=Mode.HEAT,
        armed=[
            "switch.floor_pump",
            "switch.living_floor_valve",
            "switch.living_radiator_valve",
            "switch.wall_pump",
            "switch.living_wall_valve",
        ],
    )
    sim.set_zone_temperature("living", 19.0)
    sim.unavailable("switch.living_wall_valve")
    sim.start()
    sim.run_until_true(
        lambda: sim.flowing("living.floor"),
        180.0 + 2 * REACTION,
        "the healthy floor loop runs",
    )
    sim.run_for(900.0)
    assert sim.switched("switch.living_radiator_valve") == [], (
        "the radiator loop needs the unarmed radiator pump, so its valve stays closed"
    )
    assert sim.switched("switch.wall_pump") == [], (
        "the wall loop's valve is unavailable, so its pump never starts"
    )


@_stub("the stub never stops the blocked office pump")
def test_defect_6_a_blocked_chilled_water_pump_stops_without_overrun() -> None:
    sim = Sim(plant(TWO_CEILINGS), mode=Mode.COOL)
    for zone in ("office", "den"):
        sim.set_target(zone, 24.0)
        sim.set_zone_temperature(zone, 26.0)
        sim.set_sensor(f"sensor.{zone}_supply", 18.0)
        sim.seed_running(f"{zone}.ceiling")
    sim.start()
    sim.always_for(
        lambda: sim.is_on("switch.office_pump") and sim.is_on("switch.den_pump"),
        60.0,
        "both zones cool",
    )
    # 26 °C at 50 % has a dew point of 14.8 °C, so 15 °C is inside the 2 K margin.
    sim.set_sensor("sensor.office_supply", 15.0)
    sim.run_until_true(
        lambda: not sim.is_on("switch.office_pump"),
        REACTION,
        "the blocked office pump stops at once, with no overrun in cooling",
    )
    sim.always_for(lambda: sim.flowing("den.ceiling"), 300.0, "the den keeps cooling")


@_stub("the stub desires the running floor pump off on the first evaluation")
def test_defect_7_a_reload_leaves_a_running_pump_alone() -> None:
    sim = _running_reference(living_demands=True)
    for ref in ("living_area.floor", "living_area.ceiling"):
        sim.seed_running(ref)
    sim.seed_on(REQUEST)
    sim.seed_on(TOWEL_PUMP)
    sim.seed_option(SOURCE_MODE, "Heat")
    sim.start()
    assert sim.desired.outputs[FLOOR_PUMP] == ON, "valves observed open an hour ago are ready"
    assert sim.desired.outputs[FLOOR_VALVE] == ON
    sim.always_for(lambda: sim.is_on(FLOOR_PUMP), 400.0, "the floor pump keeps running")
    assert sim.restart() == []
    sim.always_for(
        lambda: sim.is_on(FLOOR_PUMP), 400.0, "the floor pump keeps running after a reload"
    )
    touched = [call for call in sim.world.calls if call.entity in (FLOOR_PUMP, FLOOR_VALVE)]
    assert touched == [], "neither the floor pump nor its valve is ever commanded"


@_stub("the stub desires the running floor pump off before the edit")
def test_defect_8_editing_a_zone_keeps_the_plant_armed_and_running() -> None:
    sim = _running_reference(living_demands=True)
    for ref in ("living_area.floor", "living_area.ceiling"):
        sim.seed_running(ref)
    sim.seed_on(REQUEST)
    sim.seed_on(TOWEL_PUMP)
    sim.seed_option(SOURCE_MODE, "Heat")
    sim.start()
    sim.run_for(60.0)
    assert sim.desired.outputs[FLOOR_PUMP] == ON, "the floor pump keeps running before the edit"
    assert sim.state.live

    edited = _edited(sim.plant)
    calls = sim.restart(plant=edited)
    assert calls == [], "an edit changes no output"
    assert sim.state.live, "an edit keeps the Plant live"
    attic_valve = "switch.home_attic_ceiling_heating_valve"
    sim.set_thermostat("attic", DigitalThermostatState(Mode.HEAT, 21.0))
    sim.set_zone_temperature("attic", 18.0)
    sim.always_for(
        lambda: sim.is_on(FLOOR_PUMP) and not sim.is_on(attic_valve),
        600.0,
        "the Plant keeps heating, and the new zone's unarmed valve stays closed",
    )


def _edited(reference: Plant) -> Plant:
    """A thermostat preset, a name, and a sensor changed, and a new zone added."""
    zones = []
    for zone in reference.zones:
        if zone.slug == "basement":
            assert isinstance(zone.thermostat, DigitalThermostat)
            zone = replace(
                zone,
                thermostat=replace(
                    zone.thermostat,
                    presets=((Preset.COMFORT, 22.0), (Preset.ECO, 19.0), (Preset.AWAY, 16.0)),
                ),
            )
        elif zone.slug == "living_area":
            zone = replace(zone, name="Living")
        elif zone.slug == "bedroom_area":
            zone = replace(zone, temperature=(Sensor("sensor.bedroom_extra_temperature"),))
        zones.append(zone)
    attic = Zone(
        slug="attic",
        areas=(ZoneArea("attic"),),
        loops=(
            Loop(
                ref=LoopRef("attic", "ceiling"),
                valves=(Valve("switch.home_attic_ceiling_heating_valve"),),
                pump="heat_pump",
                modes=frozenset({Mode.HEAT}),
                runs=RUNS_WITH_ZONE,
            ),
        ),
    )
    edited = replace(reference, zones=(*zones, attic))
    validate_plant(edited)
    assert LIVING_CEILING in edited.outputs()
    return edited
