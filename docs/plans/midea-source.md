# A Midea heat pump as the source, through a Shelly Modbus bridge

Status: built on branch `midea-source` as of 2026-10-25, not pushed, released, or installed; the owner decides and deploys.
Done: the read-only register scan (`extras/shelly-modbus-bridge/modbus-scan.shelly.js`), and the source's `max_starts_per_hour`, `heat_sink_loops`, `start_threshold`, `health_sensor`, and loop `weight`.
Also done: the source fault's Repair and **Fault** binary sensor, and the **Cycling protection** form section and loop **Weight** field.
On 2026-10-25 the Phase 2 bridge runs on the owner's Pro 3EM with writes off, on the Mosquitto broker of home, and Home Assistant discovered its 21 entities, which match the wired controller.
Since 2026-10-25 the bridge runs with writes on, and the heartbeat automation in ha-config keeps it from handing over.
Since then the branch carries everything [the control plan](#the-control-plan-of-2026-10-25) below needs in Hydronicus; the E8 log waits, as the owner asked on 2026-10-23.

## The control plan of 2026-10-25

This section is the plan for teaching Hydronicus to run the heat pump through the bridge.
It records what is built on this branch, what the owner decides, and what the owner measures before the Plant on home changes.
Hydronicus stays generic: everything below binds the bridge's entities as ordinary entities, and nothing in the integration speaks MQTT or Modbus.

### Decisions for the owner

1. The control strategy: hold the request after demand into bounded heat sinks, as recommended below, or release it per call.
2. How Hydronicus learns that the fireplace's buffer supplies the zones: `input_boolean.home_fireplace_heating` by hand for now, which ha-config must create first, and a direct signal later; see section 8.
3. The request backend: the bridge's `switch.midea_heat_pump_space_heating`, recommended, or a dry contact through a Pro 4PM or Pro 2PM channel and an interposing relay.
4. Whether to switch the weather curve off, for a fixed cooling setpoint and later for Hydronicus's own heating supply control; until then T1S stays controller-owned.
5. Whether the E8 event log is built now; it stays deferred, as decided on 2026-10-23.
6. Whether to add a secondary supply sensor before cooling goes live, recommended, and whether ceiling surface sensors are worth it, not recommended yet.

### Measurements the owner takes first

- Whether the internal pump keeps running while the compressor rests on its curve: watch `binary_sensor.midea_heat_pump_internal_pump` while `sensor.midea_heat_pump_compressor_frequency` drops to 0 with space heating on.
  The recommended strategy depends on it, see below.
- Whether the controller accepts a zone 1 setpoint while it cools with the weather curve on: set the mode to cool on a warm day and write 20 °C to `number.midea_heat_pump_zone_1_water_setpoint`, then read `sensor.midea_heat_pump_last_write`.
- The Y-strainer, the air vent, and the internal pump on the primary side.
  E8 is a water flow failure that the flow switch reports when the internal pump starts and no flow follows; after a restart from standstill it points at a strainer that is clogging, air, or a pump that is slow to start, which a service visit fixes and no control strategy does.
  Fewer restarts lower the exposure; they do not remove the cause.
  A second E8 on 2026-10-25 at 01:10 UTC came after a DHW run with no heating toggle: the compressor stopped at 01:06, the internal pump stopped by itself at 01:08, and the fault followed its restart; so the heat pump restarts its own pump too, and no strategy of Hydronicus's can prevent those restarts.

### 1. The control strategy

Every release of the space heating request stops the compressor and both pumps, and the next start restarts the internal pump from standstill, the moment E8 struck on 2026-10-24.
The heat pump heats a plate heat exchanger with no bypass, so it must also never run while no loop carries the secondary water away.
Three strategies were compared on the same simulated house:

- **a. Request per call:** Hydronicus switches space heating with the zones' demand, protected by `min_on`, `min_off`, and `max_starts_per_hour`, with the floor as the heat sink for the rest of the minimum run.
- **b. Always on:** space heating stays on and the heat pump heats on its own curve; Hydronicus only keeps a heat sink open whenever no zone calls, and switches heating off only for long idle periods.
- **c. Hybrid, recommended:** the request starts with demand as in a, and once demand ends it is held for up to `hold_after_demand` into the heat sink loops, each of which takes heat only while its zone is less than `heat_sink_overshoot` over its heating target.
  When no heat sink has room, or the hold ends, the request is released.

The simulator in `tests/sim/heat_pump.py` models the house's rooms, the four loops' emitters, the secondary water, the plate heat exchanger, and the heat pump: its internal pump, its compressor modulating between 5 and 12 kW to hold its curve, a stop 2 K over the curve and a start 2 K under it, and the measured 3 minute restart delay.
Its numbers are sized for the house but are assumptions, so the table compares strategies with each other and predicts no absolute energy use.
`uv run python -m tests.sim.heat_pump_strategies` prints it; each row is two days after a six-hour warm-up with a daily outdoor swing of 3 K, and digital thermostats at their defaults.

| Strategy | Outdoor °C | Requests/day | Pump starts/day | Compressor starts/day | Mean run, min | Heating into closed valves, min/day | Overheat, K h/day | Warmest room, °C |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| today: no source | -3 | 0.0 | 0.0 | 21.5 | 53 | 10 | 0.0 | 21.2 |
| a: request per call | -3 | 10.0 | 10.0 | 17.0 | 68 | 0 | 0.0 | 21.2 |
| a: rest 30 min, 2 starts/h | -3 | 9.0 | 9.0 | 17.0 | 68 | 0 | 0.0 | 21.2 |
| b: always on, floor sink | -3 | 0.0 | 0.0 | 16.5 | 77 | 0 | 0.0 | 21.2 |
| c: hold 4 h, floor, +0.5 K | -3 | 0.0 | 0.0 | 16.5 | 77 | 0 | 0.0 | 21.2 |
| c: hold 4 h, all loops, +0.5 K | -3 | 4.0 | 4.0 | 9.0 | 126 | 0 | 0.1 | 21.6 |
| today: no source | 7 | 0.0 | 0.0 | 49.5 | 17 | 25 | 0.0 | 21.2 |
| a: request per call | 7 | 13.5 | 13.5 | 44.5 | 19 | 0 | 0.0 | 21.2 |
| a: rest 30 min, 2 starts/h | 7 | 11.0 | 11.0 | 34.5 | 24 | 0 | 0.0 | 21.2 |
| b: always on, floor sink | 7 | 1.0 | 1.0 | 63.0 | 18 | 0 | 19.1 | 23.4 |
| c: hold 4 h, floor, +0.5 K | 7 | 4.5 | 4.5 | 49.5 | 21 | 0 | 0.2 | 21.6 |
| c: hold 4 h, all loops, +0.5 K | 7 | 5.5 | 5.5 | 24.5 | 32 | 0 | 0.3 | 21.6 |
| today: no source | 12 | 0.0 | 0.0 | 64.0 | 9 | 29 | 0.0 | 21.3 |
| a: request per call | 12 | 12.5 | 12.5 | 45.5 | 12 | 0 | 0.0 | 21.3 |
| a: rest 30 min, 2 starts/h | 12 | 10.5 | 10.5 | 49.0 | 11 | 0 | 0.0 | 21.2 |
| b: always on, floor sink | 12 | 0.0 | 0.0 | 101.0 | 8 | 0 | 53.4 | 24.5 |
| c: hold 4 h, floor, +0.5 K | 12 | 7.5 | 7.5 | 57.0 | 11 | 0 | 0.7 | 21.8 |
| c: hold 4 h, all loops, +0.5 K | 12 | 4.5 | 4.5 | 31.5 | 16 | 0 | 0.4 | 21.6 |

Pump starts count the internal pump starting from standstill, the E8 exposure; requests count the space heating request turning on; overheat sums the kelvin-hours each room spends more than 0.5 K over its target.
What the table shows:

- Today, without a source, the heat pump heats into closed valves for 10 to 29 minutes a day whenever every zone is satisfied, and short cycles most in mild weather, the pattern this work exists to end.
- Request per call ends that, but restarts the internal pump 10 to 14 times a day; a longer rest and fewer starts per hour barely help, because the zones call again soon after they are satisfied.
- Always on restarts the pump almost never, but a floor that takes the heat pump's minimum output for hours overheats the living area by 2.4 to 3.2 K, and with every loop open the comfort rests entirely on the curve.
- The hybrid with every heating loop as a heat sink and a 0.5 K overshoot restarts the pump 4 to 5.5 times a day in every weather, about 60 percent fewer than request per call, halves the compressor's starts against today, and keeps every room within 0.6 K of its target.
  The floor alone as the sink restarts less in deep cold but more in mild weather, which is most of the season, and short cycles the compressor as much as today.
  A longer hold changes nothing, since the sinks fill within the hour; a larger overshoot buys a start a day for over 4 K h of overheat.

If the internal pump stops whenever the compressor rests on its curve, every compressor start is a pump start, and the hybrid cuts requests but not pump starts:

| Strategy | Outdoor °C | Requests/day | Pump starts/day | Compressor starts/day |
| --- | --- | --- | --- | --- |
| a, pump stops in thermo-off | 7 | 8.5 | 16.5 | 16.5 |
| c floor, pump stops in thermo-off | 7 | 1.5 | 14.5 | 14.5 |

So the first measurement decides it: with a pump that runs through the compressor's rests, the hybrid is clearly better; with one that stops, the E8 exposure is the heat pump's own cycling, which longer compressor runs, that is fewer open loops and a lower curve, reduce, and the strategy matters less than the service visit.

Recommendation: the hybrid, with these defaults for the house, which `HOME_HEAT_PUMP` in `tests/sim/plants.py` runs with the zones' sensors and thermostats of the simulator:

```yaml
mode_dwell: 7200
source:
  request: switch.midea_heat_pump_space_heating
  mode: {entity: select.midea_heat_pump_mode, heat: Heat, cool: Cool}
  post_run: 0
  min_on: 1500
  min_off: 720
  max_starts_per_hour: 3
  heat_sink_loops: [living_area.floor, living_area.ceiling, basement.ceiling, bedroom_area.ceiling]
  hold_after_demand: 14400
  heat_sink_overshoot: 0.5
  health_sensor: binary_sensor.midea_heat_pump_modbus_healthy
  handover_sensor: binary_sensor.midea_heat_pump_handover_to_controller
  write_interval: 300
  inhibit_sensor: input_boolean.home_fireplace_heating
  no_load:
    supply_temperature: sensor.midea_heat_pump_water_outlet
    return_temperature: sensor.midea_heat_pump_water_inlet
    compressor_sensor: sensor.midea_heat_pump_compressor_frequency
  compressor_sensor: sensor.midea_heat_pump_compressor_frequency
  supply:
    entity: number.midea_heat_pump_zone_1_water_setpoint
    modes: [cool]
    cool_temperature: 18
    minimum: 16
    maximum: 22
    step: 1
  dhw:
    switch: switch.midea_heat_pump_dhw
    setpoint: number.midea_heat_pump_dhw_setpoint
    minimum: 40
    maximum: 55
    step: 1
    max_boost: 10800
pumps:
  heat_pump: {driven_by: source, min_flow: guaranteed}
  heating:
    switch: switch.home_underfloor_heating_pump
    overrun: 240
    supply_temperature: sensor.midea_heat_pump_water_outlet
```

The ceilings get `modes: [heat, cool]`, the floor stays heat only, and each zone gets `max_humidity: 65`; the towel dryer loop stays as it is today.

`min_off` stays above the bridge's 5 minute write limit, so turning heating back on is never refused, and `min_on` keeps each run long enough for the defrost and the oil return the compressor needs.
The heat sink loops are listed in the order the owner prefers them; all of them take heat while their zones have room.

### 2. Binding the source to the bridge

The source binds `switch.midea_heat_pump_space_heating` as its request.
The dry contact through a Pro 4PM or Pro 2PM channel and an interposing relay remains possible and needs no change in Hydronicus, since it is also a switch, but it loses the bridge's read-back and its refusal reasons, and the wired controller's own on and off would then fight the contact; the bridge's switch is recommended.

- `health_sensor` is `binary_sensor.midea_heat_pump_modbus_healthy`: a lost Shelly, broker, or Modbus link releases the request at once and keeps it off.
  An E8 or E0 does not: the link stays healthy, and switching heating off and on during an E8 would only restart the pump again, so the request stays and the heat pump's own retry runs; `binary_sensor.midea_heat_pump_alarm` shows the fault.
- The internal circulator joins the Plant as a source-driven pump with guaranteed flow and no loops: the plate heat exchanger gives it flow whatever the valves do.
  A source-driven pump with guaranteed flow normally means a separator that also absorbs the heat; one without loops does not, so the request found on with no open path is still reported for it.
  Its running sensor, `binary_sensor.midea_heat_pump_internal_pump`, is bound only once the owner has measured that it stays on through the compressor's rests, since a running sensor that drops would release the request.
- The new `handover_sensor` reads on while something else controls the source: Hydronicus then sends the source nothing, treats it as possibly running, and keeps its heat sink loops open while it may heat; see section 4.

`HOME_HEAT_PUMP` in `tests/sim/plants.py` is that Plant with the bridge's entity IDs, and the scenarios in `tests/sim/test_home_heat_pump.py`, `test_home_heat_pump_cooling.py`, and `test_home_heat_pump_dhw.py` run it.

### 3. DHW and setpoints

The source gets an optional `dhw` section: a switch, a setpoint number, its hard limits, and a boost.
Each setting has one owner by the decision of 2026-10-23: Hydronicus owns the DHW switch and T5S, and a change on the wired controller is reported and adopted as Hydronicus's own value, never written back.

- Hydronicus publishes a **DHW** switch and a **DHW target** number, whose values are the owned ones; the owner changes them there or on the wired controller.
- An owned target outside `minimum` and `maximum`, 40 and 55 °C here, is clamped and logged, including a value adopted from the wired controller, since a hard limit protects the tank and the heat pump.
- A boost, through the `hydronicus.boost_dhw` action with a temperature and a duration, raises T5S within the limits for at most `boost.max_duration` and then restores the owned target.
  The boost's end and the target to restore are persisted with the Plant's state, so a restart restores it at the right time and a lost link restores it once the setpoint is available again.
  A change on the wired controller during a boost ends the boost without restoring, since the owner has just chosen a value.
  A PV surplus automation calls the action when surplus starts and lets the duration bound it.
- While the handover sensor reads on, the controller owns every setting and Hydronicus sends none; the values it changed are adopted when the handover ends.
- T1S, the zone 1 setpoint, stays controller-owned while the weather curve is on, because the controller refuses it; Hydronicus binds it only for cooling, see section 6.

### 4. Tolerating the bridge

The bridge refuses a write within 5 minutes of the same setting's last write, unless it turns heating or DHW off, and shows a refusal or an ignored value only in `sensor.midea_heat_pump_last_write`.

- The source's new `write_interval` keeps Hydronicus from writing a source output, the DHW outputs included, sooner than that after its last write to it, except a switch turning off.
  The reconciler then retries such an output no faster than the interval, so three refusals take 10 minutes, not 70 seconds, before the output's Repair.
- A write that is still not taken after those attempts becomes a status: the reconciler keeps the output's Repair and sends it again only after an hour, or as soon as the target or the output's state changes.
  A switch turning off is never held.
- A supply setpoint that changes only within its tolerance or within the write interval is held at its observed value; cooling's safety does not depend on that write, since the request is released while the observed setpoint is below what the dew point needs.
- While the handover sensor reads on, the bridge refuses everything, so Hydronicus sends the source nothing and raises no Repair for it.
  In heating the wired controller switches zone 1 on: Hydronicus treats the source as possibly running and keeps its heat sink loops open while the request shows on or unknown.
  In cooling it switches zone 1 off, and Hydronicus closes the cooling loops as it would after any release.
  When the heartbeat returns and the sensor reads off, Hydronicus takes over from the observed state, as after a restart.
- Until the bridge fix of 2026-10-25 is loaded on the Shelly, a bridge restart publishes one state in which every switch reads off for about a second.
  Hydronicus then counts a stop and a start of the request, which restarts its minimum run and adds to its starts per hour, and adopts the DHW switch as off and on again with two log lines; it sends no harmful write, because the bridge skips a write that changes nothing.
  Loading the fix removes it; Hydronicus adds no debounce of its own.

### 5. Diagnostics

The source's optional `compressor_sensor` is a numeric sensor that reads above zero while the compressor runs, here `sensor.midea_heat_pump_compressor_frequency`.
Hydronicus then publishes **Compressor starts**, the starts within the last hour, and **Compressor cycle**, the mean length of the runs that ended within the last 24 hours, counted from that sensor's readings at each evaluation and kept with the Plant's state.
The E8 and E0 event log, with the time, the activity before, the time since the last DHW run, the time since the internal pump last started, Tw_in, Tw_out, and the compressor frequency, is proposed as a diagnostics entry that keeps the last 20 faults; it is not built until the owner asks.

### 6. Cooling

The ceilings of the basement, the living area, and the bedroom area cool; the living area's floor stays heat only.
Floor cooling would add little capacity next to the ceilings, has no surface sensor for its 20 °C surface minimum, and puts any condensation where people walk.

- `select.midea_heat_pump_mode` is the source's mode select, heat `Heat` and cool `Cool`.
- `number.midea_heat_pump_zone_1_water_setpoint` is the source's supply setpoint, for cooling only through the new `supply.modes: [cool]`, with `cool_temperature: 18`, `minimum: 16`, and `maximum: 22`.
  Hydronicus proposes a cooling setpoint only once the mode select shows cool, since the bridge accepts 16 to 22 °C only then.
  With the weather curve on, the controller may refuse it; that is the owner's measurement above, and the write becomes a status, not a retry loop.
- `sensor.midea_heat_pump_water_outlet`, Tw_out, is the switched heating pump's `supply_temperature`, the condensation reference of every ceiling loop.

What Tw_out does not cover, plainly:

- It reads the primary loop, the heat pump's leaving water before the plate heat exchanger; the secondary supply that reaches the ceilings is a little warmer, by the exchanger's approach and the pipes' gains, so the guard errs on the safe side.
- It is meaningful only while the internal pump runs; while it rests, Tw_out reads standing water that warms toward the plant room, while no cooling reaches the secondary either, so it overstates the supply temperature exactly when nothing is cooled.
- It is no surface temperature: it says nothing about a ceiling panel that a cold supply has cooled below the dew point locally, which the 2 K margin and the release band cover only as margins.

Recommendation: add one secondary supply sensor, a clip-on probe on the flow pipe after the heating pump through a Shelly add-on, before cooling goes live; it reads the water that reaches the ceilings, whenever the heating pump runs, independent of the heat pump's pump.
It replaces Tw_out as the pump's `supply_temperature`.
Ceiling surface sensors are not worth it while the supply stays 3.5 K or more above the worst-case dew point, which the supply control already enforces; reconsider them if the ceilings ever run closer.
Each zone's areas name their humidity sensors, which stay required for cooling: a zone without a usable humidity reading blocks its ceiling's cooling.

Defaults for the house: `mode_dwell: 7200`, so a change between heating and cooling waits two hours after the old mode's flow; each zone's `max_humidity: 65`, five points under the default, since ceilings condense first; and the guard's fixed 2 K margin and 1 K release above the worst-case dew point.
The simulated summer day in `tests/sim/test_home_heat_pump_cooling.py` covers a humid afternoon that raises the cooling setpoint and then blocks a ceiling, Tw_out going stale, the bridge's handover while cooling, and a change of mode.

### 7. Exercise, Dry run, and the simulator

The exercise never requests the source and keeps its own heat sink rules; Dry run proposes the DHW outputs like every other output and never sends them.
The simulator's world now models the heat pump's own pump, its restart delay, and an E8 after a pump start from standstill, through `HeatPumpHouse` in `tests/sim/heat_pump.py`.

### 8. The fireplace's buffer

The water-jacket fireplace heats a 2000 L buffer, and its own thermostat drives a motorized selector valve so that the zones run from the buffer instead of the plate heat exchanger.
That thermostat stays the authority, and Hydronicus never commands the valve; with the buffer selected the heat pump has no load, so its request must be released at once and stay off.

- The source's new `inhibit_sensor`, a `binary_sensor` or an `input_boolean`, reads on while another source supplies the zones.
  The request is then released at once, whatever its minimum run, with the reason "another source supplies the zones", no fault, and no Repair; the zones and the heating pump go on serving demand from the buffer, and the DHW is unaffected.
  Unknown or unavailable counts as off, so a helper that does not exist yet never keeps the heat pump off; it does raise the missing binding Repair, so ha-config must create `input_boolean.home_fireplace_heating` before the Plant binds it.
- A direct signal is better than a switch someone must remember to flip: a contact sensor on the selector valve's position indicator, a Shelly input on the valve motor's drive, or a probe at the top of the buffer compared with the thermostat's setpoint, in that order of preference, since the first two read the valve itself.
- The new `no_load` guard is the safety net whatever the inhibit says: once the request is on, the compressor has run for 10 minutes, and Tw_out and Tw_in have stayed within 1 K for 10 minutes too, the heat has nowhere to go, the buffer selected, every valve closed, a failed pump, or air, and Hydronicus releases the request and holds it off for 30 minutes.
  A missing or stale reading never trips it, and two trips within a day raise the `source_no_load` Repair.
  The heat pump's low ΔT has been the owner's only hint that the fireplace heats; it is a fair guard, but too slow and too weak to control on, which is why the inhibit exists.

### Build order on this branch

1. `hold_after_demand` and `heat_sink_overshoot`, with the strategy comparison.
2. The handover sensor, and a request found on with no open loop reported even behind a separator.
3. `write_interval`, and a write the bridge does not take becoming a status that is retried hourly.
4. Cooling: `supply.modes` and `supply.step`, the wait for the mode select, and the summer day.
5. DHW: switch, target, limits, adoption, and the boost with its restore.
6. The inhibit and the no-load guard.
7. The compressor diagnostics.

All seven are built, with core, simulator, and integration tests, and `make verify` passes.
The new source settings are plant file keys; only the hold, the overshoot, and the handover sensor are in the **Cycling protection** form so far.

### The owner's steps

1. The measurements above, and the primary circuit's service.
2. In ha-config, create `input_boolean.home_fireplace_heating`.
3. Decide the open points at the top, then release a Hydronicus version with this branch.
4. Edit the Plant on home from the snippet above, arm the new outputs one by one while watching **Last write**, and keep Control equipment off for a Dry run day first.

Deploying a Hydronicus version and editing the Plant on home are the owner's steps; nothing on this branch arms an output, writes to the heat pump, or changes the live Plant.
The DHW switch write through the bridge at 01:24 UTC on 2026-10-25 came from neither the bridge session nor this one, since this work only ran the simulator and tests.

## Owner decisions

On 2026-10-23 the owner decided:

- The bridge talks to Home Assistant over MQTT with discovery, not through Shelly virtual components, so the number of registers it exposes has no limit of ten.
- A setting that Hydronicus owns and that someone changes on the wired controller is reported and adopted: Hydronicus takes the new value as its own and does not write it back.
- The source-selector valve has no position signal yet, so it stays on the heat pump while Hydronicus controls the heat pump; a position signal later becomes a condition of the request.
  On 2026-10-25 the owner described it: a thermostat drives the motorized valve to the buffer while the water-jacket fireplace has heated it, and that thermostat stays the authority; Hydronicus gets a source inhibit input from the valve's position and never commands the valve.
- The bridge scripts live in `extras/shelly-modbus-bridge/` in this repository, outside the release package.

Earlier decisions from the brief stand: the bridge holds no control logic, writes go only to a whitelist with read-modify-write on packed registers, every write is read back, and no write reaches the heat pump before the owner approves Phase 2.

On 2026-10-25 the owner decided the house cools through its ceilings in summer, so the bridge switches between heat and cool (auto stays on the wired controller), limits the cooling setpoint to 16 to 22 °C, and at a handover while cooling switches zone 1 off instead of on.
Hydronicus keeps cooling disabled until it has a condensation reference; the heat pump's leaving water, `sensor.midea_heat_pump_water_outlet`, is the candidate, colder than the secondary supply and so on the safe side.

## The plant

The heat pump heats a plate heat exchanger that only the zones load, with no bypass, so the zones are its only sink and it must never run with every zone valve closed.
The plant file binds it as a source whose request is the bridge's heating switch or, if the owner chooses the dry contact, the Shelly channel that drives the interposing relay.
Its health sensor is the bridge's `modbus_healthy`, and its heat sinks, its hold after demand, and its limits are those of [the control plan](#1-the-control-strategy).

## The MQTT contract of the bridge

The Shelly's own MQTT connection goes to the broker that Zigbee2MQTT already uses on home; the owner enters its address and credentials in the Shelly's settings, never in the script.
The script uses `MQTT.publish`, `MQTT.subscribe`, and `MQTT.setConnectHandler` from the Shelly script API, which allows ten subscriptions per script.

| Topic | Direction | Content |
| --- | --- | --- |
| `<base>/modbus_healthy` | bridge to HA, retained | `ON` or `OFF`. |
| `<base>/state` | bridge to HA, retained | One JSON object of every mapped value, published when a value changes. |
| `<base>/set/<name>` | HA to bridge | A requested value for one whitelisted name: `heating`, `dhw`, `t1s`, or `t5s`. |
| `<base>/write_result` | bridge to HA | `{name, requested, read_back, ok, reason}` after every write or refusal. |
| `<base>/registers` | bridge to HA, retained | The raw register table, for diagnostics. |
| `homeassistant/<component>/<node>/<object>/config` | bridge to HA, retained | Discovery for each entity, published on every connect. |

Every discovered entity lists two availability topics with `availability_mode: all`: the Shelly's own `online` topic, which its broker connection keeps, and `<base>/modbus_healthy`.
So a lost Shelly, a lost broker, and a lost Modbus link all make the entities unavailable, and the health sensor makes Hydronicus release the request.
`<base>` is a script setting, `hydronicus/midea` by default.

## Ownership by adoption

Each setting the bridge exposes has one owner, `hydronicus` or `controller`.
A controller-owned setting is only read and shown.
For a Hydronicus-owned setting, a value change that Hydronicus did not command is reported as an event and in the setting's status, and becomes Hydronicus's value from then on.
A change during a DHW boost ends the boost without restoring the previous value, since the owner has just chosen one.

## Handover to the wired controller

On 2026-10-23 the owner decided that while Home Assistant is gone, the wired controller runs the heat pump by itself, as it did before Hydronicus.
The heat pump then heats on its own weather curve whenever its controller says so, which is only safe while it has a sink, so the handover has two halves.

- The bridge restores each whitelisted setting to its configured fallback value, the heating bit on by default, once it has heard no heartbeat from Home Assistant for a configurable time, 10 minutes by default so that a restart does not trigger it.
  It then writes nothing more until a heartbeat returns, and it publishes `<base>/handover` as `ON` so that Hydronicus does not adopt those writes as the owner's changes.
  This is the bridge's one rule of its own, and it only ever hands control back, never takes it.
- The Pro 4PM and Pro 2PM that switch the valves and pumps open the living area's floor and ceiling valves and run the secondary pump once they too have heard no heartbeat for that time, through a small script of their own.
  The owner chose those two loops on 2026-10-23; the basement and bedroom ceilings stay as they are, and the script leaves every channel it does not name alone.
  Without that half the heat pump would heat into closed valves, the short cycling this work exists to prevent.

When Home Assistant returns, its heartbeat ends the handover, the bridge clears `<base>/handover`, and Hydronicus takes over from the observed state like after any restart: the open valves and the running pump stay until its usual sequence closes what no zone needs.
The settings the controller changed meanwhile are adopted, since the controller owned them during the handover.
A Shelly that loses power keeps the valves closed, since they are normally closed, and the heat pump's own protections remain the last layer.

The scan must confirm that the heating bit and the wired controller's own on and off are the same state, which is what makes restoring the bit a handover rather than a command.

## The owner's unit on the bus

On 2026-10-24 the controller answered at Modbus address 16, rotary switch S3 at position 0 as Midea's service manual gives, at 9600 baud 8N1.
It needs the wired controller's E as signal ground besides A to H2 and B to H1; house protective earth instead of E made the add-on hang.
It answers holding registers 0 to 10, 100 to 131, 200 to 246, and 255 to 260, and refuses a read that spans any other address with exception 2.

A first read while the heat pump heated, before any toggle confirmed a bit:

| Register | Value | Reading |
| --- | --- | --- |
| H:0 | 2 | Bit 1 on, which the community map calls zone 1 water control; neither DHW candidate bit, 2 or 3, is on. |
| H:1 | 3 | Heat. |
| H:2 | 34 | T1S zone 1 34 °C in the low byte, zone 2 0. |
| H:4 | 50 | T5S 50 °C. |
| H:5 | 4096 | Bit 12 on, an active weather curve on newer units, which matches the owner's setup. |
| H:6 | 5 | Weather curve 5 for zone 1. |
| H:100 | 35 | Compressor frequency. |
| H:101 | 3 | Operating mode heat. |
| H:104, H:105 | 30, 34 | Tw_in and Tw_out, 4 K apart. |
| H:107 | 7 | Outdoor temperature T4. |
| H:115 | 38 | DHW tank T5. |
| H:124 | 0 | No fault; E0 reads 1 and E8 reads 9 per the service manual. |
| H:129 | 8776 | Bits 3, 6, 9, and 13: internal pump, external pump, SV3, and run. |
| H:130, H:131 | 24, 28 | Software and wired controller versions. |
| H:203, H:204 | 55, 25 | The controller's own T1S heating limits for zone 1. |
| H:207, H:208 | 60, 40 | The controller's own DHW setpoint limits, so the plan's 35 °C lower limit for T5S is below what the unit accepts. |

Toggling on the wired controller on 2026-10-24 confirmed:

- DHW on and off sets and clears bit 2 of H:0 (2 to 6 and back), as Shelly's guide says; the community map's bit 3 is wrong for this unit, and bit 2 is not zone 2.
- H:4 is T5S in whole degrees: an accidental step down to 49 °C and back showed at once.
- Space heating off and on clears and sets bit 1 of H:0 (2 to 0 and back), and the operating mode, H:101, follows within about four seconds, 3 to 0 and back, so H:101 0 is standby.
- Turning space heating off stops the compressor and both pumps (bits 3 and 6 of H:129 cleared), so every off and on costs a compressor start.
- The wired controller refuses a manual zone 1 setpoint while the weather curve is on, so T1S, the low byte of H:2, stays controller-owned in this setup unless the curve is switched off.
- A live E8 confirmed the fault encoding: H:124 and H:125 read 9 and bit 12 of H:129 (alarm) set, about four minutes after a heating off and on had stopped the internal pump, which is the pattern the owner suspected.

A DHW run on 2026-10-25 showed that the operating mode, H:101, does not name DHW on this controller: it went from 3 to 0 for the switchover and back to 3 for the run, while SV1 (bit 4 of H:129, the valve to the tank coil) turned on and the external pump off.
The bridge's **Activity** sensor therefore reads fault, defrost, standby, dhw, heating, or cooling from H:124, H:128, H:101, and SV1 together.

The community map adds two writable settings that this unit reports: bit 12 of H:5 switches the zone 1 weather curve on and off (it reads on), and the low byte of H:6 selects the zone 1 curve, 1 to 9 (it reads 5), with zone 2 in the high byte.
Neither has been written yet.
On 2026-10-24 the owner decided both join the Phase 2 write whitelist: bit 12 of H:5 and the low byte of H:6, each with read-modify-write, writes only on change, the rate limit, and a read-back.
Switching the curve off hands T1S to Hydronicus's supply temperature control, which is a separate decision taken when that control is set up.

Compressor target frequency, water flow, and energy, H:132 onwards, do not exist on this unit, so the E8 log uses H:100 for compressor frequency and bit 3 of H:129 for the internal pump.
