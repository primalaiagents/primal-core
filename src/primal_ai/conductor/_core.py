"""Conductor facade — delegate, register_agent, find, set_active_trajectory.

The user-facing surface. Holds a module-level ``AgentRegistry`` plus a
module-level ``EventBus``; the facade methods are classmethods so callers
never need to instantiate ``Conductor``.

Delegation is synchronous in MVP. ``timeout_seconds`` is implemented via
``threading.Thread.join(timeout)`` — if the agent thread is still alive
after the budget, we return a TIMEOUT result and let the thread continue
in the background (Python doesn't safely kill threads). Async delegation
is documented as Phase 2 work.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from primal_ai._jsonschema import first_error
from primal_ai._trajectory_context import current_trajectory
from primal_ai.conductor._card import AgentCard, Capability
from primal_ai.conductor._delegation import DelegationResult, DelegationStatus
from primal_ai.conductor._events import Event, EventBus, EventKind
from primal_ai.conductor._registry import AgentRegistry

if TYPE_CHECKING:
    from primal_ai.conductor._agent import Agent

# Module-level singletons. Tests reset them between runs by direct manipulation
# (unregister_agent / event_bus.unsubscribe), so there's no global "clear all".
_REGISTRY = AgentRegistry()
_EVENT_BUS = EventBus()


def register_agent(agent: Agent) -> None:
    """Module-level shortcut for ``Conductor.register_agent``."""
    Conductor.register_agent(agent)


def unregister_agent(name: str) -> None:
    """Module-level shortcut for ``Conductor.unregister_agent``."""
    Conductor.unregister_agent(name)


class Conductor:
    """Multi-agent task router with capability-based discovery.

    Delegates a task to one agent (or picks one by capability), records
    inter-agent handoffs into the active ``Trajectory`` (when present),
    and emits lifecycle events on a sync ``EventBus`` so downstream
    observers can react.

    Example:
        >>> from primal_ai import (
        ...     AgentCard, Capability, Conductor, Pipeline, PipelineStep,
        ... )
        >>> class Echo:
        ...     name = "echo"
        ...     card = AgentCard(
        ...         name="echo",
        ...         description="...",
        ...         capabilities=(Capability(name="echo", description="..."),),
        ...     )
        ...     def invoke(self, input):
        ...         return {"echoed": input}
        >>> Conductor.register_agent(Echo())
        >>> result = Conductor.delegate("say hi", capability="echo", input="hi")
        >>> result.status.value
        'SUCCESS'
    """

    # Bus is exposed as a class attribute so tests + users can
    # subscribe/unsubscribe directly.
    event_bus: EventBus = _EVENT_BUS

    # ──────────────────────────────────────────────────────────────────
    # Registry surface
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def register_agent(cls, agent: Agent) -> None:
        """Add ``agent`` to the default registry. Raises ``ValueError`` on duplicate name."""
        _REGISTRY.register(agent)
        cls._publish(
            EventKind.AGENT_REGISTERED.value,
            {"agent": agent.name},
        )

    @classmethod
    def unregister_agent(cls, name: str) -> None:
        """Remove the agent named ``name`` from the default registry. No-op if absent."""
        had = _REGISTRY.get(name) is not None
        _REGISTRY.unregister(name)
        if had:
            cls._publish(EventKind.AGENT_UNREGISTERED.value, {"agent": name})

    @classmethod
    def get_agent(cls, name: str) -> Agent | None:
        """Return the agent named ``name``, or ``None`` if absent."""
        return _REGISTRY.get(name)

    @classmethod
    def list_agents(cls) -> list[AgentCard]:
        """Return every registered agent's ``AgentCard`` as a snapshot list."""
        return _REGISTRY.cards()

    @classmethod
    def find(
        cls,
        capability: str | None = None,
        tag: str | None = None,
    ) -> list[AgentCard]:
        """Find agents by capability and/or tag. Both filters AND together."""
        candidates: list[Agent]
        if capability is not None and tag is not None:
            by_cap = {a.name: a for a in _REGISTRY.find_by_capability(capability)}
            by_tag = {a.name: a for a in _REGISTRY.find_by_tag(tag)}
            common = set(by_cap) & set(by_tag)
            candidates = [by_cap[n] for n in common]
        elif capability is not None:
            candidates = _REGISTRY.find_by_capability(capability)
        elif tag is not None:
            candidates = _REGISTRY.find_by_tag(tag)
        else:
            candidates = _REGISTRY.all()
        return [a.card for a in candidates]

    # ──────────────────────────────────────────────────────────────────
    # Active-trajectory scope
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    @contextmanager
    def set_active_trajectory(cls, trajectory: Any) -> Iterator[Any]:
        """Context manager that scopes delegation recording to a specific trajectory.

        Inside the ``with`` block, every ``Conductor.delegate`` call
        records an ``AGENT_HANDOFF`` step on ``trajectory``. Outside, the
        ContextVar reverts to its prior value (``None`` if never set).

        Useful when you have a trajectory object but didn't open it as a
        context manager — or when you want a partial scope distinct from
        the surrounding trajectory.
        """
        token = current_trajectory.set(trajectory)
        try:
            yield trajectory
        finally:
            current_trajectory.reset(token)

    # ──────────────────────────────────────────────────────────────────
    # Delegation
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def delegate(
        cls,
        task: str,
        agents: Sequence[Agent] | None = None,
        *,
        capability: str | None = None,
        input: Any = None,
        timeout_seconds: float | None = None,
        from_agent: str | None = None,
    ) -> DelegationResult:
        """Delegate ``task`` to one agent and return a ``DelegationResult``.

        Resolution order for the target agent:
            1. If ``agents`` is provided, use the first one (after the
               optional capability + input-schema check).
            2. Otherwise, if ``capability`` is provided, search the
               default registry for agents that advertise it and use
               the first match.
            3. Otherwise, return REFUSED with "no target specified".

        This method NEVER raises — every failure mode (raising agent,
        unmatched capability, schema mismatch, timeout) becomes a
        ``DelegationResult`` with the appropriate ``status`` and a
        populated ``reason``.
        """
        started = time.time()
        started_mono = time.monotonic()

        target, refusal_reason = cls._resolve_target(agents, capability, input)
        if target is None:
            return cls._refused(
                task=task,
                input=input,
                capability=capability,
                from_agent=from_agent,
                reason=refusal_reason or "no target specified",
                started_at=started,
            )

        cls._publish(
            EventKind.DELEGATION_STARTED.value,
            {
                "from_agent": from_agent,
                "to_agent": target.name,
                "capability": capability,
                "task": task,
            },
        )

        status, output, reason = cls._invoke_target(target, input, timeout_seconds)
        ended = time.time()
        duration_ms = (time.monotonic() - started_mono) * 1000.0

        result = DelegationResult(
            delegation_id=uuid.uuid4().hex,
            from_agent=from_agent,
            to_agent=target.name,
            capability=capability,
            task=task,
            input=input,
            output=output,
            status=status,
            reason=reason,
            started_at=started,
            ended_at=ended,
            duration_ms=duration_ms,
        )

        cls._record_handoff(result)
        cls._publish_result(result)
        return result

    # ──────────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_target(
        agents: Sequence[Agent] | None,
        capability: str | None,
        input: Any,
    ) -> tuple[Agent | None, str | None]:
        """Pick the agent and pre-validate the input. Return ``(agent, refusal_reason)``."""
        # Choose candidate pool.
        candidates: list[Agent]
        if agents is not None and len(agents) > 0:
            candidates = list(agents)
            # When a capability is also given, prefer agents that advertise it.
            if capability is not None:
                filtered = [a for a in candidates if a.card.has_capability(capability)]
                if filtered:
                    candidates = filtered
        elif capability is not None:
            candidates = _REGISTRY.find_by_capability(capability)
        else:
            return None, "no agents and no capability specified"

        if not candidates:
            return None, f"no agent advertises capability {capability!r}"

        target = candidates[0]
        # Optional input-schema gate using the shared JSON Schema validator.
        if capability is not None:
            cap = _find_capability(target.card, capability)
            if cap is not None and cap.input_schema is not None:
                err = first_error(cap.input_schema, input)
                if err is not None:
                    return None, f"input rejected by capability schema: {err}"
        return target, None

    @staticmethod
    def _invoke_target(
        target: Agent,
        input: Any,
        timeout_seconds: float | None,
    ) -> tuple[DelegationStatus, Any, str | None]:
        """Run ``target.invoke(input)`` with an optional join-timeout."""
        if timeout_seconds is None:
            try:
                return DelegationStatus.SUCCESS, target.invoke(input), None
            except Exception as exc:  # noqa: BLE001 — convert any exception to FAILED
                return DelegationStatus.FAILED, None, f"{type(exc).__name__}: {exc}"

        # Threaded invocation so we can join with a budget. Note: Python
        # cannot safely kill a stuck thread, so a TIMEOUT means the agent
        # keeps running in the background — document this for users who
        # care about resource cleanup.
        outcome: dict[str, Any] = {"status": None, "output": None, "reason": None}

        def runner() -> None:
            try:
                outcome["output"] = target.invoke(input)
                outcome["status"] = DelegationStatus.SUCCESS
            except Exception as exc:  # noqa: BLE001
                outcome["status"] = DelegationStatus.FAILED
                outcome["reason"] = f"{type(exc).__name__}: {exc}"

        worker = threading.Thread(target=runner, daemon=True)
        worker.start()
        worker.join(timeout=timeout_seconds)
        if worker.is_alive():
            return (
                DelegationStatus.TIMEOUT,
                None,
                f"agent did not return within {timeout_seconds}s",
            )
        status = outcome["status"] or DelegationStatus.FAILED
        return status, outcome["output"], outcome["reason"]

    @staticmethod
    def _refused(
        *,
        task: str,
        input: Any,
        capability: str | None,
        from_agent: str | None,
        reason: str,
        started_at: float,
    ) -> DelegationResult:
        """Build (and publish) a REFUSED ``DelegationResult``."""
        ended = time.time()
        result = DelegationResult(
            delegation_id=uuid.uuid4().hex,
            from_agent=from_agent,
            to_agent="",  # no agent was selected
            capability=capability,
            task=task,
            input=input,
            output=None,
            status=DelegationStatus.REFUSED,
            reason=reason,
            started_at=started_at,
            ended_at=ended,
            duration_ms=(ended - started_at) * 1000.0,
        )
        Conductor._record_handoff(result)
        Conductor._publish(
            EventKind.DELEGATION_FAILED.value,
            {"result": result.to_dict()},
        )
        return result

    @staticmethod
    def _publish(kind: str, payload: dict[str, Any]) -> None:
        """Convenience wrapper to publish an ``Event`` on the module bus."""
        _EVENT_BUS.publish(Event(kind=kind, payload=payload))

    @staticmethod
    def _publish_result(result: DelegationResult) -> None:
        """Publish the appropriate COMPLETED / FAILED event for ``result``."""
        kind = (
            EventKind.DELEGATION_COMPLETED.value
            if result.status == DelegationStatus.SUCCESS
            else EventKind.DELEGATION_FAILED.value
        )
        Conductor._publish(kind, {"result": result.to_dict()})

    @staticmethod
    def _record_handoff(result: DelegationResult) -> None:
        """Append an ``AGENT_HANDOFF`` step to the active trajectory, if any."""
        tr = current_trajectory.get()
        if tr is None:
            return
        # Use the dict form so we don't import Step here — keeps Conductor
        # independent of the Trajectory package internals.
        tr.add_step(
            {
                "kind": "AGENT_HANDOFF",
                "data": {
                    "from_agent": result.from_agent,
                    "to_agent": result.to_agent,
                    "capability": result.capability,
                    "task": result.task,
                    "status": result.status.value,
                    "duration_ms": result.duration_ms,
                },
            },
        )


def _find_capability(card: AgentCard, name: str) -> Capability | None:
    """Return the named capability on ``card``, or ``None`` if absent."""
    for cap in card.capabilities:
        if cap.name == name:
            return cap
    return None


__all__ = ["Conductor", "register_agent", "unregister_agent"]
