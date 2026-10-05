"""Sending the reconciler's actions to Home Assistant, outside the evaluation.

One dispatcher per Plant sends every batch of actions in the order the
evaluations decided them, one call at a time, so calls to one entity act in the
order they were decided. Each call is limited to ``CALL_TIMEOUT`` after the
evaluation that decided it, so none acts later than ``step()`` assumes. A
returned call is not a confirmation; the next observation is.

Only one task sends at a time: it runs while batches are queued and ends when
the queue is empty. Stopping drops the queue and cancels that task, so no call
starts once stopping has begun.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from math import isfinite
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfTemperature
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .core.model import NumericTarget, OptionTarget, OutputTarget, SwitchTarget
from .core.reconcile import Action
from .core.step import CALL_TIMEOUT

_LOGGER = logging.getLogger(__name__)


def service_call(action: Action, state: State | None = None) -> tuple[str, str, dict[str, Any]]:
    """Return the domain, service, and data of the call that drives an output to a target.

    The plant file allows switch and valve outputs, source mode selects, and
    source temperature numbers. Numeric targets are canonical Celsius.
    """
    entity = action.entity
    domain = entity.partition(".")[0]
    data: dict[str, Any] = {"entity_id": entity}
    match action.target:
        case SwitchTarget(on=on):
            if domain == "valve":
                return domain, "open_valve" if on else "close_valve", data
            return domain, "turn_on" if on else "turn_off", data
        case OptionTarget(option=option):
            return domain, "select_option", {**data, "option": option}
        case NumericTarget(value=value):
            return domain, "set_value", {**data, "value": native_temperature(value, state)}


def native_temperature(value: float, state: State | None) -> float:
    """Convert a Celsius target only when the current number's unit and bounds permit it."""
    if state is None:
        raise ValueError("temperature number is missing")
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or UnitOfTemperature.CELSIUS
    if (
        not isinstance(unit, str)
        or unit not in TemperatureConverter.VALID_UNITS
        or not isfinite(value)
    ):
        raise ValueError("temperature number has an unsupported unit or invalid target")
    native = TemperatureConverter.convert(value, UnitOfTemperature.CELSIUS, str(unit))
    try:
        minimum = float(state.attributes["min"])
        maximum = float(state.attributes["max"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("temperature number has no valid bounds") from error
    if not isfinite(minimum) or not isfinite(maximum) or not minimum <= native <= maximum:
        raise ValueError("temperature target is outside the number's bounds")
    return native


class Dispatcher:
    """Sends a Plant's actions in order, and stops without sending another."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        name: str,
        authorized: Callable[[Action], bool],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.name = name
        self._authorized = authorized
        # Each unsent action with the time of the evaluation that decided it.
        self._actions: deque[tuple[Action, float]] = deque()
        self._task: asyncio.Task[None] | None = None
        self._stopped = False

    @callback
    def send(self, actions: Iterable[Action], sent_at: float) -> None:
        """Queue a batch after the ones not yet sent; the evaluation never awaits it."""
        if self._stopped:
            return
        self._actions.extend((action, sent_at) for action in actions)
        if self._task is None or self._task.done():
            # Not eager: the evaluation that queued the batch finishes before any call starts.
            self._task = self.entry.async_create_task(
                self.hass,
                self._async_send_queued(),
                f"Send Hydronicus Plant {self.name} actions",
                eager_start=False,
            )

    @callback
    def discard_obsolete(self, armed: frozenset[str], targets: Mapping[str, OutputTarget]) -> None:
        """Invalidate unsent commands that the latest authorized plan no longer requests."""
        self._actions = deque(
            (action, at)
            for action, at in self._actions
            if action.entity in armed and targets.get(action.entity) == action.target
        )

    @callback
    def stop(self) -> None:
        """Cancel synchronously so no queued command can begin after the stop event."""
        self._stopped = True
        self._actions.clear()
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def async_stop(self) -> None:
        """Drop the actions not yet sent and await cancellation of the call in progress."""
        self.stop()
        if self._task is not None and not self._task.done():
            await asyncio.wait([self._task])

    async def _async_send_queued(self) -> None:
        while self._actions and not self._stopped:
            action, sent_at = self._actions.popleft()
            await self._async_send(action, sent_at)

    async def _async_send(self, action: Action, sent_at: float) -> None:
        if self._stopped or not self._authorized(action):
            return
        remaining = sent_at + CALL_TIMEOUT - dt_util.utcnow().timestamp()
        if remaining <= 0:
            _LOGGER.warning(
                "Plant %s did not send %s to %s in time; it retries",
                self.name,
                action.target,
                action.entity,
            )
            return
        domain, service = action.entity.partition(".")[0], "set_target"
        try:
            domain, service, data = service_call(action, self.hass.states.get(action.entity))
            async with asyncio.timeout(remaining):
                await self.hass.services.async_call(domain, service, data, blocking=True)
        except TimeoutError:
            _LOGGER.warning(
                "Plant %s: %s.%s for %s did not return in time",
                self.name,
                domain,
                service,
                action.entity,
            )
        except Exception as error:  # Any failure is retried and surfaced as a Repair.
            _LOGGER.warning(
                "Plant %s: %s.%s for %s failed: %s",
                self.name,
                domain,
                service,
                action.entity,
                error,
            )
