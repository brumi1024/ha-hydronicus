# Hydronicus domain glossary

## Plant

A Plant is one config entry: an optional Source, its Pumps, its Zones, and its Plant loops.

Objects are addressed by slugs, which are chosen at creation, never change, and form unique IDs with the Plant ID.
Names are separate and editable, and a missing name reads as the slug in words.

## Source

A Source is the generator Hydronicus asks for heat or cooling, such as a heat pump, and a Plant has at most one.

Hydronicus reaches it only through generic entities: a request switch, an optional mode select, and later a flow setpoint number.

A Plant without a Source still opens valves and runs switched Pumps, which suits a boiler with its own controls.

## Pump

A Pump is a circulator that Hydronicus switches, or that the Source drives and Hydronicus never commands.

Every Pump has a minimum flow: `guaranteed` when a Separator gives it a path whatever the Loops do, or `path` when it needs an open Loop while it runs.

## Loop

A Loop is a flow path: zero or more valves that open together, and exactly one Pump.

A Loop with no valve is always an open path, and its Pump is its only control.

A Loop runs in heating, cooling, or both, and it may cool only with a condensation reference: its Pump's supply temperature sensor or its own surface sensor.

## Zone

A Zone is the space one thermostat controls; it covers zero or more Areas, owns its Loops, and is one `zone` config subentry of its Plant.

Zones reference only Plant-level Pumps and the Source, so removing a Zone removes exactly its own Loops and valves.

## Plant loop

A Plant loop is a Loop that no Zone owns, which runs with the Source or with a set of Zones.

A Loop that several Zones use is a Plant loop that runs with those Zones.

## Area

An Area is a Home Assistant area, usually one physical room, that a Zone covers.

A Zone covers zero or more Areas, and an Area may be covered by several Zones.

A Zone follows the temperature sensor and the humidity sensor that each of its Areas currently names in Home Assistant, in addition to its explicit sensors.

An Area that is missing or names no sensor contributes no reading, and never makes the Plant fail to load.

## Thermostat ownership

Every Zone receives Demand from exactly one thermostat.

The thermostat can be a digital thermostat that Hydronicus provides or one existing external Home Assistant climate entity.

The Zone owns observations and Loops, while the thermostat owns target and Demand state.

External thermostat Demand is accepted from normalized `hvac_action` only, and an external thermostat is never commanded.

## Mode

The Mode is Plant-wide: off, heat, or cool.

Heating and cooling never run at the same time, and a change of Mode is sequenced through the old Mode's shutdown and a minimum dwell.

## Demand

Demand is a Zone's request in the current Mode, with an on or off decision and a level from 0 to 1.

## Min-flow path

A Min-flow path is the set of Loops held open so that a Pump without guaranteed flow always has a path while it may run.

A Source-driven Pump with minimum flow `path` names its Min-flow path loops.

## Separator

A Separator is a hydraulic separator, low-loss header, buffer, or bypass that gives a Pump a path whatever the Loops do.

## Desired state

The Desired state is what every output should be now, computed by each evaluation.

## Armed output

An Armed output is an output entity the owner has confirmed Hydronicus may command.

An output entity has exactly one role in one Plant: a valve of one Loop, a Pump switch, or a Source output.

## Plant file

A Plant file is the YAML document that describes one whole Plant, and it uses the same schema as storage.

The config entry's data holds everything except `zones`, and each Zone subentry's data holds that Zone's mapping plus its slug.
Storage lists Pumps and Loops as objects that carry their slugs, so their order survives Home Assistant sorting stored keys.

Importing an exported Plant file rebuilds the Plant with the same Plant ID, object slugs, and entity IDs.
