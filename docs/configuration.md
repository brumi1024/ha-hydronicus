# Configuration

This page is a map of the Hydronicus forms: creating a Plant, its settings, changing it later, and its zones.
Every field in the forms has its own help text and default, so this page focuses on the choices that need a little more context.
[How it works](how-it-works.md) explains what the settings do, and the [plant file](plant-file.md) describes the same Plant as YAML.

## Before you start

Have these entities ready in Home Assistant:

| For | You need |
| --- | --- |
| Every valve | A `switch` or `valve` entity that opens and closes it. |
| Every pump Hydronicus switches | A `switch` entity. |
| The heat pump or boiler, optional | A `switch` that asks it for heat or cooling, and optionally a `select` that switches its mode. |
| Every zone | A temperature sensor, named in the settings of its Home Assistant areas or chosen in the zone form. |
| Every zone that cools | A humidity sensor, the same way. |
| Every loop that cools | A water supply temperature sensor on its pump, or a surface temperature sensor on the loop. |
| Windows, optional | A `binary_sensor` per window or door, on while it is open. |
| Condensation switches, optional | A `binary_sensor` per dew point switch on a cooling pipe, on when it detects condensation. |
| Running and flow feedback, optional | Binary running feedback for the source or pumps, and binary flow proof for a pump. |
| Supply control, optional | A source supply temperature `number` and an outdoor temperature `sensor` for a heating curve. |
| Comfort schedule, optional | A Home Assistant `schedule` helper for each participating digital thermostat. |
| Recovery weather, optional | A `weather` entity with hourly forecasts and, when available, a measured outdoor temperature `sensor`. |

The forms never offer entities that Hydronicus itself provides, because a Plant that reads its own output would feed back into itself.
If you are new to Hydronicus, try the [trial Plant](getting-started.md#part-1-a-trial-plant) first.

For a system where Hydronicus controls only circuit valves and pumps, leave the source request empty and select each pump's switch.
A pump starts once a demanded loop's valves are ready, with normal overrun and hydraulic protection.
Recovery learning needs room temperatures and circuit observations; it does not require heat-pump control.

## Create a Plant

Open **Settings > Devices & services > Add integration** and search for **Hydronicus**.
Choose **Guided setup** to build the Plant form by form, or **Import a plant file** to paste a [plant file](plant-file.md).
Both end with **Review the Plant**, and nothing is created until you submit it.

### Guided setup

Guided setup walks from the source to the pumps, then the zones and their loops, then the loops no zone owns.

1. **The Plant and its source**: the **Plant name**, and the source's **Source request switch** and **Source mode select** if Hydronicus should ask a heat pump or boiler for heat.
   Leave the request switch empty for a source that follows its own controls; valves and pumps still run on demand.
   The collapsed **Timing** and **Protection** sections hold the mode dwell, the source's timings, [frost protection](how-it-works.md#frost-protection), and the [exercise](how-it-works.md#exercise) of idle pumps and valves.
   Optional source running feedback observes operation separately from its request.
   **Source feedback timeout** gives requested equipment time to report operation, 300 seconds by default.
   **Supply temperature control** selects the optional supply number, bounds, fixed targets, and outdoor heating curve.
   **Weather forecast** selects optional hourly forecasts and an outdoor reading for recovery learning, independently of source control.
2. **Source modes**, only with a mode select: which of its options means heating and which means cooling.
3. **Pump**, once per pump: its **Pump switch**, or none for a pump the source runs by itself, such as a heat pump's own circulator.
   The **Minimum flow** says whether the pump **Needs an open loop**, or whether **A separator guarantees its flow**; see [minimum flow](how-it-works.md#minimum-flow).
   A **Supply temperature sensor** lets the pump's loops cool.
   Optional running feedback and water flow proof confirm operation and circulation independently of the pump command.
4. **How is your home zoned?**: **One zone per area**, **Zones that cover several areas**, such as one zone per floor, or **Zones without areas**, for zones with their own sensors or an existing thermostat.
5. **Add a zone**: its **Areas**, any **Extra temperature sensors** and **Extra humidity sensors**, and its thermostat.
   Leave **Existing thermostat** empty to get a digital thermostat from Hydronicus.
   Leave **Zone name** empty to take the name of the one chosen area, or of the floor every chosen area is on.
   **Default comfort temperatures**, **Heating presets**, and **Cooling presets** keep the modes separate.
   **Comfort schedule** and **Recovery learning** configure the optional [comfort controls](#thermostats).
6. The loop form: the **Valves** that open together, the **Pump**, and the **Modes**.
   Leave **Valves** and **Pump** empty for a zone that only a plant loop serves.
7. The zone's menu: **Add another loop to this zone**, such as a floor loop next to a ceiling loop, **Add another zone**, or **Continue**.
8. **Plant loops**: **Add a plant loop** for a loop no zone owns, or **Continue**.
   Its **Runs** setting runs it **With the source**, such as a towel dryer, or **With zones**, such as a hall that two zones share.
9. **Min-flow loops**, for each pump the source runs that needs an open loop: the **Loops to hold open** while no other loop of that pump is ready; a ceiling loop is a good choice.
10. **Review the Plant**: the whole Plant, with warnings about what may not work as intended, such as an area without a temperature sensor.
    Warnings never block.

Every form checks the whole Plant with the same rules as a plant file, and shows a problem next to the field it belongs to.

Names become entity IDs, such as `climate.living_area` for the zone `Living area`, so choose names you want to keep.
Each object also gets a slug from its name when it is created, such as `living_area`, and the slug never changes.

### Import a plant file

Choose **Import a plant file** and paste the file into **Plant file**.
**Review the Plant** shows the Plant before it is created.
A file with the ID of a Plant that is already set up is refused; remove that Plant first, or use **Replace from a plant file** on it.

## Plant settings

**Configure** on the Plant's entry opens the Plant settings:

- **Arm outputs** lists every output with its role, such as `Pump Floor: switch.floor_pump`.
  Hydronicus commands only the outputs you check here, and only while **Control equipment** is on.
  Check each entity against the device it controls first; [getting started](getting-started.md#part-2-your-own-plant) walks through going live.
- **Show the plant file** shows the Plant as a [plant file](plant-file.md), which imports as the same Plant with the same entity IDs.

Arming and **Control equipment** survive restarts, and changing them never reloads the Plant.

## Change the Plant

**Reconfigure** on the Plant's entry changes everything except the zones:

- **Plant and source**: the forms of steps 1 and 2 above.
- **Pumps**: choose a pump to change or remove, or `Add a pump`.
  A pump that a loop still uses cannot be removed; move or remove those loops first.
- **Plant loops**: choose a plant loop to change or remove, or `Add a plant loop`.
- **Replace from a plant file**: replace the whole Plant, zones included, from a plant file with this Plant's ID or no ID.
- **Review and save**: **Save the changes** shows what is added, removed, and changed before anything is stored.

Nothing is stored until you submit **Save the changes**, and the Plant then reloads.
Removed outputs are disarmed, and new outputs wait for you to arm them.
If a removed output was running, the Plant first stops the equipment of its old configuration, in the usual safe order.
If the Plant changed while the form was open, such as a zone saved meanwhile, nothing is stored; open **Reconfigure** again.

A pump the source runs that needs an open loop must have min-flow loops.
If it has none yet, **Review and save** asks for its **Loops to hold open** first.
If no loop uses the pump yet, **A pump without a loop** lets you **Add a plant loop** for it, or **Change the pump** to **A separator guarantees its flow** until you have added its zone loops.

## Zones

Each zone is listed as its own entry under the Plant's entry.

- **Add zone** adds a zone, with the same forms as guided setup.
- **Reconfigure** on a zone offers **Zone settings**, **Loops**, where you choose a loop to change or `Add a loop`, and **Save**.
- **Delete** on a zone removes it with exactly its own loops and valves.

A zone is saved only as part of a valid Plant, and saving it reloads the Plant.
A new zone's valves start unarmed, so its loops wait for you to arm them while the rest of the Plant keeps running.
Editing a thermostat, a sensor, a name, or a timing never changes what is armed.

Deleting a zone whose loops are running first stops the equipment in order.
If the deletion leaves a pump the source runs without a min-flow loop, the Plant stops, only observes, and raises a Repair that opens its **Reconfigure**.

## Areas

A Home Assistant area can name the sensor that represents its temperature and the one for its humidity.
A zone that covers the area follows those sensors, so you choose each room's sensor once, in one place.

To set them, open **Settings > Areas, labels & zones**, open the area, choose **Area settings** in its menu, and choose the **Temperature sensor** and the **Humidity sensor**.
The area settings only offer sensors that belong to the area, so first set the sensor's **Area** in its own settings, or put its device in the area.

How a zone uses its areas:

- It reads its extra sensors first, then the sensors each area names.
- Changing an area's sensor takes effect at once, without a reload.
- Area sensors are optional by default: a stale or missing one is left out, so one flat battery in a five-room zone does not stop the other four rooms.
  The [plant file](plant-file.md#areas) can make them required.
- A missing area, or one that names no sensor, never stops the Plant from loading; a Repair reports it.
- Home Assistant does not update an area when you rename a sensor's entity ID, so a Repair asks you to choose the sensor again.
- An area may be covered by several zones, such as a hall between two floors; its sensors then count in each of them.

A zone that covers exactly one area puts its thermostat in that area, so it shows on the area's page and answers voice commands such as "set the bedroom to 21".

## Sensors

A zone combines its usable temperatures by **Combine temperatures by**: **Mean**, **Minimum**, or **Maximum**.
An extra sensor you choose in the zone form is required: while it is stale or unavailable, the zone does not call.
A reading is stale after an hour without a report, which suits battery sensors with an hourly heartbeat; the [plant file](plant-file.md#sensors) can change that and make a sensor optional.

Hydronicus reads each sensor's unit and converts it, whatever unit system Home Assistant displays:

| Reading | Accepted units | Plausible range |
| --- | --- | --- |
| Zone and surface temperature | `°C`, `°F`, `K`, or no unit, taken as °C | -50 to 100 °C |
| Pump supply temperature | The same | -50 to 150 °C |
| Outdoor compensation temperature | The same | -50 to 100 °C |
| Humidity | `%` or no unit | 0 to 100 % |

A reading in another unit or outside its range, such as -127 °C from a disconnected probe, counts as unavailable.

## Thermostats

Each zone has exactly one thermostat.

A digital thermostat is a climate entity that Hydronicus provides.
It restores separate heating and cooling manual targets, its preset, and its mode after a restart.
A new thermostat starts off, with heating at 21 °C and cooling at 24 °C by default.
Its available modes follow every loop serving the zone, including shared plant loops.
Heating presets apply only to heating and cooling presets only to cooling.
It calls for heat once the temperature is 0.3 K below its target, and stops 0.1 K above it; cooling works the same way the other side of the target.
It keeps each decision for at least 10 minutes, so a short call does not open a slow thermoelectric valve only to close it again before the pump has run.
The [plant file](plant-file.md#thermostats) can change these values.

Configure a helper under **Comfort schedule**, then select the thermostat's `schedule` preset to follow it.
On periods use its manual comfort target; off periods apply the configured reduction for heat or increase for cool.
A manual temperature change or another preset cancels schedule control until `schedule` is selected again.
Early start is off by default and has a maximum of six hours when enabled; its configured rates are in K/hour.
An unavailable schedule falls back to manual comfort, and an unusable next-event timestamp disables early start.
See [comfort schedules](how-it-works.md#comfort-schedules) and the [example plant](examples/comfort-and-feedback.yaml).

The **Recovery learning** section is off by default.
Choose **Observe** to collect recovery observations and predictions without changing the configured thermostat behavior; this works without a schedule.
Choose **Assist** only when you want validated learned recovery estimates to influence a configured comfort schedule's early start.
The configured rate remains the fallback and **Maximum early start** remains an absolute limit, including when a prediction says the room needs longer.
Manual target changes and other presets still leave schedule control.

Configure optional inputs under the Plant's **Weather forecast** section.
Choose a weather entity that supports hourly forecasts and, when available, a separate measured outdoor temperature sensor.
**Use weather for recovery** is a separate zone option that requires Assist, a comfort schedule, and those Plant weather settings.
Unusable weather falls back to learned recovery or the configured rate without suppressing ordinary comfort demand.
Forecasts do not replace room temperatures, condensation sensors, or pump feedback.
See the [circuit-only example](examples/predictive-circuits.yaml) and [recovery learning settings](plant-file.md#recovery-learning).

An existing thermostat is a climate entity you already have, which then owns the zone's demand.
Hydronicus only reads its `hvac_action` and never commands it.
Make sure it does not also switch a valve or pump that Hydronicus commands.

## Windows

A zone's **Windows** are binary sensors that are on while a window or door is open.
Once one has been open for the **Window open delay**, a minute by default, the zone stops calling, in heating and in cooling.
It calls again once every window has been closed for the **Window close delay**.
The delays keep a door you walk through from closing valves that take minutes to open again.

A window sensor that is unavailable counts as closed, so a flat battery never leaves a room unheated.

## Cooling limits

The [condensation guard](how-it-works.md#cooling-and-condensation) keeps every cooling loop above the dew point.
Three optional limits add to it:

- A **Condensation switch** on a pump or a loop stops cooling at once while it is on or unavailable.
- The **Cooling surface minimum** of a loop with a surface sensor, 20 °C by default, keeps a cooled floor comfortable; a ceiling may use a lower value.
- The **Maximum humidity for cooling** of a zone, 70 % by default, stops cooling while the zone is more humid.

Empty fields mean the defaults; only the [plant file](plant-file.md) turns the surface minimum or the humidity limit off.
