# Hydronicus {{VERSION}}

This release rebuilds Hydronicus around a model that fits heat pump plants: an optional source, its pumps, zones, and the loops that connect them.
Control is now one pure evaluation that computes the desired state of every output, and a reconciler that drives each output there and retries until Home Assistant shows the result.
It is a breaking release: Plants set up with 0.1.0 are not migrated and must be set up again.

## Highlights

- Describe a plant without placeholder entities: a loop may have no valve, a pump may be driven by the source itself, and a heat pump can be asked for heating and for cooling.
- A pump that needs an open loop always has one while it may run, through its own min-flow loops or a separator, buffer, or bypass that guarantees its flow.
- Plant loops that no zone owns, such as a towel dryer, run with the source or with a set of zones.
- The Plant mode (off, heat, cool) is a select, and a mode change is sequenced: the old mode's source is released after its minimum on time, its pumps finish overrun and post-run, its loops close, and the dwell passes before the new mode starts.
- Heating and cooling never run at the same time, and every loop that cools is guarded against condensation with the worst-case dew point of its zones.
- Zone demand has a level from 0 to 1 besides on and off, ready for proportional valves and flow setpoints.
- Arming is per output: you confirm each output entity, and **Control equipment** turns control on for the armed outputs.
  Editing a thermostat, a sensor, a name, or a timing never disarms the Plant, and a new zone's outputs get a Repair that confirms them while the rest keeps running.
- Failed commands are retried with backoff from 10 seconds to 5 minutes, and a Repair names an output that does not respond after three attempts.
- Reloads and Home Assistant restarts send no command and continue every timer, including a valve that was still opening.
- Removing a zone, a loop, a pump, or the source first stops the equipment it removes, and a Plant left invalid by a removal stops in order and then only observes until it is fixed.

## Setup

- Guided setup asks for the Plant and its source, the pumps, how the home is zoned, one form per zone with its loops, plant loops, and the min-flow loops of each source-driven pump, then shows a review whose warnings never block.
- Each zone is its own entry under the Plant, with **Add zone** and **Reconfigure** for its areas, sensors, thermostat, and loops.
- **Reconfigure** on the Plant edits the Plant and its source, the pumps, and the plant loops, or replaces the whole Plant from a plant file after a summary of what changes.
- **Plant settings** arm outputs and show the plant file.
- The plant file is now format 2, the same schema Home Assistant stores, and exporting and importing a Plant reproduces its entity IDs.
- Repairs open the form that fixes them.

## Entities

- A Plant has a mode select, a **Control equipment** switch, and a status sensor.
- A zone has its climate entity when Hydronicus provides the thermostat, heating and cooling demand with their level, its combined temperature, and its dew point when it cools.
- A loop has a flowing sensor, and the source has a requested sensor.
- The reference plant gets 24 entities instead of about 60.
- The entity contract in `docs/entities.md` is the interface for dashboards.

## Removed

- The bundled Lovelace cards and their theming contract; build dashboards on the entity contract instead.
- Source recommendation and selection, per-equipment mode arbitration, simultaneous heating and cooling, shared valves, per-actuator entities, and the reconciliation counters.
- Sensor weights, calibration offsets, the designated reference, the median, and the weighted mean; calibrate a sensor at its source.

## Upgrade

Hydronicus requires Home Assistant 2026.9.0 or newer.

A Plant set up with 0.1.0 is refused at startup with a log message saying it must be set up again.
Plant files of format 1 are not read.
Remove the old Plant, install this release through HACS, restart Home Assistant, and set the Plant up again through guided setup or by importing a format 2 plant file.
If you added the Hydronicus cards to a dashboard, remove them.

A new Plant starts with nothing armed and **Control equipment** off, so it runs in Dry run until you arm its outputs and turn control on.

## Rollback

This release cannot load a Plant from 0.1.0, and 0.1.0 cannot load a Plant from this release.
To roll back, restore the Home Assistant backup taken before the upgrade.

Keep physical temperature, condensation, pressure, and flow safeguards independently active during any rollback.

## Known limitations

Hydronicus is a coordination layer, not a safety-rated controller.
Keep independent physical safeguards, such as high-limit, pressure, flow, freeze, and condensation protection, in service on every Plant.

The source is reached through a request switch and an optional mode select; writing a flow temperature setpoint arrives with heat pump control over Modbus in a later release.
There is no automatic season selection yet; an automation can set the Plant mode.
A plant loop that cools with zones that have no cooling loop of their own does not yet get a cooling thermostat for those zones.

## Hydronicus rename boundary

Hydronicus is installed from `custom_components/hydronicus` and uses the `hydronicus` domain.

The former `hydronic_climate` integration name and domain are not supported and must not be recreated during an upgrade.
