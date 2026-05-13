"""``Verdict`` dataclass and ``VerdictStatus`` enum — the unit of a verifier layer's output."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class VerdictStatus(StrEnum):
    """Three-state status for a verifier verdict.

    Values:
        PASS:       The layer is confident the output is correct.
        FAIL:       The layer is confident the output is incorrect.
        UNCERTAIN:  The layer didn't have enough signal to commit either
                    way. UNCERTAIN is honest — it tells the aggregator
                    "I checked but I'm not sure".
    """

    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class Verdict:
    """The output of one verifier layer.

    Verdicts are immutable (``frozen=True``) so once a layer hands its
    verdict to the aggregator, nothing downstream can silently rewrite
    it. JSON-serializable via :meth:`to_dict` so verdicts can flow into
    Trajectories or external systems without extra encoding.

    Args:
        verifier_name: Name of the layer that produced this verdict.
        status: One of ``VerdictStatus.PASS``, ``FAIL``, or ``UNCERTAIN``.
        confidence: 0.0–1.0. Rule-based layers usually return ``1.0``;
            LLM-judge layers populate this from model output.
        reasons: Ordered list of human-readable reason strings. The
            first reason is typically the most useful for log output.
        details: Verifier-specific structured payload (rule names that
            fired, schema path of the failure, raw LLM response, etc.).
        cost: Optional dollar cost of producing this verdict (set by
            LLM-judge layers; left ``None`` by rule-based ones).
        latency_ms: Optional wall-clock latency, useful for budget tuning.
    """

    verifier_name: str
    status: VerdictStatus
    confidence: float
    reasons: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    cost: float | None = None
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of this verdict."""
        return {
            "verifier_name": self.verifier_name,
            "status": self.status.value,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "details": dict(self.details),
            "cost": self.cost,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Verdict:
        """Rebuild a ``Verdict`` from a ``to_dict`` payload."""
        return cls(
            verifier_name=str(payload["verifier_name"]),
            status=VerdictStatus(payload["status"]),
            confidence=float(payload.get("confidence", 0.0)),
            reasons=list(payload.get("reasons") or []),
            details=dict(payload.get("details") or {}),
            cost=payload.get("cost"),
            latency_ms=payload.get("latency_ms"),
        )


__all__ = ["Verdict", "VerdictStatus"]
