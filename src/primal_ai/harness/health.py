"""Harness health — liveness and readiness probes.

Standard ``/healthz`` and ``/readyz`` style probes for every registered
agent and tool, plus an aggregate cluster status.
"""

from __future__ import annotations

from typing import Any


class Health:
    """Liveness / readiness probes. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def check(cls, target: str | None = None) -> dict[str, Any]:
        """Return health status for a target (or all targets). STUB."""
        raise NotImplementedError("Health.check will be implemented in Phase 2")
