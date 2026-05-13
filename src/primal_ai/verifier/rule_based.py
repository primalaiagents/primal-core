"""``RuleBasedVerifier`` — deterministic, composable, no-LLM verification layer.

Each rule is a callable returning ``(status, reason)``. Rules see whatever
``Verifier.audit`` hands them: a raw output, or — when
``accepts_trajectory=True`` — the full ``Trajectory``. The layer's overall
verdict aggregates its rules with the same rule the top-level facade uses
(any FAIL → FAIL, all PASS → PASS, otherwise UNCERTAIN).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from primal_ai.verifier._verdict import Verdict, VerdictStatus

Rule = Callable[[Any], tuple[VerdictStatus | str, str]]


def _coerce(status: VerdictStatus | str) -> VerdictStatus:
    """Normalize the loose-typed return of a rule into a ``VerdictStatus``."""
    if isinstance(status, VerdictStatus):
        return status
    upper = status.strip().upper()
    if upper not in {"PASS", "FAIL", "UNCERTAIN"}:
        return VerdictStatus.UNCERTAIN
    return VerdictStatus(upper)


class RuleBasedVerifier:
    """A verifier layer composed of one or more deterministic rule callables.

    Args:
        rules: Iterable of rule callables. Each callable takes the audit
            target and returns ``(status, reason)`` where ``status`` is
            either a ``VerdictStatus`` or one of ``"pass" / "fail" /
            "uncertain"`` (case-insensitive).
        name: Identifier surfaced in ``Verdict.verifier_name``. Defaults
            to ``"rule_based"``.
        accepts_trajectory: When ``True``, the layer receives a
            ``Trajectory`` instance instead of the raw output. Rules can
            then call ``target.find_steps(...)`` or ``target.summary()``.

    Example:
        >>> from primal_ai import RuleBasedVerifier, VerdictStatus
        >>> def has_answer(out):
        ...     return ("pass", "answer present") if "answer" in out else ("fail", "no answer")
        >>> layer = RuleBasedVerifier(rules=[has_answer])
        >>> layer.verify({"answer": "tokyo"}).status == VerdictStatus.PASS
        True
    """

    def __init__(
        self,
        rules: Iterable[Rule] | None = None,
        *,
        name: str = "rule_based",
        accepts_trajectory: bool = False,
    ) -> None:
        self.name = name
        self.accepts_trajectory = accepts_trajectory
        self.rules: list[Rule] = list(rules) if rules is not None else []

    def verify(self, target: Any) -> Verdict:
        """Run every rule against ``target`` and aggregate into one verdict."""
        if not self.rules:
            return Verdict(
                verifier_name=self.name,
                status=VerdictStatus.UNCERTAIN,
                confidence=0.0,
                reasons=["no rules configured"],
                details={"rule_count": 0},
            )

        statuses: list[VerdictStatus] = []
        reasons: list[str] = []
        for rule in self.rules:
            raw_status, reason = rule(target)
            statuses.append(_coerce(raw_status))
            reasons.append(reason)

        agg = _aggregate(statuses)
        return Verdict(
            verifier_name=self.name,
            status=agg,
            confidence=1.0,  # deterministic — full confidence in our own answer
            reasons=reasons,
            details={
                "rule_count": len(self.rules),
                "statuses": [s.value for s in statuses],
            },
        )


def _aggregate(statuses: list[VerdictStatus]) -> VerdictStatus:
    """Apply the canonical aggregation rule across rule statuses."""
    if not statuses:
        return VerdictStatus.UNCERTAIN
    saw_pass = False
    saw_uncertain = False
    for s in statuses:
        if s == VerdictStatus.FAIL:
            return VerdictStatus.FAIL
        if s == VerdictStatus.PASS:
            saw_pass = True
        else:
            saw_uncertain = True
    if saw_pass and not saw_uncertain:
        return VerdictStatus.PASS
    return VerdictStatus.UNCERTAIN


__all__ = ["RuleBasedVerifier", "Rule"]
