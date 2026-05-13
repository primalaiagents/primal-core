"""LLM-judge verifier — small-model semantic verifier, codename "Howl".

The middle verification layer. Uses a deliberately small, cheap model
to judge semantic correctness of agent outputs. Kept small on purpose:
verification has to be cheaper than the action it verifies.
"""

from __future__ import annotations

from typing import Any


class Howl:
    """Small-model LLM judge for semantic output verification. STUB.

    Named ``Howl`` for the wolf motif — a watchful, cheap verifier that
    barks loudly when something looks off but doesn't try to be smarter
    than the agent it's judging.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def judge(
        cls,
        output: Any,
        criteria: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Judge an output against semantic criteria. STUB."""
        raise NotImplementedError("Howl.judge will be implemented in Phase 2")
