"""Failure cascade — exponential cooldown for unhealthy providers.

When a provider fails, push it onto a cooldown timer; subsequent failures
extend the timer exponentially. Lets the router skip known-bad options
without permanently disabling them.
"""

from __future__ import annotations


class Cascade:
    """Failure-aware cooldown for providers. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def trip(cls, provider: str, reason: str | None = None) -> None:
        """Trip a provider into cooldown after a failure. STUB."""
        raise NotImplementedError("Cascade.trip will be implemented in Phase 2")

    @classmethod
    def is_available(cls, provider: str) -> bool:
        """Return True if a provider is past its cooldown window. STUB."""
        raise NotImplementedError("Cascade.is_available will be implemented in Phase 2")
