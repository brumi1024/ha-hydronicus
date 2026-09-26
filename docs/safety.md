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

While **Control equipment** is off, the Plant runs in Dry run and sends nothing; it only checks the configuration and the sequence.
Read [what Dry run proves](how-it-works.md#what-dry-run-proves): it cannot prove that a valve opens, that a pump produces flow, or that the source delivers water at a safe temperature.

## Stopping

Turning **Control equipment** off stops the armed equipment in order: the source is released, pumps finish their overrun or the source's post-run, and valves close once their pumps are seen off.
Only then does the Plant go to Dry run; the switch's `live` attribute shows when it has.
Switching the **Mode** select to off stops the equipment the same way and keeps it stopped, except that the source's request stays on until it has been on for its minimum on time, as at the end of demand.
**Control equipment** off, a blocking condensation guard, a lost pump or path, and stopping a previous configuration release the request at once.

## Frost protection and the exercise

Frost protection heats a zone whose coldest reading falls below 5 °C, even while its thermostat or the **Mode** select is off, but only while Home Assistant runs, the zone's sensors report, and its outputs are armed and **Control equipment** is on.
It never acts while the Plant cools.
It is a comfort safeguard, not frost protection of the plant: keep the source's own frost protection, antifreeze, or drain-down where pipes can freeze.

Hydronicus also exercises a switched pump or a valve that has not been on for a week, only while nothing else runs, one pump at a time, and never with the source asked for heat.
It never runs a pump through a loop of the other mode or through a blocked condensation guard.

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
A condensation switch that is unavailable or unknown blocks cooling too.
A window sensor is the one exception: an unavailable or unknown window reads as closed, because a lost window sensor should not leave a home unheated.

## Cooling and condensation

A loop may cool only with a condensation reference: its pump's supply temperature sensor or its own surface temperature sensor.
Its condensation guard blocks when the coldest reference is below the zone's worst-case dew point plus 2 K, and releases only 1 K above that, after at least 5 minutes.
A missing or stale reference, or a zone without a usable dew point, blocks cooling.
Pumps stop without overrun in cooling, and the source is not asked for cooling while a guard blocks a loop that a source-driven pump would pass water through.

Three secondary inputs only add to that guard:

- A condensation switch on a pump's supply pipe or on a loop blocks cooling at once while it reads on, unavailable, or unknown, and cooling resumes only once it has read off for 5 minutes.
  A condensation switch that Home Assistant reads works only while Home Assistant runs; wire one to the pump or valves as well, as described below.
- A loop's surface minimum, 20 °C by default, stops cooling while its surface sensor reads colder.
- A zone's maximum humidity, 70 % by default, stops cooling while the zone is more humid, whatever its dew point.
  A humidity limit such as 75 % alone does not protect a surface cooled with 16 to 18 °C water, which is why it never replaces the dew point check.

Turning the surface minimum or the humidity limit off in the plant file removes only that input; the dew point check stays.

The guard is only as good as its sensors.
A supply temperature measures the water, not the coldest point of a ceiling or floor, and a humidity sensor measures the room it is in.
Keep physical condensation protection where the emitters require it.
A pump the source drives with `min_flow: path` may carry chilled water through its min-flow loop during the source's post-run, even when that loop's guard blocks; a separator, buffer, or bypass with `min_flow: guaranteed` avoids that.

See [cooling while Home Assistant is not running](#cooling-while-home-assistant-is-not-running) for what protects the plant when the guard itself is not running.

## Cooling while Home Assistant is not running

The condensation guard only exists while Home Assistant is running and Hydronicus is evaluating.
If Home Assistant stops or crashes during cooling, the source request, the valves, and the pumps stay exactly as they were, and chilled water keeps flowing with nothing watching the dew point.
A reload, an unload, and a restart deliberately send no command, as [reloads, restarts, and changes](#reloads-restarts-and-changes) below describes, so nothing closes the loop by itself either.

Protect against this independently of Hydronicus:

- A hardware dew point or condensation switch on the cooling supply pipe, wired to stop the pump or close the valves directly, the way Danfoss and Siemens radiant systems do; such switches typically stop the plant at about 90% surface relative humidity.
- A relay-level watchdog, such as a Shelly Gen2 switch's `auto_off` set with a delay on the source request or the cooling valves, combined with an automation that re-asserts them periodically while cooling should run.
  `auto_off` also stops heating if Home Assistant stops, which is usually acceptable, since unmonitored cooling risks condensation while unmonitored heating mostly risks comfort.
  The re-asserting automation must not fight Hydronicus: it must only refresh a relay that is already on, never turn one on that Hydronicus has not asked for.
- The heat pump's own minimum supply temperature setting for cooling, typically 16 to 18 °C for floor and ceiling cooling, as the last line of defence.

Treat this the same as the [physical protection](#two-separate-layers) the plant needs regardless of software: it has to work whether or not Home Assistant is running.

## Reloads, restarts, and changes

A reload, an unload, and a Home Assistant restart never send a command, so the equipment stays exactly as it was while Hydronicus is not running; with unchanged observations, the first evaluation after one sends no command either.

Removing a zone, a loop, a pump, or the source, or replacing the Plant from a plant file, first stops the whole equipment of the old configuration, in the same order as **Control equipment** off, before the new configuration runs; the **Status** sensor reads `stopping` until then.
A Plant left invalid by a removal stops the same way and then only observes, with its **Status** reading `invalid` and a Repair open until a **Reconfigure** fixes it.
Removing the whole Plant does not stop the equipment it controlled; stop it first with **Control equipment**.

Read [reloads and restarts](how-it-works.md#reloads-and-restarts) for exactly what each evaluation stores, restores, and stops.

## Safe operating rule

Try a Plant on synthetic entities first, then on real sensors with **Control equipment** off, and check the proposals.
Arm real outputs only when every one is the entity of the device its role names, and the physical protections work without Home Assistant.
Stay near the plant the first time **Control equipment** is on, and keep a way to stop the equipment by hand.
