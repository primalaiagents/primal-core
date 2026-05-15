"""Guardian core — wrap, wrap_async, escalate, dry-run.

Glue between user-facing API and the policy primitives. ``Guardian`` is a
class with only class-level state (the escalation handler and the
dry-run violation buffer) so callers never need to instantiate it.
"""

from __future__ import annotations

import inspect
import logging
import threading
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from typing import Any, cast

from primal_ai.guardian._policy import Policy, PolicyViolation
from primal_ai.observability import add_event, record_exception, span

_logger = logging.getLogger("primal_ai.guardian")

# Module-level state. The escalation handler is a single configurable
# callback; the dry-run buffer is per-context (works in async tasks and
# threads without leaking violations between unrelated callers).
_escalation_handler: Callable[[Any], None] | None = None
_escalation_lock = threading.Lock()
_dry_run_violations: ContextVar[list[PolicyViolation] | None] = ContextVar(
    "primal_ai_guardian_dry_run", default=None
)


def _default_escalation_handler(item: Any) -> None:
    """Default handler — logs the violation on the ``primal_ai.guardian`` logger."""
    if isinstance(item, PolicyViolation):
        _logger.warning("guardian violation: %s", item.to_dict())
    else:
        _logger.warning("guardian escalate: %r", item)


def _resolve_policies(policies: Sequence[Policy | str] | None) -> list[Policy]:
    """Resolve a mixed list of ``Policy`` objects and DSL strings into ``Policy`` objects."""
    if not policies:
        return []
    # Local import — _dsl depends on _policy but not _core, breaking the cycle.
    from primal_ai.guardian._dsl import parse_policy

    resolved: list[Policy] = []
    for item in policies:
        if isinstance(item, str):
            resolved.append(parse_policy(item))
        else:
            resolved.append(item)
    return resolved


def _run_pre(resolved: list[Policy], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    """Run every pre-hook in declared order. Honors dry-run mode."""
    for policy in resolved:
        check_pre = getattr(policy, "check_pre", None)
        if check_pre is None:
            continue
        try:
            check_pre(args, kwargs)
        except PolicyViolation as v:
            _handle_violation(v)


def _run_post(
    resolved: list[Policy],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    result: Any,
) -> Any:
    """Run every post-hook in declared order. May return a replacement result."""
    for policy in resolved:
        check_post = getattr(policy, "check_post", None)
        if check_post is None:
            continue
        try:
            replacement = check_post(args, kwargs, result)
        except PolicyViolation as v:
            _handle_violation(v)
            continue
        if replacement is not None:
            result = replacement
    return result


def _handle_violation(v: PolicyViolation) -> None:
    """Either record (under dry-run) or escalate-and-raise."""
    buf = _dry_run_violations.get()
    if buf is not None:
        buf.append(v)
        add_event(
            "primal.guardian.violation",
            {
                "primal.guardian.policy": v.policy_name,
                "primal.guardian.reason": v.reason,
                "primal.guardian.phase": v.phase,
                "primal.guardian.dry_run": True,
            },
        )
        return
    add_event(
        "primal.guardian.violation",
        {
            "primal.guardian.policy": v.policy_name,
            "primal.guardian.reason": v.reason,
            "primal.guardian.phase": v.phase,
            "primal.guardian.dry_run": False,
        },
    )
    Guardian.escalate(v)
    raise v


class Guardian:
    """Policy-enforced agent wrapper.

    ``Guardian`` provides three things:

    1. A ``wrap`` / ``wrap_async`` function that turns a plain callable
       into one that runs registered ``Policy`` checks before and after
       every invocation.
    2. A pluggable escalation channel (``escalate`` + ``set_escalation_handler``)
       so violations can be routed to logs, metrics, or webhooks.
    3. A ``dry_run`` context manager that records violations without
       raising — useful for shadow-evaluating new policies against live
       traffic before enforcement.

    Example:
        >>> from primal_ai import Guardian, RateLimit
        >>> def agent(q: str) -> str:
        ...     return f"results: {q}"
        >>> wrapped = Guardian.wrap(agent, policies=[RateLimit(per_minute=60)])
        >>> wrapped("flights to tokyo")
        'results: flights to tokyo'
    """

    # ──────────────────────────────────────────────────────────────────
    # Wrapping
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def wrap(
        cls,
        agent: Callable[..., Any],
        policies: Sequence[Policy | str] | None = None,
    ) -> Callable[..., Any]:
        """Wrap a callable with Guardian policies.

        Accepts both ``Policy`` instances and DSL strings (parsed via the
        registry in :mod:`primal_ai.guardian._dsl`). Coroutine functions
        are auto-detected — the returned wrapper is awaitable in that
        case. For explicit clarity in async code, use :meth:`wrap_async`.

        Args:
            agent: The agent callable to wrap.
            policies: Sequence of ``Policy`` objects or DSL strings.

        Returns:
            A new callable with the same signature as ``agent`` that runs
            policy checks before and after each invocation.
        """
        resolved = _resolve_policies(policies)
        if inspect.iscoroutinefunction(agent):
            async_agent = cast(Callable[..., Awaitable[Any]], agent)
            return _build_async_wrapper(async_agent, resolved)
        return _build_sync_wrapper(agent, resolved)

    @classmethod
    def wrap_async(
        cls,
        agent: Callable[..., Awaitable[Any]],
        policies: Sequence[Policy | str] | None = None,
    ) -> Callable[..., Awaitable[Any]]:
        """Explicit async variant of :meth:`wrap`.

        Use when the caller already knows ``agent`` is a coroutine
        function and wants a typed awaitable wrapper.
        """
        resolved = _resolve_policies(policies)
        return _build_async_wrapper(agent, resolved)

    # ──────────────────────────────────────────────────────────────────
    # Escalation
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def escalate(cls, violation_or_trajectory: Any) -> None:
        """Forward a violation (or trajectory) to the configured handler.

        Default behavior is to log at WARNING on the ``primal_ai.guardian``
        logger. Replace with :meth:`set_escalation_handler` to route to a
        webhook, metrics sink, or Trajectory recorder.

        If a ``Trajectory`` is passed (duck-typed via ``add_step``), a
        ``POLICY_VIOLATION`` step is recorded on it before the handler is
        invoked. Bare ``PolicyViolation`` objects flow through unchanged.
        """
        if hasattr(violation_or_trajectory, "add_step"):
            # Trajectory handoff — record a marker step so the recorded
            # trajectory shows where escalation occurred. Never break
            # escalation if the trajectory's add_step raises.
            with suppress(Exception):
                violation_or_trajectory.add_step(
                    {
                        "kind": "POLICY_VIOLATION",
                        "data": {"escalated": True},
                    },
                )

        with _escalation_lock:
            handler = _escalation_handler
        if handler is None:
            _default_escalation_handler(violation_or_trajectory)
        else:
            handler(violation_or_trajectory)

    @classmethod
    def set_escalation_handler(cls, handler: Callable[[Any], None] | None) -> None:
        """Register (or clear) the escalation handler.

        Passing ``None`` restores the stderr logging default. The handler
        receives whatever was passed to :meth:`escalate` — typically a
        ``PolicyViolation``.
        """
        global _escalation_handler  # noqa: PLW0603 — single module-level slot is intentional
        with _escalation_lock:
            _escalation_handler = handler

    # ──────────────────────────────────────────────────────────────────
    # Dry-run mode
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    @contextmanager
    def dry_run(cls) -> Iterator[list[PolicyViolation]]:
        """Context manager: record violations without raising.

        Lets users replay live traffic through a candidate policy set and
        observe what would have been blocked. The buffer is per-context
        (via :class:`contextvars.ContextVar`), so nested or async-task
        usage is safe.

        Example:
            >>> with Guardian.dry_run():
            ...     wrapped("some input")
            ...     violations = Guardian.get_dry_run_violations()
        """
        buf: list[PolicyViolation] = []
        token = _dry_run_violations.set(buf)
        try:
            yield buf
        finally:
            _dry_run_violations.reset(token)

    @classmethod
    def get_dry_run_violations(cls) -> list[PolicyViolation]:
        """Return the in-progress dry-run buffer, or ``[]`` outside dry-run."""
        buf = _dry_run_violations.get()
        return list(buf) if buf is not None else []


def _build_sync_wrapper(
    agent: Callable[..., Any], resolved: list[Policy]
) -> Callable[..., Any]:
    """Build a synchronous wrapper closure."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with span(
            "primal.guardian.invoke",
            {
                "primal.guardian.policy_count": len(resolved),
                "primal.guardian.dry_run": _dry_run_violations.get() is not None,
            },
        ) as s:
            try:
                _run_pre(resolved, args, kwargs)
                result = agent(*args, **kwargs)
                final = _run_post(resolved, args, kwargs, result)
            except PolicyViolation as exc:
                s.set_attribute("primal.guardian.status", "VIOLATION")
                s.set_status(_otel_error_status(exc.reason))
                record_exception(exc)
                raise
            except BaseException as exc:
                s.set_attribute("primal.guardian.status", "AGENT_ERROR")
                s.set_status(_otel_error_status(str(exc)))
                record_exception(exc)
                raise
            s.set_attribute("primal.guardian.status", "OK")
            return final

    return wrapper


def _build_async_wrapper(
    agent: Callable[..., Awaitable[Any]], resolved: list[Policy]
) -> Callable[..., Awaitable[Any]]:
    """Build an asynchronous wrapper coroutine function."""

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        with span(
            "primal.guardian.invoke",
            {
                "primal.guardian.policy_count": len(resolved),
                "primal.guardian.dry_run": _dry_run_violations.get() is not None,
            },
        ) as s:
            try:
                _run_pre(resolved, args, kwargs)
                result = await agent(*args, **kwargs)
                final = _run_post(resolved, args, kwargs, result)
            except PolicyViolation as exc:
                s.set_attribute("primal.guardian.status", "VIOLATION")
                s.set_status(_otel_error_status(exc.reason))
                record_exception(exc)
                raise
            except BaseException as exc:
                s.set_attribute("primal.guardian.status", "AGENT_ERROR")
                s.set_status(_otel_error_status(str(exc)))
                record_exception(exc)
                raise
            s.set_attribute("primal.guardian.status", "OK")
            return final

    return wrapper


def _otel_error_status(description: str) -> Any:
    """Return an OTel ``Status(StatusCode.ERROR, description)`` or ``None``.

    Deferred import keeps Guardian import-safe when ``opentelemetry-api``
    isn't installed.
    """
    try:
        from opentelemetry.trace import Status, StatusCode
    except ImportError:
        return None
    return Status(StatusCode.ERROR, description)


__all__ = ["Guardian"]
