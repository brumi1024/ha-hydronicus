# Hydronicus {{VERSION}}

This is the sixth installable release candidate for supervised Dry run evaluation.
Use it in Dry run before considering active heating control.

## Changes since rc.5

- Replace hybrid topology storage with one validated parent-owned Plant graph and stable ID-only config-subentry handles.
- Add a restart-safe migration from config-entry version 1.1 to 2.0 that restores Dry run and invalidates stale output authorization.
- Serialize every per-Plant runtime mutation and make actuator timeout reconciliation target-aware.
- Reconcile late service completions conservatively without suppressing a required opposite command.
- Add Home Assistant 2026.8 object devices with singular config-entry and config-subentry ownership.
- Return safely to Dry run after topology or physical binding changes and retain the old graph when an active deletion cannot shut down safely.
- Define reload, unload, removal, and Home Assistant stop as command-free lifecycle boundaries with explicit active-equipment warnings.
- Validate configuration flows, migration, diagnostics, reload, deletion, removal, and shutdown in disposable Home Assistant 2026.8.2 staging with zero synthetic actuator calls.
- Expand the complete gate to 420 Python tests, 8 frontend tests, and a large-Plant benchmark covering setup, refresh, reconciliation, publication, memory, and service-call counts.

## Highlights

- Complete Dry run Zone climate entities with comfort, eco, and away presets.
- Required and optional temperature observations with calibration and freshness handling.
- Mean, median, minimum, maximum, designated-reference, and weighted-mean aggregation.
- Configurable hysteresis, minimum active duration, and minimum idle duration.
- Aggregate-temperature, blocked-state, blocked-reason, and structured shared-valve warning visibility.
- Cooling condensation diagnostics and deterministic Dry run source recommendations.
- Explicit idempotent actuator execution with one Plant-level Dry run control.
- Proposed-versus-executed operation reporting and ordered safe shutdown when Dry run is re-enabled.
- Topology-driven Plant status with shared hydraulic relationships and precise proposed, executed, suppressed, failed, and shadow states.

## Upgrade

Back up the Home Assistant configuration before upgrading.

Install this release through HACS, restart Home Assistant, and confirm that the Hydronicus config entry reloads without errors.

Back up Home Assistant before the first RC6 start.
RC6 migrates stored version 1.1 Plants to the version 2.0 parent-owned graph before runtime setup.
Migration returns every Plant to Dry run and requires the configured output list to be reviewed again before active heating can be authorized.

Every Plant created through the UI starts in Dry run.
The Plant reconfiguration flow can disable Dry run after one confirmation of the configured heating outputs.
Cooling starts and source-selector operations remain Dry run only.

Version 2.0 config subentries are stable Home Assistant ownership handles while the parent entry owns the complete validated topology.
Do not edit Home Assistant config-entry storage by hand to bypass migration or output authorization.

## Rollback

If the integration does not load correctly, follow the backup-first rollback guide.

Keep physical temperature, condensation, pressure, and flow safeguards independently active during any rollback.

## Known limitations

Dry run Plants do not issue physical actuator service calls.
When Dry run is off, the generic executor can control configured heating valves, pumps, and direct source demand after the safety checks.
Physical rollout remains unauthorized until the exact RC6 HACS installation evidence and human approval are complete.

Repairs, redacted downloadable diagnostics, startup reconciliation, and bounded command-failure recovery are implemented.
Physical cooling starts and automatic source selection remain gated while the public beta matures.

## Hydronicus rename boundary

Hydronicus is installed from `custom_components/hydronicus` and uses the `hydronicus` domain.

The former `hydronic_climate` integration name and domain are not supported and must not be recreated during an upgrade.
