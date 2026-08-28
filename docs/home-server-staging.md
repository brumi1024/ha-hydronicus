# Home-server staging environment

The home-server environment is a final integration-test surface for Home Assistant UI and runtime behavior.
It does not replace deterministic local tests or CI.

Keep staging isolated from the production Home Assistant configuration and physical plant control.
Use a separate Home Assistant instance or a separate disposable configuration directory with its own storage, database, and test entities.

## Required shape

- Run the same Home Assistant release declared in `hacs.json` or the compatibility version currently under test.
- Mount or synchronize this checkout into `config/custom_components/hydronicus`.
- Use synthetic temperature sensors and input booleans for the first validation stage.
- Keep Dry run enabled when observing real sensors or equipment.
- Keep credentials, server addresses, tokens, and site-specific paths outside the repository.
- Make restoring the staging configuration or container a simple, documented server-side operation.

The existing site-specific home-server document should supply the host, deployment path, restart command, and log command.
Do not duplicate those private values in this repository.

## Chunk smoke test

Run `make verify` locally before deploying a chunk.
Then perform the applicable staging checks:

1. Synchronize the integration directory and restart Home Assistant or reload the integration as appropriate.
2. Confirm Home Assistant starts without integration or translation errors.
3. Create, reconfigure, reload, and delete the affected plant objects through the UI.
4. Confirm entity IDs, unique IDs, topology preview, and diagnostics match the configured synthetic plant.
5. Drive the synthetic sensor values through the chunk's named scenario.
6. Confirm the visible explanations and virtual actuator sequence match the automated scenario.
7. Confirm logs contain no unexpected exceptions or repeated warnings.
8. Confirm Dry run issued no physical service calls.

Record the Home Assistant version, commit SHA, scenario name, result, and any log excerpt needed to explain a failure.

## Observed disposable run on 2026-08-28

The production-hardening working tree was staged against Home Assistant `2026.8.2` in a new disposable configuration derived from base commit `7b9defc2f3f6cb7913fb8550cc21b92d37ff2513`.
Because the hardening changes were not committed, this run is working-tree evidence and is not release-artifact or HACS-install evidence.

The run observed all of the following behavior:

- Home Assistant created one Plant through its config-flow HTTP surface in Dry run.
- The synthetic Plant contained one initial Zone, one Circuit, one valve, and one pump.
- Home Assistant added a second Zone subentry, reconfigured it without changing its subentry or object ID, and rebuilt the complete runtime graph.
- The resulting registry contained five Plant or topology devices and 42 Hydronicus entities with singular config-entry and config-subentry ownership.
- Every topology device pointed to the parent Plant through `via_device_id`.
- A real Hydronicus climate service call produced proposed heating operations while the synthetic valve and pump stayed off.
- A WebSocket subscription to Home Assistant service-call events observed zero calls targeting either synthetic actuator.
- A forced stored version `1.1` entry with a full legacy subentry, disabled Dry run, and stale output authorization migrated to version `2.0` on restart.
- Migration restored Dry run, removed stale authorization, rebuilt parent ownership, and minimized the subentry to its ID-only handle.
- Downloaded diagnostics remained redacted and contained none of the configured names or entity IDs.
- Config-entry reload, subentry deletion, parent-graph reconciliation, full entry removal, and registry cleanup completed without actuator calls.
- The final service-level Home Assistant stop exited with status zero and logged no Hydronicus warning or error.

The first shutdown reproduced two real lifecycle defects before the final pass: WebSocket cleanup mutated Home Assistant's subscription map during iteration, and a one-shot Home Assistant stop listener was removed twice.
Both defects now have regression tests and were absent from the final disposable run.

The host environment logged its standard custom-integration warning, a zlib acceleration fallback, and a missing FFmpeg executable from Home Assistant's own loaded components.
The same FFmpeg message occurred without a Hydronicus operation and is recorded as staging-environment noise rather than an integration failure.

This run does not authorize physical control, replace a HACS installation test from a committed archive, complete the separate cooling or source pilots, or satisfy non-author installation approval.

## Activation boundary

Do not use staging to exercise real actuator service calls until the implementation plan reaches the corresponding staged rollout and provides an immediate manual rollback.
Synthetic testing comes first, Dry run observation comes second, and any physical control requires an explicit rollout decision.
