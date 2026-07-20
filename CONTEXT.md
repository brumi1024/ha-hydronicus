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
