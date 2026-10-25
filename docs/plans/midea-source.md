# A Midea heat pump as the source, through a Shelly Modbus bridge

Status: in progress on branch `midea-source` as of 2026-10-23; not released or installed.
Done: the read-only register scan (`extras/shelly-modbus-bridge/modbus-scan.shelly.js`), and the source's `max_starts_per_hour`, `heat_sink_loops`, `start_threshold`, `health_sensor`, and loop `weight`.
Also done: the source fault's Repair and **Fault** binary sensor, and the **Cycling protection** form section and loop **Weight** field.
On 2026-10-25 the Phase 2 bridge runs on the owner's Pro 3EM with writes off, on the Mosquitto broker of home, and Home Assistant discovered its 21 entities, which match the wired controller.
Next: a heartbeat automation in ha-config, then writes on; the E8 log waits, as the owner asked on 2026-10-23.

## Owner decisions

On 2026-10-23 the owner decided:

- The bridge talks to Home Assistant over MQTT with discovery, not through Shelly virtual components, so the number of registers it exposes has no limit of ten.
- A setting that Hydronicus owns and that someone changes on the wired controller is reported and adopted: Hydronicus takes the new value as its own and does not write it back.
- The source-selector valve has no position signal yet, so it stays on the heat pump while Hydronicus controls the heat pump; a position signal later becomes a condition of the request.
- The bridge scripts live in `extras/shelly-modbus-bridge/` in this repository, outside the release package.

Earlier decisions from the brief stand: the bridge holds no control logic, writes go only to a whitelist with read-modify-write on packed registers, every write is read back, and no write reaches the heat pump before the owner approves Phase 2.

On 2026-10-25 the owner decided the house cools through its ceilings in summer, so the bridge switches between heat and cool (auto stays on the wired controller), limits the cooling setpoint to 16 to 22 °C, and at a handover while cooling switches zone 1 off instead of on.
Hydronicus keeps cooling disabled until it has a condensation reference; the heat pump's leaving water, `sensor.midea_heat_pump_water_outlet`, is the candidate, colder than the secondary supply and so on the safe side.

## The plant

The heat pump heats a plate heat exchanger that only the zones load, with no bypass, so the zones are its only sink and it must never run with every zone valve closed.
The plant file binds it as a source whose request is the bridge's heating switch or, if the owner chooses the dry contact, the Shelly channel that drives the interposing relay.
Its health sensor is the bridge's `modbus_healthy`, its heat sink is the living area's floor, and it limits itself to three starts an hour with a 25 minute minimum run and a 12 minute minimum rest.

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
