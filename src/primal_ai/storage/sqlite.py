"""SQLite-backed Storage implementation.

Default Storage backend for single-node deployments. Will use WAL
(Write-Ahead Logging) mode for concurrent reads and safer writes —
set via ``PRAGMA journal_mode=WAL`` during connection setup.
"""

from __future__ import annotations

from typing import Any


class SQLiteStorage:
    """SQLite-backed Storage. STUB.

    NOTE: Stub only. Phase 2 implementation will:
      - open a connection with ``PRAGMA journal_mode=WAL`` (concurrent
        readers, single writer, durable on power loss)
      - set ``PRAGMA synchronous=NORMAL`` for the WAL fsync trade-off
      - create a simple ``kv(key TEXT PRIMARY KEY, value BLOB)`` table
    """

    def __init__(self, path: str = ":memory:") -> None:
        # Phase 2: open sqlite3 connection here, then run
        # ``PRAGMA journal_mode=WAL`` and ``PRAGMA synchronous=NORMAL``.
        self.path = path

    def put(self, key: str, value: Any) -> None:
        """Store a value under a key. STUB."""
        raise NotImplementedError("SQLiteStorage.put will be implemented in Phase 2")

    def get(self, key: str) -> Any | None:
        """Return the value for a key, or ``None`` if missing. STUB."""
        raise NotImplementedError("SQLiteStorage.get will be implemented in Phase 2")

    def delete(self, key: str) -> None:
        """Remove a key. STUB."""
        raise NotImplementedError("SQLiteStorage.delete will be implemented in Phase 2")
