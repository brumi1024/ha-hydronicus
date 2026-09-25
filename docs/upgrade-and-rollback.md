# Install, update, and rollback

Hydronicus uses config-entry version 4.0 as its canonical persisted contract.

## Plants from earlier development versions

Plants created by an earlier development version, with config-entry version 1.1, 2.0, or 3.0, are not migrated.
Home Assistant shows such a Plant as failed to set up, and the Home Assistant log says that it was created by an earlier development version and must be set up again.

To keep a Plant's objects and entity IDs, export its [plant file](plant-file.md) with **Show the plant file** in the Plant settings before you update.
After the update:

1. Remove the Plant under **Settings > Devices & services > Hydronicus**.
2. Rename the top-level `rooms` key of the exported plant file to `zones`.
3. Optionally, give each zone an `areas` list of the Home Assistant areas it covers, as described in [the plant file reference](plant-file.md#areas).
   A zone then follows the sensors those areas name, in addition to the sensors the file lists.
4. Add the Hydronicus integration again, choose **Import a plant file**, and paste the file.

The imported Plant keeps the object IDs of the file, and therefore the unique IDs of its entities.
Review its entity IDs afterwards, because entity settings you changed on the removed Plant belonged to that Plant.
Areas can also be added later in each zone's edit menu.
Without an exported plant file, set the Plant up again with guided setup.
Every Plant starts in Dry run, so review its outputs before you leave Dry run again.

## Fresh HACS installation

1. Open HACS and select **Integrations**.
2. Open the HACS menu and select **Custom repositories**.
3. Add `https://github.com/brumi1024/ha-hydronicus` and choose **Integration** as the repository type.
4. Install Hydronicus.
5. Restart Home Assistant when HACS requests it.
6. Open **Settings > Devices & services > Add integration** and search for **Hydronicus**.
7. Follow [configuration and simulation](configuration.md) and keep Dry run enabled for the first Plant.

The package installs only `custom_components/hydronicus`.
The old `hydronic_climate` package and domain are not part of Hydronicus and must not be created.

## Before changing an installation

Create a Home Assistant backup before updating Hydronicus, changing a Plant that controls heating, or testing a source checkout.

Keep Dry run enabled until the configured sensors, valves, pumps, source demand, topology preview, and proposed operations match the intended Plant.

Do not update or reload Hydronicus during a physical heating intervention.
Use the Safe shutdown action or enable Dry run and confirm the ordered shutdown completes before updating, reloading, unloading, or removing an active Plant.

## Updating after later releases exist

Use HACS to install the selected released version and restart Home Assistant when requested.

After the restart:

1. Confirm the Hydronicus version.
2. Confirm that every Plant loads and shows one Zone entry per zone.
3. Open each zone's edit menu and confirm that its loops and valves are the ones you expect.
4. Review the topology preview, the devices, and the entity IDs.
5. Confirm the Plant returned to Dry run after any topology edit.
6. Use **Show the plant file** in the Plant settings to keep a copy of each Plant.
7. Review the exact output list before authorizing active heating again.
8. Exercise the smallest safe scenario before relying on active heating.

Release-specific compatibility instructions belong in the release that introduces them.

## Rolling back a development checkout

Keep the Plant in Dry run.
Stop the isolated Home Assistant test instance before replacing integration files.
If the older checkout understands config-entry version 4.0, restore `custom_components/hydronicus` from the recorded commit or a clean backup.
If the older checkout predates version 4.0, it cannot load a Plant set up by this version, so restore the complete Home Assistant backup taken before the update.
Start Home Assistant and verify the config entry, object devices, topology preview, and Dry run behavior.

If the configuration is no longer trustworthy, restore the complete Home Assistant backup rather than editing `.storage` by hand.

Never use a destructive Git operation against a working tree that contains someone else's changes.

## Lifecycle boundary

Reload, unload, removal, and Home Assistant stop do not issue implicit equipment commands.
This avoids beginning a timed hydraulic shutdown that the lifecycle operation may not remain alive to complete.
When active equipment is observed or conservatively retained, Hydronicus logs an explicit warning and relies on independent hardware safeguards.
This boundary is not a substitute for using Safe shutdown or enabling Dry run before planned maintenance.
Deleting a zone or source entry is handled differently because it changes the graph rather than merely stopping the integration.
Hydronicus waits for the old graph to reach Dry run before removing the zone or source from parent storage.
If that transition fails, Hydronicus retains the old parent graph and logs the incomplete deletion instead of claiming a safe topology change.

## If rollback is incomplete

Do not activate physical equipment to test whether rollback worked.
Keep independent physical controls in charge of the Plant.
Restore the Home Assistant backup, then repeat the Dry run test from a clean state.
Report the problem with the [diagnostic bug-report template](../.github/ISSUE_TEMPLATE/diagnostic-bug-report.md).
