---
name: hydronicus-verify
description: Verify a Hydronicus change against its done criteria, the invariants in docs/architecture.md, Home Assistant behaviour, and the simulator. Use when implementing, reviewing, or declaring a change complete in this repository.
---

# Hydronicus Verify

Treat repository commands as the source of truth and produce explicit evidence for each done criterion.

## Workflow

1. State the change's done criteria in one line each.
2. Read the invariants in `docs/architecture.md#testing-and-invariants` and name the ones the change touches.
3. Pick the test seam for each criterion:

   | Change | Seam |
   | --- | --- |
   | Model, plant file, `step()`, reconciler, demand, supply, DHW | `tests/core/` |
   | Setup, flows, entities, persistence, lifecycle, Repairs, actions | `tests/integration/` |
   | Behaviour over many evaluations, timings, or plant shapes; any invariant | `tests/sim/` (scenario or property) |
   | Adapter scripts in `adapters/` | `tests/test_adapters.py` |
   | Docs, examples, release metadata | `tests/test_docs_examples.py`, `tests/test_release_package.py` |

4. Write the smallest test that fails without the change, then make it pass.
5. Check the side files a change can need:
   - a new plant file key: `docs/examples/full-plant.yaml`;
   - a UI string: `strings.json`, copied to `translations/en.json`;
   - a new entity, Repair, or action: the README's overview if it changes what a user sees.
6. Run the narrowest target while working: `make test-core`, `make test-integration`, `make test-sim`, or a single test file with `uv run pytest`.
   After a change to the core or the simulator, also run `HYPOTHESIS_SIM_PROFILE=sim-dev make test-sim`.
7. Run `make verify` before declaring the change complete.
8. If UI or runtime behaviour changed, check it in a disposable Home Assistant with synthetic entities, such as the trial kit in `docs/examples/trial/`, with **Control equipment** off unless the check needs commands, and record what you saw.

## Completion report

List each done criterion with its evidence: the test that proves it, the commands run and their outcome, and live evidence when applicable.
Name any gap that is not verified.
Do not claim a change is complete while a required check is skipped or failing, and do not arm physical equipment to finish a verification step.
