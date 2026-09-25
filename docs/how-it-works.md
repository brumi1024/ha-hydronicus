# How Hydronicus works

Hydronicus coordinates a hydronic heating and cooling plant from Home Assistant.
It decides, from what it observes, what every valve, pump, and source request should be now, and then drives those outputs there and checks that they got there.
This page explains the model, one evaluation step by step, how outputs are commanded, and where the boundaries are.

## The model

A Plant is one heating and cooling system, set up as one Hydronicus entry.
It has:

- An optional source: the heat pump or boiler that Hydronicus asks for heat or cooling through a request switch, and optionally switches between heating and cooling through a mode select.
  Hydronicus reaches it only through generic Home Assistant entities, whatever integration provides them.
  A Plant without a source still opens valves and runs switched pumps, which suits a boiler that follows its own controls.
- Pumps: circulators that Hydronicus switches, or that the source drives by itself and Hydronicus never commands, such as a heat pump's own circulator.
- Zones: each zone is the space one thermostat controls.
  A zone covers zero or more Home Assistant areas and follows the temperature and humidity sensors those areas name, plus any extra sensors of its own.
  Its thermostat is a digital thermostat that Hydronicus provides, or an existing Home Assistant climate entity that Hydronicus only reads.
- Loops: a loop is a flow path, made of zero or more valves that open together and exactly one pump.
  A zone owns its loops.
  A loop with no valve is always open, and its pump is its only control.
  A loop heats, cools, or both.
- Plant loops: loops that no zone owns, which run whenever the source is requested, such as a towel dryer, or with a set of zones, such as a loop that several zones share.

The [reference plant](examples/reference-plant.yaml) shows all of it: an air-to-water heat pump with its own circulator, three zones over Home Assistant areas with a ceiling loop each, an underfloor loop with its own pump, and a towel dryer with a pump and no valve.

Each output entity has exactly one role in one Plant: a valve of one loop, a pump's switch, or a source output.
Hydronicus commands an output only once you have armed it.

## When the Plant evaluates

The Plant evaluates again whenever something it observes changes: an output, a sensor, a thermostat, the area settings of a covered area, the **Mode** select, **Control equipment**, or the armed outputs.
It also evaluates when a timer it is waiting for runs out, such as a valve's opening time or a pump's overrun, and when a command is due to be retried.
Changes that arrive together share one evaluation.

Each evaluation takes a snapshot of every entity the Plant reads, decides the desired state of every output, compares it with what the outputs show, sends what differs, stores its timers, and updates the entities.

## One evaluation, step by step

### 1. Observe

Hydronicus reads every output, sensor, and thermostat.
It converts temperatures to °C and humidity to percent, and a reading that is unavailable, stale, in an unsupported unit, or physically implausible counts as missing.
It re-reads which sensors each covered area names, so a change in the area settings takes effect at once, without a reload.

### 2. Demand

Each zone combines its usable temperatures by its aggregation: mean, minimum, or maximum.
A required sensor that is missing blocks the zone, and an optional one is left out.
A digital thermostat demands heating once the temperature is `heat_start_delta` (0.3 K) below the target, and stops once it is `heat_stop_delta` (0.1 K) above; cooling works the same way the other side of the target.
It can hold a decision for a minimum on or off time, and it reports a demand level from 0 to 1 from the distance to target over its proportional band.
An external thermostat demands heating while its `hvac_action` is heating or preheating, cooling while it is cooling, and nothing while it is idle or off; anything else, or an unavailable thermostat, blocks the zone.
A zone's demand counts only when its thermostat's mode matches the Plant mode; a zone that asks to cool while the Plant heats is shown as blocked.

### 3. Mode

The Plant mode is off, heat, or cool, chosen with the **Mode** select, and heating and cooling never run at the same time.
A change between heating and cooling is sequenced, as described in [mode changes](#mode-changes).

### 4. Wanted loops

A zone loop is wanted when its zone demands in the Plant mode and the loop runs in that mode.
A plant loop that runs with zones is wanted when any of them demands, and one that runs with the source is wanted while the source's request is on.
A wanted loop is dropped when an output it needs is not armed or not available, or when its [condensation guard](#cooling-and-the-condensation-guard) blocks.

### 5. Readiness

A loop is ready once each of its valves has been seen open for its opening time, 180 seconds by default, or its readiness sensor reports it open.
A loop with no valve is ready at once.
Readiness comes only from what Home Assistant shows, never from a command having been sent.

### 6. Minimum flow

A pump that needs an open loop while it runs keeps one, as described in [minimum flow](#minimum-flow).

### 7. Valves

Every valve of a wanted loop should be open.
A valve also stays open while it is the last open path of a pump that may still be running.

### 8. Pumps

A switched pump should run while one of its wanted loops is ready.
After heating ends it keeps running for its overrun, 180 seconds by default, with its loops held open.
Cooling stops a pump without overrun.
A pump never runs a loop in the wrong mode or through a blocked condensation guard.

### 9. Source

The source's mode select should show the option of the Plant mode.
The source's request should be on once a loop that a zone calls for is ready in the Plant mode, its switched pump is seen running, the mode select shows the right option, and every source-driven pump has an open path.
A plant loop that runs with the source never asks for heat by itself.
The request stays on for at least its minimum on time, 600 seconds by default, while a ready loop remains, and stays off for at least its minimum off time, also 600 seconds, before it is asked again.
After the request ends, the source's post-run, 180 seconds by default, keeps the loops of its own pumps open.

### 10. Timers

The evaluation records its timers, such as when each valve became ready and when each pump's overrun started, and works out when it next needs to look again.

Safe shutdown is the same evaluation with the Plant mode forced to off, so stopping always follows the same sequence as a normal end of demand.

## How outputs are commanded

Hydronicus compares the desired state of every output with what Home Assistant shows and sends a command for each difference.
It keeps comparing on every evaluation, so a difference that remains is sent again until the output shows what is asked.

Within one evaluation the commands go out in dependency order:

1. The source request off.
2. Pumps off.
3. Valves open.
4. Valves close.
5. Pumps on.
6. The source mode.
7. The source request on.

The waits between the steps are already part of the desired state.
A pump is asked to run only once its loop is ready, a valve closes only once the pump that needs it is seen off, and the source is asked for heat only once its loop's pump is seen running.
So heating starts with the valves, then the pumps, then the source, and it stops with the source, then the pumps, then the valves.

A command that returns without an error is not a confirmation; only the output's state in Home Assistant is.
Each command may take up to 10 seconds, and until the output shows the result, Hydronicus assumes the command may still act: a pump it asked to start counts as possibly running, and one it asked to stop counts as possibly still running.
At most one command per output is outstanding at a time.

A command whose result is not seen is sent again after a wait that starts at 10 seconds and doubles up to 5 minutes, for as long as the difference remains.
After three attempts without a result, Hydronicus raises a Repair saying that the output does not respond, and keeps retrying; the Repair clears once the output shows what is asked.
Meanwhile a pump whose stop is not seen keeps its last path open, and a valve whose opening is not seen keeps its loop from counting as ready.
An output that is unavailable gets no command until it returns.

## Minimum flow

Every pump has a minimum flow setting.

- `guaranteed` means a hydraulic separator, low-loss header, buffer, or bypass gives the pump a path whatever the loops do.
- `path` means the pump needs an open loop while it runs.

A switched pump that needs a path simply never runs without a ready loop, and its last ready loop stays open until the pump is seen off.

A pump that the source drives is different, because the source can run it at any time: while its request is on, during its post-run, and whenever Home Assistant shows the pump running.
Such a pump with `path` names its min-flow loops, and Hydronicus holds them open whenever none of the pump's other loops is ready while the pump may run.
Before the source is asked for heat, a min-flow loop is opened and becomes ready first.

In the reference plant, the heat pump's own circulator holds the living area's ceiling loop open while no zone calls.
If the separator protects that circulator, `min_flow: guaranteed` makes the min-flow loop unnecessary.

In cooling, a min-flow loop may carry chilled water during the source's post-run even when its condensation guard blocks, because the pump may still be running; a `guaranteed` pump avoids that.

## Mode changes

The **Mode** select chooses off, heat, or cool, and cool is offered only when a loop of the Plant cools.
There is no automatic mode; an automation can set the select.

A change between heating and cooling runs in order:

1. No new loop starts in the old mode, the source's request is released, and the old mode's pumps finish their overrun or the source's post-run.
2. The old mode's loops close, and the status reads `changing_over` with the reason `stopping heat before cool`.
3. The mode dwell runs from the moment the old mode's flow ended, 3600 seconds by default, with the reason `waiting for the mode dwell before cool`.
4. The new mode starts, and the source's mode select is set to the new mode's option before its request goes on.

Returning to the mode that last ran, or starting the first mode of a new Plant, needs no dwell.
Switching the Plant to off stops the current mode with the same sequence.

## Cooling and the condensation guard

A loop may cool only when it has a condensation reference: its pump's supply temperature sensor, or its own surface temperature sensor.
A loop without either runs heat only.
A zone that cools needs a humidity reading, from a humidity sensor or from its areas.

Each loop that cools has a condensation guard, checked on every evaluation:

- The zone's worst-case dew point is the dew point of its warmest temperature and its highest humidity, because the zone may span rooms whose readings are not paired.
  For a plant loop, the highest dew point of all zones counts, so every zone then needs a humidity reading.
- The guard blocks when the coldest reference is below that dew point plus a 2 K margin.
- It releases only once the coldest reference is at least 1 K above that threshold, and only after it has blocked for at least 5 minutes.
- A missing or stale reference blocks the guard, and so does a zone without a usable dew point.

A blocked guard drops the loop, and the source is not asked for cooling while a guard blocks a loop that a source-driven pump would pass water through.
Pumps have no overrun in cooling, so a pump stops as soon as its last cooling loop releases.

## Arming, Control equipment, and Dry run

Hydronicus commands an output only when two things hold: you have armed that output, and **Control equipment** is on.

- **Arm outputs** in the Plant settings lists every output with its role, and you confirm each one after checking it against the device it controls.
  A loop runs only when every output it needs is armed.
- **Control equipment** is a switch on the Plant device.
  While it is on, Hydronicus commands the armed outputs.
- A new Plant starts with no output armed and **Control equipment** off.

While **Control equipment** is off, the Plant runs in Dry run.
Every new Plant starts in Dry run.
In Dry run Hydronicus sends nothing: it records each command it would send as proposed, and treats the proposal as if the output had followed it, so the sequence advances exactly as it would with real equipment.
The **Status** sensor's `proposed` attribute shows the proposed state of each output, and the loop flowing sensors follow the proposals.
Arm the outputs first, because a loop whose outputs are not armed is dropped in Dry run too.

Turning **Control equipment** on starts commanding at once, from what the outputs really show.
Turning it off first runs the off-mode sequence on the armed outputs: the source is released, pumps finish their overrun or post-run, and valves close once their pumps are seen off.
Only then does the Plant go to Dry run, and the switch's `live` attribute stays true until it has.

A new output, such as the valve of a new zone, starts unarmed.
The loops that need it do not run until you arm it, while the rest of the Plant keeps running, and once any output of the Plant is armed, a Repair lists the ones that are not.
Removing an output disarms it, and editing a thermostat, a sensor, a name, or a timing never changes what is armed.

## Reloads and restarts

A reload, an unload, and a Home Assistant restart never send a command; the equipment stays as it is while Hydronicus is not running.

Hydronicus stores its timers, the Plant mode, its retry state, and when each output last changed, and restores them before the first evaluation.
The first evaluation waits until Home Assistant has started and every digital thermostat has restored its target and mode.
A valve that has been open for an hour therefore still counts as ready after a restart, and with unchanged observations the first evaluation sends no command.

Changing a Plant's configuration reloads it.
A change in the area settings or the armed outputs does not; the Plant just evaluates again.

## What Home Assistant shows

The Plant publishes a small set of entities: the **Mode** select, the **Control equipment** switch, and the **Status** sensor for the Plant, a thermostat, demand, temperature, and dew point for each zone, a flowing sensor for each loop, and a **Requested** sensor for the source.
Their attributes carry the reasons behind every decision.
See [the entities](entities.md) for the full list.

Problems that need you are Repairs: an output that does not respond, an entity that does not exist, outputs awaiting confirmation, and area problems.
See [troubleshooting](troubleshooting.md#repairs).

## What Dry run proves

Dry run shows what Hydronicus would command, in what order, and when, against the real states of your entities.
It does not simulate water, pressure, or temperature, and it cannot prove that a valve opens, that a pump produces flow, or that the source delivers safe water.
Treat it as a check of the configuration and the sequence, not of the plant.
Read [safety limits](safety.md) before you turn **Control equipment** on.
