"""SQLite-backed ``Storage`` implementation.

The default durable backend for single-node deployments. Stores JSON-encoded
values in a single ``kv`` table under WAL mode, with one ``sqlite3.Connection``
per thread (lazily created and cached on ``threading.local``). Survives
process restart, safe under concurrent writers, no external dependencies.

Values must be JSON-serializable (dict / list / str / number / bool /
``None`` and combinations). Anything else raises ``TypeError`` at ``put``
time — there is no silent ``str()`` fallback because strings that look
like ``datetime`` objects but aren't would be a footgun. Callers that
need richer types should encode/decode themselves above the Storage
boundary, or upgrade to ``PostgresStorage`` when JSONB lands in Phase 2.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import suppress
from pathlib import Path
from types import TracebackType
from typing import Any, cast

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key        TEXT PRIMARY KEY NOT NULL,
    value      TEXT NOT NULL,
    updated_at REAL NOT NULL
)
"""

_UPSERT = (
    "INSERT INTO kv(key, value, updated_at) VALUES (?, ?, ?) "
    "ON CONFLICT(key) DO UPDATE SET "
    "value = excluded.value, updated_at = excluded.updated_at"
)
_SELECT = "SELECT value FROM kv WHERE key = ?"
_DELETE = "DELETE FROM kv WHERE key = ?"
_LIST_KEYS = "SELECT key FROM kv WHERE key LIKE ? || '%' ORDER BY key"


class SQLiteStorage:
    """Durable key/value store backed by SQLite + WAL.

    Values are JSON-encoded; any JSON-serializable Python value (dict,
    list, str, number, bool, None, and combinations thereof) round-trips
    cleanly. Non-serializable values raise ``TypeError`` at ``put`` time.

    Each thread that touches the store gets its own ``sqlite3.Connection``
    (lazily created on first use, cached on ``threading.local``). This
    avoids the cross-thread Connection sharing pitfall while keeping
    per-call latency low.

    Args:
        path: Filesystem path to the SQLite database. ``":memory:"`` is
            accepted for tests. A non-existent parent directory is created
            automatically.
        busy_timeout_ms: How long ``sqlite3`` waits when the database is
            locked before raising ``OperationalError``. Default 5000ms
            matches the KARIS pattern.
        check_same_thread: Forwarded to ``sqlite3.connect``. Default
            ``False`` because we never share a connection across threads
            anyway — defense in depth, not the primary mechanism.

    Example:
        >>> from primal_ai.storage import SQLiteStorage
        >>> with SQLiteStorage("primal.db") as store:
        ...     store.put("agent:1", {"name": "alpha"})
        ...     store.get("agent:1")
        {'name': 'alpha'}
    """

    def __init__(
        self,
        path: str | Path,
        *,
        busy_timeout_ms: int = 5000,
        check_same_thread: bool = False,
    ) -> None:
        self.path: str = self._resolve_path(path)
        self._busy_timeout_ms = busy_timeout_ms
        self._check_same_thread = check_same_thread

        # Per-thread connection cache + the set of every connection we've
        # opened (so ``close`` can shut them all down).
        self._local = threading.local()
        self._all_connections: list[sqlite3.Connection] = []
        self._connections_lock = threading.Lock()

        # Open a primary connection up front so the schema + PRAGMAs are
        # established immediately and any path/permission problems fail
        # loudly at construction time rather than first use.
        self._connection_for_thread()

    # ──────────────────────────────────────────────────────────────────
    # Public Storage Protocol
    # ──────────────────────────────────────────────────────────────────

    def put(self, key: str, value: Any) -> None:
        """Store ``value`` under ``key``. UPSERT — overwrites any existing entry.

        Raises:
            TypeError: If ``value`` isn't JSON-serializable. No silent
                ``str()`` fallback — encode richer types yourself above
                the Storage boundary.
        """
        try:
            encoded = json.dumps(value, ensure_ascii=False)
        except TypeError as exc:
            raise TypeError(
                f"SQLiteStorage.put: value for key {key!r} is not JSON-serializable: {exc}",
            ) from exc
        conn = self._connection_for_thread()
        with conn:
            conn.execute(_UPSERT, (key, encoded, time.time()))

    def get(self, key: str) -> Any | None:
        """Return the JSON-decoded value for ``key``, or ``None`` if missing."""
        conn = self._connection_for_thread()
        cur = conn.execute(_SELECT, (key,))
        row = cur.fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def delete(self, key: str) -> None:
        """Remove ``key`` if present. No-op if the key doesn't exist."""
        conn = self._connection_for_thread()
        with conn:
            conn.execute(_DELETE, (key,))

    def list_keys(self, prefix: str = "") -> list[str]:
        """Return every key starting with ``prefix``, sorted ascending.

        SQLite-only extension to the ``Storage`` Protocol — useful for
        bulk operations like loading every trajectory under a known
        key prefix.
        """
        conn = self._connection_for_thread()
        cur = conn.execute(_LIST_KEYS, (prefix,))
        return [row[0] for row in cur.fetchall()]

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close every connection this store has opened. Idempotent."""
        with self._connections_lock:
            for conn in self._all_connections:
                with suppress(sqlite3.Error):
                    conn.close()
            self._all_connections.clear()
        # Drop the per-thread cache too — any further use on this thread
        # will open a fresh connection lazily.
        self._local = threading.local()

    def __enter__(self) -> SQLiteStorage:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ──────────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_path(path: str | Path) -> str:
        """Normalize ``path`` to a string; create the parent dir if needed."""
        p = path if isinstance(path, Path) else Path(path)
        if str(p) == ":memory:":
            return ":memory:"
        # Create the parent directory if it doesn't exist. For relative
        # paths with no directory component, ``p.parent`` is ``"."`` which
        # already exists — ``mkdir(exist_ok=True)`` makes this a no-op.
        parent = p.parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        return str(p)

    def _connection_for_thread(self) -> sqlite3.Connection:
        """Return this thread's connection, opening it lazily on first use."""
        existing = getattr(self._local, "conn", None)
        if existing is not None:
            return cast(sqlite3.Connection, existing)
        conn = sqlite3.connect(self.path, check_same_thread=self._check_same_thread)
        self._configure(conn)
        self._local.conn = conn
        with self._connections_lock:
            self._all_connections.append(conn)
        return conn

    def _configure(self, conn: sqlite3.Connection) -> None:
        """Apply PRAGMAs + ensure the schema is in place on a fresh connection."""
        # WAL mode is per-database; setting it on every connection is harmless
        # and ensures the first connection (even before any write) flips it.
        # ``:memory:`` ignores journal_mode but the PRAGMA itself is safe to issue.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)}")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(_SCHEMA)
        conn.commit()


__all__ = ["SQLiteStorage"]
