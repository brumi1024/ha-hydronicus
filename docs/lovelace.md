# Hydronicus Lovelace Plant card

The Hydronicus Plant card is a bundled TypeScript custom card for one configured Plant.
It presents the Plant state and the controller's structured explanations without exposing configured sensor, valve, pump, source-demand, or private URL bindings.

## Install the card resource

Restart Home Assistant after installing or upgrading Hydronicus so the integration can register its frontend path.
Open **Settings > Dashboards > Resources**.
Select **Add Resource**.
Enter `/hydronicus/hydronicus-plant-card.js` as the URL.
Choose **JavaScript Module** as the resource type.
Save the resource and reload the browser page.

The URL is served by Hydronicus from the installed integration package.
Do not copy the generated bundle into `/config/www`.
The release package validator checks that the bundled JavaScript exists and has the same version as the integration manifest.

## Add one card

Use the Lovelace card editor and select one Plant from the dynamic Plant list.
The editor stores the Plant UUID and an optional density preference.
The equivalent YAML is:

```yaml
type: custom:hydronicus-plant-card
plant: 00000000-0000-4000-8000-000000000001
density: comfortable
```

Replace the example UUID with the UUID of the configured Plant.
The editor does not hardcode Zones, Circuits, valves, pumps, sources, or household entity IDs.

## Card contract

The card subscribes to `hydronicus/subscribe_plant` and validates the versioned presentation schema before rendering.
The integration sends one initial snapshot and subsequent meaningful snapshots after runtime state, diagnostics, or operation outcomes change.
The card can show multiple configured Plants through separate card instances without mixing their snapshots.

The header shows the Plant name, operational status, requested mode, active mode, execution boundary, active source, and recommended source.
The Zones section shows thermostat ownership, current and target temperatures when available, presets for Hydronicus thermostats, demand, sensor qualification, cooling diagnostics, blocked reasons, and coupling notices.
The delivery path section renders the ordered Zone to Circuit to Valve to Pump to Source route.
The actuator section shows shared ownership and the active Circuit consumer set using configured object IDs and names.
The alert and explanation sections surface stable priority-ordered diagnostics and controller reasoning.
The operation section distinguishes proposed, executed, suppressed, failed, and timed-out outcomes.

The presentation schema is version 2.

Hydronicus thermostat Zones receive a permission-filtered Hydronicus climate entity and expose target and preset controls.

External thermostat Zones are explicitly read-only.

The card displays their diagnostic target and current temperature values when available, but never renders target or preset controls for them.

The card never calls the external climate entity.

The backend uses each Zone's Hydronicus-owned demand entity for visibility filtering.

A user without read access to that entity receives none of the Zone's name, observations, demand, routes, alerts, or explanations.
The Plant mode control calls only the Hydronicus-owned mode select entity.
Safe shutdown is a hold-to-confirm action and calls only the Hydronicus-owned shutdown button entity.
Configured physical entity IDs do not cross the presentation boundary and are never rendered as card action targets.

The configured external thermostat entity ID is also redacted from the presentation stream.

The card displays the active Dry run or mixed execution boundary prominently.
It does not provide a Dry run toggle.
The existing Plant configuration and its safety gates remain the authority for whether actuator operations are proposed or executed.

## Layout and accessibility

The card exposes Home Assistant Sections grid options with a default six-row by six-column footprint.
The minimum footprint is four rows by three columns.
The card uses a responsive Zone grid and collapses its controls for narrow layouts.
The `comfortable` and `compact` density values provide a readable default and a denser dashboard option.
Colors are based on Home Assistant theme variables with light and dark theme fallbacks.
Interactive controls have visible focus indicators, keyboard labels, disabled states, and touch-friendly minimum sizes.
Safe shutdown accepts pointer or keyboard hold input and shows hold progress.

## Synthetic staging checks

Use the repository's disposable or synthetic Home Assistant staging workflow before connecting a Plant to real equipment.
Confirm that two Plants remain isolated, permission-filtered users see only their allowed Zones and Hydronicus-owned controls, and reload or unload produces a clean subscription state.
Keep the Plant in Dry run while validating presentation, routing, alerts, and proposed operation outcomes.
Do not interpret a passing card render or a Dry run snapshot as proof of hydraulic, electrical, or equipment safety.
