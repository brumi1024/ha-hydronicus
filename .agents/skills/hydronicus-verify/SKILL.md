---
name: hydronicus-verify
description: Verify a Hydronicus change against the done criteria of its phase in docs/redesign-plan.md, the plan's invariants, Home Assistant adapter behavior, and the simulator scenarios. Use when implementing, reviewing, or declaring a change complete in this repository.
---

# Hydronicus Verify

Treat repository commands as the source of truth and produce explicit evidence for the selected done criteria.

## Verification workflow

1. Read the phase and its done criteria in `docs/redesign-plan.md`, with the invariants and the contracts the phase names.
2. Read `CONTEXT.md` and keep the boundary between the pure core in `custom_components/hydronicus/core/` and the Home Assistant adapter.
3. State which public test seams the change touches:
   - Use `tests/core/` for the model, the plant file, `step()`, and the reconciler.
   - Use `tests/integration/` for Home Assistant setup, flows, entities, persistence, lifecycle, and Repairs.
   - Use `tests/sim/` for behavior over several evaluations on simulated physical state, and for the plan's invariants.
4. Add or update the smallest tests that prove the selected criteria.
5. Add a simulator property or scenario when the change affects an invariant across many plant shapes or timings.
6. Run the narrowest applicable target while working: `make test-core`, `make test-integration`, or `make test-sim`.
7. Run `make verify` before declaring the change complete.
8. If Home Assistant UI or runtime behavior changed, check it in a live Home Assistant with synthetic entities, such as the trial kit in `docs/examples/trial/`, with Control equipment off unless the check needs commands, and record the observed result.

## Completion report

Report the selected done criteria, the automated evidence for each, commands and outcomes, live evidence when applicable, and any unverified gap.
Do not claim a change is complete while a required check is skipped or failing.
Do not arm physical equipment merely to complete a verification step.
