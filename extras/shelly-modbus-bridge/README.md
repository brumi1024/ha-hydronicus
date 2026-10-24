# Shelly Modbus bridge

A Shelly Pro with the Shelly Pro Modbus Add-on can bridge a heat pump's Modbus RTU registers to Home Assistant, where Hydronicus binds them as ordinary entities.
The bridge holds no control logic: it reads registers and, in a later phase, executes whitelisted requests from Home Assistant.
These scripts are not part of the Hydronicus release; you install them on the Shelly yourself.

## Phase 1: register scan

`modbus-scan.shelly.js` only reads.
It contains no Modbus write call, and `tests/test_extras.py` keeps it that way.
The only configuration it changes is the Shelly's own Serial component, when `configureSerial` is true.

It polls the holding registers in `CONFIG.blocks` with FC03, by default 0 to 10, 100 to 145 and 200 to 272, every 10 seconds, at 9600 baud 8N1 like the community setups that work on these controllers.
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
