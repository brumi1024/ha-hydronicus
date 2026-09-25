<p align="center">
  <img src="custom_components/hydronicus/brand/icon@2x.png" alt="Hydronicus" width="220">
</p>

<h1 align="center">Hydronicus</h1>

<p align="center">
  <strong>One plant. Many zones. No valve fights.</strong>
</p>

Hydronicus is a Home Assistant custom integration that coordinates a hydronic heating and cooling plant: the valves, the pumps, and the heat pump or boiler behind them.
You describe the plant once, as zones with their loops, and Hydronicus decides from what it observes which valves should be open, which pumps should run, and when to ask the source for heat or cooling.
It then drives those outputs in the right order and checks that each one got there.

## What it does

- A Plant has an optional source, such as an air-to-water heat pump, reached through a request switch and an optional mode select.
- Pumps are switched by Hydronicus, or driven by the source itself, such as a heat pump's own circulator, which Hydronicus never commands.
- A zone is the space one thermostat controls.
  It can cover Home Assistant areas and follow the temperature and humidity sensors those areas name.
  Its thermostat is a digital thermostat that Hydronicus provides, or an existing climate entity that Hydronicus only reads.
- A loop is a flow path of a zone: zero or more valves that open together and one pump.
  A loop without a valve is fine, and a loop that no zone owns, such as a towel dryer or a loop several zones share, is a plant loop.
- Heating and cooling share the same loops, the Plant mode chooses between them, and a change of mode is sequenced with a dwell.
- Every loop that cools is guarded against condensation with the zone's worst-case dew point.
- Valves open before pumps start, pumps run before the source is asked, and it all stops in reverse, with pump overrun and source post-run.
- A pump that needs an open loop always has one while it may run.
- A command counts as done only when Home Assistant shows its result; otherwise it is retried, and a Repair names the output that does not respond.
- Reloads and restarts send no command and continue every timer.
- Hydronicus commands only the outputs you arm, and only while **Control equipment** is on; otherwise it runs in Dry run and shows what it would do.

Read [how Hydronicus works](docs/how-it-works.md) for the details, and [the reference plant](docs/examples/reference-plant.yaml) for a complete example.

## Installation

Hydronicus is installed as a HACS custom repository.
Use a disposable or staging Home Assistant instance for a first evaluation.

1. Open HACS, open its menu, and choose **Custom repositories**.
2. Add `https://github.com/brumi1024/ha-hydronicus` with **Integration** as the type.
3. Install Hydronicus from HACS and restart Home Assistant.
4. Open **Settings > Devices & services**, choose **Add integration**, and search for **Hydronicus**.

The minimum Home Assistant version declared by this repository is `2026.9.0`.
A Plant set up with version 0.1.0 has to be set up again; see [upgrade and rollback](docs/upgrade-and-rollback.md).

## First simulated Plant

The trial kit in [docs/examples/trial](docs/examples/trial) builds a small Plant on synthetic entities, so you can watch Hydronicus work without equipment:

- [package.yaml](docs/examples/trial/package.yaml) is a Home Assistant package with synthetic entities for two zones and one pump.
- [plant.yaml](docs/examples/trial/plant.yaml) is a plant file bound to those entities.
- [plant-areas.yaml](docs/examples/trial/plant-areas.yaml) is the same Plant with zones that follow two Home Assistant areas instead of naming their sensors.

Each zone gets a temperature sensor driven by an `input_number`, and each valve and the pump is a template switch backed by an `input_boolean`.
Because every output is backed by a helper, the helper's history shows every command that reached it.

### Load the trial package

1. Copy `docs/examples/trial/package.yaml` to `packages/hydronicus_trial.yaml` in the Home Assistant configuration directory.
2. Add the package to `configuration.yaml`:

   ```yaml
   homeassistant:
     packages:
       hydronicus_trial: !include packages/hydronicus_trial.yaml
   ```

3. Restart Home Assistant.

The package creates `sensor.hydronicus_trial_living_room_temperature`, `sensor.hydronicus_trial_bedroom_temperature`, `switch.hydronicus_trial_living_room_valve`, `switch.hydronicus_trial_bedroom_valve`, and `switch.hydronicus_trial_pump`.
Both zone temperatures start at 21 °C.
See [Home Assistant's packages documentation](https://www.home-assistant.io/docs/configuration/packages/) if your configuration already uses packages.

### Create the Plant

Open **Settings > Devices & services > Add integration** and search for **Hydronicus**.
Import the trial plant file, or build the same Plant with guided setup; both give the same entity IDs.

To import the plant file, choose **Import a plant file**, paste `docs/examples/trial/plant.yaml` into **Plant file**, and submit.

To use guided setup, choose **Guided setup**:

1. In **The Plant and its source**, enter `Trial plant` as the **Plant name**, leave the **Source request switch** empty, and submit.
2. In **Pump**, enter `Circulation pump` as the **Pump name**, choose `switch.hydronicus_trial_pump` as the **Pump switch**, and submit.
3. In **How is your home zoned?**, choose **Zones without areas**.
4. In **Add a zone**, enter `Living room` as the **Zone name**, choose `sensor.hydronicus_trial_living_room_temperature` under **Extra temperature sensors**, and submit.
5. In the loop form, enter `Floor` as the **Loop name**, choose `switch.hydronicus_trial_living_room_valve` under **Valves** and the circulation pump as the **Pump**, and submit.
6. Choose **Add another zone**, and add `Bedroom` the same way with its sensor and its valve.
7. Choose **Continue**, then **Continue** again in **Plant loops**.

**Review the Plant** lists the two zones, each with its loop, and the pump.
Submit it to create the Plant.

### Follow Home Assistant areas

A zone can cover Home Assistant areas and follow the temperature sensor each area names, so a sensor is chosen once, in the area settings.
A package cannot create areas, so this variant starts in the UI:

1. Open **Settings > Areas, labels & zones** and create the areas `Living room` and `Bedroom`.
2. Open `sensor.hydronicus_trial_living_room_temperature`, open its settings, set its **Area** to `Living room`, and save.
   Do the same for `sensor.hydronicus_trial_bedroom_temperature` and `Bedroom`.
   The area settings offer only the sensors that belong to the area, which is why this step comes first.
3. Open the `Living room` area, choose **Area settings** in its menu, choose the trial living room temperature as its **Temperature sensor**, and save.
   Do the same for `Bedroom`.

Then import [plant-areas.yaml](docs/examples/trial/plant-areas.yaml), or use guided setup with **One zone per area**: keep both areas in **Choose the areas**, and each **Add a zone** form comes filled in with its area, whose name the zone takes when **Zone name** stays empty, so only the loop is left to add.
Each zone's thermostat, `climate.bedroom` and `climate.living_room`, is placed in its area.
The **Combined temperature** sensor of each zone lists its area and the sensor it follows in its `areas` attribute, and choosing another sensor in the area settings takes effect at once.

### Watch it in Dry run

The new Plant, `Trial plant`, has the **Mode** select `select.trial_plant_mode`, the **Control equipment** switch `switch.trial_plant_control_equipment`, and the **Status** sensor `sensor.trial_plant_status`.
Each zone has a thermostat, such as `climate.bedroom`, and a loop flowing sensor, such as `binary_sensor.bedroom_floor_flowing`.

1. Open **Configure** on the Plant's entry, choose **Arm outputs**, check the two valves and the pump, and submit.
   **Control equipment** stays off, so the Plant runs in Dry run.
2. Set `select.trial_plant_mode` to heat.
3. Set `climate.bedroom` to heat; a new thermostat starts off with a 21 °C target.
4. Lower `input_number.hydronicus_trial_bedroom_temperature` to 18 °C.
5. `binary_sensor.bedroom_heating_demand` turns on with a `level` of 1.
   The `proposed` attribute of `sensor.trial_plant_status` shows the bedroom valve on at once, and the pump on 180 seconds later, once the valve has had its opening time.
6. Raise the bedroom temperature to 22 °C.
   Demand ends, and the pump keeps running for its 180 second overrun before the valve closes.
   `proposed` lists only the outputs whose proposed state differs from what they show, so the pump drops out of it after the overrun, and then the valve.

Dry run sends nothing, so the history of the three trial `input_boolean` helpers stays unchanged.
Now turn on `switch.trial_plant_control_equipment` and lower the bedroom temperature to 18 °C again: the valve's helper turns on, and the pump's follows after the opening time.
Turn **Control equipment** off again, and Hydronicus stops what runs in order before it returns to Dry run.

See [configuration](docs/configuration.md) for every form, [the plant file](docs/plant-file.md) for the file format, and [troubleshooting](docs/troubleshooting.md) if something does not behave as expected.

## Dry run and control

Dry run is where every Plant starts, and where it returns when **Control equipment** is turned off.
It evaluates the Plant against the real states of your entities and records each command as proposed instead of sending it.
It is a check of the configuration and the sequence, not a physical simulation of water, pressure, or temperature, and it cannot prove that a valve opens or a pump produces flow.

With **Control equipment** on, Hydronicus commands the outputs you armed, and nothing else.
It never commands an external thermostat or a pump the source drives.

## Safety limits

Hydronicus is software coordination.
It is not a boiler safety controller, pressure relief, flow proving, a condensation sensor, a high-limit thermostat, or an emergency stop.
Keep the physical protections of the heat source, the emitters, the water circuit, and the electrical installation independent of Home Assistant.
Read [safety limits](docs/safety.md) before you arm real equipment.

## Documentation

- [How Hydronicus works](docs/how-it-works.md): the model, one evaluation step by step, how outputs are commanded, minimum flow, mode changes, and the condensation guard.
- [Configuration](docs/configuration.md): every form, from guided setup to arming, reconfiguring, and zones.
- [Plant file](docs/plant-file.md): the YAML format, every key and default, and the errors.
- [Entities](docs/entities.md): the entities a Plant publishes, for dashboards and automations.
- [Safety limits](docs/safety.md): what Hydronicus does and does not protect.
- [Troubleshooting](docs/troubleshooting.md): the status, the reasons, every Repair, and diagnostics.
- [Upgrade and rollback](docs/upgrade-and-rollback.md): installing, updating, and moving a Plant from version 0.1.0.
- [Development](docs/development.md): the local environment, the tests, and the architecture.

When reporting a problem, use the [diagnostic bug report template](.github/ISSUE_TEMPLATE/diagnostic-bug-report.md), and remove credentials, tokens, private addresses, and household details first.
