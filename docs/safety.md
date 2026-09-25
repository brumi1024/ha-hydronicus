# Safety limits

Hydronicus is software coordination for a hydronic plant.
It decides when valves open, when pumps run, and when the source is asked for heat or cooling, but it does not make the plant safe.

## Two separate layers

Physical protection keeps the plant safe whatever software does: the source's own controls and interlocks, pressure relief, high-limit thermostats, frost and condensation protection, flow proving, and the electrical protection of pumps and valves.
Keep all of it independent of Home Assistant, as the equipment and local regulations require.

Hydronicus is the second layer.
It coordinates the equipment in a sensible order and refuses to do what it can see is wrong, such as running a pump without an open loop, or cooling a ceiling below the dew point.
It is not a boiler safety controller, pressure relief, a flow proving device, a condensation sensor, a high-limit thermostat, or an emergency stop.
Never use it to bypass a hardware interlock, or to decide whether equipment is safe to run.

## What Hydronicus commands

Hydronicus commands an output only when you have armed it and **Control equipment** is on.

- A new Plant starts with no output armed and **Control equipment** off.
- **Arm outputs** in the Plant settings lists every output with its role; confirm each one against the device it controls.
- A loop runs only when every output it needs is armed and available, and the rest of the Plant runs meanwhile.
- A new output, such as the valve of a new zone, starts unarmed, and editing a thermostat, a sensor, a name, or a timing never changes what is armed.
- An output belongs to one Plant, and has exactly one role in it: a form or a plant file that binds an output another Plant uses is refused.

Hydronicus never commands:

- An external thermostat, which it only reads.
- A pump the source drives, which it only reasons about.
- An output that is not armed, including in Dry run.
- Any entity that is not an output of the Plant, such as a sensor.

## Dry run is not a safety proof

While **Control equipment** is off, the Plant runs in Dry run: it evaluates everything against the real states of your entities and records each command as proposed instead of sending it.
Dry run shows whether the configuration and the sequence are what you intend.
It does not simulate water, pressure, or temperature, and it cannot prove that a valve opens, that a pump produces flow, or that the source delivers water at a safe temperature.

## Stopping

Turning **Control equipment** off stops the armed equipment in order: the source is released, pumps finish their overrun or the source's post-run, and valves close once their pumps are seen off.
Only then does the Plant go to Dry run; the switch's `live` attribute shows when it has.
Switching the **Mode** select to off stops the equipment the same way and keeps it stopped.

## Failures are retried and surfaced

A command counts as done only when Home Assistant shows its result.
A command whose result is not seen is sent again, after 10 seconds at first and then after twice the previous wait, up to 5 minutes, for as long as the difference remains.
After three attempts, a Repair names the output that does not respond, and the Plant's **Status** reads `degraded`.

While a command has not taken effect, Hydronicus assumes the worst of it:

- A pump whose stop is not seen counts as running, so its last open path stays open.
- A valve whose opening is not seen keeps its loop from counting as ready, so no pump starts on it and the source is not asked for it.
- A source request whose release is not seen keeps the source's pumps' loops open for its post-run.

An output that is unavailable gets no command, and the loops that need it do not run until it returns.
A bound entity that does not exist is a Repair, and whatever needs it is blocked.

## Sensors fail closed

A required sensor that is unavailable, stale, in an unsupported unit, or physically implausible blocks its zone, and the zone does not call.
An optional sensor in the same state is left out.
Sensors named by a zone's areas are optional unless the [plant file](plant-file.md#areas) makes them required, so a zone with several areas keeps working when one area's sensor is missing.
For a zone that cools, consider making the humidity of each area required, because a room whose humidity is not observed is where a cooled surface condenses.

## Cooling and condensation

A loop may cool only with a condensation reference: its pump's supply temperature sensor or its own surface temperature sensor.
Its condensation guard blocks when the coldest reference is below the zone's worst-case dew point plus 2 K, and releases only 1 K above that, after at least 5 minutes.
A missing or stale reference, or a zone without a usable dew point, blocks cooling.
Pumps stop without overrun in cooling, and the source is not asked for cooling while a guard blocks a loop that a source-driven pump would pass water through.

The guard is only as good as its sensors.
A supply temperature measures the water, not the coldest point of a ceiling or floor, and a humidity sensor measures the room it is in.
Keep physical condensation protection where the emitters require it.
A pump the source drives with `min_flow: path` may carry chilled water through its min-flow loop during the source's post-run, even when that loop's guard blocks; a separator, buffer, or bypass with `min_flow: guaranteed` avoids that.

## Reloads, restarts, and changes

A reload, an unload, and a Home Assistant restart never send a command, so the equipment stays exactly as it was while Hydronicus is not running.
Hydronicus stores its timers, the Plant mode, and its retry state, and restores them before the first evaluation, which waits for Home Assistant to start and for every digital thermostat to restore.
With unchanged observations, the first evaluation after a reload or restart sends no command.

A Plant whose stored configuration is not valid, for example after a zone its pump needed was deleted, does not run at all.
It sends no command, the equipment stays as it was, and a Repair opens the Plant's **Reconfigure** to fix it.

When an output leaves the Plant, because you remove a zone, a loop, a valve, or the source, Hydronicus stops commanding it and leaves it exactly as it is.
A valve that was open stays open, and a request that was on stays on.
Before you remove equipment from a running Plant, set the affected zones' thermostats, or the Plant's **Mode**, to off and wait until the equipment has stopped.

## Safe operating rule

Try a Plant on synthetic entities first, then on real sensors with **Control equipment** off, and check the proposals.
Arm real outputs only when every one is the entity of the device its role names, and the physical protections work without Home Assistant.
Stay near the plant the first time **Control equipment** is on, and keep a way to stop the equipment by hand.
