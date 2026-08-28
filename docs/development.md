# Development environment

The supported local workflow uses Python 3.14.2 or newer, `uv`, and the commands in the root `Makefile`.
The lockfile is the source of truth for exact development and test dependency versions.

## First setup

Install `uv`, then run:

```console
make bootstrap
make hooks
```

`make bootstrap` creates or updates `.venv` from `uv.lock`.
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

## Canonical configuration and migration

Config-entry version 2 and minor version 0 are the supported persisted contract.
The parent config entry owns one complete UUID-backed graph in `topology`, including every Plant, Zone, Circuit, Delivery Route, Valve, Pump, Source, and selector relationship.
The `subentry_objects` map records which graph objects are exposed through Home Assistant config subentries.
Each version 2 subentry is only a stable Home Assistant ownership handle containing `{"id": "<object UUID>"}`.
No topology field is duplicated between the parent graph and a subentry.
Fresh UI setup, reconfiguration, and deletion compile the proposed complete graph before it is persisted.
If Home Assistant removes a subentry while a Plant is active, Hydronicus completes the ordered transition to Dry run against the old graph before deleting that object from the parent graph.
If the shutdown cannot complete, the parent graph and active runtime are retained and the failure is logged.
Zone observations use typed temperature and humidity metadata collections rather than parallel legacy representations.

Version 1.1 entries are migrated to version 2.0 before runtime setup.
Migration first makes the complete graph durable in the parent entry, then minimizes each legacy subentry to its object ID.
Repeating migration after an interruption is safe because both phases are idempotent.
Migration invalidates output authorization and returns the Plant to Dry run.
Do not add speculative schema aliases or migration paths without a concrete persisted predecessor and fixtures that prove the transition.

## Architecture boundaries

`custom_components/hydronicus/core/configuration.py` decodes only the canonical persisted objects into typed domain values.
`custom_components/hydronicus/entry_configuration.py` owns graph mutation, migration, subentry ownership, and exact output-authorization fingerprints without importing controller policy.
`custom_components/hydronicus/core/topology.py` indexes objects, validates relationships, and builds deterministic summaries and warnings.
`custom_components/hydronicus/core/controller.py` is a pure pipeline for heating, cooling, route arbitration, mode changeover, valve planning, pump planning, source coordination, and final assembly.
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
