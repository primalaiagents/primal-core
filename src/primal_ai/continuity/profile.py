"""Portable User Format (PUF) — the user-profile schema for Continuity.

A signed, versioned JSON document that captures preferences, consents,
and trust scopes; portable across agents and providers.
"""

from __future__ import annotations

from typing import Any


class Profile:
    """Portable User Format (PUF) document. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        """Construct a Profile from a PUF dict. STUB."""
        raise NotImplementedError("Profile.from_dict will be implemented in Phase 2")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this Profile to a PUF dict. STUB."""
        raise NotImplementedError("Profile.to_dict will be implemented in Phase 2")
