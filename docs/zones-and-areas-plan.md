# Zones and areas plan

This plan replaces the Room concept with a Zone that covers Home Assistant areas.
It is the single source of truth for decisions, contracts, invariants, and phases.
The lead runs the phases in order and may dispatch a phase to a subagent with the [subagent brief](#subagent-brief).

## Evidence

Investigated on 2026-09-25 against Home Assistant 2026.9 and Hydronicus v0.1.0 (`f387348`).

- Home Assistant areas carry a `temperature_entity_id` and a `humidity_entity_id` since area registry version 1.8 (`homeassistant/helpers/area_registry.py`).
- Home Assistant only checks that these are sensors of the right device class, so an area can name any temperature sensor, including one that Hydronicus itself provides.
- The maintainer's home has one area per physical room, most with both sensors, and three heating zones that each cover several areas.
- Other installations range from one zone for the whole home to one zone per room.
- The UI calls one thermostat's space a Room, so a zone that covers a kitchen, a dining room, and a hall reads as a Room that contains rooms.
- Core code, the Lovelace card, and the WebSocket snapshot already say Zone.
- The maintainer decided on 2026-09-25 that no backward compatibility is required at this stage, so stored names, the plant file, and the card change without aliases or migration.
- `DeviceInfo.suggested_area` still assigns an area to a newly created device.
- Reload and unload are command-free lifecycle boundaries, and `_async_reload_entry` skips a reload when `runtime_configuration_fingerprint` is unchanged.

## Outcome

- The UI, the documentation, the plant file, and the card speak of Zones, and a zone covers zero or more Home Assistant areas.
- A zone follows the temperature and humidity sensors that its areas name in Home Assistant, so a sensor is chosen once, in the area settings.
- Guided setup asks how the home is zoned and fills in zones from areas.
- The zone card shows each area's reading when a zone covers two or more areas.
- Entries from earlier development versions are refused with a clear message and set up again.

## Terminology

| UI term | Core term | Meaning |
| --- | --- | --- |
| Plant | Plant | One config entry and its complete graph. |
| Zone | Zone | The space one thermostat controls, with its areas, sensors, Delivery Routes, and private loops and valves; one `zone` subentry. |
| Area | none | A Home Assistant area, usually one physical room, that a zone covers. |
| Loop | Circuit | A water path through one or more valves and one pump. |
| Plant equipment | Pump, Valve, Circuit, Source, source selector | Owned by the Plant. |

Core code keeps the names Zone and Circuit, and adapter code, stored names, and the card rename Room to Zone.

## Decisions

These are settled; implement them rather than revisiting them.

1. **Zone replaces Room** in every user-facing string, the documentation, the plant file, the card, adapter code, and stored names, including the subentry type `zone` and the key `zone_objects`.
   Loop stays, and the card's remaining Circuit wording becomes Loop.
2. **A zone covers areas.** A zone stores zero or more area IDs, each at most once.
   An area may be covered by several zones, which the review reports as a warning that never needs confirmation.
3. **Area sensors are followed live.** Each covered area contributes the temperature sensor and the humidity sensor that Home Assistant currently names for it.
   Home Assistant defines these as the sensors that represent the area, which is exactly the reading a thermostat needs, and replacing a dead sensor then takes one edit instead of two.
   The resolved entity IDs appear in the Combined temperature attributes and diagnostics, so the input is never hidden.
4. **Explicit sensors stay** for sensors outside areas, such as a floor probe, and for zones without areas.
   When an explicit sensor and an area resolve to the same entity, it counts once, with the explicit sensor's settings and a designated reference if either marks one.
5. **Area settings** are `required` (default `false`), `weight` (default 1), `designated_reference` (default `false`), and `max_age_seconds` (default 1800).
   They apply to the area's temperature sensor.
   An area's humidity sensor is always required, with the area's maximum age, because an unobserved humid room is exactly where a cooled floor condenses.
   An area temperature sensor defaults to optional because one flat battery in a five-area zone must not stop heating the other four.
6. **Resolution never breaks a Plant.** Structural rules, such as a Hydronicus thermostat needing a temperature source and the designated reference count, are checked against the declarations, where an area counts as a source.
   An area that is missing or names no sensor contributes nothing, and a zone left without a usable reading is blocked by the existing fail-closed aggregation and gets a Repair.
7. **Area changes reload the Plant** through the existing coalesced reload, and only when the resolved sensors of a covered area change, because the fingerprint includes the resolution.
8. **Self-feed guard.** An area sensor that Hydronicus provides is ignored and reported as a Repair, because it would feed the Plant back into itself.
9. **Device placement.** A zone that covers exactly one area suggests that area for its device when the device is created.
   A zone that covers several areas leaves its device unassigned, because a device has one area.
10. **Guided setup asks "How is your home zoned?"** with three answers: one zone for the whole home, one zone per area, or group areas into zones.
    Every answer still ends in the zone form, where valves are chosen.
11. **Plant file.** `zones` replaces `rooms` and a zone accepts `areas`, and the format number stays 1 because no earlier file needs to import.
    A covered area that does not exist is a review warning that needs confirmation, like an entity that does not exist yet, so a file can move between instances.
12. **Card names.** `hydronicus-zone-card` with a `zone` option is the card, the Plant card section is `zones`, and the parts are `zone` and `zone-title`, with no aliases.
13. **Config entry version 4.0.** An older entry is not migrated: setup logs that it came from an earlier development version and must be set up again, and the legacy migration code is deleted.
14. **The dew point is out of scope.** The worst-case dew point change runs on its own branch, and this plan neither changes nor depends on the dew point math.

## Invariants

- Dry run issues zero actuator service calls.
- Reload, unload, removal, and Home Assistant stop remain command-free lifecycle boundaries.
- A change to an area, or to an entity an area names, never makes a Plant fail to load.
- Entity unique IDs and device identifiers keep their current scheme, so a Plant set up again from its plant file gets the same entity IDs.
- Round-trip: importing an exported plant file reproduces the Plant exactly.
- `custom_components/hydronicus/core/` stays free of Home Assistant imports, keeps at least 90 percent coverage, and passes mypy.
- `make verify` is the gate.

## Working rules

- A behaviour change starts red: first a test that fails on the old behaviour, then the change that turns it green.
- Read a Home Assistant API in `.venv/lib/python3.14/site-packages/homeassistant/` before relying on it.
- Edit `strings.json`, then copy it to `translations/en.json` byte for byte.
- Prose uses plain dashes, never em dashes, and long Markdown puts each full sentence on its own physical line.
- Commit messages use the repository prefixes (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`) and carry no agent attribution or co-author lines.
- `CHANGELOG.md`, `RELEASE_NOTES.md`, version numbers, and generated files stay untouched, except the built card bundle, which `make` regenerates.
- Fix or explicitly report lint failures, test failures, and flaky tests, even when unrelated.

## Contracts

### K1 Stored zone

A stored zone object gains an optional `areas` list:

```text
areas: [{area_id: str, required?: bool = false, weight?: float = 1.0,
         designated_reference?: bool = false, max_age_seconds?: float = 1800}]
```

- `area_id` values are unique within a zone, and an unknown field is a `StoredTopologyError`.
- `temperature_sensor_metadata` may be empty when `areas` is not empty.
- A Hydronicus thermostat needs a non-empty `temperature_sensor_metadata` or a non-empty `areas`.
- At most one sensor or area sets `designated_reference`, and `designated_reference` aggregation needs exactly one.
- Cooling-enabled loops need, in every zone they serve, a temperature source and a humidity source, where an area counts as both.
- The version is 4.0 from P1, so `areas` needs no version change.

### K2 Core resolution

`core/model.py` gains:

```python
@dataclass(frozen=True, slots=True)
class ZoneArea:
    area_id: str
    required: bool = False
    weight: float = 1.0
    designated_reference: bool = False
    max_age_seconds: float = 1800.0

@dataclass(frozen=True, slots=True)
class AreaSensors:
    temperature_entity_id: str | None = None
    humidity_entity_id: str | None = None
```

- `Zone` gains `areas: tuple[ZoneArea, ...] = ()`, the declarations.
- `TemperatureSensorMetadata` gains `area_id: str | None = None`, set on records that come from an area.
- `plant_configuration_from_entry_data(data, *, area_sensors: Mapping[str, AreaSensors] = MappingProxyType({}))` validates declarations first, then builds each zone's effective `temperature_sensor_metadata` and `humidity_sensor_metadata`: explicit records in stored order, then one record per resolved area in area order, merged by [decision 4](#decisions).
- An area absent from `area_sensors`, or with `None` for a measurement, contributes no record for it.
- The controller is unchanged: it aggregates the effective records exactly as it aggregates explicit ones today.

### K3 Adapter resolution

A new module `custom_components/hydronicus/areas.py` owns every area registry read:

- `resolve_area_sensors(hass, area_ids) -> AreaResolution`, where `AreaResolution` holds the `area_sensors` mapping for K2, the missing area IDs, and the self-provided entity IDs it dropped.
- A self-provided entity is one that `plant_file.first_own_entity` or the existing own-entity check recognises as provided by any Hydronicus Plant.
- The runtime, flows, the plant file review, diagnostics, and repairs call only this module.
- `runtime_configuration_fingerprint(entry)` includes the resolution of the Plant's covered areas.
- `async_setup_entry` subscribes to `EVENT_AREA_REGISTRY_UPDATED` and calls `_async_reload_entry` when the event's area is covered, which reloads only if the fingerprint changed.
- Entity registry renames of an area's sensor reach the Plant through the area registry, which Home Assistant updates; verify this against the installed version and subscribe to entity registry updates as well if it does not.

### K4 Repairs

- `zone_area_missing`: a zone covers an area that no longer exists, fixed in the zone's reconfigure flow.
- `zone_without_temperature_source`: a zone with a Hydronicus thermostat resolves no temperature sensor, so it is blocked; the repair names its areas and links to the zone.
- `zone_area_self_feed`: an area names a sensor Hydronicus provides; the repair names the area and tells the user to choose another sensor in the area settings.
- Each repair clears itself when the resolution no longer shows the problem.

### K5 Plant file

```yaml
hydronicus: 1
name: Home
pumps:
  pump: switch.manifold_pump
zones:
  ground_floor:
    areas:
      - living_room
      - area: kitchen
        weight: 0.5
      - area: dining_room
        designated_reference: true
    temperature_aggregation: designated_reference
    loops:
      ground_floor_loop:
        valves: [switch.ground_floor_valve]
        pump: pump
```

- An item of `areas` is an area ID or a mapping of `area` and the [K1](#k1-stored-zone) settings.
- Export writes an area as its bare ID when every setting is the default.
- Error paths say `zones.<slug>...`, and export slugs use the `zone_` prefix where they used `room_`.
- The review warns, needing confirmation, for an area that does not exist and for an area without a humidity sensor in a zone a cooling loop serves; it warns, without confirmation, for an area without a temperature sensor and for an area covered by several zones.

### K6 Flows

- The zone form asks, in order: **Name**, **Areas**, **Extra temperature sensors**, **Thermostat**, **Valves**, **Pump**, **Shared loops**, and the collapsed **Cooling** section with **Extra humidity sensors**.
- **Name** may be left empty when areas are chosen: one area gives the area's name, areas on one floor give the floor's name, and otherwise the form asks for a name.
- A Hydronicus thermostat without a resolved temperature sensor stops the form with `no_temperature_source` on **Areas**.
- The zone's options menu keeps its steps, renamed from room to zone, and **Sensors** gains **Areas**; **Edit sensor metadata** opens one form per explicit sensor and then one per area.
- Guided setup, after the Plant form, shows a menu: `zoning_whole_home`, `zoning_per_area`, `zoning_grouped`.
  - Whole home opens one zone form named `Home` with every area that has a temperature sensor.
  - Per area first asks which areas, defaulting to every area with a temperature sensor, then opens one prefilled zone form per area with its progress in the description.
  - Grouped opens the zone form with **Add another zone**, as guided setup does today.
- `topology_device_info` passes `suggested_area` for a zone that covers exactly one existing area.

### K7 Snapshot and card

- `ZoneSnapshot` gains `areas: {id, name, temperature, humidity, temperature_entity_id, humidity_entity_id}[]` in the zone's area order, with `null` where an area names no sensor or its reading is unusable.
- The zone card shows one compact line per area when a zone covers two or more areas.
- The card editor offers zones and writes `zone`.
- New `--hydronicus-*` tokens or parts are added to `docs/lovelace.md`, and the report lists them so the ha-config adapter can map them.

## Phases

### P1 Rename

Rename Room to Zone across `strings.json`, flows, adapter code, stored names, docs, tests, README, CONTEXT.md, the plant file, the device model name, and the card, and move the config entry to version 4.0 without migration.
Commit: `refactor: call the thermostat unit a Zone`.
Done when no user-facing text or stored name calls the thermostat unit a Room, an older entry is refused with a clear log message, and `make verify` passes.

### P2 Areas in the model

K1, K2, K3, K4, and the K5 syntax and review warnings, with tests for resolution, merging, self-feed, live area changes, and reload coalescing.
Commit: `feat: zones follow the sensors of their Home Assistant areas`.

### P3 Areas in the flows

K6, with flow tests for every guided setup answer, the zone form, the options steps, and device placement.
Commit: `feat: set up zones from Home Assistant areas`.

### P4 Areas on the card

K7, with frontend tests.
Commit: `feat: show each area of a zone on the zone card`.

### P5 Documentation and end to end

Update `docs/configuration.md`, `docs/plant-file.md`, `docs/how-it-works.md`, `docs/lovelace.md`, `docs/troubleshooting.md`, `docs/upgrade-and-rollback.md`, and the trial kit.
Run a live Home Assistant with areas like the maintainer's home, set up each zoning answer, change an area's sensor, and remove one, and check the UI closely.
Commit: `docs: describe zones and areas`.

## Subagent brief

```text
You are implementing phase <ID> of the Hydronicus zones and areas plan.
Work in <path> on branch zones-and-areas, and run `make bootstrap` first if the environment is missing.
Read docs/zones-and-areas-plan.md: Evidence, Terminology, Decisions, Invariants, Working rules, the contracts your phase names, and your phase.
Also read CONTEXT.md and the "Architecture boundaries" section of docs/development.md.
Work red then green.
You are done when your phase's done criteria hold and `make verify` passes.
Commit once, with the commit message your phase names.
Report: each done criterion with its evidence; deviations from the contracts and why; lint, test, or flakiness problems you saw, related or not; anything unverified.
```

## Out of scope

- Following an HA floor's membership live; the floor is only a naming default and a setup shortcut.
- Pairing each area's temperature and humidity for a per-area dew point.
- Placing loops in areas.
- Version bumps and release notes, which belong to the release step.
