# Configuration and simulation

This guide describes a generic first Plant and the topology choices currently represented by Hydronicus.
It uses synthetic Home Assistant entities so that the test cannot operate real equipment.

## Prepare synthetic entities

Create the test entities in a disposable Home Assistant instance or a separate staging configuration.
Do not use a production valve or pump entity for a first test.

Hydronicus currently needs these entity types:

| Purpose | Accepted entity type | Example name |
| --- | --- | --- |
| Zone temperature | Numeric `sensor` | `sensor.simulated_zone_temperature` |
| Valve actuator | `switch` or `valve` | `switch.simulated_zone_valve` |
| Pump actuator | `switch` | `switch.simulated_zone_pump` |

The example names are placeholders for a disposable test only.
Use the entity picker in the flow rather than copying these names into a production configuration.

Home Assistant Template helpers can create sensors and switches through the UI.
Manual YAML is also supported by Home Assistant's Template integration.
See the [Home Assistant Template documentation](https://www.home-assistant.io/integrations/template/) for the current helper and YAML syntax.
For a disposable fixture, copy [examples/simulated-entities.yaml](examples/simulated-entities.yaml) into the test configuration and restart or reload the relevant helpers.

The actuator entities are observed by the current release.
Every Plant created through the UI starts in Dry run, so Hydronicus does not switch them until the Plant setting is deliberately changed.

## Create the first Plant

Open **Settings > Devices & services > Add integration**, search for **Hydronicus**, and enter a Plant name.
Leave **Dry run** enabled for the first test.
The flow stores the Plant with Dry run enabled by default.

### Add a Comfort Zone

Give the Zone a descriptive generic name such as `Simulated zone`.
Choose the thermostat owner before entering Zone details.

Choose **Hydronicus digital thermostat** when Hydronicus should own the target, presets, HVAC mode, hysteresis, and thermostat timing.

Choose **Existing Home Assistant climate entity** when another integration owns those thermostat decisions.

An external thermostat must not independently command an actuator also configured as Hydronicus-owned.

Hydronicus does not infer the external integration's actuator or support externally actuated or valve-less delivery routes.

For a Hydronicus thermostat, select one or more numeric temperature sensors.
Selected sensors are required by default.
Enable detailed sensor editing to configure each observation as required or optional and set its calibration offset, maximum age, aggregation weight, or designated-reference status.
An unusable required sensor blocks the Zone immediately.
An unusable optional sensor is excluded and reported, but the Zone still blocks if no usable observation remains.
Select one of the available policies:

- **Mean** calculates the arithmetic mean.
- **Median** selects the middle value after sorting the readings.
- **Heating-oriented minimum** uses the lowest reading.
- **Cooling-oriented maximum** supports cooling shadow evaluation, but physical cooling starts are not supported or authorized in this release.
- **Designated reference** uses the one observation marked as the reference.

### Observation units

Hydronicus evaluates every temperature in degrees Celsius and every humidity in percent, whatever unit system Home Assistant displays.
It reads each observation's `unit_of_measurement` attribute and normalizes the value once, when the observation is read.
The same rules apply to Zone temperature sensors, Zone humidity sensors, Circuit supply and surface temperature sensors, and Source temperature inputs.

| Observation | Accepted unit | Result |
| --- | --- | --- |
| Temperature | `°C` | Used as reported. |
| Temperature | `°F` or `K` | Converted to Celsius. |
| Temperature | No unit | Assumed to be Celsius. |
| Temperature | Any other unit | Unusable. |
| Humidity | `%` or no unit | Used as relative humidity in percent. |
| Humidity | Any other unit | Unusable. |

A sensor without a unit is assumed to report Celsius, so give a unit-less template sensor a Celsius value or add the correct `unit_of_measurement`.
An unusable observation takes the same path as an unavailable or non-numeric one, so a required sensor blocks its Zone and the controller fails closed.
An existing external climate entity reports its current and target temperatures in the Home Assistant unit system, and Hydronicus converts them to Celsius as well.
Hydronicus-owned sensors, diagnostics, and the Plant card data carry Celsius values, and Home Assistant converts the entity values for display.

### Plausible observation ranges

After unit conversion, each reading must also fall inside a physically plausible range.
A reading outside its range is unusable and takes the same fail-closed path as an unsupported unit.
The ranges are inclusive and fixed; they catch sensor faults, not comfort or safety limits.

| Observation | Plausible range | Why |
| --- | --- | --- |
| Zone temperature | -50 to 100 °C | Room air, from unheated spaces to saunas. |
| Circuit surface temperature | -50 to 100 °C | Heated or cooled floors, walls, and ceilings stay within room-air limits. |
| Circuit supply temperature | -50 to 150 °C | Pressurized boilers and district heating can supply water above 100 °C. |
| Source temperature | -50 to 150 °C | Buffer and boiler water follows the same limits as supply water. |
| Zone humidity | 0 to 100 % | Relative humidity cannot leave this range. |

The ranges reject common fault readings, such as 0 K (-273.15 °C) from a misconfigured template or -127 °C from a disconnected one-wire probe.
The blocked reason names the rejected value, for example `implausible value -273.15 °C`.
- **Weighted mean** applies the positive weights configured through detailed sensor editing.

Designated-reference and weighted-mean policies become available after completing the detailed sensor editor because they depend on per-sensor metadata.

Hydronicus starts a fresh thermostat at 21.0 °C and HVAC mode off.
Use the Hydronicus climate entity to change its target and mode after setup.
Configure the heating start and stop deltas to define the hysteresis band around the runtime target.
Minimum active duration holds an already-requested Zone until its deadline unless a required sensor blocks it.
Minimum idle duration prevents a satisfied Zone from requesting heat again until its deadline.
Optional comfort, eco, and away target fields configure the corresponding Hydronicus climate presets.
Changing the target or preset reevaluates demand immediately without bypassing a remaining duration deadline.

For an external thermostat, select exactly one existing climate entity.
Do not configure target, preset-target, hysteresis, or thermostat-duration fields for that Zone.
Hydronicus consumes `hvac_action` as the authoritative demand signal.
The external target and current temperature attributes are diagnostic only.
External idle or off releases demand immediately.
External cooling still requires explicit Zone humidity and Circuit safety observations.

### Add a Hydraulic Circuit

Give the Circuit a generic name such as `Simulated circuit`.
Select the synthetic valve and pump entities.
Keep the opening and overrun timings long enough to observe the virtual sequence.

The initial flow creates one valve, one pump, one Circuit, and one Delivery Route from the first Zone to that Circuit.
The review page shows the compiled relationship and the expected valve-before-pump ordering.
Submit the flow only after confirming that the topology is the synthetic one you intended to test.

## Observe the result

After setup, Hydronicus exposes entities associated with the Plant.
The exact entity IDs depend on the Plant and Zone names chosen in Home Assistant.

The useful states for a first simulation are:

- The Zone climate entity, which reports the aggregate current temperature and target.
- The Zone demand binary sensor, which reports the calculated virtual heat demand.
- The aggregate-temperature sensor, which identifies usable and excluded observations in its attributes.
- The blocked binary sensor and blocked-reason sensor, which expose fail-closed sensor decisions without parsing prose.
- The valve requested and pump requested binary sensors, which report virtual requests.
- The topology preview sensor, which reports object counts and exposes compiled logic and structured warnings as separate attributes.
- The Zone explanation sensor, which reports why demand is requested, idle, or blocked.

Change the synthetic temperature below the target and wait for the configured virtual valve opening time.
The virtual sequence is:

```text
zone demand -> circuit request -> valve opening -> valve ready -> pump requested
```

Raise the synthetic temperature above the stop threshold.
The pump enters virtual overrun before it becomes idle, and the valve closes after the pump no longer needs protection.

No physical service call is dispatched while Dry run remains enabled.

Cooling demand, condensation blocking, source recommendations, and source changeover reasoning are also visible in Dry run when their required objects and observations are configured.
Cooling starts and source-selector operations remain Dry run only.
When Dry run is off, heating valves, pumps, and a configured direct source-demand output can execute after the required confirmation and pump-path checks.

## Add more objects

After the first Plant exists, use the config entry's subentry controls to add more objects.

- Add a **Circuit** to connect existing Zones, valves, and pumps.
- Add a **Zone** to select one or more existing Circuits and temperature sensors.
- Add an **Actuator** to add a valve to one or more existing Circuits.

The current Actuator subentry represents a valve.
Pumps are selected by Circuits from the pumps already present in the Plant topology.

Every relationship is stored by a generated identifier rather than by a display name.
Renaming an object should therefore not be used as a substitute for reviewing the resulting topology.
Always open the topology preview after a reconfiguration.

## Shared equipment

Select the same existing pump or valve when it is physically shared by multiple Circuits.
Hydronicus keeps the actuator requested while any active Circuit still consumes it.
It warns when a shared valve prevents independent hydraulic control.

Read [how Hydronicus works](how-it-works.md) for diagrams and the complete ownership rules.

## One live Plant per actuator entity

One actuator entity belongs to one live Plant.
Sharing equipment between Circuits happens inside one Plant, never across Plants.
A valve, pump, or source-demand entity that two Plants bind can be commanded by only one of them at a time, because two live Plants would switch it against each other and either one's Safe shutdown could stop equipment the other needs.
A Plant counts as live when it is loaded and not in Dry run.
Plants in Dry run may bind the same entities, for example to compare a draft configuration with the live one.
When you choose a valve, pump, or source-demand entity that another Plant already binds, the initial setup review and the actuator and source review steps list it as a warning that names the other Plant.
The warning does not block saving; in the actuator and source forms you confirm it with "I understand these warnings".
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
- Each Zone has at least one selected Circuit.
- Each Circuit has a valid valve path and pump.
- Shared equipment is intentional and documented for the test.
- The topology preview describes the expected route and sequence.
- The Plant remains in Dry run for the first test.
- No real equipment is being used as a test substitute.

If validation rejects a proposed object, review the object references and ownership boundaries before trying a different name.
Hydronicus rejects inconsistent topology, and a Zone that no enabled Delivery Route leaves, rather than silently guessing the intended relationship.
A Circuit, valve, or pump that no enabled Delivery Route reaches is accepted, reported as unused equipment, and never requested.
