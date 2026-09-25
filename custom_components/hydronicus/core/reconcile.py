"""The level-triggered reconciler: from the desired state to the actions to send now.

On every evaluation the runtime passes the desired state from ``step()``, the
observed state of every output, and the reconciler's own State. The reconciler
compares desired and observed state and returns the actions to send, in
dependency order: when starting, valves open, then pumps on, then the source mode
and request; when stopping, the source request off, then pumps off, then valves
close, and a valve that is some running pump's last open path waits until that
pump is observed off.

A service call that returns is not a confirmation; only a later observation is.
The runtime sends each action outside its lock with a timeout of
``CALL_TIMEOUT`` seconds, so an action sent longer ago than that has either
taken effect or never will. An action whose target is still unmet is sent again
after a backoff that doubles from ``BACKOFF_MIN`` to ``BACKOFF_MAX``, and an
output is reported for a Repair once ``REPAIR_AFTER`` attempts have failed.

In Dry run nothing is sent. The reconciler records each action as proposed and
treats it as observed once, and ``dry_run_view`` shows ``step()`` those proposed
states, so the virtual sequence advances exactly as it would live.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final

from .model import Desired, OptionTarget, OutputTarget, Plant, SwitchTarget, ValueTarget
from .step import Observations, OptionState, OutputState, SwitchState, ValueState

# How long the runtime waits for one service call before it gives up on it.
CALL_TIMEOUT: Final = 10.0
BACKOFF_MIN: Final = 10.0
BACKOFF_MAX: Final = 300.0
REPAIR_AFTER: Final = 3


@dataclass(frozen=True, slots=True)
class Action:
    """One service call: drive an output entity to a target."""

    entity: str
    target: OutputTarget


@dataclass(frozen=True, slots=True)
class Attempt:
    """The sends of one target to one output that no observation has confirmed yet."""

    target: OutputTarget
    # How many times the target has been sent.
    count: int
    # When it was last sent.
    sent_at: float


@dataclass(frozen=True, slots=True)
class ReconcileState:
    """What the reconciler carries between evaluations; persisted like the step State."""

    # Unconfirmed sends, by output entity.
    attempts: Mapping[str, Attempt] = field(default_factory=dict)
    # Dry run: the proposed state of each output, which counts as observed.
    dry_run: Mapping[str, OutputState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-friendly data that ``from_dict`` reads back."""
        return {
            "attempts": {
                entity: {
                    "target": _target_to_dict(attempt.target),
                    "count": attempt.count,
                    "sent_at": attempt.sent_at,
                }
                for entity, attempt in self.attempts.items()
            },
            "dry_run": {entity: _output_to_dict(state) for entity, state in self.dry_run.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReconcileState:
        """Read persisted data; a missing key takes its initial value."""
        return cls(
            attempts={
                entity: Attempt(
                    target=_target_from_dict(value["target"]),
                    count=int(value["count"]),
                    sent_at=float(value["sent_at"]),
                )
                for entity, value in data.get("attempts", {}).items()
            },
            dry_run={
                entity: _output_from_dict(value)
                for entity, value in data.get("dry_run", {}).items()
            },
        )


@dataclass(frozen=True, slots=True)
class Reconciled:
    """The result of one reconciliation."""

    state: ReconcileState
    # The actions to send now, in order; always empty in Dry run.
    send: tuple[Action, ...] = ()
    # Dry run: the actions that would have been sent; never dispatched.
    proposed: tuple[Action, ...] = ()
    # When the next retry is due, as a timestamp, or None when nothing waits.
    retry_at: float | None = None
    # Outputs whose target is still unmet after ``REPAIR_AFTER`` failed attempts.
    repairs: frozenset[str] = frozenset()


def reconcile(
    plant: Plant,
    desired: Desired,
    outputs: Mapping[str, OutputState],
    state: ReconcileState,
    now: float,
    *,
    armed: frozenset[str],
    live: bool,
) -> Reconciled:
    """Return the actions that drive the observed ``outputs`` toward ``desired``.

    ``outputs`` is what the runtime observed, never the Dry run view. An output
    outside ``armed`` is never sent anything, and nothing is sent unless
    ``live``, which is the ``live`` flag of the State ``step()`` just returned.

    This is a stub until phase R3: it sends and proposes nothing.
    """
    del plant, desired, outputs, now, armed, live
    return Reconciled(state=state)


def dry_run_view(observations: Observations, state: ReconcileState) -> Observations:
    """Return the observations ``step()`` sees: in Dry run, outputs as proposed.

    The proposed states apply only while Control equipment is off, so the first
    evaluation after it turns on already sees the real outputs.
    """
    if observations.control or not state.dry_run:
        return observations
    return replace(observations, outputs={**observations.outputs, **state.dry_run})


# Persistence


def _target_to_dict(target: OutputTarget) -> dict[str, Any]:
    match target:
        case SwitchTarget(on=on):
            return {"on": on}
        case OptionTarget(option=option):
            return {"option": option}
        case ValueTarget(value=value):
            return {"value": value}


def _target_from_dict(data: Mapping[str, Any]) -> OutputTarget:
    if "on" in data:
        return SwitchTarget(bool(data["on"]))
    if "option" in data:
        return OptionTarget(str(data["option"]))
    return ValueTarget(float(data["value"]))


def _output_to_dict(state: OutputState) -> dict[str, Any]:
    match state:
        case SwitchState(on=on, since=since):
            return {"on": on, "since": since}
        case OptionState(option=option, since=since):
            return {"option": option, "since": since}
        case ValueState(value=value, since=since):
            return {"value": value, "since": since}


def _output_from_dict(data: Mapping[str, Any]) -> OutputState:
    since = float(data["since"])
    if "on" in data:
        return SwitchState(None if data["on"] is None else bool(data["on"]), since)
    if "option" in data:
        return OptionState(None if data["option"] is None else str(data["option"]), since)
    return ValueState(None if data["value"] is None else float(data["value"]), since)
