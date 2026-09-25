# Hydronicus domain glossary

## Delivery Route

A Delivery Route is an explicit connection from one Zone to one Hydraulic Circuit.

## Eligible Delivery Route

An Eligible Delivery Route is an enabled Delivery Route whose Zone currently has heating demand.

## Route Arbitration

Route Arbitration determines the Hydraulic Circuits requested by Eligible Delivery Routes.

## Any Demand

Any Demand requests every Hydraulic Circuit reached by an Eligible Delivery Route.

## Thermostat ownership

Every Zone receives demand from exactly one thermostat.

The thermostat can be a Hydronicus-owned digital thermostat or one existing external Home Assistant climate entity.

The Zone owns observations and topology relationships, while the thermostat owns target and demand state.

External thermostat demand is accepted from normalized `hvac_action` only.

## Zone

A Zone is the space one thermostat controls, together with its Areas, its sensors, its Delivery Routes, and its private Loops and valves.

Each Zone is one `zone` config subentry of its Plant.

## Area

An Area is a Home Assistant area, usually one physical room, that a Zone covers.

A Zone covers zero or more Areas, and an Area may be covered by several Zones.

A Zone follows the temperature sensor and the humidity sensor that each of its Areas currently names in Home Assistant, in addition to its explicit sensors.

An Area that is missing or names no sensor contributes no reading, and never makes the Plant fail to load.

## Loop

A Loop is the UI name of one Hydraulic Circuit: a water path through one or more valves and one pump.

A private Loop belongs to one Zone, and a shared Loop is Plant equipment that several Zones can route to.

## Plant equipment

Plant equipment is every graph object that the Plant owns rather than a Zone: every pump, every source, the source selector, and the shared valves and shared Loops.

Plant equipment that no enabled Delivery Route reaches is unused equipment, which compiles with a warning and is never requested.

## Deletion-closed ownership

Deletion-closed ownership assigns every graph object to the Plant or to exactly one Zone, with references pointing only from a Zone toward the Plant.

Removing a Zone therefore removes exactly its own objects and always leaves a graph that validates and compiles.

## Plant file

A Plant file is the YAML document that describes one whole Plant, with objects addressed by slugs and optional explicit IDs.

It is used only for import, export, and whole-Plant editing, and importing an exported Plant file rebuilds the Plant with the same object IDs and entity IDs.
