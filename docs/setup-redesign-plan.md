# Setup redesign plan

This plan makes a first Hydronicus Plant easy and reproducible to set up, and makes every compilable topology reachable.
It is the setup-flow redesign that `docs/ha-modernization-plan.md` left out of scope.
It is the single source of truth for decisions, contracts, invariants, workstreams, and acceptance criteria.
The lead agent runs the waves in order and dispatches each workstream to a subagent with the [subagent brief](#subagent-brief).
A subagent reads the sections its brief names and its own workstream, not the whole plan.

## Evidence

Investigated on 2026-09-25 against Home Assistant 2026.9.3, with a throwaway test driving the real config and subentry flows.
Revalidated the same day against modernization commit `b4b22fe`, with identical results.

- Home Assistant gives an integration no veto over subentry deletion (`ConfigEntries.async_remove_subentry`), so every subentry must be removable without breaking the graph.
- The current flows get there by offering only parent-owned objects in subentry forms (`subentry_owned_ids` in `entry_configuration.py`).
- `core/topology.py` rejects any zone, valve, pump, or circuit that no enabled route reaches.
- Together these stop subentries from building independent branches: a new circuit can only reuse the first valve, a new valve can only join the first circuit, and a new zone can only route to the first circuit.
- Building Living room and Bedroom, each with its own valve and one shared pump, produced Bedroom to Living loop and Living room to Bedroom loop, with both loops on the Living loop valve.
- No flow can add a second pump.
- The first Plant takes five forms, with about 20 visible and 17 collapsed fields, before the review.
- A Plant cannot be exported, imported, or rebuilt with the same object IDs, so staging runs are clicked by hand.
- Home Assistant removes every entity of a removed subentry (`EntityRegistry.async_clear_config_subentry`), and subentry unique IDs must be unique across all subentry types of one entry.
- Entity unique IDs are `<plant_id>_..._<object_id>_...` and device identifiers are `<plant_id>:<kind>:<object_id>`; neither contains a subentry ID, so ownership can move without renaming anything.

## Outcome

- A three-room manifold with one pump takes six screens: a menu, a Plant form, one form per room, and a review.
- Every topology the core can compile is reachable, the common ones through the UI and all of them through the plant file.
- A plant file rebuilds a Plant exactly, including entity IDs, on any instance.
- Existing installations migrate without losing entity IDs, entity customizations, devices, or history.

## Terminology

| UI term | Core term | Meaning |
| --- | --- | --- |
| Plant | Plant | One config entry and its complete graph. |
| Room | Comfort Zone | One zone with its thermostat, its Delivery Routes, and its private loops and valves, exposed as one `room` subentry. |
| Loop | Hydraulic Circuit | A water path through one or more valves and one pump. |
| Private loop, private valve | Circuit, Valve | Owned by exactly one room. |
| Plant equipment | Pump, Valve, Circuit, Source, source selector | Owned by the Plant; shared valves and shared loops are Plant equipment. |
| Plant file | none | The YAML plant document defined in [K5](#k5-plant-file-format). |

Core code keeps the names Zone and Circuit.
Flow strings and documentation use Room and Loop.
Entity names and device names stay unchanged, so newly generated entity IDs stay unchanged.

## Decisions

These are settled; implement them rather than revisiting them.

1. **Rooms.** A `room` subentry replaces the `zone`, `circuit`, and `actuator` subentry types, and `source` subentries stay unchanged.
2. **Deletion-closed ownership.** Every graph object has one owner, the Plant or one room, and references point only toward the Plant ([K1](#k1-ownership)).
   Removing a room subentry removes exactly its room closure and always leaves a valid graph, so no form filters its options for deletion safety.
3. **Unused Plant equipment is a warning.** A valve, pump, or loop that no enabled route reaches compiles with an `unused_equipment` warning and is never requested ([K2](#k2-unused-equipment)).
4. **Guided setup** replaces the initial flow.
   New Plants always start in Dry run, and leaving Dry run happens only in Plant settings, behind the existing confirmation.
5. **UI scope.** The UI creates and edits rooms, their private loops and valves, pumps, and Dry run.
   Shared loops, shared valves, Plant-owned sources, and the source selector are created and edited only through the plant file, and room forms can select existing shared loops and shared valves.
6. **The plant file is import and export only.** The user chose this on 2026-09-25, and nothing reads `configuration.yaml`.
7. **Config entry version 3.0.** Version 2.0 entries migrate one way, and version 1.1 entries chain through 2.0 in the same call.
8. **IDs.** Export writes explicit IDs for the Plant and every object, a hand-written file without IDs derives them deterministically ([K5](#k5-plant-file-format)), and UI-created objects keep random UUIDs.
9. **A room form creates at most one private loop.** Further private loops come from the room's `add_loop` step or the plant file.
10. **Export surfaces.** Plant settings show the plant file in a dialog, and the admin action `hydronicus.export_plant` returns it as response data.
11. **Confirmation.** A warning other than `unused_equipment` that the change introduces requires the existing confirm step before saving, and `unused_equipment` never blocks a save.
    A warning is identified by its code and equipment, so a warning the Plant already had, such as the shared pump of a manifold, is not confirmed again on every edit; an output another Plant binds is always confirmed.
12. **Flow modules.** Flow code lives in a `flows/` package so each workstream owns separate modules, and `config_flow.py` only composes them.

## Invariants

Every workstream preserves these, and every review checks them.

- Dry run issues zero actuator service calls.
- Every graph change (room, loop, pump, import, plant file edit, migration) invalidates output authorization and returns to Dry run, completing the safe shutdown first when the Plant is active.
- Reload, unload, removal, and Home Assistant stop remain command-free lifecycle boundaries.
- **Deletion-closed:** removing any room subentry leaves a graph that passes `validate_ownership` and compiles.
- **Round-trip:** importing an exported plant file reproduces the topology, ownership, and room and source subentry set exactly, and exporting an imported file yields the canonical form of that file.
- Migration keeps every entity unique ID, entity ID, entity registry customization, and device identifier.
- `custom_components/hydronicus/core/` stays free of Home Assistant imports, keeps at least 90 percent coverage, and passes mypy.
- `make verify` is the gate.

## Working rules

- A behaviour change starts **red**: first a test that fails on the old behaviour, then the change that turns it **green**.
- Edit only your **owned files**, and report a needed change elsewhere as a **contract request** naming the file, the change, and the reason.
- When a contract turns out wrong against the installed Home Assistant, follow the installed API, keep the contract's intent, and report the deviation.
- Read a Home Assistant API in `.venv/lib/python3.14/site-packages/homeassistant/` before relying on it.
- Edit only your owned keys of `strings.json`, then copy `strings.json` to `translations/en.json` byte for byte.
- In `tests/integration/test_translations.py`, edit only the cases for your own flows.
- From Wave 2 on, `flows/common.py` belongs to the lead; put a new helper in your own module and request a move when another module needs it.
- Prose uses plain dashes, and long Markdown puts each full sentence on its own physical line.
- Commit messages use the repository prefixes (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`) and carry no agent attribution or co-author lines.
- `CHANGELOG.md`, `RELEASE_NOTES.md`, version numbers, and generated files stay untouched.
- Quality, simplicity, robustness, and long-term maintainability outweigh short-term effort.
- Fix or explicitly report lint failures, test failures, and flaky tests, even when they are unrelated to your workstream.
- The large synthetic benchmark can be timing-sensitive under parallel load; rerun it alone before calling it a failure.
- Map your done criteria to evidence with the repository-local `hydronicus-verify` skill in `.agents/skills/hydronicus-verify/SKILL.md`.

## Contracts

Each contract has one owner, named in its heading or first line; consumers code against it as written.

### K1 Ownership

Module `custom_components/hydronicus/core/ownership.py`, built by the lead in Wave 0.

```python
class OwnershipError(ValueError):
    object_ids: tuple[str, ...]  # the objects that break the rule

@dataclass(frozen=True, slots=True)
class PlantOwnership:
    room_objects: Mapping[str, str]  # private circuit or valve id -> owning zone id

@dataclass(frozen=True, slots=True)
class RoomClosure:
    zone_id: str
    route_ids: frozenset[str]
    circuit_ids: frozenset[str]
    valve_ids: frozenset[str]

def owner_of(configuration: PlantConfiguration, ownership: PlantOwnership, object_id: str) -> str | None: ...
def validate_ownership(configuration: PlantConfiguration, ownership: PlantOwnership) -> None: ...
def derive_ownership(configuration: PlantConfiguration) -> PlantOwnership: ...
def room_closure(configuration: PlantConfiguration, ownership: PlantOwnership, zone_id: str) -> RoomClosure: ...
def without_room(
    configuration: PlantConfiguration, ownership: PlantOwnership, zone_id: str
) -> tuple[PlantConfiguration, PlantOwnership]: ...
```

`owner_of` returns the owning zone id, or `None` for the Plant.
`validate_ownership` raises `OwnershipError` with a message naming the offending objects when a rule fails.
Like the typed errors in `core/configuration.py` and `core/topology.py`, it carries object ids so adapters can point at the right field or plant file path without parsing messages.
The rules:

- **R1** Every key of `room_objects` is a circuit or valve id, and every value is a zone id.
- **R2** A zone owns itself, and a route belongs to the room of its `zone_id`; pumps, sources, the source selector, and every object absent from `room_objects` belong to the Plant.
- **R3** A Plant-owned circuit references only Plant-owned valves.
- **R4** A room-owned circuit references only valves owned by the same room or by the Plant.
- **R5** A route from zone Z targets a circuit owned by Z's room or by the Plant.
- **R6** Every room-owned circuit has at least one route from its owning zone, and every room-owned valve is referenced by at least one circuit of its room.

R3 to R5 make ownership deletion-closed, because no object outside a room closure references an object inside it.

`derive_ownership` is the migration rule.
A circuit is private to zone Z when every route targeting it comes from Z.
A valve is private to Z when every circuit referencing it is private to Z.
Everything else belongs to the Plant.
For any configuration that compiles, the derived ownership satisfies R1 to R6.

### K2 Unused equipment

Module `custom_components/hydronicus/core/topology.py`, changed by the lead in Wave 0.

- A valve, pump, or circuit that no enabled route reaches no longer raises `TopologyValidationError`.
- The compiler emits one `TopologyWarning(code="unused_equipment")` per unused object, following the existing convention of putting the equipment id in `valve_id` and setting `equipment_kind` and `equipment_id`, and `EquipmentKind` gains a `CIRCUIT` member.
- A zone that no enabled route leaves is still an error.
- A Plant with no zones compiles.
- The controller never requests unused equipment, and with Dry run off an unused valve or pump receives exactly the commands an idle used one receives.
- `ControlPlan.cooling_actuator_ids` may still list unused cooling equipment; it only forces start commands into shadow, so it requests nothing.

### K3 Stored data version 3

Config entry version 3, minor version 0, owned by W1.

```text
entry.data
  name, plant_id, dry_run, requested_mode                      unchanged
  output_authorization, diagnostics_include_actuator_details   unchanged and optional
  topology                                                     zones, valves, pumps, circuits, routes, sources, source_selector
  subentry_objects                                             {zone_id: "room", source_id: "source"}
  room_objects                                                 {circuit_or_valve_id: zone_id}

room subentry     type "room", data {"id": zone_id}, unique_id zone_id, title zone name
source subentry   unchanged
```

- Record shapes inside `topology` are exactly those decoded by `core/configuration.py`, and this redesign changes no record field.
- Every zone has exactly one room handle, and `room_objects` is `PlantOwnership.room_objects`.
- A Plant-owned source without a subentry stays valid, and editing the plant file gives every source a subentry.
- A zone whose room handle disappeared was deleted, so setup and reload remove its room closure through `without_room`.
- Version 3 readers reject the `zone`, `circuit`, and `actuator` subentry types.

Migration from 2.0 to 3.0 runs in `async_migrate_entry` in this order.
Every step is idempotent, so a restart at any point resumes to the same result.

0. While migration has not started (no `room` subentry and no `legacy:` unique ID), remove every object whose version 2 handle was deleted while the entry was unloaded, with version 2 removal semantics, and write that version 2.0 data durably.
   A version 2 Plant with circuits always has zones, so this condition cannot misread a Plant that stopped between steps 6 and 7.
1. Compute the plan from the topology alone: `derive_ownership`, one room per zone, and the target owner of every object.
2. Give every legacy `zone`, `circuit`, and `actuator` subentry the unique ID `legacy:<object id>`, which frees the object IDs for room handles.
3. Add a `room` subentry for every zone that has none.
4. Move every entity registry entry of the config entry to its target owner with `async_update_entity(config_subentry_id=...)`; the target object is the object UUID, other than the Plant id, contained in the entity's unique ID, and an entity without one belongs to the Plant.
5. Move every topology device to the same owner with the move API of the installed device registry.
6. Remove the legacy subentries, which by now own no entities or devices.
7. Write the version 3 data, with output authorization invalidated, together with version 3.0 in one `async_update_entry` call.

### K4 Graph edit API

Module `custom_components/hydronicus/entry_configuration.py`, built by W1 and used by W3, W4, and W5.
Every function is pure over mappings and imports nothing from Home Assistant.
Every function that returns new data validates K1, compiles, and returns data with Dry run on and output authorization removed.

```python
@dataclass(frozen=True, slots=True)
class EffectivePlant:
    configuration: PlantConfiguration
    ownership: PlantOwnership
    compiled: CompiledPlant
    object_subentry_ids: Mapping[str, str]  # zone, room-owned circuit and valve, and source ids -> subentry id

@dataclass(frozen=True, slots=True)
class RoomDraft:
    zone: dict[str, Any]            # stored zone record
    circuits: list[dict[str, Any]]  # private stored circuit records
    valves: list[dict[str, Any]]    # private stored valve records
    routes: list[dict[str, Any]]    # every route from this zone

@dataclass(frozen=True, slots=True)
class SubentrySync:
    add: list[dict[str, Any]]       # ConfigSubentryData-shaped handles
    remove: list[str]               # subentry ids
    retitle: list[tuple[str, str]]  # subentry id, new title

class EquipmentInUseError(ValueError):
    users: tuple[str, ...]          # names of the loops using the equipment

def effective_plant(entry: Any) -> EffectivePlant: ...
def effective_plant_from_data(data: Mapping[str, Any]) -> EffectivePlant: ...  # object_subentry_ids is empty
def new_plant_data(*, name: str, plant_id: str, topology: Mapping[str, Any], ownership: PlantOwnership) -> dict[str, Any]: ...
def room_draft(data: Mapping[str, Any], zone_id: str) -> RoomDraft: ...
def data_with_room(data: Mapping[str, Any], draft: RoomDraft) -> dict[str, Any]: ...  # inserts or replaces draft.zone["id"]
def data_with_pump(data: Mapping[str, Any], pump_id: str, record: Mapping[str, Any] | None) -> dict[str, Any]: ...  # None removes
def data_with_plant(data: Mapping[str, Any], imported: ImportedPlant) -> dict[str, Any]: ...  # replaces name, topology, and ownership
def subentries_for(data: Mapping[str, Any]) -> list[dict[str, Any]]: ...  # room and source handles for async_create_entry
def subentry_sync(entry: Any, data: Mapping[str, Any]) -> SubentrySync: ...
```

`data_with_pump` raises `EquipmentInUseError` when removing a pump that a loop uses.
`flows/common.py` provides `async_persist_entry_data(flow, entry, data) -> bool`, which reaches Dry run through the runtime first when the Plant is active and returns `False` when that shutdown cannot complete.
`migration.py` provides `async_move_object_registrations(hass, entry, owners)`, which moves the entities and devices of every object id in `owners` to the given subentry id, or to the parent for `None`; migration and plant file edits share it.

### K5 Plant file format

Module `custom_components/hydronicus/core/plant_document.py`, built by W2.

```python
PLANT_FILE_FORMAT: Final = 1

class PlantDocumentError(ValueError):
    path: str  # dotted path such as "rooms.bedroom.loops.bedroom_loop.pump", empty for whole-plant errors

@dataclass(frozen=True, slots=True)
class ImportedPlant:
    plant_id: str
    name: str
    topology: dict[str, Any]  # stored version 3 topology collections
    ownership: PlantOwnership
    compiled: CompiledPlant
    entity_paths: Mapping[str, str]  # every bound entity ID -> the first path that binds it

def import_plant_document(document: Mapping[str, Any], *, plant_id: str) -> ImportedPlant: ...
def export_plant_document(
    *, name: str, plant_id: str, topology: Mapping[str, Any], ownership: PlantOwnership
) -> dict[str, Any]: ...
```

The file's `id` wins over the `plant_id` argument, which is the fallback for a file without one.
The module works on parsed mappings; YAML is only the transport, and adapters parse and dump it.

Example:

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
    thermostat: climate.bedroom
    loops:
      bedroom_loop:
        valves: [switch.bedroom_valve]
        pump: manifold_pump
```

Top-level keys:

| Key | Required | Value |
| --- | --- | --- |
| `hydronicus` | yes | Format version, `1`. |
| `id` | no | Plant UUID. |
| `name` | yes | Plant name. |
| `pumps` | no | Slug to pump. |
| `valves` | no | Slug to Plant-owned (shared) valve. |
| `loops` | no | Slug to Plant-owned (shared) loop. |
| `rooms` | no | Slug to room. |
| `sources` | no | Slug to source. |
| `source_selector` | no | The stored source selector record. |

Object fields:

- Leaf fields use exactly the stored record keys and units decoded by `core/configuration.py`, such as `entity_id`, `opening_time_seconds`, and `overrun_seconds`, so the file adds no second vocabulary.
- Every object accepts an optional `id` and an optional `name`, and a missing name comes from the slug, with underscores as spaces and the first letter capitalized.
- A pump or valve may be written as an entity ID string, shorthand for `{entity_id: <string>}`.
- A loop has `valves` (a list), `pump` (a pump slug), and the stored circuit fields other than `id`, `valve_ids`, and `pump_id`.
- A loop's `valves` item is a valve slug, or an entity ID (it contains a dot) as shorthand for a new valve owned by the loop's owner, with slug `<loop slug>_valve`, `<loop slug>_valve_2`, and so on, and name `<loop name> valve`, `<loop name> valve 2`, and so on.
- A room has `thermostat`, `temperature_sensors`, `humidity_sensors`, `temperature_aggregation`, `valves`, `loops`, and `shared_loops`.
- A room's `thermostat` is the stored thermostat record with `kind` defaulting to `hydronicus`, or a `climate.*` entity ID as shorthand for an external thermostat.
- A room's `temperature_sensors` and `humidity_sensors` are lists of entity IDs or stored sensor metadata records.
- A room's `valves` and `loops` are its private valves and loops, and each private loop accepts optional `route_id` and `route_enabled`.
- A room's `shared_loops` items are loop slugs, or `{loop, route_id, route_enabled}` mappings.
- A room-owned loop may use valves of its own room and Plant-owned valves, and a Plant-owned loop may use only Plant-owned valves.
- Slugs match `^[a-z][a-z0-9_]*$` and are unique per kind across the whole file: all valves share one namespace, all loops share one namespace, and rooms, pumps, and sources each have their own.
- Unknown keys are errors.
- Dry run, output authorization, requested mode, and the diagnostics flag are not part of the file, and an import always starts in Dry run.

IDs:

- An object without `id` gets `uuid5(UUID(plant_id), "<kind>:<slug>")`, with kind `zone`, `valve`, `pump`, `circuit`, `source`, or `source_selector`.
- A route without `route_id` gets `uuid5(UUID(plant_id), "route:<room slug>:<loop slug>")`.

Import resolves slugs, builds stored records, decodes them with `plant_configuration_from_entry_data`, checks `validate_ownership`, and compiles.
Any failure raises `PlantDocumentError` at the most specific path:

- a shape or reference error points at the offending key;
- a typed core error points at the object it names, mapping ids back to slugs: `DuplicateActuatorBindingError` to the second binding of the entity, `CoolingReferenceError` to the loop, `CoolingObservationError` to the room's `temperature_sensors` or `humidity_sensors`, `DesignatedReferenceError` to the room's `temperature_sensors`, `BufferTemperatureRequiredError` to the source, and `OwnershipError` to the first object it names;
- any other decode or compile error has an empty path and keeps the core message.

The module cannot see the entity registry, so adapters check `entity_paths` for Hydronicus-provided entities.

Export writes the canonical form:

- long forms only, with explicit `id` and `name` on the Plant and every object and explicit `route_id` on every route;
- `route_enabled` only when it is `false`;
- stored fields exactly as stored, with keys in stored-decoder order and collections sorted by slug;
- slugs made from names: lowercased, every run of other characters replaced by `_`, a leading digit prefixed with the kind, an empty result replaced by the kind, and duplicates suffixed `_2`, `_3` in (name, id) order.

### K6 Flow contract

Field keys equal stored record keys wherever a stored key exists, and existing form keys such as `temperature_sensors`, `external_climate_entity`, and `pump_entity` keep their names.
Menu labels live in `step.<menu step>.menu_options`, and a menu option opens the step with the same name.

#### Flow conventions

Every flow keeps the guards the current flows already enforce; the current `config_flow.py` is the reference implementation.

- **Own-entity guard.** Every flow handler mixes in the guard (today `_OwnEntityPickerMixin`), so entity pickers hide Hydronicus entities, and runs the submit check (today `_own_entity_errors`), which reports `own_entity` on the field, or on the form for a field inside a section.
  Every new entity field key, including `valves`, joins the shared entity-field set (today `_ENTITY_FIELDS`), and `external_climate_entity` keeps its dedicated `thermostat_loop` check.
- **Empty required selections.** `vol.Required` accepts the empty list that a lazily loaded picker can submit, so a flow checks each required multi-select before normalizing and reports the field-level `*_required` key.
- **Typed errors to fields.** A rejected proposal maps typed core errors to the field the user can fix: `DuplicateActuatorBindingError` to `actuator_entity_in_use`, `CoolingReferenceError` to `cooling_reference_required`, `CoolingObservationError` to `temperature_required_for_cooling` or `humidity_required_for_cooling` on a room and `cooling_requires_zone_observations` on a loop, `DesignatedReferenceError` to `designated_reference_count`, and `EquipmentInUseError` to `equipment_in_use`.
  Any other error falls back to the form's generic key, with the core message as its `error` placeholder.
- **Resubmission.** A rejected form is shown again with the submitted values (today `_with_submitted_values`).
- **Discoverable keys.** Error keys are string literals, either assigned in the handler or returned by a helper merged with `errors.update(...)`, so the static discovery in `tests/integration/test_translations.py` finds them.
  Extend that discovery when a new pattern is unavoidable.
- **Existing keys first.** A key that already exists keeps its meaning and text, and a flow reuses it before adding a new one.

#### Room basics

Module `flows/room_form.py`, built by W3 and used by W5.

| Field | Selector | Rule |
| --- | --- | --- |
| `name` | text | Required. |
| `temperature_sensors` | sensor entities with the temperature device class, multiple | Required unless `external_climate_entity` is set. |
| `external_climate_entity` | climate entity | Optional; when set, the room uses that external thermostat. |
| `valves` | switch or valve entities, multiple | Creates the room's first private loop `<name> loop`, with valves named by the K5 shorthand rule (`<loop name> valve`, `<loop name> valve 2`, and so on). |
| `pump` | select of Plant pumps | Shown only when the Plant has two or more pumps; with exactly one pump it is implied. |
| `shared_loops` | select of Plant-owned loops, multiple | Shown only when shared loops exist. |

A room needs `valves` or `shared_loops`.

```python
def room_form_schema(
    *,
    pumps: Sequence[SelectOptionDict],
    shared_loops: Sequence[SelectOptionDict],
    defaults: Mapping[str, Any] | None = None,
    include_valves: bool = True,
) -> vol.Schema: ...
def room_draft_from_form(
    user_input: Mapping[str, Any], *, plant: EffectivePlant, existing: RoomDraft | None
) -> RoomDraft: ...  # a new room gets a new zone id
def room_form_errors(
    hass: HomeAssistant, user_input: Mapping[str, Any], plant: EffectivePlant
) -> tuple[dict[str, str], dict[str, str]]: ...  # errors by field or "base", and placeholders; empty when valid
```

#### Room subentry flow

Module `flows/room.py`, built by W3.

| Step | Kind | Fields or options |
| --- | --- | --- |
| `user` | form | Room basics; aborts `no_pumps` when the Plant has no pump. |
| `review` | form | `confirm`, with placeholder `warnings`. |
| `reconfigure` | menu | `room`, `thermostat` (Hydronicus thermostat only), `sensors`, `add_loop`, `edit_loop` (only when a private loop exists). |
| `room` | form | `name`, `temperature_sensors`, `external_climate_entity`, `shared_loops`. |
| `thermostat` | form | The current Hydronicus thermostat fields: start and stop deltas, minimum durations, preset targets, and section `cooling`. |
| `sensors` | form | `temperature_aggregation`, `humidity_sensors`, `configure_sensor_metadata`. |
| `sensor_metadata`, `sensor_policy` | form | The current per-sensor editor and policy steps. |
| `add_loop` | step | Opens `loop` empty. |
| `edit_loop` | form | `loop`, a select of the room's private loops, which opens `loop` prefilled. |
| `loop` | form | `name`, `valves`, `shared_valves` (only when Plant-owned valves exist), `pump`, `valve_opening_time_seconds`, `configure_valve_feedback`, section `cooling`, and `remove_loop` when editing. |
| `valve_details` | form | Once per private valve of the loop: `readiness_entity_id`, `position_feedback_entity`, `position_feedback_max_age_seconds`. |

Rules:

- Every save persists through `async_persist_entry_data`, then creates the subentry or ends with `reconfigure_successful`.
- Within a room, a valve's identity is its entity ID: a retained entity keeps its valve id and details, a new entity creates a valve, and a dropped entity removes its private valve unless another loop of the room still uses it.
- Retained loops keep their circuit and route ids.
- `valve_opening_time_seconds` applies to every private valve of the loop and is prefilled from the first one.
- Switching a room to an external thermostat drops its Hydronicus thermostat settings, and switching back starts from defaults.

Errors, reusing the current zone and circuit keys where they exist: `name_required`, `temperature_sensors_required`, `valves_required`, `actuator_entity_in_use`, `own_entity`, `thermostat_loop`, `sensor_metadata_required`, `designated_reference_count`, `temperature_required_for_cooling`, `humidity_required_for_cooling`, `cooling_reference_required`, `cooling_requires_zone_observations`, `confirm_required`, `dry_run_shutdown_in_progress`.
New errors: `delivery_required` (neither `valves` nor `shared_loops`), `pump_required`, and `invalid_room` (placeholder `error`).
Aborts: `no_pumps`, `already_configured`, `reconfigure_successful`.

#### Plant settings

Parent reconfigure flow in module `flows/plant.py`, built by W4.

| Step | Kind | Fields or options |
| --- | --- | --- |
| `reconfigure` | menu | `dry_run`, `add_pump`, `edit_pump`, `export_plant`, `edit_plant`. |
| `dry_run`, `dry_run_confirmation` | form | The current Dry run field and confirmation. |
| `add_pump` | step | Opens `pump` empty. |
| `edit_pump` | form | `pump`, a select of Plant pumps, which opens `pump` prefilled. |
| `pump` | form | `name`, `entity_id`, `overrun_seconds`, section `feedback` with the stored pump feedback fields, and `remove_pump` when editing. |
| `export_plant` | abort | Reason `plant_exported`, with placeholder `document` holding the YAML in a fenced block. |
| `edit_plant` | form | `document`, an object selector prefilled with the current export. |
| `edit_plant_review` | form | `confirm`, with placeholders `changes`, `logic`, `warnings`. |

Errors: `name_required`, `actuator_entity_in_use`, `own_entity`, `equipment_in_use` (placeholder `users`), `invalid_document` (placeholders `path` and `error`), `document_own_entity` (placeholders `path` and `entity_id`), `plant_id_mismatch`, `confirm_required`, and the current Dry run errors.
Aborts: `reconfigure_successful`, `plant_exported`, `no_changes`.

An edited plant file is applied in one synchronous block, with no `await` between the parent data update and the subentry adds, removes, and retitles, so the reload listener sees one consistent graph.

#### Guided setup and import

Config flow for a new Plant in module `flows/setup.py`, built by W5.

| Step | Kind | Fields or options | Next |
| --- | --- | --- | --- |
| `user` | menu | `guided`, `import_plant` | The chosen step. |
| `guided` | form | `name`, `pump_entity`, section `pump_options` with `overrun_seconds` | `room` |
| `room` | form | Room basics without `pump` and `shared_loops`, plus `add_another` | `room` again, or `review` |
| `review` | form | `confirm` only with a blocking warning; placeholders `rooms`, `logic`, `warnings` | Create the entry with its room subentries. |
| `import_plant` | form | `document`, an object selector | `import_review` |
| `import_review` | form | `confirm` only with a blocking warning; placeholders `name`, `rooms`, `logic`, `warnings` | Create the entry with its room and source subentries. |

Errors: `name_required`, `own_entity`, `invalid_document` (placeholders `path` and `error`), `document_own_entity` (placeholders `path` and `entity_id`), `confirm_required`, and the room basics errors.
Aborts: `already_configured`.
The current initial flow's `duplicate_actuator_entity` goes away with its steps, because a pump entity reused as a valve now surfaces as `actuator_entity_in_use` on the room's `valves`.

#### Action, runtime ownership, and Repairs

- **Action** `hydronicus.export_plant` (W4, modules `services.py` and `services.yaml`): field `config_entry_id` with a config entry selector for this integration, registered with `async_register_admin_service` and `SupportsResponse.ONLY`, returning `{"document": <plant file>}`, and raising `ServiceValidationError` with key `plant_not_found`.
- **Runtime ownership** (W1): `HydronicRuntime.object_subentry_ids` replaces the four per-type maps and backs `subentry_id_for(object_id) -> str | None`; platforms attach zone, valve, and source entities to `subentry_id_for` their object, and pump entities to the parent.
- **Repairs**: a binding on a room-owned object opens that room's reconfigure flow (W1); a pump binding opens Plant settings through `next_flow` with the config flow type (W4); a binding on a shared valve, shared loop, Plant-owned source, or the source selector is not fixable, and its text tells the user to edit the plant file (W4).

## Waves

Every wave ends green: after integrating its commits, the lead runs `make verify`.

### Wave 0 - keystone (lead)

Start only after the Home Assistant 2026.9 modernization pull request has merged into `main`; otherwise stop and report.

1. Check for drift since `b4b22fe`: every module, class, function, and test this plan names still exists on `main` (`git grep`), and a throwaway flow test still reproduces the [Evidence](#evidence) scenario.
   Update this plan before continuing when a difference changes a contract, and report it.
2. Create the branch `setup-redesign` from `main`, and commit this plan as `docs: add setup redesign plan`.
3. Move the flow code without changing behaviour, committed as `refactor: split config flows into a flows package`:
   - `flows/common.py`: every module-level helper used by more than one handler, including the own-entity guard (`_OwnEntityPickerMixin`, `_own_entity_errors`, `_ENTITY_FIELDS`, and their helpers), the typed-error helpers (`_effective_topology_error`, `_circuit_cooling_error`), selector and section builders, `_with_submitted_values`, warning review helpers, sensor metadata helpers, and the persistence helper;
   - `flows/legacy.py`: the zone, circuit, and actuator subentry handlers, with the helpers only they use;
   - `flows/source.py`: the source subentry handler, with the helpers only it uses;
   - `flows/setup.py`: a `SetupSteps` mixin holding the current initial steps;
   - `flows/plant.py`: a `PlantSettingsSteps` mixin holding the current reconfigure and Dry run confirmation steps;
   - `config_flow.py`: `HydronicClimateConfigFlow(OwnEntityPickerMixin, SetupSteps, PlantSettingsSteps, config_entries.ConfigFlow, domain=DOMAIN)`, which keeps the guard first in the method resolution order as today, and `async_get_supported_subentry_types`;
   - `migration.py`: `migration_plan`, `MigrationPlan`, and `SubentryMigration`, moved from `entry_configuration.py`;
   - `tests/test_config_flow_import.py`: scans `config_flow.py` and every `flows/*.py`.
   A helper that becomes shared across modules drops its leading underscore.
   This step is done when `git diff -M --stat` shows only moves, import updates, and dropped underscores, and `make verify` passes.
4. Build the keystone core, committed as `feat: add plant ownership and allow unused plant equipment`:
   - `tests/core/strategies.py`: a Hypothesis strategy for valid configurations that vary the sharing of valves, pumps, and circuits and route several zones;
   - K1 in `core/ownership.py`, with `tests/core/test_ownership.py` covering every rule and property tests that derived ownership validates and that `without_room` for every zone yields a configuration that validates and compiles;
   - K2 in `core/topology.py`, turning the existing orphan expectations red first, with a property test in `tests/core/test_properties.py` that unused equipment is never requested;
   - `SUBENTRY_TYPE_ROOM = "room"` and `CONF_ROOM_OBJECTS = "room_objects"` in `const.py`, without a version bump.
   This step is done when each property test runs at least 200 examples and `make verify` passes.

### Wave 1 - two parallel workstreams

Each agent works in its own git worktree based on the Wave 0 commit and runs `make bootstrap` first.
Integrate W1, then W2.

#### W1 Storage version 3 and migration

Contracts: K1, K2, K3, K4, and the flow conventions, runtime ownership, and Repairs parts of K6.
Commit: `feat: store plants as rooms and migrate to config entry version 3`.

Owned files:

- `entry_configuration.py`, `migration.py`, `__init__.py`, `const.py`, `diagnostics.py`, `repairs.py`, `config_flow.py`;
- `runtime.py` (ownership fields and `from_entry` only), and the entity-to-subentry assignment in `binary_sensor.py`, `sensor.py`, and `climate.py`;
- `flows/common.py`, `flows/setup.py`, `flows/legacy.py`, and a new stub `flows/room.py`;
- `strings.json` keys `config_subentries.zone`, `config_subentries.circuit`, `config_subentries.actuator`, `config_subentries.room`, and `issues`;
- tests `test_entry_configuration.py`, `test_migration.py`, `test_init.py`, `test_entities.py`, `test_repairs.py`, `test_diagnostics.py`, `test_zone_subentry.py`, `test_circuit_subentry.py`, `test_actuator_subentry.py`, the legacy subentry cases of `test_translations.py`, and new `tests/integration/plant_fixtures.py` and `tests/integration/test_room_ownership.py`.

Tasks, in order:

1. Implement K3 readers, room handle validation, and removal reconciliation through `without_room`, implement K4 in full, and include `room_objects` in `runtime_configuration_fingerprint`.
2. Implement the K3 migration with `async_move_object_registrations`, bump `CONFIG_ENTRY_VERSION` to 3 and `CONFIG_ENTRY_MINOR_VERSION` to 0, and keep the legacy subentry type names only in `migration.py`.
3. Replace the per-type runtime maps with `object_subentry_ids`, and assign platform entities as K6 describes.
4. Make a binding on a room-owned object open its room's reconfigure flow.
5. Keep the current initial steps in `flows/setup.py`, but create the entry as version 3 data with one room subentry, a room-owned loop and valve, and a Plant pump; W5 replaces these steps.
6. Register `room` with a stub handler in `flows/room.py` whose `user` and `reconfigure` steps abort `room_flow_pending`, which W3 replaces.
7. Port the behaviours listed below into `test_room_ownership.py`, then delete `flows/legacy.py`, the legacy subentry strings, and the three legacy flow test files.
8. Add builders to `tests/integration/plant_fixtures.py` for version 3 entries with room and source subentries, for W3, W4, and W5 to use.
9. Show each object's owner (room title or Plant) in diagnostics without exposing anything redacted today.

Behaviours to port into room terms:

- deleting a room while the Plant is active reaches Dry run before the graph changes (from `test_active_valve_deletion_reaches_dry_run_before_graph_removal`);
- a failed shutdown retains the parent graph (from `test_failed_shutdown_retains_parent_graph_after_subentry_removal`);
- deleting a room removes its entities and devices and leaves a Plant that loads;
- reload reconstructs rooms and their entity ownership.

The flow-guard tests in the legacy files (own entities, empty required selections, and typed-error field mapping) stay out of this port, because W3 re-creates them for rooms.

W1 is done when:

- every task is green and `make verify` passes;
- a migration test builds the cross-wired manifold from [Evidence](#evidence) as version 2 data with zone, circuit, actuator, and source subentries, customizes one entity's name and entity ID, migrates, and finds the same entity IDs, customizations, device identifiers, and graph;
- a migration interrupted after each of K3 migration steps 2 to 6 resumes to the same final state;
- a version 1.1 entry reaches version 3.0 in one setup;
- `tests/integration/test_public_beta.py` passes unchanged, which proves new Plants keep their entity IDs;
- the names `zone_subentry_ids`, `actuator_subentry_ids`, `circuit_subentry_ids`, `SUBENTRY_TYPE_ZONE`, `SUBENTRY_TYPE_CIRCUIT`, and `SUBENTRY_TYPE_ACTUATOR` appear nowhere in `custom_components/` except `migration.py`.

#### W2 Plant file core

Contracts: K1, K3, K5.
Commit: `feat: add the plant file format`.
Owned files: `core/plant_document.py`, `tests/core/test_plant_document.py`, and `tests/fixtures/plant_files/`.

Tasks:

1. Implement K5 import and export.
2. Add fixtures for a single room, a three-room manifold with one pump, two pumps, a shared loop with a shared valve used by two rooms, a room with two private loops sharing a private valve, an external thermostat, a cooling loop with humidity sensors, sources with a source selector, and every shorthand form.
3. Add one negative fixture per error class: unknown key, invalid slug, duplicate slug, unknown reference, another room's private valve, a Plant loop using a private valve, a compile failure, a missing format version, and each typed core error that K5 maps to a path.
4. Add property tests over `tests/core/strategies.py` with `derive_ownership`: export then import reproduces topology and ownership, and import then export of a canonical file is the identity.
   `stored_plants()` draws config entry data with stored topology records, `plant_configurations()` draws the decoded configurations, and names repeat and carry characters a slug must replace.

W2 is done when every K5 rule is pinned by a test, every negative fixture asserts its error path, each property test runs at least 200 examples, and `make verify` passes with core coverage of at least 90 percent.

### Wave 2 - two parallel workstreams

Each agent works in its own worktree based on the integrated Wave 1 commit.
Integrate W3, then W4.

#### W3 Rooms

Contracts: K1, K4, and the flow conventions, room basics, and room subentry flow parts of K6.
Commit: `feat: add room subentries with private loops`.
Owned files: `flows/room.py`, `flows/room_form.py`, `strings.json` keys `config_subentries.room` and `selector.temperature_aggregation`, and `tests/integration/test_room_flow.py`.

Tasks:

1. Implement room basics in `flows/room_form.py` with the exact K6 signatures.
2. Replace the stub in `flows/room.py` with the K6 room subentry flow.

W3 is done when:

- the [Evidence](#evidence) scenario, built through room flows on a one-pump Plant, yields Living room to Living room loop to Living room loop valve and Bedroom to Bedroom loop to Bedroom loop valve, with no warning other than the shared pump;
- deleting each room in turn leaves a Plant that loads, with only `unused_equipment` warnings once no room uses the pump;
- reconfigure tests prove that zone, circuit, route, and valve ids survive every step, including valve identity by entity ID;
- tests prove every K6 flow convention in the room flows: own-entity hiding and rejection, empty required selections, and each typed-error mapping a room or loop form can hit;
- a test reaches every error and abort key, and the translation tests pass;
- `make verify` passes.

#### W4 Plant settings and plant file editing

Contracts: K4, K5, and the flow conventions, Plant settings, action, and Repairs parts of K6.
Commit: `feat: add plant settings, plant file export, and plant file editing`.

Owned files:

- `flows/plant.py`, new `services.py` and `services.yaml`, the `services` entry of `icons.json`, the action registration in `__init__.py`, and `repairs.py`;
- `strings.json` keys for the Plant settings steps, errors, and aborts in K6, `services`, `exceptions.plant_not_found`, and the `issues` text for non-fixable Plant equipment;
- tests `tests/integration/test_plant_settings.py`, `tests/integration/test_export_action.py`, and the pump cases in `test_repairs.py`.

Tasks:

1. Implement the K6 Plant settings flow, including the export dialog and plant file editing with `subentry_sync` and `async_move_object_registrations`.
2. Implement the `hydronicus.export_plant` action.
3. Implement the pump and non-fixable Repairs rules.

W4 is done when:

- pumps can be added, edited, and removed, and removing a pump in use shows `equipment_in_use` naming its loops;
- the pump form keeps the K6 flow conventions, and a plant file that binds a Hydronicus entity shows `document_own_entity` with its path;
- the export dialog and the action return the same document, and importing it rebuilds an identical Plant;
- plant file edit tests add a room, remove a room, rename a room, move a private loop to the Plant, and change a valve entity, and each asserts that entities and devices end under the right owner with stable entity IDs;
- an unchanged plant file aborts `no_changes` without touching Dry run or output authorization;
- a plant file carrying another Plant's id shows `plant_id_mismatch`;
- the action refuses a non-admin user;
- a pump binding repair opens Plant settings;
- `make verify` passes.

### Wave 3 - W5 Guided setup and import

Contracts: K4, K5, and the flow conventions and guided setup and import parts of K6.
Commit: `feat: replace the initial flow with guided setup and plant file import`.
Owned files: `flows/setup.py`, the `strings.json` keys for the guided setup steps, errors, and aborts in K6, the removal of the old initial step keys and `selector.thermostat_kind`, `tests/integration/test_config_flow.py`, and `tests/integration/test_public_beta.py`.

W5 is done when:

- guided setup creates a three-room manifold in exactly six screens, with three room subentries, correct routes, and Dry run on;
- importing a plant file creates the same entry data, room subentries, and source subentries as importing its own export;
- a file whose id matches an existing Plant aborts `already_configured`, every W2 negative fixture shows `invalid_document` with its path, and a file that binds a Hydronicus entity shows `document_own_entity` with its path;
- the guard tests in the current `test_config_flow.py` (empty sensor selection, own entities, and typed cooling and reference errors) are ported to the new steps and pass;
- `test_public_beta.py` goes through guided setup and keeps its pinned entity IDs;
- `make verify` passes.

### Wave 4 - W6 Documentation and trial kit

Contracts: K5 and K6.
Commit: `docs: document rooms, guided setup, and the plant file`.

Owned files:

- `README.md`, `CONTEXT.md`, `docs/configuration.md`, `docs/how-it-works.md`, `docs/troubleshooting.md`, `docs/upgrade-and-rollback.md`, the canonical configuration and migration section of `docs/development.md`, and a new `docs/plant-file.md`;
- `docs/examples/`;
- `tests/integration/test_public_beta.py`, and new `tests/integration/test_trial_kit.py` and `tests/test_docs_examples.py`.

Tasks:

1. Build the trial kit: `docs/examples/trial/package.yaml` (input numbers, input booleans, and template sensors and switches for two rooms and one pump) and `docs/examples/trial/plant.yaml` bound to it, replacing `docs/examples/simulated-entities.yaml`.
2. In `test_trial_kit.py`, set up the package's integrations, import `plant.yaml` through the config flow, drive heating demand, and assert Bedroom to Bedroom loop to Bedroom loop valve with zero actuator service calls.
3. Rewrite the README's "First simulated Plant" around the trial kit and guided setup, keeping every phrase `scripts/public_beta_smoke.py` pins, and move `test_public_beta.py` to the documented trial path.
4. Write `docs/plant-file.md` as the user reference for K5, and make `tests/test_docs_examples.py` parse and import every YAML example in it.
5. Update the remaining owned documents, including in the upgrade guide that the version 3 migration is one way and rolling back means restoring the Home Assistant backup taken before the upgrade.
6. Add Room, Loop, Plant equipment, Plant file, and deletion-closed ownership to the `CONTEXT.md` glossary.

W6 is done when every UI label quoted in the documents matches `strings.json` exactly, every plant file example imports, `make public-beta-check` passes, and `make verify` passes.

### Wave 5 - end to end (lead, one user checkpoint)

Setup:

1. Create a disposable configuration directory in the session scratchpad, outside the repository.
2. Write `configuration.yaml` with `default_config:`, the trial package, and extra synthetic entities for a third room and a second pump, each actuator backed by an `input_boolean` so any service call shows in history.
3. Symlink `custom_components/hydronicus` from a checkout of `main` for phase A.
4. Start `.venv/bin/hass -c <dir>` on a free port, and open it in the in-app browser.
5. Ask the user to complete onboarding and log in, and wait for their confirmation; agents never create accounts or type passwords.
6. Phase A on `main`: build the cross-wired manifold from [Evidence](#evidence) with the old flows, rename one entity and change one entity ID in the UI, then stop Home Assistant.
7. Phase B: point the symlink at the `setup-redesign` checkout and start Home Assistant again.

Checklist, with each item recorded as pass or fail with evidence:

1. The phase A Plant migrated: rooms appear as subentries with their devices, entity IDs and customizations are intact, and the Plant is in Dry run.
2. Guided setup builds a three-room manifold on the trial entities in six screens, and the review shows the right routes.
3. The room reconfigure menu works end to end: edit a room, add a second private loop, change valve feedback, and delete a room.
4. Plant settings add a second pump, a room loop moves to it, and removing the pump in use is refused with the loop named.
5. The export dialog shows the plant file, and the action in Developer tools returns the same document.
6. Editing the plant file changes a valve entity and adds a shared loop used by two rooms; the review lists the changes, and entity IDs stay the same after applying.
7. Deleting the Plant and importing its exported file brings back identical entity IDs.
8. The object selector renders a YAML editor, a YAML syntax error is reported clearly, and an invalid document shows its path.
9. Removing a bound room valve entity raises a repair that opens the room's reconfigure flow, and a pump binding repair opens Plant settings.
10. No menu, form, error, abort, or dialog shows a raw translation key, and every form reads well at mobile width and in dark mode.
11. The history of every synthetic `input_boolean` shows no change during the run.
12. Home Assistant logs show no Hydronicus errors or unexpected warnings.

Save screenshots and log excerpts in the scratchpad.
A failed item goes to a fresh fix agent for the owning workstream, with the failing evidence, and is retested after integration.
Wave 5 is done when every item passes with evidence, and Home Assistant is stopped with its configuration directory kept for the user.

### Wave 6 - review (lead)

1. Run the `code-review` skill against `main`, with this plan as the spec.
2. In parallel, run one adversarial reviewer agent that tries to break deletion-closed ownership through any flow or plant file, checks Dry run and output authorization on every new write path, and checks migration idempotency, registry safety, round-trip losslessness, and how unused equipment executes.
3. Fix every confirmed finding red then green.

Wave 6 is done when every confirmed finding is fixed and `make verify` passes.

### Wave 7 - ship (lead)

1. Check that `README.md` and every document under `docs/` agree with the shipped behaviour.
2. Push the branch and open a pull request against `main` whose body covers the evidence and outcome, the screen counts before and after, the Wave 5 results table, the compatibility notes (one-way migration, replaced subentry types, stable entity IDs, Dry run after migration), and the out-of-scope follow-ups.
3. Watch the `CI` and `Validate` checks, and fix failures.

Wave 7 is done when the pull request is open and every check is green.

## Subagent brief

The lead fills in the angle-bracket fields and sends one brief per workstream.

```text
You are implementing workstream <ID> <name> of the Hydronicus setup redesign.
Work in <worktree path> on branch <branch>, based on commit <sha>, and run `make bootstrap` first.
Read docs/setup-redesign-plan.md: Evidence, Terminology, Decisions, Invariants, Working rules, contracts <list>, and workstream <ID>.
Also read CONTEXT.md and the "Architecture boundaries" section of docs/development.md.
Change only your owned files, and send anything else back as a contract request.
Work red then green, and collect evidence with the hydronicus-verify skill.
You are done when every done criterion of <ID> holds and `make verify` passes in your worktree.
Commit once, with the commit message named in <ID>.
Report, in this order: each done criterion with its evidence (test names, commands, results); contract requests; deviations from contracts and why; lint, test, or flakiness problems you saw, related or not; anything unverified.
```

Lead duties:

- Dispatch the workstreams of one wave in a single message with the Agent tool and `isolation: "worktree"`.
- Integrate each commit in the stated order, resolve `strings.json` conflicts key by key, copy it to `translations/en.json`, and run `make verify` after each integration.
- Resolve contract requests during integration, or return them to the requesting agent with SendMessage.
- Continue an agent with SendMessage to fix its own work, and start a fresh agent for an end-to-end failure.

## Out of scope

Record these as pull request follow-ups rather than implementing them.

- Plants managed from `configuration.yaml`.
- UI editors for shared loops, shared valves, Plant-owned sources, and the source selector.
- Renaming entity and device names from Zone and Circuit to Room and Loop, which would change newly generated entity IDs.
- Suggesting rooms and entities from Home Assistant areas.
- Simulated equipment created by Hydronicus itself.
- Lovelace card changes.
- Version bumps and release notes, which belong to the release step.
