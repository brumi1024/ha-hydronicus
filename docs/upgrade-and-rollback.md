# Install, update, and rollback

Hydronicus uses config-entry version 3.0 as its canonical persisted contract.
Version 2.0 Plants, and version 1.1 Plants through version 2.0 in the same step, are migrated automatically before runtime setup.

## The version 3 migration

Version 3 replaces the Zone, Circuit, and Actuator entries under a Plant with one Room entry per room.
The migration:

- gives every Zone its own Room entry, with the Zone's name;
- makes a Circuit private to a room when only that room routes to it, and a valve private to a room when only that room's private Circuits use it;
- keeps pumps, sources, the source selector, and every other Circuit and valve as Plant equipment, which becomes shared loops and shared valves;
- moves the entities and devices of every object to its new owner, so every entity ID, entity customization, device, and history entry stays the same;
- drops objects whose entries were deleted while Hydronicus was not loaded, the way deleting them would have;
- removes the old Zone, Circuit, and Actuator entries, which by then own no entities or devices;
- invalidates the confirmed heating outputs and returns the Plant to Dry run.

Source entries stay as they are.
Each step can be repeated, so a restart during the migration resumes to the same result.

The migration is one way.
A release before version 3 cannot load a migrated Plant, and there is no downgrade migration.
Rolling back means restoring the Home Assistant backup taken before the upgrade, which also restores the Plant as it was.
Changes made after the upgrade are lost by that restore, so export each Plant's [plant file](plant-file.md) first if you want to keep a record of them.

After the migration, rooms, their private loops and valves, pumps, and Dry run are edited in the UI, and shared loops, shared valves, and the source selector through the plant file.

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
2. Confirm that every Plant loads and shows one Room entry per room, and no Zone, Circuit, or Actuator entries.
3. Open each room's **Edit room** menu and confirm that its loops and valves are the ones you expect.
4. Review the topology preview, the devices, and the entity IDs, which the migration keeps.
5. Confirm the Plant returned to Dry run after migration or any topology edit.
6. Use **Show the plant file** in the Plant settings to keep a copy of each migrated Plant.
7. Review the exact output list before authorizing active heating again.
8. Exercise the smallest safe scenario before relying on active heating.

Release-specific compatibility instructions belong in the release that introduces them.
The current schema migrates the concrete version 1.1 and 2.0 predecessors only.

## Rolling back a development checkout

Keep the Plant in Dry run.
Stop the isolated Home Assistant test instance before replacing integration files.
If the older checkout understands config-entry version 3.0, restore `custom_components/hydronicus` from the recorded commit or a clean backup.
If the older checkout predates version 3.0, restore the complete Home Assistant backup created before migration, because the migration is one way.
Start Home Assistant and verify the config entry, object devices, topology preview, and Dry run behavior.

If the configuration is no longer trustworthy, restore the complete Home Assistant backup rather than editing `.storage` by hand.

Never use a destructive Git operation against a working tree that contains someone else's changes.

## Lifecycle boundary

Reload, unload, removal, and Home Assistant stop do not issue implicit equipment commands.
This avoids beginning a timed hydraulic shutdown that the lifecycle operation may not remain alive to complete.
When active equipment is observed or conservatively retained, Hydronicus logs an explicit warning and relies on independent hardware safeguards.
This boundary is not a substitute for using Safe shutdown or enabling Dry run before planned maintenance.
Deleting a room or source entry is handled differently because it changes the graph rather than merely stopping the integration.
Hydronicus waits for the old graph to reach Dry run before removing the room or source from parent storage.
If that transition fails, Hydronicus retains the old parent graph and logs the incomplete deletion instead of claiming a safe topology change.

## If rollback is incomplete

Do not activate physical equipment to test whether rollback worked.
Keep independent physical controls in charge of the Plant.
Restore the Home Assistant backup, then repeat the Dry run test from a clean state.
Report the problem with the [diagnostic bug-report template](../.github/ISSUE_TEMPLATE/diagnostic-bug-report.md).
