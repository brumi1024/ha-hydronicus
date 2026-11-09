# Heat pump adapters

Hydronicus reaches a heat pump only through ordinary Home Assistant entities: a request switch, a mode select, a supply target number, hot water controls, and feedback sensors.
An adapter turns a heat pump's own interface into those entities.
It can be a Modbus bridge, a local or cloud Wi-Fi integration, or an ESPHome device.

Adapters are not part of the Hydronicus release; each one has its own install steps.
They hold no control logic: Hydronicus decides, and the adapter reads the heat pump and carries out the writes it is asked for.

## Available adapters

| Adapter | Heat pumps | Interface |
| --- | --- | --- |
| [midea-shelly-modbus](midea-shelly-modbus/) | Midea M-Thermal and rebrands | Shelly Pro with the Modbus add-on, over MQTT discovery |

## The contract

A Plant's source binds these entities; only the request is required.

| Entity | Plant file key | Purpose |
| --- | --- | --- |
| `switch` | `request` | Asks the heat pump for space heating or cooling. |
| `select` | `mode` | Switches between heating and cooling. |
| `switch` | `weather_curve.switch` | Turns the heat pump's own weather curve on, so heating can run on it. |
| `switch` | `mode_switches` | Settings that must be on in one mode only, such as a backup heater. |
| `number` | `supply.entity` | The water supply target, in °C. |
| `switch`, `number` | `dhw.switch`, `dhw.setpoint` | Hot water on or off, and its target. |
| `binary_sensor` | `health_sensor` | On while the adapter reaches the heat pump. |
| `binary_sensor` | `handover_sensor` | On while the heat pump runs on its own controller. |
| `binary_sensor` | `running_sensor` | On while the heat pump runs. |
| `sensor` | `compressor_sensor`, `no_load` | Compressor frequency, supply and return temperatures. |

[The full example](../docs/examples/full-plant.yaml) shows each key in place.

## Writing an adapter

A good adapter:

- reports every value at least once a minute, even when it did not change, so Hydronicus can tell a steady reading from a stale one;
- reads back every write and reports a write that did not take, instead of pretending it did;
- writes only a whitelist of settings within their limits, and protects the heat pump's non-volatile memory with a write budget;
- turns its health sensor off when it loses the heat pump, which releases the request;
- hands control back to the heat pump's own controller when Home Assistant goes quiet, and reports that through its handover sensor;
- never cools on its own, since only Hydronicus watches the dew point.

Add an adapter in its own directory with a README that covers the supported models, installation, what it writes, and how it hands over, and add tests for its write rules next to [the existing ones](../tests/test_adapters.py).
