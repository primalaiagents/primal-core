"""Domain-specific verifier layers — JSON Schema, regex, and the user-extension surface.

Two concrete domain verifiers ship in the MVP:

  - :class:`JSONSchemaVerifier` — validates structured outputs against
    PRIMAL's shared JSON Schema subset (the same one Guardian's
    ``SchemaValidator`` uses).
  - :class:`RegexMatchVerifier` — pattern allow/deny lists over the
    stringified output.

The :class:`DomainVerifier` Protocol marks domain-specific layers
conceptually — it has the same shape as ``VerifierLayer`` but communicates
"this is task-specific, not universal".
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

from primal_ai._jsonschema import first_error
from primal_ai.verifier._verdict import Verdict, VerdictStatus


@runtime_checkable
class DomainVerifier(Protocol):
    """Structural contract for a domain-specific verifier layer.

    Same shape as :class:`~primal_ai.verifier._protocol.VerifierLayer`,
    re-exported here as a documentation surface so users writing a new
    domain verifier have a clear hook.
    """

    name: str

    def verify(self, target: Any) -> Verdict:
        """Return a ``Verdict`` for ``target``."""
        ...


class JSONSchemaVerifier:
    """Validate the audit target against PRIMAL's shared JSON Schema subset.

    The supported subset is the same one Guardian's ``SchemaValidator``
    enforces: ``type``, ``required``, ``properties``. Anything outside
    the subset is silently ignored — callers needing richer schemas
    should reach for ``jsonschema`` in user code above this boundary.

    Args:
        schema: A JSON Schema-style dict.
        name: Verifier name. Defaults to ``"json_schema"``.

    Example:
        >>> from primal_ai import JSONSchemaVerifier
        >>> layer = JSONSchemaVerifier(
        ...     schema={"type": "object", "required": ["answer"]},
        ... )
        >>> layer.verify({"answer": "tokyo"}).status.value
        'PASS'
    """

    accepts_trajectory: bool = False

    def __init__(self, schema: dict[str, Any], name: str = "json_schema") -> None:
        self.schema = schema
        self.name = name

    def verify(self, target: Any) -> Verdict:
        """Validate ``target`` against the configured schema."""
        err = first_error(self.schema, target)
        if err is None:
            return Verdict(
                verifier_name=self.name,
                status=VerdictStatus.PASS,
                confidence=1.0,
                reasons=["matches schema"],
                details={"schema": self.schema},
            )
        return Verdict(
            verifier_name=self.name,
            status=VerdictStatus.FAIL,
            confidence=1.0,
            reasons=[err],
            details={"schema": self.schema, "error": err},
        )


class RegexMatchVerifier:
    """Pattern allow/deny verifier over the stringified output.

    PASS iff every ``must_match`` pattern hits the stringified target
    AND no ``must_not_match`` pattern hits. Otherwise FAIL, with one
    ``reasons`` entry per missed-required or hit-forbidden pattern.

    Args:
        must_match: Regex patterns that MUST all be present in the output.
        must_not_match: Regex patterns that must NOT appear in the output.
        name: Verifier name. Defaults to ``"regex_match"``.

    Example:
        >>> layer = RegexMatchVerifier(must_match=[r"\\bOK\\b"], must_not_match=[r"ERROR"])
        >>> layer.verify("status: OK").status.value
        'PASS'
    """

    accepts_trajectory: bool = False

    def __init__(
        self,
        must_match: list[str] | None = None,
        must_not_match: list[str] | None = None,
        name: str = "regex_match",
    ) -> None:
        self.must_match = list(must_match or [])
        self.must_not_match = list(must_not_match or [])
        self.name = name
        self._must_match_re = [re.compile(p) for p in self.must_match]
        self._must_not_match_re = [re.compile(p) for p in self.must_not_match]

    def verify(self, target: Any) -> Verdict:
        """Apply allow/deny pattern lists to the stringified target."""
        text = target if isinstance(target, str) else str(target)
        reasons: list[str] = []
        for pattern, compiled in zip(self.must_match, self._must_match_re, strict=True):
            if not compiled.search(text):
                reasons.append(f"required pattern not found: {pattern!r}")
        for pattern, compiled in zip(self.must_not_match, self._must_not_match_re, strict=True):
            if compiled.search(text):
                reasons.append(f"forbidden pattern matched: {pattern!r}")

        if not reasons:
            return Verdict(
                verifier_name=self.name,
                status=VerdictStatus.PASS,
                confidence=1.0,
                reasons=["all patterns matched/avoided as required"],
                details={
                    "must_match": self.must_match,
                    "must_not_match": self.must_not_match,
                },
            )
        return Verdict(
            verifier_name=self.name,
            status=VerdictStatus.FAIL,
            confidence=1.0,
            reasons=reasons,
            details={
                "must_match": self.must_match,
                "must_not_match": self.must_not_match,
            },
        )


__all__ = ["DomainVerifier", "JSONSchemaVerifier", "RegexMatchVerifier"]
