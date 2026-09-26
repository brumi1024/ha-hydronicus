# Contributing

Keep changes focused, and consistent with [the redesign plan](docs/redesign-plan.md), which records the decisions, contracts, and invariants of the current design.

Put control logic in the pure core, `custom_components/hydronicus/core/`, and keep Home Assistant specifics in the adapter around it, as [the architecture boundaries](docs/development.md#architecture-boundaries) describe.

Start a behaviour change with a test that fails without it: a core test for control and the plant file, a simulator scenario or property for a safety invariant, and an integration test for setup, flows, entities, and lifecycle.

Use the commands in [the development environment guide](docs/development.md).
Run `make verify` before handing off a change.
Use the repository-local `hydronicus-verify` skill to map a change's done criteria to test and live evidence.
