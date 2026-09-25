# Hydronicus Lovelace cards

Hydronicus bundles two TypeScript custom cards.
The Hydronicus Plant card is the complete view of one configured Plant.
The Hydronicus Zone card shows one Zone of a Plant, so a dashboard can place Zones in its own layout.
Both present the Plant state and the controller's structured explanations without exposing configured sensor, valve, pump, source-demand, or private URL bindings.

## Loading the cards

Hydronicus loads both cards automatically, from one bundle.
Restart Home Assistant after installing or upgrading Hydronicus, then reload the browser page.
No dashboard resource is needed, and the bundle must not be copied into `/config/www`.

The integration serves the bundle from the installed package at a URL that contains the integration version, such as `/hydronicus/0.1.0/hydronicus-plant-card.js`, and registers it as a frontend module.
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
The picker shows the Plant card's description rather than a preview, because a whole Plant is taller than the picker's rows.
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
The editor does not hardcode Zones, Loops, valves, pumps, sources, or household entity IDs.

### Show part of a Plant

The optional `sections` list chooses which parts of the Plant card to show, in the order listed.
Without `sections`, the card shows every section in its default order, exactly as before.

| Section | Shows |
| --- | --- |
| `header` | The Plant name, status, mode control, safe shutdown, and the execution boundary |
| `alerts` | The priority-ordered alerts |
| `zones` | The Zone tiles |
| `paths` | The Hydraulic Flow section, one route per Zone and Loop |
| `equipment` | Each valve and pump with the Loops that use it |
| `explanations` | The controller explanations |
| `operations` | The latest operation outcomes |

```yaml
type: custom:hydronicus-plant-card
plant: 00000000-0000-4000-8000-000000000001
sections:
  - header
  - alerts
```

A section name that is unknown or listed twice is a configuration error.
An empty list shows every section, which is what the visual editor stores when every choice is cleared.
The visual editor offers the sections as an ordered multiple choice.
A notice about a lost connection and an error from a failed action are always shown, above the first section when the header is not shown.

## Add a Zone card

Pick **Hydronicus Zone** from the card picker.
The picker prefills the first Plant you can read and its first visible Zone.
The visual editor lists the Plants you can read by name, and then the Zones of the chosen Plant by name.
Choosing another Plant clears the Zone, because a Zone belongs to one Plant.
The equivalent YAML is:

```yaml
type: custom:hydronicus-zone-card
plant: 00000000-0000-4000-8000-000000000001
zone: 00000000-0000-4000-8000-00000000000a
density: comfortable
```

`zone` is the id of the Zone in the Plant snapshot, which the editor fills in for you.
`density` is optional and takes the same values as on the Plant card.

The Zone card shows the same Zone tile as the Plant card, with the same HVAC mode, target, preset, and more-info controls and the same read-only rules for external thermostats.
It shows the same loading, unavailable, not found, no access, and reconnecting states as the Plant card.
When the Plant snapshot has no Zone with that id, the card shows Zone not found.
The snapshot leaves out Zones you may not read, so a Zone you have no access to also shows Zone not found.

## Build a dashboard from pieces

Every Hydronicus card on a page that shows the same Plant shares one subscription, so a dashboard can use as many pieces as it needs.
This Sections view shows the Plant header and alerts, a Zone card per Zone, and the hydraulic detail below them:

```yaml
type: sections
sections:
  - type: grid
    cards:
      - type: custom:hydronicus-plant-card
        plant: 00000000-0000-4000-8000-000000000001
        sections: [header, alerts]
      - type: custom:hydronicus-zone-card
        plant: 00000000-0000-4000-8000-000000000001
        zone: 00000000-0000-4000-8000-00000000000a
      - type: custom:hydronicus-zone-card
        plant: 00000000-0000-4000-8000-000000000001
        zone: 00000000-0000-4000-8000-00000000000b
  - type: grid
    cards:
      - type: custom:hydronicus-plant-card
        plant: 00000000-0000-4000-8000-000000000001
        sections: [paths, equipment, operations]
```

## Card contract

The cards subscribe to `hydronicus/subscribe_plant` and validate the versioned presentation schema before rendering.
The integration sends one initial snapshot and subsequent meaningful snapshots after runtime state, diagnostics, or operation outcomes change.
A dashboard can show multiple configured Plants through separate card instances without mixing their snapshots.

All Hydronicus cards on a page share one subscription per Home Assistant connection and Plant, and the subscription ends when the last of them leaves the page.
A card that the dashboard moves within the page keeps the shared subscription.
The connection states below apply to every card that shares the subscription.
A stream for a Plant whose config entry exists but is not loaded yet, for example while Home Assistant starts or reloads the Plant, is accepted.
It reports the Plant as unavailable and starts sending snapshots once the Plant finishes loading.
While a Plant is unloaded or reloading, the card shows it as unavailable and hides its controls.
After a lost connection, the card keeps the last snapshot with a notice and subscribes again when Home Assistant is reachable.
A transient subscription failure is retried with exponential backoff, from one second up to one minute.
A Plant that no longer exists and a Plant the user may not read are terminal states with a clear message; the card does not retry them.
When the backend revokes access to a stream, it sends an `unauthorized` status event before it ends the stream.
When a Plant is deleted, its streams end with a `plant_not_found` status event.

The card says Loop where the snapshot and the core code say Circuit.
The header shows the Plant name, operational status, requested mode, and execution boundary.
It adds the active mode only when an explicit requested mode is not active yet, for example during a changeover.
It shows the active and recommended source only when the Plant has sources.
The Zones section shows thermostat ownership, the HVAC mode, current and target temperatures when available, presets for Hydronicus thermostats, heating or cooling demand, sensor qualification, cooling diagnostics, blocked reasons, and coupling notices.
A Zone whose thermostat is off shows Off instead of an idle phase.
The Hydraulic Flow section renders the ordered Zone to Loop to Valve to Pump to Source route.
The Equipment section shows each valve and pump with the Loops that currently use it.
The alert and explanation sections surface stable priority-ordered diagnostics and controller reasoning.
The operation section distinguishes proposed, executed, suppressed, failed, and timed-out outcomes.

The presentation schema is version 2.
Each thermostat in the snapshot carries its `hvac_mode`, and a Hydronicus thermostat also carries `hvac_modes`, the modes its climate entity supports.
Every temperature in the snapshot is in degrees Celsius.
The card shows temperatures in the unit system of the Home Assistant instance, and formats numbers with the number format from the user's profile.
Target changes are sent in that unit system, which Home Assistant converts for the climate entity.
The plus and minus buttons step by 0.5 °C, or by 1 °F under US customary units.

Hydronicus thermostat Zones receive a permission-filtered Hydronicus climate entity and expose HVAC mode, target, and preset controls.
The HVAC mode control offers exactly the modes of the Zone's climate entity: Off and Heat, plus Cool and Heat/Cool when the Zone reaches a cooling-enabled Loop.
It calls `climate.set_hvac_mode` on that climate entity.

External thermostat Zones are explicitly read-only.

The card displays their HVAC mode and diagnostic target and current temperature values when available, but never renders HVAC mode, target, or preset controls for them.

The card never calls the external climate entity.

The backend uses each Zone's Hydronicus-owned demand entity for visibility filtering.

A user without read access to that entity receives none of the Zone's name, observations, demand, routes, alerts, or explanations.
Source summaries and source-selection operations remain Plant-wide because sources serve the shared hydraulic system.
Any user allowed to discover the Plant can see that source state, while configured physical source entity IDs remain redacted.
The Plant mode control calls only the Hydronicus-owned mode select entity.
Safe shutdown is a hold-to-confirm action and calls only the Hydronicus-owned shutdown button entity.
Configured physical entity IDs do not cross the presentation boundary and are never rendered as card action targets.

The configured external thermostat entity ID is also redacted from the presentation stream.

Selecting the Plant name opens the more-info dialog of the Hydronicus mode select entity.
Selecting a Hydronicus thermostat Zone name opens the more-info dialog of its Hydronicus climate entity.

When an action such as a mode or target change fails, the card keeps showing the Plant, returns the control to its real value, and shows the error inline until you dismiss it or the next action succeeds.

The Plant card displays the execution boundary prominently in its header section.
The Zone card and a Plant card without the `header` section do not show it, so keep a Plant card with its header on any dashboard that uses them.
The badge reads Dry run while nothing executes, Mixed while heating and cooling may execute but source selection stays shadow-only, and Live when every output may execute.
Cooling outputs follow the Plant's Dry run setting like heating outputs, so the card treats a cooling demand like a heating demand and does not describe cooling as shadow-only.
While Dry run is on, the safe shutdown button stays available with a quieter style.
It does not provide a Dry run toggle.
The existing Plant configuration and its safety gates remain the authority for whether actuator operations are proposed or executed.

## Frontend data

Each card reads the Home Assistant connection, the action API, the unit system, and the locale from the frontend context groups that Home Assistant documents for custom cards.
When a context is not provided, it falls back to the `hass` object that Home Assistant also sets on every card.
It stores only the values it uses, so state changes of unrelated entities do not re-render the card.

## Layout and accessibility

In the Sections view the Plant card spans the full section width by default, at least six columns, and its height follows its content, so it never overlaps the cards below it.
A Plant card that shows none of the `zones`, `paths`, and `equipment` sections spans half a section by default, at least four columns.
A Zone card spans half a section by default, like a thermostat card, at least four columns, and its height follows its content.
In the masonry view the Plant card reports a height estimate based on the Zones, paths, equipment, alerts, and operations it shows.
The card uses a responsive Zone grid, horizontally scrollable hydraulic paths, and controls that collapse for narrow layouts.
A hydraulic path is a compact chain from the start of its row, with short connectors at any card width.
Each path takes the heating or cooling color of its own Zone's demand.
The `comfortable` and `compact` density values provide a readable default and a denser dashboard option.
Each card renders inside `ha-card` and uses Home Assistant theme variables, so it follows light, dark, and custom themes.
Heating and cooling colors follow the theme's climate state colors.
Text in a state color, such as the Dry run badge or a warning, is mixed toward the text color so small labels keep enough contrast.
Heating, cooling, idle, and attention colors are derived from the real Plant snapshot and do not change controller behavior.
The layout uses logical CSS properties, so it mirrors in right-to-left languages, including the direction of the flow animation.
Active, requested, waiting, and overrun delivery paths animate in the flow direction.
Idle, blocked, and unavailable paths remain still so motion never implies flow that the controller did not report.
Interactive controls have visible focus indicators, accessible names, disabled states, and touch-friendly minimum sizes.
Headings start at level two inside each card, and grouped diagnostics are exposed as lists.
The Zone name is the level two heading of a Zone card, and a level four heading below the Zones heading inside the Plant card.
Safe shutdown accepts pointer or keyboard hold input and shows hold progress.
The hold is cancelled when the pointer is released early, leaves the button, is cancelled by the browser, or loses capture, and when the button loses focus.
The card disables ambient, flow, loading, and state animations when the operating system requests reduced motion.

## Theming

Without a theme, both cards look like stock Home Assistant cards.
They use the frame, radius, border, shadow, surface, font, and colors of the active Home Assistant theme, with a flat surface and no decorative glow.
The Plant mark, the status dot, and the flow animation stay, because they show the Plant and path state.
Like stock cards, they appear without an entrance animation.

A Home Assistant theme restyles the cards through theme keys, so no `card_mod` is needed for colors, shapes, fonts, and frames.

### How a theme reaches the cards

Home Assistant turns every theme key into a CSS variable on the page, so the key `hydronicus-radius` becomes `--hydronicus-radius`.
Write each key without the leading dashes:

```yaml
frontend:
  themes:
    My theme:
      hydronicus-radius: "20px"
      hydronicus-accent: "#7b3fa0"
```

A variable set on the page, on a view, or on any element around a card reaches the card, because the card only reads the public `--hydronicus-*` variables and never declares them.
Inside the card, each public variable is resolved once into a private `--_hy-*` property, which is internal and may change without notice.
A variable that no theme sets falls back to the Home Assistant variable in the table below, and then to a fixed value, so a theme only needs the keys it wants to change.
A shorthand token such as `hydronicus-card-border` takes a whole CSS `border` value, such as `2px solid #222`.

### Theme tokens

| Token | Role | Fallback |
| --- | --- | --- |
| `--hydronicus-surface` | Card background | `--ha-card-background`, then `--card-background-color`, then `#fff` |
| `--hydronicus-surface-raised` | Zone tiles, paths, equipment, controls, and notices | The text color at 4% over transparent |
| `--hydronicus-text` | Primary text | `--primary-text-color`, then `#1c1c1c` |
| `--hydronicus-text-muted` | Secondary text and labels | `--secondary-text-color`, then `#5f6368` |
| `--hydronicus-line` | Hairlines, and the default tile and control borders | `--divider-color`, then the text color at 13% |
| `--hydronicus-accent` | Focus ring, selected segment, and link hover | `--primary-color`, then `#03a9f4` |
| `--hydronicus-heating-color` | Heating state | `--state-climate-heat-color`, then `#ff8100` |
| `--hydronicus-cooling-color` | Cooling state | `--state-climate-cool-color`, then `#2b9af9` |
| `--hydronicus-idle-color` | Idle state | `--primary-color`, then `#03a9f4` |
| `--hydronicus-attention-color` | Attention state | `--error-color`, then `#db4437` |
| `--hydronicus-success-color` | Executed and ready states | `--success-color`, then `#43a047` |
| `--hydronicus-warning-color` | Dry run, proposed operations, and warnings | `--warning-color`, then `#ffa600` |
| `--hydronicus-danger-color` | Blocked, failed, and safe shutdown | `--error-color`, then `#db4437` |
| `--hydronicus-radius` | The card's own corner | `--ha-card-border-radius`, then `--ha-border-radius-lg`, then `12px` |
| `--hydronicus-radius-inner` | Zone tiles, paths, metrics, and notices | `--ha-border-radius-md`, then `8px` |
| `--hydronicus-radius-control` | Buttons, selects, and the segmented HVAC mode control | `--hydronicus-radius-inner` |
| `--hydronicus-card-border` | The card's border shorthand | `var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0))`, as `ha-card` draws it |
| `--hydronicus-card-shadow` | The card's shadow | `--ha-card-box-shadow`, then `none` |
| `--hydronicus-tile-border` | Border shorthand of Zone tiles, paths, equipment, and the explanation and operation panels | `1px solid` in the line color |
| `--hydronicus-tile-shadow` | Shadow of the same tiles | `none` |
| `--hydronicus-tile-active-border` | Border shorthand of a Zone tile with demand and of a flowing path | Zone tile: `1px solid` in the Zone's state color mixed with the line color; path: `--hydronicus-tile-border` |
| `--hydronicus-tile-active-shadow` | Shadow of a Zone tile with demand and of a flowing path | `--hydronicus-tile-shadow` |
| `--hydronicus-control-border` | Border shorthand of buttons, selects, and the segmented control | `1px solid` in the line color |
| `--hydronicus-control-shadow` | Shadow of the same controls | `none` |
| `--hydronicus-control-surface` | Fill of the same controls | `--hydronicus-surface-raised` |
| `--hydronicus-control-color` | Label color of buttons and selects | `--hydronicus-text` |
| `--hydronicus-selected-background` | Fill of the selected HVAC mode segment and any pressed control | Heat and Cool: their state color at 16%; Off: `--hydronicus-surface-raised`; other modes: the accent at 14% |
| `--hydronicus-selected-color` | Label color of the selected segment | `--hydronicus-text` |
| `--hydronicus-font-body` | Body text | `--ha-font-family-body`, then the inherited font |
| `--hydronicus-font-display` | The Plant title, Zone titles, and section titles | `--hydronicus-font-body` |
| `--hydronicus-font-weight-display` | Weight of the display text | `--ha-font-weight-medium`, then `500` |
| `--hydronicus-ambient-opacity` | Opacity of the ambient state glow behind the card | `0`, so the glow is off |
| `--hydronicus-glass-blur` | Blur of the dashboard behind the card, added to `--ha-card-backdrop-filter` | `0px` |
| `--hydronicus-glass-opacity` | Opacity of the card surface | `100%` |
| `--hydronicus-flow-duration` | Period of the flow animation | `2.2s` |
| `--hydronicus-ambient-duration` | Period of the ambient glow animation | `16s` |

The active tile border is a separate shorthand, so a theme that changes the width of `hydronicus-tile-border` should also set `hydronicus-tile-active-border`.
Set a glass opacity below 100% and a glass blur to let the dashboard background show through, and keep enough contrast between the surface and the text in both light and dark themes.

### Parts

For what the tokens do not reach, the cards expose CSS parts, which a theme's `card-mod-theme` or a dashboard's `card_mod` can style with `::part()`.
Both cards expose the same parts from the same templates, and a Zone card's tile has exactly the parts of the Zone inside the Plant card.
The parts are public and stable; any other element inside a card is internal.

| Part | Element |
| --- | --- |
| `card` | The `ha-card` frame of every card, including loading and message cards |
| `header` | The Plant header |
| `mark` | The animated Plant status mark |
| `eyebrow` | The small label above a card title |
| `title` | The Plant name, or the title of a message card |
| `status` | The Plant status line |
| `controls` | A group of controls: the Plant header controls, or a Zone's target and preset controls |
| `control` | A button, a select, the Plant mode control, or the segmented HVAC mode control as a whole |
| `segment` | One HVAC mode button inside the segmented control |
| `badge` | A pill label: the execution boundary badge, a Zone phase, or a path or equipment state |
| `chip` | A Zone diagnostic or a Loop that uses equipment |
| `notice` | An alert, a connection notice, a failed action, or a message card's message |
| `boundary` | The execution boundary strip |
| `section` | One Plant card section |
| `section-title` | The heading of a section |
| `zone` | A Zone tile |
| `zone-title` | A Zone name |
| `metric` | A current or target temperature |
| `path` | A hydraulic path |
| `node` | One step of a hydraulic path |
| `equipment` | A valve or pump |
| `disclosure` | The expandable controller explanation and operation panels |

For example, this `card_mod` hides the Plant mark and the eyebrow label:

```yaml
card_mod:
  style: |
    :host::part(mark), :host::part(eyebrow) { display: none; }
```

### Example theme

This theme gives the cards rounder corners, a serif display font, and flat outlined tiles with a hard drop shadow:

```yaml
frontend:
  themes:
    Outlined:
      hydronicus-radius: "24px"
      hydronicus-radius-inner: "14px"
      hydronicus-font-display: "Georgia, serif"
      hydronicus-font-weight-display: "700"
      hydronicus-card-border: "2px solid #2a2118"
      hydronicus-card-shadow: "4px 4px 0 #2a2118"
      hydronicus-tile-border: "2px solid #2a2118"
      hydronicus-tile-active-border: "2px solid var(--hydronicus-heating-color, #d9480f)"
      hydronicus-control-border: "2px solid #2a2118"
      hydronicus-control-shadow: "2px 2px 0 #2a2118"
      hydronicus-ambient-opacity: "0.6"
```

### Color configuration

The cards have no color options in their configuration, because every color is drawn by CSS and a theme token already reaches it.
The cards paint no canvas and no inline SVG, so they need no JavaScript color resolver for Home Assistant color names or hex values.

## Synthetic staging checks

Use the repository's disposable or synthetic Home Assistant staging workflow before connecting a Plant to real equipment.
Confirm that two Plants remain isolated, permission-filtered users see only their allowed Zones and Hydronicus-owned controls, and reload or unload produces a clean subscription state.
Keep the Plant in Dry run while validating presentation, routing, alerts, and proposed operation outcomes.
Do not interpret a passing card render or a Dry run snapshot as proof of hydraulic, electrical, or equipment safety.
