"""Harness discovery — Tool RAG over the available tool catalog.

Embedding-based lookup over registered tools so an agent can ask
"what tools can do X?" and get a ranked, callable shortlist instead of
having every tool jammed into its system prompt.
"""

from __future__ import annotations

from typing import Any


class Discovery:
    """Tool RAG — semantic search over the tool catalog. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def search(cls, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Return the top-k tools matching a natural-language query. STUB."""
        raise NotImplementedError("Discovery.search will be implemented in Phase 2")
