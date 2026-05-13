"""SQLite Storage MVP — round-trips, WAL, durability, threading, Trajectory integration.

These tests are the contract for the Phase 1 ``SQLiteStorage``: a stdlib-only
durable backend for the ``Storage`` Protocol with WAL mode, JSON values, and
one connection per thread.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────────
# Construction
# ──────────────────────────────────────────────────────────────────────────


def test_construct_in_memory() -> None:
    """``SQLiteStorage(":memory:")`` constructs and is usable immediately."""
    from primal_ai.storage import SQLiteStorage

    store = SQLiteStorage(":memory:")
    assert store is not None
    store.close()


def test_construct_with_path_string(tmp_path: Path) -> None:
    """A string path opens an on-disk database without error."""
    from primal_ai.storage import SQLiteStorage

    db = tmp_path / "primal.db"
    store = SQLiteStorage(str(db))
    store.put("k", {"v": 1})
    store.close()
    assert db.exists()


def test_construct_with_path_instance(tmp_path: Path) -> None:
    """A ``pathlib.Path`` argument is accepted just like a string."""
    from primal_ai.storage import SQLiteStorage

    db = tmp_path / "primal.db"
    with SQLiteStorage(db) as store:
        store.put("k", "v")
        assert store.get("k") == "v"


def test_parent_directory_is_created_if_missing(tmp_path: Path) -> None:
    """A path whose parent doesn't exist creates the parent on construction."""
    from primal_ai.storage import SQLiteStorage

    nested = tmp_path / "a" / "b" / "c" / "primal.db"
    with SQLiteStorage(nested) as store:
        store.put("k", 1)
    assert nested.exists()


# ──────────────────────────────────────────────────────────────────────────
# Round-trips
# ──────────────────────────────────────────────────────────────────────────


def test_put_get_roundtrips_a_dict() -> None:
    """A nested dict round-trips through put/get unchanged."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        store.put("agent:1", {"name": "alpha", "score": 0.9})
        assert store.get("agent:1") == {"name": "alpha", "score": 0.9}


def test_put_get_roundtrips_a_list() -> None:
    """A list round-trips."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        store.put("xs", [1, 2, "three", None, True])
        assert store.get("xs") == [1, 2, "three", None, True]


def test_put_get_roundtrips_a_string() -> None:
    """A bare string round-trips."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        store.put("greeting", "hello, primal")
        assert store.get("greeting") == "hello, primal"


def test_put_get_roundtrips_a_number() -> None:
    """A float round-trips with full precision."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        store.put("n", 3.14159)
        assert store.get("n") == pytest.approx(3.14159)


def test_put_get_roundtrips_a_nested_structure() -> None:
    """A deeply nested dict/list mix round-trips byte-for-byte."""
    from primal_ai.storage import SQLiteStorage

    payload: dict[str, Any] = {
        "outer": {
            "inner": [{"deep": True, "values": [1, 2, 3]}],
            "meta": {"count": 1},
        },
    }
    with SQLiteStorage(":memory:") as store:
        store.put("k", payload)
        assert store.get("k") == payload


def test_get_returns_none_for_missing_key() -> None:
    """``get`` returns ``None`` for a key that was never put."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        assert store.get("never_set") is None


# ──────────────────────────────────────────────────────────────────────────
# Mutation
# ──────────────────────────────────────────────────────────────────────────


def test_put_overwrites_existing_key() -> None:
    """A second ``put`` on the same key replaces the previous value (UPSERT)."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        store.put("k", "first")
        store.put("k", "second")
        assert store.get("k") == "second"


def test_delete_removes_a_key() -> None:
    """``delete`` removes a key so subsequent ``get`` returns ``None``."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        store.put("k", 1)
        store.delete("k")
        assert store.get("k") is None


def test_delete_is_noop_on_missing_key() -> None:
    """``delete`` on an absent key is silently a no-op."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        store.delete("never_set")  # must not raise


def test_put_with_non_json_value_raises_typeerror() -> None:
    """A value that JSON can't serialize raises ``TypeError`` at ``put`` time."""
    from primal_ai.storage import SQLiteStorage

    class NotSerializable:
        __slots__ = ()

    with SQLiteStorage(":memory:") as store, pytest.raises(TypeError):
        store.put("k", NotSerializable())


# ──────────────────────────────────────────────────────────────────────────
# list_keys
# ──────────────────────────────────────────────────────────────────────────


def test_list_keys_empty_store() -> None:
    """``list_keys()`` on an empty store returns an empty list."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        assert store.list_keys() == []


def test_list_keys_filters_by_prefix_and_sorts() -> None:
    """``list_keys("trajectory:")`` returns only matching keys, sorted ascending."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        store.put("trajectory:b", {})
        store.put("trajectory:a", {})
        store.put("agent:x", {})
        keys = store.list_keys("trajectory:")
        assert keys == ["trajectory:a", "trajectory:b"]


def test_list_keys_empty_prefix_returns_all() -> None:
    """``list_keys("")`` returns every key in the store."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        store.put("a", 1)
        store.put("b", 2)
        assert sorted(store.list_keys("")) == ["a", "b"]


# ──────────────────────────────────────────────────────────────────────────
# Pragmas
# ──────────────────────────────────────────────────────────────────────────


def test_wal_mode_is_enabled_on_disk(tmp_path: Path) -> None:
    """On a disk-backed database, ``PRAGMA journal_mode`` reports ``wal``."""
    from primal_ai.storage import SQLiteStorage

    db = tmp_path / "primal.db"
    with SQLiteStorage(db) as store:
        store.put("k", 1)  # force a connection
        # Peek at the same DB via a fresh connection to observe the journal_mode.
        with sqlite3.connect(str(db)) as raw:
            cur = raw.execute("PRAGMA journal_mode")
            mode = cur.fetchone()[0]
    assert mode.lower() == "wal"


def test_busy_timeout_matches_constructor() -> None:
    """``busy_timeout`` is set to the value passed to the constructor."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:", busy_timeout_ms=1234) as store:
        conn = store._connection_for_thread()
        cur = conn.execute("PRAGMA busy_timeout")
        assert cur.fetchone()[0] == 1234


# ──────────────────────────────────────────────────────────────────────────
# Durability
# ──────────────────────────────────────────────────────────────────────────


def test_value_survives_process_restart_via_close_and_reopen(tmp_path: Path) -> None:
    """A written value is readable from a fresh ``SQLiteStorage`` over the same file."""
    from primal_ai.storage import SQLiteStorage

    db = tmp_path / "primal.db"
    s1 = SQLiteStorage(db)
    s1.put("k", {"v": "persisted"})
    s1.close()

    s2 = SQLiteStorage(db)
    try:
        assert s2.get("k") == {"v": "persisted"}
    finally:
        s2.close()


# ──────────────────────────────────────────────────────────────────────────
# Threading
# ──────────────────────────────────────────────────────────────────────────


def test_concurrent_puts_from_multiple_threads_do_not_corrupt(tmp_path: Path) -> None:
    """Eight threads each ``put`` 50 keys; every value is readable afterward."""
    from primal_ai.storage import SQLiteStorage

    db = tmp_path / "primal.db"
    store = SQLiteStorage(db)
    errors: list[BaseException] = []

    def writer(thread_id: int) -> None:
        try:
            for i in range(50):
                store.put(f"t{thread_id}:k{i}", {"thread": thread_id, "i": i})
        except BaseException as exc:  # noqa: BLE001 — capture for assert
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    keys = store.list_keys("")
    assert len(keys) == 8 * 50
    # Spot-check one value from each thread.
    for t in range(8):
        v = store.get(f"t{t}:k0")
        assert v == {"thread": t, "i": 0}
    store.close()


# ──────────────────────────────────────────────────────────────────────────
# Context manager / Protocol
# ──────────────────────────────────────────────────────────────────────────


def test_context_manager_closes_on_exit() -> None:
    """``with SQLiteStorage(...) as store`` returns the store and closes cleanly."""
    from primal_ai.storage import SQLiteStorage

    with SQLiteStorage(":memory:") as store:
        store.put("k", 1)
        assert store.get("k") == 1
    # After exit, calling close again should be safe (idempotent).
    store.close()


def test_sqlite_storage_satisfies_storage_protocol() -> None:
    """``SQLiteStorage`` is structurally a ``Storage`` (runtime-checkable Protocol)."""
    from primal_ai.storage import SQLiteStorage, Storage

    with SQLiteStorage(":memory:") as store:
        assert isinstance(store, Storage)


# ──────────────────────────────────────────────────────────────────────────
# Trajectory integration
# ──────────────────────────────────────────────────────────────────────────


def test_trajectory_save_and_load_round_trip_through_sqlite(tmp_path: Path) -> None:
    """A full ``Trajectory`` (with steps) persists via SQLite and loads back identically."""
    from primal_ai import Trajectory
    from primal_ai.storage import SQLiteStorage

    db = tmp_path / "trajectories.db"
    with SQLiteStorage(db) as store:
        with Trajectory.record(agent_id="search") as tr:
            tr.record_input({"q": "flights"})
            call = tr.record_tool_call("search", {"q": "flights"})
            tr.record_tool_result(call.step_id, {"hits": 3}, cost=0.02)
            tr.record_output({"answer": "found"})
        tr.save(store)

        restored = Trajectory.load(tr.trajectory_id, store)
    assert restored.agent_id == "search"
    assert [s.kind for s in restored.replay()] == [s.kind for s in tr.replay()]
    assert restored.summary()["total_cost"] == pytest.approx(0.02)
