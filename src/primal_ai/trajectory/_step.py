"""``Step`` dataclass and ``StepKind`` enum — the atomic unit of a trajectory."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class StepKind(StrEnum):
    """Canonical step kinds for typed iteration and filtering.

    ``Step.kind`` is a plain ``str`` so users may add custom kinds outside
    this enum (e.g. ``"CUSTOM_AUDIT"``); the enum just bundles the values
    PRIMAL itself produces and consumes. Each enum value matches its name,
    so JSON serialization round-trips cleanly.

    Values:
        INPUT, OUTPUT:                    user-facing request/response bookends.
        TOOL_CALL, TOOL_RESULT:           paired tool invocations.
        LLM_CALL, LLM_RESULT:             paired model invocations.
        ERROR, RETRY:                     failure and recovery markers.
        POLICY_VIOLATION:                 emitted by ``Guardian.escalate``.
    """

    INPUT = "INPUT"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    LLM_CALL = "LLM_CALL"
    LLM_RESULT = "LLM_RESULT"
    ERROR = "ERROR"
    RETRY = "RETRY"
    OUTPUT = "OUTPUT"
    POLICY_VIOLATION = "POLICY_VIOLATION"


def _new_step_id() -> str:
    """Return a fresh uuid4-hex step identifier."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Step:
    """One atom of a trajectory — a single recorded event.

    ``Step`` is immutable (``frozen=True``) so once a recorder hands a
    step to the trajectory it can never be silently rewritten. Timing
    is captured twice: ``timestamp`` (``time.time()``) for human-readable
    wall-clock reporting, and ``monotonic`` (``time.monotonic()``) for
    accurate durations across wall-clock adjustments.

    Args:
        kind: A ``StepKind`` value (or a custom string for extensions).
        data: Kind-specific JSON-serializable payload.
        cost: Optional dollar cost — surfaced in ``Trajectory.summary``
            and visible to ``DollarCap``.
        latency_ms: Optional latency for paired (call → result) steps.
        parent_step_id: Optional reference to an earlier step's ``step_id``,
            used to chain results back to the call that produced them.
        step_id: Auto-generated uuid4 hex. Users who need globally
            sortable IDs can pass their own (e.g. a ULID).
        timestamp: Wall-clock time at construction (``time.time()``).
        monotonic: Monotonic time at construction (``time.monotonic()``).
    """

    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    cost: float | None = None
    latency_ms: float | None = None
    parent_step_id: str | None = None
    step_id: str = field(default_factory=_new_step_id)
    timestamp: float = field(default_factory=time.time)
    monotonic: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of this step."""
        return {
            "step_id": self.step_id,
            "kind": self.kind,
            "data": self.data,
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "parent_step_id": self.parent_step_id,
            "timestamp": self.timestamp,
            "monotonic": self.monotonic,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Step:
        """Rebuild a ``Step`` from a ``to_dict`` payload (or a partial dict)."""
        return cls(
            kind=str(payload["kind"]),
            data=dict(payload.get("data") or {}),
            cost=payload.get("cost"),
            latency_ms=payload.get("latency_ms"),
            parent_step_id=payload.get("parent_step_id"),
            step_id=str(payload.get("step_id") or _new_step_id()),
            timestamp=float(payload.get("timestamp") or time.time()),
            monotonic=float(payload.get("monotonic") or time.monotonic()),
        )


__all__ = ["Step", "StepKind"]
