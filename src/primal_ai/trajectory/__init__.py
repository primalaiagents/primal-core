"""Trajectory — structured "black box recorder" for agent executions.

The MVP captures every input, tool call, LLM call, error, and output of
one agent run into a JSON-serializable record. Used as a context manager
around an agent invocation; persists via the ``Storage`` Protocol; pairs
cleanly with Guardian for escalation. Nine canonical step kinds plus an
open extension point for custom strings.

Example:
    >>> from primal_ai import Trajectory
    >>> with Trajectory.record(agent_id="search") as tr:
    ...     tr.record_input({"q": "flights to tokyo"})
    ...     call = tr.record_tool_call("search", {"q": "flights to tokyo"})
    ...     tr.record_tool_result(call.step_id, {"hits": 3}, cost=0.02)
    ...     tr.record_output({"answer": "..."})
    >>> tr.summary()["status"]
    'SUCCESS'
"""

from __future__ import annotations

from primal_ai.trajectory._core import Trajectory, set_default_store
from primal_ai.trajectory._status import TrajectoryStatus
from primal_ai.trajectory._step import Step, StepKind

__all__ = [
    "Step",
    "StepKind",
    "Trajectory",
    "TrajectoryStatus",
    "set_default_store",
]
