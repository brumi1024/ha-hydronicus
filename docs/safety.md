# Safety limits

Hydronicus is a topology and coordination layer inside Home Assistant.
It is not a safety-rated controller.

## Two separate safety layers

Physical protection and software coordination have different responsibilities.

| Layer | What it can do | What it cannot guarantee |
| --- | --- | --- |
| Physical protection | Enforce limits when Home Assistant, the network, or the integration is unavailable | Understand Hydronicus topology or explain a software decision |
| Hydronicus software | Describe topology, calculate demand, sequence requests, explain the calculation, and record or dispatch explicit commands behind the Dry run boundary | Prove flow, pressure, temperature, condensation safety, electrical safety, or equipment capacity |

Keep appropriate independent hardware protection in service.
Depending on the plant, this can include high-limit controls, pressure relief, flow protection, freeze protection, condensation protection, pump protection, source interlocks, and emergency isolation.
The correct protection set depends on the equipment design and local requirements.

Never remove or bypass a physical interlock because Hydronicus reports that a route is ready.

## Thermostat ownership

Every Zone receives demand from exactly one thermostat.

The Hydronicus thermostat owns its target, presets, HVAC mode, hysteresis, and duration timing.

An external thermostat owns those decisions and Hydronicus consumes only its normalized `hvac_action`.

External heating and preheating request heating.

External cooling is accepted only through the existing explicit cooling and condensation safety observations.

External idle, off, unavailable, unknown, malformed, contradictory, or unsupported input cannot create actuator demand.

Hydronicus never calls a service on an external thermostat.

An external thermostat must not independently command an actuator also configured as Hydronicus-owned.

Externally actuated or valve-less delivery routes are unsupported.

## Current release boundary

Every new Plant starts in Dry run.
The Home Assistant UI exposes one Plant-level setting for changing that boundary.

Dry run can be turned off for valves and pumps, in heating and cooling, and for an optional direct source-demand output.
Dry run remains the default, and automatic source selection remains Dry run only.

The release calculates and publishes:

- Heating and cooling demand.
- Required and optional observation handling.
- The worst-case zone dew point and condensation margins.
- Supply or surface-temperature interlocks.
- Valve readiness, pump sequencing, and pump overrun.
- Minimum active and idle durations.
- Actuator feedback and mismatch diagnostics.
- Source eligibility, recommendation, demand permission, and changeover reasoning.
- Safe-shutdown plans, Repairs, and redacted diagnostics.

The codebase also contains a generic actuator executor and safe-shutdown dispatcher tested with synthetic and intercepted Home Assistant services.
The executor records proposed operations in Dry run and dispatches the allowed valve, pump, and source-demand operations when Dry run is off.
Source-selector operations are forcibly kept in Dry run by the runtime.
Direct source-demand output requires a valid running pump path.
Changing Dry run back on performs the ordered safe shutdown before further commands are suppressed.

## Dry run is not a safety proof

Dry run is safe for observing the software decision path because the runtime does not issue equipment service calls while it is enabled.
It still cannot prove that the configured topology matches the water circuit.

A passing topology validation means that the configured graph is internally consistent.
It does not mean that:

- A valve is installed on the expected pipe.
- A pump can serve all of its consumers.
- A sensor is calibrated or located correctly.
- A source can produce the requested water conditions.
- A circuit is protected against condensation or overheating.
- A hardware interlock will trip when required.

Use synthetic entities first, then shadow observation of real sensors if the staging contract and rollout decision permit it.
Do not use a Dry run result to authorize physical control.

## Cooling and condensation

Cooling requires different evidence from heating.
Zone temperature alone cannot establish a safe cooling request.

Condensation risk depends on humidity, dew point, supply or surface temperature, sensor freshness, circuit compatibility, and physical protection.

Hydronicus calculates these conditions and, outside Dry run, opens cooling valves and starts pumps only while every one of them is satisfied.
When the margin to the dew point becomes unsafe, it stops the pump immediately and closes the valves, without pump overrun.

Hydronicus checks condensation against one worst-case dew point per zone, calculated from the highest usable zone temperature and the highest usable zone humidity, including the sensors of its areas.
Dew point rises with both temperature and humidity, so this bound covers every area and space a zone spans without knowing which temperature and humidity sensors share a space.
A zone's temperature aggregation, such as a heating-oriented minimum or a designated reference, decides demand only and never lowers the dew point.
One humid space, such as a bathroom after a shower, therefore blocks cooling for the whole room even when the average humidity looks safe.
Cooling stays blocked while a required zone temperature or humidity sensor is unusable, or while no usable reading remains.
The worst case covers only the spaces that have sensors, so give every cooled space that can turn humid its own humidity sensor.

Hydronicus does not command the chilled-water source, so the source's own supply temperature limits stay in charge of how cold the water gets.
Keep an independent condensation or dew-point protection on every cooled emitter, because a stale sensor or a lost Home Assistant connection leaves the last commanded state in place.

## Shared equipment

Shared equipment is owned by the complete active-consumer set in the model.
That ownership prevents one virtual Zone release from stopping an actuator still needed by another virtual Circuit.

This software rule does not validate hydraulic balancing or manufacturer limits.
An actuator can be logically shared and still be physically unsuitable for the combined load.

Review shared valves, pumps, sources, and interlocks with the person responsible for the physical installation.

## Safe operating rule

For the current release, the safe operating rule is simple:

1. Use a disposable or isolated Home Assistant instance for initial setup.
2. Use synthetic entities for functional tests.
3. Confirm that requests and explanations change while the bound actuator entities do not.
4. Keep physical protection independent.
5. Stop the test if the topology, sensor state, or explanation is unexpected.
6. Report the issue with redacted diagnostics before changing the physical installation.
