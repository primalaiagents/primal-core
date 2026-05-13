"""Continuity — portable user profile + BYO autolearn.

The MVP exposes a dependency-injected profile facade with explicit merge
strategies and a BYO autolearn surface. Storage is always optional — a
profile lives in memory until saved through the ``Storage`` Protocol.

Three primitives compose the surface:

  - :class:`ProfileField` — one fact with source + confidence metadata.
  - :class:`UserProfile` — a map of fields with three merge strategies
    (``self`` / ``other`` / ``higher_confidence``).
  - :class:`Autolearn` Protocol + :class:`BYOAutolearn` concrete —
    extract ``ProfileField`` lists from text via a user-supplied LLM
    callable. No first-party LLM ships in MVP (same zero-dep boundary
    Verifier's ``BYOLLMJudge`` and Atlas's ``BYOProvider`` established).

Profile mutations emit ``PROFILE_UPDATED`` on the shared event bus so
external observers can react without polling.

Example:
    >>> from primal_ai import Continuity
    >>> from primal_ai.storage import InMemoryStorage
    >>> store = InMemoryStorage()
    >>> profile = Continuity.update(
    ...     "user-k", "language", "en",
    ...     source="user", confidence=1.0, store=store,
    ... )
    >>> profile.get("language")
    'en'
"""

from __future__ import annotations

from primal_ai.continuity._core import Continuity
from primal_ai.continuity.autolearn import (
    DEFAULT_AUTOLEARN_PROMPT,
    Autolearn,
    BYOAutolearn,
    register_autolearn,
)
from primal_ai.continuity.profile import MergeStrategy, ProfileField, UserProfile

__all__ = [
    "Autolearn",
    "BYOAutolearn",
    "Continuity",
    "DEFAULT_AUTOLEARN_PROMPT",
    "MergeStrategy",
    "ProfileField",
    "UserProfile",
    "register_autolearn",
]
