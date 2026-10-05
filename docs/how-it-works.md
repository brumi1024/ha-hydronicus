# How it works

Hydronicus looks at your plant, decides what every valve, pump, and source request should be right now, sends what differs, and checks that each output got there.
This page explains those decisions: what makes a zone call, in which order the equipment starts and stops, and what keeps it safe.

## The parts of a Plant

A Plant is one heating and cooling system, set up once as one Hydronicus entry.

- The source is the heat pump or boiler, asked for heat or cooling through a request switch, and optionally switched between the two through a mode select.
  A Plant without a source still opens valves and runs switched pumps, which suits a boiler or heat pump that regulates its own water temperature.
- A pump is a circulator that Hydronicus switches, or one that the source runs by itself, such as a heat pump's own circulator, which Hydronicus never commands.
- A zone is the space one thermostat controls.
  It can cover Home Assistant areas and follow the sensors those areas name, and its thermostat is either a digital one that Hydronicus provides or an existing climate entity that Hydronicus only reads.
- A loop is one water path of a zone: zero or more valves that open together, and exactly one pump.
  A loop without a valve is always open, and its pump is its only control.
  A loop heats, cools, or both.
- A plant loop is a loop that no zone owns.
  It runs whenever the source is asked for heat, such as a towel dryer, or with a set of zones, such as a hall that two zones share.

Every output has exactly one role in one Plant: a valve of one loop, a pump's switch, or a source output.
The [reference plant](examples/reference-plant.yaml) shows a complete example: a heat pump with its own circulator, three zones with a ceiling loop each, an underfloor loop with its own pump, and a towel dryer.

## When Hydronicus decides

The Plant evaluates whenever something it reads changes, such as a sensor, a thermostat, an output, or the **Mode** select, and whenever a timer it waits for runs out.
An unchanged sensor report also refreshes its age, so a recovered sensor does not stay blocked until its value changes.
Schedule early-start deadlines and due command retries also trigger evaluation.
Each evaluation reads everything, decides the state every output should have, sends a command for each difference, and saves its timers.
Stopping is the same evaluation with the mode forced to off, so every stop follows the same safe sequence.

## When a zone calls

A zone combines its usable temperatures into one, by mean, minimum, or maximum.
A required sensor that is missing, stale, or implausible stops the zone from calling; an optional one is left out.

A digital thermostat calls for heat once the temperature is 0.3 K below its target, and stops once it is 0.1 K above; cooling mirrors that.
It keeps each decision for at least 10 minutes, because a thermoelectric valve takes minutes to open.
Heating and cooling keep separate manual and preset targets.
An optional [comfort schedule](#comfort-schedules) chooses comfort or setback, with bounded early start.
An existing thermostat calls while its `hvac_action` is heating, preheating, or cooling.

A zone's call counts only when its thermostat's mode matches the Plant's **Mode**.
Then two things can override it:

- An open window: once any window of the zone has been open for its delay, a minute by default, the zone stops calling, until every window has been closed for its delay.
- [Frost protection](#frost-protection): a zone that is about to freeze is heated regardless, even with a window open.

## The safe order

Every loop a calling zone needs is wanted, unless an output it needs is not armed or not available, or its [condensation guard](#cooling-and-condensation) blocks.
From the wanted loops, Hydronicus starts the equipment in order, and each step waits for the one before to be seen done:

1. The loop's valves open.
2. Once every valve has been seen open for its opening time, 3 minutes by default, the loop is ready, and its pump starts.
3. Once the pump is seen running, the source's mode select shows the right mode, and its optional supply target is confirmed, the source is asked for heat or cooling.

When the zone stops calling, it all stops in reverse:

1. The source's request is released, once it has been on for its minimum on time, 10 minutes by default.
2. After heating, a switched pump keeps running for its overrun, 3 minutes by default, with its loops held open; after cooling it stops at once.
3. The valves close once their pump is seen off.

A source that runs its own pumps keeps them going for its post-run after the request ends, 3 minutes by default, and Hydronicus keeps their loops open meanwhile.
The source's request also stays off for its minimum off time before it is asked again.
Minimum on and off timers begin with observed request transitions, so a delayed command cannot consume the equipment's minimum time before it acts.
Optional switched-pump running and flow feedback must confirm circulation before the source is requested.
A source-driven pump may start from known-off feedback when first requested, then has the source's `feedback_timeout` to prove operation, 300 seconds by default; unavailable feedback blocks startup.
A blocked condensation guard, a lost ready loop or pump, turning **Control equipment** off, and stopping an old configuration release the source request immediately.

## Commands are confirmed

A command that returns without an error is not a confirmation; only the output's state in Home Assistant is.
Until an output shows the result, Hydronicus assumes the worst: a pump it asked to stop may still run, so its last open loop stays open, and a valve it asked to open does not count as open.

Each service call has a 10-second timeout, with an unconfirmed command modeled as possibly acting during that window.
That timeout cannot cancel a command already accepted by downstream equipment.
The simulator assumes device commands act within that window and preserve order; equipment that acts later or reorders commands needs independent interlocks and commissioning checks.
At most one command per output is outstanding at a time.
Before dispatching each queued command, Hydronicus rechecks arming and whether the Plant still permits it.
Disarming prevents unsent commands from starting; it does not undo a call already sent.

A command whose result is not seen is sent again, after 10 seconds at first, then twice as long each time, up to every 5 minutes.
After three attempts, a Repair names the output that does not respond, and the Plant's **Status** reads `degraded`.
A `valve` entity that shows opening or closing is left to move, and counts as possibly open until it shows closed.
An output that is unavailable gets no command until it returns.

## Minimum flow

Every pump has a minimum flow setting:

- `path`: the pump needs an open loop while it runs.
- `guaranteed`: a hydraulic separator, low-loss header, buffer, or bypass gives the pump a path, whatever the loops do.

A pump that Hydronicus switches and that needs a path simply never runs without a ready loop, and its last loop stays open until the pump is seen off.

A pump the source runs is harder, because the source can run it at any time.
If it needs a path, it names min-flow loops, and Hydronicus holds one of them open whenever none of the pump's other loops is.
In the reference plant, the heat pump's circulator keeps the living area's ceiling loop open while no zone calls.

## Heating, cooling, and mode changes

The **Mode** select chooses off, heat, or cool, and heating and cooling never run at the same time.
Cool is offered only when a loop of the Plant cools.
There is no automatic mode, but [an automation can switch it](entities.md#automatic-heat-and-cool-changeover).

A change between heating and cooling runs in order:

1. No new loop starts in the old mode, and the old mode stops in the usual order.
   The **Status** reads `changing_over`, with the reason `stopping heat before cool`.
2. The mode dwell runs from the moment the old mode's flow ended, an hour by default, with the reason `waiting for the mode dwell before cool`.
3. The new mode starts, and the source's mode select is set before its request goes on.

Going back to the mode that last ran needs no dwell, and neither does the first mode of a new Plant.

## Cooling and condensation

Water that is colder than the room's dew point makes a floor or ceiling wet.
So a loop may only cool with a condensation reference, a temperature that shows how cold its water or surface is: its pump's supply temperature sensor, or its own surface temperature sensor.
A loop without either heats only.

Every cooling loop has a condensation guard, checked on every evaluation:

- The zone's worst-case dew point is the dew point of its warmest temperature and its highest humidity, because a zone may span rooms whose sensors are not paired.
  A plant loop reads the zones it runs with, or every zone when it runs with the source.
- The guard blocks when the coldest reference is less than 2 K above that dew point.
- It releases only once the reference is at least 3 K above the dew point, and only after it has blocked for at least 5 minutes.
- A missing reference, one that has not reported for 30 minutes, or a zone without a usable dew point also blocks.

Three optional inputs add to the dew point check, and none of them relaxes it:

- A condensation switch on the pump or the loop blocks at once while it reads on or unavailable, and releases once it has read off for 5 minutes.
- A loop's surface minimum, 20 °C by default, blocks while its surface is colder.
- A zone's maximum humidity, 70 % by default, blocks while the zone is more humid, and releases 5 points below.

A blocked guard drops its loop, and the source is not asked for cooling while a pump it runs would pass water through a blocked loop.
A new guard, such as that of a loop just added, starts blocked unless every check already passes.

## Frost protection

Frost protection keeps a zone from freezing while its thermostat, or the whole Plant, is off.
Once the coldest reading of a zone is below the frost protection temperature, 5 °C by default, the zone is heated whatever its thermostat says, until that reading is 1 K warmer.
Its reason then reads `frost protection: heat to 6.0 °C from 4.0 °C`.

- Only a zone that a loop heats is protected, and the coldest usable reading counts, so one warm sensor cannot hide a cold room.
- While the **Mode** select is off, frost protection runs the Plant in heat, only for the zones it protects.
- It never acts while the Plant cools or is asked to cool.
- It obeys arming and **Control equipment** like any other demand, so in Dry run it is only proposed.

The **Status** sensor's `frost_protection` attribute lists the zones it heats.

## Exercise

A circulator or a thermoelectric valve that stays off for months can seize.
So Hydronicus exercises every switched pump and every valve that has not been seen on for a week: it opens the pump's loops, runs the pump for a minute once a loop is ready, and closes the loops once the pump is seen off.

- It runs only while nothing else does, one pump at a time, and stops at once when a zone calls.
- It never asks the source for heat or cooling.
- The clock of each pump and valve starts when Hydronicus first sees it, survives restarts, and moves only with what the outputs really show.
- It only passes water through loops of the mode that last ran, and after cooling, only through loops whose dew point check and condensation switches allow it.
- A pump the source runs is never commanded, so only its loops' valves are exercised.
- An exercise gives up on a valve that never becomes ready, and that valve's own Repair says what is wrong.

The **Status** reads `exercising` meanwhile, and its `idle_since` attribute shows since when each pump and valve has been off.

## Arming, Control equipment, and Dry run

Hydronicus commands an output only when both hold:

- You have armed that output in **Arm outputs**.
- **Control equipment** is on.

A new Plant has nothing armed and **Control equipment** off.
A new output, such as the valve of a new zone, starts unarmed, and a loop runs only when every output it needs is armed.

While **Control equipment** is off, the Plant runs in Dry run.
It sends nothing, records each command it would send as proposed, and treats the proposal as if the output had followed, so the sequence advances just as it would with real equipment.
The **Status** sensor's `proposed` attribute shows the proposals.

Turning **Control equipment** on starts from real outputs and physical mode history.
A sequence simulated in Dry run cannot satisfy the mode dwell required by equipment that was running in the other mode.
Turning it off first stops the armed equipment in the usual order; the switch's `live` attribute stays true until it has.

### What Dry run proves

Dry run shows what Hydronicus would command, in what order, and when, against the real states of your entities.
It does not simulate water, pressure, or temperature, and it cannot prove that a valve opens, that a pump moves water, or that the source delivers safe water.
Treat it as a check of the configuration and the sequence, not of the plant.

## Reloads, restarts, and changes

Reload, unload, removal, and Home Assistant stop never send a command; the equipment stays as it is while Hydronicus is not running.
Stopping cancels dispatch and drops queued commands, so no unsent command starts after shutdown begins.
It does not claim that a previously sent command or physical equipment has stopped.
Hydronicus saves its timers, the Plant mode, and when each output last changed, and restores them first, so a valve that has been open for an hour still counts as ready, and an unchanged plant gets no command after a restart.

Changing the Plant's configuration reloads it; changing an area's sensors or the armed outputs does not.
When a change removes an output that is on, Hydronicus first stops the equipment of the old configuration in order, with the **Status** reading `stopping`, and only then runs the new one.
A configuration that is not valid stops the same way, then only observes, with its **Status** reading `invalid` and a Repair until you fix it.

## Supply temperature control

A source can bind an optional `number` entity for its water supply target.
Without an outdoor sensor, heating and cooling each use a configured fixed target.
With an outdoor sensor, heating uses a linear curve between two outdoor temperatures and their supply targets, clamped at both ends.
For example, the default curve asks for 45 °C at -10 °C outdoors, 35 °C at 5 °C, and 25 °C at 20 °C or warmer.
This responds to a current outdoor measurement; it does not predict the weather.

The policy stays inside its configured bounds and the number entity's usable temperature range.
A configured outdoor sensor that is missing, stale, or invalid blocks the heating request.
Cooling remains independent of the outdoor sensor, and raises its proposed target when needed to preserve the worst measured dew point plus the guard's 2 K margin and 1 K release allowance.
If that would exceed the configured maximum, the source stays off with a reason.
The existing condensation guard still checks actual measured water or surface temperatures.

The number is an armed output with the same confirmation, timeout, and retry path as other outputs.
A small configurable tolerance accepts feedback near the requested value, so rounding or a small outdoor temperature change does not continually rewrite it.
The source waits for confirmation before requesting operation.
Choose one owner for the supply setpoint; leave this feature off when the source's own controller already owns its heating curve.

## Comfort schedules

A digital thermostat can follow an existing Home Assistant `schedule` helper after its `schedule` preset is selected.
During on periods it uses the manual comfort target for its current mode.
Outside those periods it reduces the heating target by `heat_setback`, or increases the cooling target by `cool_setback`.
The heating and cooling targets and preset dictionaries remain separate.

An optional early start estimates recovery time from the current temperature difference and a configured warming or cooling rate in K/hour.
It never begins earlier than `max_early_start` before the next comfort period, and zero disables early start.
For example, a room 1 K below its heating target with `heating_rate: 1` may start one hour early, provided the configured limit allows it.
A room already at target needs no early start.
Once early start begins, it stays active until that comfort period starts, so a warming or cooling room cannot repeatedly switch back to setback.
The latch survives reloads and resets when its schedule event, control mode, or applicable limit changes.
The thermostat exposes its effective target and schedule status, including whether early start is active.

A manual target change or a different preset cancels schedule control until `schedule` is selected again.
An unavailable helper falls back to manual comfort, while a missing or invalid next event disables early start.
The schedule never changes the Plant mode or overrides windows, arming, condensation guards, minimum times, or hydraulic sequencing.
By default this is a bounded estimate using configured rates, with optional learned recovery described below.
It does not guarantee the room will reach comfort at the scheduled time.

## Recovery learning

Each digital thermostat can learn empirical room recovery times from observed circuit operation and temperature reports.
Learning is off by default.
Observe records usable episodes and shadow predictions while leaving configured-rate comfort planning unchanged.
Assist permits an accepted estimate to choose scheduled recovery timing, within the existing maximum early start.
The learner keeps each zone and mode separate and rejects episodes affected by unusable readings, changed targets, safety blocks, or interrupted operation.
Dry run proposals are not learning evidence.

Admission requires independent recovery history spread over time and successful predictions made before their observed outcomes.
Too little history, prediction error, stale evidence, or a deficit outside the observed range returns planning to the configured rate.
A forecast can refine recovery only when the zone separately opts in and evidence supports using outdoor conditions.
Weather failure falls back to the learned baseline or configured rate.
Neither learning nor forecasts change the manual comfort target, extend the configured lead limit, or suppress ordinary demand.

An accepted early start remains tied to that schedule event while the user keeps schedule control.
A manual target or preset change still cancels it.
The thermostat's displayed effective target and demand use the same evaluated proposal.
The **Reset recovery learning** button discards a zone's model without changing its manual controls or hydraulic state.

These features work with a source-less Plant that opens valves and starts switched pumps once a loop is ready.
They do not require a heat-pump request switch or create one.
An autonomous heat pump can regulate its inlet and outlet water temperatures without knowing zone demand: opening circuits and circulating their water lowers water temperature, which can make its own controller start heating after a delay.
The learned interval begins with observed circulation, so it includes any subsequent autonomous source delay and the water and emitter response together.
Scheduled learned recovery separately budgets the longest remaining configured valve-opening time among the zone's serving loops in the current mode, within the same maximum early-start limit.
Already ready valves add no delay, and valves partway through opening add only their remaining configured wait.
This timing allowance never replaces hydraulic readiness checks or identifies the compressor's startup timestamp.
Pump and valve observations describe circuit operation; without independent proof, circulation remains an estimate.
Even proven circulation and measured room temperature do not establish heat delivered, compressor operation, electricity use, savings, or COP.
Those claims require their own trustworthy measurements.

## Equipment feedback

A source or pump can bind a `running_sensor`, and a pump can additionally bind a `flow_sensor`.
Each is a binary input from the equipment's own integration.
Running feedback tells Hydronicus that equipment may still need an open path after its command ends, including autonomous source or pump activity.
Switched-pump flow feedback confirms circulation before the source is requested.
Source running feedback and source-driven pump feedback may start known off and must confirm within the source's `feedback_timeout`, 300 seconds by default.
This equipment startup period is separate from the 10-second service call timeout.
Missing or unknown feedback must not be interpreted as confirmation that equipment stopped.

Without feedback, running and loop flow are estimates derived from output states and configured timing.
Even with pump flow proof, an open loop's flowing state is not an individual loop flow meter and gives no measured water volume, heat output, or efficiency.
Use actual flow, temperature difference, and energy measurements for those quantities.
Keep hardware flow proving and other source protections independent of Home Assistant.

## Known limitations

- Source control uses generic Home Assistant switches, selects, and optional supply temperature numbers; there is no built-in Modbus driver.
- There is no automatic heat and cool mode; an [automation](entities.md#automatic-heat-and-cool-changeover) can set the **Mode** select.
- Heat-only loops are not exercised between the end of cooling and the next heating.
- A zone that frost protection heats switches the Plant to heat even when all its heating loops are unarmed or unavailable, although nothing then heats.
- The condensation guard runs only while Home Assistant runs; see [safety limits](safety.md#cooling-while-home-assistant-is-not-running).
- Removing the whole Plant does not stop its equipment; see [removing Hydronicus](updating-and-removing.md#removing-hydronicus).
