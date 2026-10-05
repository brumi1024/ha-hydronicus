# Predictive comfort and solar planning

Status: recovery learning and hourly weather support implemented in the working tree on 2026-10-06; physical commissioning and metered evaluation remain outstanding.
This document records the design, installation assumptions, implemented scope, and remaining evidence requirements.
PV and tariff optimization remain deferred, and no measured energy savings are claimed.

Build a small planning layer above the existing thermostat policy, while the existing controller continues to own hydraulic sequencing and equipment safety.
Start by observing and validating recovery behavior, then allow learned recovery times and weather-aware recovery.
Forecast acquisition can be built alongside learning because reading a forecast does not require authority to change comfort.

## This installation

The owner supplied the following information on 2026-10-06.
These are installation inputs for the plan, not independently inspected wiring or verified live entity capabilities.

| Item | Owner supplied information | Planning consequence |
| --- | --- | --- |
| Heat pump | Midea M-Thermal air-to-water split, outdoor unit `MHA-V16W/D2RN1`, using its own inlet and outlet water-temperature control. | Leave the Hydronicus Source absent; no request switch, zone demand input, or direct heat-pump command is available. |
| Circuit control | Hydronicus opens circuit valves and starts the serving pump; circulation lowers water temperature and the heat pump starts itself after a delay. | Learn the combined circuit-to-room recovery response, including that autonomous delay, without treating pump operation as compressor or heat-delivery proof. |
| Future source integration | Modbus observation or control is planned later. | Do not invent present bindings or require Modbus for circuit learning. |
| Emitters | Underfloor heating, ceiling heating, and bathroom towel radiators. | Expect different delays and residual heat between Zones; learn them separately. |
| Heat-pump electricity | Separate H-tariff supply, with no household PV behind that meter. | Household solar export cannot directly supply this heat pump, so PV-surplus activation is excluded from this installation's roadmap. |
| Household electricity | PV power and energy, and grid import and export, are measured. | These describe the household electrical system, not spare electricity on the heat-pump supply. |
| Heat-pump metering | Separate daily, weekly, and monthly energy totals are available. | These can support longer-period evaluation; instantaneous electrical power remains unconfirmed. |
| Forecasts | `weather.forecast_home` and Solcast PV forecasts are available. | Verify hourly weather support; Solcast is not a heat-pump electricity budget or a direct estimate of room solar gains. |
| Battery | No confirmed usable battery measurements; evcc power and state of charge show zero and capacity is unknown. | Battery presence and policy remain unknown; zero readings do not establish that no battery exists. |

This plan proposes no rewiring, meter changes, assumptions about H-tariff rules, or tariff-based control.
The initial deployment scope is heating.
Cooling support remains a separate commissioning decision for eligible circuits with verified measured condensation protection.
The initial Plant controls valves and pumps only, as shown in the [circuit example](../examples/predictive-circuits.yaml).
Its configured valve-opening wait remains separate from recovery learning, which begins once usable circuit operation is observed.
Later Modbus integration should expose generic Home Assistant entities through the equipment's integration; no brand-specific Modbus driver is part of this work.
Compatible measured water temperatures can then use existing temperature-input bindings, and actual source control can be configured only when an owned request entity exists.
The current Source model requires a request switch and does not accept arbitrary read-only domestic-hot-water, defrost, or operating-state bindings.
Changes to configured sensors, topology, or source equipment context invalidate the affected learned evidence.

## Current foundation

The repository already provides independent heating and cooling targets, Schedule presets, fixed-rate bounded early start, equipment feedback, commissioning diagnostics, and optional fixed or outdoor-compensated supply temperature control.
The relevant boundaries are documented in [development](../development.md#comfort-and-supply-extension-seams).

- [The comfort policy](../../custom_components/hydronicus/core/comfort.py) turns a manual target and schedule observation into an effective target and a next evaluation deadline.
- [The demand policy](../../custom_components/hydronicus/core/demand.py) applies thermostat hysteresis and persists the active early-start event.
- [Supply control](../../custom_components/hydronicus/core/supply.py) calculates a bounded water temperature using current observations.
- [The runtime](../../custom_components/hydronicus/runtime.py) evaluates synchronously, so forecast retrieval must finish outside that evaluation and publish an immutable snapshot.
- [Flow history](../../custom_components/hydronicus/flow_history.py) counts observed or inferred circulation time; it does not measure delivered heat or electrical energy.

The current schedule observation contains only whether the schedule is active and its next transition.
While inactive, that transition can identify the next comfort start.
While active, it identifies the end of the current block, not the following start or a complete day of future blocks.
The implemented recovery planner stays within that known horizon.

The hydraulic simulator checks sequencing, and an independent thermal layer now models room and emitter heat storage, delayed water response, noise, and residual heating.
These tests support recovery and safety checks without claiming to reproduce this home's measured dynamics.
There is no heat-pump electrical model or metered-energy evaluation, so a passing simulation cannot establish lower electricity use.

## Verified Home Assistant contracts

Weather forecasts are separate from entity state and support explicit daily, hourly, or twice-daily capabilities.
Use `weather.get_forecasts` with `type: hourly`; check that the selected entity supports it.
The response is keyed by entity ID and contains forecast points with timestamps and temperatures in the entity's configured `temperature_unit`.
Optional fields can be absent.
Daily highs and lows must not be expanded into invented hourly temperatures.
[Weather entity contract](https://developers.home-assistant.io/docs/core/entity/weather/), [weather action contract](https://www.home-assistant.io/actions/weather.get_forecasts/).

Home Assistant also supports forecast subscriptions.
In the inspected 2026.9.3 source, `WeatherEntity.async_subscribe_forecast` is used by the weather subscription API and accesses an entity instance.
The implemented adapter uses the public action from a bounded asynchronous refresh task, avoiding a dependency on another integration's entity-component internals.
A later subscription adapter is worthwhile only if it simplifies lifecycle handling and remains covered by supported-version tests.
[Weather subscription implementation](https://github.com/home-assistant/core/blob/2026.9.3/homeassistant/components/weather/websocket_api.py).

Forecast.Solar already exposes a public `forecast_solar.get_forecast` action in the inspected Home Assistant 2026.9.3 version.
It returns cached `watts` and `wh_period` maps, accepts a configuration entry and time range, and does not fetch a new forecast from its upstream service.
Its keys include a timezone offset and identify period starts; raw power and interval energy are different quantities.
Prefer interval energy when comparing future production windows, and normalize all timestamps to UTC.
[Forecast.Solar action contract](https://www.home-assistant.io/actions/forecast_solar.get_forecast/), [pinned implementation](https://github.com/home-assistant/core/blob/2026.9.3/homeassistant/components/forecast_solar/services.py).

Forecast.Solar's own integration refreshes hourly without an API key and every 30 minutes with a key.
Hydronicus should consume that integration rather than duplicate cloud credentials, polling, and rate-limit handling.
[Forecast.Solar documentation](https://www.home-assistant.io/integrations/forecast_solar/).

Solcast is an optional later adapter to the existing custom integration's `query_forecast_data` action, not a new direct cloud client.
Its update actions and API quota remain the responsibility of that integration.
Provider data models must be normalized explicitly: Solcast's vendor API uses averaged power with `period_end` and a duration, which differs from Forecast.Solar's action contract.
Check the installed custom integration's response before supporting it; vendor API fields are not a substitute for that check.
[Solcast integration actions](https://github.com/BJReplay/ha-solcast-solar/blob/main/custom_components/solcast_solar/services.yaml), [Solcast interval contract](https://docs.solcast.com.au/docs/section/rooftop-pv-power).

Power in W or kW describes a rate; energy in Wh or kWh describes an amount over time.
PV production, household consumption, grid export, battery power, and hydronic source power are separate observations.
Forecast production alone does not establish available surplus.
[Home Assistant sensor classes](https://developers.home-assistant.io/docs/core/entity/sensor/).

## Research basis

Predictive building control combines a model, forecasts of disturbances such as weather, and explicit comfort and equipment constraints; model mismatch and uncertainty affect its performance.
[Serale et al., 2018, review of predictive control for buildings and HVAC](https://cse.lab.imtlucca.it/~bemporad/publications/papers/energies-mpc-buildings.pdf).
The small empirical recovery learner below is an engineering choice for this repository, not a reproduction of a validated controller from that paper or evidence of savings in this home.

## Recovery design and current limits

### Passive thermal learning

Learn an empirical recovery estimate separately for each Zone and Mode from ordinary operation.
The implemented learner estimates how long a temperature deficit takes to recover after usable circulation is observed, including the combined autonomous heat-pump, water, and emitter delay.
That interval does not measure the compressor's startup timestamp, building thermal resistance, thermal capacity, heat-pump COP, or delivered heat.
An on request, open valve, or running pump alone does not prove that the room is receiving a particular amount of heat.
For the floor and ceiling circuits, compare a constant target and a shallow setback with the current schedule before assuming deeper setbacks or additional early heating are useful.

Keep the configured heating and cooling rates as the fallback.
Learning starts in observation mode and never runs deliberate heating or cooling experiments.
Only an explicit enablement allows an accepted learned estimate to replace the configured rate in bounded schedule recovery.

The sampler starts an episode when usable circulation is first observed, then samples on a controlled cadence and uses report timestamps to distinguish fresh measurements from repeated evaluations.
An active episode tracks its target, initial deficit, Mode, optional measured outdoor temperature, and later room reports; completed records retain recovery timing, outcome, prediction, and rejection reason.
Robust empirical fitting reports confidence, prediction error, and the observed deficit range rather than claiming a calibrated physical model.
Post-stop overshoot and settling are represented in the independent simulator but are not collected as runtime learning metrics yet.
Supply-temperature-conditioned learning and separate source startup measurements also remain future work.

The sampler excludes Dry run, invalid or stale temperatures, open windows, unusable circuit evidence, changed targets, and safety-blocked operation, and censors interrupted episodes.
Early-start recovery before a Schedule becomes active is a valid learning opportunity when its other conditions are valid; do not require the Schedule to already be active.
Domestic-hot-water, defrost, and source fault inputs are not yet bound for this installation, so the learner cannot attribute their delays or exclude them by status.
Only response quality, failures, freshness, and independent prediction checks can qualify the available episodes.
Reject implausible slopes, sensor jumps, insufficient temperature movement, and heating episodes that predominantly cool the room or vice versa.

Diagnostics expose retained episodes, usable independent episode counts, validation error, expiry, current collection reason, and the estimate's fallback reason.
Confidence must require repeated independent episodes, enough temperature movement above sensor resolution, plausible parameters, and acceptable predictions on later episodes that were not used for fitting.
A large sample count by itself is insufficient.

Invalidate or reduce confidence when temperature sensor membership, Loop topology, supply policy, or equipment changes materially.
Age old evidence gradually, retain separate heat and cool histories, and offer a per-Zone reset.
Persist learned state independently of hydraulic timer state so malformed optional learning data cannot discard safety history.

### First learning model

Use a small empirical candidate that predicts a complete recovery episode:

```text
heating_deficit = max(0, target_celsius - start_celsius)
cooling_deficit = max(0, start_celsius - target_celsius)
positive_deficit = the deficit for the current Mode

recovery_seconds = 0 when no actionable deficit remains
recovery_seconds = startup_delay_seconds
                 + 3600 * positive_deficit / effective_rate_celsius_per_hour otherwise
```

The delay must be nonnegative and the rate positive.
Use the existing comfort tolerance to decide whether a deficit is actionable, rather than introducing a competing thermostat threshold.
Fit and update robustly from comparable complete episodes, keeping heating and cooling separate and recording the observed outdoor condition when available.
Do not extrapolate beyond validated deficit and operating-condition ranges.
If the observations cannot distinguish delay from rate, use a rate-only candidate rather than invent a delay estimate.
If either candidate predicts poorly on later episodes, use the configured baseline.
This equation is a provisional engineering model to test against independent delayed thermal dynamics, not an identification of the building's physical resistance or capacity.

Do not train only on successful recoveries.
Retain stalled and missed-target episodes as validation failures that reduce confidence, even when they are unsuitable for fitting the rate.
Record incomplete episodes as censored outcomes with their reasons, including manual intervention, and never count them as successful predictions.
Runtime measurement of residual temperature movement after the target is reached remains a separate overshoot and settling extension.

Collect new quality-tagged telemetry from current observations and their report timestamps.
Do not reconstruct training episodes from existing flow counters or daily, weekly, and monthly electricity summaries.
Start with the smallest bounded sample store that can explain the learned estimate and validate later episodes.

### Weather-aware recovery

First use hourly outdoor temperature to refine the time needed to reach the next scheduled comfort target.
For example, a Zone with repeatably slower recovery in colder weather may begin earlier before the next comfort period, still within the owner's existing maximum early-start duration.
The configured baseline remains available when the forecast or model is unusable.
If weather data fails while the learned baseline remains valid, return to that baseline; if learning confidence is insufficient, use the configured rate directly.
Preserve an already accepted early-start event according to the existing bounded event-latch semantics, including during a forecast outage.
Refreshing an estimate must not repeatedly start, cancel, or relatch the same recovery.
Manual override, a reduced early-start cap, and existing safety conditions remain authoritative.

The first active version changes recovery timing only.
It does not automatically change Plant Mode, add an unrestricted room-temperature offset, or alter the current outdoor-compensated supply curve.
Reducing unnecessary early recovery during a warming period can be considered only when the validated estimate still predicts comfort on time.
It must not delay ordinary thermostat demand simply because a forecast is optimistic.

Forecast humidity and outdoor dew point cannot replace measured room humidity, supply temperature, surface temperature, or condensation contacts.
Cloud coverage is not a calibrated estimate of solar heat entering a particular Zone.
Wind, irradiance, orientation, shading, and indoor solar gains remain later model extensions if simpler recovery prediction demonstrably needs them.

### Solar optimization is deferred for this installation

The separate heat-pump supply makes household PV surplus the wrong input for deciding whether to run the heat pump.
A sunny-hour start could still change comfort or operating conditions, but it must not be justified as consuming this household's otherwise exported PV electricity.
Available Solcast data therefore does not activate any room target, early-start adjustment, or source command in this plan.

Solar gain through windows is a different physical effect from photovoltaic electricity production.
Estimating it would require Zone-specific evidence about glazing, orientation, shading, and observed temperature response.
Do not use PV forecast or cloud percentage as a direct room heat-gain proxy.
Investigate that extension only if recorded prediction residuals show a material pattern that the simpler outdoor-temperature model cannot explain.

For a future installation where source and PV share the relevant electrical connection, solar shifting could become a separate optional feature.
Its eligibility must explicitly verify that electrical topology; entity availability alone is insufficient.
Only then should implementation consider measured net export, start and continuation hysteresis, source self-consumption, a bounded comfort allowance, and battery reserve and discharge protection.
It must distinguish W from Wh, avoid assuming PV production equals spare power, and never command external thermostats, batteries, or EVs.
Measured surplus would precede forecast-PV timing, and both would require their own commissioning and acceptance criteria.

No tariff-specific settings, dependencies, or optimizer should be built now.

## Data and module boundaries

Keep this as a few small modules, not a generic provider framework or a second equipment controller.

| Responsibility | Implemented location | Output |
| --- | --- | --- |
| Asynchronous weather reads, cache, backoff, and lifecycle | New adapter `forecast.py` | Validated immutable forecast snapshot with quality and expiry. |
| Controlled sampling and independent persistence | New adapter `learning.py` | Bounded recovery episode records and model state. |
| Pure update, prediction, and confidence rules | New `core/thermal.py` | Recovery estimate and reason, with uncertainty and a deadline. |
| Schedule, learned recovery, and weather composition | Existing `core/comfort.py` | One effective comfort proposal. |
| Hydraulic safety and output ordering | Existing `core/step.py` and reconciler | Existing desired state and command path. |
| User explanation | Existing view, climate, and diagnostics | The same effective proposal that demand uses. |

Compute the effective comfort proposal once and publish it through the view.
The climate entity and demand calculation must not make separate predictive decisions with different snapshots.
Keep the user's manual heating and cooling targets distinct from the effective target.
Apply one absolute comfort envelope relative to the manual target, not independent additive offsets from different policies.

Each optional proposal needs an origin, mode, effective target or recovery start, validity interval, confidence or quality state, reason, and fallback.
Rejected optional data must never invalidate the baseline Plant or its measured safety observations.
No forecast, learner, or solar module may call an actuator or command an external thermostat.

Forecast snapshots should contain normalized time intervals or points, units, source identity, retrieval time, optional provider issue time, coverage, and an expiry.
Neither public weather nor Forecast.Solar action responses guarantee a provider-issued timestamp.
Re-reading cached data must not be described as a newly issued forecast or reset all freshness checks.
Combine available source-health information, provider metadata, content age, and horizon coverage; if freshness cannot be established sufficiently for an active policy, keep the result advisory.
Weather temperature interpolation and PV energy resampling need distinct rules.
Reject ambiguous local times, malformed values, non-finite numbers, duplicates with conflicting values, unordered intervals, excessive gaps, and unsupported units.

Allow at most one retrieval in flight per selected source, enforce a timeout, cache responses, and use bounded retries with jitter.
Do not retrieve on every thermostat evaluation or force upstream PV refreshes.
Unload, removal, configuration changes, and Home Assistant stop must cancel work and prevent late responses from publishing into an obsolete runtime.
A provider failure falls back for new predictions while preserving any already accepted bounded early-start event as described above; ordinary comfort and safety continue.

## Provisional engineering defaults

These values are starting points for tests and commissioning, not conclusions from published research or guaranteed settings for this home.

| Setting | Proposed starting point | Reason to revisit |
| --- | --- | --- |
| Learning and predictive control | Disabled until explicitly selected; observation mode before active use. | User acceptance and available telemetry. |
| Thermal sampling | Episode start cadence of 5 minutes, report-aware progress, and at most 128 retained episodes per Zone and Mode within 30 days. | Sensor resolution and emitter delay. |
| Model admission | At least 10 independent usable recovery episodes per Zone and Mode across at least 7 days, plus held-out error and coverage checks. | Never pool other Zones to admit an unobserved Zone; count alone does not establish confidence. |
| Forecast planning horizon | Next known comfort start, at most the existing early-start cap. | Full future schedule support is a separate feature. |
| Weather reads | Every 60 minutes plus initial and binding-change refresh, with backoff on failure. | Actual provider update cadence and supported integration behavior. |

Do not silently extend the existing maximum early-start duration because a learner predicts slow recovery.
Report that the configured bound may prevent reaching comfort on time.
Initial model error thresholds must be chosen against actual sensor precision and agreed comfort tolerance, then exercised on withheld episodes before active enablement.

## Implementation status and remaining acceptance

The working tree implements the following scope; automated and synthetic Home Assistant checks remain distinct from physical commissioning.
Every behavior change still requires `make verify`, the appropriate expanded simulator profile, and live Home Assistant checks with synthetic entities before completion.
All 12 [existing invariants](../development.md#invariants) continue to apply.

| Slice | Current implementation | Remaining installation evidence |
| --- | --- | --- |
| Passive learning | Per-zone `off` and `observe`, bounded episode retention, independent persistence, rejection reasons, configuration invalidation, and reset. | Confirm real sensors, reporting cadence, circuit feedback, and representative heating recoveries. |
| Hourly weather | Asynchronous cache, units and content validation, coverage and expiry, retries, lifecycle cancellation, and diagnostics. | Verify the actual provider's hourly support, report freshness, and measured outdoor sensor. |
| Recovery prediction | Separate heat/cool empirical models with prior-outcome validation and independent thermal simulations of delay, noise, residual heat, and missing heat delivery. | Validate predictions against this home's floor, ceiling, and towel-radiator response; runtime overshoot and settling metrics are not implemented. |
| Assisted recovery | Explicit `assist`, confidence and expiry checks, configured-rate fallback, unchanged early-start cap, event latch, manual override, and one shared display/demand proposal. | Commission Observe first and enable assistance only after real prediction and comfort acceptance. |
| Weather-informed recovery | Separate opt-in and weather-conditioned predictions admitted only when comparable history validates their benefit. | Collect representative outdoor conditions and confirm benefit over learned-only timing. |
| Metered evaluation | No electricity ingestion, compressor-start telemetry, savings calculation, or COP calculation added. | Compare reset-aware heat-pump meter periods, comfort, and independently measured cycling when those observations become available. |

PV-surplus control, PV forecast timing, and tariff optimization are not implementation slices for this installation.

Turning off an optional feature returns to the existing configured-rate and thermostat behavior through normal sequencing.
Discarding a model or forecast never resets hydraulic safety timers.
Do not silently re-enable an option after a quality failure or reset the owner's manual override.

## Evidence required before active deployment

The independent thermal simulator exercises slow floors, faster emitters, delayed and residual response, and source-less schedule recovery alongside hydraulic safety checks.
It is separate from the learner's equation, but its simulated outcomes do not commission the physical installation.
Multi-zone interaction, actual autonomous source behavior, uncertain internal gains, and repeatedly wrong forecasts still need representative site evaluation.
Electrical simulation and metered energy comparison remain separate work.

The following are remaining field-evaluation requirements, not a claim that the runtime already collects every metric.
Record comfort error at occupancy start, minutes outside the allowed band, temperature overshoot after operation stops, compressor starts, and optional-plan fallback time.
Compressor starts require an independent operating observation; do not infer their timestamps from valve or pump commands.
Use the separate heat-pump meter for electricity comparisons, with intervals long enough for the available measurements.
Daily, weekly, and monthly totals overlap and must not be added together.
Use reset-aware daily readings for coarse whole-Plant comparisons, never for per-cycle or per-Zone energy allocation.
Do not subtract household PV production from the separate heat-pump meter's consumption.
Household solar self-consumption is not an objective for this heat pump on its separate supply.
Do not report energy savings from pump runtime or on/off duty alone, and do not claim COP without trustworthy heat-output and electrical-input measurements.

Compare candidate behavior with the current controller on identical simulated weather and load traces.
For live evaluation, begin in observation mode and use matched operating periods where possible; ordinary before/after totals are confounded by weather and occupancy.
Promote an active policy only if it improves the chosen objective without unacceptable comfort degradation or additional cycling.
Return that policy to advisory mode if prediction error, overshoot, cycling, or sensor quality exceeds its acceptance bounds.

## Installation details to confirm

Planning can proceed with generic entity bindings, but active settings require the following information.

- Does `weather.forecast_home` support hourly forecasts, which measured outdoor sensor is available, and how fresh are those observations?
- Which Zones combine underfloor, ceiling, and towel-radiator emitters, and what arrival error and temperature overshoot are acceptable in each Mode?
- Are source running, supply temperature, domestic-hot-water status, and defrost status available and reliable?
- Can the separate heat-pump meter expose instantaneous power or cumulative energy with a useful reporting cadence, in addition to its daily, weekly, and monthly summaries?
- Which circuits are actually used for cooling, and what measured condensation observations protect them?
- Which schedule transitions and recovery periods are representative enough for the initial observation period?

The next installation step is observation and validation of the implemented recovery learning with the actual circuit controls.
Assisted and weather-informed recovery remain opt-in and await representative physical evidence even though their bounded policies are implemented.
The separate electrical supplies remove PV optimization from this installation's active roadmap, and tariff work does not block that progression.

## Key references

- [Home Assistant weather forecast action](https://www.home-assistant.io/actions/weather.get_forecasts/): supported request and response contract.
- [Home Assistant Forecast.Solar action](https://www.home-assistant.io/actions/forecast_solar.get_forecast/): cached PV forecast contract for possible future electrically eligible installations.
- [Serale et al., predictive control for buildings and HVAC, 2018](https://cse.lab.imtlucca.it/~bemporad/publications/papers/energies-mpc-buildings.pdf): model, disturbance, constraint, and uncertainty considerations.
