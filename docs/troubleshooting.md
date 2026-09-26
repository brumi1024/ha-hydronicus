# Troubleshooting

Start with the Plant's **Status** sensor: its state says what the Plant does, and its attributes say why.
Then check the Repairs, which name every problem Hydronicus needs you to fix, and download diagnostics when you need to look deeper or report a problem.

## Before troubleshooting

- Reproduce the problem on a disposable instance or with synthetic entities, such as the [trial kit](../README.md#first-simulated-plant), when you can.
- Turn **Control equipment** off while you investigate a Plant that controls real equipment, and let the equipment stop.
- Create a Home Assistant backup before you change a Plant.

## Nothing happens

When a zone calls for heat and nothing moves, check these in order:

1. The Plant's **Mode** select is on heat, or cool.
2. The zone's thermostat is in the same mode; a new digital thermostat starts off.
   An external thermostat must report `heating` or `cooling` as its `hvac_action`.
3. The zone's **Heating demand** or **Cooling demand** is on; its `reason` attribute says why not.
4. Every output of the zone's loop is armed: the **Status** sensor lists the others in `unarmed_outputs`, and the loop's reason reads `dropped: ... unarmed or unavailable`.
5. **Control equipment** is on; otherwise the Plant runs in Dry run, and the **Status** sensor's `proposed` attribute shows what it would do.
6. The loop's valves have had their opening time, 180 seconds by default, before its pump starts.

## The status

| Status | Meaning | Look at |
| --- | --- | --- |
| `off` | The **Mode** select is off, and nothing runs. | Set the **Mode**. |
| `idle` | The Plant is in a mode, and nothing is asked to run. | The zones' demand and `blocked_zones`. |
| `heating` or `cooling` | Something runs, or is asked to run, in that mode. | `active_loops`, and `proposed` in Dry run. |
| `changing_over` | The Plant is stopping the old mode, or waiting for the mode dwell, before the new mode starts. | `reasons`, under `mode`. |
| `degraded` | An output does not respond, or an entity the Plant binds does not exist. | `outputs_not_responding`, `missing_entities`, and the Repairs. |
| `stopping` | A change removed outputs that were running, or left a configuration that is not valid, and the equipment of the previous configuration is being stopped. | `stopping_outputs`; see [removed equipment keeps running](#removed-equipment-keeps-running). |
| `invalid` | The configuration is not valid, and the Plant only observes. | `configuration_problem` and the [Plant is not valid](#plant-is-not-valid) Repair. |
| unavailable | The Plant has not evaluated yet, or is not loaded. | Whether every digital thermostat has loaded, and the Repairs. |

The **Status** sensor's `reasons` attribute explains every decision, keyed by zone slug, loop, output entity, `source`, and `mode`.
Common reasons:

| Reason | Meaning |
| --- | --- |
| `idle: thermostat off` | The zone's thermostat is off. |
| `idle: thermostat not restored` | The zone's digital thermostat has not loaded, or its entity is disabled. |
| `idle: no usable temperature` | A required sensor of the zone is missing or stale, or the zone has no usable reading at all. |
| `idle: thermostat unavailable` | The zone's external thermostat is unavailable or reports an action Hydronicus does not know. |
| `dropped: ... unarmed or unavailable` | The loop needs an output that is not armed or not available. |
| `dropped: condensation guard blocks` | The loop cools and its condensation guard blocks; the loop's `.guard` reason gives the reference and the threshold. |
| `min-flow path` | The loop is held open for a pump the source drives. |
| `held open as a path` | The loop stays open because a pump that may still run needs it. |
| `overrun` | A switched pump runs its overrun after heating ended. |
| `waiting for the source mode` | The source's mode select does not show the Plant mode's option yet. |
| `waiting for a path for every source-driven pump` | A pump the source drives has no ready loop yet. |
| `held for its minimum on time` | The source request stays on for its minimum on time. |
| `held off for its minimum off time` | The source request stays off for its minimum off time. |
| `no ready loop calls` | No loop that a zone calls for is ready yet. |
| `stopping heat before cool` | The mode is changing, and the old mode is still stopping. |
| `waiting for the mode dwell before cool` | The mode is changing, and the dwell has not passed. |

`blocked_zones` lists each zone that cannot get what its thermostat asks for, such as `thermostat asks to cool while the Plant runs heat`.

## Repairs

Hydronicus raises Repairs under **Settings > System > Repairs**, and removes each one by itself once its problem is gone.
Diagnostics list the current Repairs by the key in the second column.

| Repair | Key | Severity |
| --- | --- | --- |
| Plant is not valid | `invalid_plant` | Error |
| An output does not respond | `output_not_responding` | Error |
| Outputs awaiting confirmation | `outputs_awaiting_confirmation` | Warning |
| An entity does not exist | `missing_binding` | Error |
| An area names a missing sensor | `missing_area_sensor` | Error |
| A zone covers a missing area | `zone_area_missing` | Error |
| A zone has no temperature sensor | `zone_without_temperature_source` | Error |
| An area names a Hydronicus sensor | `zone_area_self_feed` | Warning |

### Plant is not valid

The stored configuration is not a valid Plant, so the Plant does not run it.
It stops the equipment of its last valid configuration in order, with the **Status** sensor reading `stopping`, and then only observes, reading `invalid`, with the problem in `configuration_problem`.
Meanwhile it shows only its **Mode** select, **Control equipment** switch, and **Status** sensor, and the entities of its zones are unavailable.
This happens when a zone that the Plant still needs is deleted, such as the zone of a pump's only min-flow loop.
The Repair names the problem; select **Submit** to open the Plant's **Reconfigure**, and fix it there, for example by choosing other **Min-flow loops** or with **Replace from a plant file**.
Saving a valid Plant runs it again.

### An output does not respond

Hydronicus asked an output to change three times and never saw the change.
It keeps retrying, up to every 5 minutes, and the Repair clears once the output shows what the Plant asks for.
Check that the device is powered and reachable, and that its state in Home Assistant follows it.
Meanwhile a pump whose stop is not seen keeps its path open, and a valve whose opening is not seen keeps its loop from counting as ready.

### Outputs awaiting confirmation

Some outputs of the Plant are not armed, such as the valves of a new zone, so the loops that need them do not run while the rest of the Plant does.
Select **Submit** after checking the outputs under **Outputs to arm**; submitting with none checked leaves the Repair in place.
This Repair appears once any output of the Plant is armed; a new Plant with nothing armed is armed in **Arm outputs** instead.

### An entity does not exist

The Plant binds an entity that Home Assistant does not have, such as a renamed valve.
Whatever needs it is blocked: a loop with a missing output does not run, and a zone with a missing required sensor does not call.
Restore the entity, or select **Submit** to open the form that binds it and choose another one: the loop form of a valve, the pump form of a pump switch or supply sensor, the zone form of a zone sensor or thermostat, or **The Plant and its source** for a source entity.
The form is part of the zone's or the Plant's **Reconfigure**, so the change is stored when you save it there.

### An area names a missing sensor

A covered area's settings name a sensor that Home Assistant does not have, usually because the sensor was renamed; Home Assistant does not update the area settings when an entity ID changes.
The area adds no reading until you open **Settings > Areas, labels & zones**, open the area's **Area settings**, and choose the sensor again.

### A zone covers a missing area

A zone covers an area that no longer exists, so the zone gets no reading from it.
Select **Submit** to open the zone's settings and remove the area.
Creating an area with the name the Repair gives also works, because Home Assistant makes a new area's ID from its name.

### A zone has no temperature sensor

A zone with a digital thermostat covers areas that name no temperature sensor Hydronicus can follow, and has no extra temperature sensor, so it does not heat or cool.
Select **Submit** to open the zone's settings and add a sensor or another area, or choose a **Temperature sensor** in the area settings.

### An area names a Hydronicus sensor

A covered area's settings name a sensor that Hydronicus provides, such as a zone's **Combined temperature**.
Following it would feed the Plant back into itself, so the zone ignores it.
Choose a sensor that measures the room in the area settings.

## Setup and forms

### Hydronicus is not listed

Check that HACS installed Hydronicus from the custom repository, and that Home Assistant has restarted since.
The minimum Home Assistant version is `2026.9.0`.

### A form does not offer an entity

The forms offer only entities of the right domain: a `switch` or `valve` for a valve, a `switch` for a pump or the source request, a `select` for the source mode, a `sensor` for temperatures and humidity, and a `climate` entity for an existing thermostat.
They never offer Hydronicus's own entities, because a Plant that reads its own output would feed back into itself.

### A form or plant file is refused

Every form, import, and replace checks the whole Plant and names the first problem, in words such as `Zone Living area, loop Floor, pump`.
[The plant file errors](plant-file.md#errors) list the problems with their paths and messages.
Two more refusals come from outside the Plant:

- An entity that Hydronicus provides cannot be bound.
- An output that another Plant binds cannot be bound; an output belongs to one Plant.

### A plant file cannot be imported

A file that carries the ID of a Plant that is already set up is refused with `This Plant is already set up.`
Remove the Plant first, or change it with **Replace from a plant file**.
**Replace from a plant file** refuses a file of another Plant; remove its `id` line to keep the Plant's own ID.

### A pump cannot be removed

A pump that a loop still uses cannot be removed.
Move those loops to another pump or remove them first, in the zones' **Reconfigure** and in **Plant loops**.

### A new pump the source runs is refused

A pump the source runs that needs an open loop must name loops to hold open, and a new pump has none yet.
Add it with **A separator guarantees its flow**, give it loops, then change its **Minimum flow** and choose its **Min-flow loops**.

### Cooling is not offered

The **Mode** select offers cool only when a loop of the Plant cools, and a loop may cool only with a condensation reference: its pump's **Supply temperature sensor** or its own **Surface temperature sensor**.
A zone that cools also needs a humidity sensor or an area, and so does each zone a plant loop that cools runs with, or every zone when that loop runs with the source.

## Sensors

### A zone does not call

- A required sensor that is unavailable, not a number, stale, in an unsupported unit, or outside its plausible range blocks the zone.
  The [observation units](configuration.md#observation-units) list the accepted units and ranges.
- A sensor is stale 1800 seconds after its last report by default; a battery sensor that reports only on change may need a longer maximum age in the [plant file](plant-file.md#sensors).
- A sensor without a unit is taken as °C.

### The combined temperature is unexpected

The **Combined temperature** sensor combines only usable readings, by the zone's **Combine temperatures by**.
Its `areas` and `sensors` attributes show each reading it had, and which sensor each area names.

### The zone does not follow the area's sensor

Check the area's **Area settings**: the zone follows the **Temperature sensor** and **Humidity sensor** named there, and a change takes effect at the next evaluation.
If the area names a sensor that does not exist, a Repair says so.

### Cooling stays blocked

The loop's condensation guard blocks when its coldest reference is below the zone's worst-case dew point plus 2 K, and releases only 1 K above that, after at least 5 minutes.
The **Dew point** sensor shows the zone's worst-case dew point, and the `.guard` reason in the **Status** sensor's `reasons` shows the reference and the threshold.
A missing or stale reference, or a zone without a usable humidity reading, also blocks.
For a plant loop that cools, the dew points of the zones it runs with count, or of every zone when it runs with the source, so each of those zones needs a humidity reading.

## Logs and diagnostics

Open **Settings > System > Logs** and filter for `hydronicus`.
Hydronicus logs a warning when a command fails or does not return in time, when the persisted state of a Plant cannot be read, when the thermostats of a Plant do not load, when the stored configuration is not valid, and when it stops the outputs of a previous configuration.
It logs an error when it refuses a Plant created by an earlier version.

Download diagnostics with **Download diagnostics** on the Plant's entry.
They hold:

| Key | Content |
| --- | --- |
| `plant` | The Plant as its plant file. |
| `options` | The armed outputs and **Control equipment**. |
| `requested_mode` and `status` | The **Mode** select and the **Status** sensor. |
| `observations` | What the last evaluation read: outputs, readiness sensors, sensors, areas, and thermostats. |
| `desired` | What the last evaluation decided, with its reasons and each zone's demand. |
| `state` and `reconcile` | The stored timers and the commands waiting for a result. |
| `repairs` and `issues` | The outputs that do not respond, and the current Repairs by key. |
| `proposals` | The last 50 commands Dry run proposed, with their times. |
| `missing` | The bound entities that do not exist. |
| `configuration_problem` | Why the stored configuration is not valid, or none. |
| `stopping` | While the previous configuration stops: that configuration, the outputs it stops, and those not yet seen off. |

Diagnostics leave out the Plant ID and every name, but they keep entity IDs, area IDs, and slugs.
Review them before you share them, and remove anything that identifies your household.
Use the [diagnostic bug report template](../.github/ISSUE_TEMPLATE/diagnostic-bug-report.md) to report a problem.

## Recovery

### The Plant fails to set up

A Plant created by an earlier version is refused, and the log says it must be set up again; see [upgrade and rollback](upgrade-and-rollback.md).
A Plant whose stored configuration is not valid loads, stops its equipment, and raises the [Plant is not valid](#plant-is-not-valid) Repair.

### The equipment is in an unexpected state

Turn **Control equipment** off, and wait until its `live` attribute is false.
If equipment still runs, stop it by hand or with its own controls; Hydronicus never commands an output it does not own, and a removed output only while it stops it.

### Removed equipment keeps running

After a change removes outputs that were running, the **Status** sensor reads `stopping`, and `stopping_outputs` lists the outputs of the previous configuration that are not yet seen off.
The new configuration runs once that list is empty.
An output that does not respond keeps the list from emptying and raises the [An output does not respond](#an-output-does-not-respond) Repair; one that is unavailable waits until it returns, so fix the device or stop it by hand.
An output that was unavailable when the change was saved, or that was never armed, is left as it is; stop it by hand.

### The test instance is no longer trustworthy

Restore the Home Assistant backup instead of editing `.storage` by hand, and repeat the test from a clean state.
