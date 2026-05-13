"""Continuity — portable user profiles and auto-learned preferences.

Lets a user's preferences, history, and consent rules travel with them
across agents, sessions, and providers via a Portable User Format (PUF).
"""

from __future__ import annotations

from typing import Any


class Continuity:
    """Portable user profile + auto-learn façade. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def load(cls, user_id: str) -> dict[str, Any]:
        """Load a portable user profile by id. STUB."""
        raise NotImplementedError("Continuity.load will be implemented in Phase 2")

    @classmethod
    def save(cls, user_id: str, profile: dict[str, Any]) -> None:
        """Persist a portable user profile. STUB."""
        raise NotImplementedError("Continuity.save will be implemented in Phase 2")
