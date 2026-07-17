# Hydronic Climate

Hydronic Climate is a Home Assistant custom integration for topology-aware hydronic heating and cooling control.

It starts as a shadow-mode plant model and will grow into a deterministic controller for shared valves, pumps, sources, and safety interlocks.

## Status

This repository is in early implementation.

The current slice establishes the config flow and setup lifecycle for an empty plant.
It also includes a deterministic, shadow-only heating controller for zones, circuits, valves, and pumps.
No Home Assistant service calls are issued.

## Installation

Install the repository as a custom integration through HACS.

Then add Hydronic Climate from the Home Assistant UI.
