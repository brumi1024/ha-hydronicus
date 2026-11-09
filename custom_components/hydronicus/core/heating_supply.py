"""Who owns the heating supply temperature: the owner's choice, and adopting outside changes.

A source with a weather curve switch, a supply number, or both offers the
strategies of ``HeatingSupply``: the source's own curve, a fixed setpoint, or
Hydronicus's curve. The owner picks one through Hydronicus's entities, and a
change made elsewhere, such as the curve switched off on the source's own
controller, is adopted as the owner's choice and never reverted. Cooling is
not a choice: the curve is off and the setpoint is Hydronicus's, so nothing
changed while cooling is adopted.

The source's curve number, when bound, is owned the same way: a change made
elsewhere is adopted as Hydronicus's value and never written back.

A warm-up holds the heating supply at least at a warm-up temperature for a
bounded time: a fixed temperature or Hydronicus's curve is raised to it, and
the source's own curve is turned off for its time while the supply setpoint
holds it, then turned on again. The strategy in force stays. It ends after its
duration, once every zone that called when it started is warm, as soon as the
Plant cools, when the heating supply strategy changes, or when the curve it
turned off is turned on elsewhere. Without a supply setpoint it is refused.
``heating_supply_step`` is pure: ``step()`` calls it with the physical outputs,
the owner's last command, and the zones' demand.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from math import isfinite
from typing import Any

from .model import MAX_WARM_UP_DURATION, HeatingSupply, Mode, Source

__all__ = [
    "HeatingSupplyResult",
    "HeatingSupplyState",
    "SupplyCommand",
    "WarmUpRefusal",
    "clamp_fixed",
    "heating_supply_step",
    "warm_up_refusal",
]


@dataclass(frozen=True, slots=True)
class SupplyCommand:
    """What the owner last asked of the heating supply through Hydronicus, stamped when asked."""

    at: float
    strategy: HeatingSupply | None = None
    fixed: float | None = None
    curve_number: float | None = None
    # True starts a warm-up, for ``warm_for`` seconds to ``warm_to`` °C when
    # given, else the configured duration and the Warm-up temperature; False ends it.
    warm_up: bool | None = None
    warm_for: float | None = None
    warm_to: float | None = None
    # The owner's Warm-up temperature, which also applies to a running warm-up.
    warm_temperature: float | None = None


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
    # The owned curve number, the last usable one seen, and the one Hydronicus
    # last asked for, so that its own value landing is not adopted.
    curve_number: float | None = None
    seen_number: float | None = None
    last_number: float | None = None
    # The owner's Warm-up temperature, or None for the configured one.
    warm_temperature: float | None = None
    # The warm-up in progress: until when, the temperature an action asked for
    # it alone, or None for the Warm-up temperature, and the zones that called
    # when it started, whose warmth ends it early.
    warm_until: float | None = None
    warm_to: float | None = None
    warm_zones: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": None if self.strategy is None else self.strategy.value,
            "fixed": self.fixed,
            "seen_curve": self.seen_curve,
            "seen_setpoint": self.seen_setpoint,
            "last_target": self.last_target,
            "command_at": self.command_at,
            "curve_number": self.curve_number,
            "seen_number": self.seen_number,
            "last_number": self.last_number,
            "warm_temperature": self.warm_temperature,
            "warm_until": self.warm_until,
            "warm_to": self.warm_to,
            "warm_zones": list(self.warm_zones),
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
            curve_number=number("curve_number"),
            seen_number=number("seen_number"),
            last_number=number("last_number"),
            warm_temperature=number("warm_temperature"),
            warm_until=number("warm_until"),
            warm_to=number("warm_to"),
            warm_zones=tuple(str(zone) for zone in data.get("warm_zones", ())),
        )

    @property
    def warming(self) -> bool:
        return self.warm_until is not None


@dataclass(frozen=True, slots=True)
class HeatingSupplyResult:
    state: HeatingSupplyState
    # The strategy in force and the fixed strategy's temperature, None without a
    # supply number.
    strategy: HeatingSupply
    fixed: float | None
    # What changed that the owner should hear about: adoptions and choices.
    events: tuple[str, ...] = ()
    # The curve number to ask for now, None without one or before it is known.
    curve_number: float | None = None
    # The Warm-up temperature in force, None without a supply number.
    warm_temperature: float | None = None
    # The temperature a running warm-up holds the heating supply at least at.
    warm_up: float | None = None

    @property
    def source_curve(self) -> bool:
        """Whether the source's own curve heats: chosen, and no warm-up turns it off."""
        return self.strategy is HeatingSupply.SOURCE_CURVE and self.warm_up is None


class WarmUpRefusal(StrEnum):
    """Why a warm-up is not started; each value is also a translation key."""

    COOLING = "warm_up_while_cooling"
    NO_SUPPLY = "warm_up_no_supply"


_REFUSALS = {
    WarmUpRefusal.COOLING: "a warm-up only heats, so it was not started while cooling",
    WarmUpRefusal.NO_SUPPLY: (
        "a warm-up was not started: the source has no supply setpoint to hold"
    ),
}


def warm_up_refusal(source: Source, *, cooling: bool) -> WarmUpRefusal | None:
    """Why a warm-up cannot raise the heating supply, None when it can."""
    if cooling:
        return WarmUpRefusal.COOLING
    if source.supply is None:
        return WarmUpRefusal.NO_SUPPLY
    return None


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


def _given(value: float | None, default: float) -> float:
    """A command's positive finite value, else the configured one."""
    return value if value is not None and isfinite(value) and value > 0 else default


def heating_supply_step(
    source: Source,
    mode: Mode,
    curve: bool | None,
    setpoint: float | None,
    ours: Callable[[str], bool],
    state: HeatingSupplyState,
    command: SupplyCommand | None,
    *,
    number: float | None = None,
    cools: bool = False,
    now: float = 0.0,
    reached: Callable[[float], bool] = lambda _: False,
    calling: tuple[str, ...] = (),
    warm: Callable[[tuple[str, ...]], bool] = lambda _: False,
) -> HeatingSupplyResult | None:
    """Adopt a change made elsewhere, apply the owner's command, and choose the strategy.

    ``mode`` is the mode the outputs run in. ``curve``, ``setpoint``, and
    ``number`` are the weather curve switch's, the supply number's, and the
    curve number's usable physical values, None while unknown. ``ours(entity)``
    says whether a value an output shows is one of Hydronicus's calls landing.
    ``cools`` says whether the Plant is asked to cool though its outputs do not
    yet. ``calling`` are the zones that call for heat now, and ``warm(zones)``
    says whether every one of them has reached its heating target. None when the
    source offers no strategy.
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

    warm_until, warm_to, warm_zones = state.warm_until, state.warm_to, state.warm_zones

    def end_warm_up(why: str) -> None:
        nonlocal warm_until, warm_to, warm_zones
        if warm_until is not None:
            events.append(f"the warm-up ended {why}")
        warm_until, warm_to, warm_zones = None, None, ()

    weather, supply = source.weather_curve, source.supply
    if weather is not None and curve is not None and curve != seen_curve:
        # A warm-up on the source's own curve turns it off for its time.
        on_curve = (strategy or default) is HeatingSupply.SOURCE_CURVE
        wanted = on_curve and warm_until is None
        first = heating and strategy is None
        changed = (
            heating and seen_curve is not None and curve != wanted and not ours(weather.switch)
        )
        if changed and curve and on_curve:
            # The curve turned on again elsewhere: the warm-up ends, the curve stays.
            end_warm_up("since the weather curve was turned on elsewhere")
        elif first or changed:
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

    config = source.curve_number
    owned, seen_number = state.curve_number, state.seen_number
    if config is not None and number is not None and number != seen_number:
        if owned is None:
            # The first sighting takes over the curve the source runs now.
            owned = config.clamp(number)
        elif number != state.last_number and not ours(config.entity):
            owned = config.clamp(number)
            events.append(f"the curve number was set elsewhere to {number:g}; adopted")
        seen_number = number

    command_at, chose = state.command_at, False
    warm_temperature = state.warm_temperature
    fresh = command is not None and (command_at is None or command.at > command_at)
    if command is not None and fresh:
        command_at = command.at
        if command.strategy is not None and command.strategy in offered:
            chose = command.strategy is not (strategy or default)
            strategy = command.strategy
        if command.fixed is not None and supply is not None:
            fixed = clamp_fixed(source, command.fixed)
        if command.curve_number is not None and isfinite(command.curve_number) and config:
            owned = config.clamp(command.curve_number)
        chosen = clamp_fixed(source, command.warm_temperature)
        if chosen is not None:
            # The owner's latest choice applies at once, over an action's own.
            warm_temperature, warm_to = chosen, None

    current = strategy or default
    if chose or (state.strategy is not None and state.strategy is not current and not events):
        events.append(f"heating now uses {_NAMES[current]}")
    if current is not (state.strategy or default):
        end_warm_up("since the heating supply strategy changed")
    cooling = cools or not heating
    if command is not None and fresh and command.warm_up is False:
        end_warm_up("early")
    elif command is not None and fresh and command.warm_up is True:
        refusal = warm_up_refusal(source, cooling=cooling)
        if refusal is not None:
            events.append(_REFUSALS[refusal])
        else:
            duration = min(_given(command.warm_for, source.warm_up.duration), MAX_WARM_UP_DURATION)
            warm_until, warm_zones = now + duration, calling
            warm_to = clamp_fixed(source, command.warm_to)
            temperature = _warm_temperature(source, warm_temperature, warm_to)
            events.append(
                f"a warm-up raises the heating supply to at least {temperature:g} °C "
                f"for {duration / 60:g} min"
            )

    if warm_until is not None:
        if cooling:
            end_warm_up("since the Plant cools")
        elif reached(warm_until):
            end_warm_up("after its time")
        elif warm_zones and warm(warm_zones):
            end_warm_up("since its zones reached their targets")
        elif supply is None:
            end_warm_up("since the source has no supply setpoint")
    effective = (
        None if supply is None else (fixed if fixed is not None else supply.heat_temperature)
    )
    asked = None if config is None else owned
    next_state = replace(
        state,
        strategy=strategy,
        fixed=fixed,
        seen_curve=seen_curve,
        seen_setpoint=seen_setpoint,
        command_at=command_at,
        curve_number=owned,
        seen_number=seen_number,
        last_number=state.last_number if asked is None else asked,
        warm_temperature=warm_temperature,
        warm_until=warm_until,
        warm_to=warm_to,
        warm_zones=warm_zones,
    )
    return HeatingSupplyResult(
        next_state,
        current,
        clamp_fixed(source, effective),
        tuple(events),
        curve_number=asked,
        warm_temperature=_warm_temperature(source, warm_temperature, None),
        warm_up=None
        if warm_until is None
        else _warm_temperature(source, warm_temperature, warm_to),
    )


def _warm_temperature(source: Source, setting: float | None, asked: float | None) -> float | None:
    """The temperature a warm-up holds: an action's own, else the owner's, else the configured."""
    if asked is not None:
        return clamp_fixed(source, asked)
    return clamp_fixed(source, source.warm_up.temperature if setting is None else setting)
