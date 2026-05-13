"""``HealthStatus`` + ``HealthCheck`` + ``HealthMonitor`` — pluggable liveness probes.

A check is any zero-arg callable returning a ``HealthCheck``. A check that
raises is converted into an ``UNHEALTHY`` verdict — never propagates.
``HealthMonitor.overall_status`` returns the worst grade seen across every
registered check, useful as a top-level readiness signal.
"""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from primal_ai._events import Event, EventKind, default_bus

# Ordered worst → best for ``overall_status`` comparison.
_STATUS_ORDER: dict[str, int] = {
    "UNHEALTHY": 3,
    "DEGRADED": 2,
    "UNKNOWN": 1,
    "HEALTHY": 0,
}


class HealthStatus(StrEnum):
    """Four-state liveness grade for one health check (and the monitor overall).

    Values:
        HEALTHY:   The check confirmed the dependency is fully functional.
        DEGRADED:  Working but with reduced quality (slow, partial,
                   rate-limited, etc.).
        UNHEALTHY: Not working — the dependency failed or the check
                   raised an exception.
        UNKNOWN:   No verdict could be reached (data missing, check not
                   yet run).
    """

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HealthCheck:
    """One health check result.

    Frozen — a check writes its verdict once and downstream consumers can
    rely on the snapshot.
    """

    name: str
    status: HealthStatus
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: float = field(default_factory=time.time)
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "name": self.name,
            "status": self.status.value,
            "reason": self.reason,
            "details": dict(self.details),
            "checked_at": self.checked_at,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> HealthCheck:
        """Rebuild a ``HealthCheck`` from a ``to_dict`` payload."""
        return cls(
            name=str(payload["name"]),
            status=HealthStatus(payload["status"]),
            reason=payload.get("reason"),
            details=dict(payload.get("details") or {}),
            checked_at=float(payload.get("checked_at") or time.time()),
            latency_ms=payload.get("latency_ms"),
        )


HealthCheckFn = Callable[[], HealthCheck]


class HealthMonitor:
    """Registry of named health-check callables.

    Threadsafe under a single per-monitor lock. Each call to ``run``
    publishes a ``HEALTH_CHECK_RUN`` event so external observers can
    aggregate without polling.

    Example:
        >>> from primal_ai import HealthCheck, HealthStatus
        >>> from primal_ai.harness import HealthMonitor
        >>> monitor = HealthMonitor()
        >>> monitor.register_check(
        ...     "db",
        ...     lambda: HealthCheck(name="db", status=HealthStatus.HEALTHY),
        ... )
        >>> monitor.run("db").status.value
        'HEALTHY'
    """

    def __init__(self) -> None:
        self._checks: dict[str, HealthCheckFn] = {}
        self._lock = threading.Lock()

    def register_check(self, name: str, check: HealthCheckFn) -> None:
        """Register a check callable under ``name``. Replaces any prior check by that name."""
        with self._lock:
            self._checks[name] = check

    def unregister_check(self, name: str) -> None:
        """Remove a previously-registered check. No-op if absent."""
        with self._lock:
            self._checks.pop(name, None)

    def run(self, name: str) -> HealthCheck | None:
        """Execute one check by name. ``None`` if the name isn't registered."""
        with self._lock:
            check = self._checks.get(name)
        if check is None:
            return None
        result = _run_one(name, check)
        default_bus.publish(
            Event(
                kind=EventKind.HEALTH_CHECK_RUN.value,
                payload={"check": result.to_dict()},
            ),
        )
        return result

    def run_all(self) -> dict[str, HealthCheck]:
        """Execute every registered check; return ``{name: HealthCheck}``."""
        with self._lock:
            checks = dict(self._checks)
        results: dict[str, HealthCheck] = {}
        for name, check in checks.items():
            results[name] = _run_one(name, check)
            default_bus.publish(
                Event(
                    kind=EventKind.HEALTH_CHECK_RUN.value,
                    payload={"check": results[name].to_dict()},
                ),
            )
        return results

    def overall_status(self) -> HealthStatus:
        """Return the worst status across every currently-registered check.

        ``UNHEALTHY`` > ``DEGRADED`` > ``UNKNOWN`` > ``HEALTHY``. With no
        checks registered, returns ``UNKNOWN``.
        """
        results = self.run_all()
        if not results:
            return HealthStatus.UNKNOWN
        worst = max(results.values(), key=lambda c: _STATUS_ORDER[c.status.value])
        return worst.status


def _run_one(name: str, check: HealthCheckFn) -> HealthCheck:
    """Execute ``check`` and convert exceptions into an UNHEALTHY verdict."""
    started = time.monotonic()
    try:
        return check()
    except Exception as exc:  # noqa: BLE001 — convert any exception to UNHEALTHY
        latency_ms = (time.monotonic() - started) * 1000.0
        return HealthCheck(
            name=name,
            status=HealthStatus.UNHEALTHY,
            reason=f"{type(exc).__name__}: {exc}",
            details={"traceback": traceback.format_exc()},
            checked_at=time.time(),
            latency_ms=latency_ms,
        )


__all__ = ["HealthCheck", "HealthCheckFn", "HealthMonitor", "HealthStatus"]
