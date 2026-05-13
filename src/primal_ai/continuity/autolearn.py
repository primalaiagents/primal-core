"""Auto-learn — derive preference updates from observed user behavior.

Watches Trajectories for implicit signals (accept/decline, repeated edits,
time-on-task) and proposes diffs to the user's PUF profile, gated by
explicit consent.
"""

from __future__ import annotations

from typing import Any


class AutoLearn:
    """Behavior-driven preference learner. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def propose(cls, trajectory: Any) -> list[dict[str, Any]]:
        """Propose profile diffs from a trajectory. STUB."""
        raise NotImplementedError("AutoLearn.propose will be implemented in Phase 2")
