"""Harness — health checks, scheduling, tool discovery, and dynamic loading.

The runtime substrate that keeps PRIMAL agents alive: liveness probes,
periodic jobs, MCP-style tool discovery (Tool RAG), and hot-loading of
new agents/tools without restart.
"""

from __future__ import annotations

from typing import Any


class Harness:
    """Runtime substrate for agents and tools. STUB.

    NOTE: Stub only. Full implementation extracted from karis_harness.py in Phase 2.
    """

    @classmethod
    def start(cls, config: dict[str, Any] | None = None) -> None:
        """Start the harness runtime. STUB."""
        raise NotImplementedError("Harness.start will be implemented in Phase 2")

    @classmethod
    def stop(cls) -> None:
        """Stop the harness runtime. STUB."""
        raise NotImplementedError("Harness.stop will be implemented in Phase 2")
