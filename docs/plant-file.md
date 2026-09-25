# Plant file

A plant file describes one whole Plant in YAML: its pumps, rooms, loops, valves, sources, and source selector.
It is the portable form of a Plant.
Exporting a Plant and importing the file rebuilds it with the same object IDs, and therefore the same entity IDs, on any Home Assistant instance.

The plant file is for import and export only.
Hydronicus never reads it from `configuration.yaml`, and the Plant you import is stored in Home Assistant like any other config entry.

## Where plant files are used

| Task | Where |
| --- | --- |
| Create a Plant from a file | **Settings > Devices & services > Add integration > Hydronicus > Import a plant file**. |
| See the file of an existing Plant | The Plant entry's **Reconfigure** menu, then **Show the plant file**. |
| Get the file from an automation or script | The `hydronicus.export_plant` action, which returns `{"document": ...}`. |
| Change the whole Plant, including shared equipment | The Plant entry's **Reconfigure** menu, then **Edit plant file**. |

The **Plant file** field is a YAML editor.
Paste the file there, either as the YAML text or as the parsed object that the editor shows.

The `hydronicus.export_plant` action is available only to administrators.
Run it from **Developer tools > Actions** with the Plant selected, and choose to return the response.

Import and edit both show a review before anything is saved.
The review lists the rooms or the changes, the compiled topology, and the warnings.
A warning other than unused equipment must be confirmed with **I understand these warnings** before saving.
When you edit an existing Plant, only the warnings the edit introduces need that confirmation, because the Plant's earlier warnings were confirmed when they appeared.
A Plant created from a file always starts in Dry run, and applying an edited file returns the Plant to Dry run.

## A first example

This file describes a manifold with one pump and three rooms, each with its own loop and valve:

```yaml
hydronicus: 1
name: Manifold
pumps:
  manifold_pump: switch.manifold_pump
rooms:
  living_room:
    temperature_sensors: [sensor.living_temperature]
    loops:
      living_loop:
        valves: [switch.living_valve]
        pump: manifold_pump
  bedroom:
    temperature_sensors: [sensor.bedroom_temperature]
    loops:
      bedroom_loop:
        valves: [switch.bedroom_valve]
        pump: manifold_pump
  office:
    temperature_sensors: [sensor.office_temperature]
    loops:
      office_loop:
        valves: [switch.office_valve]
        pump: manifold_pump
```

The rooms get a Hydronicus thermostat, because none names another thermostat.
Each valve entity in a loop's `valves` list creates a valve of that room named after the loop, such as `Living loop valve`.
Every loop uses the same pump, so the review shows a warning that the shared pump limits independent control, and you confirm it with **I understand these warnings**.

The [trial kit plant file](examples/trial/plant.yaml) is a smaller file of the same shape, bound to the synthetic entities of the [trial package](examples/trial/package.yaml).

## Top-level keys

| Key | Required | Value |
| --- | --- | --- |
| `hydronicus` | yes | The format version, `1`. |
| `id` | no | The Plant UUID. |
| `name` | yes | The Plant name. |
| `pumps` | no | Slug to pump. |
| `valves` | no | Slug to shared valve, owned by the Plant. |
| `loops` | no | Slug to shared loop, owned by the Plant. |
| `rooms` | no | Slug to room. |
| `sources` | no | Slug to source. |
| `source_selector` | no | The source selector. |

Unknown keys are errors at every level of the file.

The file does not carry Dry run, the confirmed heating outputs, the requested mode, or the diagnostics setting.
These belong to one installation, so an imported Plant always starts in Dry run with nothing confirmed.

## Slugs and names

Every object is written under a slug, such as `living_room` or `manifold_pump`.
A slug starts with a lowercase letter and contains only lowercase letters, digits, and underscores.
Slugs are unique per kind across the whole file: all valves share one namespace, all loops share one namespace, and rooms, pumps, and sources each have their own.
A room-owned valve and a shared valve therefore cannot use the same slug.

Other objects refer to an object by its slug, so a loop names its pump as `pump: manifold_pump`.
References may point forward to an object written later in the file.

Every object accepts an optional `name`.
Without one, the name comes from the slug with underscores as spaces and the first letter capitalized, so `living_room` becomes `Living room`.
The name is what Home Assistant shows, and it decides the entity IDs of a new object.

## Pumps

A pump is either an entity ID, or a mapping of the stored pump fields:

| Field | Value |
| --- | --- |
| `entity_id` | Required. The switch that runs the pump. |
| `overrun_seconds` | How long the pump keeps running after the last valve closes. Defaults to 120. |
| `power_feedback_entity`, `flow_feedback_entity`, `fault_feedback_entity` | Optional feedback entities. |
| `power_feedback_max_age_seconds`, `flow_feedback_max_age_seconds`, `fault_feedback_max_age_seconds` | Feedback older than this is stale. |

`manifold_pump: switch.manifold_pump` is shorthand for `manifold_pump: {entity_id: switch.manifold_pump}`.
Pumps are always Plant equipment, and any loop can use any pump.

## Valves

A valve is either an entity ID, or a mapping of the stored valve fields:

| Field | Value |
| --- | --- |
| `entity_id` | Required. The switch or valve that opens the valve. |
| `opening_time_seconds` | How long the valve needs to open before the pump may start. Defaults to 30. |
| `readiness_entity_id` | Optional entity that reports the valve is fully open. When set, the pump waits for it. |
| `position_feedback_entity` | Optional sensor that reports the measured valve position. |
| `position_feedback_max_age_seconds` | Position feedback older than this is stale. |

A valve written under a room's `valves` belongs to that room.
A valve written under the top-level `valves` is a shared valve, owned by the Plant.

A loop can also create valves inline, as described below, so many files never write a `valves` section at all.

## Loops

A loop is a water path through one or more valves and one pump:

| Field | Value |
| --- | --- |
| `valves` | Required, a non-empty list. Each item is a valve slug, or an entity ID that creates a new valve. |
| `pump` | Required. A pump slug. |
| `cooling_enabled` | Allow the loop to deliver cooling. |
| `supply_temperature_sensor`, `surface_temperature_sensor` | Cooling references for condensation protection. |
| `condensation_margin` | Cooling is blocked when the reference comes within this margin of the dew point. Defaults to 2. |
| `supply_temperature_max_age_seconds`, `surface_temperature_max_age_seconds` | Reference readings older than this are stale. |

An item of `valves` that contains a dot is an entity ID.
It creates a new valve with the same owner as the loop, with slug `<loop slug>_valve` and name `<loop name> valve`.
A second inline valve in the same loop gets `<loop slug>_valve_2` and `<loop name> valve 2`, and so on.
An inline valve keeps the default opening time; write it out under `valves` to set other fields.

A loop written under a room's `loops` is a private loop of that room.
It also delivers heat to that room, so it accepts two more keys for that connection, its Delivery Route:

| Field | Value |
| --- | --- |
| `route_id` | Optional UUID of the route. |
| `route_enabled` | `false` keeps the loop but stops the room from requesting it. Defaults to `true`. |

A loop written under the top-level `loops` is a shared loop, owned by the Plant.
Rooms connect to it through their `shared_loops`.

## Rooms

A room is one Comfort Zone with its thermostat, its sensors, and its loops:

| Field | Value |
| --- | --- |
| `thermostat` | The room's thermostat. Defaults to a Hydronicus thermostat with default settings. |
| `temperature_sensors` | A list of entity IDs or sensor mappings. Required for a Hydronicus thermostat. |
| `humidity_sensors` | A list of entity IDs or sensor mappings, used for the dew point when cooling. |
| `temperature_aggregation` | `mean`, `median`, `minimum`, `maximum`, `designated_reference`, or `weighted_mean`. Defaults to `mean`. |
| `valves` | Slug to private valve of the room. |
| `loops` | Slug to private loop of the room. |
| `shared_loops` | A list of shared loop slugs that also deliver heat to the room. |

A room needs at least one enabled loop, private or shared.

`thermostat` is either a `climate.*` entity ID, for an existing Home Assistant thermostat that owns the room's demand, or a mapping:

| Field | Value |
| --- | --- |
| `kind` | `hydronicus` (the default) or `external_climate`. |
| `entity_id` | The climate entity, for `external_climate` only. |
| `initial_target_temperature` | The target of a fresh thermostat. Defaults to 21. |
| `heating_start_delta`, `heating_stop_delta` | Heating hysteresis. Default to 0.3 and 0.1. |
| `cooling_start_delta`, `cooling_stop_delta` | Cooling hysteresis. Default to 0.3 and 0.1. |
| `minimum_active_duration_seconds`, `minimum_idle_duration_seconds` | Demand holds. Default to 0. |
| `preset_targets` | A mapping with any of `comfort`, `eco`, and `away`. |
| `initial_preset` | `none`, or one of the configured presets. |

`thermostat: climate.study` is shorthand for `thermostat: {kind: external_climate, entity_id: climate.study}`.
Hydronicus only reads an external thermostat's `hvac_action` and never commands it.

A sensor is either an entity ID or a mapping of the stored sensor fields:

| Field | Value |
| --- | --- |
| `entity_id` | Required. |
| `required` | A required sensor that is stale or unavailable blocks the room. Defaults to `true`. |
| `designated_reference` | Used alone by `designated_reference` aggregation. Exactly one sensor must set it for that policy. |
| `weight` | Relative weight in `weighted_mean` aggregation. |
| `calibration_offset` | Added to every reading before aggregation. |
| `max_age_seconds` | A reading older than this is stale. |

Items of `shared_loops` are loop slugs, or mappings with `loop` and the optional `route_id` and `route_enabled`.

This file uses the long forms: sensor metadata, thermostat settings, a room valve with feedback, and an external thermostat.

```yaml
hydronicus: 1
name: Upstairs
pumps:
  upstairs_pump:
    entity_id: switch.upstairs_pump
    overrun_seconds: 180
rooms:
  bedroom:
    thermostat:
      initial_target_temperature: 20
      heating_start_delta: 0.4
      minimum_idle_duration_seconds: 600
      preset_targets:
        comfort: 21
        eco: 18.5
    temperature_sensors:
      - entity_id: sensor.bedroom_temperature
        designated_reference: true
      - entity_id: sensor.bedroom_window_temperature
        required: false
        calibration_offset: -0.5
        max_age_seconds: 1800
    temperature_aggregation: designated_reference
    valves:
      bedroom_valve:
        entity_id: valve.bedroom
        opening_time_seconds: 180
        readiness_entity_id: binary_sensor.bedroom_valve_open
    loops:
      bedroom_loop:
        valves: [bedroom_valve]
        pump: upstairs_pump
  study:
    thermostat: climate.study
    loops:
      study_loop:
        valves: [switch.study_valve]
        pump: upstairs_pump
```

## Ownership and shared equipment

Every object has one owner: the Plant or one room.

- A room owns itself, its routes, and the valves and loops written under it.
- Pumps, sources, the source selector, and the top-level valves and loops belong to the Plant and are called Plant equipment.
- A private loop may use the valves of its own room and shared valves.
- A shared loop may use only shared valves.
- A room may connect to its own loops and to shared loops, never to another room's loop.

References point only from a room toward the Plant, never from the Plant or another room into a room.
This makes ownership deletion-closed: removing a room removes exactly the room, its routes, and its private loops and valves, and always leaves a valid Plant.
It is why Home Assistant can delete a room without asking Hydronicus first.

The Home Assistant UI creates and edits rooms, their private loops and valves, pumps, and Dry run.
Shared loops, shared valves, and the source selector are created and edited only through the plant file, although room forms can select existing shared loops and shared valves.
Sources can be written in the file or added in the UI as **Source** entries.

This file has a shared hall loop used by two rooms, and a Bedroom loop that also needs the shared hall valve open:

```yaml
hydronicus: 1
name: Shared manifold
pumps:
  pump: switch.pump
valves:
  hall_valve:
    entity_id: switch.hall_valve
    opening_time_seconds: 120
loops:
  hall_loop:
    valves: [hall_valve]
    pump: pump
rooms:
  living_room:
    temperature_sensors: [sensor.living_temperature]
    shared_loops: [hall_loop]
  bedroom:
    temperature_sensors: [sensor.bedroom_temperature]
    shared_loops:
      - loop: hall_loop
        route_enabled: false
    loops:
      bedroom_loop:
        valves: [switch.bedroom_valve, hall_valve]
        pump: pump
```

Bedroom keeps its connection to the hall loop but does not request it, because the route is disabled.
The review warns that the hall valve is shared, because one valve serving two loops cannot give them independent flow.

One room can also have several private loops that share a room valve:

```yaml
hydronicus: 1
name: Big room
pumps:
  pump: switch.pump
rooms:
  hall:
    temperature_sensors: [sensor.hall_temperature]
    valves:
      hall_zone_valve: switch.hall_zone_valve
    loops:
      north_loop:
        valves: [hall_zone_valve, switch.north_valve]
        pump: pump
      south_loop:
        valves: [hall_zone_valve, switch.south_valve]
        pump: pump
```

A valve, pump, or loop that no enabled route reaches is accepted as unused equipment.
The review lists it as a warning that never needs confirmation, and Hydronicus never requests it.

## Sources and the source selector

A source is a mapping of the stored source fields:

| Field | Value |
| --- | --- |
| `source_type` | `external` (the default) or `temperature_qualified_buffer`. |
| `priority` | When several sources are available, the lowest number wins. Defaults to 100. |
| `availability_entity` | Optional entity that reports whether the source can supply heat. |
| `source_demand_entity` | Optional switch or valve that requests heat from the source. |
| `temperature_entity` | The buffer temperature sensor. Required for a temperature-qualified buffer. |
| `minimum_temperature` | The buffer qualifies only at or above this temperature. |
| `maximum_age_seconds` | A buffer reading older than this is stale. |
| `hysteresis` | Once qualified, the buffer stays qualified until it falls this far below the minimum. Defaults to 0.5. |

`source_selector` is one mapping with `entity_id`, `break_interval_seconds` (default 30), `minimum_dwell_seconds` (default 300), `release_option`, and `shadow_only`.
Source-selector operations stay in Dry run in this release.

```yaml
hydronicus: 1
name: Sources
pumps:
  pump: switch.pump
rooms:
  living_room:
    temperature_sensors: [sensor.living_temperature]
    humidity_sensors: [sensor.living_humidity]
    loops:
      living_loop:
        valves: [switch.living_valve]
        pump: pump
        cooling_enabled: true
        supply_temperature_sensor: sensor.living_supply
        condensation_margin: 3
sources:
  heat_pump:
    priority: 1
    source_demand_entity: switch.heat_pump_demand
  buffer:
    source_type: temperature_qualified_buffer
    temperature_entity: sensor.buffer_temperature
    minimum_temperature: 35
    priority: 2
source_selector:
  entity_id: select.heat_source
  minimum_dwell_seconds: 600
```

Importing a file gives every source its own **Source** entry under the Plant, so a source can then also be changed in the UI.

## IDs and entity IDs

Every object, and the Plant, accepts an optional `id`, and every route accepts an optional `route_id`, each a UUID.
An object that keeps its ID keeps its devices, its entities, their entity IDs, and their history.

Without an ID, Hydronicus derives one from the Plant ID and the slug, so the same file always produces the same IDs for the same Plant.
A file without a top-level `id` becomes a new Plant with a new ID when you import it.

Export writes every ID explicitly, so importing an exported file on another instance rebuilds the Plant with the same entity IDs.
Importing a file whose `id` matches a Plant that already exists stops with **This plant is already configured.**
Delete the existing Plant first to rebuild it from its file, or remove the top-level `id` to create a copy.

When you edit a Plant's file, a top-level `id` must match the Plant.
Remove the line, or keep the exported one, to apply the file to the same Plant.
An object with a new slug and no `id` is a new object, and an object whose `id` disappears from the file is removed.

## The exported form

Export writes the canonical form of a Plant:

- every object in its long form, with explicit `id` and `name`, and every route with its `route_id`;
- `route_enabled` only when it is `false`;
- the stored fields exactly as stored, with collections sorted by slug;
- slugs made from names.

This is the export of a one-room Plant:

```yaml
hydronicus: 1
id: 0b1f6c3e-2d4a-4f5b-9c8d-7e6f5a4b3c2d
name: Flat
pumps:
  pump:
    id: a33aefa6-f061-56eb-b7b6-318fd6d13252
    name: Pump
    entity_id: switch.pump
rooms:
  bedroom:
    id: 510eb94b-7003-5859-80c7-658755af8533
    name: Bedroom
    thermostat:
      kind: hydronicus
    temperature_sensors:
    - entity_id: sensor.bedroom_temperature
    valves:
      bedroom_loop_valve:
        id: b2b5a38a-5a31-5acd-b65c-570d37fd1268
        name: Bedroom loop valve
        entity_id: switch.bedroom_valve
    loops:
      bedroom_loop:
        id: 076d48c2-f79e-5847-a699-35fc5bd9f072
        name: Bedroom loop
        valves:
        - bedroom_loop_valve
        pump: pump
        route_id: 1bd342db-127d-5639-8663-9928063bec3f
```

Export makes each slug from the object's name:

1. The name is lowercased and accented letters are folded to ASCII, so `Ärkély` becomes `arkely`.
2. Every run of other characters becomes `_`, and leading and trailing underscores are removed.
3. A slug that would start with a digit gets its kind as a prefix: `room_`, `loop_`, `valve_`, `pump_`, or `source_`, so a pump named `2nd floor pump` becomes `pump_2nd_floor_pump`.
4. A name with nothing left, such as `!!!`, becomes the kind itself, such as `valve`.
5. When two objects of one kind get the same slug, the later one in name and ID order gets `_2`, the next `_3`, and so on, such as `arkely_valve_2`.

Exporting a file you imported gives the canonical form of that file, and importing that export gives the same Plant again.

## Errors

A file that cannot be imported keeps the form open with the error `The plant file is not valid at <path>: <message>`.
The path is a dotted list of keys, with list items as numbers, such as `rooms.bedroom.loops.bedroom_loop.pump` for an unknown pump slug, or `rooms.Living room` for a slug with capitals and a space.
A problem with the whole Plant, such as invalid YAML or a topology that does not compile, is reported at the top level.

Typical problems and where they are reported:

| Problem | Reported at |
| --- | --- |
| Unknown key, invalid slug, or duplicate slug | That key. |
| Unknown valve, loop, or pump slug | The reference. |
| A room valve used by another room's loop, or by a shared loop | The reference. |
| A room without an enabled loop | The room. |
| A Hydronicus thermostat without temperature sensors | The room's `temperature_sensors`. |
| The same valve or pump entity bound twice | The second binding of that entity. |
| Cooling without a supply or surface reference | The loop. |
| Cooling without room temperature or humidity sensors | The room's `temperature_sensors` or `humidity_sensors`. |
| Designated reference without exactly one reference sensor | The room's `temperature_sensors`. |

A file that binds an entity provided by Hydronicus itself is refused with the path of that binding, because it would feed the Plant back into itself.
An edited file identical to the current Plant stops with **The plant file matches the current Plant, so nothing was changed.**
