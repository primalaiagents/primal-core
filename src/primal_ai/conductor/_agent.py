"""``Agent`` Protocol — the structural contract every Conductor-registered agent satisfies."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from primal_ai.conductor._card import AgentCard


@runtime_checkable
class Agent(Protocol):
    """Structural contract for any agent the Conductor can delegate to.

    Required:
        name (str): Stable identifier; must match ``card.name``.
        card (AgentCard): The discoverable description of this agent.
        invoke(input) -> Any: Synchronous entry point. Receives the
            delegation input, returns the result. May raise — the
            Conductor catches and converts to a FAILED ``DelegationResult``.

    Optional (use ``getattr`` for runtime detection):
        invoke_async(input) -> Awaitable[Any]: Async variant. The MVP
            Conductor only uses ``invoke``; an async delegation path is
            documented as Phase 2 work in CONDUCTOR_ROADMAP.

    Example:
        class EchoAgent:
            name = "echo"
            card = AgentCard(
                name="echo",
                description="Echoes its input",
                capabilities=(Capability(name="echo", description="..."),),
            )

            def invoke(self, input):
                return {"echoed": input}
    """

    name: str
    card: AgentCard

    def invoke(self, input: Any) -> Any:
        """Synchronous entry point — return the delegation output."""
        ...


__all__ = ["Agent"]
