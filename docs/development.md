# Development environment

The supported local workflow uses Python 3.14.2 or newer, `uv`, and the commands in the root `Makefile`.
The lockfile is the source of truth for exact development and test dependency versions.
[CONTEXT.md](../CONTEXT.md) is the glossary, and [the invariants](#invariants) are the rules every change keeps.

## First setup

Install `uv`, then run:

```console
make bootstrap
make hooks
```

`make bootstrap` creates or updates `.venv` from `uv.lock`.
`make hooks` installs the shared pre-commit hooks after bootstrapping the environment.

## Daily commands

- `make test-core` runs the pure tests of the model, the plant file, `step()`, and the reconciler, with core coverage.
- `make test-integration` runs the Home Assistant tests of setup, the runtime, persistence, arming, areas, entities, flows, and Repairs.
- `make test-sim` runs the plant simulator: the invariants over generated Plants and event traces, the reproduced defects, and the reference plant.
- `make lint` checks Ruff linting, Python compilation, and the repository's JSON files.
- `make format-check` checks the whole repository with the Ruff formatter.
- `make typecheck` checks the whole `custom_components/hydronicus` package with mypy.
- `make release-check` and `make public-beta-check` build and inspect the HACS release archive and check the installation documentation.
- `make test` runs every test with core coverage.
- `make verify` runs the complete local quality gate that CI runs.

Run the narrowest relevant target while developing, and `make verify` before handing off a change.
The pre-commit hook formats changed Python files with Ruff, runs `make lint`, and runs the core tests.

The simulator's property tests use the Hypothesis profile `sim-ci`, which is deterministic, so CI sees the same examples on every run.
Set `HYPOTHESIS_SIM_PROFILE=sim-dev` to explore many more examples locally:

```console
HYPOTHESIS_SIM_PROFILE=sim-dev make test-sim
```

## Stored configuration

Config entry version 5.0 is the supported persisted contract.
The entry's data is the format 2 plant file without `zones`, and each zone is a `zone` subentry whose data is that zone's mapping plus its `slug`; the subentry's unique ID is the slug and its title is the zone's name.
Home Assistant stores a config entry with sorted keys, so `pumps`, `loops`, and each zone's `loops` are stored as lists of objects that carry their `slug`, which keeps the order the owner chose.
The entry's options hold `armed_outputs`, the confirmed output entity IDs, and `control`, the **Control equipment** state.
The runtime's timers, the Plant mode, the reconciler's retry state, the output memory, and the last valid Plant with the outputs it was commanding are stored per Plant with `homeassistant.helpers.storage.Store`.

Entries of earlier versions are not migrated: `async_migrate_entry` logs that the Plant must be set up again and refuses the entry.
Do not add schema aliases or migration paths without a concrete persisted predecessor and fixtures that prove the transition.

## Architecture boundaries

`custom_components/hydronicus/core/` is the pure core: it has no Home Assistant imports, keeps at least 90 percent test coverage, and the simulator loads it without Home Assistant.

- `core/model.py` describes a Plant as an optional source, its pumps, its zones, and its loops, as frozen values addressed by slugs, and the desired state that `step()` returns.
- `core/plant_file.py` reads, validates, and writes the format 2 plant file, which is also the storage schema: `to_storage` splits a Plant into entry data and zone subentry data with its slug-keyed objects listed in order, `from_storage` joins them again, and `describe_path` puts a problem's path in words.
- `core/demand.py` holds what `step()` reads from sensors and thermostats: fail-closed aggregation, the worst-case dew point, digital thermostat hysteresis and minimum durations, and the normalization of an external thermostat's `hvac_action`.
- `core/step.py` defines the observations `step()` reads and the State it persists, and `step()` computes the desired state of every output with every hydraulic wait already in it: a valve stays open while a pump that may still run needs it, a pump stays on while a released source request may still be on, and the source is requested only once its loops are ready and their pumps are observed running.
- `core/reconcile.py` turns the desired state into the service calls to send, in dependency order, keeps at most one call per output in flight, retries with backoff, reports the outputs for Repairs, and proposes instead of sending in Dry run; `step_view` shows `step()` the calls still in flight and the Dry run proposals.

A decision never counts on a call having acted: a call that no observation has confirmed may act until `CALL_TIMEOUT` after it was sent.

The Home Assistant adapter lives beside the core:

- `runtime.py` runs one Plant: it observes, calls `step()` and `reconcile()`, sends the actions outside the evaluation, persists the State, raises the Repairs, publishes the entities, and schedules the next evaluation.
  Evaluations are coalesced and never await, so they need no lock.
  Setup restores the stored State and the digital thermostats before the first evaluation, and stopping only cancels, never commands.
  When a new configuration removes an output that is on, or is not valid, the first evaluation runs the stored previous Plant with Control equipment forced off until its outputs are observed off, and only then the new Plant.
  A configuration that is not valid still loads, as an empty Plant with its stored ID and name that only observes, next to the `invalid_plant` Repair.
- `observe.py` reads Home Assistant states as observations: output feedback, units and plausibility of sensors, external thermostats, and the output memory that keeps when an output last changed across restarts.
- `areas.py` owns every area and floor registry read: it resolves the sensors that covered areas name on every evaluation, drops sensors Hydronicus provides, and reports area problems for the runtime, the reviews, and Repairs.
  `zone_area.py` puts a new zone climate entity in the one area its zone covers.
- `storage.py` moves the Plant in and out of the config entry and its zone subentries, prunes references to a removed zone, and holds the arming options.
  `async_store_plant` stores a Plant over an entry in an order that never lets the update listener prune a reference, and the listener reloads a loaded Plant once however many parts change.
- `bindings.py` refuses an entity Hydronicus provides and an output another Plant binds.
- `config_flow.py` exposes the flows in `flows/`: guided setup, import, and the entry's reconfigure in `plant.py`, the zone subentry flow in `zone.py`, and Plant settings in `settings.py`.
  Every flow edits a plant file document with the helpers in `flows/documents.py`, which keep the settings a form does not show, and checks the whole resulting Plant with `flows/forms.py`, which maps a problem onto the field its path belongs to.
  A select's fixed options are translated through its `translation_key`, such as the add option of a pick form, whose value `add-new` is a valid translation key that no slug can be.
  What the code writes into a form stays English: labels of options whose values are slugs or entity IDs, such as `Living area / Ceiling` or a pump driven by the source, and description placeholders, such as the reviews, the change summary, and the reconfigure status, because Home Assistant translates neither.
- `issues.py` computes the Repairs of a Plant, and `repairs.py` holds their fix flows: arming unconfirmed outputs, and opening the entry's or a zone's reconfigure flow through `next_flow`, with a missing binding's path as the flow's init data so that it opens at the form that binds it.
- `entity.py` and the platforms publish the [entity contract](entities.md); unique IDs derive from the Plant ID and object slugs.
- `services.py` registers the `hydronicus.export_plant` action, and `diagnostics.py` redacts the configuration, the last observations, the desired state, and the reconciler state.

Reload, unload, removal, and Home Assistant stop are command-free lifecycle boundaries and must never claim that physical shutdown occurred.

## Test boundaries

- `tests/core/` holds pure tests of the model, the plant file, `step()`'s stages, and the reconciler's ordering, backoff, and Repairs.
- `tests/integration/` holds Home Assistant tests of setup, the runtime, persistence, arming, areas, entities, flows, and Repairs, with mocked actuators from `tests/integration/helpers.py`.
- `tests/sim/` holds the simulator, which owns physical state, drives `step()` and `reconcile()` as the runtime does, and asserts the plan's invariants after every event, with the reference plant and the reproduced defects as named scenarios.
- Root-level tests cover isolated units that need no Home Assistant harness, the release package, and the documentation.

`tests/test_docs_examples.py` keeps the user documentation true: every plant file example imports, the documented error paths and messages are the real ones, the reference plant example matches the test fixture, and every bold UI label exists in `strings.json` or Home Assistant.
Edit `strings.json`, then copy it to `translations/en.json` byte for byte.

## Dependency changes

Edit `pyproject.toml`, then regenerate and validate the lockfile:

```console
uv lock
make bootstrap
make verify
```

Commit `pyproject.toml` and `uv.lock` together.

## Invariants

The simulator under `tests/sim/` checks invariants 1 to 8 on simulated physical state, not on controller belief, after every event of random plants and random traces.
A trace may delay, reject, or time out any command, restart the runtime, jump the clock, and make a sensor stale or an entity unavailable.
Only a spontaneous physical change, such as a valve closing by itself, is exempt, and the controller must react to it within one evaluation.

1. Dry run and an unarmed output receive zero service calls.
2. A pump with `min_flow: path` never runs without an open path, where a loop with no valve is always an open path.
3. The source is requested only while at least one loop of the current mode is ready and, when its pump is switched, that pump is observed running.
4. A source-driven pump with `min_flow: path` has an open path while the source is requested, during its post-run, and while it is observed running.
5. Heating loops and cooling loops never flow at the same time, and a mode change waits for the dwell and for the old mode's loops to stop.
6. A cooling loop flows only while its condensation guard permits, except a min-flow path during the source's post-run.
7. Every difference between desired and observed state is eventually observed resolved or reported as a Repair.
8. With unchanged observations, the first evaluation after a reload or restart sends no command.
9. Removing an object first stops the equipment it removes, and a configuration that is not valid stops in order and then only observes, with a Repair.
10. `custom_components/hydronicus/core/` has no Home Assistant imports and at least 90 percent coverage, and the whole package passes mypy.
11. Exporting a Plant and importing the file reproduces the Plant, its object IDs, and its entity IDs.
12. `make verify` is the gate.

The plans of earlier versions are in the git history, not in the repository.
