"""A Plant's previous configuration, and stopping its outputs before a new one runs.

The runtime persists the last valid Plant with the armed outputs it was
commanding. When a new configuration removes an output that is still on, or is
not valid at all, the first evaluation runs the off sequence of that previous
Plant, as Control equipment off would, until its outputs are observed off, and
only then runs the new Plant; an invalid one is then only observed.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.core import StateMachine

from .core.model import OutputRole, Plant
from .core.plant_file import export_plant, parse_plant
from .observe import numeric_value, option_value, switch_value

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Commanding:
    """A valid Plant and the armed outputs it commanded, persisted across setups.

    A new configuration compares itself with it, so that outputs it no longer
    has are stopped by the Plant that started them.
    """

    plant: Plant
    outputs: frozenset[str]

    def to_dict(self, document: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Return JSON-friendly data, with the Plant's export when already made."""
        return {
            "plant": dict(document) if document is not None else export_plant(self.plant),
            "outputs": sorted(self.outputs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Commanding:
        outputs = data["outputs"]
        if not isinstance(outputs, list):
            raise TypeError("outputs is not a list")
        return cls(parse_plant(data["plant"]), frozenset(str(entity) for entity in outputs))


class PreviousConfiguration:
    """What the last setup persisted, and the previous Plant while its off sequence runs."""

    def __init__(self, title: str, plant: Plant, document: Mapping[str, Any] | None) -> None:
        """``document`` is the configured Plant's plant file, or None when it is not valid."""
        self.title = title
        # The last valid Plant and the outputs it commanded, as persisted.
        self.persisted: Commanding | None = None
        # The previous Plant while its off sequence runs, with the outputs it stops.
        self.stopping: Commanding | None = None
        self.decided = False
        self._plant = plant
        self._export = document
        self._stopping_export: dict[str, Any] | None = None

    def load(self, data: Mapping[str, Any] | None) -> None:
        """Take the persisted previous configuration; one that cannot be read stops nothing."""
        if data is None:
            return
        try:
            self.persisted = Commanding.from_dict(data)
        except Exception as error:  # Whatever is wrong with it, nothing is stopped.
            _LOGGER.warning(
                "The previous configuration of Plant %s could not be read, so outputs it "
                "removed are not stopped: %s",
                self.title,
                error,
            )

    def decide(
        self,
        states: StateMachine,
        attempts: Mapping[str, object],
        outputs: Mapping[str, OutputRole],
        valid: bool,
    ) -> bool:
        """Before the first evaluation, choose whether the previous Plant stops first.

        It does when the configuration is not valid, or when an output it
        commanded and the new Plant, with ``outputs``, does not have is observed on
        or has a call in flight, which is in ``attempts``. The off sequence stops
        every output of the previous Plant that is available now; one that is
        unavailable cannot be reached and is left as it is. Return whether it stops.
        """
        self.decided = True
        previous = self.persisted
        if previous is None or not previous.outputs:
            return False
        roles = previous.plant.outputs()

        def value(entity: str) -> bool | str | float | None:
            state = states.get(entity)
            if roles[entity] is OutputRole.SOURCE_MODE:
                return option_value(state)
            if roles[entity] is OutputRole.SOURCE_SETPOINT:
                return numeric_value(state)
            return switch_value(state)

        commanded = {entity for entity in previous.outputs if entity in roles}
        if valid and not any(
            entity in attempts or value(entity) is True for entity in commanded - set(outputs)
        ):
            return False
        reachable = frozenset(
            entity for entity in commanded if entity in attempts or value(entity) is not None
        )
        if not reachable:
            return False
        _LOGGER.warning(
            "Plant %s stops the outputs of its previous configuration before it runs the new one",
            self.title,
        )
        self.stopping = Commanding(previous.plant, reachable)
        self._stopping_export = export_plant(previous.plant)
        return True

    def stopped(self) -> None:
        """Every output of the previous Plant is observed off: the new one takes over."""
        _LOGGER.info("Plant %s stopped the outputs of its previous configuration", self.title)
        self.stopping = self._stopping_export = None

    def to_persist(self, commanded: frozenset[str]) -> dict[str, Any] | None:
        """The Plant whose outputs may be on and the outputs it commands, to persist.

        ``commanded`` is what the configured Plant commands now: its armed
        outputs while it is live, else none.
        """
        if not self.decided:
            # Nothing has run yet: keep what the previous setup left.
            return None if self.persisted is None else self.persisted.to_dict()
        if self.stopping is not None:
            return self.stopping.to_dict(self._stopping_export)
        if self._export is None:
            # A configuration that is not valid commands nothing.
            return None
        return Commanding(self._plant, commanded).to_dict(self._export)
