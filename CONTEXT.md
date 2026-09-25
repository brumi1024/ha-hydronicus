# Hydronicus domain glossary

## Delivery Route

A Delivery Route is an explicit connection from one Comfort Zone to one Hydraulic Circuit.

## Eligible Delivery Route

An Eligible Delivery Route is an enabled Delivery Route whose Comfort Zone currently has heating demand.

## Route Arbitration

Route Arbitration determines the Hydraulic Circuits requested by Eligible Delivery Routes.

## Any Demand

Any Demand requests every Hydraulic Circuit reached by an Eligible Delivery Route.

## Thermostat ownership

Every Comfort Zone receives demand from exactly one thermostat.

The thermostat can be a Hydronicus-owned digital thermostat or one existing external Home Assistant climate entity.

The Zone owns observations and topology relationships, while the thermostat owns target and demand state.

External thermostat demand is accepted from normalized `hvac_action` only.

## Room

A Room is the UI name of one Comfort Zone together with its thermostat, its Delivery Routes, and its private Loops and valves.

Each Room is one `room` config subentry of its Plant, and core code keeps the name Zone.

## Loop

A Loop is the UI name of one Hydraulic Circuit: a water path through one or more valves and one pump.

A private Loop belongs to one Room, and a shared Loop is Plant equipment that several Rooms can route to.

## Plant equipment

Plant equipment is every graph object that the Plant owns rather than a Room: every pump, every source, the source selector, and the shared valves and shared Loops.

Plant equipment that no enabled Delivery Route reaches is unused equipment, which compiles with a warning and is never requested.

## Deletion-closed ownership

Deletion-closed ownership assigns every graph object to the Plant or to exactly one Room, with references pointing only from a Room toward the Plant.

Removing a Room therefore removes exactly its own objects and always leaves a graph that validates and compiles.

## Plant file

A Plant file is the YAML document that describes one whole Plant, with objects addressed by slugs and optional explicit IDs.

It is used only for import, export, and whole-Plant editing, and importing an exported Plant file rebuilds the Plant with the same object IDs and entity IDs.
