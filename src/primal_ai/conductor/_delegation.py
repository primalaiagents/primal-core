"""``DelegationResult`` + ``DelegationStatus`` — the structured outcome of one delegation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DelegationStatus(StrEnum):
    """Four-state outcome for a single delegation.

    Values:
        SUCCESS: The agent invoked cleanly and returned an output.
        FAILED:  The agent raised an exception.
        REFUSED: No agent matched the requested capability, or the agent
                 declined the delegation up front (e.g. input-schema
                 mismatch). Distinct from FAILED so downstream consumers
                 can treat "wrong agent" differently from "agent broke".
        TIMEOUT: The agent didn't return within ``timeout_seconds``.
    """

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUSED = "REFUSED"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class DelegationResult:
    """Structured record of one delegation attempt.

    Frozen because the Conductor never mutates a result after returning
    it; downstream consumers (Trajectory, EventBus subscribers) can rely
    on the snapshot.

    Args:
        delegation_id: uuid4 hex identifier.
        from_agent: Name of the calling agent, or ``None`` if the user
            called ``Conductor.delegate`` directly.
        to_agent: Name of the agent that handled (or would have handled)
            the delegation.
        capability: Requested capability name, or ``None`` when the user
            picked the target agent by instance instead of by capability.
        task: The task description string.
        input: Input passed to ``agent.invoke``. JSON-serializable.
        output: Output returned by ``agent.invoke``. ``None`` on
            non-SUCCESS results.
        status: One of ``DelegationStatus``.
        reason: Human-readable explanation for non-SUCCESS results.
        started_at / ended_at: Wall-clock timestamps (``time.time()``).
        duration_ms: ``(ended_at - started_at) * 1000``.
    """

    delegation_id: str
    from_agent: str | None
    to_agent: str
    capability: str | None
    task: str
    input: Any
    output: Any
    status: DelegationStatus
    reason: str | None
    started_at: float
    ended_at: float
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "delegation_id": self.delegation_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "capability": self.capability,
            "task": self.task,
            "input": self.input,
            "output": self.output,
            "status": self.status.value,
            "reason": self.reason,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DelegationResult:
        """Rebuild a ``DelegationResult`` from a ``to_dict`` payload."""
        return cls(
            delegation_id=str(payload["delegation_id"]),
            from_agent=payload.get("from_agent"),
            to_agent=str(payload["to_agent"]),
            capability=payload.get("capability"),
            task=str(payload.get("task") or ""),
            input=payload.get("input"),
            output=payload.get("output"),
            status=DelegationStatus(payload["status"]),
            reason=payload.get("reason"),
            started_at=float(payload.get("started_at") or 0.0),
            ended_at=float(payload.get("ended_at") or 0.0),
            duration_ms=float(payload.get("duration_ms") or 0.0),
        )


__all__ = ["DelegationResult", "DelegationStatus"]
