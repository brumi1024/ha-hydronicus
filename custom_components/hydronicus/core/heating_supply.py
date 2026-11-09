"""Who owns the heating supply temperature: the owner's choice, and adopting outside changes.

A source with a weather curve switch, a supply number, or both offers the
strategies of ``HeatingSupply``: the source's own curve, a fixed setpoint, or
Hydronicus's curve. The owner picks one through Hydronicus's entities, and a
change made elsewhere, such as the curve switched off on the source's own
controller, is adopted as the owner's choice and never reverted. Cooling is
not a choice: the curve is off and the setpoint is Hydronicus's, so nothing
changed while cooling is adopted. ``heating_supply_step`` is pure: ``step()``
calls it with the physical outputs and the owner's last command.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from math import isfinite
from typing import Any

from .model import HeatingSupply, Mode, Source

__all__ = [
    "HeatingSupplyResult",
    "HeatingSupplyState",
    "SupplyCommand",
    "clamp_fixed",
    "heating_supply_step",
]


@dataclass(frozen=True, slots=True)
class SupplyCommand:
    """What the owner last asked of the heating supply through Hydronicus, stamped when asked."""

    at: float
    strategy: HeatingSupply | None = None
    fixed: float | None = None


@dataclass(frozen=True, slots=True)
class HeatingSupplyState:
    """The owner's heating supply choice and what was last seen of it, persisted with the State."""

    # None until the first evaluation that sees the source chooses one.
    strategy: HeatingSupply | None = None
    # The fixed strategy's supply temperature, or None for the configured one.
    fixed: float | None = None
    # The last usable observed values, so that only a change of value is adopted,
    # not an output that becomes available again.
    seen_curve: bool | None = None
    seen_setpoint: float | None = None
    # The heating supply target Hydronicus last proposed, so that its own value
    # landing is not taken for a change made elsewhere.
    last_target: float | None = None
    # When the last applied command was asked, so that each applies once.
    command_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": None if self.strategy is None else self.strategy.value,
            "fixed": self.fixed,
            "seen_curve": self.seen_curve,
            "seen_setpoint": self.seen_setpoint,
            "last_target": self.last_target,
            "command_at": self.command_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HeatingSupplyState:
        def number(key: str) -> float | None:
            value = data.get(key)
            return None if value is None else float(value)

        strategy = data.get("strategy")
        seen_curve = data.get("seen_curve")
        return cls(
            strategy=None if strategy is None else HeatingSupply(strategy),
            fixed=number("fixed"),
            seen_curve=None if seen_curve is None else bool(seen_curve),
            seen_setpoint=number("seen_setpoint"),
            last_target=number("last_target"),
            command_at=number("command_at"),
        )


@dataclass(frozen=True, slots=True)
class HeatingSupplyResult:
    state: HeatingSupplyState
    # The strategy in force and the fixed strategy's temperature, None without a
    # supply number.
    strategy: HeatingSupply
    fixed: float | None
    # What changed that the owner should hear about: adoptions and choices.
    events: tuple[str, ...] = ()


_NAMES = {
    HeatingSupply.SOURCE_CURVE: "the source's own weather curve",
    HeatingSupply.FIXED: "a fixed supply temperature",
    HeatingSupply.CURVE: "Hydronicus's heating curve",
}


def clamp_fixed(source: Source, value: float | None) -> float | None:
    """A fixed supply temperature within the supply's limits, at its resolution."""
    supply = source.supply
    if supply is None or value is None or not isfinite(value):
        return None
    if supply.step is not None:
        value = supply.step * round(value / supply.step)
    return min(supply.maximum, max(supply.minimum, value))


def heating_supply_step(
    source: Source,
    mode: Mode,
    curve: bool | None,
    setpoint: float | None,
    ours: Callable[[str], bool],
    state: HeatingSupplyState,
    command: SupplyCommand | None,
) -> HeatingSupplyResult | None:
    """Adopt a change made elsewhere, apply the owner's command, and choose the strategy.

    ``mode`` is the mode the outputs run in. ``curve`` and ``setpoint`` are the
    weather curve switch's and the supply number's usable physical values, None
    while unknown. ``ours(entity)`` says whether a value an output shows is one
    of Hydronicus's calls landing. None when the source offers no strategy.
    """
    offered = source.heating_supplies
    default = source.default_heating_supply
    if default is None:
        return None
    events: list[str] = []
    strategy = state.strategy if state.strategy in offered else None
    fixed = state.fixed
    seen_curve, seen_setpoint = state.seen_curve, state.seen_setpoint
    # Cooling is not a choice, so nothing changed while it runs is adopted.
    heating = mode is not Mode.COOL

    weather, supply = source.weather_curve, source.supply
    if weather is not None and curve is not None and curve != seen_curve:
        wanted = (strategy or default) is HeatingSupply.SOURCE_CURVE
        first = heating and strategy is None
        if first or (
            heating and seen_curve is not None and curve != wanted and not ours(weather.switch)
        ):
            # The first sighting takes over what the source does now, and a later
            # change is the owner's new choice.
            strategy = HeatingSupply.SOURCE_CURVE if curve else HeatingSupply.FIXED
            if not curve and setpoint is not None and supply is not None:
                # The source now heats to its own fixed setpoint, which stays.
                fixed = clamp_fixed(source, setpoint)
            if not first:
                events.append(
                    f"the weather curve was turned {'on' if curve else 'off'} elsewhere; "
                    f"heating now uses {_NAMES[strategy]}"
                )
        seen_curve = curve

    if supply is not None and setpoint is not None and setpoint != seen_setpoint:
        owned = (strategy or default) in (HeatingSupply.FIXED, HeatingSupply.CURVE) and (
            weather is None or curve is False
        )
        echo = state.last_target is not None and abs(setpoint - state.last_target) <= (
            supply.tolerance
        )
        if heating and owned and seen_setpoint is not None and not echo and not ours(supply.entity):
            fixed = clamp_fixed(source, setpoint)
            if (strategy or default) is HeatingSupply.CURVE:
                strategy = HeatingSupply.FIXED
                events.append(
                    f"the supply temperature was set elsewhere to {setpoint:g} °C; "
                    "heating now uses it as a fixed supply temperature"
                )
            else:
                events.append(f"the fixed supply temperature was set elsewhere to {setpoint:g} °C")
        seen_setpoint = setpoint

    command_at, chose = state.command_at, False
    if command is not None and (command_at is None or command.at > command_at):
        command_at = command.at
        if command.strategy is not None and command.strategy in offered:
            chose = command.strategy is not (strategy or default)
            strategy = command.strategy
        if command.fixed is not None and supply is not None:
            fixed = clamp_fixed(source, command.fixed)

    current = strategy or default
    if chose or (state.strategy is not None and state.strategy is not current and not events):
        events.append(f"heating now uses {_NAMES[current]}")
    effective = (
        None if supply is None else (fixed if fixed is not None else supply.heat_temperature)
    )
    next_state = replace(
        state,
        strategy=strategy,
        fixed=fixed,
        seen_curve=seen_curve,
        seen_setpoint=seen_setpoint,
        command_at=command_at,
    )
    return HeatingSupplyResult(next_state, current, clamp_fixed(source, effective), tuple(events))
