"""Continuity MVP — portable user profile + BYO autolearn + Storage-backed persistence.

Contract for Phase 1 Session 9 Continuity: a stdlib-only profile layer with
explicit confidence/source metadata, three merge strategies, BYO autolearn
(no first-party LLM call), and PROFILE_UPDATED events on the shared bus.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────────
# ProfileField
# ──────────────────────────────────────────────────────────────────────────


def test_profile_field_round_trips_via_to_dict_from_dict() -> None:
    """``ProfileField`` round-trips through JSON without loss."""
    from primal_ai import ProfileField

    f = ProfileField(
        key="language",
        value="en",
        confidence=0.9,
        source="user",
        updated_at=42.0,
    )
    restored = ProfileField.from_dict(json.loads(json.dumps(f.to_dict())))
    assert restored.key == "language"
    assert restored.value == "en"
    assert restored.confidence == pytest.approx(0.9)


# ──────────────────────────────────────────────────────────────────────────
# UserProfile
# ──────────────────────────────────────────────────────────────────────────


def test_user_profile_set_creates_field_with_source_and_confidence() -> None:
    """``set`` populates a new field with the given source + confidence."""
    from primal_ai import UserProfile

    p = UserProfile(user_id="u1", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    p.set("language", "en", source="user", confidence=1.0)
    field = p.get_field("language")
    assert field is not None
    assert field.value == "en"
    assert field.source == "user"
    assert field.confidence == pytest.approx(1.0)


def test_user_profile_set_overwrites_existing_field() -> None:
    """A second ``set`` on the same key overwrites the prior field's value."""
    from primal_ai import UserProfile

    p = UserProfile(user_id="u1", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    p.set("language", "en")
    p.set("language", "ja")
    assert p.get("language") == "ja"


def test_user_profile_get_returns_value_or_default_when_missing() -> None:
    """``get`` returns the value when present and the default otherwise."""
    from primal_ai import UserProfile

    p = UserProfile(user_id="u1", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    p.set("language", "en")
    assert p.get("language") == "en"
    assert p.get("timezone", default="UTC") == "UTC"


def test_user_profile_remove_drops_the_key() -> None:
    """``remove`` removes a key. Subsequent ``get`` returns the default."""
    from primal_ai import UserProfile

    p = UserProfile(user_id="u1", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    p.set("language", "en")
    p.remove("language")
    assert p.get("language") is None


def test_user_profile_merge_prefer_self_keeps_existing_on_conflict() -> None:
    """``merge(prefer='self')`` keeps the receiving profile's values on key conflict."""
    from primal_ai import UserProfile

    a = UserProfile(user_id="u1", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    a.set("language", "en", source="user", confidence=1.0)
    b = UserProfile(user_id="u1", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    b.set("language", "ja", source="autolearn", confidence=0.6)
    merged = a.merge(b, prefer="self")
    assert merged.get("language") == "en"


def test_user_profile_merge_prefer_other_keeps_other_on_conflict() -> None:
    """``merge(prefer='other')`` takes the supplied profile's values on conflict."""
    from primal_ai import UserProfile

    a = UserProfile(user_id="u1", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    a.set("language", "en", source="user", confidence=1.0)
    b = UserProfile(user_id="u1", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    b.set("language", "ja", source="autolearn", confidence=0.6)
    merged = a.merge(b, prefer="other")
    assert merged.get("language") == "ja"


def test_user_profile_merge_prefer_higher_confidence_picks_max() -> None:
    """``merge(prefer='higher_confidence')`` keeps the higher-confidence value."""
    from primal_ai import UserProfile

    a = UserProfile(user_id="u1", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    a.set("language", "en", source="autolearn", confidence=0.5)
    b = UserProfile(user_id="u1", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    b.set("language", "ja", source="user", confidence=1.0)
    merged = a.merge(b, prefer="higher_confidence")
    assert merged.get("language") == "ja"


def test_user_profile_round_trips_via_to_dict_from_dict() -> None:
    """A full ``UserProfile`` (with fields + metadata) round-trips through JSON."""
    from primal_ai import UserProfile

    p = UserProfile(
        user_id="u1",
        fields={},
        metadata={"region": "us"},
        created_at=1.0,
        updated_at=2.0,
    )
    p.set("language", "en", source="user", confidence=1.0)
    p.set("timezone", "Asia/Tokyo", source="user")
    restored = UserProfile.from_dict(json.loads(json.dumps(p.to_dict())))
    assert restored.user_id == "u1"
    assert restored.get("language") == "en"
    assert restored.get("timezone") == "Asia/Tokyo"
    assert restored.metadata == {"region": "us"}


# ──────────────────────────────────────────────────────────────────────────
# Continuity.load / save / update / delete / list_users
# ──────────────────────────────────────────────────────────────────────────


def test_continuity_load_returns_empty_profile_for_unknown_user() -> None:
    """``Continuity.load`` on a missing user returns a fresh ``UserProfile`` — never raises."""
    from primal_ai import Continuity, UserProfile
    from primal_ai.storage import InMemoryStorage

    store = InMemoryStorage()
    p = Continuity.load("u-fresh", store=store)
    assert isinstance(p, UserProfile)
    assert p.user_id == "u-fresh"
    assert p.keys() == []


def test_continuity_load_returns_saved_profile_when_present() -> None:
    """A previously-saved profile is returned by ``Continuity.load``."""
    from primal_ai import Continuity, UserProfile
    from primal_ai.storage import InMemoryStorage

    store = InMemoryStorage()
    src = UserProfile(user_id="u-saved", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    src.set("language", "en")
    Continuity.save("u-saved", src, store=store)

    loaded = Continuity.load("u-saved", store=store)
    assert loaded.get("language") == "en"


def test_continuity_save_persists_via_storage() -> None:
    """``Continuity.save`` writes ``continuity:profile:{user_id}`` to the store."""
    from primal_ai import Continuity, UserProfile
    from primal_ai.storage import InMemoryStorage

    store = InMemoryStorage()
    p = UserProfile(user_id="u-save", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    p.set("k", "v")
    Continuity.save("u-save", p, store=store)
    assert store.get("continuity:profile:u-save") is not None


def test_continuity_save_with_no_store_is_a_noop() -> None:
    """``save`` with ``store=None`` doesn't raise — it just logs and returns."""
    from primal_ai import Continuity, UserProfile

    p = UserProfile(user_id="u", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    Continuity.save("u", p)  # no store — must not raise


def test_continuity_update_load_then_set_then_save_in_one_call() -> None:
    """``Continuity.update`` rolls load + set + save into one operation."""
    from primal_ai import Continuity
    from primal_ai.storage import InMemoryStorage

    store = InMemoryStorage()
    p = Continuity.update("u-up", "language", "en", source="user", store=store)
    assert p.get("language") == "en"
    reloaded = Continuity.load("u-up", store=store)
    assert reloaded.get("language") == "en"


def test_continuity_update_emits_profile_updated_event() -> None:
    """A ``PROFILE_UPDATED`` event fires with ``{user_id, key, source, confidence}``."""
    from primal_ai import Conductor, Continuity, Event, EventKind
    from primal_ai.storage import InMemoryStorage

    seen: list[Event] = []
    sub = Conductor.event_bus.subscribe(EventKind.PROFILE_UPDATED, seen.append)
    try:
        Continuity.update(
            "u-event",
            "language",
            "en",
            source="user",
            confidence=1.0,
            store=InMemoryStorage(),
        )
    finally:
        Conductor.event_bus.unsubscribe(sub)
    assert len(seen) == 1
    payload = seen[0].payload
    assert payload["user_id"] == "u-event"
    assert payload["key"] == "language"
    assert payload["source"] == "user"


def test_continuity_delete_removes_profile_from_store() -> None:
    """``Continuity.delete`` removes the persisted profile."""
    from primal_ai import Continuity, UserProfile
    from primal_ai.storage import InMemoryStorage

    store = InMemoryStorage()
    p = UserProfile(user_id="u-del", fields={}, metadata={}, created_at=0.0, updated_at=0.0)
    Continuity.save("u-del", p, store=store)
    assert store.get("continuity:profile:u-del") is not None
    Continuity.delete("u-del", store=store)
    assert store.get("continuity:profile:u-del") is None


def test_continuity_list_users_returns_user_ids_from_store() -> None:
    """``Continuity.list_users`` returns the user_ids of every stored profile."""
    from primal_ai import Continuity, UserProfile
    from primal_ai.storage import SQLiteStorage

    store = SQLiteStorage(":memory:")
    Continuity.save(
        "u-1",
        UserProfile(user_id="u-1", fields={}, metadata={}, created_at=0.0, updated_at=0.0),
        store=store,
    )
    Continuity.save(
        "u-2",
        UserProfile(user_id="u-2", fields={}, metadata={}, created_at=0.0, updated_at=0.0),
        store=store,
    )
    ids = set(Continuity.list_users(store=store))
    assert {"u-1", "u-2"} <= ids
    store.close()


# ──────────────────────────────────────────────────────────────────────────
# Autolearn Protocol + BYOAutolearn
# ──────────────────────────────────────────────────────────────────────────


def test_autolearn_protocol_satisfied_by_minimal_class() -> None:
    """A class with ``name`` + ``extract`` satisfies the ``Autolearn`` Protocol."""
    from primal_ai import Autolearn, ProfileField

    class Minimal:
        name = "min"

        def extract(self, text: str, current_profile: Any = None) -> list[ProfileField]:
            return []

    inst: Autolearn = Minimal()
    assert isinstance(inst, Autolearn)


def test_byo_autolearn_calls_user_supplied_call_llm() -> None:
    """``BYOAutolearn.extract`` invokes the supplied LLM callable with the formatted prompt."""
    from primal_ai import BYOAutolearn

    seen: list[str] = []

    def fake_llm(prompt: str) -> str:
        seen.append(prompt)
        return ""

    BYOAutolearn(call_llm=fake_llm).extract("the user prefers japanese")
    assert len(seen) == 1
    assert "japanese" in seen[0]


def test_byo_autolearn_parses_key_value_lines_into_profile_fields() -> None:
    """Each ``KEY: VALUE`` line in the response becomes a ``ProfileField``."""
    from primal_ai import BYOAutolearn

    response = "language: ja\ntimezone: Asia/Tokyo"
    fields = BYOAutolearn(call_llm=lambda _p: response).extract("some text")
    by_key = {f.key: f.value for f in fields}
    assert by_key == {"language": "ja", "timezone": "Asia/Tokyo"}


def test_byo_autolearn_skips_malformed_lines_without_raising() -> None:
    """Lines that don't match ``KEY: VALUE`` are silently ignored."""
    from primal_ai import BYOAutolearn

    response = "language: ja\nthis is just text\ntimezone: UTC"
    fields = BYOAutolearn(call_llm=lambda _p: response).extract("x")
    keys = {f.key for f in fields}
    assert keys == {"language", "timezone"}


def test_continuity_autolearn_extract_merge_save_in_one_call() -> None:
    """``Continuity.autolearn`` loads, extracts, merges (higher_confidence), saves, returns."""
    from primal_ai import BYOAutolearn, Continuity
    from primal_ai.storage import InMemoryStorage

    store = InMemoryStorage()
    # Pre-existing low-confidence preference (autolearn-flavoured).
    Continuity.update(
        "u-al",
        "language",
        "en",
        source="autolearn:old",
        confidence=0.4,
        store=store,
    )

    fake_llm = lambda _prompt: "language: ja\ntimezone: Asia/Tokyo"  # noqa: E731
    autolearn = BYOAutolearn(call_llm=fake_llm)
    profile = Continuity.autolearn("u-al", "the user prefers japanese", autolearn, store=store)

    # The autolearn-derived "ja" beats the older 0.4 "en" because BYOAutolearn
    # emits fields at confidence 0.7 by default.
    assert profile.get("language") == "ja"
    assert profile.get("timezone") == "Asia/Tokyo"
