# Feature roadmap research

This is a research proposal, not a plan of record.
It surveys what Hydronicus does in 0.8.0, what comparable Home Assistant projects and commercial hydronic controllers do, and what users struggle with, and turns that into a ranked list of candidate features for the owner to pick from.
Nothing here changes behaviour, and every design sketch must still pass the invariants in [development](../development.md#invariants) and the `make verify` gate.

How to read the sources:

- Links marked (fetched) were opened and read.
- Links marked (issue) are GitHub issues whose title and opening text were read through the GitHub API.
- Links marked (search) were seen in web search results only; the page exists but its details were not checked, because `community.home-assistant.io`, `assets.danfoss.com`, `assets.new.siemens.com`, and Reddit were not reachable from this research session.
- Parameter values from manuals can differ between firmware versions, so check the exact model before using one as a default.

## Executive summary

Before any new feature, fix the robustness gaps in [Fix first](#fix-first): together they decide whether a house stays warm when one sensor dies.
The most serious is that a stale outdoor sensor blocks every heating request, frost protection included, when the outdoor heating curve is configured ([F3](#f3-a-lost-outdoor-sensor-blocks-all-heating-including-frost-protection)).
The two xfail bugs from the characterization PRs are small fixes and belong in the same release ([F1](#f1-frost-protection-forgets-its-latch-after-a-dropout-xfail), [F2](#f2-hysteresis-boundaries-move-with-float-rounding-xfail)).

The top 5 features, ranked by value against effort and risk:

1. **Complete the heating curve** (M, low to medium risk).
   Add a warm weather shutdown (heating limit), outdoor damping, a user offset number, optional room influence, and an outdoor fallback value.
   Every commercial controller surveyed has these, they cut shoulder-season short cycling on a heat pump, and they extend the existing pure `core/supply.py` seam.
2. **Plant-wide holiday and away mode** (S, low risk).
   One switch or action sets every digital thermostat to an away level until a return time, and recovers in time for the return using the existing early start.
   Users report that presence, away, and frost precedence is the most confusing part of blueprint heating setups.
3. **Automatic heat and cool changeover** (M, medium risk).
   An `auto` option on the **Mode** select, driven by a damped outdoor temperature with a dead band and the existing mode dwell.
   Today it is an automation the owner must write, and getting it wrong runs cooling in spring mornings or heating in a heatwave night.
4. **A bundled Plant card** (M to L, no control risk).
   Hydronicus already computes reasons, holds, and proposals that no stock card shows; the earlier card was removed in the 0.2 redesign ([#41](https://github.com/brumi1024/ha-hydronicus/pull/41)) and its specification is still in [#32](https://github.com/brumi1024/ha-hydronicus/issues/32).
5. **Scheduled DHW: anti-legionella cycle and a DHW schedule** (M, medium risk).
   Hydronicus already owns the DHW switch and setpoint and can boost them, but cannot run the weekly or fortnightly pasteurisation that heat pump controllers and HSE guidance describe, and cannot detect that one failed.

The next tier is floor surface limits in heating, an actuation budget for valves, and price or PV-aware preheating through a bounded comfort shift; see the [ranked list](#ranked-list).

[Questions for the owner](#questions-for-the-owner) lists the assumptions this ranking depends on; the answers can move items up or down.

## Implementation status

The owner chose to implement the top 5 and F1 to F6, with item 4 limited to the data a card needs and no bundled card.
Each landed as its own commit on this branch:

- F1 and F2, the xfail bugs: frost protection keeps its latch through a dropout, and hysteresis boundaries compare with a float tolerance.
- F5: a source found running after a lost store is held for its minimum on time.
- Item 1 with F3: the heating curve's `offset` and **Heating curve offset** number, `outdoor_damping`, `outdoor_fallback`, `room_influence`, `heating_limit`, a frost path that never waits for an outdoor sensor, and the `outdoor_sensor_unusable` Repair.
  The Plant form now keeps the supply keys it does not show, which it dropped before, `modes` and `step` included.
- F4: an opt-in, heating-only `sensor_fallback` per zone.
- F6: the **Heartbeat** sensor and a relay watchdog automation example.
- Item 2: the **Away** switch, the `set_away` and `end_away` actions, the Plant's `away` targets, and an early return before the return time.
- Item 3: the **Mode** select's `auto` option from a Plant `changeover`.
- Item 5: a DHW `schedule` with block targets, and a `disinfect` cycle against legionella with the **Last disinfection** sensor and the `disinfect_failed` Repair.
- Item 4: the versioned `hydronicus/plant_view` and `hydronicus/plant_view/subscribe` websocket commands.

These answers to the [questions](#questions-for-the-owner) are settled: the outdoor fallback is opt-in, and frost protection heats regardless.
The design sketches below are kept as written; the plant file reference and how it works describe what shipped.

## Hydronicus today

### What it does

The facts below come from the [README](../../README.md), [how it works](../how-it-works.md), the [plant file reference](../plant-file.md), and the release notes in [releases](../releases).

- Topology: one Plant with at most one source, switched or source-driven pumps, zones with their own loops, and plant loops such as a towel dryer or a shared hall.
- Safe order: valves open, then after their opening time or readiness sensor the pump starts, then the source is requested; everything stops in reverse with pump overrun and source post-run.
- Minimum flow: a pump with `min_flow: path` never runs without an open loop, and a source-driven pump keeps a min-flow loop open.
- Verified commands: only the entity state confirms a command, with retries, backoff, and a Repair after three attempts.
- Arming and Dry run: nothing is commanded until each output is armed and **Control equipment** is on.
- Demand: digital thermostats with hysteresis and 10 minute minimum on and off times, or an external climate entity read through `hvac_action`.
- Comfort: separate heating and cooling targets and presets, a `schedule` helper with block levels, setbacks, bounded early start, and optional recovery learning with weather forecasts.
- Source cycling: minimum on and off times from observed transitions, `max_starts_per_hour`, `start_threshold` with loop weights, heat sink loops, `hold_after_demand`, and the no-load guard.
- Source integration: a request switch, a mode select, mode switches, a supply setpoint number, health, handover, and inhibit sensors, a write interval for slow bridges, and a compressor sensor for cycle statistics.
- Supply control: a fixed target or a two-point linear outdoor curve, clamped, with a cooling target raised above the worst dew point.
- Cooling: a condensation guard per loop from a supply or surface reference, worst-case dew point, condensation switches, surface minimum, and humidity limit.
- Mode changes: heat and cool never overlap, with the old mode stopped and a dwell, an hour by default.
- Domestic hot water: an owned DHW switch and setpoint with hard limits, adoption of external changes, and a bounded boost action.
- Protection: frost protection per zone at 5 °C, weekly exercise of idle pumps and valves, window sensors and window detection, and a response check that reports a zone that does not warm.
- Diagnostics: a Status sensor with reasons, holds, proposals, sensor health and operation basis, duty cycle and runtime sensors, Repairs, and downloadable diagnostics.

### Configuration surface

- Guided setup and reconfigure flows in `flows/`, a zone subentry per zone, and Plant settings.
- The plant file, format 2, which is also the storage schema and the only place for advanced keys such as `no_load`, `write_interval`, `dhw`, `window_detection`, and `response_check`.
- Runtime entities: the **Mode** select, **Control equipment** switch, a climate entity per digital thermostat, setback numbers, DHW switch and target, the **Reset recovery learning** button, and the `export_plant`, `boost_dhw`, and `end_dhw_boost` actions.

### Documented limitations

These are listed in [how it works](../how-it-works.md#known-limitations), [safety](../safety.md), and the [0.4.0 notes](../releases/v0.4.0.md).

- No automatic heat and cool mode.
- One source per Plant, with no bivalent or hybrid source selection; the source-switching work of the pre-release milestones ([#16](https://github.com/brumi1024/ha-hydronicus/issues/16), [#22](https://github.com/brumi1024/ha-hydronicus/issues/22)) did not survive the redesign.
- No mixing valve control, so radiators and underfloor loops on one source share one supply temperature.
- On and off demand only, with no modulation or duty-cycle balancing of loops.
- No tariff, PV surplus, or SG Ready logic, and no Modbus driver.
- No energy, heat, or COP measurement, by design.
- Heat-only loops are not exercised between the end of cooling and the next heating.
- Frost protection switches the Plant to heat even when every heating loop of the zone is unarmed or unavailable.
- Every protection exists only while Home Assistant runs; the relay-level watchdog in [safety](../safety.md#cooling-while-home-assistant-is-not-running) is left to the owner.

### Recent test PRs

The characterization PRs added tests only, with suspected bugs marked `xfail(strict=True)`:

- [#55](https://github.com/brumi1024/ha-hydronicus/pull/55) pins hysteresis boundaries and found the float boundary bug (three xfails).
- [#56](https://github.com/brumi1024/ha-hydronicus/pull/56) pins sensor dropout mid-cycle and found the frost protection latch bug (one xfail).
- [#57](https://github.com/brumi1024/ha-hydronicus/pull/57) pins conflicting zone modes and mode toggling, with no suspected bug.
- [#58](https://github.com/brumi1024/ha-hydronicus/pull/58) pins a restart with and without the stored State, and raised one open question about the source's minimum on time.

## Fix first

These are not features.
They are gaps in what already ships, ranked by how likely they are to leave a house cold, wet, or short cycling.
Each is small enough to land before the next feature release.

### F1. Frost protection forgets its latch after a dropout (xfail)

- What happens: `frost_demand` returns no demand while the zone has no usable reading, so `step()` drops the zone from `State.frost`; when a reading of 5.5 °C returns, the zone is above the 5 °C start and the latch is gone, so it stops below its 6 °C release.
  See `core/step.py` `frost_protection` and `core/demand.py` `frost_demand`, and `test_frost_protection_resumes_below_its_release_after_a_dropout` in `tests/core/test_sensor_dropout.py`.
- Why it matters: a Zigbee sensor in a cold utility room that drops out for one evaluation turns a 1 K band into a 0 K band, which cycles the source on and off around the frost limit.
- Fix: keep the zone in `State.frost` while it has no reading, as window detection keeps its state through a missing reading, and only clear it on a reading at or above the release.
- Effort: S.
- Risk: low; the change can only extend frost heating, never start it without a reading.
- Test: turn the xfail into a pass, and add a simulator scenario with a frost zone whose sensor flaps.

### F2. Hysteresis boundaries move with float rounding (xfail)

- What happens: `zone_demand` compares `target - temperature` with the delta without a tolerance, so a configured 0.2 K delta at a 0.1 K sensor step behaves as 0.3 K.
  See `core/demand.py` and the three xfails in `tests/core/test_demand_boundaries.py`.
- Fix: compare with a small tolerance, as window detection does with `_WINDOW_TOLERANCE`, or round the difference to a fixed number of decimals before comparing.
- Effort: S.
- Risk: very low; boundaries move by one sensor step at most, towards what the documentation says.
- Test: the three xfails pass, `test_a_configured_delta_of_two_tenths_starts_one_sensor_step_later_today` is updated, and a Hypothesis property checks that a reading exactly at the boundary always acts.

### F3. A lost outdoor sensor blocks all heating, including frost protection

- What happens: with `supply.outdoor_sensor` set, `supply_target` returns no target when the outdoor reading is missing, invalid, or older than `max_age`, and the source then waits with `waiting for the source supply temperature`.
  Frost protection runs the Plant in heat but goes through the same source path, so it circulates water that nobody heats.
  This is documented as intended ("blocks the heating request instead of silently choosing a different target"), but it makes one outdoor sensor a single point of failure for the whole house in the coldest weather, which is when outdoor sensors on batteries fail.
- How others do it: the tekmar 256 assumes 0 °C on an open or shorted outdoor sensor and keeps running, with an error until the sensor is repaired ([manual, search](https://manualshive.com/en/manual/watts/tekmar-256/876853?page=19)).
  Versatile Thermostat treats a stale outdoor sensor as a safety condition with a reduced fixed output rather than a full stop ([advanced features, fetched](https://github.com/jmcollin78/versatile_thermostat/blob/main/documentation/en/feature-advanced.md)).
- Fix: add `supply.outdoor_fallback`, a fixed outdoor temperature such as 0 °C that the curve uses while the reading is unusable, plus a Repair `outdoor_sensor_lost` and a reason `heating curve at fallback 0.0 °C outdoors`.
  Keep today's block as the behaviour when `outdoor_fallback` is `null`, so an owner who prefers fail-closed can keep it, and make the fallback the default for new Plants only after the owner agrees (see [questions](#questions-for-the-owner)).
  Independently of the curve, let frost protection request heat at `heat_cold`'s clamp or at `supply.minimum` plus a margin when no curve target exists, because frost protection must not depend on an optional comfort input.
- Effort: S to M.
- Risk: medium; a wrong fallback overheats or underheats, but it stays inside `minimum` and `maximum`, and the high limit remains hardware.
- Test: core tests in `tests/core/test_supply.py` for fallback, recovery, and the frost path; a simulator scenario where the outdoor sensor dies at -10 °C with every zone calling.

### F4. A lost zone sensor leaves the zone unheated with no bound

- What happens: a required sensor that is unavailable or stale ends the call at once, and the zone then stays off until the sensor returns; frost protection also needs a usable reading.
  A Repair appears after 10 minutes, but nothing heats the room meanwhile, for days if the owner is away.
  The characterization tests in [#56](https://github.com/brumi1024/ha-hydronicus/pull/56) pin this.
- How others do it:
  - Versatile Thermostat enters safety mode after `safety_delay_min` (60 min) and runs `safety_default_on_percent` (0.1), and its docs warn that 0 risks freezing ([fetched](https://github.com/jmcollin78/versatile_thermostat/blob/main/documentation/en/feature-advanced.md)).
  - Smart Thermostat PID forces `output_safety` (5 %) after `sensor_stall` (6 h) ([fetched](https://github.com/ScratMan/HASmartThermostat)).
  - The Honeywell CM927 relay failsafe offers 0 % or about 20 % on ([search](https://www.diynot.com/diy/goto/post?id=2010019)).
  - Generic Thermostat holds the last reading, which users report as a bug ([core #18912, issue](https://github.com/home-assistant/core/issues/18912), [core #31171, issue](https://github.com/home-assistant/core/issues/31171)).
- Fix: an opt-in `sensor_fallback` per zone, for heating only, with `after` (such as 3600 s) and `duty` (such as 0.15 of a `period` of 2 hours), which calls the zone's loops for that share of time while every temperature of the zone is unusable, with a reason `sensor fallback: 15 % until sensor.x returns` and the existing Repair.
  It never applies in cooling, because cooling without a humidity and temperature picture is the condensation risk.
  It feeds the source only within `max_starts_per_hour` and `min_on`, so it cannot short cycle.
- Effort: M.
- Risk: medium; fail-to-heat and fail-to-stop are both failure modes, so the duty must be small and bounded, and the default stays off until the owner chooses.
- Test: core tests for the duty clock across restarts, and a simulator property that fallback never runs in cooling and never exceeds its duty.

### F5. A source found running after a lost store is released inside its minimum on time

- What happens: when the stored State is lost, a boiler or heat pump found on 60 s earlier is released at once even though `source_observed_changed` is known, because the minimum on time only applies when `State.source_request` was set (`core/step.py` around the source decision; `test_without_the_store_a_boiler_found_on_is_released_inside_its_minimum_on_time`).
- Why it matters: it is one extra short cycle per lost store, which is rare, but heat pump compressors are what the cycling features exist to protect.
- Fix: hold a request found on for `min_on` from its observed start whenever the observation proves the start time; this is the owner's decision from the open question in [#58](https://github.com/brumi1024/ha-hydronicus/pull/58).
- Effort: S.
- Risk: low.
- Test: flip the pinned test to the new expectation, and extend the simulator restart traces with a lost store.

### F6. A built-in heartbeat for relay-level watchdogs

- What happens: if Home Assistant stops while cooling, chilled water keeps flowing with no dew point check; [safety](../safety.md#cooling-while-home-assistant-is-not-running) asks the owner to build a relay watchdog by hand, with an automation that must refresh only relays that are already on.
  Users in the forum report the same class of problem for heating stuck on after a Shelly went offline ([fail-safe thread, search](https://community.home-assistant.io/t/fail-safe-needed-for-climate-control/572176)), and move logic into ESPHome or Tasmota `PulseTime` as a dead-man switch.
- Fix: publish a **Heartbeat** event or a `sensor.<plant>_heartbeat` timestamp that each successful evaluation updates at least every minute while live, with the list of outputs that may stay on, so an ESPHome or Shelly script can turn its relay off when the heartbeat is older than its timeout.
  Ship a tested example script next to `extras/shelly-modbus-bridge`.
  Hydronicus itself still never turns a relay on through this path, which keeps invariant 1.
- Effort: S for the entity, M with tested device scripts.
- Risk: low in Hydronicus; the device script must fail towards off for cooling and must not fail towards off for frost-critical heating without the owner's choice.
- Test: an integration test that the heartbeat advances only on successful evaluations and stops on evaluation failure, and a Node test of the script like `tests/test_extras.py`.

### F7. Smaller gaps worth a line each

- Frost protection with unarmed loops switches the Plant to heat while nothing heats; raise a Repair `frost_protection_unserved` naming the zone instead of only a reason.
- Heat-only loops are not exercised between cooling and heating; allow it once the pump's supply reading is above the worst dew point plus the guard margin, since water at room temperature can neither heat nor condense.
- A repeatedly failing evaluation leaves every output as it was, by design; consider a Repair escalation after 10 minutes that names whether the Plant was cooling, since that is the case where staying as it was is unsafe.
- Readings that report only on change, such as MQTT without `force_update`, go stale after an hour and stop a zone; Dual Smart Thermostat users hit the same with passive BLE sensors ([#672, issue](https://github.com/swingerman/ha-dual-smart-thermostat/issues/672)); the troubleshooting page covers it, and the setup flow could warn when a bound sensor has not reported for longer than its `max_age` at review time.

## Ranked list

Effort is for one maintainer, including tests and documentation: S is a few days, M is one to two weeks, L is several weeks.
Risk is the risk to heating safety or comfort if the feature misbehaves, after the existing interlocks.
Value weighs how many hydronic owners have the problem, how badly, and how well Hydronicus is placed to solve it compared with an automation.

| Rank | Feature | Value | Effort | Risk |
| --- | --- | --- | --- | --- |
| 1 | [Complete the heating curve](#1-complete-the-heating-curve) | High | M | Low to medium |
| 2 | [Plant-wide holiday and away mode](#2-plant-wide-holiday-and-away-mode) | Medium to high | S | Low |
| 3 | [Automatic heat and cool changeover](#3-automatic-heat-and-cool-changeover) | High for cooling plants | M | Medium |
| 4 | [A bundled Plant card](#4-a-bundled-plant-card) | High | M to L | None to control |
| 5 | [Scheduled DHW and anti-legionella](#5-scheduled-dhw-and-anti-legionella) | Medium | M | Medium |
| 6 | [Floor surface limits in heating](#6-floor-surface-limits-in-heating) | Medium | S | Low |
| 7 | [Actuation budget and wear counters](#7-actuation-budget-and-wear-counters) | Medium | S | Low |
| 8 | [Price and PV-aware comfort shift](#8-price-and-pv-aware-comfort-shift) | High demand | M | Medium |
| 9 | [Measured heat, delta-T, and COP](#9-measured-heat-delta-t-and-cop) | Medium | M | Low |
| 10 | [Optimum stop and overshoot learning](#10-optimum-stop-and-overshoot-learning) | Medium | M | Low |
| 11 | [Valve commissioning measurements](#11-valve-commissioning-measurements) | Low to medium | S to M | Low |
| 12 | [Demand-based supply temperature](#12-demand-based-supply-temperature) | Medium | L | Medium |
| 13 | [Loop duty-cycle balancing](#13-loop-duty-cycle-balancing) | Medium | L | Medium |
| 14 | [Screed drying program](#14-screed-drying-program) | Low for an existing house | M | Medium to high |
| 15 | [Mixed circuits](#15-mixed-circuits) | High for mixed emitters | L | High |
| 16 | [Bivalent and hybrid sources](#16-bivalent-and-hybrid-sources) | Medium | L | High |

What was considered and left out:

- PID or TPI room control replacing hysteresis: for underfloor loops with wax actuators the users of Smart Thermostat PID and SAT report derivative spikes and integral windup on slow slabs ([#180, issue](https://github.com/ScratMan/HASmartThermostat/issues/180), [#320, issue](https://github.com/ScratMan/HASmartThermostat/issues/320), [SAT #181, issue](https://github.com/Alexwijn/SAT/issues/181)), and Hydronicus already plans recovery from learned behaviour; item 13 covers the useful part.
- Presence detection: Home Assistant automations already set presets from person entities, and item 2 gives them one target to set.
- A native Modbus driver: the [0.4.0 notes](../releases/v0.4.0.md) already rule it out, and the generic entity seam plus the Shelly bridge is the right boundary.

### 1. Complete the heating curve

- Problem: the curve is two points and a clamp, so the owner cannot nudge it without reconfiguring, it heats on a warm afternoon after a cold night, it reacts to every outdoor fluctuation, and it knows nothing about the rooms.
- Who has it: every owner who lets Hydronicus own the supply setpoint of a heat pump or boiler; shoulder-season short cycling is the main heat pump complaint ([Octopus #824, fetched](https://www.github.com/BottlecapDave/HomeAssistant-OctopusEnergy/discussions/824), [Daikin data, search](https://community.openenergymonitor.org/t/daikin-altherma-data/26637)).
- How others do it:
  - Siemens Albatros: slope 0.10 to 4.00 and a parallel displacement of ±4.5 °C ([RVS46, search](https://manualmachine.com/siemens/ce1u2353en01a/485324-user-manual)); room influence on the RVL470 ([search](https://www.manualslib.com/manual/958756/Siemens-Rvl470.html?page=33)); an adapting heating curve ([search](https://mybuilding.siemens.com/D036861342594/Help/EngineeringHelp/en-US/15763162635.html)).
  - Viessmann Vitotronic: per-circuit slope, 0.2 to 0.8 for underfloor ([search](https://www.scribd.com/document/717251945/vitotronic-200h)).
  - Vaillant sensoCOMFORT: heating off above an outdoor switch-off threshold ([search](https://manualslib.mx/manual/744302/Vaillant-Sensocomfort-Vrc-720-3.html?page=60)).
  - tekmar: warm weather shutdown at the curve's starting point, while still monitoring sensors ([search](https://watts.com/dfsmedia/0533dbba17714b1ab581ab07a4cbb521/81341-source/253-d-01)).
  - Bosch and Buderus EMS: room influence in K from a reference room ([RC35, search](https://www.manualslib.com/manual/831369/Bosch-Rc35.html?page=35)).
  - Community: template curves with a hard-coded slope ([search](https://community.home-assistant.io/t/weather-compensation-heating-automation/735997)), the WDA sensor with indoor corrections ([search](https://github.com/sokolovs/wda-sensor/wiki/About-integration/09a7b38dc4556cda3da81a0baf824855d94d35d9)), and offset nudging of a native Nibe curve ([search](https://community.home-assistant.io/t/smart-nibe-ultra-adaptive-heat-curve-control-mqtt-spot-prices/975863)).
- Design:
  - `core/supply.py` gains, all optional: `offset` (K, a parallel shift), `heating_limit` (an outdoor temperature above which heating demand is not passed to the source, with a 1 K hysteresis), `outdoor_damping` (a time constant in seconds for a first-order filter of the outdoor reading, such as 10800), `room_influence` (`{zone: <slug>, factor: 1.0, limit: 5}`, shifting the curve by factor times the lead zone's error, clamped), and `outdoor_fallback` from F3.
  - The damped outdoor value and the heating limit state persist in `State`, so a restart does not reset them; `step()` passes them to `supply_target` explicitly, keeping the core pure.
  - The heating limit also works for a source without a supply number: it keeps the request off while zones may still circulate, with a reason `warm weather shutdown at 17.2 °C outdoors`.
    Frost protection is exempt.
  - New entities: a **Heating curve offset** number (±5 K) any user may set, and **Damped outdoor temperature** and **Supply target** sensors.
  - Plant file keys under `source.supply`, the Plant settings form for offset and heating limit, and `docs/plant-file.md`.
- Effort: M.
- Risk: low to medium; every target remains inside `minimum` and `maximum`, and the heating limit only withholds heat, with frost protection as the floor.
  Room influence can feed back on a lead room with a fireplace, so it stays clamped and off by default.
- Test: core tests of each term and their clamps; Hypothesis properties that the target is monotonic in outdoor temperature for a fixed offset and always inside the bounds; a simulator scenario with a cold night and a warm afternoon that checks fewer source starts with the heating limit.

### 2. Plant-wide holiday and away mode

- Problem: there is no single place to say "we are away until Sunday 18:00"; each thermostat's preset must be changed, and changing it leaves schedule control, so the owner must remember to select `schedule` again on return.
- Who has it: everyone with more than two zones; forum users report frost, away, and eco precedence bugs in the largest heating blueprint ([Advanced Heating Control, search](https://community.home-assistant.io/t/advanced-heating-control/469873)) and schedules that leak between zones ([search](https://community.home-assistant.io/t/multiple-per-thermostat-schedules/975718)).
- How others do it: Heatmiser neoStat holds a holiday temperature for N days and then resumes the schedule ([search](https://manualmachine.com/heatmiser/neostate/21203534-user-manual)); Versatile Thermostat has timed presets and returns to the previous preset ([fetched](https://github.com/jmcollin78/versatile_thermostat)).
- Design:
  - A Plant-level **Away** switch and a **Away until** `datetime` entity, plus `hydronicus.set_away` and `hydronicus.end_away` actions with an optional `until`.
  - While away, each digital thermostat uses its `away` preset target, or a Plant `away` default such as 16 °C heating and 30 °C cooling, without leaving schedule control and without touching the manual target.
  - Before `until`, early start recovers towards the level the schedule will ask for at that time, with the existing `max_early_start` bound and learned rates.
  - The away state and `until` persist in `State`; `core/comfort.py` treats away as a level with a precedence documented in one table: frost protection, then windows, then away, then schedule.
  - External thermostats are untouched, since Hydronicus never commands them.
- Effort: S.
- Risk: low; away only lowers heating and raises cooling targets.
- Test: core tests of precedence and early recovery to `until`; an integration test that away survives a restart and ends on time; a test that a manual change during away is kept for after the return.

### 3. Automatic heat and cool changeover

- Problem: the **Mode** select is manual; the documented automation ([entities](../entities.md#automatic-heat-and-cool-changeover)) must pick thresholds, damping, and timing by itself.
  A naive one flips to cooling on a warm spring afternoon and burns the hour-long dwell twice a day.
- Who has it: every owner with cooling loops, which Hydronicus supports more completely than any other Home Assistant project surveyed; Dual Smart Thermostat offers heat-cool, but per room, not for a shared plant ([fetched](https://github.com/swingerman/ha-dual-smart-thermostat)).
- How others do it: heat pump controllers switch on a damped or averaged outdoor temperature with separate heating and cooling limits; Vaillant's switch-off threshold and tekmar's warm weather shutdown are the heating half ([Vaillant, search](https://manualslib.mx/manual/744302/Vaillant-Sensocomfort-Vrc-720-3.html?page=60)).
  The exact cooling-side defaults were not confirmed from a primary manual in this research.
- Design:
  - An `auto` option on the **Mode** select, offered when a loop cools and a `changeover` mapping exists: `{outdoor_sensor, heat_below: 15, cool_above: 22, averaging: 86400, min_dwell: 43200}`.
  - The requested mode follows the damped outdoor temperature with the dead band between the two limits, and changes at most once per `min_dwell`, through the existing changeover sequence and `mode_dwell`.
  - Cooling is only requested when a zone actually calls for cooling, so a cool spell does not start the source mode change with nothing to cool.
  - The damped outdoor value is shared with item 1.
  - The Status gains `requested_mode_basis: auto` and a reason such as `auto: 24 h mean 23.1 °C above 22.0 °C`.
- Effort: M.
- Risk: medium; a wrong change is harmless in heating but in cooling it relies on the condensation guard, which stays authoritative.
- Test: core tests of the dead band and `min_dwell`; simulator properties that auto never violates invariant 5 and never changes mode more than once per `min_dwell`; a seasonal trace in `tests/sim` from April to June.

### 4. A bundled Plant card

- Problem: the Status sensor's `reasons`, `holds`, `proposed`, and `blocked_zones` are what make Hydronicus explainable, but stock cards show none of it, and the owner must assemble dozens of entities.
- Who has it: every user, and most of all one in Dry run deciding whether to go live.
- How others do it: Better Thermostat ships a UI card ([fetched](https://github.com/KartoffelToby/better_thermostat)); the Scheduler card is the reason the Scheduler component is popular ([fetched](https://github.com/nielsfaber/scheduler-component)); forum builders bundle dashboards with their controllers ([search](https://community.home-assistant.io/t/multi-zone-heating-cooling-control-with-schedules-presence-modes-safety-lockouts-and-responsive-dashboard/1014675)).
- Design: follow the specification already written in [#32](https://github.com/brumi1024/ha-hydronicus/issues/32), with the read model taken from `view.py` through the Status attributes, registered as a frontend resource from the integration so HACS installs it, and with no control beyond the **Mode** select, the climate entities, and **Control equipment**.
  Show zone, loop, valve, pump, and source as one path with its current wait and timer, Dry run proposals beside actual states, and Repairs at the top.
- Effort: M to L.
- Risk: none to control, as long as the card only calls existing services; a misleading card is a comfort and trust risk, so it must render reasons verbatim.
- Test: JavaScript unit tests run in Node, as `tests/test_extras.py` already does for the bridge, and Playwright screenshots of the trial Plant from [getting started](../getting-started.md#part-1-a-trial-plant) in Dry run and live.

### 5. Scheduled DHW and anti-legionella

- Problem: Hydronicus owns the DHW target but holds it constant, so the owner cannot heat the tank in cheap or sunny hours, and nothing runs or verifies a pasteurisation cycle when the owned target is below 60 °C, which is common on heat pumps for efficiency.
- Who has it: heat pump owners whose own controller's legionella function is disabled or is bypassed because Hydronicus owns the setpoint.
- How others do it:
  - Mitsubishi Ecodan defaults to 65 °C every 15 days from 03:00, with a 3 hour maximum and 30 minutes held ([search](https://manualslib.mx/manual/202549/Mitsubishi-Electric-Ecodan-Ehst20-Serie.html?page=40)).
  - Nibe's periodic increase runs every 1 to 90 days, 14 by default ([search](https://www.manualslib.com/manual/1146229/Nibe-F1145.html?page=45)); a forum report shows it failing silently ([search](https://renewableheatinghub.co.uk/forums/renewable-heating-air-source-heap-pumps-ashps/nibe-f2040-periodic-warm-water-increase-fails)).
  - Guidance: HSE asks for storage at 60 °C or more ([search](https://hse.gov.uk/Legionnaires/hot-and-cold.htm)); DVGW W551 thermal disinfection is 70 °C at outlets for 3 minutes, per secondary sources ([search](https://www.caleffi.com/sites/default/files/media/external-file/01325_EN.pdf)).
- Design:
  - `source.dhw.schedule`: a `schedule` helper whose blocks carry `target` data, reusing the block data reader from comfort schedules, and falling back to the owned target outside blocks.
  - `source.dhw.legionella`: `{temperature: 60, interval: 604800, start: "02:00", hold: 1800, timeout: 10800, tank_temperature: sensor.tank}`, with its own `legionella_maximum` so the normal `maximum` stays low.
  - `core/dhw.py` runs the cycle as a bounded boost whose success needs the tank sensor to hold `temperature` for `hold`; a timeout raises a `legionella_failed` Repair, and a **Last disinfection** sensor records success.
  - The cycle never runs while handover is on or **Control equipment** is off, and it counts as a source start for `max_starts_per_hour`.
- Effort: M.
- Risk: medium; a high DHW target is a scald risk at outlets without a thermostatic mixing valve, which HSE guidance expects anyway, and the documentation must say so.
  It is also a comfort risk if the cycle collides with space heating; heat pumps usually prioritise DHW, so the cycle should start at night.
- Test: core tests in `tests/core/test_dhw.py` for start, hold, timeout, restart mid-cycle, and adoption of an external change; a simulator scenario in `tests/sim/test_home_heat_pump_dhw.py`.

### 6. Floor surface limits in heating

- Problem: a loop's `surface_temperature` is used only in cooling; in heating nothing stops a floor from exceeding comfort or material limits when the supply is high, for example during a DHW-shared or boiler-fed run.
- Who has it: underfloor owners with a boiler, or with radiators and floors on one supply temperature; requested from Versatile Thermostat ([#232, issue](https://github.com/jmcollin78/versatile_thermostat/issues/232)) and Dual Smart Thermostat ([#647, issue](https://github.com/swingerman/ha-dual-smart-thermostat/issues/647)).
- How others do it: EN 1264-3 sets 29 °C for occupied zones and 35 °C for the peripheral zone ([summary, search](https://iteh.es/catalog/standards/sist/e24888ec-0fa8-4e52-8560-8ebc95be8b93/sist-en-1264-3-2021)); Dual Smart Thermostat has floor minimum and maximum per preset ([fetched](https://github.com/swingerman/ha-dual-smart-thermostat)).
- Design: a loop `surface_maximum` for heating, with a 1 K release, that drops the loop like a condensation guard does in cooling, and an optional `surface_comfort` minimum that keeps a bathroom floor warm while the room is satisfied, as Uponor's comfort setting does ([search](https://brandportal.uponor.com/m/201ae4eebd5d084a/original/TI-Smatrix-EN-1116265-v4.pdf)).
- Effort: S.
- Risk: low; the maximum only withholds heat, and a stale surface reading should leave heating allowed with a Repair, unlike cooling, because a floor limit is a comfort limit and the hardware limiter is the safety device.
- Test: core tests mirroring the condensation guard tests; a simulator check that a surface limit never blocks frost protection.

### 7. Actuation budget and wear counters

- Problem: every valve opening and every pump start costs actuator and relay life, and a bad hysteresis or a flapping sensor shows up only when a part fails.
- Who has it: owners with many wax actuators on relays; Smart Thermostat PID users ask to limit valve movements to under 100 a day ([#240, issue](https://github.com/ScratMan/HASmartThermostat/issues/240)); the Shelly bridge already holds settings to a daily write budget ([#52](https://github.com/brumi1024/ha-hydronicus/pull/52)).
- Design: count observed on transitions per output in `flow_history.py` style hourly buckets, publish **Starts today** attributes per loop and pump, and raise a `excessive_cycling` Repair above a configurable daily count; no control change.
- Effort: S.
- Risk: low, diagnostics only.
- Test: integration tests of counting across restarts and the Repair threshold.

### 8. Price and PV-aware comfort shift

- Problem: users want to store heat in the slab when electricity is cheap or the PV array exports, and to avoid heating in expensive hours, without breaking minimum run times.
- Who has it: heat pump owners on dynamic tariffs or with PV; it is one of the most frequent forum topics ([Nordpool and SG Ready, search](https://community.home-assistant.io/t/control-nibe-heat-pump-using-shelly-and-sg-ready-based-on-nordpool-price/466862), [15-minute pricing, search](https://community.home-assistant.io/t/optimizing-hvac-energy-savings-with-nordpool-15-min-pricing-part-1-3-theory-implementation-and-examples/936741), [EMHASS heat pump, search](https://emhass.readthedocs.io/en/latest/study_cases/heat_pump_walkthrough.html)), and a user asked for start blocking near price-slot edges because of short cycling ([Octopus #824, fetched](https://www.github.com/BottlecapDave/HomeAssistant-OctopusEnergy/discussions/824)).
- How others do it: SG Ready uses two relay inputs for four states, normal, recommended on, blocked, and forced ([search](https://www.alpha-innotec.com/en/knowledge-base/heat-pump-knowledge-center/sg-ready-interface-for-heat-pumps)), and the signal should last at least 10 minutes ([Kostal, search](https://documents.kostal.com/PLENTICORE-G3/BA/en-GB/136335755603408651.html)).
- Design:
  - Hydronicus does not compute prices; it consumes a Plant-level `flex` mapping: `{boost: binary_sensor.cheap_or_surplus, block: binary_sensor.expensive, heat_raise: 1.0, cool_lower: 1.0, block_floor: 1.0}`.
  - While `boost` is on, each opted-in zone's effective heating target rises by `heat_raise` (cooling target lowers by `cool_lower`), so the slab stores heat within a bounded band; while `block` is on, zones call only below their target minus `block_floor`, so comfort has a floor.
  - Changes of `boost` or `block` never cut a running request short of `min_on` or `hold_after_demand`, and the DHW target of item 5 can follow the same `boost`.
  - SG Ready relay outputs are left to the owner's automation, since Hydronicus already has the `inhibit_sensor` for utility lockout.
- Effort: M.
- Risk: medium; a stuck `boost` overheats by at most `heat_raise`, and a stuck `block` underheats by at most `block_floor`, both shown in reasons.
- Test: core tests of the bounded shift and the floor; a simulator trace with a price signal that toggles every 15 minutes, checking that source starts stay within `max_starts_per_hour`.

### 9. Measured heat, delta-T, and COP

- Problem: the documentation rightly refuses to call duty cycle heat or energy, but owners who have a heat meter, flow rate, or supply and return probes still assemble COP from templates with known errors, such as delta-T lingering after the compressor stops ([COP help, search](https://community.home-assistant.io/t/help-with-calculating-heat-pump-cop/718001), [WTH COP, search](https://community.home-assistant.io/t/wth-doesnt-the-energy-dashboard-show-the-cop-of-my-heat-pump/804401)).
- Who has it: heat pump owners and anyone balancing loops ([manifold probes, search](https://community.home-assistant.io/t/temperature-sensors-for-underfloor-heating-manifold/920963)).
- Design:
  - Optional loop `return_temperature`, pump `flow_rate` (numeric), and source `electrical_energy` bindings.
  - A **Loop delta-T** sensor while the loop flows, a **Heat power** and a `total_increasing` **Heat energy** sensor only when a measured flow rate exists, and a **COP** sensor over the last day from summed energies, never from averaged instantaneous values.
  - Energy accumulates only while the source is observed running, which removes the lingering delta-T error.
  - The response check can use delta-T as extra evidence that a loop really carries heat.
- Effort: M.
- Risk: low; diagnostics only.
- Test: core tests of integration and gating; integration tests of the Energy dashboard compatible state classes.

### 10. Optimum stop and overshoot learning

- Problem: early start brings comfort on time, but the slab keeps heating after the comfort period ends, and the [0.4.0 notes](../releases/v0.4.0.md) list post-stop overshoot and settling as future work.
- How others do it: Honeywell evohome has optimum stop per zone ([user guide, search](https://evohome.resideo.com/app/uploads/2025/07/evohome_Userguide_EN.pdf)); Netatmo learns a thermal model over about two weeks ([search](https://helpcenter.netatmo.com/hc/en-us/articles/31975595742098)).
- Design: extend `learning.py` and `core/thermal.py` to record overshoot after a call ends, and let `assist` end heating up to a bounded `max_early_stop` before a setback when the learned coast keeps the room within 0.5 K of comfort until the period ends.
- Effort: M.
- Risk: low; it can only end a call early within a bound, and the hysteresis restarts it if the room falls.
- Test: simulator scenarios with the thermal world, as the existing predictive tests do.

### 11. Valve commissioning measurements

- Problem: `opening_time` defaults to 180 s, but wax actuators take about 2 minutes of dead time plus 3 minutes of stroke and more when cold ([TWA-Z datasheet, search](https://manualmachine.com/danfoss/twaz/18782518-data-sheet); [forum timings, search](https://community.home-assistant.io/t/convert-switch-to-valve-with-configurable-delays/666506)).
- Design: with a readiness sensor or a loop supply probe, record the observed time from the open command to readiness or to a supply rise, and publish the 90th percentile per valve in diagnostics with a suggestion when it exceeds `opening_time`; never change the configuration automatically.
- Effort: S to M.
- Risk: low.
- Test: integration tests with delayed readiness from `tests/integration/helpers.py`.

### 12. Demand-based supply temperature

- Problem: an outdoor curve ignores solar and internal gains; the zones themselves know how far they are from target.
- How others do it: Loxone puts the highest heating or lowest cooling computed flow setpoint on its output ([search](https://www.loxone.com/enen/?p=1272)); Danfoss Icon2 offers demand-based flow temperature from all rooms ([search](https://designcenter.danfoss.com/products/climate-solutions-for-heating/smart-heating/danfoss-icon2/icon2-main-controllers/danfoss-icon2-main-controller)); Nibe integrates a degree-minute deficit ([search](https://www.manualslib.com/manual/1612921/Nibe-Smo-40.html?page=45)).
- Design: after item 1, add a bounded `demand_boost` term to the curve proportional to the largest calling zone's deficit, rate-limited per hour, so the supply rises only when zones lag.
- Effort: L, mostly in tuning and simulation.
- Risk: medium; feedback on slow slabs can oscillate, which the simulator's thermal world must show before it ships.
- Test: simulator comparisons against the plain curve over cold and mild weeks.

### 13. Loop duty-cycle balancing

- Problem: on and off demand opens the loops of a short and a long circuit for the same time, so the short circuit overheats while the long one lags; the duty cycle sensor shows it but nothing acts.
- How others do it: Uponor autobalancing sets per-loop on and off duty from estimated need, recalculated every 2 or 10 minutes ([search](https://www.danfoss.com/en/about-danfoss/articles/dhs/types-of-hydronic-balancing-auto-balancing/)); multizone-thermostat schedules valve PWM across satellites to keep the source running smoothly ([fetched](https://github.com/vindaalex/multizone-thermostat)); Smart Thermostat PID users ask to synchronise PWM across zones ([#321, issue](https://github.com/ScratMan/HASmartThermostat/issues/321)).
- Design: an opt-in per zone that throttles a loop within a call to a learned share of a long period (such as 2 hours), while the source sees a steadier combined load; it respects valve `min_on`, the actuation budget of item 7, and the min-flow path.
- Effort: L.
- Risk: medium; more valve cycles and more complex reasons, so it should follow items 7 and 9.
- Test: simulator properties for invariants 2 to 4 under throttling, and a thermal comparison of two unequal loops.

### 14. Screed drying program

- Problem: new underfloor screed needs a functional heating program before use.
- How others do it: EN 1264-4 protocols hold about 25 °C for 3 days, then the design maximum for at least 4 days ([KAN-therm protocol, search](https://lt.kan-therm.com/resfile/open/2605/new_KAN-therm-protokol-EN-2026_surface-heating-cooling-screed-heating.pdf)); Vaillant VRC 700 and Daikin Altherma run a day-by-day profile per circuit ([search](https://manualshive.com/en/manual/vaillant/vrc-700-2/848955?page=18), [search](https://www.daikin.co.uk/content/dam/dauk/document-library/installation-manuals/heat/air-to-water-heat-pump-low-temperature/ebla09dv3u/EBLA09DV3U.EBLA09D3V3U_Installation%20manual_4PEN765229-1_English%20UK.pdf)).
- Design: a `screed` action with a profile of daily supply targets that overrides demand and supply control for chosen loops, with progress persisted.
- Effort: M.
- Risk: medium to high; wrong temperatures crack screed, and the source's own program is usually the better tool.
- Value: low for an existing house; leave it unless another user asks.

### 15. Mixed circuits

- Problem: radiators need 45 °C while floors need 30 °C, and one supply temperature serves both badly.
- How others do it: Viessmann and Siemens run a separate curve per mixed circuit with its own mixing valve ([Vitotronic, search](https://www.scribd.com/document/717251945/vitotronic-200h)); VT users with underfloor plus radiators on one heat pump were declined ([discussion #1851, fetched](https://github.com/jmcollin78/versatile_thermostat/discussions/1851)).
- Design: a pump `mixing` mapping with a `number` or `valve` position output, a mixed supply sensor, and its own curve, controlled by a PI loop in a new pure module with a fixed evaluation period.
- Effort: L.
- Risk: high; a stuck mixing valve sends boiler water into a floor, which a hardware limiter must stop, and the periodic control loop is a new kind of evaluation for the runtime.
- Value: high for houses with mixed emitters, but only worth it once the owner or a user has one.

### 16. Bivalent and hybrid sources

- Problem: a heat pump with a boiler backup, or a fireplace buffer, needs source selection by outdoor temperature or price.
- Current state: `inhibit_sensor` already covers "another source supplies the zones"; the earlier source-switching milestones ([#16](https://github.com/brumi1024/ha-hydronicus/issues/16), [#22](https://github.com/brumi1024/ha-hydronicus/issues/22)) were dropped in the redesign.
- Design: a second source with a bivalence point and break-before-make selection, reusing the old milestone's state machine design.
- Effort: L.
- Risk: high; two sources multiply the interlocks of invariants 3 to 6.
- Value: medium; most owners can use the inhibit sensor and the backup's own controls.

## Questions for the owner

The ranking assumes the answers in brackets; a different answer changes it.

1. Does Hydronicus own your heat pump's heating supply setpoint, or only cooling (`supply.modes`)?
   [Assumed: at least one Plant uses the outdoor curve, which makes item 1 and F3 the top priorities.]
2. When a zone sensor or the outdoor sensor is lost in winter, do you prefer fail-closed (no heat, Repair) or a bounded fallback?
   [Assumed: a bounded fallback, opt-in, as F3 and F4 propose.]
3. Do you use the DHW binding, and does the heat pump's own legionella function still run?
   [Assumed: yes and unknown, which keeps item 5 in the top 5.]
4. Do you have a dynamic tariff or PV export?
   [Assumed: no; with a yes, item 8 moves into the top 5.]
5. Is the dashboard card for you alone or for other users of the integration?
   [Assumed: other users matter, which keeps item 4 in the top 5.]

## Sources

### Hydronicus

- [README](../../README.md), [CONTEXT](../../CONTEXT.md), [how it works](../how-it-works.md), [safety](../safety.md), [plant file](../plant-file.md), [entities](../entities.md), [development](../development.md), [releases](../releases).
- Characterization PRs: [#55](https://github.com/brumi1024/ha-hydronicus/pull/55), [#56](https://github.com/brumi1024/ha-hydronicus/pull/56), [#57](https://github.com/brumi1024/ha-hydronicus/pull/57), [#58](https://github.com/brumi1024/ha-hydronicus/pull/58).
- Earlier specifications: [#16](https://github.com/brumi1024/ha-hydronicus/issues/16), [#22](https://github.com/brumi1024/ha-hydronicus/issues/22), [#32](https://github.com/brumi1024/ha-hydronicus/issues/32), and the redesign [#41](https://github.com/brumi1024/ha-hydronicus/pull/41).

### Home Assistant projects

- Versatile Thermostat: [README (fetched)](https://github.com/jmcollin78/versatile_thermostat), [algorithms (fetched)](https://github.com/jmcollin78/versatile_thermostat/blob/main/documentation/en/algorithms.md), [auto-TPI (fetched)](https://github.com/jmcollin78/versatile_thermostat/blob/main/documentation/en/feature-autotpi.md), [central boiler (fetched)](https://github.com/jmcollin78/versatile_thermostat/blob/main/documentation/en/feature-central-boiler.md), [advanced and safety (fetched)](https://github.com/jmcollin78/versatile_thermostat/blob/main/documentation/en/feature-advanced.md), [auto start and stop (fetched)](https://github.com/jmcollin78/versatile_thermostat/blob/main/documentation/en/feature-auto-start-stop.md).
- Versatile Thermostat issues: [#234 central boiler (fetched)](https://github.com/jmcollin78/versatile_thermostat/issues/234), [#1851 multiple central configurations (fetched)](https://github.com/jmcollin78/versatile_thermostat/discussions/1851), [#1909](https://github.com/jmcollin78/versatile_thermostat/issues/1909), [#2084](https://github.com/jmcollin78/versatile_thermostat/issues/2084), [#1908](https://github.com/jmcollin78/versatile_thermostat/issues/1908), [#1831](https://github.com/jmcollin78/versatile_thermostat/issues/1831), [#1437](https://github.com/jmcollin78/versatile_thermostat/issues/1437), [#2052](https://github.com/jmcollin78/versatile_thermostat/issues/2052), [#2107](https://github.com/jmcollin78/versatile_thermostat/issues/2107), [#1220](https://github.com/jmcollin78/versatile_thermostat/issues/1220), [#232](https://github.com/jmcollin78/versatile_thermostat/issues/232), [#1144](https://github.com/jmcollin78/versatile_thermostat/issues/1144) (issue).
- Better Thermostat: [README (fetched)](https://github.com/KartoffelToby/better_thermostat); issues [#2750](https://github.com/KartoffelToby/better_thermostat/issues/2750), [#1959](https://github.com/KartoffelToby/better_thermostat/issues/1959), [#2770](https://github.com/KartoffelToby/better_thermostat/issues/2770), [#1164](https://github.com/KartoffelToby/better_thermostat/issues/1164), [#1403](https://github.com/KartoffelToby/better_thermostat/issues/1403), [#2357](https://github.com/KartoffelToby/better_thermostat/issues/2357) (issue).
- Smart Thermostat PID: [README (fetched)](https://github.com/ScratMan/HASmartThermostat); issues [#220](https://github.com/ScratMan/HASmartThermostat/issues/220), [#196](https://github.com/ScratMan/HASmartThermostat/issues/196), [#67](https://github.com/ScratMan/HASmartThermostat/issues/67), [#180](https://github.com/ScratMan/HASmartThermostat/issues/180), [#320](https://github.com/ScratMan/HASmartThermostat/issues/320), [#321](https://github.com/ScratMan/HASmartThermostat/issues/321), [#240](https://github.com/ScratMan/HASmartThermostat/issues/240) (issue).
- Generic Thermostat: [docs (fetched)](https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/generic_thermostat.markdown), [frozen, core #183690 (issue)](https://github.com/home-assistant/core/pull/183690), [template climate, core #173033 (issue)](https://github.com/home-assistant/core/pull/173033), [core #18912 (issue)](https://github.com/home-assistant/core/issues/18912), [core #31171 (issue)](https://github.com/home-assistant/core/issues/31171), [fail-safe mode (search)](https://community.home-assistant.io/t/generic-thermostat-fail-safe-mode/356954?page=2).
- Scheduler component: [README (fetched)](https://github.com/nielsfaber/scheduler-component); issues [#234](https://github.com/nielsfaber/scheduler-component/issues/234), [#277](https://github.com/nielsfaber/scheduler-component/issues/277), [#305](https://github.com/nielsfaber/scheduler-component/issues/305) (issue).
- SAT: [README (fetched)](https://github.com/Alexwijn/SAT); issues [#155](https://github.com/Alexwijn/SAT/issues/155), [#178](https://github.com/Alexwijn/SAT/issues/178), [#199](https://github.com/Alexwijn/SAT/issues/199), [#144](https://github.com/Alexwijn/SAT/issues/144), [#181](https://github.com/Alexwijn/SAT/issues/181) (issue); [forum thread (search)](https://community.home-assistant.io/t/custom-component-smart-autotune-thermostat/550542).
- Dual Smart Thermostat: [README (fetched)](https://github.com/swingerman/ha-dual-smart-thermostat); issues [#672](https://github.com/swingerman/ha-dual-smart-thermostat/issues/672), [#647](https://github.com/swingerman/ha-dual-smart-thermostat/issues/647) (issue).
- Other projects: [hass-ufh-controller (fetched)](https://github.com/lnagel/hass-ufh-controller), [multizone-thermostat (fetched)](https://github.com/vindaalex/multizone-thermostat), [Schedule helper docs (fetched)](https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/schedule.markdown), [OpenTherm Gateway docs (fetched)](https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/opentherm_gw.markdown), [Advanced Heating Control (search)](https://community.home-assistant.io/t/advanced-heating-control/469873), [WDA sensor (search)](https://github.com/sokolovs/wda-sensor/wiki/About-integration/09a7b38dc4556cda3da81a0baf824855d94d35d9), [ClimateOptimizer (search)](https://github.com/smefa/ClimateOptimizer), [EMHASS heat pump (search)](https://emhass.readthedocs.io/en/latest/study_cases/heat_pump_walkthrough.html), [Octopus Energy discussion #824 (fetched)](https://www.github.com/BottlecapDave/HomeAssistant-OctopusEnergy/discussions/824).

### Community threads (search)

- [Underfloor heating with zone control](https://community.home-assistant.io/t/underfloor-heating-with-zone-control/570356), [Multi-zone hydronic floor heating](https://community.home-assistant.io/t/multi-zone-hydronic-floor-heating-control-system/965116), [WTH underfloor heating](https://community.home-assistant.io/t/wth-are-we-missing-support-for-underfloor-heating/813657), [Underfloor heating controller](https://community.home-assistant.io/t/underfloor-heating-controller/977236).
- [Boiler with multiple thermostats](https://community.home-assistant.io/t/boiler-automation-with-multiple-thermostat-inputs/684083), [One of two thermostats turns off the boiler](https://community.home-assistant.io/t/avoiding-that-one-of-two-thermostats-turns-off-heating-boiler/446716), [Radiator thermostats and heating pump](https://community.home-assistant.io/t/several-radiator-thermostats-and-heating-pump/285745), [Switch to valve with delays](https://community.home-assistant.io/t/convert-switch-to-valve-with-configurable-delays/666506).
- [Weather compensation automation](https://community.home-assistant.io/t/weather-compensation-heating-automation/735997), [Nibe Modbus](https://community.home-assistant.io/t/modbus-configuration-for-nibe-s-series-heatpumps/400422), [Nibe adaptive curve](https://community.home-assistant.io/t/smart-nibe-ultra-adaptive-heat-curve-control-mqtt-spot-prices/975863), [Daikin Altherma data](https://community.openenergymonitor.org/t/daikin-altherma-data/26637).
- [Fail-safe for climate control](https://community.home-assistant.io/t/fail-safe-needed-for-climate-control/572176), [Shelly and ESPHome thermostat if HA crashes](https://community.home-assistant.io/t/shelly-esphome-to-act-as-a-thermostat-in-case-ha-crashes/1002575), [Sensor failover blueprint](https://community.home-assistant.io/t/stop-freezing-in-the-dark-build-unbreakable-sensors-with-the-failover-blueprint/1013598).
- [Dew point sensors for floors](https://community.home-assistant.io/t/room-thermostat-temperature-floor-temp-dew-point-sensors/787909), [Nibe SG Ready with Nordpool](https://community.home-assistant.io/t/control-nibe-heat-pump-using-shelly-and-sg-ready-based-on-nordpool-price/466862), [Nordpool 15-minute pricing](https://community.home-assistant.io/t/optimizing-hvac-energy-savings-with-nordpool-15-min-pricing-part-1-3-theory-implementation-and-examples/936741), [Multiple per-thermostat schedules](https://community.home-assistant.io/t/multiple-per-thermostat-schedules/975718), [Multi-zone control with presence and dashboard](https://community.home-assistant.io/t/multi-zone-heating-cooling-control-with-schedules-presence-modes-safety-lockouts-and-responsive-dashboard/1014675).
- [Heat pump COP](https://community.home-assistant.io/t/help-with-calculating-heat-pump-cop/718001), [WTH COP in the Energy dashboard](https://community.home-assistant.io/t/wth-doesnt-the-energy-dashboard-show-the-cop-of-my-heat-pump/804401), [Manifold temperature sensors](https://community.home-assistant.io/t/temperature-sensors-for-underfloor-heating-manifold/920963), [Relay failsafe (diynot)](https://www.diynot.com/diy/goto/post?id=2010019), [Nibe periodic increase fails](https://renewableheatinghub.co.uk/forums/renewable-heating-air-source-heap-pumps-ashps/nibe-f2040-periodic-warm-water-increase-fails).

### Commercial controllers and standards (search)

- Heating curves: [Siemens RVL470](https://www.manualslib.com/manual/958756/Siemens-Rvl470.html?page=35), [Siemens RVS46](https://manualmachine.com/siemens/ce1u2353en01a/485324-user-manual), [Siemens adapting heating curve](https://mybuilding.siemens.com/D036861342594/Help/EngineeringHelp/en-US/15763162635.html), [Viessmann Vitotronic 200-H](https://www.scribd.com/document/717251945/vitotronic-200h), [Vaillant sensoCOMFORT](https://manualslib.mx/manual/744302/Vaillant-Sensocomfort-Vrc-720-3.html?page=60), [Bosch RC35](https://www.manualslib.com/manual/831369/Bosch-Rc35.html?page=35), [tekmar brochure](https://watts.com/dfsmedia/0533dbba17714b1ab581ab07a4cbb521/81341-source/253-d-01), [Danfoss ECL application guide](https://manualmachine.com/danfoss/eclcomfort210/18792967-application-guide).
- Optimum start and stop: [evohome user guide](https://evohome.resideo.com/app/uploads/2025/07/evohome_Userguide_EN.pdf), [Netatmo anticipation](https://helpcenter.netatmo.com/hc/en-us/articles/31975595742098), [tado early start](https://support.tado.com/en/articles/3387209).
- Frost protection: [Siemens RVL470](https://www.manualslib.com/manual/958756/Siemens-Rvl470.html?page=54), [Siemens LMS14](https://www.manualslib.com/manual/1308475/Siemens-Lms14.html?page=203), [Vaillant frost advice](https://www.vaillant.co.uk/advice/heating-tips/home-advice/controls-and-frost-protection/), [tekmar 256 sensor fault](https://manualshive.com/en/manual/watts/tekmar-256/876853?page=19).
- Legionella: [HSE hot and cold water](https://hse.gov.uk/Legionnaires/hot-and-cold.htm), [HSG274](https://designingbuildings.co.uk/wiki/HSG_274_Legionnaires'_disease,_Technical_guidance), [Caleffi on W551](https://www.caleffi.com/sites/default/files/media/external-file/01325_EN.pdf), [Mitsubishi Ecodan](https://manualslib.mx/manual/202549/Mitsubishi-Electric-Ecodan-Ehst20-Serie.html?page=40), [Nibe F1145](https://www.manualslib.com/manual/1146229/Nibe-F1145.html?page=45).
- Exercise and actuators: [Uponor Smatrix](https://brandportal.uponor.com/m/130acd4eb93386b/original/TI-Smatrix-EN-1116265-v6.pdf), [Wavin Sentio](https://mediahub.wavin.com/m/6f1524a27dc77676/original/Sentio-Quick-Installation-Guide.pdf), [Danfoss TWA-ZL](https://manualmachine.com/danfoss/twazl/18799159-data-sheet), [Danfoss TWA-Z](https://manualmachine.com/danfoss/twaz/18782518-data-sheet).
- Heat pumps: [Kensa buffer sizing](https://kensa.co.uk/resources/buffer-tank-sizing-heat-pump), [starts per hour](https://community.openenergymonitor.org/t/heatpumpmonitor-org-starts-starts-per-hour/26246), [Nibe SMO 40](https://www.manualslib.com/manual/1612921/Nibe-Smo-40.html?page=45), [Danfoss Icon2](https://www.manualslib.com/manual/3444694/Danfoss-Icon2.html?page=16), [SG Ready (alpha innotec)](https://www.alpha-innotec.com/en/knowledge-base/heat-pump-knowledge-center/sg-ready-interface-for-heat-pumps), [SG Ready (Kostal)](https://documents.kostal.com/PLENTICORE-G3/BA/en-GB/136335755603408651.html).
- Underfloor: [EN 1264-3 summary](https://iteh.es/catalog/standards/sist/e24888ec-0fa8-4e52-8560-8ebc95be8b93/sist-en-1264-3-2021), [KAN-therm screed protocol](https://lt.kan-therm.com/resfile/open/2605/new_KAN-therm-protokol-EN-2026_surface-heating-cooling-screed-heating.pdf), [Vaillant VRC 700 screed](https://manualshive.com/en/manual/vaillant/vrc-700-2/848955?page=18), [Rehau Nea Smart 2.0](https://www.rehau.com/downloads/383816/nea-smart-2-0-service-manual.pdf), [Uponor condensation set](https://uponor.com/en-en/product-online-catalogue/controls/controls-wired/base/uponor-base-condensation-set-s-80).
- Balancing and demand aggregation: [Danfoss auto-balancing](https://www.danfoss.com/en/about-danfoss/articles/dhs/types-of-hydronic-balancing-auto-balancing/), [Uponor Smatrix v4](https://brandportal.uponor.com/m/201ae4eebd5d084a/original/TI-Smatrix-EN-1116265-v4.pdf), [Loxone](https://www.loxone.com/enen/?p=1272), [Danfoss Icon2 controller](https://designcenter.danfoss.com/products/climate-solutions-for-heating/smart-heating/danfoss-icon2/icon2-main-controllers/danfoss-icon2-main-controller), [Heatmiser neoStat](https://manualmachine.com/heatmiser/neostate/21203534-user-manual).
