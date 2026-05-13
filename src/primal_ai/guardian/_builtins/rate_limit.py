"""``RateLimit`` — token-bucket request rate limiting (stdlib only)."""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from primal_ai.guardian._policy import PolicyViolation


class RateLimit:
    """Cap the rate of wrapped-agent calls per second, minute, and/or hour.

    Implemented as three sliding-window counters over ``time.monotonic()``;
    no external clock or dependency required. Setting a limit to ``None``
    disables that window.

    Args:
        per_second: Maximum allowed calls in any rolling 1-second window.
        per_minute: Maximum allowed calls in any rolling 60-second window.
        per_hour:   Maximum allowed calls in any rolling 3600-second window.

    Example:
        >>> from primal_ai import Guardian, RateLimit
        >>> wrapped = Guardian.wrap(agent, policies=[RateLimit(per_minute=60)])
    """

    name = "rate_limit"

    def __init__(
        self,
        per_second: int | None = None,
        per_minute: int | None = None,
        per_hour: int | None = None,
    ) -> None:
        self.per_second = per_second
        self.per_minute = per_minute
        self.per_hour = per_hour
        # One deque of timestamps is enough — we trim per-window on each check.
        self._calls: deque[float] = deque()

    def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        """Block when any configured window is full."""
        del args, kwargs  # unused — rate-limit is call-frequency-only
        now = time.monotonic()
        # Trim to the largest active window so the deque can't grow unbounded.
        oldest_window = self._oldest_relevant_window()
        if oldest_window is not None:
            cutoff = now - oldest_window
            while self._calls and self._calls[0] < cutoff:
                self._calls.popleft()

        for window, limit in self._windows():
            if limit is None:
                continue
            count = sum(1 for t in self._calls if t >= now - window)
            if count >= limit:
                reason = (
                    f"rate limit exceeded: {count + 1} calls in last "
                    f"{window}s (limit={limit})"
                )
                raise PolicyViolation(
                    policy_name=self.name,
                    reason=reason,
                    phase="pre",
                    context={
                        "window_seconds": window,
                        "limit": limit,
                        "observed": count + 1,
                    },
                )

        self._calls.append(now)

    def _windows(self) -> list[tuple[float, int | None]]:
        return [
            (1.0, self.per_second),
            (60.0, self.per_minute),
            (3600.0, self.per_hour),
        ]

    def _oldest_relevant_window(self) -> float | None:
        active = [w for w, lim in self._windows() if lim is not None]
        return max(active) if active else None


def factory(arg: str) -> RateLimit:
    """DSL factory: ``"rate_limit:per_minute=60"`` etc."""
    from primal_ai.guardian._dsl import parse_kv

    kv = parse_kv(arg)
    kwargs: dict[str, int | None] = {}
    for key in ("per_second", "per_minute", "per_hour"):
        if key in kv and kv[key] != "":
            kwargs[key] = int(kv[key])
    return RateLimit(**kwargs)


__all__ = ["RateLimit", "factory"]
