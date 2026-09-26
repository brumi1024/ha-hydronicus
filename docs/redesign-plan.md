# Redesign plan

This plan rebuilds the Hydronicus control core, storage, setup, and entity surface around a model that fits heat pump plants.
It is the single source of truth for decisions, contracts, invariants, and phases.
The lead runs the phases in order and may dispatch a phase to a subagent with the [subagent brief](#subagent-brief).

## Evidence

Investigated on 2026-09-25 against Home Assistant 2026.9.3 and Hydronicus `main` at `a252557` (v0.1.0 plus #39 and #40).
The maintainer asked for an architectural review with full freedom to redesign, and no installation runs Hydronicus with Dry run off.

### Goals of this version

- Put hydraulic loops together from zones, where a zone is built from one Home Assistant area, several areas, or from scratch.
- Control valves and pumps correctly.
- Adopt an existing thermostat as a zone's thermostat, or create a digital one.
- Leave clean seams for the roadmap: heat pump control through Modbus entities, weather compensation, intelligent targets, and forecast-based flow temperature.

### The maintainer's plant

The maintainer's home is the reference installation, and v0.1.0 cannot model it.

- The source is a Midea air-to-water monoblock with R410a.
  A Shelly Modbus module will expose it to Home Assistant in a later iteration, through an integration that is not chosen yet.
  Until then, a spare Shelly relay channel could drive its heat request input.
- A hydraulic separator (low-loss header) divides the heat pump's primary circuit from the house's secondary circuits.
  There is no buffer tank or bypass valve today; one will be added later.
- Three zones cover Home Assistant areas: basement, bedroom area, and living area.
- Each zone has a ceiling heating and cooling loop with one zone valve and no pump that Home Assistant switches.
  The ceiling loops sit on the secondary side of the separator, behind a pump the heat pump controls.
- The living area also has an underfloor loop with its own valve and its own pump, a mixing valve, its own supply temperature sensor, and a high limit.
- A bathroom towel dryer circuit has a pump and no valve, and may run whenever the heat pump heats.
  No chilled water passes through it while its pump is off.
- Every valve and pump is a channel of a Shelly Pro 4PM with power metering.
- No physical room thermostats exist, so every zone needs a digital thermostat.
- A supply temperature sensor for the ceiling circuit will be added; until then ceiling cooling has no condensation reference.
- Whether the Midea keeps its own heating curve or Hydronicus sets the flow temperature is decided in iteration 2.

### What blocks that plant in v0.1.0

- Every loop needs at least one valve (`core/topology.py` rejects `not circuit.valve_ids`) and a pump that Hydronicus switches (`core/plant_document.py`: "A loop needs a pump.").
  The ceiling loops would need a fake pump entity, and the towel dryer cannot be expressed.
- Direct source demand is only requested while heating (`_source_demand_permit` in `core/controller.py`), so a heat pump can never be asked for cooling.
- The source guard requires a running Hydronicus-switched pump, which cannot exist when the only pump on the path belongs to the source.

### Control defects reproduced in v0.1.0

Each defect was reproduced with a script against the pure core or with an integration test, and each becomes a regression scenario in [R2](#r2-simulator-invariants-and-regression-scenarios).

1. **Safe shutdown with two pumps leaves one running against closed valves.**
   When one pump finishes its overrun while another still overruns, `safe_shutdown` returns before the pump plan's commands are added, and `_plan_shutdown_pumps` has already recorded the first pump as off.
   Its turn off is never sent, the valves then close, and Dry run switches on, so nothing stops it.
2. **A rejected pump turn off still closes the valve and is never retried.**
   The executor runs with `stop_on_failure=False`, so the valve close in the same plan is dispatched.
   The executor then suppresses the same command as `FAILED`, and the adapter re-seeds the pump as running, which loops overrun and a suppressed turn off forever.
3. **A failed valve open drops later pump turn offs.**
   The adapter adds the pumps of a loop whose valve failed to `unavailable_actuator_ids`, and the executor skips every command for them, including turn off.
4. **The heat request stays latched after the pump path is lost.**
   `_advance_active_source` never re-checks the demand permit, so after a pump fault the heat request stays on with no flow while diagnostics say it is not permitted.
5. **The degraded-loop filter is bypassed.**
   `_coordinate_mode_routing` recomputes routes from zone demand and ignores the result of `_filter_degraded_routes`, so a loop reported as blocked still opens its valve and starts its pump.
6. **A chilled-water pump overruns after a condensation block while another zone heats.**
   `_plan_pumps` keys the no-overrun rule for cooling on the global plant mode, which is heating when both modes run on separate equipment.
7. **A reload cycles a running pump.**
   `_reconcile_actuator_runtime` re-seeds every valve observed on as opening from now, so with 180 second actuators and a 60 second overrun a plain reload switched the pump off at 90 seconds and on again at 180 seconds.
   Reloads come from restarts, manual reloads, and every change to a covered area's sensor.
8. **Any zone edit disarms the whole Plant.**
   `output_authorization` fingerprints the whole topology and `_finalized` calls `invalidate_output_authorization` on every edit, so changing a preset target runs a whole-plant safe shutdown and heating stays off until someone confirms Dry run off again.

Defects 1 to 6 share a root cause.
The controller emits commands only on state transitions, the adapter patches observed state back into controller state, safe shutdown is a second sequencing path, and heating and cooling run on duplicated paths.

### Size and shape

- Production Python is about 21,000 lines: the core is 8,200 and the adapter 13,100.
- About 31 percent of `core/controller.py` is source recommendation and selection, which the runtime forces into Dry run and the reference plant does not need.
- About 15 percent is per-equipment heat and cool arbitration and changeover, which contains defects 5 and 6.
- Delivery Routes, Route Arbitration, and Any Demand are about 16 lines of code behind four glossary terms.
- Zone ownership is stored in six places: the topology records, `subentry_objects`, `zone_objects`, the subentries, `config_subentry_id` on entities, and the device registry.
- The reference plant would get about 60 entities, of which about 15 are useful.
- The bundled card needs about 1,600 lines of Python (`presentation.py`, `websocket.py`, `frontend.py`) and 5,300 lines of TypeScript with its own CI job.
- The maintainer's ha-config repository already has its own card library with pixel-diff tests, which is where the home dashboard's heating page belongs.

### Practice and prior art

- Installers prefer weather compensation with mostly open loops for heat pumps with underfloor or ceiling emitters; aggressive on and off zoning short-cycles the compressor.
- Thermal actuators take roughly 2 to 5 minutes to open, and pumps commonly overrun about 3 minutes after the last demand.
- Manufacturers correct the heating curve with a slow room-temperature trim rather than letting room thermostats drive the source directly.
- Cooling through floors and ceilings keeps the flow temperature above the room dew point plus a margin.
- Per-room projects such as Better Thermostat and Advanced Heating Control leave the plant to the user, and flow-temperature projects such as SAT, adaptive-heating, and heating_curve_optimizer leave the rooms to the user; Versatile Thermostat's central boiler and multizone-thermostat come closest to both.
- Home Assistant offers no heat pump entity type, so a plant integration owns its model and meets devices through `switch`, `select`, `number`, `sensor`, and `climate` entities.
- Some Modbus heat pump integrations limit and deduplicate setpoint writes, because controller memory tolerates a limited number of writes.

## Outcome

- The reference plant is described without fake entities: loops without a switched pump, loops without a valve, a heat pump that heats and cools, and a hydraulic separator.
- Control is one pure evaluation that returns the desired state of every output, and a level-triggered reconciler drives the outputs to it, retrying until it observes the result.
- The reproduced defects are regression scenarios, and a simulator checks the invariants on simulated physical state over random plants and event traces.
- A reload or restart with unchanged observations changes no output.
- A zone lives in its own subentry, so removing it is closed by construction, and the plant file uses the same schema as storage.
- Editing a thermostat, a sensor, or a name never disarms the Plant.
- The integration publishes a small, stable entity contract and no bundled card.
- The heat source has a slot for a flow setpoint strategy that iteration 2 fills.

## Terminology

| Term | Meaning |
| --- | --- |
| Plant | One config entry: an optional source, its pumps, its zones, and its plant loops. |
| Source | The generator Hydronicus asks for heat or cooling, such as a heat pump; at most one per Plant. |
| Pump | A circulator that Hydronicus switches, or that the source drives and Hydronicus never commands. |
| Loop | A flow path: zero or more valves that open together, and exactly one pump. |
| Zone | The space one thermostat controls; it covers zero or more Home Assistant areas, owns its loops, and is one `zone` subentry. |
| Plant loop | A loop no zone owns, which runs with the source or with a set of zones. |
| Area | A Home Assistant area, usually one physical room, that a zone covers. |
| Mode | Plant-wide: off, heat, or cool. |
| Demand | A zone's request in the current mode, with an on or off decision and a level from 0 to 1. |
| Min-flow path | The loops held open so that a pump without guaranteed flow always has a path while it may run. |
| Desired state | What every output should be now, computed by each evaluation. |
| Armed output | An output entity the owner has confirmed Hydronicus may command. |
| Separator | A hydraulic separator, low-loss header, buffer, or bypass that gives a pump a path whatever the loops do. |

Delivery Route, Hydraulic Circuit, Route Arbitration, Any Demand, Plant equipment, shared valve, source selector, and deletion-closed ownership leave the vocabulary.

## Decisions

These are settled; implement them rather than revisiting them.
They supersede the conflicting decisions of `docs/setup-redesign-plan.md` and `docs/zones-and-areas-plan.md`, which stay as history.

1. **Rewrite, do not migrate.** The config entry moves to version 5.0; an older entry is refused with a log message saying it must be set up again, as version 4.0 did.
   Entity unique IDs derive from the Plant ID and object slugs, so a Plant rebuilt from its plant file gets the same entity IDs.
2. **One pure step, one reconciler.** `step()` computes the desired state of every output from configuration, observations, and persisted state.
   A level-triggered reconciler compares desired and observed state on every evaluation and sends what differs, in dependency order, until the observation matches.
   A service call that returns without error is not a confirmation; only an observation is.
3. **A loop has zero or more valves and exactly one pump.** The pump is either switched by Hydronicus or driven by the source.
   A loop with no valve is valid, and its pump is its only control.
   An output entity appears in at most one role in one Plant: a valve entity is never shared by two loops, and a pump entity is never also a valve or a source output.
4. **The source is optional, first-class, and reached only through generic entities.** It has a request switch, an optional mode select, and later a flow setpoint number.
   Hydronicus never speaks Modbus; whichever integration exposes the Shelly Modbus module provides the entities.
   A Plant without a source still opens valves and runs switched pumps, which suits a boiler with its own controls.
5. **Source strategies.** `request` asks for heat or cooling and lets the source choose its flow temperature from its own curve; it ships now.
   `setpoint` also writes a flow setpoint number; its stage exists in `step()` from the start and returns nothing until [iteration 2](#roadmap-hooks).
6. **Minimum flow is a property of each pump.** `min_flow: guaranteed` means a separator, buffer, or bypass gives the pump a path whatever the loops do.
   `min_flow: path` means the pump needs an open loop while it runs.
   A switched pump with `path` simply never runs without a ready loop.
   A source-driven pump with `path` must name `min_flow_loops`, which Hydronicus holds open whenever no other loop of that pump is ready while the pump may run: while the source is requested, during its post-run, and while the pump is observed running.
   In cooling, a min-flow path may carry chilled water during the source's post-run even when its condensation guard blocks, which a `guaranteed` pump avoids.
   Adding a buffer later is a one-line change to `guaranteed`.
7. **Plant mode is off, heat, or cool, chosen by a select.** There is no automatic mode in this version; an automation can set the select, and automatic season selection returns with weather compensation.
   A change of mode is sequenced: the old mode's source is released, its pumps finish overrun or post-run, its loops close, and the minimum mode dwell has passed before the new mode starts.
   Heating and cooling never run at the same time.
8. **Demand has a level.** A digital thermostat decides on or off with its hysteresis and minimum durations as today, and also reports a level from 0 to 1 from the distance to target over a proportional band.
   An external thermostat's demand comes only from its `hvac_action`, with a level of 1 or 0.
   Nothing consumes the level in this version except the entities; it is the seam for proportional valves and the flow setpoint.
9. **Zone thermostats keep today's ownership.** A digital thermostat is a Hydronicus climate entity with restored target, preset, and mode; an external thermostat is read only and never commanded.
   A zone's thermostat mode counts only when it matches the Plant mode, and a mismatch is reported as the zone's reason.
10. **Cooling is guarded per loop.** A loop may cool only when a condensation reference exists: its pump's supply temperature sensor or the loop's own surface sensor.
    The guard blocks below the worst-case dew point plus the margin and releases only 1 K above that, after a minimum blocked time.
    Pumps have no overrun in cooling, and a loop without a reference is heat only and validates as such.
11. **Aggregation is mean, minimum, or maximum.** Each sensor, explicit or from an area, has `required` and `max_age_seconds`.
    Weights, calibration offsets, the designated reference, the median, and the weighted mean are removed; calibrate a sensor at its source.
    The worst-case dew point from #39 stays exactly as it is.
12. **Areas are resolved on every evaluation.** The runtime re-reads each covered area's temperature and humidity sensor and re-subscribes to state changes when the area or entity registry changes, instead of reloading the Plant.
    The self-feed guard and the area Repairs from #40 stay.
13. **Storage matches the plant file.** Plant-level data (name, source, pumps, plant loops, settings) lives in the config entry's data and is edited through the entry's reconfigure flow.
    Each zone's complete record, including its loops and valves, lives in its subentry's data and is edited through the subentry's reconfigure flow.
    Zones reference only Plant-level pumps and the source, so removing a zone subentry removes exactly its objects.
    Reconfigure refuses to remove a pump that a zone loop still uses.
14. **The plant file is the storage schema.** Format number 2 is the entry data plus a `zones` mapping of the subentry data.
    It is used for import on setup, export through the `hydronicus.export_plant` action and Plant settings, and a whole-Plant replace in reconfigure.
    Replace creates, updates, and removes zone subentries by slug and shows a summary of added, removed, and changed zones and outputs, not a field diff.
15. **Arming is per output.** The owner confirms output entities, and a loop runs only when every output it needs is armed.
    A switch, **Control equipment**, turns control on for the armed outputs; turning it off runs the off-mode sequence and then observes only.
    A new output, such as a new zone's valve, gets a Repair with a fix flow that confirms it, and the rest of the Plant keeps running meanwhile.
    Editing a thermostat, a sensor, a name, or a timing never changes arming.
16. **Failures are retried and surfaced.** The reconciler retries an unmet output with backoff from 10 seconds to 5 minutes, and raises a Repair naming the entity after three failed attempts.
    A pump whose stop is not observed keeps its last path open, and a valve whose open is not observed keeps its loop out of the ready set.
17. **State survives reloads.** Actuator timers, zone demand timers, the mode and its changeover, and reconciler retry state are persisted with `homeassistant.helpers.storage.Store` and restored before the first evaluation.
    The first evaluation runs only after every zone thermostat has restored.
18. **An output belongs to one Plant.** A form or a plant file that binds an entity another Plant already binds is refused, which replaces the multi-Plant output arbitration.
19. **Deleted features.** Source recommendation, source selection and the selector, per-equipment mode arbitration, independent simultaneous heating and cooling, shared valves, Delivery Routes, per-actuator entities, and the periodic reconciliation counters are removed.
    A loop that several zones use is a plant loop that runs with those zones.
20. **No bundled card.** `presentation.py`, `websocket.py`, `frontend.py`, `frontend/`, the theming contract, and `docs/lovelace.md` are removed.
    The entity contract in [K7](#k7-entities) is the interface for dashboards, and the maintainer's heating page is built in ha-config as its own follow-up.

## Invariants

The simulator in [K9](#k9-simulator) checks every invariant on simulated physical state, not on controller belief, for random plants and random event traces.
A trace may delay, reject, or time out any command, restart the runtime, jump the clock, and make a sensor stale or an entity unavailable.
Only a spontaneous physical change, such as a valve closing by itself, is exempt, and the controller must react to it within one evaluation.

1. Dry run and an unarmed output receive zero service calls.
2. A pump with `min_flow: path` never runs without an open path, where a loop with no valve is always an open path.
3. The source is requested only while at least one loop of the current mode is ready and, when its pump is switched, that pump is observed running.
4. A source-driven pump with `min_flow: path` has an open path while the source is requested, during its post-run, and while it is observed running.
5. Heating loops and cooling loops never flow at the same time, and a mode change waits for the dwell and for the old mode's loops to stop.
6. A cooling loop flows only while its condensation guard permits, except a min-flow path during the source's post-run ([decision 6](#decisions)).
7. Every difference between desired and observed state is eventually observed resolved or reported as a Repair.
8. With unchanged observations, the first evaluation after a reload or restart sends no command.
9. Removing a zone leaves a valid Plant, and every zone removal path goes through the same validation as setup.
10. `custom_components/hydronicus/core/` has no Home Assistant imports and at least 90 percent coverage, and the whole package passes mypy.
11. Round-trip: exporting a Plant and importing the file reproduces the Plant, its object IDs, and its entity IDs.
12. `make verify` is the gate.

## Working rules

- A behaviour change starts red: first a test that fails on the old behaviour or a missing capability, then the change that turns it green.
- Read a Home Assistant API in `.venv/lib/python3.14/site-packages/homeassistant/` before relying on it.
- Edit `strings.json`, then copy it to `translations/en.json` byte for byte.
- Prose uses plain dashes, never em dashes, and long Markdown puts each full sentence on its own physical line.
- Commit messages use the repository prefixes (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`) and carry no agent attribution or co-author lines.
- `CHANGELOG.md`, `RELEASE_NOTES.md`, version numbers, and generated files stay untouched.
- Fix or explicitly report lint failures, test failures, and flaky tests, even when unrelated.
- Delete replaced code in the same phase that replaces it; do not leave compatibility shims.

## Contracts

### K1 Plant file and storage

The reference plant, which the phases use as their end-to-end fixture:

```yaml
hydronicus: 2
id: 7c9e6679-7425-40de-944b-e07fc1f90ae7   # optional; keeps entity IDs on import
name: Home
mode_dwell: 3600
source:
  name: Heat pump
  strategy: request
  request: switch.heat_pump_heat_request                           # hypothetical entity
  mode: {entity: select.heat_pump_mode, heat: Heat, cool: Cool}   # optional, hypothetical
  post_run: 180
  min_on: 600
  min_off: 600
pumps:
  heat_pump:
    driven_by: source
    min_flow: path                 # secondary side of the separator (O2)
    min_flow_loops: [living_area.ceiling]   # O1
    supply_temperature: sensor.ceiling_supply_temperature   # added later
  floor:
    switch: switch.home_underfloor_heating_pump
    overrun: 180
  towel_dryer:
    switch: switch.home_bathrooms_towel_dryer_pump
    overrun: 120
loops:
  towel_dryer:
    pump: towel_dryer
    runs: with_source
    modes: [heat]
zones:
  basement:
    areas: [basement, workshop]
    thermostat: {digital: {presets: {comfort: 21, eco: 19, away: 16}}}
    loops:
      ceiling:
        valves: [switch.home_basement_ceiling_heating_valve]
        pump: heat_pump
        modes: [heat, cool]
  bedroom_area:
    areas: [main_bedroom, lilla_bedroom]
    loops:
      ceiling:
        valves: [switch.home_bedroom_area_ceiling_heating_valve]
        pump: heat_pump
        modes: [heat, cool]
  living_area:
    areas: [living_room, dining_room, kitchen, hallway]
    loops:
      ceiling:
        valves: [switch.home_living_area_ceiling_heating_valve]
        pump: heat_pump
        modes: [heat, cool]
      floor:
        valves: [switch.home_living_area_floor_heating_valve]
        pump: floor
        modes: [heat]
```

The area lists are illustrative; the maintainer chooses them during setup.

- Keys under `pumps`, `loops`, and `zones`, and each zone's `loops`, are slugs.
  A slug is chosen at creation, never changes, and forms unique IDs with the Plant `id`; names are separate and editable.
- A cross-zone reference is written `<zone>.<loop>` and is allowed only in `min_flow_loops`.
- `thermostat` is `{digital: {...}}` or `{external: climate.x}`; a missing thermostat means a digital one with defaults.
- `runs` on a plant loop is `with_source` or `{with_zones: [...]}`.
- `modes` defaults to `[heat]`; `cool` needs a condensation reference ([decision 10](#decisions)).
- A valve is an entity ID or `{entity, opening_time, readiness}`; `opening_time` defaults to 180 seconds, and `readiness` names a binary sensor that confirms the valve is open.
- `min_flow` defaults to `path`, `overrun` to 180 seconds, and a loop with no valve is always an open path.
- A zone's extra sensors are `temperature: [...]` and `humidity: [...]`, each an entity ID or `{entity, required, max_age}`, and `aggregation` is `mean`, `min`, or `max`.
- Unknown keys are errors with a path such as `zones.living_area.loops.floor.pump`.
- The config entry's data holds everything except `zones`, and each zone subentry's data holds that zone's mapping plus its slug; the subentry title is the zone name and its unique ID is the slug.
  Home Assistant stores config entries with sorted keys, so storage lists `pumps`, `loops`, and each zone's `loops` as objects that carry their slug, which keeps their order.

### K2 Core types

```python
@dataclass(frozen=True, slots=True)
class Pump:
    slug: str
    switch: str | None          # None when driven by the source
    overrun: float = 180.0
    min_flow: MinFlow = MinFlow.PATH
    min_flow_loops: tuple[LoopRef, ...] = ()
    supply_temperature: str | None = None

@dataclass(frozen=True, slots=True)
class Loop:
    ref: LoopRef                # (zone slug or None, loop slug)
    valves: tuple[Valve, ...]
    pump: str
    modes: frozenset[Mode]
    runs: LoopRun               # zone, with_source, or with_zones
    surface_temperature: str | None = None

@dataclass(frozen=True, slots=True)
class Desired:
    outputs: Mapping[str, OutputTarget]   # entity ID -> on, off, option, or value
    source_request: bool
    mode: Mode
    flow_setpoint: float | None           # always None until iteration 2
    reasons: Mapping[str, str]            # per zone, loop, and output
```

`Plant`, `Zone`, `Source`, `Valve`, and the observation and state types follow the same style.
`step(plant, observations, state, now) -> tuple[State, Desired, float | None]` returns the next state, the desired state, and the seconds until the next evaluation is due.

### K3 The step pipeline

1. **Observe.** Normalize sensors, thermostats, and output feedback; mark stale and unavailable inputs.
2. **Demand.** Aggregate each zone's temperature and humidity, evaluate its thermostat, and produce on or off plus a level; fail closed.
3. **Mode.** Apply the requested mode with its sequenced changeover and dwell.
4. **Wanted loops.** A zone loop is wanted when its zone demands in the current mode and the loop supports the mode, and a plant loop is wanted per its `runs`, where `with_source` follows the source request of the previous evaluation; a loop is dropped when an output it needs is unarmed or unavailable, or when its condensation guard blocks.
5. **Readiness.** From observations only: a loop is ready when every valve is observed open for its opening time or its readiness sensor is on, and a loop with no valve is ready at once.
6. **Min flow.** For every source-driven `path` pump that may run, keep its `min_flow_loops` wanted until another of its loops is ready, and release them only after that.
7. **Valves.** Desired open for every valve of a wanted loop, and held open for every loop whose pump is still running or in post-run and would otherwise lose its last path.
8. **Pumps.** A switched pump is desired on when one of its loops is ready, stays on through its heating overrun, and is off otherwise; a `path` pump is never desired on without a ready loop.
9. **Source.** The request is on when a loop of the current mode is ready, its switched pump if any is observed running, and the anti-short-cycle timers allow it; the mode select follows the Plant mode.
10. **Setpoint.** The `setpoint` strategy's stage; empty in this version.
11. **Timers.** Advance valve, pump, source, demand, guard, and mode timers, and compute the next due time.

Safe shutdown is `step()` with the Plant mode forced to off, and it uses the same pipeline.

### K4 Reconciler

- Input: `Desired`, the observed state of every output, and the reconciler's retry state.
- Output: the ordered actions to send now, and the next retry time.
- Order when starting: valves open, then pumps on, then the source mode and request.
- Order when stopping: source request off, then pumps off, then valves close, and a valve that is some running pump's last open path waits until that pump is observed off.
- An action is re-sent when its target is still unmet after its backoff, and the backoff doubles from 10 seconds to 5 minutes.
- In Dry run the reconciler records each action as proposed and treats it as observed once, so the virtual sequence advances exactly as it would live.
- Actions run outside the runtime lock with a per-call timeout, and the result is only ever confirmed by the next observation.

### K5 Runtime

- One state listener covers every observed entity, area sensors included, and is rebuilt when the area or entity registry changes a covered area.
- Evaluations are coalesced; each one snapshots, calls `step()`, calls the reconciler, dispatches, persists changed state, publishes changed entities, and schedules the next due time.
- Setup restores persisted state and the thermostats before the first evaluation, and unload and reload never send a command.
- Diagnostics use `async_redact_data` over the configuration, the last observations, the desired state, and the reconciler state.

### K6 Arming

- `entry.options["armed_outputs"]` lists confirmed output entity IDs; `entry.options["control"]` is the **Control equipment** state.
- A new Plant starts with nothing armed and control off.
- The Plant settings step **Arm outputs** lists every output with its role and asks for confirmation; the Repair for new outputs opens the same step for the new ones only.
- Removing an output disarms it silently; replacing a valve's entity makes the new entity a new output.

### K7 Entities

| Object | Entities |
| --- | --- |
| Plant | `select` mode (off, heat, cool); `switch` Control equipment; `sensor` status (off, idle, heating, cooling, changing over, degraded) with attributes for active loops, blocked zones and reasons, unarmed outputs, and the source request |
| Zone | `climate` for a digital thermostat; `binary_sensor` heating demand with a `level` attribute; `binary_sensor` cooling demand where a loop of the zone cools; `sensor` combined temperature with the area breakdown as attributes; `sensor` dew point where the zone cools |
| Loop | `binary_sensor` flowing, with valve and pump states as attributes |
| Source | `binary_sensor` requested; `sensor` flow setpoint from iteration 2 |

Output faults, missing bindings, and unconfirmed outputs are Repairs, not entities.
The reference plant gets about 25 entities.

### K8 Flows

- **Config flow:** name and source (optional), then pumps, then "How is your home zoned?" as in #40, then one zone form per zone with **Add another loop** and **Add another zone**, then a review whose warnings never block, or import a plant file.
- **Zone subentry:** add and reconfigure one zone, with its areas, extra sensors, thermostat, and loops.
- **Entry reconfigure:** name, source, pumps, plant loops, mode dwell, and replace from a plant file.
- **Plant settings (options):** arm outputs, show the plant file.
- **Repairs:** missing area, zone without a temperature source, area self-feed, missing binding, output not responding, outputs awaiting confirmation.

### K9 Simulator

A pure test harness under `tests/sim/` that owns physical state: each valve follows its commands after its travel time, each pump runs when switched and its source-driven pumps run while the source runs or post-runs, commands can be delayed, rejected, or time out, and sensors drift, go stale, and come back.
Hypothesis generates plants (1 to 4 pumps with both kinds, 1 to 6 loops with 0 to 3 valves, 1 to 4 zones, an optional source) and traces, runs `step()` and the reconciler over the simulated plant, and asserts every [invariant](#invariants) after every event.
The reference plant and each reproduced defect are named scenarios in the same harness.

## Code fate

| Keep and adapt | Rewrite | Delete |
| --- | --- | --- |
| Aggregation, dew point, and condensation margin from `core/controller.py` | `core/model.py` | `presentation.py`, `websocket.py`, `frontend.py`, `frontend/` |
| Digital thermostat timing (`_apply_zone_timing`) and external thermostat normalization | `core/controller.py` into `core/step.py` | Source selection and recommendation, the selector |
| `areas.py`, `zone_area.py`, and the area Repairs | `core/executor.py` into `core/reconcile.py` | `output_ownership.py`, `core/ownership.py` |
| `climate.py` restore of the exact Celsius target | `core/topology.py`, `core/configuration.py`, `core/plant_document.py` into `core/plant_file.py` | Per-actuator entities and the reconciliation counters |
| The `hydronicus.export_plant` action | `runtime.py`, `entry_configuration.py`, `flows/`, entity platforms, `repairs.py`, `diagnostics.py` | `docs/lovelace.md`, the theming contract, the card CI job |

## Phases

### R1 Model and plant file

K1 and K2, with validation and round-trip tests for the reference plant, the trial kit, and every rejection path.
Update `CONTEXT.md` to the [terminology](#terminology).
Commit: `refactor: describe a Plant as a source, pumps, zones, and loops`.
Done when the reference plant imports and exports byte-stable, loops without a valve or without a switched pump validate, and the old model modules are gone.

### R2 Simulator, invariants, and regression scenarios

K9, with the invariants as properties and the eight reproduced defects and the reference plant as named scenarios, all red against a stub `step()`.
Commit: `test: simulate plants and check control invariants`.
Done when the harness runs in under a minute in CI and each scenario fails for the stated reason.

### R3 Step and reconciler

K3 and K4 until R2 is green, with the aggregation and thermostat code carried over.
Commit: `feat: control outputs by reconciling a desired state`.
Done when every invariant and scenario passes, `core/` coverage is at least 90 percent, and the core is under about 2,500 lines.

### R4 Runtime, persistence, arming, and entities

K5, K6, and K7, with integration tests for command-free reload with slow actuators, restore-before-evaluate, per-output arming, and live area changes without reload.
Commit: `feat: run the Plant from persisted state and publish the entity contract`.

### R5 Flows and Repairs

K8, with flow tests for every zoning answer, a zone with two loops, a loop with no valve, a source-driven pump, a plant loop, replace from a plant file, and each Repair.
Commit: `feat: set up a Plant with sources, pumps, and zone loops`.

### R6 Removal and documentation

Remove the card and the other deleted code, rewrite README, `docs/how-it-works.md`, `docs/configuration.md`, `docs/plant-file.md`, `docs/safety.md`, `docs/troubleshooting.md`, and the trial kit, and add the reference plant as an example.
Commit: `docs: describe the redesigned Plant`.

### R7 End to end

Run a live Home Assistant with synthetic entities shaped like the reference plant, set it up through guided setup and through the plant file, exercise heating, cooling, a mode change, a failed pump stop, a reload with 180 second actuators, and a new zone's arming, and check the UI closely.
Report findings as fixes or follow-ups; no commit is required if nothing changes.

## Subagent brief

```text
You are implementing phase <ID> of the Hydronicus redesign plan.
Work in <path> on branch <branch>, and run `make bootstrap` first if the environment is missing.
Read docs/redesign-plan.md: Evidence, Terminology, Decisions, Invariants, Working rules, the contracts your phase names, and your phase.
Also read CONTEXT.md and the "Architecture boundaries" section of docs/development.md.
Work red then green.
You are done when your phase's done criteria hold and `make verify` passes.
Commit once, with the commit message your phase names.
Report: each done criterion with its evidence; deviations from the contracts and why; lint, test, or flakiness problems you saw, related or not; anything unverified.
```

## Roadmap hooks

- **Heat pump over Modbus.** A source with a mode select and a flow setpoint number from whichever integration exposes the Shelly Modbus module; register maps from the community are unverified, so confirm them on the unit first.
- **Weather compensation.** A curve from outdoor temperature in the `setpoint` stage, with a slow room-influence trim from zone demand levels, and writes that change the number only by at least 0.5 K and at most every 10 minutes, with a daily cap.
- **Cooling setpoint.** The same stage keeps the cooling flow temperature above the worst-case dew point plus the margin, so cooling continues instead of blocking.
- **Automatic season.** Mode selection from outdoor temperature with dwell, replacing the manual select as the default.
- **Forecast.** An offset to the curve from forecast temperature and price, or an external optimizer writing a target that the stage respects.
- **Room valves inside a zone and proportional or pulse-width valves** use the demand level.
- **Domestic hot water priority** as a source observation that pauses space heating without counting as a fault.

## Plant decisions

The maintainer answered these on 2026-09-26.

- **O1 Min-flow loops.** The living area's ceiling loop keeps the heat pump's circulation path open while no zone calls, as `min_flow_loops: [living_area.ceiling]`.
  It is the largest zone and the one most likely to be calling anyway; any other ceiling loop works the same way.
- **O2 Ceiling hydraulics.** The ceiling loops sit on the secondary side of the separator, behind a pump the heat pump controls.
  That pump is `driven_by: source` with `min_flow: path`, so it needs O1; it becomes `guaranteed` only if a buffer or bypass later protects it.
- **O3 Flow temperature ownership.** Still open: whether the Midea keeps its curve (`request`) or Hydronicus writes the setpoint (`setpoint`) is decided in iteration 2 once the register map is known.
  Until then the source uses `request`.
- **O4 Towel dryer in cooling.** No chilled water passes through the towel dryer branch while its pump is off, so it does not block ceiling cooling.
  Ceiling cooling still waits for the ceiling supply temperature sensor, its condensation reference.
- **O5 Floor loop mixing.** The underfloor loop has a mixing valve, its own supply temperature sensor, and a high limit, so it can share the heat pump's flow temperature.
  A flow setpoint from iteration 2 therefore serves the ceiling loops, and the floor loop mixes down from it.

## Out of scope

- Several sources in one Plant, and choosing between them.
- A valve shared by loops of different zones.
- A bundled Lovelace card; the ha-config heating page is planned in that repository.
