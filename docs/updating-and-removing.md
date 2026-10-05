# Updating and removing

[Installation](../README.md#install) is in the README.
This page covers what comes after: updating Hydronicus, rolling back, and removing it.
Anything only one release needs, such as moving a Plant from an older format, is in that release's [notes](releases).

## Before you change anything

- Create a Home Assistant backup.
- Keep a copy of each Plant's plant file, from **Configure** on its entry, then **Show the plant file**.
- Turn **Control equipment** off, and wait until its `live` attribute is false, so the equipment is stopped in order.
- Do not update or reload Hydronicus while someone is working on the plant.

## Updating

Install the new version with HACS, and restart Home Assistant when it asks.
Then check that:

1. The installed version is the one you intended.
2. Every Plant loads, with one entry per zone under it, and its entity IDs are unchanged.
3. The **Status** sensor and the Repairs look as expected.
4. **Arm outputs** still lists the outputs you armed.

Only then turn **Control equipment** on again.

## Rolling back

A Plant saved by one version may not load in an older one; each version's [release notes](releases) say what to expect.
To go back, restore the complete Home Assistant backup you took before the update, rather than only the integration's files.
Never edit `.storage` by hand.

If a rollback goes wrong, do not run physical equipment to test it.
Keep the plant's own controls in charge, restore the backup, and try the Dry run again from a clean state.

## Removing Hydronicus

Removing a Plant never sends a command, so the equipment stays exactly as it was.
Stop it first, so no valve, pump, or source request is left on:

1. Turn **Control equipment** off, and wait until its `live` attribute is false.
2. Check that the source request, the pumps, and the valves are off; stop anything that still runs with its own controls.
3. Optionally, keep the plant file from **Show the plant file**, so you can import the same Plant later.
4. Open **Settings > Devices & services**, open Hydronicus, and choose **Delete** on the Plant's entry.
   This removes the Plant, its zones, their entities and devices, its Repairs, and its saved state.
5. Repeat for every Plant, then remove Hydronicus in HACS and restart Home Assistant.

Preserve independent hardware protection throughout removal.
Your valves, pumps, sensors, and existing thermostats are untouched; they belong to their own integrations.
Automations and dashboards that used the Plant's entities need updating.
If you loaded the [trial package](getting-started.md#load-the-trial-entities), remove it from `configuration.yaml` as well.
