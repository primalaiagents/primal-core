"""Continuity facade — load/save/update/delete/list_users/autolearn.

Storage is dependency-injected: every method that touches persistence
accepts an optional ``store`` argument. Pass an ``InMemoryStorage`` for
tests, a ``SQLiteStorage`` for production. With ``store=None`` the
mutation/lookup is in-memory only (and ``save`` logs once + returns).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from primal_ai._events import Event, EventKind, default_bus
from primal_ai.continuity.autolearn import Autolearn
from primal_ai.continuity.profile import ProfileField, UserProfile

if TYPE_CHECKING:
    from primal_ai.storage import Storage

_logger = logging.getLogger("primal_ai.continuity")
_PROFILE_KEY_PREFIX = "continuity:profile:"


def _profile_key(user_id: str) -> str:
    return f"{_PROFILE_KEY_PREFIX}{user_id}"


# We log the no-store warning at most once per process — it's a guidance
# message, not an error, and we don't want it to flood test output.
_warned_no_store = False


def _warn_no_store_once() -> None:
    global _warned_no_store  # noqa: PLW0603 — single module-level slot
    if _warned_no_store:
        return
    _warned_no_store = True
    _logger.warning(
        "Continuity.save called without a store — profile mutations are not "
        "persisted. Pass store=<Storage> to persist via the Storage Protocol.",
    )


class Continuity:
    """Portable-user-profile facade.

    ``Continuity`` is stateless — every call takes the ``store`` it should
    read from / write to. That keeps the facade testable and makes
    multi-store deployments (per-tenant SQLite files, for instance)
    trivial: pass a different store per call.

    Example:
        >>> from primal_ai import BYOAutolearn, Continuity
        >>> from primal_ai.storage import InMemoryStorage
        >>> store = InMemoryStorage()
        >>> profile = Continuity.update(
        ...     "user-k", "language", "en",
        ...     source="user", confidence=1.0, store=store,
        ... )
        >>> profile.get("language")
        'en'
    """

    # ──────────────────────────────────────────────────────────────────
    # Read / write
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, user_id: str, *, store: Storage | None = None) -> UserProfile:
        """Return the persisted profile for ``user_id`` (or a fresh empty one).

        Never raises on missing — a missing profile is indistinguishable
        from a fresh user from the facade's perspective.
        """
        if store is not None:
            payload = store.get(_profile_key(user_id))
            if payload is not None:
                return UserProfile.from_dict(payload)
        now = time.time()
        return UserProfile(
            user_id=user_id,
            fields={},
            metadata={},
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def save(
        cls,
        user_id: str,
        profile: UserProfile,
        *,
        store: Storage | None = None,
    ) -> None:
        """Persist ``profile`` for ``user_id`` via ``store``.

        With ``store=None`` this is a no-op (one WARNING per session
        explains how to enable persistence). ``user_id`` is the
        authoritative key — the profile's ``user_id`` field is overwritten
        if it differs.
        """
        if store is None:
            _warn_no_store_once()
            return
        # Ensure the profile's user_id matches the key being saved under,
        # so a load() round-trip returns the same identity.
        if profile.user_id != user_id:
            profile = UserProfile(
                user_id=user_id,
                fields=profile.fields,
                metadata=profile.metadata,
                created_at=profile.created_at,
                updated_at=profile.updated_at,
            )
        store.put(_profile_key(user_id), profile.to_dict())

    # ──────────────────────────────────────────────────────────────────
    # Convenience mutators
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def update(
        cls,
        user_id: str,
        key: str,
        value: Any,
        *,
        source: str = "user",
        confidence: float = 1.0,
        store: Storage | None = None,
    ) -> UserProfile:
        """Load + set + save in one call. Emits ``PROFILE_UPDATED`` afterwards.

        Returns the updated profile so callers can chain further mutations
        without a second ``load``.
        """
        profile = cls.load(user_id, store=store)
        profile.set(key, value, source=source, confidence=confidence)
        cls.save(user_id, profile, store=store)
        default_bus.publish(
            Event(
                kind=EventKind.PROFILE_UPDATED.value,
                payload={
                    "user_id": user_id,
                    "key": key,
                    "source": source,
                    "confidence": confidence,
                },
            ),
        )
        return profile

    @classmethod
    def delete(cls, user_id: str, *, store: Storage | None = None) -> None:
        """Remove ``user_id``'s profile from ``store``. No-op if absent or no store."""
        if store is None:
            return
        store.delete(_profile_key(user_id))
        default_bus.publish(
            Event(
                kind=EventKind.PROFILE_DELETED.value,
                payload={"user_id": user_id},
            ),
        )

    @classmethod
    def list_users(cls, store: Storage) -> list[str]:
        """Return every ``user_id`` with a stored profile.

        Uses ``store.list_keys`` when available; falls back to an empty
        list otherwise. (``SQLiteStorage`` exposes ``list_keys``;
        ``InMemoryStorage`` doesn't in MVP.)
        """
        list_keys = getattr(store, "list_keys", None)
        if list_keys is None:
            return []
        keys = list_keys(_PROFILE_KEY_PREFIX)
        return [k[len(_PROFILE_KEY_PREFIX):] for k in keys]

    # ──────────────────────────────────────────────────────────────────
    # Autolearn integration
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def autolearn(
        cls,
        user_id: str,
        text: str,
        autolearn: Autolearn,
        *,
        store: Storage | None = None,
    ) -> UserProfile:
        """Run ``autolearn.extract`` over ``text``, merge into the user's profile, save.

        Uses the ``higher_confidence`` merge strategy: explicit user-set
        fields (confidence 1.0) win over autolearn-derived ones (default
        0.7), while old low-confidence facts get superseded by fresher
        ones. Emits a single ``PROFILE_UPDATED`` event for the batch.
        """
        current = cls.load(user_id, store=store)
        extracted = autolearn.extract(text, current_profile=current)
        merged = _merge_extracted_into(current, extracted)
        cls.save(user_id, merged, store=store)
        default_bus.publish(
            Event(
                kind=EventKind.PROFILE_UPDATED.value,
                payload={
                    "user_id": user_id,
                    "key": "_autolearn_batch",
                    "source": getattr(autolearn, "name", "autolearn"),
                    "confidence": None,
                    "extracted_count": len(extracted),
                },
            ),
        )
        return merged


def _merge_extracted_into(
    current: UserProfile,
    extracted: list[ProfileField],
) -> UserProfile:
    """Fold a list of new ``ProfileField``s into ``current`` using higher_confidence."""
    incoming_fields = {f.key: f for f in extracted}
    incoming = UserProfile(
        user_id=current.user_id,
        fields=incoming_fields,
        metadata={},
        created_at=current.created_at,
        updated_at=time.time(),
    )
    return current.merge(incoming, prefer="higher_confidence")


__all__ = ["Continuity"]
