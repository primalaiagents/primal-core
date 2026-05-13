"""``VerifierLayer`` Protocol — the structural contract every layer satisfies."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from primal_ai.verifier._verdict import Verdict


@runtime_checkable
class VerifierLayer(Protocol):
    """Structural contract for one layer in the verifier pipeline.

    Required:
        name (str): Stable identifier surfaced in ``Verdict.verifier_name``.
        verify(target) -> Verdict: Inspect ``target`` and return a verdict.

    Optional:
        accepts_trajectory (bool, default False): If ``True``, the
            facade hands the layer a ``Trajectory`` instance; otherwise
            it hands the raw output value (extracted from the trajectory's
            last OUTPUT step when a trajectory is passed at the top
            level). The class attribute is read once before ``verify``;
            instances may set it explicitly to override the default.

    Example:
        class IsTruthy:
            name = "is_truthy"
            accepts_trajectory = False

            def verify(self, target):
                from primal_ai import Verdict, VerdictStatus
                if target:
                    return Verdict(
                        verifier_name=self.name,
                        status=VerdictStatus.PASS,
                        confidence=1.0,
                        reasons=["non-empty output"],
                    )
                return Verdict(
                    verifier_name=self.name,
                    status=VerdictStatus.FAIL,
                    confidence=1.0,
                    reasons=["output was falsy"],
                )
    """

    name: str

    def verify(self, target: Any) -> Verdict:
        """Return a ``Verdict`` for ``target``."""
        ...


__all__ = ["VerifierLayer"]
