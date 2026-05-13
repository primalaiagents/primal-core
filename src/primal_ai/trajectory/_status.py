"""``TrajectoryStatus`` — lifecycle states for a recorded trajectory."""

from __future__ import annotations

from enum import StrEnum


class TrajectoryStatus(StrEnum):
    """Lifecycle status of a recorded ``Trajectory``.

    The enum is ``str``-valued so JSON serialization round-trips through
    ``json.dumps``/``json.loads`` without custom encoders.

    Values:
        RUNNING: The trajectory is open — inside a ``with`` block.
        SUCCESS: The context manager exited without an exception.
        FAILED:  The context manager exited with an exception (an ERROR
            step was also recorded).
        ESCALATED: Set by a downstream handler (e.g. ``Guardian.escalate``)
            when the trajectory was forwarded for human review.
    """

    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


__all__ = ["TrajectoryStatus"]
