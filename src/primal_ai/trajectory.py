"""Trajectory — captures every agent action with full causal context.

The "black box recorder" of PRIMAL. Records inputs, outputs, tool calls,
errors, costs, and timing for every agent execution into a JSON-serializable
structure for replay, audit, and post-mortem analysis.
"""

from __future__ import annotations

from typing import Any


class Trajectory:
    """Structured recording of a single agent execution.

    Captures the complete causal chain — inputs, outputs, tool calls,
    retries, costs, errors — into a JSON-serializable structure for
    replay and analysis. Used as a context manager around agent calls.

    Example:
        with Trajectory.record(agent_id="search-1") as tr:
            result = agent.run(query)
            tr.add_step(result)

    NOTE: Stub only. Will be implemented as a full ``@contextmanager`` in
    Phase 2 (extracted from karis_trajectory.py). The current ``record``
    classmethod raises ``NotImplementedError`` so the type signature can
    be exercised without depending on the runtime behavior yet.
    """

    @classmethod
    def record(cls, agent_id: str | None = None) -> Trajectory:
        """Record an agent execution as a context-managed Trajectory. STUB."""
        raise NotImplementedError("Trajectory.record will be implemented in Phase 2")

    def add_step(self, step: Any) -> None:
        """Append a step to this trajectory. STUB."""
        raise NotImplementedError("Trajectory.add_step will be implemented in Phase 2")

    def summary(self) -> dict[str, Any]:
        """Return a summary of this trajectory. STUB."""
        raise NotImplementedError("Trajectory.summary will be implemented in Phase 2")
