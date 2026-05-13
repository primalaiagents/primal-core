"""``ProviderHealth`` — per-provider state for routing decisions."""

from __future__ import annotations

import threading
import time


class ProviderHealth:
    """Mutable per-provider health: failure counts + cooldown window.

    Held inside the registry, never exposed as a frozen value because it
    really is mutable state. Threadsafe under a per-instance ``Lock`` so
    concurrent routes/invocations don't corrupt the counters.

    Attributes:
        consecutive_failures: How many failures in a row since the last
            success. Reset to zero by ``record_success``.
        total_calls: Lifetime count of recorded calls (success or failure).
        total_failures: Lifetime count of recorded failures.
        cooldown_until: Monotonic timestamp; the provider is considered
            unhealthy until ``time.monotonic() >= cooldown_until``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.consecutive_failures: int = 0
        self.total_calls: int = 0
        self.total_failures: int = 0
        self.cooldown_until: float = 0.0

    def is_healthy(self) -> bool:
        """Return True iff the provider is past its cooldown window."""
        with self._lock:
            return time.monotonic() >= self.cooldown_until

    def record_success(self) -> None:
        """Mark a clean call — clears consecutive_failures + cooldown."""
        with self._lock:
            self.consecutive_failures = 0
            self.total_calls += 1
            self.cooldown_until = 0.0

    def record_failure(self, cooldown_seconds: float) -> None:
        """Mark a failure and set the cooldown window to ``cooldown_seconds`` from now."""
        with self._lock:
            self.consecutive_failures += 1
            self.total_calls += 1
            self.total_failures += 1
            self.cooldown_until = time.monotonic() + cooldown_seconds

    def reset(self) -> None:
        """Clear cooldown AND failure counters. Used by ``Atlas.reset_health``."""
        with self._lock:
            self.consecutive_failures = 0
            self.cooldown_until = 0.0


__all__ = ["ProviderHealth"]
