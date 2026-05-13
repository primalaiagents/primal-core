"""Verifier — output validation across rule-based, LLM-judge, and domain layers.

Three-layer verification stack:
  1. Rule-based (cheap, deterministic) — schema, range, format checks.
  2. LLM-judge ("Howl") — small-model verifier for semantic correctness.
  3. Domain — task-specific (ImageReward, JSON-schema, code execution, etc.).
"""

from __future__ import annotations

from typing import Any


class Verifier:
    """Top-level façade for the three-layer verification stack.

    Audits an agent output through the configured verifier chain and
    returns a structured verdict (pass / fail / uncertain + reasons).

    Example:
        verdict = Verifier.audit(output, layers=["rule", "howl", "domain"])

    NOTE: Stub only. The LLM-judge layer is named ``Howl`` internally —
    a small-model verifier kept cheap by design. Full implementation
    extracted from karis_verifier.py in Phase 2.
    """

    @classmethod
    def audit(
        cls,
        output: Any,
        layers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Audit an output through the verifier chain. STUB."""
        raise NotImplementedError("Verifier.audit will be implemented in Phase 2")
