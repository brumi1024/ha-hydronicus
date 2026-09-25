# Entities

A Plant publishes a small, stable set of entities, and they are the interface for dashboards, automations, and voice assistants.
Hydronicus ships no dashboard of its own; build one from these entities with Home Assistant's own cards.

Every entity is created from the Plant's configuration, and its unique ID is made from the Plant ID and the slugs of its objects.
A Plant rebuilt from its [plant file](plant-file.md) therefore gets the same entities with the same entity IDs.

## Devices

| Device | Name | Holds |
| --- | --- | --- |
| Plant | The Plant name | The Plant's mode, **Control equipment**, status, and plant loops. |
| Zone | The zone name | The zone's thermostat, demand, temperature, dew point, and loops. It sits under the Plant device and belongs to the zone's subentry. |
| Source | The source name | Whether the source is requested. It sits under the Plant device. |

Home Assistant makes each entity ID from the device name and the entity name when the entity is created, so the patterns below assume names that have not been changed since.

## The Plant

| Entity | Entity ID | State |
| --- | --- | --- |
| **Mode** select | `select.<plant>_mode` | `off`, `heat`, or `cool`. `cool` is offered only when a loop of the Plant cools. |
| **Control equipment** switch | `switch.<plant>_control_equipment` | On while Hydronicus commands its armed outputs; off is Dry run. |
| **Status** sensor | `sensor.<plant>_status` | `off`, `idle`, `heating`, `cooling`, `changing_over`, or `degraded`. |

The **Mode** select is the Plant mode that the zones heat or cool in.
An automation can set it; Hydronicus keeps it across restarts.

The **Control equipment** switch has one attribute:

| Attribute | Value |
| --- | --- |
| `live` | Whether outputs are commanded now. It stays true after the switch is turned off until the off-mode sequence has finished. |

The **Status** sensor reads:

| State | Meaning |
| --- | --- |
| `off` | The Plant mode is off and nothing runs. |
| `idle` | The Plant is in a mode, and nothing is asked to run. |
| `heating` | Something runs, or is asked to run, for heating, from a valve opening to a pump's overrun. |
| `cooling` | The same for cooling. |
| `changing_over` | The Plant is stopping the old mode, or waiting for the mode dwell, before the new mode starts. |
| `degraded` | An output did not respond, or an entity the Plant binds does not exist. |

It is unavailable until the Plant's first evaluation, and it has these attributes:

| Attribute | Value |
| --- | --- |
| `requested_mode` | The mode the **Mode** select asks for. |
| `running_mode` | The mode the outputs run in now; during a changeover it is the old mode, then `off` during the dwell. |
| `live` | Whether outputs are commanded, as on the **Control equipment** switch. |
| `active_loops` | The loops that pass flow now, such as `living_area.floor` or `towel_dryer`. |
| `blocked_zones` | Each zone that cannot get what its thermostat asks for, with the reason. |
| `unarmed_outputs` | The outputs that are not armed. |
| `source_requested` | Whether the source's request is on. |
| `outputs_not_responding` | The outputs whose change was sent three times and never observed. |
| `missing_entities` | Each bound entity that does not exist, with where the Plant binds it. |
| `reasons` | Why, for each zone, loop, output, the source, and the mode. It is not recorded in history. |
| `proposed` | Only in Dry run: the state Hydronicus would give each output. It is not recorded in history. |

## Each zone

| Entity | Entity ID | Exists when |
| --- | --- | --- |
| Thermostat | `climate.<zone>` | The zone has a digital thermostat. |
| **Heating demand** binary sensor | `binary_sensor.<zone>_heating_demand` | Always. |
| **Cooling demand** binary sensor | `binary_sensor.<zone>_cooling_demand` | A loop of the zone cools. |
| **Combined temperature** sensor | `sensor.<zone>_combined_temperature` | The zone has a temperature sensor or an area. |
| **Dew point** sensor | `sensor.<zone>_dew_point` | A loop of the zone cools. |

The thermostat is the zone's digital thermostat.
It offers `off` and `heat`, plus `cool` when a loop of the zone cools, and the presets the zone has.
Its target ranges from 5 to 35 °C in steps of 0.5, and its target, preset, and mode survive restarts.
Its `hvac_action` shows the zone's demand: `off`, `idle`, `heating`, or `cooling`.
It shows the zone's combined temperature, and its humidity when the zone has a humidity sensor or an area.
A zone with an external thermostat gets no thermostat entity, because the existing climate entity is the thermostat.
A zone that covers exactly one area gets its thermostat placed in that area when it is first created, so it appears on the area's page and answers voice commands for the area.

The demand binary sensors are on while the zone demands heating or cooling, and have these attributes:

| Attribute | Value |
| --- | --- |
| `level` | The demand level from 0 to 1. A digital thermostat raises it with the distance to target over its proportional band; an external thermostat reports 1 or 0. |
| `reason` | Why the zone demands or not, such as `heat to 21.0 °C from 19.5 °C` or `thermostat off`. It is not recorded in history. |

The **Combined temperature** sensor is the zone's temperature, combined from its usable sensors by its aggregation.
Its attributes show where the readings come from, and are not recorded in history:

| Attribute | Value |
| --- | --- |
| `areas` | Each covered area with its `name`, its `temperature_sensor` and `temperature`, and its `humidity_sensor` and `humidity`. |
| `sensors` | Each extra temperature sensor with its reading. |

The **Dew point** sensor is the zone's worst-case dew point: the dew point of its warmest temperature and its highest humidity.
Its `humidity` attribute is that highest humidity.

## Each loop

| Entity | Entity ID | Device |
| --- | --- | --- |
| Flowing binary sensor | `binary_sensor.<zone>_<loop>_flowing` | The zone of a zone loop. |
| Flowing binary sensor | `binary_sensor.<plant>_<loop>_flowing` | The Plant, for a plant loop. |

It is on while the loop passes flow: every valve is on and its pump runs, where a source-driven pump runs while the source's request is on.
In Dry run it shows the proposed states.
Its attributes:

| Attribute | Value |
| --- | --- |
| `valves` | Each valve with its state. |
| `pump` | The slug of the loop's pump. |
| `pump_running` | Whether the pump's switch, or the source's request for a source-driven pump, is on. |
| `reason` | Why the loop runs or not, such as `wanted`, `min-flow path`, or `dropped: condensation guard blocks`. |

## The source

| Entity | Entity ID | State |
| --- | --- | --- |
| **Requested** binary sensor | `binary_sensor.<source>_requested` | On while Hydronicus wants the source's request on. |

Its attributes:

| Attribute | Value |
| --- | --- |
| `observed` | The state of the source's request switch as Home Assistant shows it. |
| `reason` | Why the source is requested or not, such as `requested`, `held for its minimum on time`, or `waiting for the source mode`. |

## The reference plant

The [reference plant](examples/reference-plant.yaml), with Plant `Home`, source `Heat pump`, and zones `Basement`, `Bedroom area`, and `Living area`, gets 24 entities:

- `select.home_mode`, `switch.home_control_equipment`, `sensor.home_status`, and `binary_sensor.home_towel_dryer_flowing` for the Plant.
- `binary_sensor.heat_pump_requested` for the source.
- For each zone, such as `living_area`: `climate.living_area`, `binary_sensor.living_area_heating_demand`, `binary_sensor.living_area_cooling_demand`, `sensor.living_area_combined_temperature`, `sensor.living_area_dew_point`, and `binary_sensor.living_area_ceiling_flowing`.
- `binary_sensor.living_area_floor_flowing` for the living area's underfloor loop.

## What is not an entity

Output faults, missing entities, and outputs awaiting confirmation are Repairs, described in [troubleshooting](troubleshooting.md#repairs).
Hydronicus creates no entity for a valve or a pump; the loop's flowing sensor shows their states, and the output entities themselves stay the ones their own integration provides.
