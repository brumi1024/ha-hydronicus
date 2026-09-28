# Getting started

This guide has two parts.
First you build a small trial Plant on fake entities and watch Hydronicus work, without touching any equipment.
Then you take your own plant live, one safe step at a time.

## Part 1: a trial Plant

The [trial kit](examples/trial) gives you a Plant with two zones, a valve in each, and one pump.
Every fake valve and pump is a template switch backed by an `input_boolean`, so the helper's history shows every command that reached it.

### Load the trial entities

1. Copy [package.yaml](examples/trial/package.yaml) to `packages/hydronicus_trial.yaml` in your Home Assistant configuration directory.
2. Add the package to `configuration.yaml`, or see [Home Assistant's packages documentation](https://www.home-assistant.io/docs/configuration/packages/) if you already use packages:

   ```yaml
   homeassistant:
     packages:
       hydronicus_trial: !include packages/hydronicus_trial.yaml
   ```

3. Restart Home Assistant.

You now have two temperature sensors, `sensor.hydronicus_trial_living_room_temperature` and `sensor.hydronicus_trial_bedroom_temperature`, both at 21 °C.
You set them with `input_number.hydronicus_trial_living_room_temperature` and `input_number.hydronicus_trial_bedroom_temperature`.
The outputs are `switch.hydronicus_trial_living_room_valve`, `switch.hydronicus_trial_bedroom_valve`, and `switch.hydronicus_trial_pump`.

### Create the trial Plant

Open **Settings > Devices & services > Add integration** and search for **Hydronicus**.
Choose **Import a plant file**, paste the contents of [plant.yaml](examples/trial/plant.yaml) into **Plant file**, and submit.
**Review the Plant** shows the two zones with their loops and the pump; submit it to create the Plant.

<details>
<summary>Or build the same Plant with guided setup</summary>

Choose **Guided setup** instead of importing:

1. In **The Plant and its source**, enter `Trial plant` as the **Plant name**, leave the **Source request switch** empty, and submit.
2. In **Pump**, enter `Circulation pump` as the **Pump name**, choose `switch.hydronicus_trial_pump` as the **Pump switch**, and submit.
3. In **How is your home zoned?**, choose **Zones without areas**.
4. In **Add a zone**, enter `Living room` as the **Zone name**, choose the living room sensor under **Extra temperature sensors**, and submit.
5. In the loop form, enter `Floor` as the **Loop name**, choose the living room valve under **Valves** and the circulation pump as the **Pump**, and submit.
6. Choose **Add another zone**, and add `Bedroom` the same way with its sensor and its valve.
7. Choose **Continue**, then **Continue** again in **Plant loops**, and submit **Review the Plant**.

Both ways give the same Plant with the same entity IDs.

</details>

### Watch it in Dry run

The Plant starts in Dry run: it decides what it would do, and sends nothing.
You'll use these entities:

| Entity | What it is |
| --- | --- |
| `select.trial_plant_mode` | The Plant's **Mode**: off, heat, or cool. |
| `switch.trial_plant_control_equipment` | **Control equipment**: while it is off, the Plant is in Dry run. |
| `sensor.trial_plant_status` | The Plant's **Status**, with what it would do in its `proposed` attribute. |
| `climate.bedroom` | The bedroom's thermostat. |
| `binary_sensor.bedroom_heating_demand` | Whether the bedroom calls for heat, and why, in its `reason` attribute. |

1. Open **Configure** on the Plant's entry, choose **Arm outputs**, check the two valves and the pump, and submit.
   Arming says which outputs Hydronicus may ever command; **Control equipment** stays off.
2. Set `select.trial_plant_mode` to heat.
3. Set `climate.bedroom` to heat. A new thermostat starts with a 21 °C target.
4. Lower `input_number.hydronicus_trial_bedroom_temperature` to 18 °C.

`binary_sensor.bedroom_heating_demand` turns on, and the `proposed` attribute of `sensor.trial_plant_status` shows the bedroom valve on at once.
180 seconds later, once the valve has had time to open, it shows the pump on too.

Now raise the bedroom temperature to 22 °C.
The demand ends, and the pump keeps running for its 180 second overrun before the valve closes.
`proposed` only lists outputs whose proposed state differs from what they show, so the pump drops out after the overrun, and then the valve.
The history of the trial `input_boolean` helpers stays unchanged, because Dry run sends nothing.

### Let it control the trial equipment

Turn on `switch.trial_plant_control_equipment`, and lower the bedroom temperature to 18 °C again.
This time the valve's helper really turns on, and the pump's helper follows after the opening time.

Turn **Control equipment** off again.
Hydronicus stops what runs in the same safe order, and only then returns to Dry run.

### Optional: follow Home Assistant areas

Instead of naming sensors in each zone, a zone can follow the temperature sensor that its Home Assistant area names.
You then choose a room's sensor once, in the area settings, and every zone that covers the area follows it.

1. Open **Settings > Areas, labels & zones** and create the areas `Living room` and `Bedroom`.
2. Open each trial temperature sensor's settings and set its **Area**.
   The area settings only offer sensors that belong to the area, so this step comes first.
3. Open each area, choose **Area settings** in its menu, choose its trial sensor as the **Temperature sensor**, and save.
4. Remove the trial Plant and import [plant-areas.yaml](examples/trial/plant-areas.yaml) instead, or use guided setup with **One zone per area**.

Each zone's thermostat now sits in its area.
The zone's **Combined temperature** sensor lists the area and the sensor it follows in its `areas` attribute, and picking another sensor in the area settings takes effect at once.

## Part 2: your own plant

Take each step only when the one before looks right.

### 1. Set it up

Create the Plant with guided setup or a plant file, as [configuration](configuration.md) describes.
Names become entity IDs, such as `climate.living_room`, so choose names you want to keep.

### 2. Check what it reads

With **Control equipment** off, check that:

- Every zone's **Combined temperature** shows the temperature you expect.
- Every zone that cools shows a plausible **Dew point**.
- Every window sensor reads open and closed as it should, and every condensation switch reads off while its pipe is dry.

### 3. Arm the outputs

Open **Configure** on the Plant's entry and choose **Arm outputs**.
The list shows every output with its role, such as `Valve of Living area / Ceiling: switch.living_area_ceiling_valve`.
Check each entity against the device it really controls before you check it here.
A loop only runs when every output it needs is armed.

### 4. Watch it in Dry run

Set the Plant's **Mode** and each zone's thermostat to heat, or cool, and let the Plant run in Dry run for a while.
The **Status** sensor's `proposed` attribute shows what Hydronicus would do, and its `reasons` attribute explains why.
The proposals should follow the safe order: valves, then pumps, then the source.

### 5. Go live

Before you turn on **Control equipment**, make sure that:

- The physical protections of your plant work without Home Assistant, as [safety limits](safety.md) describes.
- A pump the source runs is set to **A separator guarantees its flow** only if a separator, buffer, or bypass really protects it.
- You can stop the equipment by hand.

Then turn on **Control equipment**, and stay near the plant the first time it runs.
Turning it off stops the armed equipment in order and returns the Plant to Dry run; its `live` attribute stays true until the equipment has stopped.

If something does not behave as you expect, start with [troubleshooting](troubleshooting.md).
