"""Harness scheduler — periodic and one-shot agent jobs.

Cron-style scheduling for background work: refresh embeddings, recompute
bandit posteriors, sweep stale trajectories, etc.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Scheduler:
    """Periodic / one-shot job scheduler. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def schedule(
        cls,
        job: Callable[..., Any],
        cron: str | None = None,
        delay_seconds: int | None = None,
    ) -> str:
        """Schedule a job. Returns a job id. STUB."""
        raise NotImplementedError("Scheduler.schedule will be implemented in Phase 2")

    @classmethod
    def cancel(cls, job_id: str) -> None:
        """Cancel a previously scheduled job. STUB."""
        raise NotImplementedError("Scheduler.cancel will be implemented in Phase 2")
