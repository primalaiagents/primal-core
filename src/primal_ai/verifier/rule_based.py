"""Rule-based verifier — cheap, deterministic checks (schema, range, format).

The first verification layer. Runs before more expensive LLM-judge or
domain-specific checks because it's fast and catches obvious failures.
"""

from __future__ import annotations

from typing import Any


class RuleBasedVerifier:
    """Deterministic rule-based output verifier. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def check(cls, output: Any, rules: list[str] | None = None) -> dict[str, Any]:
        """Run rule-based checks on an output. STUB."""
        raise NotImplementedError("RuleBasedVerifier.check will be implemented in Phase 2")
