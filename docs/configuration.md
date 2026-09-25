# Configuration and simulation

This guide describes how to create a Plant, add and edit rooms and loops, and change the Plant settings.
It uses synthetic Home Assistant entities so that a first test cannot operate real equipment.

The UI and this guide speak of rooms and loops.
A room is one Comfort Zone with its thermostat, its sensors, and its private loops and valves.
A loop is one Hydraulic Circuit: a water path through one or more valves and one pump.
Pumps, shared valves, shared loops, sources, and the source selector are Plant equipment, owned by the Plant rather than by a room.

## Prepare synthetic entities

Create the test entities in a disposable Home Assistant instance or a separate staging configuration.
Do not use a production valve or pump entity for a first test.

Hydronicus needs these entity types:

| Purpose | Accepted entity type | Trial kit entity |
| --- | --- | --- |
| Room temperature | `sensor` with the `temperature` device class | `sensor.hydronicus_trial_bedroom_temperature` |
| Valve actuator | `switch` or `valve` | `switch.hydronicus_trial_bedroom_valve` |
| Pump actuator | `switch` | `switch.hydronicus_trial_pump` |

The quickest start is the [trial kit](examples/trial): a Home Assistant package with synthetic entities for two rooms and one pump, and a plant file bound to them.
The README's [first simulated Plant](../README.md#first-simulated-plant) shows how to load the package and create the Plant from it.

Home Assistant Template helpers can also create sensors and switches through the UI.
See the [Home Assistant Template documentation](https://www.home-assistant.io/integrations/template/) for the current helper and YAML syntax.
Use the entity pickers in the flows rather than copying entity IDs from this guide into a production configuration.

Every new Plant starts in Dry run, so Hydronicus observes the actuator entities but does not switch them until the Plant setting is deliberately changed.

## Create a Plant

Open **Settings > Devices & services > Add integration** and search for **Hydronicus**.
The first menu offers two ways to create a Plant:

- **Guided setup** asks for the Plant and its pump, then one form per room.
- **Import a plant file** rebuilds a Plant from a [plant file](plant-file.md), with the same entity IDs.

### Guided setup

Guided setup takes one menu, one Plant form, one form per room, and a review.

1. Choose **Guided setup**.
2. In **Name the Plant**, enter the **Plant name** and choose the **Pump entity** that the loops of every room share.
   **Pump options** holds the **Pump overrun**, which is how long the pump keeps running after heating demand ends, before the valves close.
   Cooling stops the pump without overrun.
3. In **Add a room**, describe one room:
   - **Room name** names the room's thermostat and entities.
   - **Temperature sensors** are combined into the room temperature.
   - **Existing climate thermostat** is optional; when set, that climate entity owns the room's demand, and the temperature sensors become optional.
   - **Loop valves** are the switches or valves of the room's own loop.
     Hydronicus creates the loop, names it after the room, such as `Bedroom loop`, and names its valves after the loop, such as `Bedroom loop valve`.
   - **Cooling** is an optional, collapsed section that lets the room's own loop cool too.
     Turn on **Cool this room**, choose the room's **Humidity sensors**, and choose a **Supply temperature sensor** or a **Surface temperature sensor**, or both, as the loop's condensation reference.
     **Condensation margin** defaults to 2.0 °C, as in the loop form.
     Cooling also needs the room's **Temperature sensors**, even when an existing climate thermostat owns the room.
   - **Add another room** shows the form again for the next room.
     Leave it off after the last room.
   From the second room on, the form lists the rooms added so far.
4. **Review the Plant** lists the rooms, how they connect, and the warnings.

Under How it connects, the review shows one line per loop and one per room, such as `Bedroom loop opens Bedroom loop valve, then starts Circulation pump.` and `Bedroom is heated by Bedroom loop.`
A room whose loop cools reads `Bedroom is heated and cooled by Bedroom loop.`
When the rooms share the pump, the review warns that the shared pump limits independent control.
A warning other than unused equipment must be confirmed with **I understand these warnings** before the Plant is created.
Later room, loop, and plant file edits ask only about warnings that the edit introduces.

The Plant is created in Dry run, with one room entry per room.
Guided setup names the pump `Circulation pump`; rename it, add more pumps, or change its options later in the Plant settings.

### Import a plant file

1. Choose **Import a plant file**.
2. Paste the file into **Plant file** and submit.
   An empty editor, or YAML that the editor cannot read, is reported at the top level, and the editor marks the line with the YAML problem.
3. **Review the imported Plant** lists the Plant name, the rooms, how they connect, and the warnings.
   Confirm a warning other than unused equipment with **I understand these warnings**, and submit.

The Plant is created in Dry run, with one room entry per room and one source entry per source.
An invalid file keeps the form open and names the path of the problem, such as `rooms.bedroom.loops.bedroom_loop.pump`.
See [the plant file reference](plant-file.md) for the format, the IDs, and the errors.

## Rooms

Every room appears as a **Room** entry under the Plant, and **Add room** adds another.
A new room needs the Plant to have a pump.

The **Add a room** form has the same fields as in guided setup, plus two that appear only when they matter:

- **Pump** appears when the Plant has two or more pumps; with one pump, the room's loop uses it.
- **Shared loops** appears when the Plant has shared loops, which are Plant loops that also deliver heat to this room.

A room needs **Loop valves** or at least one of the **Shared loops**.
The **Cooling** section applies to the room's own loop, so turning on **Cool this room** needs **Loop valves**.
A room served only by shared loops is refused with a message to choose Loop valves or leave cooling off, because a shared loop is Plant equipment that only the plant file edits.
To make an existing room cool, use **Sensor aggregation and humidity** for its humidity sensors and the **Cooling** section of its loop.
Saving a room returns the Plant to Dry run.

### Thermostat owner

A room has exactly one thermostat owner.

Leave **Existing climate thermostat** empty when Hydronicus should own the target, presets, HVAC mode, hysteresis, and thermostat timing.
Hydronicus then publishes a climate entity for the room.

Choose an **Existing climate thermostat** when another integration owns those thermostat decisions.
Hydronicus consumes only its `hvac_action` as the demand signal, and never commands it.
The external target and current temperature attributes are diagnostic only.
External idle or off releases demand immediately.
External cooling still requires explicit room humidity and loop safety observations.

An external thermostat must not independently command an actuator also configured as Hydronicus-owned.
Hydronicus does not infer the external integration's actuator or support externally actuated or valve-less delivery routes.

### Edit a room

Open the room's **Reconfigure** action to reach the room's edit menu, titled with the room name, such as `Edit Bedroom`, with these options:

- **Name, thermostat owner, and sensors** changes the **Room name**, the **Existing climate thermostat**, the **Temperature sensors**, and the **Shared loops**.
  Switching to an existing climate thermostat drops the Hydronicus thermostat settings, and switching back starts from defaults.
- **Thermostat settings** appears for a Hydronicus thermostat and sets the **Heating start hysteresis**, **Heating stop hysteresis**, **Minimum active duration**, **Minimum idle duration**, the **Comfort preset target**, **Eco preset target**, and **Away preset target**, and the **Cooling** hysteresis.
- **Sensor aggregation and humidity** sets the **Temperature aggregation** and the **Humidity sensors**, and **Edit sensor metadata** opens one form per temperature sensor.
- **Add a loop** adds another private loop to the room.
- **Edit or remove a loop** appears when the room has a private loop.

Deleting a room entry removes the room with its routes and its private loops and valves.
Plant equipment stays, so deleting a room always leaves a valid Plant; a pump or shared loop that no other room uses remains as unused equipment.
When the Plant is outside Dry run, Hydronicus completes the ordered transition to Dry run before the room leaves the graph.

### Sensors and aggregation

Selected temperature sensors are required by default.
Turn on **Edit sensor metadata** to set each sensor's **Required sensor**, **Aggregation weight**, **Calibration offset**, **Maximum age**, and **Designated reference sensor** status.
An unusable required sensor blocks the room immediately.
An unusable optional sensor is excluded and reported, but the room still blocks if no usable observation remains.

**Temperature aggregation** offers these policies:

- **Mean** calculates the arithmetic mean.
- **Median** selects the middle value after sorting the readings.
- **Heating-oriented minimum** uses the lowest reading.
- **Cooling-oriented maximum** uses the highest reading, which suits rooms that cool.
- **Designated reference** uses the one sensor marked as the reference.
- **Weighted mean** applies the positive weights set in the sensor metadata.

Designated reference and weighted mean depend on per-sensor metadata, so choose them in **Choose sensor aggregation** after completing **Edit sensor metadata**.

Hydronicus starts a fresh thermostat at 21.0 °C and HVAC mode off.
Use the room's climate entity to change its target and mode after setup.
The heating start and stop hysteresis define the band around the runtime target.
Minimum active duration holds an already-requested room until its deadline unless a required sensor blocks it.
Minimum idle duration prevents a satisfied room from requesting heat again until its deadline.
Changing the target or preset reevaluates demand immediately without bypassing a remaining duration deadline.

## Loops and valves

A room's first loop comes from **Loop valves** on the room form, and the form's **Cooling** section can make that loop cool.
**Add a loop** and **Edit or remove a loop** open **Configure a loop**:

- **Loop name** names the loop.
- **Valves** are the switches or valves that belong to this room.
  A new entity becomes a new valve, and a removed one is deleted unless another loop of the room still uses it.
- **Shared valves** appears when the Plant has shared valves, and adds Plant valves that this loop also needs open.
- **Pump** is the pump that circulates water through the loop.
- **Valve opening time** applies to every room valve of the loop: the pump may start only after the valves had this long to open.
- **Edit valve feedback** opens one **Edit valve feedback** form per room valve, with **Valve readiness feedback**, **Valve position feedback**, and **Valve position feedback maximum age**.
- **Cooling** enables cooling for the loop and sets its condensation protection.
- **Remove this loop** appears when editing, and removes the loop and the room valves that no other loop of the room uses.

A valve keeps its identity, its entities, and its feedback settings as long as its entity stays selected.
Every chosen valve must open before the pump may run.

## Plant settings

Select **Configure** on the Plant entry to open **Plant settings**, a menu that names the Plant, with these options:

- **Dry run** turns Dry run on, or leaves it after confirming the exact heating outputs.
- **Add a pump** adds a pump with its **Pump name**, **Pump entity**, **Pump overrun**, and optional **Feedback** entities.
- **Edit or remove a pump** changes a pump, and **Remove this pump** removes a pump that no loop uses.
  Removing a pump that a loop still uses is refused with the names of those loops.
- **Show the plant file** shows the Plant as a [plant file](plant-file.md), to back it up or rebuild it elsewhere.
- **Edit plant file** edits the whole Plant as a plant file, including shared loops, shared valves, sources, and the source selector.
  **Review plant file changes** lists what the file adds, removes, renames, moves, and changes before anything is saved.

Every change to rooms, loops, valves, or pumps returns the Plant to Dry run.
Leaving Dry run requires **I understand these outputs may be controlled** for the exact output list shown.
A repair for a missing pump entity opens the same **Plant settings** menu.

The `hydronicus.export_plant` action returns the same plant file as **Show the plant file**.

### What the UI edits and what the plant file edits

| Object | Created and edited in |
| --- | --- |
| Room, its thermostat and sensors | Guided setup, **Add room**, and the room's edit menu. |
| Private loop and private valve | The room form and the room's loop steps. |
| Pump | Guided setup and **Plant settings**. |
| Source | **Add source**, the source entry, or the plant file. |
| Shared loop, shared valve, source selector | The plant file only; room and loop forms can select existing shared loops and shared valves. |
| Dry run | **Plant settings** only. |

### Sources

**Add source** adds a heat source for recommendations, with its **Source type**, **Priority**, **Availability entity**, and optional **Source demand entity**.
A **Temperature-qualified buffer** also needs a **Buffer temperature entity** and a **Minimum buffer temperature**.
Direct source demand can execute only outside Dry run and after a valid pump path exists.

## Observe the result

After setup, Hydronicus exposes entities associated with the Plant.
Each room, valve, pump, and source is a device named after the object alone, under the Plant device that carries the Plant name.
Entity IDs come from those device names, so the trial Plant has entities such as `climate.bedroom`, `binary_sensor.bedroom_heating_demand`, and `binary_sensor.bedroom_loop_valve_requested`, while Plant-wide entities such as `select.trial_plant_requested_mode` keep the Plant name.
The room's combined temperature is `sensor.bedroom_combined_temperature`, so it does not take the entity ID of a room sensor such as `sensor.bedroom_temperature`.
If an entity ID is already taken, Home Assistant adds a suffix such as `_2`.

The useful states for a first simulation are:

- The room climate entity, which reports the aggregate current temperature and target.
- The room **Heating demand** binary sensor, which reports the calculated virtual heat demand.
- The room **Combined temperature** sensor, which reports the aggregate the controller uses and identifies usable and excluded observations in its attributes.
- The valve requested and pump requested binary sensors, which report virtual requests.

Explanations and reasons are diagnostic entities, listed under **Diagnostic** on the device page:

- The room **Blocked** binary sensor and **Blocked reason** sensor, which expose fail-closed sensor decisions without parsing prose.
- The room **Explanation** sensor, which reports why demand is requested, idle, or blocked.
- The **Topology preview** sensor, which reports room and loop counts, such as `2 rooms, 2 loops`, and exposes compiled logic and structured warnings as separate attributes.

Change the synthetic temperature below the target and wait for the configured virtual valve opening time.
The virtual sequence is:

```text
room demand -> loop request -> valve opening -> valve ready -> pump requested
```

Raise the synthetic temperature above the stop threshold.
The pump enters virtual overrun before it becomes idle, and the valve closes after the pump no longer needs protection.

No physical service call is dispatched while Dry run remains enabled.

Cooling demand, condensation blocking, source recommendations, and source changeover reasoning are also visible in Dry run when their required objects and observations are configured.
A room has cooling entities only when it routes to a loop with cooling turned on, which is also when its thermostat offers cool modes.
The Plant has source entities, such as **Recommended source** and **Source changeover**, only when it has at least one source.
When a change removes an object's reason for an entity, such as turning off a loop's cooling, the reload removes that entity from Home Assistant.
Source-selector operations remain Dry run only.
When Dry run is off, valves and pumps in heating and cooling, and a configured direct source-demand output, can execute after the required confirmation and pump-path checks.

Every relationship is stored by a generated identifier rather than by a display name.
Renaming an object keeps its relationships, so always open the topology preview after a change rather than relying on names.

## Observation units

Hydronicus evaluates every temperature in degrees Celsius and every humidity in percent, whatever unit system Home Assistant displays.
It reads each observation's `unit_of_measurement` attribute and normalizes the value once, when the observation is read.
The same rules apply to room temperature sensors, room humidity sensors, loop supply and surface temperature sensors, and source temperature inputs.

| Observation | Accepted unit | Result |
| --- | --- | --- |
| Temperature | `°C` | Used as reported. |
| Temperature | `°F` or `K` | Converted to Celsius. |
| Temperature | No unit | Assumed to be Celsius. |
| Temperature | Any other unit | Unusable. |
| Humidity | `%` or no unit | Used as relative humidity in percent. |
| Humidity | Any other unit | Unusable. |

A sensor without a unit is assumed to report Celsius, so give a unit-less template sensor a Celsius value or add the correct `unit_of_measurement`.
An unusable observation takes the same path as an unavailable or non-numeric one, so a required sensor blocks its room and the controller fails closed.
An existing external climate entity reports its current and target temperatures in the Home Assistant unit system, and Hydronicus converts them to Celsius as well.
Hydronicus-owned sensors, diagnostics, and the Plant card data carry Celsius values, and Home Assistant converts the entity values for display.

### Plausible observation ranges

After unit conversion, each reading must also fall inside a physically plausible range.
A reading outside its range is unusable and takes the same fail-closed path as an unsupported unit.
The ranges are inclusive and fixed; they catch sensor faults, not comfort or safety limits.

| Observation | Plausible range | Why |
| --- | --- | --- |
| Room temperature | -50 to 100 °C | Room air, from unheated spaces to saunas. |
| Loop surface temperature | -50 to 100 °C | Heated or cooled floors, walls, and ceilings stay within room-air limits. |
| Loop supply temperature | -50 to 150 °C | Pressurized boilers and district heating can supply water above 100 °C. |
| Source temperature | -50 to 150 °C | Buffer and boiler water follows the same limits as supply water. |
| Room humidity | 0 to 100 % | Relative humidity cannot leave this range. |

The ranges reject common fault readings, such as 0 K (-273.15 °C) from a misconfigured template or -127 °C from a disconnected one-wire probe.
The blocked reason names the rejected value, for example `implausible value -273.15 °C`.

## Shared equipment

Choose the same pump for several loops, or the same shared valve in several loops, when the equipment is physically shared.
Hydronicus keeps the actuator requested while any active loop still consumes it.
It warns when a shared valve or a shared pump prevents independent hydraulic control, so a manifold whose rooms share one pump shows that warning when it is created.
Later edits ask you to confirm only the warnings they introduce.
Shared loops and shared valves are Plant equipment, created in the [plant file](plant-file.md).

Read [how Hydronicus works](how-it-works.md) for diagrams and the complete ownership rules.

## One live Plant per actuator entity

One actuator entity belongs to one live Plant.
Sharing equipment between loops happens inside one Plant, never across Plants.
A valve, pump, or source-demand entity that two Plants bind can be commanded by only one of them at a time, because two live Plants would switch it against each other and either one's Safe shutdown could stop equipment the other needs.
A Plant counts as live when it is loaded and not in Dry run.
Plants in Dry run may bind the same entities, for example to compare a draft configuration with the live one.
When you choose a valve, pump, or source-demand entity that another Plant already binds, the setup, import, room, source, pump, and plant file reviews list it as a warning that names the other Plant.
You confirm it with **I understand these warnings** before saving.
Turning Dry run off is refused while another live Plant controls one of the same entities, and the error names that Plant and the shared entities.
If two Plants that are both set to run outside Dry run share an entity, the first one to finish claiming its outputs during setup runs live.
The other one is held in Dry run before it sends any command, and a repair explains the conflict.
Which Plant claims first is decided when they set up, so it is usually the same at every start, but a Plant whose setup is delayed or retried can lose to a later one.
Holding a Plant does not change its settings: its Dry run setting and its confirmed outputs are kept.
The held Plant resumes by itself, through a normal reload, once the conflict is gone, for example when the live Plant enters Dry run, is unloaded, is removed, or fails to set up.
If several held Plants share the same outputs, only the first of them in Home Assistant's entry order resumes, and the others stay held.
While a Plant is held, its Dry run binary sensor is on, its `held_by_output_conflict` attribute is true, and its `held_by_plant` attribute names the live Plant.
Turning Dry run on for a held Plant stores Dry run, so it no longer resumes by itself.

## Configuration checklist

Before accepting a simulated Plant, check all of the following:

- Every temperature sensor is numeric and available.
- Every temperature sensor reports `°C`, `°F`, `K`, or a Celsius value without a unit.
- Every reading falls inside its [plausible range](#plausible-observation-ranges).
- Every selected sensor belongs to the intended test configuration.
- Each room has at least one enabled loop.
- Each loop has a valid valve path and pump.
- Shared equipment is intentional and documented for the test.
- The topology preview describes the expected route and sequence.
- The Plant remains in Dry run for the first test.
- No real equipment is being used as a test substitute.

If validation rejects a proposed object, review the object references and ownership boundaries before trying a different name.
Hydronicus rejects inconsistent topology, and a room that no enabled Delivery Route leaves, rather than silently guessing the intended relationship.
A loop, valve, or pump that no enabled Delivery Route reaches is accepted, reported as unused equipment, and never requested.
