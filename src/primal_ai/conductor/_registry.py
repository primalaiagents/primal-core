"""``AgentRegistry`` — thread-safe name→Agent map with capability + tag indices."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from primal_ai.conductor._card import AgentCard

if TYPE_CHECKING:
    from primal_ai.conductor._agent import Agent


class AgentRegistry:
    """Process-local registry of agents. Threadsafe under a single lock.

    Used internally by ``Conductor``. Exposed methods always operate on
    snapshots (lists, not live references into the internal dict) so
    callers iterating results never see mutations mid-iteration.
    """

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._lock = threading.Lock()

    def register(self, agent: Agent) -> None:
        """Add ``agent`` keyed by ``agent.name``. Raises ``ValueError`` on duplicate."""
        with self._lock:
            if agent.name in self._agents:
                raise ValueError(f"agent {agent.name!r} is already registered")
            self._agents[agent.name] = agent

    def unregister(self, name: str) -> None:
        """Remove the agent named ``name`` if present. No-op otherwise."""
        with self._lock:
            self._agents.pop(name, None)

    def get(self, name: str) -> Agent | None:
        """Return the agent named ``name``, or ``None`` if absent."""
        with self._lock:
            return self._agents.get(name)

    def all(self) -> list[Agent]:
        """Return a snapshot list of every registered agent."""
        with self._lock:
            return list(self._agents.values())

    def cards(self) -> list[AgentCard]:
        """Return every registered agent's card as a snapshot list."""
        with self._lock:
            return [a.card for a in self._agents.values()]

    def find_by_capability(self, capability_name: str) -> list[Agent]:
        """Return every agent whose card advertises ``capability_name``."""
        with self._lock:
            return [a for a in self._agents.values() if a.card.has_capability(capability_name)]

    def find_by_tag(self, tag: str) -> list[Agent]:
        """Return every agent whose card carries ``tag`` on any capability."""
        with self._lock:
            return [a for a in self._agents.values() if a.card.has_tag(tag)]


__all__ = ["AgentRegistry"]
