"""Storage — pluggable persistence layer for PRIMAL.

Defines a minimal ``Storage`` Protocol that any backend (SQLite, Postgres,
Redis, in-memory) implements. Higher pillars depend only on the Protocol
so backends can be swapped without changes upstream.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from primal_ai.storage.memory import InMemoryStorage
from primal_ai.storage.postgres import PostgresStorage
from primal_ai.storage.redis_store import RedisStorage
from primal_ai.storage.sqlite import SQLiteStorage


@runtime_checkable
class Storage(Protocol):
    """Minimal key/value storage Protocol.

    All PRIMAL storage backends implement this interface. Values are
    typed as ``Any`` because different pillars persist different
    JSON-serializable shapes (trajectories, profiles, bandit posteriors).
    """

    def put(self, key: str, value: Any) -> None:
        """Store a value under a key."""
        ...

    def get(self, key: str) -> Any | None:
        """Return the value for a key, or ``None`` if missing."""
        ...

    def delete(self, key: str) -> None:
        """Remove a key. No-op if the key does not exist."""
        ...


__all__ = [
    "InMemoryStorage",
    "PostgresStorage",
    "RedisStorage",
    "SQLiteStorage",
    "Storage",
]
