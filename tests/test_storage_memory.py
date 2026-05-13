"""Smoke test — InMemoryStorage put/get/delete behavior."""

from __future__ import annotations


def test_inmemory_put_get_delete() -> None:
    """``InMemoryStorage`` round-trips a value, then deletes it."""
    from primal_ai.storage import InMemoryStorage

    storage = InMemoryStorage()

    # Missing key returns None.
    assert storage.get("missing") is None

    # put + get round-trip.
    storage.put("agent:1", {"name": "alpha"})
    assert storage.get("agent:1") == {"name": "alpha"}

    # Overwrite on put.
    storage.put("agent:1", {"name": "beta"})
    assert storage.get("agent:1") == {"name": "beta"}

    # delete removes the key.
    storage.delete("agent:1")
    assert storage.get("agent:1") is None

    # delete is a no-op on missing keys.
    storage.delete("agent:1")
