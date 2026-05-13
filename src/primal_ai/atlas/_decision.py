"""``RoutingDecision`` + ``RoutingStatus`` — the structured outcome of an ``Atlas.route`` call."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RoutingStatus(StrEnum):
    """Four-state outcome for a single routing decision (and cascade attempt).

    Values:
        SUCCESS:        A healthy candidate was chosen (and, for ``invoke``
                        / ``Cascade``, the call returned cleanly).
        FAILED:         A provider was chosen but raised during ``invoke``.
        NO_CANDIDATES:  No providers matched the filters (or no candidates
                        were given and the registry is empty).
        ALL_UNHEALTHY:  Every matching candidate is currently in cooldown.
    """

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    NO_CANDIDATES = "NO_CANDIDATES"
    ALL_UNHEALTHY = "ALL_UNHEALTHY"


@dataclass(frozen=True)
class RoutingDecision:
    """Snapshot of one ``Atlas.route`` invocation.

    Frozen because the decision is published on the event bus + recorded
    as a Trajectory step the moment it's made; downstream consumers must
    be able to rely on the snapshot not changing under their feet.

    Args:
        decision_id: uuid4 hex identifier.
        task: The task string passed to ``Atlas.route``.
        chosen_provider: The provider's name, or ``None`` on
            NO_CANDIDATES / ALL_UNHEALTHY.
        candidates_considered: Names of every provider that entered the
            health/capability filter, in declared order.
        candidates_skipped: ``(name, reason)`` for each provider rejected,
            in the order they were rejected.
        status: One of ``RoutingStatus``.
        reason: Human-readable explanation, populated on non-SUCCESS.
        started_at / ended_at: Wall-clock timestamps (``time.time()``).
        duration_ms: ``(ended_at - started_at) * 1000``.
        context: Snapshot of the context dict passed to ``route``
            (capability/tags hints, etc.).
    """

    decision_id: str
    task: str
    chosen_provider: str | None
    candidates_considered: tuple[str, ...]
    candidates_skipped: tuple[tuple[str, str], ...]
    status: RoutingStatus
    reason: str | None
    started_at: float
    ended_at: float
    duration_ms: float
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "decision_id": self.decision_id,
            "task": self.task,
            "chosen_provider": self.chosen_provider,
            "candidates_considered": list(self.candidates_considered),
            "candidates_skipped": [list(pair) for pair in self.candidates_skipped],
            "status": self.status.value,
            "reason": self.reason,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "context": dict(self.context),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RoutingDecision:
        """Rebuild a ``RoutingDecision`` from a ``to_dict`` payload."""
        return cls(
            decision_id=str(payload["decision_id"]),
            task=str(payload.get("task") or ""),
            chosen_provider=payload.get("chosen_provider"),
            candidates_considered=tuple(payload.get("candidates_considered") or ()),
            candidates_skipped=tuple(
                (str(item[0]), str(item[1]))
                for item in (payload.get("candidates_skipped") or [])
            ),
            status=RoutingStatus(payload["status"]),
            reason=payload.get("reason"),
            started_at=float(payload.get("started_at") or 0.0),
            ended_at=float(payload.get("ended_at") or 0.0),
            duration_ms=float(payload.get("duration_ms") or 0.0),
            context=dict(payload.get("context") or {}),
        )


__all__ = ["RoutingDecision", "RoutingStatus"]
