# Development environment

The supported local workflow uses Python 3.14.2 or newer, `uv`, and the commands in the root `Makefile`.
The lockfile is the source of truth for exact development and test dependency versions.

## First setup

Install `uv` and Node.js with npm, then run:

```console
make bootstrap
make hooks
```

`make bootstrap` creates or updates `.venv` from `uv.lock` and installs the frontend packages from `frontend/package-lock.json`.
`make hooks` installs the shared pre-commit hooks after bootstrapping the environment.

## Daily commands

- `make test-core` runs deterministic topology and controller tests with core coverage.
- `make test-integration` runs Home Assistant config, entity, and lifecycle adapter tests.
- `make test-scenarios` runs named, time-ordered operating scenarios.
- `make lint` checks Ruff linting, Python compilation, and repository JSON files.
- `make format-check` checks the complete repository with the normal Ruff formatter configuration.
- `make typecheck` checks the dependency-free controller package with mypy.
- `make verify` runs the complete local quality gate used by CI.

Run the narrowest relevant target while developing and run `make verify` before handing off a chunk.
The pre-commit hook applies Ruff formatting to every changed Python file.
The CI format check covers the same complete source tree.

## Canonical configuration

Config-entry version 4 and minor version 0 are the supported persisted contract.
The parent config entry owns one complete UUID-backed graph in `topology`, including every Zone, Circuit, Delivery Route, Valve, Pump, Source, and the source selector.
`zone_objects` maps every zone-owned Circuit and Valve to its owning Zone, and every other object belongs to the Plant, as `core/legacy/ownership.py` defines.
`subentry_objects` records which graph objects are exposed through Home Assistant config subentries.
Each Zone has exactly one `zone` subentry, and a source may have one `source` subentry; each subentry is only a stable ownership handle containing `{"id": "<object UUID>"}`.
No topology field is duplicated between the parent graph and a subentry.
Ownership is deletion-closed: removing a zone subentry removes exactly its zone closure through `without_zone` and always leaves a graph that validates and compiles.
Guided setup, plant file import and edits, zone and pump edits, and deletion build the proposed complete graph through the graph edit API in `entry_configuration.py`, which validates ownership and compiles it before it is persisted.
If Home Assistant removes a subentry while a Plant is active, Hydronicus completes the ordered transition to Dry run against the old graph before deleting that zone or source from the parent graph.
If the shutdown cannot complete, the parent graph and active runtime are retained and the failure is logged.
Zone observations use typed temperature and humidity metadata collections rather than parallel legacy representations.

The plant file in `core/legacy/plant_document.py` is the portable form of the same graph, documented for users in [the plant file reference](plant-file.md).
It maps slugs to objects, derives missing IDs with `uuid5` from the Plant ID and the slug, and exports the canonical form with every ID written, so an export and import round trip keeps every object ID and entity ID.

Entries of earlier development versions, below version 4, are not migrated: `async_migrate_entry` logs that the Plant must be set up again and refuses the entry.
Do not add speculative schema aliases or migration paths without a concrete persisted predecessor and fixtures that prove the transition.

## Architecture boundaries

The redesign in [the redesign plan](redesign-plan.md) replaces the model below phase by phase.
`custom_components/hydronicus/core/model.py` describes a Plant as an optional source, its pumps, its zones, and its loops, as frozen values addressed by slugs.
`custom_components/hydronicus/core/plant_file.py` reads, validates, and writes the format 2 plant file, which is also the storage schema: `to_storage` splits a Plant into config entry data and zone subentry data, and `from_storage` joins them again.
`custom_components/hydronicus/core/step.py` defines the observations `step()` reads and the State it persists, and `step()` computes the desired state of every output with every hydraulic wait already in it: a valve stays open while a pump that may still run needs it, a pump stays on while a released source request may still be on, and the source is requested only once its loops are ready and their pumps are observed running.
`custom_components/hydronicus/core/demand.py` holds what `step()` reads from sensors and thermostats: fail-closed aggregation, the worst-case dew point, digital thermostat hysteresis and minimum durations, and the normalization of an external thermostat's `hvac_action`.
`custom_components/hydronicus/core/reconcile.py` turns the desired state into the service calls to send in dependency order, keeps at most one call per output in flight, retries with backoff, reports Repairs, and proposes instead of sending in Dry run; `step_view` shows `step()` the calls still in flight and the Dry run proposals.
A decision never counts on a call having acted: a call that no observation has confirmed may act until `CALL_TIMEOUT` after it was sent.
Until the runtime, flows, and platforms move to the new model, they run on the v0.1 modules in `custom_components/hydronicus/core/legacy/`, which nothing new may import and which each phase deletes once their last consumer is gone.

`custom_components/hydronicus/core/legacy/configuration.py` decodes only the canonical persisted objects into typed domain values.
`custom_components/hydronicus/core/legacy/ownership.py` assigns every graph object to the Plant or to one zone so that removing a zone always leaves a valid graph.
`custom_components/hydronicus/entry_configuration.py` owns graph mutation, zone and source subentry handles, and exact output-authorization fingerprints without importing controller policy.
`custom_components/hydronicus/registrations.py` moves entity and device registrations between subentries when a graph edit changes an object's owner, and removes the registrations of objects a graph edit drops.
`custom_components/hydronicus/zone_area.py` puts a newly created zone climate entity in the one area its zone covers, after the entities have registered, and never assigns the zone device an area.
`custom_components/hydronicus/areas.py` owns every area registry read: it resolves the sensors that covered areas name, drops sensors Hydronicus provides, and reports missing areas for the runtime, the reviews, diagnostics, and repairs.
`custom_components/hydronicus/core/legacy/configuration.py` merges those resolved sensors after a zone's explicit sensors, while structural rules count an area as a sensor, so an area change never makes a stored graph invalid.
`custom_components/hydronicus/config_flow.py` composes the flow step modules in `custom_components/hydronicus/flows/`.
`custom_components/hydronicus/core/legacy/topology.py` indexes objects, validates relationships, and builds deterministic summaries and warnings.
`custom_components/hydronicus/core/legacy/controller.py` is a pure pipeline for heating, cooling, route arbitration, mode changeover, valve planning, pump planning, source coordination, and final assembly.
Its public evaluation result, diagnostics, deadlines, and command order are the contract; private phase helper structure is not.
`custom_components/hydronicus/runtime.py` owns the Home Assistant boundary and runs snapshot, evaluate, execute, and publish stages in that order.
One per-Plant operation lock serializes refresh, execution, reconciliation, safe shutdown, mode changes, Dry run changes, and teardown.
Runtime deadline scheduling, target-aware command reconciliation, and late service completion remain adapter concerns because they depend on Home Assistant time, observations, and service results.
Reload, unload, removal, and Home Assistant stop are deliberately command-free lifecycle boundaries and must never claim that physical shutdown occurred.

## Test boundaries

Pure controller behavior belongs under `tests/core/` and must use only the dependency-free controller interface.
Home Assistant setup, subentry, entity, reload, and adapter behavior belongs under `tests/integration/`.
Multi-step behavior with a fake clock belongs under `tests/scenarios/` and should use the reusable scenario harness.
Safety invariants that must hold across many topology shapes or timings belong in property-based tests.
The redesigned control is checked in `tests/sim/`, a simulator that owns physical state, drives `step()` and `reconcile()` as the runtime does, and asserts the plan's invariants after every event over generated Plants and traces.
Its Hypothesis profile `sim-ci` is deterministic; set `HYPOTHESIS_SIM_PROFILE=sim-dev` to explore many more examples locally.
The stages of `step()` and the reconciler's ordering, backoff, and Repairs also have unit tests in `tests/core/`.
The large synthetic benchmark covers pure compilation, pure evaluation, Home Assistant setup, runtime refresh, reconciliation, entity publication, memory, and zero-service-call Dry run behavior.

The current coverage threshold applies only to `custom_components/hydronicus/core`.
This keeps the safety-critical deterministic package measurable without obscuring incomplete adapter milestones behind a repository-wide percentage.

## Dependency changes

Edit `pyproject.toml`, then regenerate and validate the lockfile:

```console
uv lock
make bootstrap
make verify
```

Commit `pyproject.toml` and `uv.lock` together.
