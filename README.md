<p align="center">
  <img src="custom_components/hydronicus/brand/icon@2x.png" alt="Hydronicus" width="220">
</p>

<h1 align="center">Hydronicus</h1>

<p align="center">
  <strong>One plant. Many zones. No valve fights.</strong>
</p>

Hydronicus is a Home Assistant custom integration for describing hydronic heating and cooling plants as explicit topologies.
It models rooms (comfort zones), loops (hydraulic circuits), delivery routes, valves, pumps, and the decisions that connect them.

## Current status

The release target is `0.1.0`.
The current prerelease candidate is `0.1.0-rc.6`.
The current candidate supports end-to-end Dry run behavior and a configurable Plant control boundary.
Anyone can install Hydronicus, configure a Plant through the Home Assistant UI, exercise heating and cooling demand, inspect hydraulic sequencing and source recommendations, and troubleshoot the result without operating equipment.
A disposable Home Assistant 2026.8.2 working-tree run has validated configuration flows, migration, object ownership, diagnostics, reload, deletion, removal, and a clean Dry run shutdown with zero actuator service calls.
HACS-installed evidence from the exact committed candidate remains pending.

| Capability | Current candidate | `v0.1.0` release target |
| --- | --- | --- |
| Heating valves and pumps | Proposed in Dry run; controlled when off | Same behavior |
| Cooling and condensation protection | Starts remain Dry run | Starts remain Dry run |
| Source recommendation | Visible in both modes; selection remains Dry run | Same behavior |
| Direct source demand | Proposed in Dry run; controlled when off after a valid pump path | Same behavior |

The codebase contains the tested generic service-call executor needed for heating control.
The Plant UI exposes one Dry run setting, records proposed versus executed operations, and performs an ordered safe shutdown when Dry run is re-enabled.

The current implementation includes:

- HACS custom-repository installation.
- One Home Assistant config entry per Plant.
- Guided setup that creates a Plant with its pump and one room per form, and plant file import that rebuilds a Plant with the same entity IDs.
- Room subentries: each room owns its thermostat, its sensors, and its private loops and valves, and can use shared loops of the Plant.
- Plant settings for Dry run, pumps, showing the plant file, and editing the whole Plant as a plant file.
- The `hydronicus.export_plant` action, which returns the plant file of a Plant.
- Required and optional temperature sensors with freshness limits and calibration offsets.
- Mean, median, minimum, maximum, designated-reference, and weighted-mean aggregation.
- One thermostat owner per room: a Hydronicus thermostat or an existing Home Assistant climate entity.
- Hydronicus-owned comfort, eco, and away preset targets.
- Configurable Hydronicus thermostat hysteresis plus minimum active and idle durations.
- Several rooms per loop and several loops per room.
- Shared valve and pump modeling with active-consumer tracking.
- Heating demand with hysteresis and virtual valve opening and pump overrun timing.
- Cooling condensation diagnostics and Dry run source recommendations.
- Explicit, idempotent switch and native-valve executor operations behind the Plant Dry run control.
- Dry run climate, demand, aggregate-temperature, blocked-state, actuator-request, topology-preview, and explanation entities.
- Structured non-fatal warnings when shared valves or pumps limit independent control, and for unused Plant equipment.

Home Assistant Repairs for unresolved bindings, redacted downloadable diagnostics, startup reconciliation, and bounded command-failure handling are implemented.
Cooling starts, source-selector changeover, and physical actuator rollout remain gated milestone work.
Treat the roadmap as a statement of intent rather than authorization to use those paths on physical equipment.

## Installation

Hydronicus is currently installed as a HACS custom repository.
Use a disposable or staging Home Assistant instance for initial evaluation.

1. Open HACS and select **Integrations**.
2. Open the HACS menu and select **Custom repositories**.
3. Add `https://github.com/brumi1024/ha-hydronicus` and choose **Integration** as the repository type.
4. Install **Hydronicus** from HACS.
5. Restart Home Assistant.
6. Open **Settings > Devices & services**, select **Add integration**, and search for **Hydronicus**.
7. Add the **Hydronicus Plant** card from the Lovelace card picker; the card loads automatically, and it prefills the first Plant you can read.

If you added `/hydronicus/hydronicus-plant-card.js` as a dashboard resource for an earlier release, remove it as described in [the Lovelace guide](docs/lovelace.md#remove-the-old-manual-resource).

The minimum Home Assistant version declared by this repository is `2026.9.0`.
The integration is not currently part of the HACS default repository list, so the custom-repository step is required.

## First simulated Plant

Use a disposable Home Assistant instance or a staging configuration with synthetic entities.
Do not bind a Dry run test to equipment that must not be observed or controlled by the test.

The trial kit in [docs/examples/trial](docs/examples/trial) provides everything a first test needs:

- [package.yaml](docs/examples/trial/package.yaml) is a Home Assistant package with synthetic entities for two rooms and one pump.
- [plant.yaml](docs/examples/trial/plant.yaml) is a plant file bound to those entities.

Each room gets a temperature sensor driven by an `input_number`, and each valve and the pump are template switches backed by an `input_boolean`.
Because every actuator is backed by a helper, the helper's history shows any command that reached it.

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
Both room temperatures start at 21 °C.
See [Home Assistant's packages documentation](https://www.home-assistant.io/docs/configuration/packages/) if your configuration already uses packages.

### Create the Plant

Open **Settings > Devices & services > Add integration** and search for **Hydronicus**.
Either import the trial plant file or build the same Plant with guided setup; both give the same Plant and the same entity IDs.

To import the plant file:

1. Choose **Import a plant file**.
2. Paste the contents of `docs/examples/trial/plant.yaml` into **Plant file** and submit.
3. Continue with the review below.

To use guided setup:

1. Choose **Guided setup**.
2. In **Name the Plant**, enter `Trial plant` as the **Plant name**, choose `switch.hydronicus_trial_pump` as the **Pump entity**, and submit.
3. In **Add a room**, enter `Living room` as the **Room name**, choose `sensor.hydronicus_trial_living_room_temperature` under **Temperature sensors** and `switch.hydronicus_trial_living_room_valve` under **Loop valves**, turn on **Add another room**, and submit.
4. In the next **Add a room** form, enter `Bedroom` with `sensor.hydronicus_trial_bedroom_temperature` and `switch.hydronicus_trial_bedroom_valve`, leave **Add another room** off, and submit.
5. Continue with the review below.

Guided setup names each room's loop after the room, such as `Bedroom loop`, and its valve after the loop, such as `Bedroom loop valve`.
The plant file uses the same names, which is why both paths create the same entity IDs.

The review lists the two rooms and the compiled topology, such as `Zone Bedroom can request circuit Bedroom loop.`
It also lists one warning: both loops share the pump, so separate room thermostats cannot control them independently.
That is expected for a manifold, so turn on **I understand these warnings** and submit.
The new Plant starts in Dry run.

### Exercise the simulation

1. Set `climate.trial_plant_bedroom` to heat, because a fresh Hydronicus thermostat starts off with a 21 °C target.
2. Lower `input_number.hydronicus_trial_bedroom_temperature` to 18 °C.
3. Check that `binary_sensor.trial_plant_bedroom_demand` and `binary_sensor.trial_plant_bedroom_loop_valve_requested` turn on, while the Living room entities stay off.
4. After the valve's 30 second default opening time, check that `binary_sensor.trial_plant_pump_requested` turns on.
5. Raise the bedroom temperature to 22 °C.
   Demand ends, the virtual pump follows its 120 second default overrun, and then the virtual valve closes.

The requested entities describe what Hydronicus would do.
Dry run does not send a command to the configured valve, pump, or direct source-demand entity, so the history of the three trial `input_boolean` helpers stays unchanged.
Changing a Hydronicus climate target changes the calculated demand and the latest proposed operations.
If Dry run is turned off in an isolated test, heating valve and pump operations can execute after the configured confirmation.
Cooling starts and source-selector operations remain proposed and do not execute.

See [configuration and simulation](docs/configuration.md) for rooms, loops, and Plant settings, [the plant file reference](docs/plant-file.md) for the file format, and [troubleshooting](docs/troubleshooting.md) if the flow or entities do not behave as expected.

## Dry run boundary

Dry run is a safety boundary, not a physical simulation of water flow, pressure, temperature, or equipment response.
It evaluates the configured graph, reads actuator feedback, and records proposed operations without dispatching them.
It cannot prove that a real valve opens, that a pump produces flow, or that a heat source can deliver safe water.

Do not infer physical safety from a Dry run result.
Turning Dry run off is a tested software control boundary for heating operations, not authorization to operate a physical plant.
Keep real equipment outside the actuator path until the exact staged scope has human approval.

## Supported topology

Hydronicus uses explicit objects and relationships.
The UI speaks of rooms and loops; the model underneath speaks of Comfort Zones and Hydraulic Circuits.

- A Plant owns the complete topology and runtime state.
- A room is one Comfort Zone with its thermostat, its observations, its Delivery Routes, and its private loops and valves.
- One room thermostat owns target, preset, mode, hysteresis, and demand semantics.
- A loop is a Hydraulic Circuit: a water path through one or more valves and one pump.
- A Delivery Route connects one room to one loop.
- Plant equipment, owned by the Plant rather than a room, includes every pump, shared valves, shared loops, sources, and the source selector.
- A valve can be required by more than one loop.
- A pump can serve more than one loop.

Every object belongs to the Plant or to exactly one room, and a room never depends on another room's objects.
Deleting a room therefore removes exactly that room and always leaves a valid Plant.

Independent branches, shared pumps, shared valves, and one room routed to several loops can be represented.
Rooms, their private loops and valves, pumps, and Dry run are edited in the UI; shared loops, shared valves, and the source selector are edited through the [plant file](docs/plant-file.md).
Sharing a valve or another hydraulically coupled component does not create independent physical control.

Read [how Hydronicus works](docs/how-it-works.md) before mapping an existing plant.

## Thermostat ownership

Each room has exactly one thermostat owner.

A Hydronicus thermostat is a published climate entity with restored target, preset, and HVAC mode state.

An external thermostat is one existing `climate.*` entity whose `hvac_action` is normalized and consumed read-only.

Heating and preheating actions request heat, cooling requests cooling, and idle or off releases demand immediately.

Missing, unavailable, malformed, contradictory, or unsupported external actions fail closed.

External target and current temperature attributes are diagnostic only and never reconstruct demand.

Hydronicus never calls a service on an external thermostat.

An external thermostat must not independently command an actuator also configured as Hydronicus-owned.

Externally actuated or valve-less delivery routes are not supported by this redesign.

## Safety limits

Hydronicus is software coordination.
It is not a boiler safety controller, pressure-relief system, flow proving device, condensation sensor, high-limit thermostat, or emergency shutdown circuit.

Keep physical protection independent of Home Assistant, including the protections required by the heat source, emitters, water circuit, electrical installation, and local regulations.
Do not use the integration to bypass a hardware interlock or to decide whether equipment is safe to operate.

The software calculates heating, cooling, and source decisions while every new Plant starts in Dry run.
Cooling interlocks, dew-point checks, source selection, and the internal actuator executor are implemented and tested.
The Dry run setting controls heating valves, pumps, and configured direct source demand, while cooling starts and source selectors remain Dry run only.
These are not production safety controls or authorization to operate physical equipment.

Read [safety limits](docs/safety.md) before using any real sensor data.

## Troubleshooting, upgrades, and rollback

Start with [troubleshooting](docs/troubleshooting.md) for setup errors, unavailable sensors, warnings, logs, and recovery.
Use [upgrade and rollback](docs/upgrade-and-rollback.md) for HACS updates, configuration backups, safe reloads, and reverting an installation.

When reporting a problem, use the [diagnostic bug-report template](.github/ISSUE_TEMPLATE/diagnostic-bug-report.md).
Remove credentials, tokens, private addresses, and household-specific entity details before submitting any diagnostic information.

## Documentation

- [How Hydronicus works](docs/how-it-works.md) explains the model, evaluation cycle, shared equipment, and exact control boundary.
- [Lovelace Plant card](docs/lovelace.md) documents automatic card loading, removal of the old manual resource, dynamic Plant selector, presentation contract, and responsive layout.
- [Configuration and simulation](docs/configuration.md) walks through guided setup, rooms, loops, and Plant settings.
- [Plant file](docs/plant-file.md) is the reference for importing, exporting, and editing a whole Plant as YAML.
- [Safety limits](docs/safety.md) separates software coordination from physical protection.
- [Troubleshooting](docs/troubleshooting.md) covers setup, observations, explanations, Repairs, and diagnostics.
- [Upgrade and rollback](docs/upgrade-and-rollback.md) covers backup-first installation changes.
- [Development](docs/development.md) and [staging](docs/home-server-staging.md) are contributor references.

## Development

The deterministic controller core is isolated from Home Assistant imports.
See [the development environment](docs/development.md) for local setup and verification commands.
See [the staging contract](docs/home-server-staging.md) for synthetic and shadow runtime checks.
See [the implementation plan](docs/implementation-plan.md) for the roadmap and milestone boundaries.

Documentation in this repository describes the current public beta where it can be verified.
Active physical control remains outside this public-beta release, even where synthetic execution seams exist for tests.

Contributions are welcome while the project is taking shape.
