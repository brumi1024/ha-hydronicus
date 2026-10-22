# A Midea heat pump as the source, through a Shelly Modbus bridge

Status: in progress on branch `midea-source` as of 2026-10-23; not released or installed.
Done: the read-only register scan (`extras/shelly-modbus-bridge/modbus-scan.shelly.js`), and the source's `max_starts_per_hour`, `heat_sink_loops`, `start_threshold`, `health_sensor`, and loop `weight`.
Next: the owner runs the scan on the real unit, while the source fault's Repair and entity, the E8 log, and the form fields go ahead.

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

## Open question: the request while the bridge is unreachable

With the Modbus heating bit as the request, a lost broker or a stopped Home Assistant leaves the bit as it was, and the heat pump goes on heating with nobody to close or open zones.
A generic bridge cannot fix that without a rule of its own, so the owner chooses one of:

- The dry contact for heating on and off, with a Shelly `auto_off` watchdog that Hydronicus refreshes, as `docs/safety.md` describes under "Cooling while Home Assistant is not running", and Modbus only for DHW and setpoints.
- A single safety rule in the bridge: clear the heating bit after a configurable time without a heartbeat from Home Assistant, and never set it by itself.
- Accept the risk and rely on the heat pump's own protections.
