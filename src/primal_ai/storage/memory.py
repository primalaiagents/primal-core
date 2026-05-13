"""In-memory Storage backend.

Thin dict wrapper that satisfies the ``Storage`` Protocol. Useful for
tests and as a reference implementation; not durable across processes.
"""

from __future__ import annotations

from typing import Any


class InMemoryStorage:
    """Process-local, dict-backed Storage implementation.

    Fully implemented (it's a dict). Satisfies the ``Storage`` Protocol
    in ``primal_ai.storage``.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def put(self, key: str, value: Any) -> None:
        """Store a value under a key."""
        self._data[key] = value

    def get(self, key: str) -> Any | None:
        """Return the value for a key, or ``None`` if missing."""
        return self._data.get(key)

    def delete(self, key: str) -> None:
        """Remove a key. No-op if the key does not exist."""
        self._data.pop(key, None)
