# Configuration

This page walks through every Hydronicus form: creating a Plant, arming its outputs, changing the Plant, and adding and changing zones.
[How Hydronicus works](how-it-works.md) explains what the settings do, and [the plant file](plant-file.md) describes the same Plant as YAML.

## Before you start

Try a new Plant on a disposable or staging Home Assistant instance first, or with synthetic entities such as the [trial kit](../README.md#first-simulated-plant).

Have these entities ready:

- A `switch` or `valve` entity for every valve Hydronicus opens and closes.
- A `switch` entity for every pump Hydronicus switches.
- Optionally, a `switch` that asks the heat pump or boiler for heat or cooling, and a `select` that switches it between heating and cooling.
- A temperature sensor for every zone, either named in the settings of the zone's Home Assistant areas, as described in [Areas](#areas), or chosen in the zone form.
- For cooling: a humidity sensor for every zone that cools, and a supply temperature or surface temperature sensor as the condensation reference of every loop that cools.

Hydronicus never offers its own entities in these forms, because a Plant that reads its own output would feed back into itself.

## Create a Plant

Open **Settings > Devices & services > Add integration** and search for **Hydronicus**.
Choose **Guided setup** to build the Plant form by form, or **Import a plant file** to paste a [plant file](plant-file.md).
Both end with **Review the Plant**, and nothing is created before you submit it.

### Guided setup

Guided setup asks for the Plant and its source, then its pumps, then its zones one by one with their loops, then the loops no zone owns.

1. **The Plant and its source**.
   Enter the **Plant name**, which names the Plant's device and its Plant-wide entities.
   If Hydronicus asks a heat pump or boiler for heat, choose its **Source request switch** and give it a **Source name**, such as `Heat pump`.
   Leave the request switch empty for a source that runs on its own controls; valves and switched pumps still run on demand.
   If the source switches between heating and cooling through a select, choose it as the **Source mode select**; it needs a request switch.
   The collapsed **Timing** section holds the **Mode dwell** (3600 seconds), the **Source post-run** (180 seconds), and the **Source minimum on time** and **Source minimum off time** (600 seconds each).
2. **Source modes**, only with a mode select.
   Choose the **Heating option** and the **Cooling option** of the select.
   The form lists the options the select offers now.
3. **Pump**.
   Enter the **Pump name**.
   Choose the **Pump switch** for a pump Hydronicus switches, or leave it empty for a pump the source runs by itself, such as a heat pump's own circulator; Hydronicus never commands that one, and it needs a source.
   Set the **Overrun**, how long a switched pump keeps running after heating ends (180 seconds).
   Set the **Minimum flow** to **Needs an open loop**, or to **A separator guarantees its flow** when a hydraulic separator, buffer, or bypass gives the pump a path whatever the loops do.
   Optionally choose the **Supply temperature sensor**, the water temperature this pump supplies, which lets its loops cool.
   Turn on **Add another pump** to add the next one.
4. **How is your home zoned?**
   Choose **One zone per area** to give each chosen Home Assistant area a zone of its own, **Zones that cover several areas** to group areas into zones, such as one zone per floor, or **Zones without areas** for zones with their own sensors or an existing thermostat.
   With **One zone per area**, **Choose the areas** lists every area and starts with the ones that name a temperature sensor.
5. **Add a zone**.
   Enter the **Zone name**, or leave it empty to use the name of the one chosen area, or of the floor every chosen area is on.
   Choose the **Areas** the zone covers; with one zone per area the form is filled in with the next area.
   Add **Extra temperature sensors** and **Extra humidity sensors** that are not named by the chosen areas, such as a floor probe.
   Choose how to **Combine temperatures by**: **Mean**, **Minimum**, or **Maximum**.
   Choose an **Existing thermostat** to let an existing climate entity own the zone's demand, or leave it empty for a digital thermostat that Hydronicus provides.
   The collapsed **Digital thermostat presets** section sets the **Comfort**, **Eco**, and **Away** targets; leave a preset empty to leave it out.
6. The loop form.
   Enter the **Loop name**, such as `Ceiling` or `Floor`.
   Choose the **Valves** that open together for the loop, or none for a loop whose pump is its only control.
   Choose the **Pump** that moves the loop's water.
   Choose the **Modes**: **Heating**, **Cooling**, or both; cooling needs the pump's supply temperature sensor or the loop's **Surface temperature sensor**.
   Set the **Valve opening time**, how long every valve of the loop takes to open before its pump may start (180 seconds).
   Leave **Valves** and **Pump** empty to give the zone no loop of its own, for a zone that only a plant loop serves.
7. The zone's menu.
   Choose **Add another loop to this zone**, such as an underfloor loop next to a ceiling loop, **Add another zone**, or **Continue** once every zone is added.
   With one zone per area, **Add another zone** moves to the next chosen area, and **Continue** appears after the last one.
8. **Plant loops**.
   Choose **Add a plant loop** for a loop that no zone owns, or **Continue**.
   A plant loop has the same fields as a zone loop, plus **Runs**: **With the source** runs it whenever the source is requested, such as a towel dryer, and **With zones** runs it while any of the chosen **Zones** demands, such as a loop that several zones share.
9. **Min-flow loops**, once for every pump the source runs that needs an open loop.
   Choose the **Loops to hold open** whenever no other loop of that pump is ready while the pump may run; a ceiling loop is a good choice.
   Or turn on **A separator guarantees its flow** when a separator, buffer, or bypass protects the pump.
10. **Review the Plant**.
    The review lists the source, the pumps, the zones with their areas, thermostats, and loops, the plant loops, and the number of outputs.
    Its warnings point at what may not work as intended, such as an area without a temperature sensor, a zone that no loop serves, or a pump that drives no loop.
    Warnings never block; submit to create the Plant.

Every form checks the whole Plant as it would be stored, with the same rules as a plant file, and shows a problem on the field it belongs to.

Hydronicus makes each object's slug from its name when it is created, such as `living_area` for `Living area`, and the slug never changes.
Entity IDs come from the names, such as `climate.living_area`, so choose names you want to keep.

### Import a plant file

Choose **Import a plant file** and paste the file into **Plant file**.
The [plant file reference](plant-file.md) describes the format, and **Review the Plant** shows the Plant before it is created.
A file that carries the ID of a Plant that is already set up is refused; remove that Plant first, or replace it from the file instead.

## Arm the outputs and start

A new Plant commands nothing: no output is armed and **Control equipment** is off, so it runs in Dry run.

1. Open **Configure** on the Plant's entry, which opens the Plant settings, and choose **Arm outputs**.
   **Armed outputs** lists every output with its role, such as `Valve of Living area / Ceiling: switch.living_area_ceiling_valve` or `Pump Floor: switch.floor_pump`.
   Check each entity against the device it controls, then check it here and submit.
   A loop runs only when every output it needs is armed, and unchecking an output disarms it.
2. Set the Plant's **Mode** select to heat or cool.
3. Set each zone's thermostat to the same mode.
   A new digital thermostat starts off with a target of 21 °C.
4. Watch the Plant in Dry run: the **Status** sensor's `proposed` attribute shows the state Hydronicus would give each output, and its `reasons` attribute explains each decision.
5. Turn on the **Control equipment** switch when the proposals are right, and Hydronicus starts commanding the armed outputs.

Turning **Control equipment** off stops the armed equipment in order, and then the Plant returns to Dry run.
Arming and **Control equipment** are kept in the Plant's settings, so they survive restarts, and changing them never reloads the Plant.
See [safety limits](safety.md) before you turn **Control equipment** on for real equipment.

**Show the plant file** in the Plant settings shows the Plant's [plant file](plant-file.md), which imports as the same Plant with the same entity IDs.

## Change the Plant

Open **Reconfigure** on the Plant's entry.
The menu says whether the stored Plant is valid, and offers:

- **Plant and source**: the forms of steps 1 and 2 of guided setup.
- **Pumps**: choose a pump to change, or `Add a pump`.
  The pump form also shows **Min-flow loops** for a pump the source runs, once loops use it, and **Remove this pump**.
  A pump that a loop still uses cannot be removed; move or remove those loops first.
- **Plant loops**: choose a plant loop to change, or `Add a plant loop`.
  The loop form also shows **Remove this loop**.
- **Replace from a plant file**: paste a plant file of this Plant to replace the whole Plant, zones included.
  Zones are added, changed, and removed by their slugs.
  The file must carry this Plant's ID, or no ID.
- **Review and save**: first asks for any min-flow loops still missing, then **Save the changes** lists the zones added, removed, and changed, the Plant settings that change, and the outputs added and removed, with the warnings of the new Plant.

Nothing is stored until you submit **Save the changes**.
The Plant then reloads.
Removed outputs are disarmed, and new outputs wait for you to arm them.
If a removed output was running, the Plant first stops the equipment of its previous configuration, as [safety limits](safety.md#reloads-restarts-and-changes) describe.

A pump the source runs that needs an open loop may have no loops yet to hold open, such as a new pump, one that the source now runs instead of a switch, or one whose min-flow loop you removed.
The menu then says so, and **Review and save** asks for its **Loops to hold open** first, as guided setup does, once a loop uses the pump.
A plant loop added in the same session counts, and so does a zone loop that already uses the pump.
If no loop uses the pump yet, **Review and save** opens **A pump without a loop** instead:
**Add a plant loop** for the pump now, or, for a zone loop, **Change the pump** to **A separator guarantees its flow** for now, or remove it.
A zone loop can use the pump only once it is saved, so add it in the zone's **Reconfigure**, then change the pump's **Minimum flow** back and choose its **Min-flow loops**.

## Zones

Each zone is a subentry of the Plant, listed under the Plant's entry.

- **Add zone** adds a zone: the zone form of step 5, then a loop form, which you may leave empty, then the zone's menu.
- **Reconfigure** on a zone opens its zone form, then its menu: **Zone settings** for the name, areas, sensors, and thermostat, **Loops** to choose a loop to change or `Add a loop`, and **Save**.
  A loop's form also shows **Remove this loop**.
- **Delete** on a zone removes it with exactly its own loops and valves.

A zone is saved only as part of a valid Plant, checked with the same rules as setup, and saving it reloads the Plant.
A new zone's valves are new outputs, so its loops wait until you arm them, while the rest of the Plant keeps running.
Editing a thermostat, a sensor, a name, or a timing never changes what is armed.

Deleting a zone also removes it from any plant loop that runs with it and drops its loops from any pump's min-flow loops.
Deleting a zone whose loops are running first stops the equipment of the previous configuration, then runs the Plant without the zone.
If that leaves a pump the source runs without a min-flow loop, the Plant is no longer valid: it stops its equipment in order, then only observes, and a Repair opens its **Reconfigure** to fix it.

## Areas

Home Assistant lets each area name the sensor that represents its temperature and the one that represents its humidity.
Set them in **Settings > Areas, labels & zones**: open the area, choose **Area settings** in its menu, and choose the **Temperature sensor** and the **Humidity sensor**.
The area settings offer only the sensors that belong to the area, so first set the sensor's **Area** in its entity settings, or put its device in the area.

A zone that covers an area follows the sensors the area names:

- The zone uses its extra sensors first, then the temperature sensor and the humidity sensor that each of its areas names.
- Hydronicus re-reads the areas on every evaluation, so choosing another sensor in an area's settings, clearing one, or removing a covered area takes effect at once, without a reload.
- An area that is missing or names no sensor adds no reading, and it never stops the Plant from loading; a Repair reports it instead.
- Renaming a sensor's entity ID does not update the area, because Home Assistant keeps the old ID in the area settings; a Repair then asks you to choose the sensor again.
- An area sensor that Hydronicus itself provides, such as a zone's **Combined temperature**, is ignored, and a Repair names it.

By default an area's sensors are optional: a stale or unavailable one is left out, so one flat battery in a zone of five rooms does not stop the other four.
A reading is stale after 1800 seconds without a report.
The [plant file](plant-file.md#areas) can make an area's sensors required or change their maximum age; the forms keep those settings when you edit the zone.

A zone that covers exactly one area puts its thermostat in that area when the thermostat is first created, so it appears on the area's page and answers voice commands such as "set the bedroom to 21".
Only the thermostat goes in the area; the zone's device stays unassigned, so its other entities are not offered as the area's sensors.
A zone over several areas puts nothing in an area, and moving the thermostat later is your choice.

An area may be covered by several zones, such as a hall between two floors; its sensors then count in each of them, and the review mentions it.

The **Combined temperature** sensor of a zone lists its areas with the sensors they resolve to and their readings in its `areas` attribute.

## Sensors and aggregation

A zone combines its usable temperature readings by **Combine temperatures by**: **Mean**, **Minimum**, or **Maximum**.
An extra sensor chosen in the zone form is required: when it is stale or unavailable, the zone is blocked and does not call.
The plant file can make an extra sensor optional or change its maximum age, and the forms keep those settings.
A zone that cools uses its highest humidity reading and its highest temperature for its worst-case dew point.

## Thermostats

A zone has exactly one thermostat.

A digital thermostat is the zone's climate entity, which Hydronicus provides.
It restores its target, preset, and mode after a restart, starts off with a target of 21 °C when new, and offers heating, plus cooling when a loop of the zone cools.
It demands heating 0.3 K below its target and stops 0.1 K above it, and cooling the same way the other side.
The [plant file](plant-file.md#thermostats) can change these deltas, add minimum on and off times, and change the proportional band of the demand level.

An existing thermostat is an existing Home Assistant climate entity that owns the zone's demand.
Hydronicus reads only its `hvac_action`: heating or preheating calls for heat, cooling calls for cooling, and idle or off calls for nothing.
Hydronicus never commands it, and an unavailable or unknown action blocks the zone.
Make sure the existing thermostat does not itself switch a valve or pump that Hydronicus commands.

A zone's thermostat mode counts only when it matches the Plant mode.

## Observation units

Hydronicus evaluates every temperature in °C and every humidity in percent, whatever unit system Home Assistant displays.
It reads each sensor's `unit_of_measurement` and converts the value when it reads it.

| Observation | Unit | Result |
| --- | --- | --- |
| Temperature | `°C` | Used as reported. |
| Temperature | `°F` or `K` | Converted to °C. |
| Temperature | No unit | Taken as °C. |
| Temperature | Any other unit | Unusable. |
| Humidity | `%` or no unit | Used as relative humidity. |
| Humidity | Any other unit | Unusable. |

After conversion, a reading must also be physically plausible.
The ranges are inclusive and catch sensor faults, such as -127 °C from a disconnected probe; they are not comfort or safety limits.

| Observation | Plausible range |
| --- | --- |
| Zone temperature and loop surface temperature | -50 to 100 °C |
| Pump supply temperature | -50 to 150 °C |
| Humidity | 0 to 100 % |

An unusable reading counts like an unavailable one: a required sensor blocks its zone, an optional one is left out, and a condensation reference blocks its loop's cooling.

## Checklist

Before you turn **Control equipment** on:

- Every armed output is the entity of the device its role names.
- Every zone shows the temperature you expect on its **Combined temperature** sensor.
- Every loop that cools has a condensation reference, and every zone that cools shows a plausible **Dew point**.
- Every pump the source runs has **A separator guarantees its flow** only if a separator, buffer, or bypass really protects it.
- The Dry run proposals follow the order you expect: valves, then pumps, then the source.
- The physical protections of the plant work without Home Assistant, as [safety limits](safety.md) describes.
