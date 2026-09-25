# Install, update, and rollback

Hydronicus stores each Plant as config entry version 5.0: the Plant in the entry, and each zone in a subentry, in the format of the [plant file](plant-file.md).

## Plants from version 0.1.0

A Plant set up with version 0.1.0, or with an earlier development version, is not migrated.
Home Assistant shows it as failed to set up, and the log says that it was created by an earlier version and must be set up again.

Version 0.1.0 plant files use format 1, which this version does not read; importing one reports `Plant file format 1 is no longer read; describe the Plant in format 2.`
Exports are always format 2.

To move a Plant:

1. Before you update, write down its zones, sensors, valves, and pumps, or keep a plant file exported with **Show the plant file** as a reference.
2. Remove the Plant under **Settings > Devices & services > Hydronicus**.
3. Update Hydronicus and restart Home Assistant.
4. Set the Plant up again with **Guided setup**, or write a format 2 plant file and choose **Import a plant file**.
5. Arm its outputs and check it in Dry run before you turn **Control equipment** on.

The main differences when you rewrite a format 1 file:

| Format 1 | Format 2 |
| --- | --- |
| `hydronicus: 1` | `hydronicus: 2` |
| A pump as `slug: switch.x`, with `overrun_seconds` | `slug: {switch: switch.x, overrun: 180}`, or `driven_by: source` for a pump the source runs |
| Valves under a zone's `valves` or the top-level `valves`, with `opening_time_seconds` and `readiness_entity_id` | Valves only in a loop's `valves`, as entity IDs or `{entity, opening_time, readiness}` |
| A loop needs a valve | A loop has zero or more valves |
| `cooling_enabled`, `supply_temperature_sensor`, `surface_temperature_sensor` on a loop | `modes: [heat, cool]` on the loop, the pump's `supply_temperature`, and the loop's `surface_temperature` |
| Shared loops, shared valves, and a zone's `shared_loops` | A plant loop with `runs: {with_zones: [...]}` |
| `sources` and `source_selector` | One `source` with a `request` switch and an optional `mode` select |
| `temperature_sensors` and `humidity_sensors` | `temperature` and `humidity` |
| `temperature_aggregation`, with median, weights, and a designated reference | `aggregation`: `mean`, `min`, or `max` |
| `max_age_seconds` and `calibration_offset` on a sensor | `max_age`; calibrate the sensor at its source |
| `thermostat: climate.x` | `thermostat: {external: climate.x}` |
| A thermostat mapping with `kind: hydronicus` | `thermostat: {digital: {...}}` with `target`, `presets`, and the deltas |

Keeping the Plant `id` of an old file keeps the Plant ID, but entity unique IDs are now made from object slugs, so review the entity IDs of the new Plant, and your dashboards and automations, afterwards.

## Fresh HACS installation

1. Open HACS, open its menu, and choose **Custom repositories**.
2. Add `https://github.com/brumi1024/ha-hydronicus` with **Integration** as the type.
3. Install Hydronicus.
4. Restart Home Assistant when HACS asks for it.
5. Open **Settings > Devices & services > Add integration** and search for **Hydronicus**.
6. Follow [configuration](configuration.md), and keep **Control equipment** off for the first Plant.

The package installs only `custom_components/hydronicus`.
The old `hydronic_climate` package and domain are not part of Hydronicus and must not be created.

## Before changing an installation

Create a Home Assistant backup before you update Hydronicus, change a Plant that controls heating, or test a source checkout.
Keep a copy of each Plant's plant file from **Show the plant file**.

Do not update or reload Hydronicus in the middle of a physical intervention on the plant.
Turn **Control equipment** off, and wait until its `live` attribute is false, before you update, reload, or remove a Plant that controls equipment.

## Updating

Use HACS to install the new version and restart Home Assistant when it asks.
After the restart:

1. Confirm the Hydronicus version.
2. Confirm that every Plant loads, with one zone subentry per zone.
3. Check the **Status** sensor, the Repairs, and the entity IDs.
4. Check the armed outputs in **Arm outputs** before you turn **Control equipment** on again.

Instructions that only one release needs belong in that release's notes.

## Rolling back

A Plant stored by this version cannot be loaded by version 0.1.0, and a Plant from 0.1.0 cannot be loaded by this version.
To go back, restore the complete Home Assistant backup taken before the update, rather than only the integration files.

To roll back a development checkout on a test instance, stop Home Assistant, restore `custom_components/hydronicus` from the recorded commit, and start it again.
If the older checkout stores Plants in another config entry version, restore the backup instead.
Never edit `.storage` by hand.

## Lifecycle boundary

Reload, unload, removal, and Home Assistant stop never send a command, so the equipment stays exactly as it was.
Hydronicus stores its timers and restores them on the next start, so a reload or restart continues where it left off, and with unchanged observations the first evaluation sends no command.
Removing a Plant, a zone, or an output does not stop the equipment it controlled; stop it first, as [safety limits](safety.md#reloads-restarts-and-changes) describes.

## If rollback is incomplete

Do not run physical equipment to test whether the rollback worked.
Keep the plant's own controls in charge, restore the Home Assistant backup, and repeat the Dry run test from a clean state.
Report the problem with the [diagnostic bug report template](../.github/ISSUE_TEMPLATE/diagnostic-bug-report.md).
