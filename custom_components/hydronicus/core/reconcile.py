"""The level-triggered reconciler: from the desired state to the actions to send now.

On every evaluation the runtime passes the desired state from ``step()``, the
observed state of every output, and the reconciler's own State. The reconciler
compares desired and observed state and returns the actions to send, in
dependency order: the source request off, pumps off, valves open, valves close,
pumps on, the source mode, and the source request on. The waits between those
steps, such as a valve that stays open until its running pump is observed off,
are already part of the desired state that ``step()`` computes.

A service call that returns is not a confirmation; only a later observation is.
The runtime sends each action outside its lock with a timeout of
``CALL_TIMEOUT`` seconds, so an action sent longer ago than that has either
taken effect or never will. At most one call per output is in flight: a new
target waits until the previous call is observed or has timed out, and
``step_view`` shows ``step()`` the calls still in flight. An action whose target
is still unmet is sent again after a backoff that doubles from ``BACKOFF_MIN``
to ``BACKOFF_MAX``, and an output is reported for a Repair once
``REPAIR_AFTER`` attempts have failed.

In Dry run nothing is sent. The reconciler records each action as proposed and
treats it as observed at once, and ``step_view`` shows ``step()`` those proposed
states, so the virtual sequence advances exactly as it would live.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final

from .model import (
    Desired,
    OptionTarget,
    OutputRole,
    OutputTarget,
    Plant,
    SwitchTarget,
    ValueTarget,
)
from .step import (
    CALL_TIMEOUT,
    TICK,
    Observations,
    OptionState,
    OutputState,
    Sent,
    SwitchState,
    ValueState,
    satisfies,
    value_of,
)

__all__ = [
    "BACKOFF_MAX",
    "BACKOFF_MIN",
    "CALL_TIMEOUT",
    "REPAIR_AFTER",
    "Action",
    "Attempt",
    "ReconcileState",
    "Reconciled",
    "backoff",
    "reconcile",
    "step_view",
    "target_from_dict",
    "target_to_dict",
]

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
                    "target": target_to_dict(attempt.target),
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
                    target=target_from_dict(value["target"]),
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
    """
    roles = plant.outputs()
    if not live:
        return _dry_run(roles, desired, outputs, state, now, armed)
    attempts: dict[str, Attempt] = {}
    send: list[tuple[int, Action]] = []
    retries: list[float] = []
    repairs: set[str] = set()
    for entity, role in roles.items():
        target = desired.outputs.get(entity)
        observed = outputs.get(entity)
        attempt = state.attempts.get(entity)
        if attempt is not None and satisfies(observed, attempt.target):
            attempt = None
        if attempt is not None and now < attempt.sent_at + CALL_TIMEOUT:
            # In flight, even to an output just disarmed: ``step()`` must still
            # see it, and nothing else goes out until it acts or times out.
            attempts[entity] = attempt
            retries.append(attempt.sent_at + CALL_TIMEOUT + TICK)
            if attempt.count - 1 >= REPAIR_AFTER and target == attempt.target:
                repairs.add(entity)
            continue
        if target is None or entity not in armed:
            continue
        if satisfies(observed, target):
            continue
        if attempt is not None and attempt.target != target:
            attempt = None
        failed = 0 if attempt is None else attempt.count
        if failed >= REPAIR_AFTER:
            repairs.add(entity)
        if observed is None or value_of(observed) is None:
            # Unavailable: nothing can reach it; its return is a change that re-evaluates.
            if attempt is not None:
                attempts[entity] = attempt
            continue
        if attempt is not None and now < attempt.sent_at + backoff(attempt.count):
            attempts[entity] = attempt
            retries.append(attempt.sent_at + backoff(attempt.count) + TICK)
            continue
        attempts[entity] = Attempt(target, failed + 1, now)
        retries.append(now + CALL_TIMEOUT + TICK)
        send.append((_phase(role, target), Action(entity, target)))
    send.sort(key=lambda item: item[0])
    return Reconciled(
        state=ReconcileState(attempts=attempts),
        send=tuple(action for _, action in send),
        retry_at=min(retries) if retries else None,
        repairs=frozenset(repairs),
    )


def backoff(count: int) -> float:
    """Seconds after the ``count``-th send before the target is sent again."""
    return float(min(BACKOFF_MIN * 2 ** (count - 1), BACKOFF_MAX))


def _phase(role: OutputRole, target: OutputTarget) -> int:
    """The position of a call in one batch: stop from the source down, start from valves up."""
    on = not isinstance(target, SwitchTarget) or target.on
    match role:
        case OutputRole.SOURCE_REQUEST:
            return 6 if on else 0
        case OutputRole.PUMP:
            return 4 if on else 1
        case OutputRole.VALVE:
            return 2 if on else 3
        case _:
            return 5


def _dry_run(
    roles: Mapping[str, OutputRole],
    desired: Desired,
    outputs: Mapping[str, OutputState],
    state: ReconcileState,
    now: float,
    armed: frozenset[str],
) -> Reconciled:
    """Propose instead of sending, and count each proposal as observed at once."""
    proposals = {
        entity: proposed
        for entity, proposed in state.dry_run.items()
        if entity in roles and value_of(proposed) != _observed_value(outputs.get(entity))
    }
    proposed: list[tuple[int, Action]] = []
    for entity, role in roles.items():
        target = desired.outputs.get(entity)
        if target is None or entity not in armed:
            continue
        if satisfies(proposals.get(entity, outputs.get(entity)), target):
            continue
        proposals[entity] = _as_observed(target, now)
        proposed.append((_phase(role, target), Action(entity, target)))
    proposed.sort(key=lambda item: item[0])
    return Reconciled(
        state=ReconcileState(dry_run=proposals),
        proposed=tuple(action for _, action in proposed),
    )


def _observed_value(state: OutputState | None) -> bool | str | float | None:
    return None if state is None else value_of(state)


def _as_observed(target: OutputTarget, now: float) -> OutputState:
    match target:
        case SwitchTarget(on=on):
            return SwitchState(on, now)
        case OptionTarget(option=option):
            return OptionState(option, now)
        case ValueTarget(value=value):
            return ValueState(value, now)


def step_view(observations: Observations, state: ReconcileState) -> Observations:
    """Return the observations ``step()`` sees: the calls in flight, and Dry run proposals.

    The proposed states apply only while Control equipment is off, so the first
    evaluation after it turns on already sees the real outputs.
    """
    sent = {
        entity: Sent(attempt.target, attempt.sent_at) for entity, attempt in state.attempts.items()
    }
    outputs = observations.outputs
    if not observations.control and state.dry_run:
        outputs = {**outputs, **state.dry_run}
    if not sent and outputs is observations.outputs:
        return observations
    return replace(observations, outputs=outputs, sent=sent)


# Persistence


def target_to_dict(target: OutputTarget) -> dict[str, Any]:
    """Return JSON-friendly data for a target, which ``target_from_dict`` reads back."""
    match target:
        case SwitchTarget(on=on):
            return {"on": on}
        case OptionTarget(option=option):
            return {"option": option}
        case ValueTarget(value=value):
            return {"value": value}


def target_from_dict(data: Mapping[str, Any]) -> OutputTarget:
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
