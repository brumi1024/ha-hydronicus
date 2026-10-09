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
| `degraded` | An output does not respond, a bound entity does not exist, or the latest evaluation failed. |
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
| `holds` | Every [timer](#timers) that holds equipment as it is now, soonest end first. Not recorded in history. |
| `proposed` | Only in Dry run: the state Hydronicus would give each output. Not recorded in history. |

| `blocking_reason` | The current leading reason the Plant cannot proceed, or none. |
| `evaluated_at` | ISO timestamp of the last successful evaluation. |
| `evaluation_age_seconds` | Age of that evaluation when the entity attributes were published. It is not a continuously ticking sensor. |
| `next_evaluation_at` | Next scheduled controller check, or none; it is not a promise that equipment will change then. |
| `evaluation_error` | The latest evaluation error, or none after a successful evaluation. |
| `pending_commands` | Each output awaiting confirmation, with `target`, `age_seconds`, and `attempts`. |
| `sensor_health` | Each numeric input's `value`, `quality`, `age_seconds`, and `max_age_seconds`; quality is `fresh`, `stale`, or `unavailable or invalid`. |
| `pump_operation` | Each pump's observed or estimated operation, with `active`, `basis`, and `sensor`, plus the `reason` for its switch and the [timers](#timers) in `holds` that keep it on or off. Unknown feedback has `active: null`. |
| `source_operation` | Source operation separately from its request, with `active`, `basis`, and `sensor`. |
| `observed_flow` | Each loop's operation from actual observations, with `active`, `basis`, and `sensor`, even while Dry run shows proposals. |

## Each zone

| Entity | Entity ID | Exists when |
| --- | --- | --- |
| Thermostat | `climate.<zone>` | The zone has a digital thermostat. |
| **Heating demand** binary sensor | `binary_sensor.<zone>_heating_demand` | Always. |
| **Cooling demand** binary sensor | `binary_sensor.<zone>_cooling_demand` | A loop serving the zone cools, including a shared plant loop. |
| **Combined temperature** sensor | `sensor.<zone>_combined_temperature` | The zone has a temperature sensor or an area. |
| **Dew point** sensor | `sensor.<zone>_dew_point` | A loop serving the zone cools, including a shared plant loop. |
| **Duty cycle** sensor | `sensor.<zone>_duty_cycle` | The zone has a loop, or a plant loop runs with it. |
| **Reset recovery learning** button | `button.<zone>_reset_recovery_learning` | Digital thermostat learning is set to `observe` or `assist`. |

The thermostat's heating and cooling choices follow every loop serving the zone, including shared plant loops.
It offers the presets configured for its current mode, plus `schedule` when a comfort schedule is configured.
Its target goes from 5 to 35 °C in steps of 0.5, and its separate heating and cooling manual targets, preset, and mode survive restarts.
Its `hvac_action` shows what the equipment does for the zone, while the demand sensors show what the zone asks for:

| Action | When |
| --- | --- |
| `heating` or `cooling` | The zone calls, and one of its loops passes flow, including while frost protection heats it. |
| `preheating` | The zone calls for heat, and its loops do not pass flow yet, such as while its valves open. |
| `idle` | Anything else, such as while the Plant runs the other mode, or the zone's loops are dropped. |
| `off` | The thermostat is off, and frost protection does not heat the zone. |

The thermostat also exposes comfort planning attributes:

| Attribute | Value |
| --- | --- |
| `heat_target` and `cool_target` | The separate manual comfort targets. |
| `planned_target` | The manual comfort target for the current mode, before schedule setback or recovery. |
| `effective_target` | The target currently used for demand, including a preset, setback, or early start. |
| `early_start` | Whether the schedule is currently recovering before the next comfort period. |
| `schedule_status` | `manual`, `off`, `unavailable`, `comfort`, `setback`, or `early_start`. |
| `recovery_method` | `configured`, `learned`, or `weather`, from the comfort proposal used for demand. |
| `planned_recovery_seconds` | The proposed recovery duration before the configured early-start cap, or none without a current recovery plan. |
| `learning_mode` | The configured `off`, `observe`, or `assist` option. |
| `learning_reason` | Why the current recovery estimate is accepted or unavailable. |
| `learning_episode_count` | Independent complete recovery episodes behind the current estimate; zero when no estimate is available. |
| `learning_confidence` | Whether the current estimate passes the admission checks; Observe still leaves configured-rate planning unchanged. |
| `estimated_recovery_seconds` | The learner's current prediction, including a provisional prediction with insufficient confidence; none when unavailable. |

Changing the target or choosing a different preset exits schedule control; selecting `schedule` resumes it.
See [comfort schedules](how-it-works.md#comfort-schedules) for unavailable helpers and recovery limits.
The thermostat displays the same evaluated comfort proposal used for its demand, while a just-submitted manual change appears immediately.
**Reset recovery learning** clears only that zone's recovery observations and model, including both heating and cooling evidence.
It does not change the learning option, manual targets, presets, arming, or hydraulic safety timers.
The button is a configuration entity on the zone device and disappears when learning is turned off.
A zone with an existing thermostat gets no thermostat entity; the existing one is its thermostat.

The demand binary sensors are on while the zone calls, and their `reason` attribute says why or why not, such as `heat to 21.0 °C from 19.5 °C`, `thermostat off`, or `window open`.
Their `holds` attribute lists the zone's [timers](#timers): a window's open or close delay and the thermostat's minimum on or off time.

The **Combined temperature** sensor is the zone's temperature, combined from its usable sensors.
Its `areas` attribute shows each area with the sensors it names and their readings, and its `sensors` attribute each extra sensor.
Its `sensor_health` attribute shows numeric input freshness, age, configured maximum age, and usable value.

The **Dew point** sensor is the zone's worst-case dew point: the dew point of its warmest temperature and its highest humidity, which its `humidity` attribute shows.

The **Duty cycle** sensor is a diagnostic: the share of the last 24 whole hours in which a loop of the zone passed flow.
It counts flow inferred from live equipment observations while outputs are commanded, so it reads 0 in Dry run.
Unknown configured feedback contributes no runtime.
Its `basis` explains that inference, and `window_hours: 24` and `includes_current_hour: false` describe the window.
[Troubleshooting](troubleshooting.md#a-zone-runs-nearly-all-day) explains how to use it to balance zones.

## Each loop

| Entity | Entity ID |
| --- | --- |
| Flowing binary sensor | `binary_sensor.<zone>_<loop>_flowing`, or `binary_sensor.<plant>_<loop>_flowing` for a plant loop. |
| Runtime sensor | `sensor.<zone>_<loop>_runtime`, or `sensor.<plant>_<loop>_runtime` for a plant loop. |

Both are named after the loop, such as `Ceiling flowing` and `Ceiling runtime`.

The flowing sensor is on while the loop is inferred to pass flow: every valve is open and circulation is observed or estimated.
Configured running and flow feedback are used when present; otherwise switch state, source request, and source post-run provide the estimate.
Unknown configured feedback produces unknown flow and contributes no runtime.
Pump flow proof still does not measure how much water passes through an individual loop.
In Dry run the main state shows the proposed operation, while `observed_flow` keeps actual equipment observations separate.
Its attributes:

| Attribute | Value |
| --- | --- |
| `valves` | Each valve with its state. |
| `pump` | The slug of the loop's pump. |
| `pump_running` | Whether the pump is running according to its configured feedback or an output-based estimate; unknown is none. |
| `pump_running_basis` | Which feedback or estimate supports `pump_running`. |
| `flow_basis` | Which observations support the loop's flowing state. |
| `flow_sensor` | The pump flow proof sensor, if configured. |
| `dry_run` | Whether the main state follows proposals. |
| `observed_flow` | Flow from actual equipment observations, independently of Dry run proposals. |
| `reason` | Why the loop runs or not, such as `wanted`, `min-flow path`, `exercise`, or `dropped: condensation guard blocks`. |
| `pump_reason` | Why the loop's switched pump runs or waits, such as `waiting for its valves to open`, `overrun`, or none. |
| `holds` | The [timers](#timers) on the loop, its valves, and its pump, or its source for a source-driven pump. |

The runtime sensor is a diagnostic: how long the loop is inferred to have passed flow in total, in hours.
Its `basis` attribute makes that inference explicit; it is not a heat or energy meter.
It counts only flow that Hydronicus observes while outputs are commanded, that is while **Control equipment** is on or its off-mode sequence runs, with every valve on and the pump observed running.
The proposed flow of Dry run never counts, and neither does time while Hydronicus or Home Assistant was not running, even if the equipment ran meanwhile.
It survives reloads and restarts, and it is a total that only grows, so Home Assistant's long-term statistics give its daily, weekly, and monthly runtime, such as in a statistics graph card.
While a loop flows, the runtime and duty cycle sensors update once a minute.

## The source

| Entity | Entity ID | State |
| --- | --- | --- |
| **Requested** binary sensor | `binary_sensor.<source>_requested` | On while Hydronicus wants the source's request on. |

Its `observed` attribute is the request switch's own state, and its `reason` says why, such as `held for its minimum on time` or `waiting for the source mode`.
Its `running`, `running_basis`, and `running_sensor` attributes describe source operation separately from the request.
Its `holds` attribute lists the source's [timers](#timers), such as its minimum off time and post-run.
Configured feedback takes precedence; without it, operation is inferred from the request, and unknown feedback remains unknown.

## Timers

Hydronicus waits on purpose: a valve needs its opening time before its pump starts, a pump runs on after demand ends, and the source keeps its minimum on and off times.
Each such wait is a hold, published in the `holds` attributes above as a list of `target`, `kind`, and `until`.
`target` is keyed as in the Status sensor's `reasons`: an output entity, a zone or loop slug, `source`, `mode`, or `<loop>.guard`.
`until` is when the hold ends as an ISO timestamp, or none while its end is not known yet, such as a pump waiting for a valve not yet seen open.
A hold says when the timer ends, not that the equipment will change then: a new demand can keep a pump running past its overrun.

| `kind` | Target | Holds |
| --- | --- | --- |
| `valve_opening` | Valve | The valve is open but not yet ready, for its opening time. |
| `valve_closing` | Valve | The valve is off but may still pass flow while it closes. |
| `waiting_for_valves` | Switched pump | The pump waits for a wanted loop's valves to be ready. |
| `overrun` | Switched pump | The pump runs on after demand ends, in heating. |
| `source_min_on` | Switched pump | The pump runs for the source's minimum on time. |
| `exercise` | Pump | The pump runs for the exercise's run time. |
| `min_on`, `min_off` | `source` | The source request keeps its minimum on or off time. |
| `post_run` | `source` | The source's pumps may still run after its request turned off. |
| `feedback` | `source` | The source waits for running or flow proof before it gives up. |
| `mode_dwell` | `mode` | A mode change waits for the dwell after the old mode's flow. |
| `window_open_delay`, `window_close_delay` | Zone | A window's delay before it turns demand off, or lets it back on. |
| `demand_min_on`, `demand_min_off` | Zone | The thermostat keeps its decision for its minimum on or off time. |
| `guard_min_blocked` | `<loop>.guard` | A condensation guard stays blocked for its minimum time, in cooling. |

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

The **Status** reads `degraded` while an output does not respond, an entity is missing, or the latest evaluation failed.
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
