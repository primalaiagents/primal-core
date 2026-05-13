"""Harness loader — dynamic registration and hot-loading of agents/tools.

Picks up new agent or tool definitions from disk / a registry and makes
them callable without restarting the harness.
"""

from __future__ import annotations

from typing import Any


class Loader:
    """Dynamic agent / tool loader. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def load(cls, spec: str | dict[str, Any]) -> Any:
        """Load an agent or tool from a path, URI, or spec dict. STUB."""
        raise NotImplementedError("Loader.load will be implemented in Phase 2")

    @classmethod
    def unload(cls, name: str) -> None:
        """Unload a previously registered agent or tool. STUB."""
        raise NotImplementedError("Loader.unload will be implemented in Phase 2")
