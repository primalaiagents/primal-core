"""``Scheduler`` + ``ScheduledJob`` + ``JobStatus`` — interval-based job runner.

Thread-driven sync scheduler. One daemon thread wakes every 50ms and runs
any job whose ``next_run_at`` has elapsed. Job exceptions never propagate:
the offending job is recorded as ``FAILED`` on the shared event bus and
the thread keeps scheduling.

Async, cron syntax, and job persistence are documented as Phase 2 work in
``docs/HARNESS_ROADMAP.md``.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from primal_ai._events import Event, EventKind, default_bus

# Tick granularity for the scheduler thread. Smaller than any realistic
# user interval, large enough not to burn a core.
_TICK_SECONDS = 0.05


class JobStatus(StrEnum):
    """Lifecycle state of one scheduled job invocation.

    Values:
        SCHEDULED: Waiting for ``next_run_at`` to elapse.
        RUNNING:   Currently inside the user's ``func``.
        SUCCESS:   Most recent run completed cleanly.
        FAILED:    Most recent run raised an exception.
        CANCELLED: Removed before its next run.
    """

    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class ScheduledJob:
    """Specification of one recurring job.

    Frozen — the scheduler updates ``next_run_at`` by replacing the spec
    in its internal map, so user code never sees a mutating job object.

    ``func`` is omitted from ``to_dict`` (callables don't survive JSON).
    Persistence is a Phase 2 feature; for now ``to_dict`` is provided so
    job specs can be logged / inspected without losing the rest of the
    metadata.

    Args:
        name: Unique identifier within one ``Scheduler`` instance.
        func: Zero-argument callable to invoke every interval.
        interval_seconds: Positive interval between consecutive runs.
        next_run_at: ``time.monotonic()`` deadline of the next run. ``0.0``
            means "run immediately on next tick" — the scheduler sets it
            forward after each invocation.
        enabled: ``False`` disables this job without removing it.
        metadata: Vendor-specific extensions (description, owner, etc.).
    """

    name: str
    func: Callable[[], Any]
    interval_seconds: float = 1.0
    next_run_at: float = 0.0
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view. ``func`` is omitted."""
        return {
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "next_run_at": self.next_run_at,
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }


class Scheduler:
    """Single-thread interval scheduler.

    Threadsafe — ``add_job`` / ``remove_job`` / ``list_jobs`` all hold a
    short lock around the in-memory job map. The scheduler thread is a
    daemon, so a forgotten ``stop()`` won't keep the process alive.

    Example:
        >>> from primal_ai import ScheduledJob
        >>> from primal_ai.harness import Scheduler
        >>> scheduler = Scheduler()
        >>> scheduler.add_job(
        ...     ScheduledJob(name="heartbeat", func=lambda: None, interval_seconds=1.0),
        ... )
        >>> # scheduler.start()
        >>> # ...later
        >>> # scheduler.stop()
    """

    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledJob] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Job management ────────────────────────────────────────────────

    def add_job(self, job: ScheduledJob) -> None:
        """Register ``job`` by name. Raises ``ValueError`` on duplicate name."""
        with self._lock:
            if job.name in self._jobs:
                raise ValueError(f"job {job.name!r} is already scheduled")
            self._jobs[job.name] = job

    def remove_job(self, name: str) -> None:
        """Remove ``name`` from the schedule. No-op if absent."""
        with self._lock:
            self._jobs.pop(name, None)

    def list_jobs(self) -> list[ScheduledJob]:
        """Return a snapshot list of every currently-scheduled job."""
        with self._lock:
            return list(self._jobs.values())

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler thread. Idempotent — calling while running is a no-op."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the scheduler thread to stop and join it within ``timeout`` seconds.

        Idempotent — stopping an already-stopped scheduler is a no-op.
        """
        thread: threading.Thread | None
        with self._lock:
            thread = self._thread
            self._thread = None
        self._stop_event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def is_running(self) -> bool:
        """True iff the scheduler thread is alive and not stopping."""
        with self._lock:
            thread = self._thread
        return thread is not None and thread.is_alive() and not self._stop_event.is_set()

    # ── Internals ─────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """The scheduler thread's entry point. Wakes every ``_TICK_SECONDS`` to fire ready jobs."""
        while not self._stop_event.is_set():
            now = time.monotonic()
            due: list[ScheduledJob] = []
            with self._lock:
                for name, job in list(self._jobs.items()):
                    if not job.enabled:
                        continue
                    if job.next_run_at <= now:
                        due.append(job)
                        # Replace the frozen spec with one whose next_run_at
                        # is the future deadline (frozen → recreate).
                        self._jobs[name] = ScheduledJob(
                            name=job.name,
                            func=job.func,
                            interval_seconds=job.interval_seconds,
                            next_run_at=now + job.interval_seconds,
                            enabled=job.enabled,
                            metadata=job.metadata,
                        )
            for job in due:
                _run_one(job)
            # Tick — but respond to stop() promptly.
            if self._stop_event.wait(timeout=_TICK_SECONDS):
                return


def _run_one(job: ScheduledJob) -> None:
    """Execute a single job, publishing SUCCESS / FAILED on the shared bus."""
    started = time.monotonic()
    try:
        job.func()
    except Exception as exc:  # noqa: BLE001 — exceptions must never break the loop
        duration_ms = (time.monotonic() - started) * 1000.0
        default_bus.publish(
            Event(
                kind=EventKind.SCHEDULED_JOB_RUN.value,
                payload={
                    "job_name": job.name,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "duration_ms": duration_ms,
                },
            ),
        )
        return
    duration_ms = (time.monotonic() - started) * 1000.0
    default_bus.publish(
        Event(
            kind=EventKind.SCHEDULED_JOB_RUN.value,
            payload={
                "job_name": job.name,
                "status": "success",
                "duration_ms": duration_ms,
            },
        ),
    )


__all__ = ["JobStatus", "ScheduledJob", "Scheduler"]
