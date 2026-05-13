"""``ProfileField`` + ``UserProfile`` — portable user profile primitives.

A ``UserProfile`` carries the user's durable preferences as a map of named
``ProfileField``s. Each field records its ``value`` plus ``source`` (who
wrote it) and ``confidence`` (how strongly we believe it). The MVP merge
strategies (``self`` / ``other`` / ``higher_confidence``) compose two
profiles deterministically without hidden policy decisions.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

MergeStrategy = Literal["self", "other", "higher_confidence"]


@dataclass(frozen=True)
class ProfileField:
    """One declared fact on a ``UserProfile``.

    Frozen — every mutation produces a new ``ProfileField`` instance so
    consumers can rely on snapshots.

    Args:
        key: Stable identifier (e.g. ``"language"``, ``"timezone"``).
        value: JSON-serializable payload.
        confidence: 0.0–1.0 ; user-set fields default to ``1.0``,
            ``BYOAutolearn``-derived fields default to ``0.7`` so explicit
            user intent wins on conflict.
        source: Free-form label of the writer (``"user"``,
            ``"autolearn:byo_llm"``, ``"explicit_api"``, etc.).
        updated_at: Wall-clock timestamp (``time.time()``).
    """

    key: str
    value: Any
    confidence: float = 1.0
    source: str = "user"
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ProfileField:
        """Rebuild a ``ProfileField`` from a ``to_dict`` payload."""
        return cls(
            key=str(payload["key"]),
            value=payload.get("value"),
            confidence=float(payload.get("confidence") or 1.0),
            source=str(payload.get("source") or "user"),
            updated_at=float(payload.get("updated_at") or time.time()),
        )


@dataclass
class UserProfile:
    """Mutable, JSON-round-trippable user profile.

    A profile is a thin map of ``key → ProfileField``. Convenience
    accessors (``get`` / ``set`` / ``remove``) hide the field-wrapping
    so user code reads naturally. ``merge`` composes two profiles with
    one of three explicit conflict strategies — no hidden defaults.

    Example:
        >>> from primal_ai import UserProfile
        >>> p = UserProfile(user_id="k", fields={}, metadata={},
        ...                 created_at=0.0, updated_at=0.0)
        >>> p.set("language", "en", source="user", confidence=1.0)
        >>> p.get("language")
        'en'
    """

    user_id: str
    fields: dict[str, ProfileField]
    metadata: dict[str, Any]
    created_at: float
    updated_at: float

    def __post_init__(self) -> None:
        # Lock isn't a dataclass field; assigned via object.__setattr__ so
        # ``@dataclass`` doesn't try to include it in ``__eq__`` / etc.
        object.__setattr__(self, "_lock", threading.Lock())

    # ── Accessors ──────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value stored under ``key``, or ``default`` if absent."""
        lock: threading.Lock = self._lock  # type: ignore[attr-defined]
        with lock:
            field_obj = self.fields.get(key)
        return field_obj.value if field_obj is not None else default

    def get_field(self, key: str) -> ProfileField | None:
        """Return the full ``ProfileField`` (with source + confidence) or ``None``."""
        lock: threading.Lock = self._lock  # type: ignore[attr-defined]
        with lock:
            return self.fields.get(key)

    def keys(self) -> list[str]:
        """Snapshot list of every key currently on the profile."""
        lock: threading.Lock = self._lock  # type: ignore[attr-defined]
        with lock:
            return list(self.fields.keys())

    # ── Mutators ───────────────────────────────────────────────────────

    def set(
        self,
        key: str,
        value: Any,
        *,
        source: str = "user",
        confidence: float = 1.0,
    ) -> None:
        """Create or overwrite the field at ``key`` with the supplied metadata."""
        lock: threading.Lock = self._lock  # type: ignore[attr-defined]
        now = time.time()
        with lock:
            self.fields[key] = ProfileField(
                key=key,
                value=value,
                confidence=confidence,
                source=source,
                updated_at=now,
            )
            self.updated_at = now

    def remove(self, key: str) -> None:
        """Remove ``key`` if present. No-op otherwise."""
        lock: threading.Lock = self._lock  # type: ignore[attr-defined]
        with lock:
            if key in self.fields:
                self.fields.pop(key)
                self.updated_at = time.time()

    # ── Composition ────────────────────────────────────────────────────

    def merge(
        self,
        other: UserProfile,
        *,
        prefer: MergeStrategy = "higher_confidence",
    ) -> UserProfile:
        """Return a NEW profile combining ``self`` and ``other``.

        Args:
            other: The profile whose fields are folded into a copy of self.
            prefer: Strategy for resolving key conflicts:
                ``"self"`` keeps this profile's field;
                ``"other"`` takes ``other``'s field;
                ``"higher_confidence"`` (default) keeps the field with the
                    larger ``confidence`` value (ties go to ``self``).
        """
        merged_fields: dict[str, ProfileField] = dict(self.fields)
        for key, field_obj in other.fields.items():
            existing = merged_fields.get(key)
            if existing is None:
                merged_fields[key] = field_obj
                continue
            if prefer == "self":
                continue
            if prefer == "other":
                merged_fields[key] = field_obj
                continue
            # higher_confidence
            if field_obj.confidence > existing.confidence:
                merged_fields[key] = field_obj
        merged_meta = {**self.metadata, **other.metadata}
        now = time.time()
        return UserProfile(
            user_id=self.user_id,
            fields=merged_fields,
            metadata=merged_meta,
            created_at=min(self.created_at, other.created_at) or self.created_at,
            updated_at=now,
        )

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view including every field."""
        lock: threading.Lock = self._lock  # type: ignore[attr-defined]
        with lock:
            field_dicts = {k: f.to_dict() for k, f in self.fields.items()}
        return {
            "user_id": self.user_id,
            "fields": field_dicts,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> UserProfile:
        """Rebuild a ``UserProfile`` from a ``to_dict`` payload."""
        fields_raw = payload.get("fields") or {}
        return cls(
            user_id=str(payload["user_id"]),
            fields={k: ProfileField.from_dict(v) for k, v in fields_raw.items()},
            metadata=dict(payload.get("metadata") or {}),
            created_at=float(payload.get("created_at") or 0.0),
            updated_at=float(payload.get("updated_at") or 0.0),
        )


__all__ = ["MergeStrategy", "ProfileField", "UserProfile"]
