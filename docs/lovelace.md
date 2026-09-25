# Hydronicus Lovelace Plant card

The Hydronicus Plant card is a bundled TypeScript custom card for one configured Plant.
It presents the Plant state and the controller's structured explanations without exposing configured sensor, valve, pump, source-demand, or private URL bindings.

## Loading the card

Hydronicus loads the card automatically.
Restart Home Assistant after installing or upgrading Hydronicus, then reload the browser page.
No dashboard resource is needed, and the bundle must not be copied into `/config/www`.

The integration serves the bundle from the installed package at a URL that contains the integration version, such as `/hydronicus/0.1.0-rc.6/hydronicus-plant-card.js`, and registers it as a frontend module.
The browser caches that URL, and an upgrade or a rebuilt bundle changes it, so the browser never keeps a stale card.
The release package validator checks that the bundled JavaScript exists and has the same version as the integration manifest.

### Remove the old manual resource

Earlier releases asked you to add `/hydronicus/hydronicus-plant-card.js` as a dashboard resource.
That resource is now redundant.
Open **Settings > Dashboards**, open the three-dot menu, and select **Resources**.
Delete the `/hydronicus/hydronicus-plant-card.js` entry, then reload the browser page.
Resources are only listed when advanced mode is enabled in your user profile.
A dashboard in YAML mode lists resources under `lovelace: resources:` in `configuration.yaml`; remove the entry there and restart Home Assistant.

Until you remove it, the old resource keeps working.
The integration still serves that URL without long-lived caching, and the card ignores the second load.

## Add one card

Open a dashboard in edit mode, add a card, and pick **Hydronicus Plant** from the card picker.
The picker prefills the first Plant you can read.
The visual editor lists the Plants you can read by name and stores the Plant UUID and an optional density preference.
The equivalent YAML is:

```yaml
type: custom:hydronicus-plant-card
plant: 00000000-0000-4000-8000-000000000001
density: comfortable
```

Replace the example UUID with the UUID of the configured Plant.
Existing cards with `plant: <uuid>` keep working unchanged.
The editor does not hardcode Rooms, Loops, valves, pumps, sources, or household entity IDs.

## Card contract

The card subscribes to `hydronicus/subscribe_plant` and validates the versioned presentation schema before rendering.
The integration sends one initial snapshot and subsequent meaningful snapshots after runtime state, diagnostics, or operation outcomes change.
The card can show multiple configured Plants through separate card instances without mixing their snapshots.

The card subscribes once per Home Assistant connection and Plant.
A stream for a Plant whose config entry exists but is not loaded yet, for example while Home Assistant starts or reloads the Plant, is accepted.
It reports the Plant as unavailable and starts sending snapshots once the Plant finishes loading.
While a Plant is unloaded or reloading, the card shows it as unavailable and hides its controls.
After a lost connection, the card keeps the last snapshot with a notice and subscribes again when Home Assistant is reachable.
A transient subscription failure is retried with exponential backoff, from one second up to one minute.
A Plant that no longer exists and a Plant the user may not read are terminal states with a clear message; the card does not retry them.
When the backend revokes access to a stream, it sends an `unauthorized` status event before it ends the stream.
When a Plant is deleted, its streams end with a `plant_not_found` status event.

The card says Room and Loop where the snapshot and the core code say Zone and Circuit.
The header shows the Plant name, operational status, requested mode, and execution boundary.
It adds the active mode only when an explicit requested mode is not active yet, for example during a changeover.
It shows the active and recommended source only when the Plant has sources.
The Rooms section shows thermostat ownership, the HVAC mode, current and target temperatures when available, presets for Hydronicus thermostats, heating or cooling demand, sensor qualification, cooling diagnostics, blocked reasons, and coupling notices.
A Room whose thermostat is off shows Off instead of an idle phase.
The Hydraulic Flow section renders the ordered Room to Loop to Valve to Pump to Source route.
The Equipment section shows each valve and pump with the Loops that currently use it.
The alert and explanation sections surface stable priority-ordered diagnostics and controller reasoning.
The operation section distinguishes proposed, executed, suppressed, failed, and timed-out outcomes.

The presentation schema is version 2.
Each thermostat in the snapshot carries its `hvac_mode`, and a Hydronicus thermostat also carries `hvac_modes`, the modes its climate entity supports.
Every temperature in the snapshot is in degrees Celsius.
The card shows temperatures in the unit system of the Home Assistant instance, and formats numbers with the number format from the user's profile.
Target changes are sent in that unit system, which Home Assistant converts for the climate entity.
The plus and minus buttons step by 0.5 °C, or by 1 °F under US customary units.

Hydronicus thermostat Rooms receive a permission-filtered Hydronicus climate entity and expose HVAC mode, target, and preset controls.
The HVAC mode control offers exactly the modes of the Room's climate entity: Off and Heat, plus Cool and Heat/Cool when the Room reaches a cooling-enabled Loop.
It calls `climate.set_hvac_mode` on that climate entity.

External thermostat Rooms are explicitly read-only.

The card displays their HVAC mode and diagnostic target and current temperature values when available, but never renders HVAC mode, target, or preset controls for them.

The card never calls the external climate entity.

The backend uses each Room's Hydronicus-owned demand entity for visibility filtering.

A user without read access to that entity receives none of the Room's name, observations, demand, routes, alerts, or explanations.
Source summaries and source-selection operations remain Plant-wide because sources serve the shared hydraulic system.
Any user allowed to discover the Plant can see that source state, while configured physical source entity IDs remain redacted.
The Plant mode control calls only the Hydronicus-owned mode select entity.
Safe shutdown is a hold-to-confirm action and calls only the Hydronicus-owned shutdown button entity.
Configured physical entity IDs do not cross the presentation boundary and are never rendered as card action targets.

The configured external thermostat entity ID is also redacted from the presentation stream.

Selecting the Plant name opens the more-info dialog of the Hydronicus mode select entity.
Selecting a Hydronicus thermostat Room name opens the more-info dialog of its Hydronicus climate entity.

When an action such as a mode or target change fails, the card keeps showing the Plant, returns the control to its real value, and shows the error inline until you dismiss it or the next action succeeds.

The card displays the execution boundary prominently.
The badge reads Dry run while nothing executes, Mixed while heating and cooling may execute but source selection stays shadow-only, and Live when every output may execute.
Cooling outputs follow the Plant's Dry run setting like heating outputs, so the card treats a cooling demand like a heating demand and does not describe cooling as shadow-only.
While Dry run is on, the safe shutdown button stays available with a quieter style.
It does not provide a Dry run toggle.
The existing Plant configuration and its safety gates remain the authority for whether actuator operations are proposed or executed.

## Frontend data

The card reads the Home Assistant connection, the action API, the unit system, and the locale from the frontend context groups that Home Assistant documents for custom cards.
When a context is not provided, it falls back to the `hass` object that Home Assistant also sets on every card.
It stores only the values it uses, so state changes of unrelated entities do not re-render the card.

## Layout and accessibility

In the Sections view the card spans the full section width by default, at least six columns, and its height follows its content, so it never overlaps the cards below it.
In the masonry view the card reports a height estimate based on its Rooms, paths, equipment, alerts, and operations.
The card uses a responsive Room grid, horizontally scrollable hydraulic paths, and controls that collapse for narrow layouts.
The `comfortable` and `compact` density values provide a readable default and a denser dashboard option.
The card renders inside `ha-card` and uses Home Assistant theme variables, so it follows light, dark, and custom themes.
Heating and cooling colors follow the theme's climate state colors.
Heating, cooling, idle, and attention colors are derived from the real Plant snapshot and do not change controller behavior.
The layout uses logical CSS properties, so it mirrors in right-to-left languages, including the direction of the flow animation.
Active, requested, waiting, and overrun delivery paths animate in the flow direction.
Idle, blocked, and unavailable paths remain still so motion never implies flow that the controller did not report.
Interactive controls have visible focus indicators, accessible names, disabled states, and touch-friendly minimum sizes.
Headings start at level two inside the card, and grouped diagnostics are exposed as lists.
Safe shutdown accepts pointer or keyboard hold input and shows hold progress.
The hold is cancelled when the pointer is released early, leaves the button, is cancelled by the browser, or loses capture, and when the button loses focus.
The card disables ambient, flow, loading, and state animations when the operating system requests reduced motion.

### Theme variables

The card works without custom theme values, but a dashboard theme can tune it through inherited CSS variables.

```css
--hydronicus-glass-blur: 24px;
--hydronicus-glass-opacity: 68%;
--hydronicus-heating-color: var(--state-climate-heat-color);
--hydronicus-cooling-color: var(--state-climate-cool-color);
--hydronicus-idle-color: var(--primary-color);
--hydronicus-attention-color: var(--error-color);
--hydronicus-flow-duration: 2.2s;
--hydronicus-ambient-duration: 16s;
```

The card surface is opaque by default.
Set a glass opacity below 100% and a glass blur to let the dashboard background show through.
Keep enough contrast between the card surface and text to preserve readability in both light and dark themes.

## Synthetic staging checks

Use the repository's disposable or synthetic Home Assistant staging workflow before connecting a Plant to real equipment.
Confirm that two Plants remain isolated, permission-filtered users see only their allowed Rooms and Hydronicus-owned controls, and reload or unload produces a clean subscription state.
Keep the Plant in Dry run while validating presentation, routing, alerts, and proposed operation outcomes.
Do not interpret a passing card render or a Dry run snapshot as proof of hydraulic, electrical, or equipment safety.
