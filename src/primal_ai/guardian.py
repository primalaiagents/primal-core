"""Guardian — validates every agent action before and after execution.

The first layer of PRIMAL's reliability stack. Wraps any agent with policy
enforcement, pre/post-execution validation, and dangerous-action detection.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Guardian:
    """Policy-enforced agent wrapper.

    Wraps any agent callable with before/after hooks, schema validation,
    and built-in policy library (rate limits, dollar caps, PII redaction).

    Example:
        agent = Guardian.wrap(my_agent, policies=["no_external_network"])

    NOTE: Stub only. Full implementation extracted from karis_guardian.py in Phase 2.
    """

    @classmethod
    def wrap(
        cls,
        agent: Callable[..., Any],
        policies: list[str] | None = None,
    ) -> Callable[..., Any]:
        """Wrap an agent with Guardian policies. STUB."""
        raise NotImplementedError("Guardian.wrap will be implemented in Phase 2")

    @classmethod
    def escalate(cls, trajectory: Any) -> None:
        """Escalate a failed trajectory. STUB."""
        raise NotImplementedError("Guardian.escalate will be implemented in Phase 2")
