"""``DollarCap`` — post-execution cost ceiling per call and/or per hour."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from primal_ai.guardian._policy import PolicyViolation

_logger = logging.getLogger("primal_ai.guardian")


class DollarCap:
    """Block calls whose result reports a cost over the configured threshold.

    The wrapped agent's result must expose its dollar cost via either a
    ``.cost`` attribute or a ``["cost"]`` mapping key. When neither is
    present, ``DollarCap`` logs a single WARNING and continues — it does
    not assume zero-cost or unbounded-cost on missing data.

    Args:
        max_per_call: Maximum cost allowed for any single call (USD).
        max_per_hour: Maximum cumulative cost across a rolling 60-minute window.

    Example:
        >>> from primal_ai import DollarCap, Guardian
        >>> wrapped = Guardian.wrap(agent, policies=[DollarCap(max_per_call=0.10)])
    """

    name = "max_cost"

    def __init__(
        self,
        max_per_call: float | None = None,
        max_per_hour: float | None = None,
    ) -> None:
        self.max_per_call = max_per_call
        self.max_per_hour = max_per_hour
        self._history: deque[tuple[float, float]] = deque()  # (timestamp, cost)
        self._warned_missing_cost = False

    def check_post(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        result: Any,
    ) -> None:
        """Inspect the result's cost field and enforce both caps."""
        del args, kwargs  # unused — cost lives in the result
        cost = self._extract_cost(result)
        if cost is None:
            if not self._warned_missing_cost:
                _logger.warning(
                    "DollarCap: result has no 'cost' attribute/key; policy no-ops for this agent",
                )
                self._warned_missing_cost = True
            return

        if self.max_per_call is not None and cost > self.max_per_call:
            raise PolicyViolation(
                policy_name=self.name,
                reason=f"call cost ${cost:.4f} exceeds per-call cap ${self.max_per_call:.4f}",
                phase="post",
                context={"cost": cost, "max_per_call": self.max_per_call},
            )

        if self.max_per_hour is not None:
            now = time.monotonic()
            cutoff = now - 3600.0
            while self._history and self._history[0][0] < cutoff:
                self._history.popleft()
            running = sum(c for _, c in self._history) + cost
            if running > self.max_per_hour:
                raise PolicyViolation(
                    policy_name=self.name,
                    reason=f"hourly cost ${running:.4f} would exceed cap ${self.max_per_hour:.4f}",
                    phase="post",
                    context={
                        "cost": cost,
                        "hourly_running": running,
                        "max_per_hour": self.max_per_hour,
                    },
                )
            self._history.append((now, cost))
        return

    @staticmethod
    def _extract_cost(result: Any) -> float | None:
        """Pull a cost out of either a dict key or an object attribute."""
        raw = (
            result.get("cost")
            if isinstance(result, dict)
            else getattr(result, "cost", None)
        )
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None


def factory(arg: str) -> DollarCap:
    """DSL factory: ``"max_cost:$0.10/req"`` or ``"max_cost:max_per_call=0.10"``."""
    from primal_ai.guardian._dsl import parse_currency_per_unit, parse_kv

    currency = parse_currency_per_unit(arg)
    if currency is not None:
        amount, unit = currency
        unit_lower = unit.lower()
        if unit_lower in ("req", "request", "call"):
            return DollarCap(max_per_call=amount)
        if unit_lower in ("hr", "hour"):
            return DollarCap(max_per_hour=amount)
        raise ValueError(f"unknown DollarCap unit {unit!r}; expected 'req' or 'hour'")

    kv = parse_kv(arg)
    kwargs: dict[str, float | None] = {}
    for key in ("max_per_call", "max_per_hour"):
        if key in kv and kv[key] != "":
            kwargs[key] = float(kv[key])
    return DollarCap(**kwargs)


__all__ = ["DollarCap", "factory"]
