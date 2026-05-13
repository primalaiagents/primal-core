"""Postgres-backed Storage implementation.

For multi-node deployments. Will use ``psycopg`` (v3) with a connection
pool and JSONB columns for flexible value storage.
"""

from __future__ import annotations

from typing import Any


class PostgresStorage:
    """Postgres-backed Storage. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def put(self, key: str, value: Any) -> None:
        """Store a value under a key. STUB."""
        raise NotImplementedError("PostgresStorage.put will be implemented in Phase 2")

    def get(self, key: str) -> Any | None:
        """Return the value for a key, or ``None`` if missing. STUB."""
        raise NotImplementedError("PostgresStorage.get will be implemented in Phase 2")

    def delete(self, key: str) -> None:
        """Remove a key. STUB."""
        raise NotImplementedError("PostgresStorage.delete will be implemented in Phase 2")
