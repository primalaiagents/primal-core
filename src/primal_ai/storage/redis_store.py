"""Redis-backed Storage implementation.

For low-latency ephemeral state (bandit posteriors, rate-limit counters,
recent-trajectory cache).
"""

from __future__ import annotations

from typing import Any


class RedisStorage:
    """Redis-backed Storage. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        self.url = url

    def put(self, key: str, value: Any) -> None:
        """Store a value under a key. STUB."""
        raise NotImplementedError("RedisStorage.put will be implemented in Phase 2")

    def get(self, key: str) -> Any | None:
        """Return the value for a key, or ``None`` if missing. STUB."""
        raise NotImplementedError("RedisStorage.get will be implemented in Phase 2")

    def delete(self, key: str) -> None:
        """Remove a key. STUB."""
        raise NotImplementedError("RedisStorage.delete will be implemented in Phase 2")
