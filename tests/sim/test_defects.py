"""The control defects reproduced in v0.1.0, translated to the new model.

Each scenario builds the situation of one defect found in v0.1.0 and asserts
the behaviour the defect violated. Every scenario also checks the
invariants after every event.
"""

from __future__ import annotations

from dataclasses import replace

from custom_components.hydronicus.core.model import (
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
from custom_components.hydronicus.core.plant_file import validate_plant
from custom_components.hydronicus.core.reconcile import BACKOFF_MAX
from custom_components.hydronicus.core.step import DigitalThermostatState
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


def test_defect_3_a_failed_valve_open_does_not_drop_the_pump_stop() -> None:
    sim = Sim(plant(SHARED_PUMP), mode=Mode.HEAT)
    sim.set_zone_temperature("study", 21.5)
    sim.set_zone_temperature("lounge", 19.0)
    sim.seed_running("study.radiator")
    # The lounge calls from the start, so its valve fails from the first open.
    sim.fault("switch.lounge_radiator_valve", FaultKind.REJECT, 3600.0)
    sim.start()
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


def test_dry_run_mode_history_cannot_shorten_physical_dwell_or_relabel_exercise() -> None:
    """Reduced from the October review's randomized idle-exercise failure."""
    configured = plant("""
hydronicus: 2
name: Physical history
mode_dwell: 300
exercise: {interval: 3600, run: 30}
frost_protection: null
pumps:
  heat: {switch: switch.heat, overrun: 0}
  both: {switch: switch.both, overrun: 0, supply_temperature: sensor.supply}
zones:
  room:
    temperature: [sensor.room]
    humidity: [sensor.humidity]
    loops:
      radiator: {pump: heat, modes: [heat]}
      ceiling: {pump: both, modes: [heat, cool]}
""")
    sim = Sim(configured, mode=Mode.HEAT, control=False)
    sim.seed_on("switch.heat")
    sim.set_zone_temperature("room", 9.5)
    sim.set_sensor("sensor.supply", 10)
    sim.set_zone_humidity("room", 30)
    sim.start()
    sim.run_for(6)
    sim.set_mode(Mode.COOL, thermostats=False)
    sim.run_until(3301)
    assert sim.is_on("switch.heat") and not sim.world.calls
    sim.set_control(True)
    sim.run_for(1)
    stopped = sim.switched("switch.heat")[-1][0]
    assert not sim.is_on("switch.heat")
    sim.set_mode(Mode.OFF, thermostats=False)
    sim.run_until(stopped + 299)
    assert not sim.is_on("switch.heat") and not sim.is_on("switch.both")
    sim.run_for(4000)
    assert any(on and t >= stopped + 300 for t, on in sim.switched("switch.heat"))


def test_source_minimum_off_time_survives_an_ignored_shutdown() -> None:
    configured = plant(
        BOILER.replace("min_off: 0", "min_off: 300")
        .replace("overrun: 60", "overrun: 0")
        .replace(
            "temperature: [sensor.flat_temperature]",
            "temperature: [sensor.flat_temperature]\n"
            "    thermostat: {digital: {min_on: 0, min_off: 0}}",
        )
    )
    sim = Sim(configured, mode=Mode.HEAT)
    sim.set_zone_temperature("flat", 18)
    sim.run_until_true(lambda: sim.world.requested, 200, "source starts")
    sim.fault("switch.boiler_request", FaultKind.TIMEOUT, 610)
    sim.set_zone_temperature("flat", 25)
    sim.run_for(610)
    assert sim.world.requested
    sim.world.set_switch("switch.boiler_request", False)
    stopped = sim.t
    sim.set_zone_temperature("flat", 18)
    sim.run_for(299)
    assert not sim.world.requested
    sim.run_until_true(lambda: sim.world.requested, 20, "source restarts after actual off interval")
    assert sim.switched("switch.boiler_request")[-1][0] - stopped >= 300


def test_source_waits_for_numeric_output_retries_and_observed_confirmation() -> None:
    configured = plant(
        BOILER.replace(
            "request: switch.boiler_request,",
            "request: switch.boiler_request, supply: {entity: number.supply},",
        )
    )
    sim = Sim(configured, mode=Mode.HEAT)
    sim.seed_running("flat.radiators")
    sim.set_zone_temperature("flat", 18)
    sim.fault("number.supply", FaultKind.TIMEOUT, 80)
    sim.start()
    sim.run_for(75)
    assert not sim.world.requested
    assert "number.supply" in sim.repairs()
    sim.run_until_true(lambda: sim.world.requested, 120, "confirmed setpoint enables source")
    assert sim.world.number("number.supply") == 35
    assert all(call.t >= 80 for call in sim.calls_to("switch.boiler_request") if call.target == ON)
    calls = len(sim.calls_to("number.supply"))
    sim.world.seed_number("number.supply", 35.4)
    sim.run_for(5)
    assert len(sim.calls_to("number.supply")) == calls, "confirmation tolerance prevents thrashing"


def test_actual_source_running_feedback_keeps_path_beyond_configured_post_run() -> None:
    configured = plant("""
hydronicus: 2
name: Actual circulation
exercise: null
source:
  request: switch.source
  running_sensor: binary_sensor.source_running
  min_on: 0
  min_off: 0
  post_run: 0
pumps:
  primary: {driven_by: source, min_flow_loops: [room.floor]}
zones:
  room:
    temperature: [sensor.room]
    loops:
      floor: {pump: primary, valves: [{entity: switch.valve, opening_time: 1}]}
""")
    sim = Sim(configured, mode=Mode.HEAT)
    sim.seed_running("room.floor")
    sim.seed_on("switch.source")
    sim.world.set_source_running(True)
    sim.set_contact("binary_sensor.source_running", True)
    sim.set_zone_temperature("room", 25)
    sim.start()
    sim.run_for(20)
    assert not sim.world.requested
    assert sim.flowing("room.floor") and sim.is_on("switch.valve")
    sim.world.set_source_running(None)
    sim.set_contact("binary_sensor.source_running", False)
    sim.run_for(5)
    assert not sim.is_on("switch.valve")


def test_an_unused_dry_run_mode_does_not_label_the_first_physical_exercise() -> None:
    configured = plant("""
hydronicus: 2
name: Unused mode
mode_dwell: 300
exercise: {interval: 3600, run: 30}
frost_protection: null
pumps: {pump: {switch: switch.pump, overrun: 0}}
zones:
  room:
    temperature: [sensor.room]
    loops: {radiator: {pump: pump, modes: [heat]}}
""")
    sim = Sim(configured, mode=Mode.COOL, control=False)
    sim.start()
    sim.run_for(1)
    sim.set_mode(Mode.OFF, thermostats=False)
    sim.run_for(1)
    sim.set_control(True)
    sim.run_for(3700)
    assert any(on for _, on in sim.switched("switch.pump"))
    assert sim.checker.flow_log
    assert all(flow.exercise and flow.label is Mode.HEAT for flow in sim.checker.flow_log)


def test_handover_exercise_has_its_own_label_without_erasing_prior_cooling_flow() -> None:
    configured = plant("""
hydronicus: 2
name: Cooling history
mode_dwell: 300
exercise: {interval: 3600, run: 30}
frost_protection: null
pumps:
  heat: {switch: switch.heat, overrun: 0}
  cool: {switch: switch.cool, supply_temperature: sensor.supply, overrun: 0}
zones:
  room:
    temperature: [sensor.room]
    humidity: [sensor.humidity]
    loops:
      radiator: {pump: heat, modes: [heat]}
      ceiling: {pump: cool, modes: [cool]}
""")
    for seeded in (False, True):
        sim = Sim(configured, mode=Mode.COOL, control=not seeded)
        sim.set_zone_temperature("room", 26)
        sim.set_zone_humidity("room", 40)
        sim.set_sensor("sensor.supply", 25)
        sim.set_target("room", 27)
        if seeded:
            sim.seed_running("room.ceiling")
        sim.start()
        sim.run_for(1)
        sim.set_control(False)
        sim.run_for(1)
        sim.set_mode(Mode.OFF, thermostats=False)
        sim.run_for(1)
        sim.set_control(True)
        sim.run_for(4000)
        heat = [flow for flow in sim.checker.flow_log if flow.ref == LoopRef("room", "radiator")]
        assert heat and all(flow.exercise and flow.label is Mode.HEAT for flow in heat)
        if seeded:
            original = sim.checker.flow_log[0]
            assert original.label is Mode.COOL and not original.exercise
            assert original.end is not None
            assert heat[0].start >= original.end + configured.mode_dwell
            assert sim.checker.last_end[Mode.COOL] == original.end
