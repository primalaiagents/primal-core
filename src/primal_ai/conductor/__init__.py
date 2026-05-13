"""Conductor — agent registry, capability-based delegation, linear pipelines.

The orchestration pillar. Composes any number of agents (anything that
satisfies the ``Agent`` Protocol) and routes tasks between them. The
``AgentCard`` shape is the **PRIMAL precursor to A2A v1.0 AgentCard** —
field names are chosen so a future serializer can map 1:1 to the wire
format without renames. A2A protocol implementation itself is deferred
to Phase 2.5; this module is the surface it plugs into.

When a delegation happens inside a ``Trajectory.record()`` block, the
Conductor automatically records an ``AGENT_HANDOFF`` step into the open
trajectory via a shared ``ContextVar`` — no manual wiring required.

Example:
    >>> from primal_ai import (
    ...     AgentCard, Capability, Conductor, Pipeline, PipelineStep,
    ... )
    >>> class Echo:
    ...     name = "echo"
    ...     card = AgentCard(
    ...         name="echo",
    ...         description="Echoes its input",
    ...         capabilities=(Capability(name="echo", description="..."),),
    ...     )
    ...     def invoke(self, input):
    ...         return {"echoed": input}
    >>> Conductor.register_agent(Echo())
    >>> result = Conductor.delegate("say hi", capability="echo", input="hi")
    >>> result.status.value
    'SUCCESS'
"""

from __future__ import annotations

from primal_ai.conductor._agent import Agent
from primal_ai.conductor._card import AgentCard, Capability
from primal_ai.conductor._core import Conductor, register_agent, unregister_agent
from primal_ai.conductor._delegation import DelegationResult, DelegationStatus
from primal_ai.conductor._events import Event, EventBus, EventKind
from primal_ai.conductor._pipeline import Pipeline, PipelineStep

__all__ = [
    "Agent",
    "AgentCard",
    "Capability",
    "Conductor",
    "DelegationResult",
    "DelegationStatus",
    "Event",
    "EventBus",
    "EventKind",
    "Pipeline",
    "PipelineStep",
    "register_agent",
    "unregister_agent",
]
