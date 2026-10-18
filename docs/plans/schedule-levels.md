# Schedule levels and dashboard-editable comfort schedules

Status: implemented on branch `schedule-levels` on 2026-10-18 as version 0.6.0; not yet committed, released, or installed.
Owner decisions on 2026-10-18: Home Assistant's `schedule` helper stays the one schedule model, Hydronicus does not store a schedule of its own, and a block may choose its level by preset or by target.
The setback becomes a per-zone number entity.

## Why

A digital thermostat already follows a `schedule` helper: on periods hold the manual comfort target, off periods subtract `heat_setback` or add `cool_setback`, and early start warms ahead within `max_early_start`.
That gives two levels a day and keeps the setback in the options flow, where a dashboard cannot reach it.
A dashboard also has no way to find which helper a zone follows, so every card would have to be told the helper ID separately.

## Why the helper stays the model

Checked against Home Assistant 2026.9.3 (installed core) and the 2026.10 changelog:
- The `schedule` helper stores weekly blocks, and each block may carry a `data` mapping exposed as entity attributes while that block is active.
- `schedule.get_schedule` returns each day's blocks with their `data` (`Schedule.get_schedule` returns the stored day lists unchanged) and is not admin-only; there is no action that writes them.
- Writing is the admin-only `schedule/update` websocket command, which replaces the item's whole stored config.
- Schedule triggers and conditions (`block_started`, `block_ended`, `is_on`, `is_off`) let automations follow the same helper.
- Integrations cannot provide `schedule` entities of their own; that request is an open community thread with no implementation.

Following the helper keeps one source of truth that Home Assistant's own editor, automations and any dashboard all share.
The cost is that only administrators can change hours from a dashboard, which is a Home Assistant limitation rather than a Hydronicus one.
A Hydronicus-owned schedule with its own set and get actions was rejected: it would let non-admins edit, but it duplicates the helper and splits the household's schedules in two.
If Home Assistant later adds a non-admin write action or a schedule entity platform, Hydronicus inherits it without a model change.

## Design

### Block levels

A block's `data` may name the level for its period with exactly one of:
- `preset`: `comfort`, `eco` or `away`, resolved with `presets_for(mode)` so heating and cooling keep their own preset targets.
- `heat_target` and/or `cool_target`: explicit temperatures; the key for the current mode applies.

A block with no level keeps today's behaviour, the manual comfort target.
A block whose level does not apply in the current mode (a `cool_target`-only block while heating, or a preset the mode does not define) also uses the manual comfort target and says so in `reason`.
A block that names both a preset and a target, an unknown preset, or a non-numeric or out-of-range target is invalid: the period uses the manual comfort target, `schedule_status` reports `invalid_block`, and a Repair names the helper and the offending block.
Off periods keep the setback, now read from the number entity below.
Nothing a block says can change the Plant mode or bypass windows, arming, guards, minimum times or hydraulic sequencing.

### Early start towards the next block's level

Early start today aims at the manual target.
With levels, it aims at the level of the block that starts at `next_event`.
The active block's `data` is visible as attributes, but the next block's is not, so the runtime reads the week with `schedule.get_schedule` when the helper's state or configuration changes and keeps it on the observation for the next block.
If that read fails, early start falls back to the manual target, which can only start earlier, never later, than a lower level would.
Early start is never planned towards a block whose level is lower than the current effective target.

### Setback as a number entity

Each digital thermostat with a schedule gets `number.<zone>_heat_setback` and, when the zone can cool, `number.<zone>_cool_setback`, in K and restored across restarts.
They keep the existing separation of heating and cooling, and the plant file's `heat_setback` and `cool_setback` remain as their initial values for a new zone or an imported Plant.
`max_early_start`, `heating_rate` and `cooling_rate` stay in the options flow as installation tuning.

### What a dashboard reads and writes

The climate gains attributes so a card needs only the climate entity:
- `schedule_entity`: the helper the zone follows, or absent when none is configured.
- `schedule_level`: the active block's resolved level (`comfort`, `eco`, `away`, or `target`), alongside the existing `schedule_status`, `planned_target` and `effective_target`.
- `schedule_next_change`: the helper's `next_event`, so a card can show the next change without reading the helper.

The documented edit path for a card is: read the helper's blocks with `schedule.get_schedule`, write them with `schedule/update` keeping the item's name and icon, and change the setback through the number entity.
`docs/` gets a "Dashboards" section with that contract and an example of block `data`.

## Work

1. Core: `ScheduleState` carries the active block's level and the next block's level; `comfort_target` resolves levels as above; the plant file's setbacks become the number entities' initial values.
2. Adapter: `observe.schedule_state` reads block `data`; the runtime fetches the week with `schedule.get_schedule` on helper changes; `number` platform gains the setback; climate attributes added; Repairs for invalid blocks.
3. Flows: the schedule section's setbacks are labelled as starting values; `strings.json` and `translations/en.json` updated byte for byte.
4. Tests: core unit tests for every level case and the invalid-block fallbacks; integration tests with a real `schedule` helper carrying block `data`, including a failed `get_schedule`; simulator traces that change the helper mid-period and confirm invariants hold.
5. Docs: `configuration.md`, `how-it-works.md#comfort-schedules`, `entities.md`, the comfort example, and a release note.
6. `make verify`, then release.

## Decisions made while implementing

- `away` is allowed as a block level; it is only a preset's target, and the household-wide away state stays the owner's preset choice.
- The invalid-block Repair is computed from the whole week on every evaluation, so it appears before the block runs and clears on the first evaluation after the edit.
- Early start applies to any rise towards the next period, block to block as well as setback to block, and never towards a lower or unknown period.
- An edit that changes neither the helper's state nor its attributes reaches Hydronicus as a state report, which also triggers a fresh read of the week.
- Setbacks are capped at 10 K everywhere, and are stored with the runtime's persisted state rather than restored by the number entities, so the first evaluation after a restart already uses them.
