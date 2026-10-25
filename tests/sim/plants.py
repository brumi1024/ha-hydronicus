"""Plants for the named scenarios, written as plant files."""

from __future__ import annotations

from typing import Final

from custom_components.hydronicus.core.model import Plant
from custom_components.hydronicus.core.plant_file import read_plant_file
from tests.core.plant_files import REFERENCE_PLANT

PLANT_ID: Final = "2f1b7c3e-5d4a-4e8b-9c6d-1a2b3c4d5e6f"

# The reference plant's outputs and sensors.
REQUEST: Final = "switch.heat_pump_heat_request"
SOURCE_MODE: Final = "select.heat_pump_mode"
SUPPLY: Final = "sensor.ceiling_supply_temperature"
FLOOR_PUMP: Final = "switch.home_underfloor_heating_pump"
TOWEL_PUMP: Final = "switch.home_bathrooms_towel_dryer_pump"
FLOOR_VALVE: Final = "switch.home_living_area_floor_heating_valve"
LIVING_CEILING: Final = "switch.home_living_area_ceiling_heating_valve"
BEDROOM_CEILING: Final = "switch.home_bedroom_area_ceiling_heating_valve"
BASEMENT_CEILING: Final = "switch.home_basement_ceiling_heating_valve"
ZONES: Final = ("basement", "bedroom_area", "living_area")


def reference_plant() -> Plant:
    return read_plant_file(REFERENCE_PLANT.read_text(encoding="utf-8"))


def plant(text: str) -> Plant:
    return read_plant_file(text, new_id=lambda: PLANT_ID)


# Two zones whose radiator loops share one switched pump.
SHARED_PUMP: Final = """
hydronicus: 2
name: Radiators
pumps:
  radiators: {switch: switch.radiator_pump, overrun: 180}
zones:
  study:
    temperature: [sensor.study_temperature]
    loops:
      radiator: {valves: [switch.study_radiator_valve], pump: radiators}
  lounge:
    temperature: [sensor.lounge_temperature]
    loops:
      radiator: {valves: [switch.lounge_radiator_valve], pump: radiators}
"""

# A boiler whose only loop runs on a switched circulator.
BOILER: Final = """
hydronicus: 2
name: Flat
source: {request: switch.boiler_request, post_run: 0, min_on: 0, min_off: 0}
pumps:
  circulator: {switch: switch.circulator_pump, overrun: 60}
zones:
  flat:
    temperature: [sensor.flat_temperature]
    loops:
      radiators: {valves: [switch.flat_radiator_valve], pump: circulator}
"""

# One zone with a loop on each of three switched pumps.
THREE_LOOPS: Final = """
hydronicus: 2
name: Living
pumps:
  floor: {switch: switch.floor_pump, overrun: 60}
  radiators: {switch: switch.radiator_pump, overrun: 60}
  wall: {switch: switch.wall_pump, overrun: 60}
zones:
  living:
    temperature: [sensor.living_temperature]
    loops:
      floor: {valves: [switch.living_floor_valve], pump: floor}
      radiator: {valves: [switch.living_radiator_valve], pump: radiators}
      wall: {valves: [switch.living_wall_valve], pump: wall}
"""

# Two cooling zones, each with a ceiling loop on its own switched pump.
TWO_CEILINGS: Final = """
hydronicus: 2
name: Offices
pumps:
  office: {switch: switch.office_pump, overrun: 180, supply_temperature: sensor.office_supply}
  den: {switch: switch.den_pump, overrun: 180, supply_temperature: sensor.den_supply}
zones:
  office:
    temperature: [sensor.office_temperature]
    humidity: [sensor.office_humidity]
    loops:
      ceiling: {valves: [switch.office_ceiling_valve], pump: office, modes: [heat, cool]}
  den:
    temperature: [sensor.den_temperature]
    humidity: [sensor.den_humidity]
    loops:
      ceiling: {valves: [switch.den_ceiling_valve], pump: den, modes: [heat, cool]}
"""

# A source with a mode select, a source-driven pump with a min-flow loop, and a
# switched pump, for the simulator's own tests.
SMALL: Final = """
hydronicus: 2
name: Small
source:
  request: switch.source_request
  mode: {entity: select.source_mode, heat: Heat, cool: Cool}
  post_run: 120
  min_on: 0
  min_off: 0
pumps:
  primary: {driven_by: source, min_flow_loops: [room.ceiling]}
  floor: {switch: switch.floor_pump, overrun: 60, supply_temperature: sensor.floor_supply}
zones:
  room:
    temperature: [sensor.room_temperature]
    humidity: [sensor.room_humidity]
    loops:
      ceiling:
        valves:
          - entity: switch.room_ceiling_valve
            opening_time: 60
            readiness: binary_sensor.room_ceiling_open
        pump: primary
      floor:
        valves: [switch.room_floor_valve]
        pump: floor
        modes: [heat, cool]
"""

# The maintainer's house without its source: one switched pump drives every
# ceiling loop and the underfloor loop, and the towel dryer runs with the zones.
HEATING_PUMP: Final = FLOOR_PUMP
HOME: Final = """
hydronicus: 2
name: Home
pumps:
  heating: {switch: switch.home_underfloor_heating_pump, overrun: 180}
  towel_dryer: {switch: switch.home_bathrooms_towel_dryer_pump, overrun: 120}
loops:
  towel_dryer:
    pump: towel_dryer
    runs: {with_zones: [basement, bedroom_area, living_area]}
    modes: [heat]
zones:
  basement:
    areas: [basement, workshop]
    loops:
      ceiling: {valves: [switch.home_basement_ceiling_heating_valve], pump: heating}
  bedroom_area:
    areas: [main_bedroom, lilla_bedroom]
    loops:
      ceiling: {valves: [switch.home_bedroom_area_ceiling_heating_valve], pump: heating}
  living_area:
    areas: [living_room, dining_room, kitchen, hallway]
    loops:
      ceiling: {valves: [switch.home_living_area_ceiling_heating_valve], pump: heating}
      floor: {valves: [switch.home_living_area_floor_heating_valve], pump: heating}
"""

# The maintainer's house with its heat pump as the source, through the Modbus
# bridge: the heat pump heats a plate heat exchanger that only the zones load,
# so it must never run without an open zone, and every release restarts its
# internal pump from standstill. The request is held after demand into every
# heating loop while its zone has room, and released once none has. The
# ceilings cool, with the heat pump's leaving water as their condensation
# reference and the zone 1 setpoint as the cooling supply target; the floor
# heats only.
HEAT_PUMP_REQUEST: Final = "switch.midea_heat_pump_space_heating"
HEAT_PUMP_HEALTHY: Final = "binary_sensor.midea_heat_pump_modbus_healthy"
HEAT_PUMP_HANDOVER: Final = "binary_sensor.midea_heat_pump_handover_to_controller"
HEAT_PUMP_MODE: Final = "select.midea_heat_pump_mode"
HEAT_PUMP_SETPOINT: Final = "number.midea_heat_pump_zone_1_water_setpoint"
HEAT_PUMP_CURVE: Final = "switch.midea_heat_pump_weather_curve"
HEAT_PUMP_WATER_OUTLET: Final = "sensor.midea_heat_pump_water_outlet"
HEAT_PUMP_DHW: Final = "switch.midea_heat_pump_dhw"
HEAT_PUMP_DHW_SETPOINT: Final = "number.midea_heat_pump_dhw_setpoint"
HEAT_PUMP_WATER_INLET: Final = "sensor.midea_heat_pump_water_inlet"
HEAT_PUMP_COMPRESSOR: Final = "sensor.midea_heat_pump_compressor_frequency"
FIREPLACE_HEATING: Final = "input_boolean.home_fireplace_heating"
HOME_HEAT_PUMP: Final = """
hydronicus: 2
name: Home
mode_dwell: 7200
source:
  request: switch.midea_heat_pump_space_heating
  mode: {entity: select.midea_heat_pump_mode, heat: Heat, cool: Cool}
  mode_switches:
    switch.midea_heat_pump_weather_curve: [heat]
  post_run: 0
  min_on: 1500
  min_off: 720
  max_starts_per_hour: 3
  heat_sink_loops: [living_area.floor, living_area.ceiling, basement.ceiling, bedroom_area.ceiling]
  hold_after_demand: 14400
  heat_sink_overshoot: 0.5
  health_sensor: binary_sensor.midea_heat_pump_modbus_healthy
  handover_sensor: binary_sensor.midea_heat_pump_handover_to_controller
  write_interval: 300
  inhibit_sensor: input_boolean.home_fireplace_heating
  no_load:
    supply_temperature: sensor.midea_heat_pump_water_outlet
    return_temperature: sensor.midea_heat_pump_water_inlet
    compressor_sensor: sensor.midea_heat_pump_compressor_frequency
  compressor_sensor: sensor.midea_heat_pump_compressor_frequency
  supply:
    entity: number.midea_heat_pump_zone_1_water_setpoint
    modes: [cool]
    cool_temperature: 18
    minimum: 16
    maximum: 22
    step: 1
  dhw:
    switch: switch.midea_heat_pump_dhw
    setpoint: number.midea_heat_pump_dhw_setpoint
    minimum: 40
    maximum: 55
    step: 1
    max_boost: 10800
pumps:
  heat_pump: {driven_by: source, min_flow: guaranteed}
  heating:
    switch: switch.home_underfloor_heating_pump
    overrun: 240
    supply_temperature: sensor.midea_heat_pump_water_outlet
zones:
  basement:
    temperature: [sensor.basement_temperature]
    humidity: [sensor.basement_humidity]
    max_humidity: 65
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      ceiling:
        valves: [{entity: switch.home_basement_ceiling_heating_valve, opening_time: 15}]
        pump: heating
        modes: [heat, cool]
  bedroom_area:
    temperature: [sensor.bedroom_area_temperature]
    humidity: [sensor.bedroom_area_humidity]
    max_humidity: 65
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      ceiling:
        valves: [{entity: switch.home_bedroom_area_ceiling_heating_valve, opening_time: 15}]
        pump: heating
        modes: [heat, cool]
  living_area:
    temperature: [sensor.living_area_temperature]
    humidity: [sensor.living_area_humidity]
    max_humidity: 65
    thermostat: {digital: {min_on: 0, min_off: 0}}
    loops:
      ceiling:
        valves: [{entity: switch.home_living_area_ceiling_heating_valve, opening_time: 15}]
        pump: heating
        modes: [heat, cool]
      floor:
        valves: [{entity: switch.home_living_area_floor_heating_valve, opening_time: 15}]
        pump: heating
"""
