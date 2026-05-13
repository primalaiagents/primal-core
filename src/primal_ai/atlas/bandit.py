"""``Bandit`` — multi-armed bandit selection. **Deferred to Phase 1 Session 8.**

The class is declared so the import surface is stable from Session 7 onward.
Every public method raises ``NotImplementedError`` with a clear "Session 8"
message; once Session 8 ships, Atlas's deterministic ``route`` falls back
to ``Bandit.select`` when a bandit is wired up.

Planned Session-8 surface:

  - ``select(candidates, context)``: pick using Thompson sampling / UCB1.
  - ``observe(provider_name, outcome)``: feed back success/failure/cost.
  - ``snapshot() / restore(...)``: persist posteriors via Storage Protocol.
"""

from __future__ import annotations

from typing import Any

from primal_ai.atlas._provider import Provider


class Bandit:
    """Multi-armed bandit over providers. **Implementation deferred to Session 8.**

    Calling any method on this stub raises ``NotImplementedError``. The
    class exists so that downstream code can already import the symbol
    without it changing shape when Session 8 lands.
    """

    def select(
        self,
        candidates: list[Provider],
        context: dict[str, Any] | None = None,
    ) -> Provider:
        """Pick the next provider to try. **Stub — Session 8.**"""
        del candidates, context
        raise NotImplementedError(
            "Atlas bandit ships in Phase 1 Session 8. "
            "Use deterministic routing via Atlas.route(...) until then.",
        )

    def observe(
        self,
        provider_name: str,
        success: bool,
        cost: float | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Feed an outcome back into the bandit's posteriors. **Stub — Session 8.**"""
        del provider_name, success, cost, latency_ms
        raise NotImplementedError("Atlas bandit ships in Phase 1 Session 8.")


__all__ = ["Bandit"]
