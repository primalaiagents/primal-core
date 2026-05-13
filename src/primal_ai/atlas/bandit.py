"""Multi-armed bandit — explore/exploit across providers.

Tracks reward signals per provider (success rate, latency, cost) and
balances exploration of new options against exploitation of known winners.
Default algorithm will be Thompson sampling with Beta priors.
"""

from __future__ import annotations

from typing import Any


class Bandit:
    """Multi-armed bandit over providers. STUB.

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def pick(cls, arms: list[str]) -> str:
        """Pick the next arm to pull. STUB."""
        raise NotImplementedError("Bandit.pick will be implemented in Phase 2")

    @classmethod
    def update(cls, arm: str, reward: float, context: dict[str, Any] | None = None) -> None:
        """Update an arm's posterior with an observed reward. STUB."""
        raise NotImplementedError("Bandit.update will be implemented in Phase 2")
