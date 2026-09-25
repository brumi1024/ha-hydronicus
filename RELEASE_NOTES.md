# Hydronicus {{VERSION}}

This is the first stable release of Hydronicus.
It describes a hydronic heating and cooling Plant as rooms, loops, valves, pumps, and sources, and coordinates them from Home Assistant.
Every new Plant starts in Dry run, so Hydronicus shows what it would do before it controls any equipment.

## Changes since rc.6

### Home Assistant 2026.9

- Require Home Assistant 2026.9.0 or newer.
- Convert temperature observations reported in Fahrenheit or kelvin, so a sensor that reports in °F drives demand correctly, and fail closed on unknown units.
- Reject implausible observations, such as 0 K or -127 °C, instead of acting on them.
- Report the cooling condensation margin as a temperature difference, so it converts correctly under US customary units.
- Modernize entity names, icons, device classes, entity categories, and translations while keeping every entity ID, unique ID, and raw state value.
- Let the climate turn off, turn on, and toggle actions restore the last HVAC mode.
- Modernize the setup forms with selectors, sections, filtered entity pickers, and translated labels.
- Let an unresolved binding repair open the flow that fixes it.
- Load the Lovelace cards automatically, without a dashboard resource.
- Allow each actuator entity to belong to only one live Plant: leaving Dry run is refused on overlap, and a Plant that finds its outputs already owned at startup is held in Dry run with a repair until the conflict ends.
- Authorize exactly the output list that the Dry run confirmation displayed.

### Setup redesign

- Replace the Zone, Circuit, and Actuator entries with one Room entry per room, which owns its thermostat, its sensors, and its private loops and valves.
- Keep every object owned by the Plant or by exactly one room, so removing a room always leaves a valid Plant.
- Replace the initial flow with guided setup: a Plant form with its pump, one form per room, and a review that says how each room connects.
- Add a room edit menu for room basics, the thermostat, sensors, private loops, and valve feedback.
- Add Plant settings for Dry run, pumps, showing the plant file, and editing the whole Plant as a plant file with a change review.
- Add the plant file, a YAML format that imports, exports, and rebuilds a Plant with the same entity IDs, including shared loops, shared valves, sources, and the source selector.
- Add the `hydronicus.export_plant` action, which returns the plant file of a Plant.
- Report Plant equipment that no enabled route reaches as unused, and never request it.
- Ask for confirmation only of the warnings a save introduces, and always of outputs that another Plant binds.
- Add a trial kit in `docs/examples/trial` with a Home Assistant package and a plant file for a two-room simulated manifold.
- Migrate config entries from version 2.0, and from version 1.1 through 2.0, to version 3.0.

### Cooling and the UI pass

- Let cooling valves and pumps follow the Plant Dry run setting like heating, instead of always staying proposed.
- Stop a pump that served cooling as soon as its last cooling loop releases, without overrun, and close its valves right after, so a condensation block no longer leaves chilled water circulating.
- Add an optional Cooling section to guided setup and **Add room** for humidity sensors, a supply or surface reference, and a condensation margin.
- Move Plant settings to the **Configure** action of the Plant entry.
- Name room, valve, pump, and source devices after the object alone, so new setups get entity IDs such as `climate.living`.
- Create cooling entities only for rooms that can cool, and source entities only when the Plant has a source, and remove entities that are no longer provided.
- Never read a Hydronicus entity as an observation or an actuator.
- Use Room and Loop wording throughout the cards, explanations, and errors.
- Add an HVAC mode control to each room tile with exactly the modes its thermostat offers.

### Composable and themable cards

- Add the Room card, `custom:hydronicus-room-card`, which shows one room with its own editor.
- Add an optional, ordered `sections` list to the Plant card: `header`, `alerts`, `rooms`, `paths`, `equipment`, `explanations`, and `operations`.
- Share one Plant subscription between every card on a dashboard.
- Let themes restyle the cards through public `--hydronicus-*` tokens that fall back to Home Assistant tokens, and through documented `part` names, without card_mod.
- Match the stock Home Assistant card look by default.

## Highlights

- Guided setup, room editing, and Plant settings in the Home Assistant UI, plus a plant file for the complete topology.
- Rooms with a Hydronicus thermostat or an existing climate entity, comfort, eco, and away presets, hysteresis, and minimum active and idle durations.
- Required and optional temperature observations with calibration, freshness limits, and mean, median, minimum, maximum, designated-reference, and weighted-mean aggregation.
- Shared valves and pumps with active-consumer tracking, valve readiness before pump start, and pump overrun.
- Cooling with humidity, dew point, and condensation margin checks.
- Deterministic source recommendations and changeover reasoning.
- One Plant-level Dry run setting, proposed versus executed operations, and an ordered safe shutdown when Dry run is turned back on.
- Repairs, redacted downloadable diagnostics, startup reconciliation, and bounded command-failure recovery.
- Plant and Room cards that compose into dashboards and follow the active theme.

## Upgrade

Create a Home Assistant backup before upgrading, because the migration is one way.

Hydronicus requires Home Assistant 2026.9.0 or newer.
Install this release through HACS, restart Home Assistant, and confirm that every Hydronicus Plant loads without errors.

On the first start, Hydronicus migrates each Plant to config-entry version 3.0 before runtime setup.
The migration gives every Zone its own Room entry, makes loops and valves that only one room uses private to that room, and keeps pumps, sources, the source selector, and every other loop and valve as Plant equipment.
It moves every entity and device to its new owner, so entity IDs, customizations, devices, and history stay the same.
A restart during the migration resumes to the same result.

The migration returns every Plant to Dry run and clears the confirmed output list.
Review each room's loops and valves and the topology preview, then turn Dry run off again in **Plant settings** if you want Hydronicus to control the equipment.
Plant settings now open from the **Configure** action of the Plant entry.

Hydronicus removes entities that a Plant no longer provides, such as cooling entities of a room that cannot cool.
If you added `/hydronicus/hydronicus-plant-card.js` as a dashboard resource for an earlier release, remove it as described in the Lovelace guide.

Do not edit Home Assistant config-entry storage by hand to bypass migration or output confirmation.

## Rollback

A release before this one cannot load a migrated Plant, and there is no downgrade migration.
To roll back, restore the Home Assistant backup taken before the upgrade, which also restores each Plant as it was.
Changes made after the upgrade are lost by that restore, so export each Plant's plant file first if you want a record of them.

Keep physical temperature, condensation, pressure, and flow safeguards independently active during any rollback.

## Known limitations

Hydronicus is a coordination layer, not a safety-rated controller.
Keep independent physical safeguards, such as high-limit, pressure, flow, freeze, and condensation protection, in service on every Plant.

Dry run Plants do not issue physical actuator service calls.
When Dry run is off, Hydronicus controls the confirmed heating and cooling valves and pumps, and a configured direct source-demand output.
Source selection remains Dry run only.
Direct source demand is requested only while the Plant is heating, and only after a loop with a running pump is ready.
Hydronicus does not command a chilled-water source, so the source's own supply temperature limits stay in charge.

Reload, unload, removal, and Home Assistant stop do not issue equipment commands.
Use Safe shutdown or turn Dry run on before planned maintenance.

Shared loops, shared valves, and the source selector are edited through the plant file rather than in dedicated UI forms.
If a valid plant file in the editor is edited into invalid YAML, the frontend submits the last valid version, and the review step still shows the changes before anything is saved.

## Hydronicus rename boundary

Hydronicus is installed from `custom_components/hydronicus` and uses the `hydronicus` domain.

The former `hydronic_climate` integration name and domain are not supported and must not be recreated during an upgrade.
