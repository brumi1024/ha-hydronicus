"""The simulated heat pump behaves as the owner measured the Midea unit."""

from __future__ import annotations

from custom_components.hydronicus.core.model import Mode
from tests.sim.harness import Sim
from tests.sim.heat_pump import HeatPumpHouse, HeatPumpSettings
from tests.sim.plants import HEAT_PUMP_REQUEST, HOME_HEAT_PUMP, plant

ALARM = "binary_sensor.midea_heat_pump_alarm"


def _house(settings: HeatPumpSettings | None = None) -> tuple[Sim, HeatPumpHouse]:
    # Dry run, so the scenario switches space heating by hand, as no controller
    # would; that is the model under test here, so the invariants are not checked.
    sim = Sim(plant(HOME_HEAT_PUMP), mode=Mode.HEAT, control=False)
    sim.checker.check = lambda _t: None  # type: ignore[method-assign]
    house = HeatPumpHouse(sim, settings=settings, alarm=ALARM, outdoor=7.0)
    sim.start()
    return sim, house


def _heating(sim: Sim, on: bool) -> None:
    sim.world.set_switch(HEAT_PUMP_REQUEST, on)


def test_space_heating_runs_the_internal_pump_and_off_stops_it_with_the_compressor() -> None:
    sim, house = _house()
    _heating(sim, True)
    house.run_for(120.0)
    assert house.pump and house.compressor
    assert sim.pump_running("heat_pump")

    _heating(sim, False)
    house.run_for(30.0)
    assert not house.pump and not house.compressor
    assert not sim.pump_running("heat_pump")


def test_the_compressor_waits_its_restart_delay_after_a_stop() -> None:
    sim, house = _house()
    _heating(sim, True)
    house.run_for(120.0)
    _heating(sim, False)
    house.run_for(30.0)
    stopped = house.stopped_at
    # Cold water, so only the delay can hold the compressor back.
    house.primary = 25.0

    _heating(sim, True)
    house.run_for(120.0)
    assert not house.compressor, "the compressor rests for its restart delay"
    house.run_for(120.0)
    assert house.compressor
    assert house.metrics.compressor_starts[-1] >= stopped + house.settings.restart_delay


def test_a_pump_restart_from_a_short_standstill_faults_e8_and_three_latch_e0() -> None:
    settings = HeatPumpSettings(e8_standstill=600.0, e8_duration=300.0)
    sim, house = _house(settings)
    _heating(sim, True)
    house.run_for(120.0)
    assert house.metrics.faults == [], "a first start after a long standstill runs"

    for count in range(3):
        _heating(sim, False)
        house.run_for(60.0)
        _heating(sim, True)
        house.run_for(settings.e8_delay + 30.0)
        assert house.faulted() and sim.world.contacts[ALARM].on
        assert not house.pump and not house.compressor
        assert not sim.pump_running("heat_pump"), "the world sees the internal pump stop"
        if count < 2:
            house.run_for(settings.e8_duration)
            assert not house.faulted() and not sim.world.contacts[ALARM].on
            assert house.pump, "the heat pump retries by itself once E8 clears"
    assert [code for _, code in house.metrics.faults] == ["E8", "E8", "E0"]
    house.run_for(3600.0)
    assert house.latched and sim.world.contacts[ALARM].on, "E0 needs a manual reset"


def test_a_pump_that_stops_in_thermo_off_restarts_with_each_compressor_start() -> None:
    sim, house = _house(HeatPumpSettings(pump_stops_in_thermo_off=True))
    _heating(sim, True)
    house.run_for(4 * 3600.0)

    assert len(house.metrics.compressor_starts) > 1
    assert len(house.metrics.pump_starts) == len(house.metrics.compressor_starts)
