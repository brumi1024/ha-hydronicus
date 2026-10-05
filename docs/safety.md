# Safety limits

Hydronicus decides when valves open, when pumps run, and when the source is asked for heat or cooling.
It does not make your plant safe.
Read this page before you turn on **Control equipment** for real equipment.

## Two separate layers

The first layer is physical protection, which keeps the plant safe whatever software does: the source's own controls and interlocks, pressure relief, high-limit thermostats, frost and condensation protection, flow proving, and the electrical protection of pumps and valves.
Keep all of it working without Home Assistant, as your equipment and local regulations require.

Hydronicus is the second layer.
It runs the equipment in a sensible order, and refuses what it can see is wrong, such as running a pump without an open loop, or cooling a ceiling below the dew point.
It is not a boiler safety controller, pressure relief, a flow proving device, a condensation sensor, a high-limit thermostat, or an emergency stop.
Never use it to bypass a hardware interlock.

## What Hydronicus commands

Hydronicus commands an output only once you have armed it in **Arm outputs** and while **Control equipment** is on.
A new Plant has nothing armed and **Control equipment** off, and a new output starts unarmed.
An output belongs to one Plant and has one role in it.

Hydronicus never commands:

- An existing thermostat, which it only reads.
- A pump the source runs by itself.
- An output that is not armed.
- Any other entity, such as a sensor.

Dry run sends nothing and only checks the configuration and the sequence; see [what Dry run proves](how-it-works.md#what-dry-run-proves).

## What fails safe

- A command counts as done only once Home Assistant shows its result; until then Hydronicus assumes the worst, and after three attempts a Repair names the output.
- A required sensor that is unavailable, stale, or implausible stops its zone from calling.
- A missing or stale condensation reference, or a condensation switch that is unavailable, blocks cooling.
- A window sensor is the one exception: an unavailable one reads as closed, so a lost sensor never leaves a home unheated.

Sensors that a zone follows through its areas are optional by default, so one missing sensor does not stop a zone of several rooms.
For a zone that cools, consider making each area's humidity required in the [plant file](plant-file.md#areas), because a room whose humidity nobody sees is where a cooled surface condenses.

The 10-second service timeout is a software boundary, not a guarantee that equipment cannot act later.
The simulator assumes delayed commands act within that window and commands to one entity act in order.
A device that queues an earlier start and executes it after a later stop can violate those assumptions.
Check real device latency and ordering during commissioning, and keep independent hydraulic and electrical interlocks.

## Frost protection is for rooms, not pipes

Frost protection heats a zone whose coldest reading falls below 5 °C, but only while Home Assistant runs, the zone's sensors report, and its outputs are armed with **Control equipment** on.
Keep the source's own frost protection, antifreeze, or drain-down wherever pipes can freeze.

## Cooling and condensation

The [condensation guard](how-it-works.md#cooling-and-condensation) is only as good as its sensors.
A supply temperature measures the water, not the coldest point of a ceiling or floor, and a humidity sensor measures only the room it is in.
Keep physical condensation protection where the emitters need it.

A pump the source runs with `min_flow: path` may carry chilled water through its min-flow loop during the source's post-run, even while that loop's guard blocks.
A separator, buffer, or bypass with `min_flow: guaranteed` avoids that.

## Cooling while Home Assistant is not running

The condensation guard exists only while Home Assistant runs.
If Home Assistant stops or crashes during cooling, the source request, the valves, and the pumps stay exactly as they were, and chilled water keeps flowing with nothing watching the dew point.
Protect against that independently of Hydronicus:

- A hardware dew point or condensation switch on the cooling supply pipe, wired to stop the pump or close the valves directly; such switches typically trip at about 90 % surface relative humidity.
- A relay-level watchdog, such as a Shelly Gen2 switch's `auto_off` on the source request or the cooling valves, with an automation that refreshes them while cooling should run.
  The automation must only refresh a relay that is already on, never turn one on that Hydronicus has not asked for.
- The heat pump's own minimum supply temperature for cooling, typically 16 to 18 °C for floors and ceilings, as the last line of defence.

## Reloads, restarts, and changes

A reload or a restart never sends a command, so the equipment stays exactly as it was until Hydronicus runs again.
Removing a zone, a loop, a pump, or the source first stops the equipment of the old configuration in order, before the new configuration runs.
Removing the whole Plant does not stop its equipment; turn off **Control equipment** first, as [removing Hydronicus](updating-and-removing.md#removing-hydronicus) describes.

## Optional feedback and comfort controls

Running and flow sensors provide additional observations, but they do not replace hardwired flow proving or an equipment interlock.
A binary flow input proves only what its device measures, and an individual loop's flow may still be inferred from its open valves and pump state.
Loop runtime and duty cycle are not delivered heat or energy measurements.

Supply temperature control is optional and bounded, with cooling still subject to measured condensation guards.
Configure limits for the actual source, emitters, and mixing arrangement, and give the setpoint one controller.
A schedule or early start changes only comfort demand and never grants permission to run equipment through a blocked guard.
Configured room recovery rates are estimates and do not guarantee that comfort will be reached at a particular time.

## Safe operating rule

1. Try a [trial Plant](getting-started.md#part-1-a-trial-plant) on fake entities first.
2. Run your own Plant with **Control equipment** off, and check the proposals.
3. Arm an output only once you have checked that it is the entity of the device its role names.
4. Stay near the plant the first time **Control equipment** is on, and keep a way to stop the equipment by hand.
