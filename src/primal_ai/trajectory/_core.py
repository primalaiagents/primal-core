"""Trajectory core — context-manager recorder, helpers, summary, persistence.

The ``Trajectory`` class is the user-facing recorder. Everything else in
the trajectory package (``Step``, ``StepKind``, ``TrajectoryStatus``) is
support; ``Trajectory`` is what people put behind a ``with`` statement.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from collections.abc import Callable, Iterator
from types import TracebackType
from typing import Any

from primal_ai.storage import Storage
from primal_ai.trajectory._status import TrajectoryStatus
from primal_ai.trajectory._step import Step, StepKind

# Module-level configuration for auto-save on context exit. Threadsafe via
# a single lock; the lock is held only for the slot read/write, not for
# the storage call itself (storage backends may take their own locks).
_default_store_lock = threading.Lock()
_default_store: Storage | None = None


def set_default_store(store: Storage | None) -> None:
    """Set (or clear) the storage backend used for auto-save on context exit.

    When a default store is set, exiting a ``Trajectory`` context manager
    persists the trajectory under ``trajectory:{trajectory_id}``. Passing
    ``None`` disables auto-save (the default).

    Example:
        >>> from primal_ai import Trajectory, set_default_store
        >>> from primal_ai.storage import InMemoryStorage
        >>> set_default_store(InMemoryStorage())
        >>> with Trajectory.record() as tr:
        ...     tr.record_input({"q": "x"})
    """
    global _default_store  # noqa: PLW0603 — single module-level slot is intentional
    with _default_store_lock:
        _default_store = store


def _get_default_store() -> Storage | None:
    """Return the currently-configured default store (snapshot, thread-safe)."""
    with _default_store_lock:
        return _default_store


def _trajectory_key(trajectory_id: str) -> str:
    """Storage key convention for a single trajectory record."""
    return f"trajectory:{trajectory_id}"


class Trajectory:
    """Context-managed recording of one agent execution.

    ``Trajectory`` is the "black box recorder" for PRIMAL: open one with
    ``Trajectory.record(...)``, record steps via the ``record_*`` helpers
    (or raw ``add_step``), and either inspect it in memory or persist via
    ``save``. The full record is JSON-serializable.

    Example:
        >>> from primal_ai import Trajectory
        >>> with Trajectory.record(agent_id="search") as tr:
        ...     tr.record_input({"q": "flights"})
        ...     call = tr.record_tool_call("search", {"q": "flights"})
        ...     tr.record_tool_result(call.step_id, {"hits": 3}, cost=0.02)
        ...     tr.record_output({"answer": "..."})
        >>> tr.summary()["status"]
        'SUCCESS'
    """

    def __init__(
        self,
        *,
        trajectory_id: str | None = None,
        agent_id: str | None = None,
        parent_trajectory_id: str | None = None,
    ) -> None:
        self.trajectory_id: str = trajectory_id or uuid.uuid4().hex
        self.agent_id: str | None = agent_id
        self.parent_trajectory_id: str | None = parent_trajectory_id
        self.status: TrajectoryStatus = TrajectoryStatus.RUNNING
        self.started_at: float | None = None
        self.ended_at: float | None = None
        self._monotonic_start: float | None = None
        self._monotonic_end: float | None = None
        self._steps: list[Step] = []
        # Per-instance lock for add_step so concurrent recorders (e.g. a
        # threaded agent) don't interleave list mutations.
        self._steps_lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────────
    # Construction / context manager
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def record(
        cls,
        agent_id: str | None = None,
        *,
        parent_trajectory_id: str | None = None,
    ) -> Trajectory:
        """Create a fresh ``Trajectory`` ready for use as a context manager.

        Args:
            agent_id: Optional identifier for the agent being recorded.
            parent_trajectory_id: Optional link to a parent trajectory for
                nested executions (e.g. one agent delegating to another).
        """
        return cls(agent_id=agent_id, parent_trajectory_id=parent_trajectory_id)

    def __enter__(self) -> Trajectory:
        self.started_at = time.time()
        self._monotonic_start = time.monotonic()
        self.status = TrajectoryStatus.RUNNING
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc is not None:
            self.record_error(exc)
            self.status = TrajectoryStatus.FAILED
        else:
            self.status = TrajectoryStatus.SUCCESS
        self.ended_at = time.time()
        self._monotonic_end = time.monotonic()

        store = _get_default_store()
        if store is not None:
            self.save(store)
        # Never suppress the exception — context-manager protocol returns None.

    # ──────────────────────────────────────────────────────────────────
    # Step recording
    # ──────────────────────────────────────────────────────────────────

    def add_step(self, step: Step | dict[str, Any]) -> Step:
        """Append a ``Step`` (or a dict, coerced via ``Step.from_dict``)."""
        if isinstance(step, dict):
            step = Step.from_dict(step)
        with self._steps_lock:
            self._steps.append(step)
        return step

    def record_input(self, data: dict[str, Any]) -> Step:
        """Record an INPUT step (typically a user query or task spec)."""
        return self.add_step(Step(kind=StepKind.INPUT.value, data=dict(data)))

    def record_output(self, data: dict[str, Any]) -> Step:
        """Record an OUTPUT step (the agent's final answer)."""
        return self.add_step(Step(kind=StepKind.OUTPUT.value, data=dict(data)))

    def record_tool_call(self, tool_name: str, args: dict[str, Any]) -> Step:
        """Record a TOOL_CALL step. The returned step's ``step_id`` is the
        parent for the matching ``record_tool_result``."""
        return self.add_step(
            Step(
                kind=StepKind.TOOL_CALL.value,
                data={"tool_name": tool_name, "args": dict(args)},
            )
        )

    def record_tool_result(
        self,
        tool_call_step_id: str,
        result: Any,
        cost: float | None = None,
        latency_ms: float | None = None,
    ) -> Step:
        """Record a TOOL_RESULT step linked to a prior TOOL_CALL."""
        return self.add_step(
            Step(
                kind=StepKind.TOOL_RESULT.value,
                data={"result": result},
                cost=cost,
                latency_ms=latency_ms,
                parent_step_id=tool_call_step_id,
            )
        )

    def record_llm_call(
        self,
        model: str,
        messages: list[dict[str, Any]],
    ) -> Step:
        """Record an LLM_CALL step. The returned step's ``step_id`` is the
        parent for the matching ``record_llm_result``."""
        return self.add_step(
            Step(
                kind=StepKind.LLM_CALL.value,
                data={"model": model, "messages": list(messages)},
            )
        )

    def record_llm_result(
        self,
        llm_call_step_id: str,
        response: Any,
        cost: float | None = None,
        tokens: dict[str, int] | int | None = None,
        latency_ms: float | None = None,
    ) -> Step:
        """Record an LLM_RESULT step linked to a prior LLM_CALL."""
        return self.add_step(
            Step(
                kind=StepKind.LLM_RESULT.value,
                data={"response": response, "tokens": tokens},
                cost=cost,
                latency_ms=latency_ms,
                parent_step_id=llm_call_step_id,
            )
        )

    def record_error(self, exc: BaseException) -> Step:
        """Record an ERROR step capturing exception type, message, and traceback."""
        tb_text = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        return self.add_step(
            Step(
                kind=StepKind.ERROR.value,
                data={
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": tb_text,
                },
            )
        )

    # ──────────────────────────────────────────────────────────────────
    # Querying
    # ──────────────────────────────────────────────────────────────────

    def replay(self) -> Iterator[Step]:
        """Yield steps in insertion order. Iterator, not a list."""
        with self._steps_lock:
            snapshot = list(self._steps)
        yield from snapshot

    def find_steps(
        self,
        kind: StepKind | str | None = None,
        predicate: Callable[[Step], bool] | None = None,
    ) -> list[Step]:
        """Return steps matching ``kind`` and/or ``predicate`` (both optional)."""
        target_kind: str | None = kind.value if isinstance(kind, StepKind) else kind
        with self._steps_lock:
            snapshot = list(self._steps)
        results: list[Step] = []
        for step in snapshot:
            if target_kind is not None and step.kind != target_kind:
                continue
            if predicate is not None and not predicate(step):
                continue
            results.append(step)
        return results

    # ──────────────────────────────────────────────────────────────────
    # Summary / serialization
    # ──────────────────────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        """Return a stable-schema summary of this trajectory.

        Schema:
            ``trajectory_id``, ``agent_id``, ``status``, ``started_at``,
            ``ended_at``, ``duration_ms``, ``step_count``, ``total_cost``,
            ``step_kinds`` (dict counter by kind), ``error`` (first ERROR
            step's data, or ``None``).
        """
        with self._steps_lock:
            snapshot = list(self._steps)

        kinds: dict[str, int] = {}
        total_cost = 0.0
        error: dict[str, Any] | None = None
        for step in snapshot:
            kinds[step.kind] = kinds.get(step.kind, 0) + 1
            if step.cost is not None:
                total_cost += step.cost
            if error is None and step.kind == StepKind.ERROR.value:
                error = dict(step.data)

        if self._monotonic_start is not None:
            end = self._monotonic_end if self._monotonic_end is not None else time.monotonic()
            duration_ms: float | None = (end - self._monotonic_start) * 1000.0
        else:
            duration_ms = None

        return {
            "trajectory_id": self.trajectory_id,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": duration_ms,
            "step_count": len(snapshot),
            "total_cost": total_cost,
            "step_kinds": kinds,
            "error": error,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a full JSON-serializable view including every step."""
        with self._steps_lock:
            snapshot = list(self._steps)
        return {
            "trajectory_id": self.trajectory_id,
            "agent_id": self.agent_id,
            "parent_trajectory_id": self.parent_trajectory_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "steps": [s.to_dict() for s in snapshot],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Trajectory:
        """Rehydrate a ``Trajectory`` from a ``to_dict`` payload."""
        tr = cls(
            trajectory_id=str(payload["trajectory_id"]),
            agent_id=payload.get("agent_id"),
            parent_trajectory_id=payload.get("parent_trajectory_id"),
        )
        status_raw = payload.get("status")
        if status_raw is not None:
            tr.status = TrajectoryStatus(status_raw)
        started_raw = payload.get("started_at")
        ended_raw = payload.get("ended_at")
        tr.started_at = float(started_raw) if started_raw is not None else None
        tr.ended_at = float(ended_raw) if ended_raw is not None else None
        tr._steps = [Step.from_dict(s) for s in payload.get("steps") or []]
        return tr

    # ──────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────

    def save(self, store: Storage) -> None:
        """Persist the trajectory via the ``Storage`` Protocol.

        The key convention is ``trajectory:{trajectory_id}``. The value is
        the output of :meth:`to_dict`.
        """
        store.put(_trajectory_key(self.trajectory_id), self.to_dict())

    @classmethod
    def load(cls, trajectory_id: str, store: Storage) -> Trajectory:
        """Restore a trajectory previously persisted via :meth:`save`.

        Raises ``KeyError`` if the trajectory isn't in the store.
        """
        payload = store.get(_trajectory_key(trajectory_id))
        if payload is None:
            raise KeyError(f"trajectory not found: {trajectory_id}")
        return cls.from_dict(payload)


__all__ = ["Trajectory", "set_default_store"]
