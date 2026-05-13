"""Atlas — smart-routing layer across providers (models, APIs, local agents).

The MVP (Session 7) covers provider registration, capability / tag-based
discovery, deterministic health-aware routing, and an exponential-backoff
cascade. The bandit / cost-aware ranking layer arrives in Session 8 — the
:class:`primal_ai.atlas.bandit.Bandit` stub is in place so its eventual
behavior plugs in behind the existing public surface.

Atlas reuses Conductor's shared :class:`~primal_ai._events.EventBus`
(``Atlas.event_bus is Conductor.event_bus``) so a single subscription sees
events from every pillar. It also reads the same trajectory ``ContextVar``
that Conductor uses, recording a ``ROUTING_DECISION`` step into the open
``Trajectory`` for every call.

Example:
    >>> from primal_ai import Atlas, BYOProvider, ProviderInfo
    >>> Atlas.register_provider(
    ...     BYOProvider(
    ...         name="echo",
    ...         call=lambda task, **kw: f"echoed: {task}",
    ...         info=ProviderInfo(name="echo", capabilities=("chat",)),
    ...     ),
    ... )
    >>> name, result = Atlas.invoke("hi")
    >>> name, result
    ('echo', 'echoed: hi')
"""

from __future__ import annotations

from primal_ai.atlas._decision import RoutingDecision, RoutingStatus
from primal_ai.atlas._health import ProviderHealth
from primal_ai.atlas._provider import BYOProvider, Provider, ProviderInfo
from primal_ai.atlas.cascade import Cascade, CascadeResult
from primal_ai.atlas.router import Atlas, register_provider, unregister_provider

__all__ = [
    "Atlas",
    "BYOProvider",
    "Cascade",
    "CascadeResult",
    "Provider",
    "ProviderHealth",
    "ProviderInfo",
    "RoutingDecision",
    "RoutingStatus",
    "register_provider",
    "unregister_provider",
]
