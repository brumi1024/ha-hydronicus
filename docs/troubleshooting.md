# Troubleshooting

This guide covers the current Dry run and controlled-heating implementation.
It is written for a disposable or staging Home Assistant instance.

## Before troubleshooting

Record the Hydronicus version, Home Assistant version, and the commit or HACS version being tested.
Keep credentials, access tokens, private addresses, and household-specific entity details out of issue reports.

If the test involves real sensors, confirm that the Plant is still in Dry run before continuing.
Dry run should not issue physical actuator service calls.

## Installation and setup

### Hydronicus is not listed in HACS

Confirm that the repository was added under HACS **Custom repositories** with type **Integration**.
Reload HACS or restart Home Assistant after installing the repository if the integration does not appear.
Check that the repository contains the integration under `custom_components/hydronicus`.

The repository is not currently a HACS default repository, so searching the default catalog alone is insufficient.

### Add integration fails immediately

Check the Home Assistant log for the first Hydronicus exception.
Confirm that Home Assistant meets the repository's minimum declared version.
Remove and reinstall only after preserving the relevant log excerpt and configuration backup.

Do not create a second Plant to work around a validation error.
First confirm whether a Plant with the same repository installation already exists.

### A setup form cannot select an entity

The **Pump entity** of guided setup and the pump form expects a `switch` entity.
The zone form's **Areas** lists the Home Assistant areas, **Extra temperature sensors** expect `sensor` entities, and **Existing climate thermostat** expects one `climate` entity.
**Loop valves** and the loop form's **Valves** expect `switch` or `valve` entities.
Confirm that the synthetic entities have the expected domain and are visible in Home Assistant.
Temperature pickers list only sensors with the `temperature` device class, and humidity pickers list only sensors with the `humidity` device class.
Give a template or helper sensor the matching `device_class` if it is missing from the list.
Pickers never offer entities that Hydronicus itself creates, because binding a Hydronicus sensor back into a zone would create a feedback loop.
An entity chosen before this filtering existed stays selected when you reconfigure the object.

### The zone form has no pump or shared loop field

**Pump** appears only when the Plant has two or more pumps; with one pump, the zone's loop uses it.
**Shared loops** appears only when the Plant has shared loops, and **Shared valves** only when it has shared valves.
Add pumps in the Plant settings, and add shared loops and shared valves in the [plant file](plant-file.md).
**Add zone** stops with **The Plant has no pump yet. Add a pump before adding a zone or a loop.** until the Plant has a pump.

### A review asks to confirm a shared pump warning

Zones whose loops share one pump, as in every manifold that guided setup builds, produce a warning that the shared pump limits independent control.
The topology is valid; the warning, such as `Pump Circulation pump is shared by loops Living room loop, Bedroom loop; separate zone thermostats cannot independently control heating and cooling through the same pump.`, says that the zones cannot be controlled independently through the shared pump.
Turn on **I understand these warnings** to save.
Later edits do not ask about the shared pump again, because only a warning that a change introduces needs a confirmation.
Unused equipment is reported without ever needing a confirmation.

### A plant file is rejected

The form names the path of the first problem, such as `zones.bedroom.loops.bedroom_loop.pump`, followed by a message.
A problem with the whole file, such as invalid YAML, is reported at the top level.
An empty editor, or YAML that the editor cannot read, is reported as a plant file that is empty or not valid YAML, and the editor marks the line with the YAML problem.
Check the key at that path against the [plant file reference](plant-file.md#errors).

An import that stops with **This Plant is already configured.** has a top-level `id` of a Plant that already exists.
Delete that Plant first to rebuild it from its file, or remove the `id` line to create a new Plant.

When you edit a Plant's file, **This plant file belongs to another Plant. Remove its top-level id, or set it to this Plant's id, to apply it here.** means the file's `id` differs from the Plant being edited.

A file that binds an entity provided by Hydronicus is refused with the path and entity ID, because that entity would feed the Plant back into itself.

### A pump cannot be removed

A pump that a loop still uses cannot be removed, and the error names those loops.
Move each loop to another pump in its zone's **Edit or remove a loop** step, or edit the plant file, then remove the pump.

### The review reports an invalid topology

Review the selected sensor, valve, and pump entities.
Confirm that the loop and Delivery Route references are complete and that no object was removed while a relationship still points to it.
Hydronicus rejects inconsistent graphs, and a zone that no enabled Delivery Route leaves, rather than guessing a relationship.
A loop, valve, or pump that no enabled Delivery Route reaches is accepted, reported as unused equipment, and never requested.

## Areas

### The zone form stops with a missing temperature reading

The error `A zone that Hydronicus controls needs a temperature reading.` appears on **Areas** when none of the chosen areas names a temperature sensor and no extra temperature sensor is chosen.
Choose a temperature sensor in the settings of one of the areas, or add an extra temperature sensor, and submit again.
An existing climate thermostat does not need one, unless the zone cools.

### An empty zone name is refused

An empty **Zone name** takes the name of the one chosen area, or of the floor that every chosen area is on.
Areas on different floors, or without a floor, have no common name, so the form asks for one.

### The area settings do not offer the sensor

Home Assistant's area settings offer only the sensors that belong to the area, and the currently chosen one.
Open the sensor's entity settings and set its **Area**, or put its device in the area, then open the area settings again.
Only sensors with the `temperature` device class appear as a temperature sensor, and only `humidity` sensors as a humidity sensor.

### The zone does not follow the area's sensor

Open the zone's **Combined temperature** sensor in **Settings > Tools > States** and check its `areas` attribute, which lists the sensors each area resolves to, and `usable_sensor_ids`.
Choosing another sensor in the area settings reloads every Plant that covers the area, once; the attribute shows the new sensor after that reload.
If it does not, check that the zone covers that area in the zone's **Name, areas, thermostat owner, and sensors** step.
A sensor listed in `excluded_optional_sensor_ids` was stale or unavailable, and an area temperature is optional by default, so the zone used its other readings.

### A zone covers a missing area

The repair `Home, zone Bedroom: missing area Kids room` means an area that zone Bedroom of Plant Home covers was deleted.
Every area repair names its Plant and zone first, because several Plants can have zones and areas with the same names.
The zone gets no reading from the area, and the rest of its areas and sensors keep working.
Select **Submit** in the repair to open the zone's edit menu, choose **Name, areas, thermostat owner, and sensors**, clear the area listed as `Kids room (no longer exists)` under **Areas**, and save.
The form's description names the missing area too.
Creating the area again also clears the repair, but Home Assistant makes a new area's ID from its name and offers no way to choose the ID.
The repair therefore names the area to create, such as `Kids room` for the ID `kids_room`, and you can rename the area afterwards without changing its ID.
The repair and the zone card show a missing area by the name it last had, or by a name spelled from its ID after Home Assistant restarts, and the card marks it Missing until the area is removed.
The Plant header reports the Plant as `degraded` while an area repair is open, and the zone shows the problem as an alert.

### A zone has no temperature sensor

The repair `Home, zone Bedroom: no temperature sensor` means that none of the zone's areas names a temperature sensor that Hydronicus can follow, and the zone has no extra temperature sensor.
The zone is blocked and neither heats nor cools, and its card says so once, with the alert `No temperature sensor`.
The diagnostic **Blocked reason** sensor of the zone reads `Blocked: no usable temperature sensors remain.`
Choose a temperature sensor in the settings of one of its areas, or select **Submit** in the repair to add an extra temperature sensor or another area.

### An area names a Hydronicus sensor

The repair `Home, zone Bedroom: area Bedroom names a Hydronicus sensor` means that the area settings name a sensor that Hydronicus provides, such as a zone's **Combined temperature**.
Following it would feed the Plant back into itself, so every zone that covers the area ignores it, and each of those zones reports it.
A zone device that Hydronicus put in the area makes its **Combined temperature** appear in the area's sensor list, which is the usual way this happens.
Open the area settings and choose a sensor that measures the room.

### A repair says an area sensor is missing

Home Assistant does not update an area's sensors when the sensor's entity ID is renamed, so the area still names the old ID.
The repair `Home, zone Bedroom: missing temperature sensor of area Bedroom` names the area; open its area settings, choose the sensor under its new ID, and save.
The repair clears as soon as the sensor is available again.

### A repair or card shows an old area name

Renaming an area changes no sensor, so it does not reload the Plant.
Repairs and the cards keep the old name until the Plant reloads for another reason, such as an edit or a Home Assistant restart.

## Unavailable or invalid sensors

### The zone is unavailable or demand is off

An unavailable, unknown, non-numeric, non-finite, untimestamped, or stale required sensor blocks the zone immediately.
The zone **Blocked** binary sensor turns on, the diagnostic **Blocked reason** sensor explains the failure, and the zone releases demand even during a minimum-active hold.
An unusable optional sensor is excluded from aggregation and appears in the attributes of the zone **Combined temperature** and **Blocked** entities.
If no usable sensor remains, the zone blocks even when every configured observation is optional.

Check the sensor state in **Settings > Tools > States**.
Use a numeric value with a supported unit for the simulated sensor.
Check the observation's configured required status, maximum age, and calibration offset before changing the topology.
Do not paste private device attributes into a public report.

### A sensor with a valid number is still unusable

Check the sensor's `unit_of_measurement` attribute in **Settings > Tools > States**.
A temperature observation must report `°C`, `°F`, `K`, or no unit, and a humidity observation must report `%` or no unit.
Any other unit, including a misspelled one such as `C` or `degC`, makes the observation unusable, so a required sensor blocks the zone and demand is released.
This is deliberate: Hydronicus fails closed rather than guessing what an unknown unit means.
Fix the unit on the source entity, for example in the template sensor definition, and the zone recovers on the next state change.
A value without a unit is assumed to be Celsius, so a unit-less sensor that reports Fahrenheit produces a wrong temperature rather than a blocked zone; add the unit to such a sensor.
The **Blocked reason** sensor names the cause, for example `sensor.living_temperature (unsupported unit 'degC')`.

### A sensor is reported as an implausible value

The **Blocked reason** sensor shows `implausible value` with the reading converted to Celsius, or to percent for humidity.
The reading has a supported unit but lies outside the [plausible range](configuration.md#plausible-observation-ranges) for its observation type.
Typical causes are a disconnected probe that reports a fault value such as -127 °C, a template that reports 0 K when its source is unavailable, and a sensor whose unit does not match its value, such as a Celsius value labelled `K`.
Hydronicus fails closed for such a reading: a required sensor blocks the zone, a loop reference blocks cooling, and a Source temperature disqualifies the Source.
Fix the sensor or its unit at the source, and the observation recovers on the next state change.

### The temperature differs from the value Home Assistant shows

Hydronicus converts `°F` and `K` observations to Celsius before evaluation, and its own entities store Celsius.
Home Assistant displays those entities in the configured unit system, so a converted value can look different from the source sensor while describing the same temperature.
Compare the values after converting them to one unit before changing a target or calibration offset.

### A battery sensor appears stale

Hydronicus uses Home Assistant's latest report timestamp and the observation's configured maximum age.
The runtime schedules reevaluation at the freshness deadline, so a zone can become blocked without another state-change event.
Increase the maximum age only when the sensor's real reporting behavior justifies it.
Do not use a longer software timeout as a substitute for reliable sensing or independent physical protection.

### Multiple sensors give an unexpected aggregate

Check the selected aggregation policy and the current state of every usable sensor.
Mean and median use all usable calibrated readings selected for the zone.
Minimum and maximum intentionally bias the aggregate toward one extreme.
Designated reference requires exactly one configured reference observation.
Weighted mean uses the positive weights configured through detailed sensor editing.
Inspect the zone **Combined temperature** sensor attributes to confirm which observations were usable or excluded.

### Demand remains on or off after crossing the threshold

Inspect the zone explanation for a minimum-active hold or minimum-idle lockout deadline.
Changing a target or preset reevaluates the zone immediately but does not bypass a remaining duration.
A required-sensor failure is the exception: it blocks and releases demand immediately.

### An external thermostat does not create demand

Inspect the external climate entity's `hvac_action` attribute.

Only `heating`, `preheating`, and `cooling` are accepted demand actions.

`idle` and `off` release demand immediately.

Missing, unavailable, unknown, malformed, contradictory, or unsupported actions fail closed.

The external target and current temperature attributes do not reconstruct demand.

For cooling, verify that the zone humidity observations and loop supply or surface safety observations are configured, fresh, and valid.
If cooling blocks while the zone looks dry, compare the `dew_point_temperature` and `dew_point_humidity` attributes of the zone **Cooling dew point** sensor with each zone sensor, including the sensors of its areas, because the warmest and the most humid sensors set the dew point.

Hydronicus never calls the external climate entity.

If the external entity is missing, the zone appears in Repairs as an unresolved thermostat binding.

## Warnings, explanations, and virtual states

### An explanation or reason entity is not on the dashboard

Explanations and reasons are diagnostic entities.
Open the zone or Plant device page and look under **Diagnostic** for **Explanation**, **Blocked reason**, **Cooling blocked reason**, **Mode changeover explanation**, and **Source recommendation**.

### A zone has no cooling entities, or the Plant has no source entities

A zone has cooling entities, and its thermostat offers cool modes, only when it routes to a loop with cooling turned on.
The Plant has source entities only when it has at least one source.
Turning off a loop's cooling or removing the last source removes the matching entities on the next reload.

### Demand is on but the real valve or pump does not move

This is expected while the Plant is in Dry run.
The valve and pump request entities describe what Hydronicus would request without sending the service call.
If Dry run is off, verify that the configured entity is one of the confirmed outputs and that the confirmation completed successfully.
Source-selector operations remain proposed even when Dry run is off.

Do not edit Home Assistant config-entry storage to bypass the UI control or its safe-shutdown path.
The internal executor tests are not a supported rollout procedure.

### The valve is opening and the pump is not requested

This is expected while the configured virtual valve opening time has not elapsed.
The current sequence waits for virtual valve readiness before requesting the pump.
The valve state and zone explanation entities should show the reason.

### The pump remains requested after demand stops

This is expected during the configured virtual pump overrun period.
The overrun protects the modeled loop sequence in Dry run and active heating mode.
It does not prove that a physical pump needs the same timing.

### A shared pump does not turn off when one zone releases

This is expected when another requested loop still consumes the same pump.
Inspect the topology preview and the zone demand entities to identify the remaining virtual consumer.

### The topology preview counts do not match the setup

Reload the config entry after changing a zone or a source.
Then inspect the topology preview attributes and the Home Assistant log for a reload exception.
Do not assume that a display name identifies the persisted object relationship.

### A shared-valve warning appears during configuration

The proposed topology is valid, but the named loops share a valve that limits independent hydraulic control.
Review the affected valve, loops, and zones before confirming the non-fatal warning.
Do not suppress the warning by modeling one physical valve as several independent actuators.

## Logs and diagnostics

Capture the earliest relevant error, not only the final repeated warning.
Include the Home Assistant version, Hydronicus version, operation being attempted, and the redacted exception text.

Useful checks include:

1. Open **Settings > System > Logs**.
2. Filter for `hydronicus`.
3. Reproduce the problem once with the smallest synthetic topology.
4. Copy the first relevant exception and its short traceback.
5. Redact tokens, credentials, hostnames, private addresses, and household-specific entity details.

Download redacted diagnostics from the Hydronicus config entry or device page before filing an issue.
Diagnostics count each zone's areas, the area sensors it follows, its missing areas, and the Hydronicus sensors its areas name, without the area or sensor names.
Hydronicus also creates Repairs issues for unresolved configured entity bindings and for the [area problems](#areas) of zones, and removes them once the problem is gone.
Each repair names the Plant and the entity it misses, such as `the switch bound to Bedroom loop valve`.
A missing required sensor or any other missing binding is an error, because it blocks what depends on it.
A missing optional sensor is a warning that says Hydronicus leaves the sensor out instead of blocking control, like the `optional_sensor_unavailable` alert on the cards.
A repair for a zone's binding opens that zone's edit menu, and a repair for a pump opens the Plant settings.
A repair for a shared loop, a shared valve, or the source selector cannot open a form; edit the binding with **Edit plant file** in the Plant settings, or restore the original entity.
If diagnostics are unavailable or a binding problem does not produce a Repair, capture the first relevant log exception and report it as a runtime problem.
Use the [diagnostic bug-report template](../.github/ISSUE_TEMPLATE/diagnostic-bug-report.md) and provide only the information needed to reproduce the issue.

## Recovery

### The integration reload fails

Keep the Plant in Dry run.
If the integration card reports that the stored configuration cannot be loaded safely, the stored Plant graph could not be decoded or compiled, and Hydronicus did not start a runtime for it.
The message names the first problem it found.
Check for an invalid or partially edited zone or source and restore the last known-good configuration from a Home Assistant backup if necessary.
Then restart or reload the integration and confirm that the topology preview returns.

Reload, unload, removal, and Home Assistant stop do not issue equipment commands.
If Hydronicus observes or conservatively retains active equipment, it logs a warning that names the affected actuator IDs without claiming they were shut down.
Use Safe shutdown or enable Dry run before planned lifecycle work, and wait until the ordered source, pump, and valve sequence completes.
Physical equipment must still have its own independent controls and manual recovery procedure.

### A topology edit unexpectedly enabled Dry run

This is expected.
Every topology or physical binding change, including a zone, loop, or pump edit and a plant file edit, invalidates the prior output fingerprint and returns the Plant to Dry run.
Review the complete graph and the exact valve, pump, and direct source-demand output list before authorizing active heating again.

### A Plant is held in Dry run because of shared outputs

One actuator entity belongs to one live Plant.
When two Plants bind the same valve, pump, or source-demand entity and both are set to run outside Dry run, the first one to claim its outputs during setup runs live.
The other one is held in Dry run before it sends any command.
Its Dry run binary sensor is on, with the `held_by_output_conflict` attribute set to true and `held_by_plant` naming the live Plant.
A repair says that the Plant is held in Dry run because the other Plant is using the same outputs.
Hydronicus keeps the held Plant's Dry run setting and confirmed outputs, and resumes it automatically when the conflict is gone.
That happens when the live Plant enters Dry run, is unloaded, is removed, or fails to set up; the held Plant then reloads through its normal startup and the repair clears.
Reloading the live Plant does not hand its outputs over.
To end the conflict for good, bind different entities in one of the Plants, remove one of the Plants, or turn on Dry run for one of them.

### Turning Dry run off reports another Plant or changed outputs

If the confirmation reports that another Plant controls some of the same entities, that Plant is live and owns them.
This also applies to a Plant that is held in Dry run: its Plant settings show Dry run on, and turning it off is refused until the conflict is gone.
Resolve the overlap as described above before trying again.
If the confirmation reports that the outputs changed since the form was shown, the Plant configuration was edited while the form was open.
Review the updated output list that the form now shows, and confirm again only if it is what you expect.

### A deleted object still appears in the topology preview

Check the Hydronicus log for a message saying that the Plant could not reach Dry run after a zone or source was removed.
Hydronicus deliberately retains the parent graph when safe shutdown fails because deleting an actuator from the active runtime would hide its physical state.
Resolve the actuator failure, use Safe shutdown or enable Dry run, then trigger a Plant reload so the pending deletion can be reconciled.

### The test instance is no longer trustworthy

Stop using real sensor or actuator entities for the test.
Restore the disposable Home Assistant configuration or recreate it from a clean backup.
Repeat the synthetic test before resuming any shadow observation.

### You need to undo an installation

Follow [upgrade and rollback](upgrade-and-rollback.md) for a backup-first rollback.
Do not delete the integration directory from a running Home Assistant instance as a first response to a configuration problem.
