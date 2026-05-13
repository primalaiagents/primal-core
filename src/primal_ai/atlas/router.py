"""Atlas router — the core selection engine behind ``Atlas.route``.

Combines bandit scores, cascade health, and policy constraints into a
single ranked decision. STUB.
"""

from __future__ import annotations

from typing import Any


class Router:
    """Provider selection engine. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def select(
        cls,
        candidates: list[str],
        context: dict[str, Any] | None = None,
    ) -> str:
        """Select the best candidate from a ranked list. STUB."""
        raise NotImplementedError("Router.select will be implemented in Phase 2")
