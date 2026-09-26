# Plant file

A plant file describes one whole Plant in YAML: its source, its pumps, its plant loops, and its zones with their loops.
It is the portable form of a Plant, and it uses the same schema as the Plant that Home Assistant stores.
Importing an exported plant file rebuilds the Plant with the same Plant ID, the same object slugs, and therefore the same entity IDs.

Hydronicus never reads a plant file from `configuration.yaml`.
A Plant you import is stored in Home Assistant like any other config entry, and you change it afterwards in the UI or by replacing it from an edited file.

## Where plant files are used

| Task | Where |
| --- | --- |
| Create a Plant from a file | **Settings > Devices & services > Add integration > Hydronicus**, then **Import a plant file**. |
| See the file of an existing Plant | **Configure** on the Plant's entry, then **Show the plant file**. |
| Get the file from a script or automation | The **Export plant file** action, `hydronicus.export_plant`. |
| Change the whole Plant, zones included | **Reconfigure** on the Plant's entry, then **Replace from a plant file**. |

Paste the file into the **Plant file** field.
Both import and replace check the whole file and show the Plant before anything is stored: import shows **Review the Plant**, and replace shows **Save the changes** with the zones and outputs that are added, removed, or changed.

The **Export plant file** action is available to administrators.
Run it from **Settings > Tools > Actions** with the Plant selected.
It returns `document`, the plant file as data, and `yaml`, the same file as text.

A plant file does not carry anything that belongs to one installation: which outputs are armed, whether **Control equipment** is on, the Plant mode, the targets and modes of the zone thermostats, and the timers of a running Plant.
A Plant created from a file therefore starts like any new Plant, with nothing armed and **Control equipment** off.

## The reference plant

This is the plant the maintainer runs, and the tests use it as their end-to-end example.
It is also in [examples/reference-plant.yaml](examples/reference-plant.yaml).

```yaml
hydronicus: 2
id: 7c9e6679-7425-40de-944b-e07fc1f90ae7
name: Home
mode_dwell: 3600
source:
  name: Heat pump
  strategy: request
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
- `heat_pump` is the pump on the secondary side of the separator that the heat pump controls.
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
| `source` | no | no source | The [source](#source). |
| `pumps` | no | | Slug to [pump](#pumps). |
| `loops` | no | | Slug to [plant loop](#plant-loops). |
| `zones` | no | | Slug to [zone](#zones). |

Unknown keys are errors at every level of the file.
Times are in seconds and temperatures in °C.
Numbers must not be negative unless a key says otherwise.

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
| `strategy` | no | `request` | How Hydronicus asks for heat: `request` switches the request and lets the source choose its own flow temperature. `setpoint` is reserved for weather compensation and is refused for now. |
| `request` | yes | | The `switch` that asks the source for heat or cooling. |
| `mode` | no | | The `select` that switches the source between heating and cooling, as a mapping of `entity`, the select, `heat`, its option for heating, and `cool`, its option for cooling, such as `{entity: select.heat_pump_mode, heat: Heat, cool: Cool}`. The two options must differ. |
| `post_run` | no | `180` | How long the source keeps its own pumps running after the request ends. Hydronicus keeps their loops open for that long. |
| `min_on` | no | `600` | The shortest time the request stays on. |
| `min_off` | no | `600` | The shortest time the request stays off. |

A Plant without a source still opens valves and runs the pumps it switches, which suits a boiler that follows its own controls.

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
| `supply_temperature` | no | | A `sensor` of the water temperature this pump supplies. It is the condensation reference that lets the pump's loops cool. |

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
| `runs` | plant loops only | | When a [plant loop](#plant-loops) runs. |

A loop may cool only with a condensation reference: its pump's `supply_temperature` or its own `surface_temperature`.
A loop without either is heat only.

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
| `max_age` | no | `1800` | Seconds after which a reading of the area's sensors is stale. Must be positive. |

A zone follows the temperature sensor and the humidity sensor that each of its areas names in its area settings, after its extra sensors.
The area ID is the one Home Assistant made from the area's name when the area was created, such as `living_room`; renaming an area keeps its ID.
An area that is missing or names no sensor adds no reading, and it never makes the Plant invalid; Repairs report it instead.

### Sensors

An item of `temperature` or `humidity` is a `sensor` entity ID, or a mapping:

| Key | Required | Default | Value |
| --- | --- | --- | --- |
| `entity` | yes | | The sensor. |
| `required` | no | `true` | Whether the sensor being stale or unavailable blocks the zone. An optional sensor is left out instead. |
| `max_age` | no | `1800` | Seconds after which a reading is stale. Must be positive. |

Calibrate a sensor at its source; the plant file has no offsets or weights.

### Thermostats

`thermostat` is a mapping with one key: `external`, the existing Home Assistant climate entity that owns the zone's demand, as in `{external: climate.x}`, or `digital`, the settings of a thermostat that Hydronicus provides, as in `{digital: {...}}`.
A zone without `thermostat` gets a digital thermostat with the defaults below.

An external thermostat owns the zone's demand: Hydronicus reads only its `hvac_action` and never commands it.

A digital thermostat accepts these keys:

| Key | Default | Value |
| --- | --- | --- |
| `target` | `21` | The target of a new thermostat, in °C. It may be negative. |
| `presets` | none | Preset targets: any of `comfort`, `eco`, and `away`. |
| `heat_start_delta` | `0.3` | Heating demand starts this far below the target. |
| `heat_stop_delta` | `0.1` | Heating demand stops this far above the target. |
| `cool_start_delta` | `0.3` | Cooling demand starts this far above the target. |
| `cool_stop_delta` | `0.1` | Cooling demand stops this far below the target. |
| `min_on` | `0` | The shortest time demand stays on, in seconds. |
| `min_off` | `0` | The shortest time demand stays off, in seconds. |
| `proportional_band` | `1` | The distance to target, in kelvin, over which the demand level rises from 0 to 1. Must be positive. |

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
        min_on: 600
    loops:
      floor:
        valves:
          - {entity: switch.living_floor_valve, opening_time: 240, readiness: binary_sensor.living_floor_valve_open}
        pump: pump
```

## A small cooling Plant

A loop that cools needs a condensation reference, and its zone needs a humidity reading:

```yaml
hydronicus: 2
name: Office
source:
  request: switch.office_heat_pump_request
  mode: {entity: select.office_heat_pump_mode, heat: Heating, cool: Cooling}
pumps:
  circulator:
    switch: switch.office_circulator
zones:
  office:
    temperature: [sensor.office_temperature]
    humidity: [sensor.office_humidity]
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

## How it is stored

The plant file is also the storage schema.
The Plant's config entry holds everything except `zones`, and edits of it go through the Plant's **Reconfigure**.
Each zone is a `zone` subentry of the Plant: it holds that zone's mapping plus its slug, its title is the zone's name, and its unique ID is the slug.
Storage lists pumps and loops as objects that carry their slug, because Home Assistant sorts the keys it stores; an export writes them back in the order you gave them.
A zone references only the Plant's pumps and source, so removing a zone removes exactly its own loops and valves.

## The exported form

An export writes the canonical form of the file:

- Every structural and timing key is written, such as `mode_dwell`, a switched pump's `overrun`, and each loop's `modes`.
- Optional keys at their defaults are left out: names that read the same as their slug, sensor and area settings you did not change, and digital thermostat settings at their defaults.
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
| `zones.living_area.loops.floor.pumps` | Zone Living area, loop Floor, pumps | Unknown key; expected one of: name, valves, pump, modes, surface_temperature. |
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
| `source.strategy` | Source, strategy | The setpoint strategy arrives with weather compensation; use request. |

A file that is empty, or is not valid YAML, is reported for the whole file, and so is a mapping that repeats a key.

Beyond the file itself, Hydronicus refuses two kinds of binding when it checks a Plant:

- An entity that Hydronicus itself provides, such as a zone's **Combined temperature**, because the Plant would feed back into itself.
- An output that another Plant already binds, because an output belongs to one Plant.
