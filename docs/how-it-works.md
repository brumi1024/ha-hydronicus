# How Hydronicus works

Hydronicus turns a Home Assistant configuration into an explicit hydronic Plant model.
It observes sensors, calculates demand, coordinates shared hydraulic paths, and publishes every decision back to Home Assistant.

Every new Plant starts in Dry run.
The Plant UI exposes one setting that can turn Dry run off for valves and pumps, in heating and cooling, and for an explicitly configured direct source-demand output.
Automatic source selection remains Dry run only.
Re-enabling Dry run performs an ordered safe shutdown before further commands are suppressed.

## The model

A Plant contains the complete coordinated installation.
The UI speaks of rooms and loops, and the controller underneath uses the terms in brackets.

- A room (Comfort Zone) represents an identity, its observations, and its topology relationships.
- A room thermostat owns target state and demand semantics for exactly one room.
- A loop (Hydraulic Circuit) represents one hydraulic delivery path through one or more valves and one pump.
- A Delivery Route connects a room to a loop.
- A valve controls part of a loop's path.
- A pump circulates water for one or more loops.
- A source represents equipment or stored heat that could supply the Plant.

Relationships are stored using generated identifiers rather than display names.
This allows objects to be renamed without changing their logical relationships.

## Ownership

Every object belongs either to the Plant or to exactly one room.

- A room owns itself, its Delivery Routes, and its private loops and valves.
- Plant equipment belongs to the Plant: every pump, every source, the source selector, and the shared valves and shared loops that several rooms can use.
- A private loop uses valves of its own room and shared valves.
- A shared loop uses only shared valves.
- A room routes only to its own loops and to shared loops.

References therefore point only from a room toward the Plant.
This makes ownership deletion-closed: removing a room removes exactly the room, its routes, and its private loops and valves, and always leaves a valid Plant.
Home Assistant lets a user delete a room entry at any time, and this rule is why that is always safe for the graph.

Plant equipment that no enabled route reaches is accepted as unused equipment.
It is reported as a warning and never requested.
A room that no enabled route leaves is still an error, because it could never receive heat.

Each room is a Home Assistant config subentry, so its devices and entities are grouped under it and removed with it.
Rooms, their private loops and valves, pumps, and Dry run are edited in the UI.
Shared loops, shared valves, and the source selector are edited through the [plant file](plant-file.md), which describes the whole Plant as YAML for import, export, and editing.

## The evaluation cycle

Hydronicus repeatedly performs the same deterministic cycle:

```text
snapshot Home Assistant entities
  -> evaluate heating and cooling independently
  -> filter and arbitrate Delivery Routes
  -> coordinate shared-mode changeover
  -> plan valves, then pumps
  -> recommend and safely transition sources
  -> assemble runtime, plan, deadlines, and diagnostics
  -> execute or shadow ordered operations
  -> publish only changed public state
```

Running the cycle twice with unchanged input does not produce toggle behavior or duplicate commands.
The controller package is pure and has no Home Assistant imports.
The runtime adapter owns snapshots, service execution, timed wakeups, feedback reconciliation, Repairs, and entity publication.
This separation keeps safety decisions reproducible while containing external side effects at one boundary.

## Heating behavior

Hydronicus thermostat heating demand uses its runtime target, configured hysteresis, minimum active duration, and minimum idle duration.
A required observation that is unknown, unavailable, invalid, or stale blocks the room and releases demand immediately.

### Thermostat ownership

The Hydronicus thermostat is the only thermostat kind that Hydronicus publishes.

It starts at 21.0 °C and off when no valid restored state exists.

Its target, preset, and HVAC mode are runtime state restored through the Home Assistant entity lifecycle.
The exact Celsius target is stored beside the displayed one, so a display in whole degrees Fahrenheit does not shift the target across restarts.

An external thermostat is represented by one existing climate entity and is never controlled by Hydronicus.

The runtime adapter normalizes its state before the pure evaluator sees it.

`hvac_action` is authoritative for external demand.

Heating and preheating request heating, cooling requests cooling, and idle or off request neither.

External target and current temperature values are diagnostic only.

Hydronicus does not apply its internal hysteresis or duration holds to external demand.

Invalid or unavailable external input fails closed and releases demand immediately.

The virtual hydraulic sequence is:

```text
Room demand
  -> loop requested
  -> required valves requested
  -> valve readiness confirmed by feedback or configured delay
  -> pump requested
  -> source demand permitted only with a valid pump path
```

The codebase contains a generic Home Assistant executor for switch and valve service calls.
It is tested with synthetic and intercepted services.
While Dry run is enabled, the executor records the complete plan as proposed operations and dispatches no service calls.

When Dry run is off, Hydronicus executes heating valves, pumps, and an explicitly configured direct source-demand output.
Turning it off requires one confirmation of the displayed output set.
Turning Dry run back on will perform the ordered safe shutdown before suppressing further commands.

## Cooling behavior

Cooling demand uses room temperature, humidity, the worst-case room dew point, supply or surface temperature, sensor freshness, and explicit loop cooling compatibility.
It blocks unsafe or incomplete paths and explains condensation and shared-equipment conflicts.

When Dry run is off, Hydronicus opens the valves and starts the pumps of loops that deliver cooling, in the same order as for heating.
It does not command the source: the chilled water must come from a source that is already in cooling mode.
Direct source demand is only ever requested while the Plant is heating.

A pump that served cooling stops as soon as its last cooling loop releases, without overrun, and its valves close right after it.
Overrun only dissipates residual heat, and circulating chilled water after a condensation block is exactly what the block must prevent.

## Source behavior

Hydronicus can rank available sources using stable priority, freshness, temperature qualification, hysteresis, and dwell rules.
It publishes the recommended source and changeover reasoning.

Source-selector operations are explicitly kept in Dry run by the runtime.
The source recommendation remains visible in both modes.
Direct source-demand output can execute only when Dry run is off and a valid pump path exists.

## Shared equipment

Shared equipment is owned by its complete active-consumer set.
One room releasing demand cannot turn off an actuator that another requested loop still needs.

### Shared pump with independent valves

```text
Room A -> Loop A -> Valve A -+
                             +-> Shared pump
Room B -> Loop B -> Valve B -+
```

The pump remains requested until both ready loop consumer sets are empty.
This is the manifold that guided setup builds, and the review warns that the shared pump limits independent control.

### Shared valve and pump

```text
Room A -> Loop A -+
                  +-> Shared valve -> Shared pump
Room B -> Loop B -+
```

The topology is valid but physically coupled.
Hydronicus warns that separate room thermostats cannot independently control loops coupled by the same physical valve.
A valve used by the loops of two rooms is a shared valve, written in the plant file.

### One room with several loops

```text
                +-> Floor loop -> Floor valve -> Floor pump
Room A ---------+
                +-> Ceiling loop -> Ceiling valve -> Ceiling pump
```

Each route is evaluated explicitly.
The model does not infer water temperature, capacity, balancing, or manufacturer limits.

## What Home Assistant exposes

The integration publishes Hydronicus climate targets, aggregate temperatures, heating and cooling demand, blocked states and reasons, virtual valve and pump requests, source recommendations, topology summaries, and decision explanations.

Repairs identify configured entity bindings that are missing or unresolved.
A missing binding of a room, its private loops, or its private valves opens that room's reconfigure flow, and a source with its own entry opens that source.
A missing pump binding opens the Plant settings.
A missing binding of a shared loop, a shared valve, a source without its own entry, or the source selector cannot be fixed in a form, and the repair tells you to edit the plant file.
Downloadable diagnostics provide bounded and redacted runtime information for troubleshooting.

## What Dry run proves

Dry run proves that Hydronicus can interpret the configured graph and produce an explainable software decision without dispatching actuator service calls.
It does not prove that the graph matches the pipework, that a valve moves, that a pump produces flow, or that physical safety controls are adequate.

Read [configuration and simulation](configuration.md) to create a Plant and [safety limits](safety.md) before using real sensor observations.
