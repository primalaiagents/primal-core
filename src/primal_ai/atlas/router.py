"""Atlas facade — register/find/route/invoke/get_health/reset_health.

Deterministic MVP selection: first healthy candidate by declared order
(or by registry order when no ``candidates`` list is given). Bandit-driven
selection ships in Phase 1 Session 8 — :class:`primal_ai.atlas.bandit.Bandit`
is currently a stub that raises clearly.

``route`` and ``invoke`` NEVER raise. Provider crashes, missing
candidates, unhealthy providers — all return a structured outcome.
"""

from __future__ import annotations

import threading
import time
import uuid
from contextlib import suppress
from typing import Any

from primal_ai._events import Event, EventBus, EventKind, default_bus
from primal_ai._trajectory_context import current_trajectory
from primal_ai.atlas._decision import RoutingDecision, RoutingStatus
from primal_ai.atlas._health import ProviderHealth
from primal_ai.atlas._provider import Provider, ProviderInfo
from primal_ai.atlas._registry import ProviderRegistry
from primal_ai.atlas.bandit import (
    Bandit,
    BanditOutcome,
    _safe_update,
    resolve_selector,
)

# Module-level singletons. Reset between tests via ``Atlas.reset_health``
# / ``unregister_provider``; there is no global "clear all" by design.
_REGISTRY = ProviderRegistry()
_EVENT_BUS: EventBus = default_bus

# Active selector for bandit-driven routing. ``None`` → deterministic.
_active_selector: Bandit | None = None
_selector_lock = threading.Lock()


def register_provider(provider: Provider) -> None:
    """Module-level shortcut for :meth:`Atlas.register_provider`."""
    Atlas.register_provider(provider)


def unregister_provider(name: str) -> None:
    """Module-level shortcut for :meth:`Atlas.unregister_provider`."""
    Atlas.unregister_provider(name)


class Atlas:
    """Smart-routing facade — pick a provider, optionally invoke it, never raise.

    MVP selection is deterministic. The bandit / cost-aware ranking layer
    arrives in Session 8 and slots in behind the same public surface, so
    user code written against this MVP will keep working.

    Example:
        >>> from primal_ai import Atlas, BYOProvider, ProviderInfo
        >>> Atlas.register_provider(
        ...     BYOProvider(
        ...         name="echo",
        ...         call=lambda task, **kw: f"echoed: {task}",
        ...         info=ProviderInfo(name="echo", capabilities=("chat",)),
        ...     ),
        ... )
        >>> Atlas.route("hi")
        'echo'
        >>> name, result = Atlas.invoke("hi")
        >>> name
        'echo'
        >>> result
        'echoed: hi'
    """

    event_bus: EventBus = _EVENT_BUS

    # ──────────────────────────────────────────────────────────────────
    # Registry surface
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def register_provider(cls, provider: Provider) -> None:
        """Add ``provider`` to the default registry. Raise ``ValueError`` on duplicate name."""
        _REGISTRY.register(provider)

    @classmethod
    def unregister_provider(cls, name: str) -> None:
        """Remove the provider named ``name``. No-op if absent."""
        _REGISTRY.unregister(name)

    @classmethod
    def get_provider(cls, name: str) -> Provider | None:
        """Return the provider named ``name``, or ``None`` if absent."""
        return _REGISTRY.get(name)

    @classmethod
    def list_providers(cls) -> list[ProviderInfo]:
        """Return every registered provider's ``ProviderInfo`` as a snapshot list."""
        return _REGISTRY.infos()

    @classmethod
    def find(
        cls,
        capability: str | None = None,
        tag: str | None = None,
    ) -> list[ProviderInfo]:
        """Find providers by capability and/or tag. Both filters AND together."""
        if capability is not None and tag is not None:
            by_cap = {p.name: p for p in _REGISTRY.find_by_capability(capability)}
            by_tag = {p.name: p for p in _REGISTRY.find_by_tag(tag)}
            matched = [by_cap[n] for n in by_cap if n in by_tag]
        elif capability is not None:
            matched = _REGISTRY.find_by_capability(capability)
        elif tag is not None:
            matched = _REGISTRY.find_by_tag(tag)
        else:
            matched = _REGISTRY.all()
        return [p.info for p in matched]

    # ──────────────────────────────────────────────────────────────────
    # Health surface
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def get_health(cls, name: str) -> ProviderHealth | None:
        """Return the per-provider ``ProviderHealth``, or ``None`` if the provider is absent."""
        return _REGISTRY.get_health(name)

    @classmethod
    def reset_health(cls, name: str | None = None) -> None:
        """Clear cooldown(s). ``None`` resets every registered provider."""
        _REGISTRY.reset_health(name)

    # ──────────────────────────────────────────────────────────────────
    # Bandit selector surface
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def set_selector(cls, selector: Bandit | str | None) -> None:
        """Install a default bandit selector (or revert to deterministic with ``None``).

        Accepts a ``Bandit`` instance, a registered selector name string
        (``"thompson"``, ``"ucb1"``, or anything added via
        :func:`primal_ai.atlas.bandit.register_selector`), or ``None``.
        """
        if selector is None:
            resolved: Bandit | None = None
        elif isinstance(selector, str):
            resolved = resolve_selector(selector)
        else:
            resolved = selector
        with _selector_lock:
            global _active_selector  # noqa: PLW0603 — single module-level slot
            _active_selector = resolved

    @classmethod
    def get_selector(cls) -> Bandit | None:
        """Return the currently-installed default selector, or ``None``."""
        with _selector_lock:
            return _active_selector

    @classmethod
    def feedback(cls, outcome: BanditOutcome) -> None:
        """Forward a ``BanditOutcome`` to the active selector.

        Convenience for callers that score provider outputs after the
        fact (for example, a Verifier verdict produced post-hoc). When no
        selector is active, the call is silently a no-op.
        """
        _safe_update(cls.get_selector(), outcome)

    # ──────────────────────────────────────────────────────────────────
    # Routing
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def route(
        cls,
        task: str,
        candidates: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Pick the best healthy provider for ``task``. Return the provider's name.

        Selection (MVP, deterministic):
            1. Resolve candidate pool — explicit names (preserving order)
               or every registered provider.
            2. Filter by ``context["capability"]`` (if set) and
               ``context["tags"]`` (if set; every tag must be present).
            3. Drop providers currently in cooldown.
            4. Return the first survivor.

        Always returns a string. ``""`` indicates no provider could be
        chosen — the ``RoutingDecision.status`` (recorded on the active
        trajectory and emitted on the shared bus) carries the reason.
        """
        decision = cls._decide(task, candidates, context)
        cls._record_routing_decision(decision)
        return decision.chosen_provider or ""

    @classmethod
    def invoke(
        cls,
        task: str,
        *,
        candidates: list[str] | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[str, Any]:
        """Route + invoke convenience. Return ``(provider_name, result)``.

        On success: the chosen provider's name and the call's result.
        On failure (no candidates / unhealthy / provider raised): the
        chosen provider's name (or ``""``) and ``None``. Health counters
        are updated on both success and failure; failures incur a
        single base-cooldown penalty (Cascade owns the exponential
        backoff policy when callers care about retries).
        """
        decision = cls._decide(task, candidates, context)
        cls._record_routing_decision(decision)

        if decision.chosen_provider is None:
            return "", None

        provider = _REGISTRY.get(decision.chosen_provider)
        health = _REGISTRY.get_health(decision.chosen_provider)
        if provider is None or health is None:
            return decision.chosen_provider, None

        selector = _resolve_selector_for_call(context)
        bandit_ctx_key = _bandit_context_key(context)
        try:
            result = provider.invoke(task, **kwargs)
        except Exception:  # noqa: BLE001 — convert any exception to a failure record
            health.record_failure(cooldown_seconds=_DEFAULT_FAILURE_COOLDOWN_S)
            _safe_update(
                selector,
                BanditOutcome(
                    provider_name=decision.chosen_provider,
                    success=False,
                    reward=0.0,
                    context_key=bandit_ctx_key,
                ),
            )
            return decision.chosen_provider, None
        health.record_success()
        _safe_update(
            selector,
            BanditOutcome(
                provider_name=decision.chosen_provider,
                success=True,
                reward=1.0,
                context_key=bandit_ctx_key,
            ),
        )
        return decision.chosen_provider, result

    # ──────────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def _decide(
        cls,
        task: str,
        candidates: list[str] | None,
        context: dict[str, Any] | None,
    ) -> RoutingDecision:
        """Compute a ``RoutingDecision`` without invoking the chosen provider."""
        started = time.time()
        started_mono = time.monotonic()
        ctx = dict(context or {})

        # Step 1: resolve candidate pool, preserving order.
        if candidates is None:
            pool: list[Provider] = _REGISTRY.all()
        else:
            pool = []
            skipped: list[tuple[str, str]] = []
            for name in candidates:
                provider = _REGISTRY.get(name)
                if provider is None:
                    skipped.append((name, "not_registered"))
                else:
                    pool.append(provider)
        considered = tuple(p.name for p in pool) if candidates is None else tuple(candidates)
        if candidates is not None:
            # Re-scan to build the skipped list since we collected it inline.
            skipped = [(n, "not_registered") for n in candidates if _REGISTRY.get(n) is None]
        else:
            skipped = []

        # Step 2: capability / tag filters.
        capability = ctx.get("capability")
        tags = ctx.get("tags") or []
        if capability is not None:
            new_pool: list[Provider] = []
            for p in pool:
                if p.info.has_capability(capability):
                    new_pool.append(p)
                else:
                    skipped.append((p.name, f"no_capability:{capability}"))
            pool = new_pool
        if tags:
            new_pool = []
            for p in pool:
                missing = [t for t in tags if not p.info.has_tag(t)]
                if missing:
                    skipped.append((p.name, f"missing_tags:{','.join(missing)}"))
                else:
                    new_pool.append(p)
            pool = new_pool

        # Step 3: health filter.
        healthy: list[Provider] = []
        for p in pool:
            health = _REGISTRY.get_health(p.name)
            if health is None or health.is_healthy():
                healthy.append(p)
            else:
                skipped.append((p.name, "unhealthy"))

        # Step 4: pick. Honor the bandit selector when one is active for this call.
        selector = _resolve_selector_for_call(ctx)
        selector_name: str | None = None
        arm_scores: dict[str, float] | None = None
        exploration_factor: float | None = None

        if not pool and (candidates is not None or capability is not None or tags):
            status = RoutingStatus.NO_CANDIDATES
            chosen: str | None = None
            reason = "no providers matched the filters"
        elif not pool:
            status = RoutingStatus.NO_CANDIDATES
            chosen = None
            reason = "no providers are registered"
        elif not healthy:
            status = RoutingStatus.ALL_UNHEALTHY
            chosen = None
            reason = "every matching provider is in cooldown"
        elif selector is not None:
            healthy_names = [p.name for p in healthy]
            chosen, arm_scores, exploration_factor = _select_via_bandit(
                selector, healthy_names, ctx,
            )
            selector_name = getattr(selector, "name", type(selector).__name__)
            if chosen is None:
                status = RoutingStatus.NO_CANDIDATES
                reason = f"selector {selector_name!r} returned no choice"
            else:
                status = RoutingStatus.SUCCESS
                reason = None
        else:
            status = RoutingStatus.SUCCESS
            chosen = healthy[0].name
            reason = None

        ended = time.time()
        duration_ms = (time.monotonic() - started_mono) * 1000.0
        return RoutingDecision(
            decision_id=uuid.uuid4().hex,
            task=task,
            chosen_provider=chosen,
            candidates_considered=considered,
            candidates_skipped=tuple(skipped),
            status=status,
            reason=reason,
            started_at=started,
            ended_at=ended,
            duration_ms=duration_ms,
            context=ctx,
            selector_name=selector_name,
            arm_scores=arm_scores,
            exploration_factor=exploration_factor,
        )

    @staticmethod
    def _record_routing_decision(decision: RoutingDecision) -> None:
        """Publish the decision on the shared bus + record it onto the active trajectory."""
        _EVENT_BUS.publish(
            Event(
                kind=EventKind.ROUTING_DECIDED.value,
                payload={"decision": decision.to_dict()},
            ),
        )
        tr = current_trajectory.get()
        if tr is not None:
            with suppress(Exception):
                tr.add_step(
                    {
                        "kind": "ROUTING_DECISION",
                        "data": decision.to_dict(),
                    },
                )


# Default cooldown applied on a single ``Atlas.invoke`` failure. Cascade
# overrides this with its own exponential-backoff policy.
_DEFAULT_FAILURE_COOLDOWN_S: float = 30.0


# ──────────────────────────────────────────────────────────────────────
# Selector resolution helpers
# ──────────────────────────────────────────────────────────────────────


def _resolve_selector_for_call(context: dict[str, Any] | None) -> Bandit | None:
    """Pick the selector for this call. Per-call override beats the global default.

    ``context["selector"]`` may be a string (resolved via the bandit
    registry) or a ``Bandit`` instance. ``None`` or absent falls back to
    ``Atlas.get_selector()``.
    """
    if context is not None:
        override = context.get("selector")
        if isinstance(override, str):
            return resolve_selector(override)
        # The runtime check via the ``Bandit`` Protocol gives mypy the
        # narrowing it needs; non-Bandit values fall through.
        if override is not None and isinstance(override, Bandit):
            return override
    return Atlas.get_selector()


def _bandit_context_key(context: dict[str, Any] | None) -> str:
    """Extract the partition key for contextual bandits from a routing context."""
    if not context:
        return ""
    key = context.get("bandit_context_key")
    return "" if key is None else str(key)


def _select_via_bandit(
    selector: Bandit,
    candidates: list[str],
    context: dict[str, Any],
) -> tuple[str | None, dict[str, float] | None, float | None]:
    """Invoke the selector and harvest per-arm scores when the selector exposes them.

    Concrete built-ins (``ThompsonBandit``, ``UCB1Bandit``) expose
    ``select_with_metadata`` so the trajectory can record the scoring
    detail. Custom selectors that only implement ``select`` work too —
    we just don't record the scores.
    """
    rich = getattr(selector, "select_with_metadata", None)
    if rich is not None:
        chosen, scores, exploration = rich(candidates, context)
        return chosen, dict(scores) if scores else None, exploration
    return selector.select(candidates, context), None, None


__all__ = ["Atlas", "register_provider", "unregister_provider"]
