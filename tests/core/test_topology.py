"""Tests for the pure topology compiler."""

from __future__ import annotations

import pytest
from hydronic_climate_core.model import Circuit, DeliveryRoute, PlantConfiguration, Zone
from hydronic_climate_core.topology import TopologyValidationError, compile_topology


def test_compile_topology_produces_summary() -> None:
    """A valid topology should compile into a deterministic summary."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                id="zone-1",
                name="Living room",
                target_temperature=21.5,
                temperature_sensor="sensor.living_room_temperature",
            ),
        ),
        circuits=(
            Circuit(
                id="circuit-1",
                name="Floor loop",
                valve_id="valve-1",
                pump_id="pump-1",
            ),
        ),
        routes=(DeliveryRoute(id="route-1", zone_id="zone-1", circuit_id="circuit-1"),),
    )

    compiled = compile_topology(plant)

    assert compiled.id == "plant-1"
    assert compiled.logic_summary == (
        "Circuit Floor loop opens valve valve-1 before requesting pump pump-1.",
    )


def test_compile_topology_rejects_orphans() -> None:
    """A topology with unreferenced objects should fail closed."""
    plant = PlantConfiguration(
        id="plant-1",
        zones=(
            Zone(
                id="zone-1",
                name="Living room",
                target_temperature=21.5,
                temperature_sensor="sensor.living_room_temperature",
            ),
        ),
        circuits=(
            Circuit(
                id="circuit-1",
                name="Floor loop",
                valve_id="valve-1",
                pump_id="pump-1",
            ),
        ),
        routes=tuple(),
    )

    with pytest.raises(TopologyValidationError, match="orphaned zones"):
        compile_topology(plant)
