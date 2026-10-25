# Plant file

A plant file describes a whole Plant in YAML: its source, its pumps, its plant loops, and its zones with their loops.
Use it to share a Plant, keep a copy of it, or change many things at once.
Importing a Plant's own file rebuilds it with the same entity IDs.

A plant file is pasted into a form; Hydronicus never reads one from `configuration.yaml`.

| To | Go to |
| --- | --- |
| Create a Plant from a file | **Settings > Devices & services > Add integration > Hydronicus**, then **Import a plant file**. |
| See the file of a Plant | **Configure** on the Plant's entry, then **Show the plant file**. |
| Change the whole Plant, zones included | **Reconfigure** on the Plant's entry, then **Replace from a plant file**. |
| Get the file in a script | The [Export plant file](entities.md#export-plant-file) action, `hydronicus.export_plant`. |

Import and replace both check the whole file and show what changes before anything is stored.

The export action's required `config_entry_id` is the Home Assistant entry ID selected in its form, not the Plant UUID or a zone entity ID.
The action is response-only and refuses a missing entry, an entry from another integration, or an invalid stored Plant.
It does not arm outputs, change control, or export runtime state.

A plant file describes the plant, not how it is running: which outputs are armed, **Control equipment**, the Plant mode, the thermostats' targets, and the timers are not in it.
So a Plant created from a file starts like any new Plant, with nothing armed and **Control equipment** off.

## The reference plant

This is the plant the maintainer runs, and a good starting point for your own.
It is also in [examples/reference-plant.yaml](examples/reference-plant.yaml).

```yaml
hydronicus: 2
id: 7c9e6679-7425-40de-944b-e07fc1f90ae7
name: Home
mode_dwell: 3600
source:
  name: Heat pump
  request: switch.heat_pump_heat_request
  mode: {entity: select.heat_pump_mode, heat: Heat, cool: Cool}
  post_run: 180
  min_on: 600
  min_off: 600
pumps:
  heat_pump:
    driven_by: source
    min_flow: path
    min_flow_loops: [living_area.ceiling]
    supply_temperature: sensor.ceiling_supply_temperature
  floor:
    switch: switch.home_underfloor_heating_pump
    overrun: 180
  towel_dryer:
    switch: switch.home_bathrooms_towel_dryer_pump
    overrun: 120
loops:
  towel_dryer:
    pump: towel_dryer
    runs: with_source
    modes: [heat]
zones:
  basement:
    areas: [basement, workshop]
    thermostat: {digital: {presets: {comfort: 21, eco: 19, away: 16}}}
    loops:
      ceiling:
        valves: [switch.home_basement_ceiling_heating_valve]
        pump: heat_pump
        modes: [heat, cool]
  bedroom_area:
    areas: [main_bedroom, lilla_bedroom]
    loops:
      ceiling:
        valves: [switch.home_bedroom_area_ceiling_heating_valve]
        pump: heat_pump
        modes: [heat, cool]
  living_area:
    areas: [living_room, dining_room, kitchen, hallway]
    loops:
      ceiling:
        valves: [switch.home_living_area_ceiling_heating_valve]
        pump: heat_pump
        modes: [heat, cool]
      floor:
        valves: [switch.home_living_area_floor_heating_valve]
        pump: floor
        modes: [heat]
```

Read it from the top:

- The source is an air-to-water heat pump.
  Hydronicus asks it for heat or cooling with `switch.heat_pump_heat_request` and sets `select.heat_pump_mode` to `Heat` or `Cool` to follow the Plant mode.
- `heat_pump` is the heat pump's own circulator.
  The heat pump runs it, so Hydronicus never switches it, but it needs an open loop while it runs, so Hydronicus holds the living area's ceiling loop open whenever no other loop of that pump is open.
  Its supply temperature sensor is the condensation reference that lets the ceiling loops cool.
- `floor` and `towel_dryer` are pumps that Hydronicus switches.
- The towel dryer is a plant loop with a pump and no valve, which runs whenever the heat pump is asked for heat.
- Every zone covers Home Assistant areas and follows the temperature and humidity sensors those areas name.
  Every zone gets a digital thermostat, and the basement's has presets.
- Each zone has a ceiling loop with one valve that heats and cools, and the living area also has an underfloor loop with its own pump that only heats.

## Top-level keys

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `hydronicus` | yes | | The format, `2`. |
| `id` | no | a new random ID | The Plant ID, a UUID. It forms the unique ID of every entity, so keep it to keep the entity IDs. |
| `name` | yes | | The Plant name, which also names the Plant's device and its Plant-wide entities. |
| `mode_dwell` | no | `3600` | Seconds between the end of the old mode's flow and the start of the new mode, after a change between heating and cooling. |
| `exercise` | no | `{interval: 604800, run: 60}` | The [exercise](#exercise) of idle pumps and valves, or `false` or `null` to turn it off. |
| `frost_protection` | no | `5` | The frost protection temperature in °C, at most 10, or `false` or `null` to turn frost protection off. A zone that a loop heats is heated whatever its thermostat says once its coldest reading falls below it, until that reading is 1 K above it; see [frost protection](how-it-works.md#frost-protection). |
| `source` | no | no source | The [source](#source). |
| `weather` | no | none | Optional [weather forecast](#weather-forecast) inputs for recovery learning. |
| `pumps` | no | | Slug to [pump](#pumps). |
| `loops` | no | | Slug to [plant loop](#plant-loops). |
| `zones` | no | | Slug to [zone](#zones). |

Unknown keys are errors at every level of the file.
Times are in seconds and temperatures in °C.
Numbers must not be negative unless a key says otherwise.

## Weather forecast

The optional Plant-level `weather` mapping selects hourly forecast inputs independently of source control.
A Plant with only switched pumps and circuit valves can use it.

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `entity` | yes | | A `weather` entity that supports hourly forecasts. |
| `outdoor_sensor` | no | | A separate measured outdoor temperature `sensor`, used to compare recovery under different outdoor conditions. |
| `max_age` | no | `7200` | Positive maximum age in seconds of forecast content since first observed, weather entity reports, and the optional measured outdoor reading. |

Forecasts are optional planning inputs and never replace measured room temperatures, condensation references, or equipment feedback.
Adding this mapping alone does not enable weather-aware control: each participating digital thermostat also selects `learning: assist` and `weather_aware: true`.
Missing or stale optional inputs return recovery planning to its learned baseline or configured schedule rate.
Repeated forecast content keeps its original age; retrieving it again does not prove the provider issued a new forecast.
When the provider issue time is unavailable, diagnostics distinguish that uncertainty from the time Hydronicus first observed the forecast.

## Exercise

A pump or valve that stays off for months can seize, so Hydronicus runs each switched pump and opens each valve that has not been on for a while, as [exercising idle pumps and valves](how-it-works.md#exercise) describes.
`exercise` is a mapping of two keys, or `false` or `null` to turn the exercise off:

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `interval` | no | `604800` | Seconds a switched pump or a valve may stay off before it is exercised, a week by default. Must be at least 3600, an hour. |
| `run` | no | `60` | Seconds an exercised switched pump runs. Must be from 10 to 600. |

This Plant exercises its pump and valve every three days, and never protects against frost, because its boiler does:

```yaml
hydronicus: 2
name: Barn
exercise: {interval: 259200, run: 120}
frost_protection: false
pumps:
  pump:
    switch: switch.barn_pump
zones:
  barn:
    temperature: [sensor.barn_temperature]
    loops:
      radiators:
        valves: [switch.barn_radiator_valve]
        pump: pump
```

## Slugs and names

Every pump, plant loop, zone, and zone loop is written under a slug, such as `living_area` or `floor`.
A slug starts with a lowercase letter and holds only lowercase letters, digits, and underscores.
Pumps, plant loops, and zones each have their own slugs, and each zone's loops have their own, so two zones can both have a loop called `ceiling`.

A slug never changes, and together with the Plant ID it forms the unique IDs of the object's entities.
Names are separate: pumps, plant loops, zones, loops, and the source accept an optional `name`.
Without one, the name is the slug in words with its first letter capitalized, so `living_area` reads `Living area`.
The source's default name is `Heat source`.

A loop is referred to by its slug when it is a plant loop, and as `<zone>.<loop>` when it belongs to a zone, such as `living_area.ceiling`.
That form appears only in a pump's `min_flow_loops`.

## Source

The source is the generator Hydronicus asks for heat or cooling, such as a heat pump or a boiler, and a Plant has at most one.
Hydronicus reaches it only through generic Home Assistant entities, whichever integration provides them.

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `name` | no | `Heat source` | The source's name, which names its device. |
| `request` | yes | | The `switch` that asks the source for heat or cooling. |
| `mode` | no | | The `select` that switches the source between heating and cooling, as a mapping of `entity`, the select, `heat`, its option for heating, and `cool`, its option for cooling, such as `{entity: select.heat_pump_mode, heat: Heat, cool: Cool}`. The two options must differ. |
| `mode_switches` | no | | Switches of the source that follow the mode, each with the modes it is on in, such as `{switch.heat_pump_weather_curve: [heat]}` for a weather curve that heating uses and cooling does not. Each is off in the other mode and left as it is while the Plant is off. Hydronicus sets them with the mode select, and the supply setpoint and the request wait until they show the mode's state. They keep the source's `write_interval`. |
| `post_run` | no | `180` | How long the source keeps its own pumps running after the request ends. Hydronicus keeps their loops open for that long. |
| `min_on` | no | `600` | The shortest time the request stays on, measured from observed activation. |
| `min_off` | no | `600` | The shortest time the request stays off, measured from observed shutdown. |
| `running_sensor` | no | | A `binary_sensor` that reports whether the source actually runs, independently of its request switch. |
| `feedback_timeout` | no | `300` | Positive seconds allowed after an observed source request for source running feedback and source-driven pump running or flow feedback to confirm operation. Missing or unknown feedback blocks startup. |
| `supply` | no | | Optional [supply temperature control](#supply-temperature-control). |
| `dhw` | no | | Optional [domestic hot water](#domestic-hot-water) settings that Hydronicus owns. |
| `inhibit_sensor` | no | | A `binary_sensor` or `input_boolean` that reads on while another source supplies the zones, such as a fireplace's buffer that its own valve selects. While it reads on, the request is released at once, whatever `min_on` says, and stays off, with no fault and no Repair; the calling zones still open their loops and run their switched pumps. Unknown or unavailable counts as off. |
| `no_load` | no | | Optional [no-load guard](#no-load-guard). |
| `compressor_sensor` | no | | A `sensor` that reads above zero while the compressor runs, such as its frequency. Hydronicus then publishes the compressor's **Compressor starts** within the last hour and its mean **Compressor cycle**. |
| `max_starts_per_hour` | no | no limit | The most times the request may be observed turning on within any hour, a whole number. A start beyond it waits until the oldest start is an hour old. |
| `start_threshold` | no | none | The total `weight` of calling loops needed before the request starts. Loops below it still open and circulate; a running request is never cut short by it. |
| `heat_sink_loops` | no | | Heating loops, such as `[living_area.floor]`, that Hydronicus opens when every calling loop is satisfied while the request is held for its `min_on` or its `hold_after_demand`. The source then runs into them, and the other loops close once one of them is ready. A heat sink loop never asks for heat itself. |
| `hold_after_demand` | no | none | Seconds the heating request stays on into the `heat_sink_loops` after the last calling loop is satisfied, such as `14400`, for a heat pump whose every stop restarts its own pumps. A new call during the hold needs no new start. It needs `heat_sink_loops`. |
| `heat_sink_overshoot` | no | `1` | Beyond `min_on`, a heat sink loop takes heat only while each zone it serves reads less than this many kelvin over its heating target; a zone with no usable reading or no digital thermostat has no room. The request is released once no heat sink has room. |
| `health_sensor` | no | | A `binary_sensor` that reads on while the source and its link are healthy, such as a Modbus bridge's health. While it reads off, unknown, or unavailable, the request is released at once, whatever `min_on` says, and stays off; the calling zones still circulate. |
| `handover_sensor` | no | | A `binary_sensor` that reads on while something else controls the source, such as a Modbus bridge that handed the heat pump to its wired controller. While it reads on, Hydronicus sends the request, the mode select, and the supply setpoint nothing, so a bridge that refuses them raises no Repair, and in heating it keeps every `heat_sink_loops` loop open while the request shows on or unknown, however warm its zone. When it reads off again, Hydronicus takes over from the request as it finds it. It needs `heat_sink_loops`. |
| `write_interval` | no | none | The fewest seconds between two writes to the request, the mode select, or the supply setpoint, for a bridge that refuses faster ones, such as `300`. A switch turning off is never held. Such an output is retried no faster either, and once three writes have not been taken, Hydronicus keeps its Repair and sends it again only after an hour, or as soon as its target or its state changes. Keep `min_off` above it, so a request turning on again is not held. |

A Plant without a source still opens valves and runs the pumps it switches, which suits a boiler that follows its own controls.

### Supply temperature control

The source's `supply` mapping binds a `number` entity in addition to its request switch.
It is a separately armed output, and the source waits for its target to be confirmed before requesting heat or cooling.
All temperatures below are in °C; the adapter converts the command into the number entity's supported temperature unit and checks its advertised range.
Configure this only when Hydronicus owns the supply setpoint; do not let another heating-curve controller continuously rewrite the same number.

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `entity` | yes | | The `number` that sets the source's supply temperature. |
| `heat_temperature` | no | `35` | Fixed heating target when no outdoor sensor is bound. |
| `cool_temperature` | no | `18` | Cooling target, raised when necessary to respect the measured dew-point margin. |
| `minimum` | no | `5` | Lowest permitted supply target. |
| `maximum` | no | `60` | Highest permitted supply target; must exceed `minimum`. |
| `tolerance` | no | `0.5` | Positive temperature difference in K accepted as confirmation of the number's target, avoiding repeated commands for small changes. |
| `outdoor_sensor` | no | | A temperature `sensor` that enables the heating curve. Cooling still uses its fixed target. |
| `outdoor_cold` | no | `-10` | Outdoor temperature at the cold end of the curve; may be negative. |
| `outdoor_warm` | no | `20` | Outdoor temperature at the warm end of the curve; must exceed `outdoor_cold`. |
| `heat_cold` | no | `45` | Supply target at or below `outdoor_cold`. |
| `heat_warm` | no | `25` | Supply target at or above `outdoor_warm`; must not exceed `heat_cold`. |
| `max_age` | no | `3600` | Positive maximum age in seconds of the outdoor reading. |
| `modes` | no | `[heat, cool]` | The modes in which Hydronicus owns the setpoint, such as `[cool]` for a heat pump whose own weather curve keeps the heating setpoint. In another mode Hydronicus sends the number nothing and does not wait for it. |
| `step` | no | | The setpoint's resolution, such as `1` for a heat pump that takes whole degrees. A cooling target is rounded up to it, so it stays above the dew point margin, and a heating target to the nearest step within `minimum` and `maximum`. |

With a mode select, a target is proposed only once the select shows the mode, since a heat pump's setpoint range often follows its mode.

The curve is linear between its two endpoints and stays at an endpoint outside their outdoor range.
Every configured fixed or curve supply temperature of the setpoint's `modes` must lie within `minimum` and `maximum`.
A missing, invalid, or stale outdoor reading blocks the heating request instead of silently choosing a different target.
A cooling target that cannot satisfy the condensation margin within `maximum` blocks the source, and the measured condensation guard remains active regardless of the setpoint.
See [supply control](how-it-works.md#supply-temperature-control) and the [comfort and feedback example](examples/comfort-and-feedback.yaml).

### No-load guard

The source's `no_load` mapping releases a heat pump whose compressor runs while its leaving and returning water stay within `delta` of each other, so its heat has nowhere to go: another source supplies the zones, every valve is closed, a pump failed, or air blocks the flow.
It trips once the request is on, the compressor has run for `duration`, and the water has stayed within `delta` for `duration` too; Hydronicus then releases the request and holds it off for `hold_off`.
A missing or stale reading never trips it, and two trips within a day raise a Repair.
Its readings go stale like a condensation reference, 30 minutes after their last report, so a sensor that reports only when its value changes, such as an MQTT sensor without `force_update`, can keep the guard from tripping while the compressor runs steadily.

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `supply_temperature` | yes | | The heat pump's leaving water temperature `sensor`. |
| `return_temperature` | yes | | The heat pump's returning water temperature `sensor`. |
| `compressor_sensor` | yes | | A `sensor` that reads above zero while the compressor runs, such as its frequency. |
| `delta` | no | `1` | The temperature difference in K under which the water counts as carrying no heat. |
| `duration` | no | `600` | How long the compressor must run, and the difference stay under `delta`, before the guard trips, in seconds. |
| `hold_off` | no | `1800` | How long the request then stays off, in seconds. |

### Domestic hot water

The source's `dhw` mapping binds the source's own DHW switch, its DHW setpoint `number`, or both, which Hydronicus then owns and shows as its **DHW** switch and **DHW target** number.
Both are outputs that must be armed, and like the source's other outputs they keep its `write_interval`.
A change made elsewhere, such as on the heat pump's wired controller, is adopted: it becomes Hydronicus's value and is never written back.
The `hydronicus.boost_dhw` action raises the setpoint for a bounded time and then restores the owned target, also after a restart, and once the setpoint is back if it was unavailable when the boost ended; a change made elsewhere during a boost ends it without restoring.
While the source's handover sensor reads on, or Control equipment is off, Hydronicus sends them nothing.

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `switch` | one of the two | | The `switch` that turns the source's DHW on and off. |
| `setpoint` | one of the two | | The `number` that sets the DHW tank temperature. |
| `minimum` | no | `40` | The lowest DHW target in °C; a lower owned, adopted, or boost value is clamped and logged. |
| `maximum` | no | `55` | The highest DHW target in °C; must exceed `minimum`. |
| `tolerance` | no | `0.5` | The difference in K accepted as confirmation of the setpoint. |
| `step` | no | | The setpoint's resolution, such as `1` for whole degrees. |
| `max_boost` | no | `7200` | The longest a boost may last, in seconds. |

## Pumps

A pump is a circulator that Hydronicus switches, or one that the source drives and Hydronicus never commands.
Every loop runs on exactly one pump, and a pump can drive any number of loops.

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `name` | no | the slug in words | The pump's name. |
| `switch` | one of the two | | The `switch` that runs the pump. |
| `driven_by` | one of the two | | `source`, for a pump the source runs by itself, such as a heat pump's own circulator. It needs a source. |
| `overrun` | no | `180` | For a switched pump: how long it keeps running after heating demand ends, with its loops held open. Cooling stops a pump without overrun. A source-driven pump has no overrun; the source's `post_run` covers it. |
| `min_flow` | no | `path` | `path` when the pump needs an open loop while it runs, `guaranteed` when a hydraulic separator, buffer, or bypass gives it a path whatever the loops do. |
| `min_flow_loops` | see below | | For a source-driven pump with `min_flow: path`: the loops Hydronicus holds open whenever none of the pump's other loops is ready while the pump may run. |
| `supply_temperature` | no | | A `sensor` of the water temperature this pump supplies. It is the condensation reference that lets the pump's loops cool. It goes stale 30 minutes after its last report and then blocks cooling, so a sensor that reports only on change, such as an MQTT sensor without `force_update`, must still report at least that often while its value is steady. |
| `condensation_switch` | no | | A `binary_sensor` on this pump's supply pipe that turns on at condensation, such as a dew point switch. While it is on, unavailable, or unknown, none of the pump's loops cools. |
| `running_sensor` | no | | A `binary_sensor` that reports whether the pump actually runs. |
| `flow_sensor` | no | | A `binary_sensor` that reports whether circulation is proved. This is an input, not a water-volume or energy meter. |

A pump has either `switch` or `driven_by: source`, never both.
A switched pump with `min_flow: path` simply never runs without a ready loop, so it takes no `min_flow_loops`.
A source-driven pump with `min_flow: path` must name its `min_flow_loops`, which must be loops of that pump.
A pump with `min_flow: guaranteed` takes no `min_flow_loops`.
Adding a buffer or bypass later is a change of one line, to `min_flow: guaranteed`.

This Plant has a source whose pump is protected by a separator, so no loop needs to be held open:

```yaml
hydronicus: 2
name: Cottage
source:
  request: switch.boiler_heat_request
pumps:
  primary:
    name: Boiler pump
    driven_by: source
    min_flow: guaranteed
zones:
  lounge:
    temperature: [sensor.lounge_temperature]
    loops:
      radiators:
        valves: [valve.lounge_radiators]
        pump: primary
```

## Valves

A loop's `valves` list holds entity IDs of `switch` or `valve` entities, or mappings:

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `entity` | yes | | The `switch` or `valve` entity that opens the valve. |
| `opening_time` | no | `180` | Seconds the valve needs to open before its loop counts as ready and its pump may start. |
| `readiness` | no | | A `binary_sensor` that turns on once the valve is fully open. When it is on, the loop counts as ready without waiting for `opening_time`. |

`valves: [switch.floor_valve]` is the short form of `valves: [{entity: switch.floor_valve}]`.
Every valve of a loop opens together, and the loop is ready once each of them is.
A `valve` entity may show opening or closing while it moves: it is not ready while it shows opening, its opening time counts from when it shows open, and it counts as possibly open until it shows closed.

An output entity has exactly one role in a Plant: a valve of one loop, a pump's switch, or a source output.
A valve entity is never shared by two loops, and a pump's switch is never also a valve or the source request.

## Loops

A loop is a flow path: zero or more valves that open together, and exactly one pump.
A loop with no valve is always an open path, and its pump is its only control.

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `name` | no | the slug in words | The loop's name, such as `Ceiling` or `Floor`. |
| `valves` | no | no valve | The loop's [valves](#valves). |
| `pump` | yes | | The slug of the pump that moves the loop's water. |
| `modes` | no | `[heat]` | `[heat]`, `[cool]`, or `[heat, cool]`. |
| `surface_temperature` | no | | A `sensor` of the floor or ceiling surface temperature, the loop's own condensation reference. |
| `surface_minimum` | no | `20` | Only with `surface_temperature`: the lowest surface temperature while the loop cools, in °C. `null` turns it off. |
| `condensation_switch` | no | | A `binary_sensor` that turns on at condensation on this loop, such as a dew point switch on its pipe. While it is on, unavailable, or unknown, the loop does not cool. |
| `weight` | no | `1` | The loop's positive share of demand for the source's `start_threshold`, such as its emitter output in kW. |
| `runs` | plant loops only | | When a [plant loop](#plant-loops) runs. |

A loop may cool only with a condensation reference: its pump's `supply_temperature` or its own `surface_temperature`.
A loop without either is heat only.
A condensation switch never replaces that reference; it only adds to the [condensation guard](how-it-works.md#cooling-and-condensation).

The default `surface_minimum` of 20 °C keeps a cooled floor comfortable to stand on, as ISO 7730 and REHVA advise.
A ceiling nobody touches may run colder, so a ceiling loop may use a lower value, such as `17`, as long as the dew point allows it.

### Plant loops

A plant loop is a loop that no zone owns, written under the top-level `loops`.
It needs `runs`:

- `runs: with_source` runs the loop whenever the source's request is on, such as a towel dryer on the heating circuit.
  It needs a source, and it never asks the source for heat by itself.
- `runs: {with_zones: [<zone>, ...]}` runs the loop while any of the zones listed under `with_zones` demands, such as one loop that heats a hall and a stairwell of two zones.

A loop that several zones use is a plant loop that runs with those zones.

```yaml
hydronicus: 2
name: Townhouse
pumps:
  manifold:
    switch: switch.manifold_pump
    overrun: 120
loops:
  stairwell:
    valves: [switch.stairwell_valve]
    pump: manifold
    runs: {with_zones: [ground_floor, first_floor]}
zones:
  ground_floor:
    temperature: [sensor.ground_floor_temperature]
    loops:
      floor:
        valves: [switch.ground_floor_valve]
        pump: manifold
  first_floor:
    temperature: [sensor.first_floor_temperature]
    loops:
      floor:
        valves: [switch.first_floor_valve]
        pump: manifold
```

## Zones

A zone is the space one thermostat controls.
It covers zero or more Home Assistant areas and owns its loops.

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `name` | no | the slug in words | The zone's name, which names its device, its thermostat, and its entities. |
| `areas` | no | | The Home Assistant areas the zone covers, see [Areas](#areas). |
| `temperature` | no | | Extra temperature sensors, see [Sensors](#sensors). |
| `humidity` | no | | Extra humidity sensors, see [Sensors](#sensors). |
| `aggregation` | no | `mean` | How the zone combines its temperatures: `mean`, `min`, or `max`. |
| `thermostat` | no | a digital thermostat | See [Thermostats](#thermostats). |
| `windows` | no | | `binary_sensor` entities that are on while a window or door of the zone is open, see [Windows](#windows). |
| `window_open_delay` | no | `60` | Seconds a window must read open before the zone's demand turns off. |
| `window_close_delay` | no | `60` | Seconds every window must read closed before the zone's demand comes back. |
| `max_humidity` | no | `70` | The highest humidity, in percent, at which the loops that read the zone's dew point may cool, from 30 to 100. `null` turns the cutoff off. |
| `loops` | no | | Slug to [loop](#loops) of the zone. |

A zone with a digital thermostat needs a temperature sensor or an area.
A zone with a loop that cools needs a humidity sensor or an area, and a temperature sensor or an area, for its dew point.
So does each zone that a plant loop that cools runs with, or every zone when that plant loop runs with the source, because the loop's condensation guard reads their dew points.
A zone may have no loop of its own when a plant loop runs with it.

### Areas

An item of `areas` is the ID of a Home Assistant area, or a mapping:

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `area` | yes | | The area ID. |
| `required` | no | `false` | Whether a stale or unavailable sensor of the area blocks the zone. |
| `max_age` | no | `3600` | Seconds after which a reading of the area's sensors is stale. Must be positive. |

A zone follows the temperature sensor and the humidity sensor that each of its areas names in its area settings, after its extra sensors.
The area ID is the one Home Assistant made from the area's name when the area was created, such as `living_room`; renaming an area keeps its ID.
An area that is missing or names no sensor adds no reading, and it never makes the Plant invalid; Repairs report it instead.

### Sensors

An item of `temperature` or `humidity` is a `sensor` entity ID, or a mapping:

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `entity` | yes | | The sensor. |
| `required` | no | `true` | Whether the sensor being stale or unavailable blocks the zone. An optional sensor is left out instead. |
| `max_age` | no | `3600` | Seconds after which a reading is stale. Must be positive. |

A reading is stale once its sensor has not reported for `max_age`, whether or not its value changed.
Many battery sensors report only when their value changes, with a heartbeat about once an hour, so the default is an hour.
Raise `max_age` for a sensor whose heartbeat is rarer, so a steady room does not count as stale.
Lower it for a sensor that reports every few minutes, so a sensor that stops is noticed sooner.
The condensation guard's references, a pump's `supply_temperature` and a loop's `surface_temperature`, are stale after 1800 seconds, because cooling needs a fresh reference.

Calibrate a sensor at its source; the plant file has no offsets or weights.

### Windows

Once any window of `windows` has read open for `window_open_delay`, the zone's demand is off, in heating and in cooling, with the reason `window open`.
It comes back once every window has read closed for `window_close_delay`.
The thermostat keeps its target and mode meanwhile, and a demand that comes back holds for its `min_on` from then.
A window sensor that is unavailable or unknown reads as closed, so a lost sensor never stops the heating.

### Thermostats

`thermostat` is a mapping with one key: `external`, the existing Home Assistant climate entity that owns the zone's demand, as in `{external: climate.x}`, or `digital`, the settings of a thermostat that Hydronicus provides, as in `{digital: {...}}`.
A zone without `thermostat` gets a digital thermostat with the defaults below.

An external thermostat owns the zone's demand: Hydronicus reads only its `hvac_action` and never commands it.

A digital thermostat accepts these keys:

| Key | Default | Value |
| --- | --- | --- |
| `target` | `21` | The heating comfort target of a new thermostat, in °C. |
| `cool_target` | `24` | The cooling comfort target of a new thermostat, in °C. |
| `presets` | none | Heating preset targets: any of `comfort`, `eco`, and `away`. |
| `cool_presets` | none | Cooling preset targets, independently configured using the same names. |
| `schedule` | none | Optional [comfort schedule](#comfort-schedule) settings. Selecting the thermostat's `schedule` preset enables them. |
| `learning` | `off` | Recovery learning: `off`, `observe`, or `assist`; see [recovery learning](#recovery-learning). |
| `weather_aware` | `false` | Allow weather-informed recovery timing, only with assisted learning, a comfort schedule, and Plant weather settings. |
| `heat_start_delta` | `0.3` | Heating demand starts this far below the target. |
| `heat_stop_delta` | `0.1` | Heating demand stops this far above the target. |
| `cool_start_delta` | `0.3` | Cooling demand starts this far above the target. |
| `cool_stop_delta` | `0.1` | Cooling demand stops this far below the target. |
| `min_on` | `600` | The shortest time demand stays on, in seconds, so a short call does not open a slow valve and close it again before its pump has run. |
| `min_off` | `600` | The shortest time demand stays off after it ends, in seconds, so a valve that has just closed is not opened again at once. A zone that has not called since its thermostat started or changed mode may call at once. |

This zone has an external thermostat, and a radiator loop with no valve whose pump is its only control:

```yaml
hydronicus: 2
name: Workshop
pumps:
  radiators:
    switch: switch.workshop_radiator_pump
zones:
  workshop:
    thermostat: {external: climate.workshop}
    loops:
      radiators:
        pump: radiators
```

This zone shows the longer forms of areas, sensors, and a digital thermostat:

```yaml
hydronicus: 2
name: Flat
pumps:
  pump:
    switch: switch.flat_pump
zones:
  living:
    name: Living and dining
    areas:
      - living_room
      - {area: dining_room, required: true, max_age: 900}
    temperature:
      - {entity: sensor.floor_probe, required: false}
    aggregation: min
    thermostat:
      digital:
        target: 21.5
        presets: {comfort: 22, eco: 19}
        heat_start_delta: 0.5
        min_on: 900
    loops:
      floor:
        valves:
          - {entity: switch.living_floor_valve, opening_time: 240, readiness: binary_sensor.living_floor_valve_open}
        pump: pump
```

### Comfort schedule

A digital thermostat's `schedule` mapping follows an existing Home Assistant `schedule` helper.
It is an optional thermostat policy: it never changes the Plant mode, arms an output, or bypasses a hydraulic or condensation interlock.

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `entity` | yes | | The `schedule` helper whose on periods are comfort periods. |
| `heat_setback` | no | `2` | Reduction from 0 to 10 K from the heating comfort target outside comfort periods; the starting value of the zone's **Heating setback**. |
| `cool_setback` | no | `2` | Increase from 0 to 10 K from the cooling comfort target outside comfort periods; the starting value of the zone's **Cooling setback**. |
| `max_early_start` | no | `0` | Maximum recovery lead time in seconds, from 0 to 21600. Zero disables early start. |
| `heating_rate` | no | `1` | Positive expected room warming rate in K/hour. |
| `cooling_rate` | no | `1` | Positive expected room cooling rate in K/hour. |

Select the thermostat's `schedule` preset to follow the helper.
The comfort target is its manual target for the current mode; setbacks are limited to the thermostat's 5 to 35 °C range.
A manual temperature change or another preset leaves schedule control until `schedule` is selected again.
Switching between heat and cool retains schedule control and uses the corresponding mode's target, setback, and rate.

Before an upcoming comfort period, the thermostat divides the current temperature deficit by the configured recovery rate, and starts at most `max_early_start` seconds early.
An unavailable schedule falls back to the manual comfort target and reports that state.
A missing, invalid, or past `next_event` prevents early start, while a valid off state still applies the setback.
Without assisted learning, these rates are explicit estimates; reaching comfort at the scheduled time is not guaranteed.
The [comfort and feedback example](examples/comfort-and-feedback.yaml) combines schedules, separate targets, feedback, and a supply curve.

### Recovery learning

Learning is optional for each digital thermostat and defaults to `off`.
`observe` collects usable recovery observations and predicts recovery without changing targets or early-start timing.
Observation works without a comfort schedule and without a configured source.
`assist` requires a comfort schedule and permits an accepted learned estimate to choose recovery timing within its existing `max_early_start` limit.
An unvalidated estimate leaves the configured `heating_rate` or `cooling_rate` in effect.
Heating and cooling evidence stays separate for each zone.

Set `weather_aware: true` only with `learning: assist`, a schedule, and the Plant's `weather` mapping.
Weather may adjust bounded early-start timing but never changes the manual comfort target, extends the early-start limit, or suppresses ordinary comfort demand.
An unavailable forecast returns to the learned baseline or configured rate.
Changing the manual target still exits schedule control.

Use the [circuit-only example](examples/predictive-circuits.yaml) for a Plant that opens valves and starts its serving pumps while the heat pump uses its own controls.
Leave `source` out until there is an actual source request entity that Hydronicus owns.
Output observations are estimates of circuit operation unless independent feedback proves it; learning does not imply flow measurement or heat-pump electricity measurement.

## A small cooling Plant

A loop that cools needs a condensation reference, and its zone needs a humidity reading.
This one also stops cooling when the dew point switch on the circulator's supply pipe trips, and stops the zone's demand while its window is open:

```yaml
hydronicus: 2
name: Office
source:
  request: switch.office_heat_pump_request
  mode: {entity: select.office_heat_pump_mode, heat: Heating, cool: Cooling}
pumps:
  circulator:
    switch: switch.office_circulator
    condensation_switch: binary_sensor.office_dew_point_switch
zones:
  office:
    temperature: [sensor.office_temperature]
    humidity: [sensor.office_humidity]
    windows: [binary_sensor.office_window]
    loops:
      ceiling:
        valves: [switch.office_ceiling_valve]
        pump: circulator
        modes: [heat, cool]
        surface_temperature: sensor.office_ceiling_surface_temperature
```

## IDs and entity IDs

Every entity's unique ID is made from the Plant `id` and the slugs of the objects it belongs to.
A file without an `id` gets a new random one on import, which the Plant then keeps and every export writes.
Importing an exported file with its `id` therefore gives the same unique IDs, and Home Assistant gives the entities the same entity IDs.

A Plant whose ID is already set up cannot be imported again; remove it first, or use **Replace from a plant file**.
A file for **Replace from a plant file** must carry the Plant's own `id`, or no `id`, in which case it keeps the Plant's.

Home Assistant makes an entity ID from the names when the entity is created, such as `climate.living_area` for zone `Living area`.
Renaming an object later changes what the entity shows, not its entity ID.
See [the entities](entities.md) for every entity a Plant publishes.

## The exported form

An export writes the canonical form of the file:

- Every structural and timing key is written, such as `mode_dwell`, a switched pump's `overrun`, and each loop's `modes`.
- Optional keys at their defaults are left out: names that read the same as their slug, sensor and area settings you did not change, digital thermostat settings at their defaults, and `exercise` and `frost_protection` at theirs.
- A source-driven pump always states its `min_flow`, because it is a safety decision.
- Lists and short mappings are written on one line.

Exporting and importing a Plant reproduces it exactly, and exporting it again writes the same text.

## Errors

Import, replace, and every setup form check the whole Plant with the same rules, and report the first problem found.
A problem has a path, the dotted address of the key it is about, such as `zones.living_area.loops.floor.pump`, with list items numbered from 0.
The forms show the path in words, naming each object by its name and numbering list items from 1, followed by the message, such as `The plant file is not valid. Zone Living area, loop Floor, pump: There is no pump underfloor.`
The **Export plant file** action and Plant settings show the dotted path instead.

These are problems in variations of the reference plant, with the path, the words a form shows, and the message:

| Path | In a form | Message |
| --- | --- | --- |
| `hydronicus` | Plant file format | Plant file format 1 is no longer read; describe the Plant in format 2. |
| `zones.Living room` | Zone Living room | A slug starts with a lowercase letter and holds only lowercase letters, digits, and underscores. |
| `zones.living_area.loops.floor.pumps` | Zone Living area, loop Floor, pumps | Unknown key; expected one of: name, valves, pump, modes, surface_temperature, surface_minimum, condensation_switch, weight. |
| `zones.living_area.loops.floor.pump` | Zone Living area, loop Floor, pump | There is no pump underfloor. |
| `zones.living_area.loops.floor.modes` | Zone Living area, loop Floor, modes | A loop that cools needs a condensation reference: a supply_temperature on pump floor or the loop's surface_temperature. Without one the loop is heat only. |
| `pumps.heat_pump.min_flow_loops` | Pump Heat pump, min-flow loops | A source-driven pump with min_flow: path needs min_flow_loops, the loops held open while it may run, or min_flow: guaranteed when a separator protects it. |
| `pumps.heat_pump.min_flow_loops.0` | Pump Heat pump, min-flow loop 1 | Loop living_area.floor runs on pump floor, not heat_pump. |
| `pumps.heat_pump.driven_by` | Pump Heat pump, driven by | A source-driven pump needs a source; add one or give the pump a switch. |
| `pumps.floor` | Pump Floor | A pump has either a switch or driven_by: source. |
| `pumps.floor.switch` | Pump Floor, switch | Expected an entity of the switch domain. |
| `zones.bedroom_area.loops.ceiling.valves.0` | Zone Bedroom area, loop Ceiling, valve 1 | switch.home_basement_ceiling_heating_valve is already bound at zones.basement.loops.ceiling.valves.0; an output has exactly one role in a Plant. |
| `zones.bedroom_area` | Zone Bedroom area | A digital thermostat needs a temperature sensor or an area. |
| `zones.living_area.humidity` | Zone Living area, humidity sensors | A zone that cools needs a humidity sensor or an area for its dew point. |
| `loops.towel_dryer.runs` | Plant loop Towel dryer, runs with | This key is required. |
| `frost_protection` | Frost protection | Must be at most 10. |

A file that is empty, or is not valid YAML, is reported for the whole file, and so is a mapping that repeats a key.

Beyond the file itself, Hydronicus refuses two kinds of binding when it checks a Plant:

- An entity that Hydronicus itself provides, such as a zone's **Combined temperature**, because the Plant would feed back into itself.
- An output that another Plant already binds, because an output belongs to one Plant.
