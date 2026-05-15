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
from contextvars import Token
from types import TracebackType
from typing import Any, ClassVar

from primal_ai._trajectory_context import current_trajectory
from primal_ai.observability import record_exception, span
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
        # Token returned by ``ContextVar.set`` on __enter__, consumed on __exit__.
        self._context_token: Token[Any] | None = None
        # Open OTel span scope held across the with-block. Both slots are
        # ``Any`` to avoid leaking opentelemetry into our type surface.
        self._otel_span_cm: Any = None
        self._otel_span: Any = None
        # step_id → (otel-span-cm, otel-span). Filled on record_*_call,
        # drained on record_*_result. Anything left over at __exit__ is
        # ended with the ``orphaned`` attribute.
        self._open_step_spans: dict[str, tuple[Any, Any]] = {}

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
        # Open the OTel root span first so any pillar span created from
        # inside the with-block becomes a child of this one.
        self._otel_span_cm = span(
            "primal.trajectory.session",
            {
                "primal.trajectory.id": self.trajectory_id,
                "primal.trajectory.agent_id": self.agent_id or "",
                "primal.trajectory.parent_id": self.parent_trajectory_id or "",
            },
        )
        self._otel_span = self._otel_span_cm.__enter__()
        # Publish self as the active trajectory for this context (thread or
        # async task). Conductor.delegate reads this to record AGENT_HANDOFF
        # steps without either pillar reaching into the other.
        self._context_token = current_trajectory.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # Clear the context-var first so any escalation handler that runs
        # during shutdown can't accidentally record into a closing trajectory.
        if self._context_token is not None:
            current_trajectory.reset(self._context_token)
            self._context_token = None

        if exc is not None:
            self.record_error(exc)
            self.status = TrajectoryStatus.FAILED
        else:
            self.status = TrajectoryStatus.SUCCESS
        self.ended_at = time.time()
        self._monotonic_end = time.monotonic()

        # Close any open paired spans that never got a result. They show
        # up in traces as completed-but-orphaned so users can see partial
        # tool/llm invocations clearly. When the trajectory exits via an
        # exception we forward ``(exc_type, exc, tb)`` to each open span's
        # ``__exit__`` so OTel records the exception + sets ERROR status
        # on the in-flight tool/llm spans (not just the session span).
        for call_id, (cm, s) in list(self._open_step_spans.items()):
            s.set_attribute("primal.trajectory.orphaned", True)
            cm.__exit__(exc_type, exc, tb)
            self._open_step_spans.pop(call_id, None)

        # Decorate the OTel span before closing it.
        if self._otel_span is not None:
            summary = self.summary()
            self._otel_span.set_attribute(
                "primal.trajectory.status", self.status.value,
            )
            self._otel_span.set_attribute(
                "primal.trajectory.step_count", summary["step_count"],
            )
            duration_ms = summary["duration_ms"]
            if duration_ms is not None:
                self._otel_span.set_attribute(
                    "primal.trajectory.duration_ms", duration_ms,
                )
            self._otel_span.set_attribute(
                "primal.trajectory.total_cost", summary["total_cost"],
            )
            # Rollups by step kind so traces can be filtered by activity
            # type without scanning span events.
            for kind, count in summary["step_kinds"].items():
                self._otel_span.set_attribute(
                    f"primal.trajectory.step_kinds.{kind.lower()}", count,
                )
            if exc is not None:
                record_exception(exc)
                self._otel_span.set_status(_otel_error_status(str(exc)))

        if self._otel_span_cm is not None:
            self._otel_span_cm.__exit__(exc_type, exc, tb)
            self._otel_span_cm = None
            self._otel_span = None

        store = _get_default_store()
        if store is not None:
            self.save(store)
        # Never suppress the exception — context-manager protocol returns None.

    # ──────────────────────────────────────────────────────────────────
    # Step recording
    # ──────────────────────────────────────────────────────────────────

    # Step kinds that flow through the paired-span machinery (T06).
    _PAIRED_KINDS: ClassVar[frozenset[str]] = frozenset(
        {
            StepKind.TOOL_CALL.value,
            StepKind.TOOL_RESULT.value,
            StepKind.LLM_CALL.value,
            StepKind.LLM_RESULT.value,
        },
    )

    def add_step(self, step: Step | dict[str, Any]) -> Step:
        """Append a ``Step`` (or a dict, coerced via ``Step.from_dict``)."""
        if isinstance(step, dict):
            step = Step.from_dict(step)
        with self._steps_lock:
            self._steps.append(step)
        if step.kind not in self._PAIRED_KINDS and self._otel_span is not None:
            self._otel_span.add_event(
                "primal.trajectory.step",
                {
                    "primal.trajectory.step.kind": step.kind,
                    "primal.trajectory.step.id": step.step_id,
                },
            )
        return step

    def record_input(self, data: dict[str, Any]) -> Step:
        """Record an INPUT step (typically a user query or task spec)."""
        return self.add_step(Step(kind=StepKind.INPUT.value, data=dict(data)))

    def record_output(self, data: dict[str, Any]) -> Step:
        """Record an OUTPUT step (the agent's final answer)."""
        return self.add_step(Step(kind=StepKind.OUTPUT.value, data=dict(data)))

    def _start_step_span(
        self, name: str, attrs: dict[str, Any], step_id: str,
    ) -> None:
        """Open a child span for a paired ``record_*_call`` step."""
        cm = span(name, attrs)
        s = cm.__enter__()
        self._open_step_spans[step_id] = (cm, s)

    def _end_step_span(
        self,
        call_step_id: str,
        result_attrs: dict[str, Any],
    ) -> None:
        """End a child span opened by a matching ``record_*_call``.

        If ``call_step_id`` doesn't match an open span, this is a no-op —
        callers may legitimately pair a result against a synthetic id
        (e.g. recovered from a serialized trajectory).
        """
        entry = self._open_step_spans.pop(call_step_id, None)
        if entry is None:
            return
        cm, s = entry
        for k, v in result_attrs.items():
            if v is not None:
                s.set_attribute(k, v)
        cm.__exit__(None, None, None)

    def record_tool_call(self, tool_name: str, args: dict[str, Any]) -> Step:
        """Record a TOOL_CALL step. The returned step's ``step_id`` is the
        parent for the matching ``record_tool_result``."""
        step = Step(
            kind=StepKind.TOOL_CALL.value,
            data={"tool_name": tool_name, "args": dict(args)},
        )
        # We open the OTel span *before* appending so the span captures
        # creation time accurately (add_step takes a lock).
        if self._otel_span is not None:
            self._start_step_span(
                "primal.trajectory.tool_call",
                {
                    "primal.trajectory.tool_name": tool_name,
                    "primal.trajectory.step.id": step.step_id,
                },
                step.step_id,
            )
        with self._steps_lock:
            self._steps.append(step)
        return step

    def record_tool_result(
        self,
        tool_call_step_id: str,
        result: Any,
        cost: float | None = None,
        latency_ms: float | None = None,
    ) -> Step:
        """Record a TOOL_RESULT step linked to a prior TOOL_CALL."""
        step = Step(
            kind=StepKind.TOOL_RESULT.value,
            data={"result": result},
            cost=cost,
            latency_ms=latency_ms,
            parent_step_id=tool_call_step_id,
        )
        # End the matching span before appending the result step.
        if self._otel_span is not None:
            self._end_step_span(
                tool_call_step_id,
                {
                    "primal.trajectory.cost": cost,
                    "primal.trajectory.latency_ms": latency_ms,
                },
            )
        with self._steps_lock:
            self._steps.append(step)
        return step

    def record_llm_call(
        self,
        model: str,
        messages: list[dict[str, Any]],
    ) -> Step:
        """Record an LLM_CALL step. The returned step's ``step_id`` is the
        parent for the matching ``record_llm_result``."""
        step = Step(
            kind=StepKind.LLM_CALL.value,
            data={"model": model, "messages": list(messages)},
        )
        if self._otel_span is not None:
            self._start_step_span(
                "primal.trajectory.llm_call",
                {
                    "primal.trajectory.model": model,
                    "primal.trajectory.step.id": step.step_id,
                },
                step.step_id,
            )
        with self._steps_lock:
            self._steps.append(step)
        return step

    def record_llm_result(
        self,
        llm_call_step_id: str,
        response: Any,
        cost: float | None = None,
        tokens: dict[str, int] | int | None = None,
        latency_ms: float | None = None,
    ) -> Step:
        """Record an LLM_RESULT step linked to a prior LLM_CALL."""
        step = Step(
            kind=StepKind.LLM_RESULT.value,
            data={"response": response, "tokens": tokens},
            cost=cost,
            latency_ms=latency_ms,
            parent_step_id=llm_call_step_id,
        )
        if self._otel_span is not None:
            self._end_step_span(
                llm_call_step_id,
                {
                    "primal.trajectory.cost": cost,
                    "primal.trajectory.latency_ms": latency_ms,
                },
            )
        with self._steps_lock:
            self._steps.append(step)
        return step

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


def _otel_error_status(description: str) -> Any:
    """Return an OTel ``Status(StatusCode.ERROR, description)`` or ``None``.

    Imports are deferred so the trajectory module stays import-safe when
    ``opentelemetry-api`` isn't installed. The returned object is passed
    straight back to ``Span.set_status`` (which is a no-op on the shim's
    NoOpSpan).
    """
    try:
        from opentelemetry.trace import Status, StatusCode
    except ImportError:
        return None
    return Status(StatusCode.ERROR, description)


__all__ = ["Trajectory", "set_default_store"]
