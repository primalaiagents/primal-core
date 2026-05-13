"""Atlas — model and tool routing with bandits and failure-aware cascades.

Decides *which* model or tool to use for *which* task at *which* moment.
Uses multi-armed bandit exploration to learn what works, plus a cooldown
cascade so failing providers get sidelined automatically.
"""

from __future__ import annotations

from typing import Any


class Atlas:
    """Model + tool router with bandit-driven selection.

    Routes a request to the best provider given recent performance,
    latency, cost, and current health. Falls back through a configured
    cascade when the chosen provider fails.

    Example:
        provider = Atlas.route(task="summarize", candidates=["gpt-4o", "haiku"])

    NOTE: Stub only. Full implementation extracted from karis_atlas.py in Phase 2.
    """

    @classmethod
    def route(
        cls,
        task: str,
        candidates: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Route a task to the best candidate provider. STUB."""
        raise NotImplementedError("Atlas.route will be implemented in Phase 2")
