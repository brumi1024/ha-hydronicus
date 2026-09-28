# Entities and actions

A Plant publishes a small, stable set of entities for dashboards, automations, and voice assistants, and one action.
Hydronicus ships no dashboard of its own; build one from these entities with Home Assistant's own cards.

Each entity's unique ID comes from the Plant ID and the slugs of its objects, so a Plant rebuilt from its [plant file](plant-file.md) gets the same entity IDs.
Home Assistant makes an entity ID from the device name and the entity name when the entity is created, so the patterns below assume names you have not changed since.

## Devices

| Device | Holds |
| --- | --- |
| The Plant | The **Mode** select, the **Control equipment** switch, the **Status** sensor, and the plant loops. |
| Each zone | The zone's thermostat, demand, temperature, dew point, duty cycle, and loops. |
| The source | Whether the source is requested. |

A device goes with its object: removing a zone removes its device.

## The Plant

| Entity | Entity ID | State |
| --- | --- | --- |
| **Mode** select | `select.<plant>_mode` | `off`, `heat`, or `cool`, where `cool` exists only when a loop cools. An automation can set it, and it survives restarts. |
| **Control equipment** switch | `switch.<plant>_control_equipment` | On while Hydronicus commands its armed outputs; off is Dry run. Its `live` attribute stays true after you turn it off until the equipment has stopped. |
| **Status** sensor | `sensor.<plant>_status` | What the Plant does now, in the table below. It is unavailable until the Plant's first evaluation. |

| Status | Meaning |
| --- | --- |
| `off` | The **Mode** is off, and nothing runs. |
| `idle` | The Plant is in a mode, and nothing is asked to run. |
| `heating` | Something runs, or is asked to run, for heating, from a valve opening to a pump's overrun. |
| `cooling` | The same for cooling. |
| `exercising` | Nothing else runs, and an idle pump or its valves are [exercised](how-it-works.md#exercise). |
| `changing_over` | The Plant is stopping the old mode, or waiting for the mode dwell, before the new mode starts. |
| `degraded` | An output does not respond, or an entity the Plant uses does not exist. |
| `stopping` | A change removed outputs that were running, so the Plant first stops the equipment of its old configuration. |
| `invalid` | The configuration is not valid; the equipment has stopped, and the Plant only observes until you fix it. |

The **Status** sensor's attributes explain the state:

| Attribute | Value |
| --- | --- |
| `requested_mode` | The mode the **Mode** select asks for. |
| `running_mode` | The mode the outputs run in now; during a changeover, the old mode, then `off` during the dwell. |
| `live` | Whether outputs are commanded, as on **Control equipment**. |
| `active_loops` | The loops that pass flow now, such as `living_area.floor` or `towel_dryer`. |
| `blocked_zones` | Each zone that cannot get what its thermostat asks for, with the reason, such as `window open`. |
| `unarmed_outputs` | The outputs that are not armed. |
| `source_requested` | Whether the source's request is on. |
| `outputs_not_responding` | The outputs whose change was sent three times and never seen. |
| `missing_entities` | Each entity the Plant uses that does not exist, with where it is used. |
| `stopping_outputs` | While `stopping`, the outputs of the old configuration not yet seen off. |
| `configuration_problem` | Why the configuration is not valid, or none. |
| `frost_protection` | The zones that [frost protection](how-it-works.md#frost-protection) heats. |
| `exercising` | The slug of the pump being exercised, or none. |
| `idle_since` | Each switched pump and valve with the time since which it has been off. |
| `reasons` | Why, for each zone, loop, output, the source, and the mode. Not recorded in history. |
| `proposed` | Only in Dry run: the state Hydronicus would give each output. Not recorded in history. |

## Each zone

| Entity | Entity ID | Exists when |
| --- | --- | --- |
| Thermostat | `climate.<zone>` | The zone has a digital thermostat. |
| **Heating demand** binary sensor | `binary_sensor.<zone>_heating_demand` | Always. |
| **Cooling demand** binary sensor | `binary_sensor.<zone>_cooling_demand` | A loop of the zone cools. |
| **Combined temperature** sensor | `sensor.<zone>_combined_temperature` | The zone has a temperature sensor or an area. |
| **Dew point** sensor | `sensor.<zone>_dew_point` | A loop of the zone cools. |
| **Duty cycle** sensor | `sensor.<zone>_duty_cycle` | The zone has a loop, or a plant loop runs with it. |

The thermostat offers `off` and `heat`, plus `cool` when a loop of the zone cools, and the zone's presets.
Its target goes from 5 to 35 °C in steps of 0.5, and its target, preset, and mode survive restarts.
Its `hvac_action` shows what the equipment does for the zone, while the demand sensors show what the zone asks for:

| Action | When |
| --- | --- |
| `heating` or `cooling` | The zone calls, and one of its loops passes flow, including while frost protection heats it. |
| `preheating` | The zone calls for heat, and its loops do not pass flow yet, such as while its valves open. |
| `idle` | Anything else, such as while the Plant runs the other mode, or the zone's loops are dropped. |
| `off` | The thermostat is off, and frost protection does not heat the zone. |

A zone with an existing thermostat gets no thermostat entity; the existing one is its thermostat.

The demand binary sensors are on while the zone calls, and their `reason` attribute says why or why not, such as `heat to 21.0 °C from 19.5 °C`, `thermostat off`, or `window open`.

The **Combined temperature** sensor is the zone's temperature, combined from its usable sensors.
Its `areas` attribute shows each area with the sensors it names and their readings, and its `sensors` attribute each extra sensor.

The **Dew point** sensor is the zone's worst-case dew point: the dew point of its warmest temperature and its highest humidity, which its `humidity` attribute shows.

The **Duty cycle** sensor is a diagnostic: the share of the last 24 whole hours in which a loop of the zone passed flow.
It only counts real flow while outputs are commanded, so it reads 0 in Dry run.
[Troubleshooting](troubleshooting.md#a-zone-runs-nearly-all-day) explains how to use it to balance zones.

## Each loop

| Entity | Entity ID |
| --- | --- |
| Flowing binary sensor | `binary_sensor.<zone>_<loop>_flowing`, or `binary_sensor.<plant>_<loop>_flowing` for a plant loop. |
| Runtime sensor | `sensor.<zone>_<loop>_runtime`, or `sensor.<plant>_<loop>_runtime` for a plant loop. |

Both are named after the loop, such as `Ceiling flowing` and `Ceiling runtime`.

The flowing sensor is on while every valve of the loop is on and its pump runs; in Dry run it follows the proposals.
Its attributes are `valves` with each valve's state, `pump`, `pump_running`, and `reason`, such as `wanted`, `min-flow path`, `exercise`, or `dropped: condensation guard blocks`.

The runtime sensor is a diagnostic: the loop's total hours of flow, counting only real flow while outputs are commanded.
It only grows, so a statistics graph card shows its daily, weekly, and monthly runtime.

## The source

| Entity | Entity ID | State |
| --- | --- | --- |
| **Requested** binary sensor | `binary_sensor.<source>_requested` | On while Hydronicus wants the source's request on. |

Its `observed` attribute is the request switch's own state, and its `reason` says why, such as `held for its minimum on time` or `waiting for the source mode`.

## An example

The [reference plant](examples/reference-plant.yaml), with the Plant `Home`, the source `Heat pump`, and the zones `Basement`, `Bedroom area`, and `Living area`, gets 32 entities:

- `select.home_mode`, `switch.home_control_equipment`, `sensor.home_status`, `binary_sensor.home_towel_dryer_flowing`, and `sensor.home_towel_dryer_runtime` for the Plant.
- `binary_sensor.heat_pump_requested` for the source.
- For each zone, such as `living_area`: `climate.living_area`, `binary_sensor.living_area_heating_demand`, `binary_sensor.living_area_cooling_demand`, `sensor.living_area_combined_temperature`, `sensor.living_area_dew_point`, `sensor.living_area_duty_cycle`, `binary_sensor.living_area_ceiling_flowing`, and `sensor.living_area_ceiling_runtime`.
- `binary_sensor.living_area_floor_flowing` and `sensor.living_area_floor_runtime` for the living area's underfloor loop.

Hydronicus creates no entity for a valve or a pump; they keep the entities their own integration provides.
Problems that need you, such as an output that does not respond, are [Repairs](troubleshooting.md#repairs), not entities.

## Actions

### Export plant file

`hydronicus.export_plant` returns the [plant file](plant-file.md) of a Plant, which imports as the same Plant with the same entity IDs.
Only administrators can run it, and it only returns a response, so call it with **Actions** under **Settings > Tools**, or from a script with `response_variable`.

| Field | Required | Value |
| --- | --- | --- |
| `config_entry_id` | yes | The Plant to export. The action form lets you pick it. |

The response has two keys: `document`, the plant file as data, and `yaml`, the same file as text.
The action fails with a message when the entry is not a Hydronicus Plant, or when its stored configuration is not a valid Plant.

## Automation examples

### Tell me when the plant needs attention

The **Status** reads `degraded` while an output does not respond or an entity is missing.
This automation sends a notification when that lasts 10 minutes; replace `sensor.home_status` with your Plant's **Status** sensor:

```yaml
automation:
  - alias: "Heating: the plant needs attention"
    triggers:
      - trigger: state
        entity_id: sensor.home_status
        to: degraded
        for:
          minutes: 10
    actions:
      - action: notify.notify
        data:
          title: Heating needs attention
          message: "Not responding: {{ state_attr('sensor.home_status', 'outputs_not_responding') }}"
```

### Keep a copy of the plant file

This script shows the current plant file in a notification, so you can copy it after a change.
Replace the `config_entry_id` with your Plant's, which the action form under **Settings > Tools > Actions** fills in when you pick the Plant:

```yaml
script:
  show_plant_file:
    sequence:
      - action: hydronicus.export_plant
        data:
          config_entry_id: 01J0000000000000000000000
        response_variable: plant
      - action: persistent_notification.create
        data:
          title: Plant file
          message: "{{ plant.yaml }}"
```

### Automatic heat and cool changeover

The **Mode** select has no automatic option by design, so you choose heat or cool, or let an automation do it.
Base the automation on a slow outdoor temperature, so a cold night or a sunny afternoon does not switch modes.
The [`statistics`](https://www.home-assistant.io/integrations/statistics/) integration's 24 hour mean works well:

```yaml
sensor:
  - platform: statistics
    name: "Outdoor temperature 24h mean"
    entity_id: sensor.outdoor_temperature
    state_characteristic: mean
    max_age:
      hours: 24
```

Then switch with a neutral band between the two modes, so the mode does not flip back and forth around one threshold.
The numbers are examples; tune them to your climate and your emitters.
The `input_boolean.automatic_changeover` lets you turn the automation off and hold a mode you set by hand:

```yaml
automation:
  - alias: "Home: automatic heat/cool changeover"
    triggers:
      - trigger: state
        entity_id: sensor.outdoor_temperature_24h_mean
      - trigger: homeassistant
        event: start
    conditions:
      - condition: state
        entity_id: input_boolean.automatic_changeover
        state: "on"
    actions:
      - choose:
          - conditions:
              - condition: numeric_state
                entity_id: sensor.outdoor_temperature_24h_mean
                below: 15
            sequence:
              - action: select.select_option
                target:
                  entity_id: select.home_mode
                data:
                  option: "heat"
          - conditions:
              - condition: numeric_state
                entity_id: sensor.outdoor_temperature_24h_mean
                above: 22
            sequence:
              - action: select.select_option
                target:
                  entity_id: select.home_mode
                data:
                  option: "cool"
        default:
          - action: select.select_option
            target:
              entity_id: select.home_mode
            data:
              option: "off"
    mode: single
```

Replace `select.home_mode` with your Plant's **Mode** select.
The automation needs no delays of its own: Hydronicus always runs its own [stop sequence and mode dwell](how-it-works.md#heating-cooling-and-mode-changes) between heating and cooling, and a mode set at an awkward moment just waits behind it.
