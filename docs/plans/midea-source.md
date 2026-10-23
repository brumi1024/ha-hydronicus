# A Midea heat pump as the source, through a Shelly Modbus bridge

Status: in progress on branch `midea-source` as of 2026-10-23; not released or installed.
Done: the read-only register scan (`extras/shelly-modbus-bridge/modbus-scan.shelly.js`), and the source's `max_starts_per_hour`, `heat_sink_loops`, `start_threshold`, `health_sensor`, and loop `weight`.
Also done: the source fault's Repair and **Fault** binary sensor, and the **Cycling protection** form section and loop **Weight** field.
Next: the owner runs the scan on the real unit; the E8 log waits, as the owner asked on 2026-10-23.

## Owner decisions

On 2026-10-23 the owner decided:

- The bridge talks to Home Assistant over MQTT with discovery, not through Shelly virtual components, so the number of registers it exposes has no limit of ten.
- A setting that Hydronicus owns and that someone changes on the wired controller is reported and adopted: Hydronicus takes the new value as its own and does not write it back.
- The source-selector valve has no position signal yet, so it stays on the heat pump while Hydronicus controls the heat pump; a position signal later becomes a condition of the request.
- The bridge scripts live in `extras/shelly-modbus-bridge/` in this repository, outside the release package.

Earlier decisions from the brief stand: the bridge holds no control logic, writes go only to a whitelist with read-modify-write on packed registers, every write is read back, and no write reaches the heat pump before the owner approves Phase 2.

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
