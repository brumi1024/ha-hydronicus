# Shelly Modbus bridge

A Shelly Pro with the Shelly Pro Modbus Add-on can bridge a heat pump's Modbus RTU registers to Home Assistant, where Hydronicus binds them as ordinary entities.
The bridge holds no control logic: it reads registers and, in a later phase, executes whitelisted requests from Home Assistant.
These scripts are not part of the Hydronicus release; you install them on the Shelly yourself.

## Phase 1: register scan

`modbus-scan.shelly.js` only reads.
It contains no Modbus write call, and `tests/test_extras.py` keeps it that way.
The only configuration it changes is the Shelly's own Serial component, when `configureSerial` is true.

It polls the holding registers in `CONFIG.blocks` with FC03, by default 0 to 10, 100 to 131, 200 to 246 and 255 to 260, the ones a 2018 M-Thermal controller answers, every 10 seconds, at 9600 baud 8N1 like the community setups that work on these controllers.
The table labels each register with what community register lists, such as [svenar-iot/esphome-heatpump](https://github.com/svenar-iot/esphome-heatpump), say it holds on R32 controllers; the scan exists to confirm those labels on your unit.
The first block is the health probe: three failed probes in a row turn the `Modbus healthy` component off, and the next good one turns it on.
A later block that the heat pump refuses is read one register at a time from then on, so an unsupported address only marks itself.

### Install

1. Wire the add-on to the heat pump's RS-485 terminals, and keep the Shelly the only Modbus client on the bus.
2. In the Shelly's web interface, enable the Modbus add-on and reboot if it asks.
3. Create a script, paste the whole file, and keep the `@meta` comment as its first line, since the firmware creates the `Modbus healthy` component from it.
4. Set the add-on's Serial component to **Modbus Client**, 9600 baud, 8N1, or leave `configureSerial` on and let the script set it and read the setting back; `CONFIG.serialId` is that component's instance, 100 on the devices Shelly documents.
   The console then shows `Serial 100: Modbus client, 9600 baud, 8N1`, or says that the setting did not take.
5. Leave `CONFIG.slaveId` at 0 to search for the heat pump's address, or set the address of rotary switch S3, where position 0 is reported to mean address 1.
6. Start the script and watch its console.

### Find the address

With `slaveId: 0` the script reads one register at each address from `searchFrom` to `searchTo`, 1 to 247, and reads the first address that answers.
It tries the address it found last time first, then 1, which working community setups use, then 16, which Midea's service manual gives for S3 at position 0, so a restart or a default address is found at once.
Each quiet address takes as long as the add-on waits for an answer, a few seconds, so a search through every address may take ten minutes or more; a heat pump at address 1 is found at once.
If no address answers, the console says so with the last error, and the script searches again a minute later; check the wiring, swap A and B, and check the baud rate and format.
Once the address is known, you may set it in `slaveId` to skip the search.

### Read the registers

- `http://<shelly>/script/<script id>/registers?text` shows a table: each register in decimal, hex, bits, signed, low and high byte, how often it changed, and the last error.
- `http://<shelly>/script/<script id>/registers` returns the same as JSON, with the last 40 changes.
- The console logs every change with its old and new value.

### Validate the map

Change one thing at a time on the wired controller, wait two poll cycles, and note which register moved:

1. Space heating on and off, and DHW on and off: which bits of H:0 change.
2. The zone 1 water setpoint and, if zone 2 exists, its setpoint: which byte of H:2 holds which.
3. The DHW setpoint: H:4.
4. A DHW run, a defrost, and the compressor starting: the operating state, the compressor frequency, the tank temperature T5, and anything that shows the internal pump.
5. Note register 131, which newer Midea controllers use for the controller version, and register 5, whose bit 12 shows an active weather curve on newer units.

The community map for newer Midea units and Shelly's own Midea guide already disagree on the DHW bit of H:0, bit 3 against bit 2, so trust only what the scan shows on your unit.

## Phase 2: the bridge

`midea-bridge.shelly.js` replaces the scan once the register map is confirmed.
It polls the heat pump every 10 seconds, publishes its values to Home Assistant over MQTT with discovery, at least once a minute even when nothing changed so that a steady temperature stays fresh, and executes write requests from Home Assistant.
It ships with `writesEnabled: false`, so it only reads until you change that.

### What it writes

Only these settings, each changing only its own bits:

| Setting | Register | Values |
| --- | --- | --- |
| `heating` | H:0 bit 1, zone 1 heating or cooling | `ON`, `OFF` |
| `mode` | H:1 | `Heat`, `Cool`; auto stays on the wired controller |
| `dhw` | H:0 bit 2 | `ON`, `OFF` |
| `curve_enabled` | H:5 bit 12 | `ON`, `OFF` |
| `t1s` | H:2 low byte | 25 to 50 °C while heating, 16 to 22 °C while cooling |
| `curve` | H:6 low byte | 1 to 9 |
| `t5s` | H:4 | 40 to 55 °C |

Every write reads the register first, is skipped when the value already matches, is refused within 5 minutes of the last write of the same setting unless it turns heating or DHW off, and is read back 1.5 seconds later.
Each setting is also held to `CONFIG.dailyWriteBudget` writes a day, 50 by default; a request beyond it is refused with the minutes until its day ends, and turning heating or DHW off and the handover's writes are never refused for it, though they count.
The budget exists because a Midea controller keeps a setting written over Modbus across a power cycle, so it stores it in non-volatile memory with a limited number of write cycles.
Normal control writes a setting a few times a day; the 5 minute limit alone would still let a misbehaving automation write one setting about 100,000 times a year, which the budget cuts to about 18,000.
The day of each setting begins with its first write and is stored with the write times, and a reboot keeps its count and starts it again, so a restart never frees the budget early.
The result, including a value the heat pump did not take, such as a zone 1 setpoint while the weather curve is on, is published to `<base>/write_result` and shown by the **Last write** sensor.
Anything else, a value outside its limits, and every request while Modbus is unhealthy are refused and reported.

### The handover

Home Assistant publishes to `<base>/heartbeat` at least once a minute.
If no heartbeat arrives for 10 minutes, the bridge writes the fallback settings once, publishes `<base>/handover` as `ON`, and refuses requests until a heartbeat returns.
While the heat pump is set to heat, the fallback switches zone 1 on, so the wired controller runs the heating by itself; while it is set to cool, the fallback switches zone 1 off, because the wired controller knows no dew point and must not cool unattended.
The handover counts as done only once every fallback write is confirmed, and is retried every cycle until then.
Set up the heartbeat before you enable writes, or the bridge hands over 10 minutes after it starts.
An automation like this one sends it:

```yaml
automation:
  - alias: "Heat pump bridge heartbeat"
    triggers:
      - trigger: time_pattern
        seconds: 0
    actions:
      - action: mqtt.publish
        data:
          topic: hydronicus/midea/heartbeat
          payload: "1"
```

### Install

1. In the Shelly's settings, enable MQTT with the broker Home Assistant uses and its login.
2. Stop the scan script, create a new script, and paste `midea-bridge.shelly.js`; set `CONFIG.slaveId` to the address the scan found.
3. Start it with writes off and check the **Midea heat pump** device in Home Assistant: its temperatures, mode, and switches should match the wired controller.
4. Add the heartbeat automation.
5. Only then set `writesEnabled: true`, restart the script, and try one change, such as the DHW setpoint, while you watch the wired controller.

To load a new version through the Shelly's RPC instead of pasting it, stop the script, send the code with `Script.PutCode` in chunks of raw UTF-8, read it back with `Script.GetCode`, and only then start it.
The firmware does not decode `\u` escapes, so a JSON encoder that escapes non-ASCII text turns the `°C` units into garbage.
