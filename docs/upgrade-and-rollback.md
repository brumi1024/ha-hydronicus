# Upgrade and rollback

Hydronicus stores each Plant as one config entry; see [Stored configuration](development.md#stored-configuration) for exactly what that holds.
Instructions that only one release needs, such as moving a Plant from an earlier format, belong in that release's notes; see [docs/releases](releases).

## Fresh HACS installation

See [Installation](../README.md#installation) for the HACS steps, then follow [configuration](configuration.md), and keep **Control equipment** off for the first Plant.

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

## Removing Hydronicus

Before removing a Plant, export its plant file and turn **Control equipment** off.
Wait until `live` is false and check that the physical equipment is stopped with its own controls or feedback.
If it has not stopped, stop it with its own controls before continuing.
Delete the Plant entry from **Settings > Devices & services** to remove its zones and Hydronicus entities.
Removal does not send shutdown commands, and deleting a Plant does not remove the hardware entities supplied by other integrations.
After all Plants are removed, remove the custom integration through HACS and restart Home Assistant if requested.
Preserve independent hardware protection throughout removal.

## Rolling back

A Plant stored by one version may not load in another; a version's own [release notes](releases) say whether it can load a Plant an earlier version stored.
To go back, restore the complete Home Assistant backup taken before the update, rather than only the integration files.

To roll back a development checkout on a test instance, stop Home Assistant, restore `custom_components/hydronicus` from the recorded commit, and start it again.
If the older checkout stores Plants in another config entry version, restore the backup instead.
Never edit `.storage` by hand.

## Lifecycle boundary

Reload, unload, removal, and Home Assistant stop never send a command, so the equipment stays exactly as it was; a reload or restart continues where it left off, as [safety limits](safety.md#reloads-restarts-and-changes) describes.
Removing the whole Plant does not stop the equipment it controlled; stop it first with **Control equipment**.

## If rollback is incomplete

Do not run physical equipment to test whether the rollback worked.
Keep the plant's own controls in charge, restore the Home Assistant backup, and repeat the Dry run test from a clean state.
Report the problem with the [diagnostic bug report template](../.github/ISSUE_TEMPLATE/diagnostic-bug-report.md).
