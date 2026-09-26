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
from collections.abc import Iterable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .core.model import OptionTarget, SwitchTarget, ValueTarget
from .core.reconcile import Action
from .core.step import CALL_TIMEOUT

_LOGGER = logging.getLogger(__name__)


def service_call(action: Action) -> tuple[str, str, dict[str, Any]]:
    """Return the domain, service, and data of the call that drives an output to a target.

    The plant file allows only switch and valve entities as switched outputs and
    select entities as the source mode.
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
        case ValueTarget(value=value):
            return domain, "set_value", {**data, "value": value}


class Dispatcher:
    """Sends a Plant's actions in order, and stops without sending another."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, name: str) -> None:
        self.hass = hass
        self.entry = entry
        self.name = name
        # Each batch with the time of the evaluation that decided it.
        self._batches: deque[tuple[tuple[Action, ...], float]] = deque()
        self._task: asyncio.Task[None] | None = None
        self._stopped = False

    @callback
    def send(self, actions: Iterable[Action], sent_at: float) -> None:
        """Queue a batch after the ones not yet sent; the evaluation never awaits it."""
        if self._stopped:
            return
        self._batches.append((tuple(actions), sent_at))
        if self._task is None or self._task.done():
            # Not eager: the evaluation that queued the batch finishes before any call starts.
            self._task = self.entry.async_create_task(
                self.hass,
                self._async_send_queued(),
                f"Send Hydronicus Plant {self.name} actions",
                eager_start=False,
            )

    async def async_stop(self) -> None:
        """Drop the batches not yet sent and cancel the call in progress."""
        self._stopped = True
        self._batches.clear()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await asyncio.wait([self._task])

    async def _async_send_queued(self) -> None:
        while self._batches:
            actions, sent_at = self._batches.popleft()
            for action in actions:
                await self._async_send(action, sent_at)

    async def _async_send(self, action: Action, sent_at: float) -> None:
        remaining = sent_at + CALL_TIMEOUT - dt_util.utcnow().timestamp()
        if remaining <= 0:
            _LOGGER.warning(
                "Plant %s did not send %s to %s in time; it retries",
                self.name,
                action.target,
                action.entity,
            )
            return
        domain, service, data = service_call(action)
        try:
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
