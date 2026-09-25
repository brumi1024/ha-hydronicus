# Home Assistant 2026.9 modernization plan

This plan fixes every finding from the 2026-09-24 audit of Hydronicus against current Home Assistant.
It is the single source of truth for decisions, invariants, workstreams, and acceptance criteria.
The audit baseline is commit `4d83f22` (`0.1.0-rc.6`), tested against Home Assistant 2026.8.2 and 2026.9.3.

## Decisions

- The minimum supported Home Assistant version becomes `2026.9.0`.
- The test harness moves to `pytest-homeassistant-custom-component==0.13.366`, which pins Home Assistant `2026.9.3`.
- End-to-end checks run on a local disposable Home Assistant `2026.9.3` instance, as described in Wave 3.
- All work lands on one feature branch, `ha-2026-9-modernization`, with one commit per workstream, followed by a pull request against `main`.
- Existing installations keep their unique IDs, entity IDs, raw entity state values, config-entry schema version `2.0`, and card YAML (`plant: <uuid>`).
- Display-only changes are allowed: translated names and states, icons, device classes, entity categories, and recorder attribute exclusions.
- Temperature contract: `core/`, the runtime state, diagnostics, and the presentation snapshot carry degrees Celsius only.
- Conversion happens once, at the Home Assistant boundary in `runtime.py`, when an observation is read.
- The card converts Celsius snapshot values to the user's unit system for display.

### Observation unit policy

- A temperature observation with unit `°C`, `°F`, or `K` is converted to Celsius with `homeassistant.util.unit_conversion.TemperatureConverter`.
- A temperature observation without a unit is accepted as Celsius, preserving current behaviour, and the unit assumption is documented.
- A temperature observation with any other unit is unusable, and it takes the existing invalid-observation path, so the controller fails closed.
- A humidity observation with unit `%` or no unit is accepted, and any other unit makes it unusable.

### Out of scope

These items are recorded as pull request follow-ups rather than implemented:

- Replacing prose explanation and blocked-reason sensor states with translatable reason codes, which needs a controller contract change.
- `logo.png` and `dark_*` brand images, which need real artwork; Home Assistant falls back to `icon.png` meanwhile.
- Integration trigger and condition platforms and Labs preview features, because Home Assistant documents those APIs as unstable for integrations.
- Chaining the initial config flow into subentry flows with `async_on_create_entry`, which is a setup-flow redesign.
- Version bumps and `RELEASE_NOTES.md`, which belong to the release step.

## Invariants

Every workstream preserves these, and every review checks them:

- Dry run issues zero actuator service calls.
- Reload, unload, removal, and Home Assistant stop remain command-free lifecycle boundaries.
- Output authorization semantics and the migration path from version 1.1 are unchanged.
- `custom_components/hydronicus/core/` stays free of Home Assistant imports and keeps at least 90 percent coverage.
- `make verify` is the gate; it already runs lint, frontend checks, release checks, public beta checks, formatting, type checking, and tests.

## Working rules

- A bug fix starts **red**: first a test, or an end-to-end reproduction, that fails on the bug, then the fix that turns it **green**.
- Feature gaps get tests that pin the new behaviour.
- Each agent edits only its **owned files**.
- A needed change outside the owned files is reported as a **contract request** to the lead instead of being made.
- `custom_components/hydronicus/translations/en.json` stays byte-identical to `strings.json`; after editing `strings.json`, copy it over.
- Each agent edits only its owned top-level sections of `strings.json`.
- The committed card bundle `custom_components/hydronicus/frontend/hydronicus-plant-card.js` is rebuilt with `npm --prefix frontend run build` whenever `frontend/src` changes.
- Prose uses plain dashes, never em dashes.
- Long Markdown files put each full sentence on its own physical line.
- Commit messages use the repository's conventional prefixes (`fix:`, `feat:`, `test:`, `docs:`, `ci:`, `refactor:`) and carry no agent attribution or co-author lines.
- `CHANGELOG.md` files and files marked as generated are never edited by hand.
- Quality, simplicity, robustness, and long-term maintainability outweigh short-term effort.
- Lint failures, test failures, and flaky tests are fixed or explicitly reported, even when unrelated to the workstream.
- The large synthetic benchmark can be timing-sensitive under parallel load; rerun it alone before calling it a failure, and report any flakiness.

## Wave 0 - baseline (lead)

1. Create the branch `ha-2026-9-modernization` from `main` and commit this plan as `docs: add Home Assistant 2026.9 modernization plan`.
2. Pin `pytest-homeassistant-custom-component==0.13.366` in `pyproject.toml`, run `uv lock`, then `make bootstrap`.
3. Replace the `voluptuous_serialize` imports in `tests/integration/test_config_flow.py:5` and `tests/integration/test_source_subentry.py:5` with `probatio.to_field_list`, which Home Assistant 2026.9 itself uses with `cv.custom_serializer` in `homeassistant/helpers/data_entry_flow.py`.
4. Replace `registry.async_get_device(...)` in `tests/integration/test_init.py:189` with the identifier lookup that the installed device registry recommends, checking its signature in the installed package.
5. Set `hacs.json` `homeassistant` to `2026.9.0` and update the minimum version sentence in `README.md:70`.
6. Leave historical staging records that mention 2026.8.2 unchanged.

Wave 0 is done when `make verify` is green on Home Assistant 2026.9.3 and the result is committed as `test: move the test harness to Home Assistant 2026.9.3`.

## Wave 1 - parallel workstreams

Five agents run at once, each in its own git worktree based on the Wave 0 commit.
Each agent runs `make bootstrap` in its worktree, and W5 also runs `npm ci --prefix frontend`.

### W1 Runtime boundary

Owned files: `runtime.py`, `__init__.py`, the `exceptions` section of `strings.json`, `docs/configuration.md`, `docs/troubleshooting.md`, and the tests covering them.

Tasks:

- **B1**: implement the observation unit policy for zone temperature sensors, source availability and temperature inputs, supply and surface temperature sensors, and humidity sensors.
- **B1**: convert external climate `current_temperature` and `temperature` attributes to Celsius before they reach the runtime or presentation.
- **B1**: prove it red then green with an integration test in which a `64.4 °F` zone sensor yields 18 °C and heating demand against a 21 °C target, plus a test for the fail-closed unit path.
- **B1**: add a property test when conversion touches a safety invariant across topologies.
- **X2**: raise `ServiceValidationError` for invalid operator input and `HomeAssistantError` for runtime failures, each with `translation_domain`, `translation_key`, and placeholders.
- **X2**: raise `ConfigEntryError` with a translation key when a stored graph cannot be decoded or compiled during setup.
- **X3**: remove the lightweight test-seam fallbacks in `runtime.py` (the `EVENT_HOMEASSISTANT_STOP` import fallback, the `eager_start` `TypeError` fallback, and the `hasattr(hass, "bus")` probe), updating the tests that relied on them.
- **X3**: stop clearing `runtime_data` after a successful unload in `__init__.py`, because Home Assistant does that itself, while keeping the cleanup after a failed setup.
- Document the unit policy in `docs/configuration.md` and the fail-closed unit case in `docs/troubleshooting.md`.

Done when every task is green, `make verify` passes, and each `exceptions` key used in code exists in `strings.json`.

### W2 Entities

Owned files: `sensor.py`, `binary_sensor.py`, `select.py`, `button.py`, `climate.py`, `entity_device.py`, a new `icons.json`, the `entity` section of `strings.json`, and the tests covering them.

Tasks:

- **B2**: give the zone condensation margin sensor `SensorDeviceClass.TEMPERATURE_DELTA`; prove it red then green with a US customary test expecting 7.47 °F for a 4.15 °C margin.
- **B2**: check how the recorder treats the unit-class change for existing long-term statistics, and document the result for the pull request.
- **B3**: add `ClimateEntityFeature.TURN_ON | TURN_OFF`, and implement `async_turn_on` so it restores the zone's last non-off HVAC mode, defaulting to heat.
- **B3**: prove it red then green through the `climate.turn_off`, `climate.turn_on`, and `climate.toggle` actions; the base class would otherwise pick `heat_cool` on cooling-capable zones.
- **E1**: replace every hard-coded `_attr_name` with `translation_key` and matching `entity` strings, keeping the English names identical so newly generated entity IDs do not change.
- **E2**: move every `_attr_icon` into `icons.json`, adding state-based icons where the state carries meaning.
- **E3**: make the bounded status sensors `SensorDeviceClass.ENUM` with `options` and translated states: operating mode, controller status, reconciliation status, and source changeover.
- **E3**: translate the requested-mode select options.
- **E4**: assign binary sensor device classes and entity categories, such as `PROBLEM` for blocked and mismatch sensors and `RUNNING` for source active.
- **E4**: give the source dwell sensor `SensorDeviceClass.DURATION` with `UnitOfTime.SECONDS`; report the final per-entity table.
- **E5**: declare `_unrecorded_attributes` for volatile attributes such as operations, reasons, explanations, logic summaries, warnings, and interlocks.
- **E6**: use `AddConfigEntryEntitiesCallback` in every platform, set `PARALLEL_UPDATES = 0`, and import `DeviceInfo` from `homeassistant.helpers.device_registry` and `EntityCategory` from `homeassistant.const`.
- **E7**: expose `current_humidity` on zone climate entities that have humidity sensors, reading existing runtime accessors; any new runtime accessor is a contract request to W1.
- Remove the unreachable `ValueError` in `climate.py:178`, because the climate base class already validates HVAC modes with translated errors.

Done when every task is green, `make verify` passes, and no platform module contains `_attr_name =` or `_attr_icon =`.

### W3 Config flows

Owned files: `config_flow.py`, the `config`, `config_subentries`, and `selector` sections of `strings.json`, a new `tests/integration/test_translations.py`, and the flow tests.

Tasks:

- **B4**: add the missing strings listed in the finding register.
- **B4**: add `tests/integration/test_translations.py`, a translation contract test that fails when any error key, abort reason, `translation_key`, enum state, selector option, exception key, or issue key used in code is missing from `strings.json`, or when `en.json` differs from `strings.json`.
- **F2**: add `data_description` for every field of every config and subentry step.
- **F3**: replace `vol.Coerce(float)` and `vol.Range` fields with `NumberSelector`, using units, steps, bounds, and box mode, following the `generic_thermostat` pattern; replace plain `str` name fields with `TextSelector`.
- **F3**: persisted values keep their existing types and units.
- **F4**: group optional actuator feedback fields and cooling fields into collapsible `section()` blocks without changing the persisted data shape.
- **F5**: filter temperature and humidity entity selectors by device class, following `generic_thermostat`; verify that reconfigure forms still show a previously chosen entity that lacks the device class, and drop the filter for a field where they do not.
- **F6**: move hard-coded English option labels to `SelectSelectorConfig(translation_key=...)` with `selector` strings.
- **F8**: annotate parent flow steps with `ConfigFlowResult`.

Done when every task is green, `make verify` passes, and the translation contract test passes against every other section as it exists on the branch.

### W4 Repairs

Owned files: `repairs.py`, the `issues` section of `strings.json`, and `tests/integration/test_repairs.py`.

Tasks:

- **R1**: make unresolved-binding issues fixable when the affected object is owned by a config subentry.
- **R1**: add the repairs platform `async_create_fix_flow`, returning a flow that starts that subentry's reconfigure flow and hands off with `next_flow`, which Home Assistant 2026.9 supports.
- **R1**: keep issues for parent-owned objects non-fixable, with an actionable description.
- **R1**: keep the `async_sync_repairs` signature stable, and derive subentry ownership from `entry.runtime_data`; changing the call site in `runtime.py` is a contract request to W1.
- **X3**: remove the `hasattr(hass, "bus")` probe and the `ImportError` fallback in `repairs.py`.

Done when every task is green, `make verify` passes, and a test proves the fix flow opens the owning subentry's reconfigure flow and that the issue clears after a valid binding is restored.

### W5 Card

Owned files: `frontend/**`, `custom_components/hydronicus/frontend/**`, `frontend.py`, `websocket.py`, `presentation.py`, `manifest.json`, `docs/lovelace.md`, `.github/workflows/ci.yml`, and the tests covering them.

Before fixing each card bug, reproduce it red.
Use a browser harness when browser tools are available, and an element-level test in any case.

Tasks:

- **B5**: make every reactive field a real Lit reactive property, in the card and the editor.
- **C18**: add a DOM test environment for element-level tests and the `lit/no-classfield-shadowing` lint rule, so this bug class stays caught.
- **C2**: remove fixed `rows` from `getGridOptions`, and choose column defaults that fit the layout in the sections view.
- **C3**: bind select values so each dropdown shows its real current value.
- **C4**: make `setConfig` with a different plant resubscribe.
- **C5**: subscribe once per connection and plant, with backoff.
- **C5**: show terminal states for `plant_not_found` and unauthorized.
- **C5**: handle `unavailable` status events.
- **C5**: make the backend accept subscriptions for a plant that is not loaded yet and bind them on registration.
- **C5**: send a status event before revoking a subscription.
- **C6**: make the hold-to-shutdown gesture cancel when the pointer leaves or is lost.
- **C7**: keep the snapshot on a failed action and show an inline error.
- **C8**: use the Home Assistant frontend context API for connection and data if it is documented for custom cards in 2026.9; otherwise keep `hass`, and record the reason.
- **C9**: replace the custom editor with `getConfigForm`, and prefill `getStubConfig` from `hydronicus/list_plants`; existing `plant: <uuid>` YAML keeps working.
- **C10**: register the card automatically with `frontend.add_extra_js_url`, using a versioned URL and `cache_headers=True`.
- **C10**: add `frontend` to the manifest dependencies.
- **C10**: guard `customElements.define` against double loading.
- **C10**: document in `docs/lovelace.md` how to remove a now-redundant manual resource.
- **C11**: wrap the card in `ha-card` with current theme tokens, and fix the `.badge.dry-run` versus `dry_run` class mismatch.
- **C12**: format numbers with the user's locale, and display Celsius snapshot temperatures in the user's unit system.
- **C13**: use logical CSS properties so right-to-left layouts mirror correctly.
- **C14**: open more-info for Hydronicus-owned entities.
- **C15**: fix the accessibility findings.
- **C16**: return a realistic `getCardSize`.
- **C17**: upgrade the frontend toolchain to the newest versions that keep lint, tests, and build green, and record any major version held back and why.
- **X4**: replace string `hass.data` keys with `HassKey`, and derive loaded plants from `hass.config_entries.async_loaded_entries`.
- **M1**: set `iot_class` to `calculated`.
- Bump `PRESENTATION_SCHEMA_VERSION` only when the snapshot shape changes, and keep the card and backend versions in step.

Done when every task is green, `make verify` passes (it includes `frontend-check`), and the rebuilt bundle is committed.

## Wave 2 - integrate (lead)

1. Integrate the workstreams in this order: W1, W2, W3, W4, W5, each as exactly one commit on the feature branch.
2. Resolve `strings.json` conflicts section by section, then copy `strings.json` to `translations/en.json`.
3. Resolve contract requests while integrating, or dispatch them to a fresh agent with the requesting workstream's context.
4. Run `make verify` after each integration.

Wave 2 is done when all five commits are on the branch and `make verify` is green.

## Wave 3 - end to end (lead, with one user checkpoint)

Setup:

1. Create a disposable configuration directory outside the repository, in the session scratchpad.
2. Symlink `custom_components/hydronicus` from the feature branch checkout into it.
3. Write `configuration.yaml` with `default_config:` and synthetic entities:
   - template temperature sensors in `°C` and `°F`, with `device_class: temperature`;
   - a template humidity sensor;
   - template switches for every valve, pump, and source, each backed by an `input_boolean`, so any actuator call becomes visible in history.
4. Start `.venv/bin/hass -c <dir>` on a free port, and open it in the in-app browser.
5. Ask the user to complete onboarding and log in, then wait for their confirmation.
6. Agents never create accounts or type passwords.

Checklist, with each item recorded as pass or fail with evidence:

1. The setup flow and every subentry flow show field descriptions, units, sections, filtered pickers, and translated labels, with no raw keys in errors, aborts, or success messages (B4, F2-F6).
2. Reconfigure each subentry type, and confirm the translated success message (B4).
3. Entity names, enum states, select options, icons, device classes, and entity categories render translated and correct (E1-E5).
4. The zone thermostat turns off and on through actions and the thermostat card, and turn-on restores the previous mode (B3).
5. With the metric unit system, a `64.4 °F` zone sensor reads 18 °C and produces heating demand (B1).
6. Restart with `unit_system: us_customary` and confirm the climate display in °F, correct condensation margin delta (B2), and correct demand (B1).
7. Remove a bound synthetic entity, and confirm the repair appears, its fix opens the owning subentry's reconfigure form, and the issue clears after repair (R1).
8. The card loads with no manual resource, is offered in the card picker with a prefilled plant, and renders live data (B5, C9, C10).
9. In a sections view at one, two, and three columns and at mobile width, the card does not overlap other cards (C2).
10. The dropdowns show real values, and changing the plant in the editor switches the stream (C3, C4).
11. Unloading and reloading the integration and restarting Home Assistant show clear card states and recover (C5).
12. Releasing the hold button off target does not shut down, and a failed action shows an inline error (C6, C7).
13. The card works in dark mode and in a right-to-left language, and more-info opens for Hydronicus-owned entities (C11, C13, C14).
14. Downloaded diagnostics remain redacted.
15. The history of every synthetic `input_boolean` shows no change during the run, because Dry run stayed on.
16. Home Assistant logs show no Hydronicus errors, unexpected warnings, or translation errors.

Save screenshots and log excerpts in the scratchpad.
A failed item goes back to its owning workstream as a fresh fix agent with the failing evidence, and is retested after integration.

Wave 3 is done when every checklist item passes with evidence, and Home Assistant is stopped with its configuration directory kept for the user.

## Wave 4 - review (lead)

1. Run the `code-review` skill against `main`, using this plan as the spec.
2. In parallel, run one adversarial reviewer agent focused on the invariants, the fail-closed unit path, and migration safety.
3. Fix every confirmed finding with a red then green test.

Wave 4 is done when every confirmed finding is fixed, and `make verify` is green.

## Wave 5 - ship (lead)

1. Check that `README.md`, `docs/configuration.md`, `docs/troubleshooting.md`, and `docs/lovelace.md` agree with the shipped behaviour.
2. Push the branch, and open a pull request against `main` whose body covers:
   - each finding ID with its proof;
   - the Wave 3 results table;
   - compatibility notes (display changes, the condensation margin statistics note, removing the manual card resource, and the 2026.9.0 minimum);
   - the out-of-scope follow-ups.
3. Watch CI (`CI`, `Validate` with hassfest and HACS, and `Release` checks where triggered), and fix failures.

Wave 5 is done when the pull request is open, and every CI check is green.

## Finding register

Paths are relative to `custom_components/hydronicus/` unless they start with `frontend/`, `tests/`, or a repository root file.

| ID | Finding | Evidence | Owner |
| --- | --- | --- | --- |
| V1 | Tests cannot run on Home Assistant 2026.9.3 | Two collection errors from `voluptuous_serialize` imports, plus `test_init.py:189` using the device lookup deprecated in 2026.8 (removal 2027.8); the integration code passed 406 tests, and 42 flow tests passed with a probatio shim | Wave 0 |
| B1 | Temperature units are ignored | No code reads `unit_of_measurement`; a `64.4 °F` zone sensor produced current temperature 64.4, action idle, and no demand against 21 °C | W1 |
| B2 | Condensation margin converts as an absolute temperature | `sensor.py:453-478` uses `TEMPERATURE`; under US customary units a 4.1484 °C margin showed 39.47 °F instead of 7.47 °F | W2 |
| B3 | `climate.turn_on`, `turn_off`, and `toggle` are unsupported | `climate.py:42` declares no `TURN_ON` or `TURN_OFF`; `climate.turn_off` raised `ServiceNotSupported` | W2 |
| B4 | Flow messages render raw keys | Missing `config_subentries.{actuator,circuit,zone,source}.error.dry_run_shutdown_in_progress`, `config_subentries.*.abort.reconfigure_successful`, `config.abort.already_configured`, `config.abort.reconfigure_successful`, and `config.error.thermostat_loop` | W3 |
| B5 | The card never leaves the loading state | `frontend/tsconfig.json:10` with class fields at `frontend/src/hydronicus-plant-card.ts:311-316` and `557-560` shadow Lit accessors; reproduced in a browser | W5 |
| X2 | No Home Assistant exception types are used | `ValueError` and `RuntimeError` at `runtime.py:229`, `273`, `417-474`, `1158`, and `1879-1883`; raw errors from `runtime.py:146-149` during setup | W1 |
| X3 | Legacy test-seam shims and redundant cleanup | `runtime.py:14-17`, `323`, `845-850`; `repairs.py:32-43`; `__init__.py:200` | W1, W4 |
| E1 | Hard-coded English entity names | `_attr_name` across `sensor.py`, `binary_sensor.py`, `select.py`, `button.py`; there is no `entity` section in `strings.json` | W2 |
| E2 | Hard-coded icons | More than 20 `_attr_icon` assignments, and no `icons.json` | W2 |
| E3 | Status sensors and select options are untranslated strings | Operating mode, controller status, reconciliation status, source changeover, and the requested-mode select | W2 |
| E4 | Binary sensors and the dwell sensor lack classes and categories | No `device_class` on binary sensors; the dwell sensor uses unit `"s"` with no device class | W2 |
| E5 | Volatile attributes are recorded | Operations, reasons, explanations, and logic summaries change on every evaluation | W2 |
| E6 | Outdated platform typing and imports, and no `PARALLEL_UPDATES` | `AddEntitiesCallback` is used while passing `config_subentry_id`; `entity_device.py:5` | W2 |
| E7 | Zone climate entities omit humidity | Zones already bind humidity sensors | W2 |
| F2 | No field descriptions | None of the 23 config and subentry steps has `data_description` | W3 |
| F3 | Numeric and name fields use raw validators | `vol.Coerce(float)` and `vol.Range` throughout `config_flow.py`, and plain `str` names | W3 |
| F4 | Long optional field groups are not sectioned | Actuator feedback fields and cooling fields | W3 |
| F5 | Entity pickers are unfiltered | Temperature and humidity bindings use `domain="sensor"` only | W3 |
| F6 | Option labels are hard-coded English | `SelectOptionDict(label=...)` for thermostat kind, aggregation, and source type | W3 |
| F8 | Parent flow steps use the generic `FlowResult` | `config_flow.py:1781`, `1807` | W3 |
| R1 | Repairs cannot be fixed from the UI | `repairs.py:70` sets `is_fixable=False` | W4 |
| C2 | The card overflows in the sections view | `getGridOptions` fixes six rows (376 px) while content needs more than 1,200 px | W5 |
| C3 | Dropdowns show the wrong value | `.value` is bound before options exist at `hydronicus-plant-card.ts:392`, `438`, `571` | W5 |
| C4 | Changing the plant is ignored | `hydronicus-plant-card.ts:321-330` with the early return at `463` | W5 |
| C5 | The subscription lifecycle is fragile | A retry storm of about 120 per second on persistent errors, duplicate subscribes, dropped `unavailable` events, a silent revoke at `websocket.py:72-76`, and a possible silent failure on resubscribe | W5 |
| C6 | Hold-to-shutdown fires when released off target | `hydronicus-plant-card.ts:402`, `516-531` | W5 |
| C7 | A failed action replaces the whole card | `hydronicus-plant-card.ts:357`, `495-500` | W5 |
| C8 | Frontend context API unused | Documented from Home Assistant 2026.4 and 2026.5 | W5 |
| C9 | Custom editor and empty stub config | `getStubConfig` returns an empty plant; the native select editor never retries | W5 |
| C10 | Manual resource registration, unversioned and uncached | `frontend.py:10`, `22-24`; `docs/lovelace.md:6-13` | W5 |
| C11 | Theme tokens ignored, and a badge class mismatch | No `ha-card`; `.badge.dry-run` at `hydronicus-plant-card.ts:150` versus `dry_run` at `391` | W5 |
| C12 | Fixed English text, `toFixed`, and a hard-coded `°C` | `hydronicus-plant-card.ts:417-433`; `logic.ts:122-124` | W5 |
| C13 | Right-to-left layouts do not mirror | Physical CSS properties at `hydronicus-plant-card.ts:145`, `170`, `225-226`, `293-296` | W5 |
| C14 | No more-info access | No `hass-more-info` event | W5 |
| C15 | Accessibility gaps | `aria-label` on plain elements at `hydronicus-plant-card.ts:391`, `424-425`, and an `h1` per card | W5 |
| C16 | Unrealistic card size | `getCardSize` returns 7 | W5 |
| C17 | Outdated frontend toolchain | esbuild 0.25, vitest 3, TypeScript 5, `@types/node` 24 | W5 |
| C18 | Element behaviour is untested | Frontend tests cover only `logic.ts`, and lint is only `tsc` | W5 |
| X4 | Untyped `hass.data` and a hand-kept runtime registry | `websocket.py:89`, `193`, `199` | W5 |
| M1 | `iot_class` does not describe a calculating integration | `manifest.json` declares `local_push` | W5 |
