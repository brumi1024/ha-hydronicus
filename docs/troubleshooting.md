# Troubleshooting

Start with the Plant's **Status** sensor: its state says what the Plant does, and its `reasons` attribute says why.
Then check **Settings > System > Repairs**, where Hydronicus names every problem it needs you to fix.
While you investigate a Plant that controls real equipment, turn **Control equipment** off and let the equipment stop.

## Nothing happens

When a zone should heat and nothing moves, check these in order:

1. The Plant's **Mode** select is on heat, or cool.
2. The zone's thermostat is in the same mode; a new digital thermostat starts off.
   An existing thermostat must report `heating` or `cooling` as its `hvac_action`.
3. The zone's **Heating demand** or **Cooling demand** is on; if not, its `reason` attribute says why.
4. Every output of the zone's loop is armed; the **Status** sensor lists the others in `unarmed_outputs`.
5. **Control equipment** is on; otherwise the Plant is in Dry run, and `proposed` shows what it would do.
6. The loop's valves have had their opening time, 3 minutes by default, before the pump starts.

## Read the status

| Status | What to look at |
| --- | --- |
| `off` | The **Mode** select is off; set it. |
| `idle` | Nothing calls: the zones' demand sensors, and `blocked_zones`. |
| `heating` or `cooling` | `active_loops`, and `proposed` in Dry run. |
| `exercising` | Nothing else runs, and an idle pump is exercised: `exercising` and `idle_since`. |
| `changing_over` | The mode is changing: `reasons`, under `mode`. |
| `degraded` | `outputs_not_responding`, `missing_entities`, `evaluation_error`, and the Repairs. |
| `stopping` | `stopping_outputs`; see [removed equipment keeps running](#removed-equipment-keeps-running). |
| `invalid` | `configuration_problem`, and the [Plant is not valid](#plant-is-not-valid) Repair. |
| unavailable | The Plant has not evaluated yet or is not loaded; check that every digital thermostat has loaded, and the Repairs. |

The `reasons` attribute is keyed by zone slug, loop, output entity, `source`, and `mode`.
The common reasons:

| Reason | Meaning |
| --- | --- |
| `idle: thermostat off` | The zone's thermostat is off. |
| `idle: thermostat not restored` | The zone's digital thermostat has not loaded, or its entity is disabled. |
| `idle: no usable temperature` | A required sensor of the zone is missing or stale, or the zone has no usable reading. |
| `idle: thermostat unavailable` | The zone's existing thermostat is unavailable, or reports an action Hydronicus does not know. |
| `idle: window open` | A window of the zone is open, so the zone does not call until every window has been closed for its delay. |
| `demands: ..., held for its minimum on time` | The zone has reached its target, but its thermostat keeps calling for its minimum on time; `held for its minimum off time` is the same after a call ends. |
| `demands: frost protection: ...` | The zone is heated because its coldest reading is below the frost protection temperature. |
| `dropped: ... unarmed or unavailable` | The loop needs an output that is not armed or not available. |
| `dropped: condensation guard blocks` | The loop's condensation guard blocks cooling; the loop's `.guard` reason shows the reference and the threshold. |
| `min-flow path` | The loop is held open for a pump the source runs. |
| `held open as a path` | The loop stays open because a pump that may still run needs it. |
| `overrun` | A switched pump runs on after heating ended. |
| `exercise` | The loop or pump is exercised; `exercise over` is its pump stopping. |
| `waiting for the source mode` | The source's mode select does not show the right option yet. |
| `waiting for a path for every source-driven pump` | A pump the source runs has no ready loop yet. |
| `held for its minimum on time` | The source request stays on for its minimum on time. |
| `held off for its minimum off time` | The source request stays off for its minimum off time. |
| `no ready loop calls` | No loop that a zone calls for is ready yet. |
| `stopping heat before cool` | The mode is changing, and the old mode is still stopping. |
| `waiting for the mode dwell before cool` | The mode is changing, and the dwell has not passed. |

## Common problems

### A zone does not call

- A required sensor that is unavailable, stale, in an unsupported unit, or outside its plausible range stops the zone from calling; after 10 minutes, [a Repair](#a-sensor-blocks-its-zone) names it.
  [Sensors](configuration.md#sensors) lists the accepted units and ranges.
- A reading is stale an hour after its last report, whether its value changed or not.
  A sensor whose heartbeat is rarer needs a longer `max_age` in the [plant file](plant-file.md#sensors).
- A zone that follows an area uses the **Temperature sensor** and **Humidity sensor** in the area's **Area settings**; its **Combined temperature** sensor's `areas` attribute shows what it read.

### Cooling is not offered

The **Mode** select offers cool only when a loop of the Plant cools.
A loop may cool only with a condensation reference: its pump's **Supply temperature sensor** or its own **Surface temperature sensor**.
Its zone also needs a humidity sensor, of its own or through an area.

### Cooling stays blocked

The condensation guard blocks while the coldest reference is less than 2 K above the zone's worst-case dew point, and releases 3 K above it, after at least 5 minutes.
Compare the zone's **Dew point** sensor with the loop's `.guard` reason in `reasons`, which shows the reference and the threshold.
It also blocks when the reference has not reported for 30 minutes, when the zone has no usable humidity reading, or while a condensation switch is on or unavailable.
A plant loop reads the dew points of the zones it runs with, or of every zone when it runs with the source.

### A zone runs nearly all day

A zone's **Duty cycle** sensor shows the share of the last 24 hours in which its loops passed flow.
Compare the zones over a few days of similar weather in the same mode.
A zone that stays near 100 percent while the others run much less gets too little heat or cooling: its loops are undersized, or the hydraulic balancing gives it too little flow.
Open its balancing valves or raise its flow, or throttle the zones that reach their targets easily, then watch the duty cycles settle.
Only flow inferred from live equipment observations counts, so duty cycle reads 0 in Dry run.
A pump flow sensor proves circulation, not individual loop flow or delivered heat.
Without flow proof these remain estimates, and unknown configured feedback contributes no runtime.

### The equipment is in an unexpected state

Turn **Control equipment** off, and wait until its `live` attribute is false.
If equipment still runs, stop it by hand or with its own controls.

### Removed equipment keeps running

After a change removes outputs that were running, the **Status** reads `stopping`, and `stopping_outputs` lists the old outputs not yet seen off.
The new configuration runs once that list is empty.
An output that does not respond keeps the list from emptying and raises [a Repair](#an-output-does-not-respond).
An output that was unavailable when you saved the change, or that was never armed, is left as it is; stop it by hand.

## Setup and forms

- Hydronicus is not listed: check that HACS installed it and that Home Assistant has restarted since. Hydronicus requires Home Assistant 2026.9.0 or newer.
- A form does not offer an entity: the forms offer only entities of the right domain, such as a `switch` or `valve` for a valve, and never the entities Hydronicus itself provides.
- A form or plant file is refused: the message names the problem and where it is, such as `Zone Living area, loop Floor, pump`; the [plant file errors](plant-file.md#errors) explain the common ones.
  An output that another Plant already uses cannot be used again.
- A plant file import is refused with `This Plant is already set up.`: remove that Plant first, or use **Replace from a plant file** on it.
- A pump cannot be removed: a loop still uses it; move or remove those loops first.
- A new pump the source runs is refused: it needs loops to hold open, and a new pump has none yet.
  Add it with **A separator guarantees its flow**, give it loops, then change its **Minimum flow** back and choose its **Min-flow loops**.

## Repairs

Hydronicus raises these under **Settings > System > Repairs**, and removes each one by itself once its problem is gone.
Diagnostics list them by the key in the second column.

| Repair | Key | Severity |
| --- | --- | --- |
| [Plant is not valid](#plant-is-not-valid) | `invalid_plant` | Error |
| [A Plant cannot evaluate](#a-plant-cannot-evaluate) | `evaluation_failed` | Error |
| [An output does not respond](#an-output-does-not-respond) | `output_not_responding` | Error |
| [Outputs awaiting confirmation](#outputs-awaiting-confirmation) | `outputs_awaiting_confirmation` | Warning |
| [An entity does not exist](#an-entity-does-not-exist) | `missing_binding` | Error |
| [An area names a missing sensor](#an-area-names-a-missing-sensor) | `missing_area_sensor` | Error |
| [A zone covers a missing area](#a-zone-covers-a-missing-area) | `zone_area_missing` | Error |
| [A zone has no temperature sensor](#a-zone-has-no-temperature-sensor) | `zone_without_temperature_source` | Error |
| [An area names a Hydronicus sensor](#an-area-names-a-hydronicus-sensor) | `zone_area_self_feed` | Warning |
| [A sensor blocks its zone](#a-sensor-blocks-its-zone) | `zone_sensor_unusable` | Error |
| [A condensation input blocks cooling](#a-condensation-input-blocks-cooling) | `condensation_input_unusable` | Error |

### Plant is not valid

The stored configuration is not a valid Plant, usually because a zone it still needs was deleted, such as the zone of a pump's only min-flow loop.
The Plant stops its equipment in order, then only observes, with only its **Mode**, **Control equipment**, and **Status** available.
Select **Submit** to open the Plant's **Reconfigure** and fix it, for example by choosing other **Min-flow loops**.

### A Plant cannot evaluate

An evaluation failed with an error, which is a bug in Hydronicus.
Meanwhile the Plant sends no new command, so the outputs stay as they were; if they must not, stop them by hand.
Its status changes to `degraded` and reports `evaluation_error`, while the last successful view and its `evaluated_at` remain available for diagnosis.
It tries again every minute, and the Repair clears after the next evaluation that works.
Please report it with the error from the log and the Plant's diagnostics.

### An output does not respond

Hydronicus asked an output to change three times and never saw the change, or a `valve` entity still moves long after its opening time.
Check that the device is powered and reachable, and that its state in Home Assistant follows it.
Hydronicus keeps retrying, and the Repair clears once the output shows what it asked for.

### Outputs awaiting confirmation

Some outputs are not armed, such as the valves of a new zone, so the loops that need them do not run.
Check the outputs under **Outputs to arm**, then select **Submit**.
This Repair appears once any output of the Plant is armed; for a new Plant, use **Arm outputs** instead.

### An entity does not exist

The Plant uses an entity that Home Assistant does not have, such as a renamed valve, and whatever needs it is blocked.
Restore the entity, or select **Submit** to open the form that uses it, choose another entity, and save.

### An area names a missing sensor

An area's settings name a sensor that does not exist, usually because the sensor was renamed; Home Assistant does not update areas when an entity ID changes.
Open the area's **Area settings** and choose the sensor again.

### A zone covers a missing area

A zone covers an area that no longer exists.
Select **Submit** to open the zone's settings and remove the area, or create an area with the name the Repair gives.

### A zone has no temperature sensor

A zone with a digital thermostat has no temperature sensor it can follow, so it does not heat or cool.
Select **Submit** to add a sensor or an area to the zone, or choose a **Temperature sensor** in its area's settings.

### An area names a Hydronicus sensor

An area's settings name a sensor that Hydronicus provides, such as a zone's **Combined temperature**, which would feed the Plant back into itself, so the zone ignores it.
Choose a sensor that measures the room in the area settings.

### A sensor blocks its zone

A sensor the zone requires has had no usable reading for 10 minutes, so the zone does not call, and its loops do not cool.
Check the sensor, its battery, and its connection.
If it reports only on change, and less often than its `max_age`, raise `max_age` in the [plant file](plant-file.md#sensors).
Area sensors are optional unless the plant file makes them `required`.

### A condensation input blocks cooling

A condensation switch, supply temperature, or surface temperature of a cooling loop has had no usable state for 10 minutes, so the loop cannot cool.
The Repair names the input and the loops it blocks, and shows whatever the Plant mode is, because cooling cannot start without it.
Check the device, its battery, and its connection.

## Commissioning optional controls

The **Status** sensor's `blocking_reason` gives the leading current obstruction.
Use `evaluated_at`, `evaluation_age_seconds`, and `next_evaluation_at` to distinguish an old successful view from a controller waiting for its next deadline.
The next evaluation is a controller check, not a guarantee that a pump or valve will change then.
`pending_commands` shows each requested target, its age, and how many attempts were made.
`sensor_health` reports numeric input freshness and configured maximum ages.

Compare `pump_operation` and `source_operation` with the equipment's own feedback.
Each includes its evidence `basis`, and unknown feedback appears as an unknown value rather than confirmed stopped equipment.
`observed_flow` remains separate from the simulated proposals in Dry run.
The loop's `flow_basis` and `pump_running_basis` show which parts are inferred.

### The source waits for its supply temperature

Confirm that the supply number is armed, supports a temperature unit, and advertises a range that includes the target.
The source waits for observed confirmation within its configured `tolerance`.
A missing or stale outdoor input blocks an outdoor-compensated heating request; check its `sensor_health` and `max_age`.
An outdoor sensor reporting the same value again still refreshes its age.
Cooling may raise its target for the measured dew-point margin; if that exceeds the configured maximum, it must remain blocked.
Do not increase a limit just to clear a block without checking the emitters and source requirements.

### A schedule does not start when expected

Confirm that the thermostat has selected its `schedule` preset, the helper exists, and the Plant and thermostat use the same mode.
A manual target change or another preset leaves schedule control.
Inspect the thermostat's `schedule_status`, `planned_target`, `effective_target`, and `early_start` attributes.
A valid off schedule applies setback, while an unavailable helper falls back to manual comfort.
Early start also needs a future next event and a positive maximum lead time.
Its rate describes room temperature recovery in K/hour, not water temperature change, and its limit may be shorter than the recovery the room actually needs.

## Recovery learning and weather

Start with the thermostat's `learning_mode`, `learning_reason`, `learning_confidence`, and `recovery_method` attributes.
Observe intentionally keeps `recovery_method` at `configured`, even when a shadow prediction has confidence.
Assist also falls back to `configured` until independent recovery episodes and prediction validation support the current deficit.
An available provisional prediction is not evidence that active learning is enabled.
The configured maximum early-start limit still applies when the predicted recovery takes longer.

Learning ignores Dry run and interrupted or unreliable observations.
Check `learning` in diagnostics for each zone's collection reason, active episode, accepted history, and separate heating and cooling estimates.
Recovery requires both room temperature reports and usable circuit observations; output-derived circulation remains an estimate unless independent feedback proves it.
Use **Reset recovery learning** after an installation change when you want to discard a zone's history explicitly.
The reset leaves targets, presets, arming, and hydraulic timers alone.

Check `forecast` in diagnostics for unsupported hourly forecasts, unavailable reports, coverage, expiry, and failed retrievals.
Repeated forecast content retains its original first-observed age, so another successful retrieval does not necessarily make it fresh.
`issued_at` is `null` when the provider issue time is unknown, and `quality` reports that limitation.
A stale or missing forecast returns recovery planning to its learned baseline or configured rate.
Measured condensation and temperature inputs remain authoritative.

## Logs and diagnostics

Open **Settings > System > Logs** and filter for `hydronicus`.
Hydronicus logs a warning when a command fails or times out, when its saved state or the Plant's configuration cannot be read, when thermostats do not load, and when it stops the outputs of an old configuration.
It logs an error when an evaluation fails, and when it refuses a Plant created by an earlier version.

**Download diagnostics** on the Plant's entry gives you a file with:

| Key | Content |
| --- | --- |
| `plant` | The Plant as a plant file. |
| `options` | The armed outputs and **Control equipment**. |
| `requested_mode` and `status` | The **Mode** select and the **Status** sensor. |
| `observations` | What the last evaluation read. |
| `desired` | What the last evaluation decided, with its reasons. |
| `desired.comfort` | The authoritative comfort proposal used for each digital thermostat's demand, including recovery method and bounded early-start decision. |
| `learning` | Bounded recovery observations, collection reasons, active episodes, and separate mode estimates with confidence and validation evidence. |
| `forecast` | Optional hourly forecast source, freshness, coverage, retrieval failures, and provider issue-time uncertainty. |
| `state` and `reconcile` | The saved timers, and the commands waiting for a result. |
| `unusable_inputs` | When each blocking sensor and condensation input became unusable. |
| `flow` | Each loop's runtime, and each zone's flow per hour. |
| `repairs` and `issues` | The outputs that do not respond, and the current Repairs. |
| `proposals` | The last 50 commands Dry run proposed. |
| `missing` | The entities that do not exist. |
| `configuration_problem` | Why the configuration is not valid, or none. |
| `stopping` | While an old configuration stops: what it stops, and what is not yet off. |

Nothing in the diagnostics is redacted: they include entity IDs, area IDs, and the names of your Plant and zones.
Review them before you share them, and use the [diagnostic bug report template](../.github/ISSUE_TEMPLATE/diagnostic-bug-report.md).

## Recovery

- The Plant fails to set up: a Plant created by an earlier version is refused, and the log says it must be set up again; see the [release notes](releases) of the version you came from.
- A test instance is no longer trustworthy: restore a Home Assistant backup rather than editing `.storage` by hand, and repeat the test from a clean state.
