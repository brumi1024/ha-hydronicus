"""Plants for the named scenarios, written as plant files."""

from __future__ import annotations

from typing import Final

from hydronicus_core.model import Plant
from hydronicus_core.plant_file import read_plant_file

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
