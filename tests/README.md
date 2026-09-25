# Test layout

`core/` contains pure deterministic tests of the model, the plant file, `step()`, and the reconciler.
`integration/` contains Home Assistant tests of setup, the runtime, persistence, arming, areas, entities, and Repairs, with mocked actuators from `integration/helpers.py`.
`sim/` contains the plant simulator, which runs `step()` and `reconcile()` over simulated physical state and checks the redesign plan's invariants after every event, with the reference plant and the reproduced defects as named scenarios.
Root-level tests cover isolated units that do not need the Home Assistant test harness, the release package, and the documentation.
