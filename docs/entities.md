# Entities

A Plant publishes a small, stable set of entities, and they are the interface for dashboards, automations, and voice assistants.
Hydronicus ships no dashboard of its own; build one from these entities with Home Assistant's own cards.

Every entity is created from the Plant's configuration, and its unique ID is made from the Plant ID and the slugs of its objects.
A Plant rebuilt from its [plant file](plant-file.md) therefore gets the same entities with the same entity IDs.

## Devices

| Device | Name | Holds |
| --- | --- | --- |
| Plant | The Plant name | The Plant's mode, **Control equipment**, status, and plant loops. |
| Zone | The zone name | The zone's thermostat, demand, temperature, dew point, duty cycle, and loops. It sits under the Plant device and belongs to the zone's subentry. |
| Source | The source name | Whether the source is requested. It sits under the Plant device. |

A device goes with its object: removing the source removes the source device, and removing a zone removes the zone device.
Home Assistant lets you delete a Hydronicus device by hand only when the Plant no longer has its object.

Home Assistant makes each entity ID from the device name and the entity name when the entity is created, so the patterns below assume names that have not been changed since.

## The Plant

| Entity | Entity ID | State |
| --- | --- | --- |
| **Mode** select | `select.<plant>_mode` | `off`, `heat`, or `cool`. `cool` is offered only when a loop of the Plant cools. |
| **Control equipment** switch | `switch.<plant>_control_equipment` | On while Hydronicus commands its armed outputs; off is Dry run. |
| **Status** sensor | `sensor.<plant>_status` | `off`, `idle`, `heating`, `cooling`, `exercising`, `changing_over`, `degraded`, `stopping`, or `invalid`. |

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
| `exercising` | Nothing else runs, and an idle pump or its valves are [exercised](how-it-works.md#exercising-idle-pumps-and-valves) so they do not seize. |
| `changing_over` | The Plant is stopping the old mode, or waiting for the mode dwell, before the new mode starts. |
| `degraded` | An output did not respond, a bound entity does not exist, or the latest evaluation failed. |
| `stopping` | A changed configuration removed outputs that were running, or is not valid, so the Plant first stops the equipment of its previous configuration. |
| `invalid` | The configuration is not valid; the equipment it ran has stopped, and the Plant only observes until a reconfigure fixes it. |

It is unavailable until the Plant's first evaluation, and it has these attributes:

| Attribute | Value |
| --- | --- |
| `requested_mode` | The mode the **Mode** select asks for. |
| `running_mode` | The mode the outputs run in now; during a changeover it is the old mode, then `off` during the dwell. |
| `live` | Whether outputs are commanded, as on the **Control equipment** switch. |
| `active_loops` | The loops that pass flow now, such as `living_area.floor` or `towel_dryer`. |
| `blocked_zones` | Each zone that cannot get what its thermostat asks for, with the reason, such as `no usable temperature` or `window open`; a zone that frost protection heats is not listed. |
| `unarmed_outputs` | The outputs that are not armed. |
| `source_requested` | Whether the source's request is on. |
| `outputs_not_responding` | The outputs whose change was sent three times and never observed. |
| `missing_entities` | Each bound entity that does not exist, with where the Plant binds it. |
| `stopping_outputs` | While `stopping`, the outputs of the previous configuration that are not yet seen off. |
| `configuration_problem` | Why the configuration is not valid, or none. |
| `frost_protection` | The zones that [frost protection](how-it-works.md#frost-protection) heats. |
| `exercising` | The slug of the pump whose exercise runs, or none. |
| `idle_since` | Each switched pump and valve with the time since which it has not been on, or none while it is on; the exercise counts from it. |
| `reasons` | Why, for each zone, loop, output, the source, and the mode. It is not recorded in history. |
| `proposed` | Only in Dry run: the state Hydronicus would give each output. It is not recorded in history. |
| `blocking_reason` | The current leading reason the Plant cannot proceed, or none. |
| `evaluated_at` | ISO timestamp of the last successful evaluation. |
| `evaluation_age_seconds` | Age of that evaluation when the entity attributes were published. It is not a continuously ticking sensor. |
| `next_evaluation_at` | Next scheduled controller check, or none; it is not a promise that equipment will change then. |
| `evaluation_error` | The latest evaluation error, or none after a successful evaluation. |
| `pending_commands` | Each output awaiting confirmation, with `target`, `age_seconds`, and `attempts`. |
| `sensor_health` | Each numeric input's `value`, `quality`, `age_seconds`, and `max_age_seconds`; quality is `fresh`, `stale`, or `unavailable or invalid`. |
| `pump_operation` | Each pump's observed or estimated operation, with `active`, `basis`, and `sensor`. Unknown feedback has `active: null`. |
| `source_operation` | Source operation separately from its request, with `active`, `basis`, and `sensor`. |
| `observed_flow` | Each loop's operation from actual observations, with `active`, `basis`, and `sensor`, even while Dry run shows proposals. |

## Each zone

| Entity | Entity ID | Exists when |
| --- | --- | --- |
| Thermostat | `climate.<zone>` | The zone has a digital thermostat. |
| **Heating demand** binary sensor | `binary_sensor.<zone>_heating_demand` | Always. |
| **Cooling demand** binary sensor | `binary_sensor.<zone>_cooling_demand` | A loop serving the zone cools, including a plant loop that runs with it. |
| **Combined temperature** sensor | `sensor.<zone>_combined_temperature` | The zone has a temperature sensor or an area. |
| **Dew point** sensor | `sensor.<zone>_dew_point` | A loop serving the zone cools, including a plant loop that runs with it. |
| **Duty cycle** sensor | `sensor.<zone>_duty_cycle` | The zone has a loop, or a plant loop runs with it. |
| **Reset recovery learning** button | `button.<zone>_reset_recovery_learning` | The zone's digital thermostat has learning set to `observe` or `assist`. |

The thermostat is the zone's digital thermostat.
Its heating and cooling choices follow all loops serving the zone, including shared plant loops.
It offers the presets configured for its current mode, plus `schedule` when a comfort schedule is configured.
Its target ranges from 5 to 35 °C in steps of 0.5, and its separate heating and cooling manual targets, preset, and mode survive restarts.
Its `hvac_action` shows what the equipment does for the zone, not what the zone asks for, which the demand binary sensors show:

| Action | When |
| --- | --- |
| `off` | The thermostat is off, and frost protection does not heat the zone. |
| `heating` or `cooling` | The zone demands in the mode the outputs run in, and one of its loops, or a plant loop that runs with it, passes flow. Frost protection's demand counts, even while the thermostat is off. |
| `preheating` | The zone demands heat while the outputs run heat, and a loop it wants does not pass flow yet, such as while its valves open. |
| `idle` | Anything else, such as while the Plant mode is off or runs the other mode, or while the zone's loops are dropped. |

In Dry run it follows the proposed states, as the loop flowing sensors do.
It shows the zone's combined temperature, and its humidity when the zone has a humidity sensor or an area.
Its `reason` attribute is the zone's demand reason, the same as on the demand binary sensors, such as `window open`; it is not recorded in history.
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
A zone with an external thermostat gets no thermostat entity, because the existing climate entity is the thermostat.
A zone that covers exactly one area gets its thermostat placed in that area when it is first created, so it appears on the area's page and answers voice commands for the area.

The demand binary sensors are on while the zone demands heating or cooling, and have this attribute:

| Attribute | Value |
| --- | --- |
| `reason` | Why the zone demands or not, such as `heat to 21.0 °C from 19.5 °C`, `frost protection: heat to 6.0 °C from 4.0 °C`, `thermostat off`, or `window open` while one of the zone's windows turns its demand off. It is not recorded in history. |

The **Combined temperature** sensor is the zone's temperature, combined from its usable sensors by its aggregation.
Its attributes show where the readings come from, and are not recorded in history:

| Attribute | Value |
| --- | --- |
| `areas` | Each covered area with its `name`, its `temperature_sensor` and `temperature`, and its `humidity_sensor` and `humidity`. |
| `sensors` | Each extra temperature sensor with its reading. |
| `sensor_health` | The freshness, age, configured maximum age, and usable value of the zone's numeric inputs. |

The **Dew point** sensor is the zone's worst-case dew point: the dew point of its warmest temperature and its highest humidity.
Its `humidity` attribute is that highest humidity.

The **Duty cycle** sensor is a diagnostic: the share of the last 24 hours, in percent, in which a loop of the zone, or a plant loop that runs with it, passed flow.
It covers the 24 whole hours before the current hour, so it changes when a new hour begins, and an hour counts in full once it is over.
Only flow inferred from equipment observations while outputs are commanded counts, as for the loops' runtime below: time in Dry run, and time while Hydronicus or Home Assistant was not running, count as no flow.
Its `basis` attribute explains that loop flow is inferred from equipment feedback, and `window_hours: 24` and `includes_current_hour: false` describe the window.
It is unknown until the Plant's first evaluation.
[Troubleshooting](troubleshooting.md#a-zone-runs-nearly-all-day) explains how to use it to balance the zones.

## Each loop

| Entity | Entity ID | Device |
| --- | --- | --- |
| Flowing binary sensor | `binary_sensor.<zone>_<loop>_flowing` | The zone of a zone loop. |
| Flowing binary sensor | `binary_sensor.<plant>_<loop>_flowing` | The Plant, for a plant loop. |
| Runtime sensor | `sensor.<zone>_<loop>_runtime` | The zone of a zone loop. |
| Runtime sensor | `sensor.<plant>_<loop>_runtime` | The Plant, for a plant loop. |

Both are named after the loop, such as `Ceiling flowing` and `Ceiling runtime`.

It is on while the loop is inferred to pass flow: every valve is open and circulation is observed or estimated.
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

Its attributes:

| Attribute | Value |
| --- | --- |
| `observed` | The state of the source's request switch as Home Assistant shows it. |
| `running` | Source operation from running feedback when configured, otherwise inferred from the request; unknown is none. |
| `running_basis` | Which feedback or estimate supports `running`. |
| `running_sensor` | The configured source running sensor, if any. |
| `reason` | Why the source is requested or not, such as `requested`, `held for its minimum on time`, or `waiting for the source mode`. |

## The reference plant

The [reference plant](examples/reference-plant.yaml), with Plant `Home`, source `Heat pump`, and zones `Basement`, `Bedroom area`, and `Living area`, gets 32 entities:

- `select.home_mode`, `switch.home_control_equipment`, `sensor.home_status`, `binary_sensor.home_towel_dryer_flowing`, and `sensor.home_towel_dryer_runtime` for the Plant.
- `binary_sensor.heat_pump_requested` for the source.
- For each zone, such as `living_area`: `climate.living_area`, `binary_sensor.living_area_heating_demand`, `binary_sensor.living_area_cooling_demand`, `sensor.living_area_combined_temperature`, `sensor.living_area_dew_point`, `sensor.living_area_duty_cycle`, `binary_sensor.living_area_ceiling_flowing`, and `sensor.living_area_ceiling_runtime`.
- `binary_sensor.living_area_floor_flowing` and `sensor.living_area_floor_runtime` for the living area's underfloor loop.

## What is not an entity

Output faults, missing entities, and outputs awaiting confirmation are Repairs, described in [troubleshooting](troubleshooting.md#repairs).
Hydronicus creates no entity for a valve or a pump; the loop's flowing sensor shows their states, and the output entities themselves stay the ones their own integration provides.
