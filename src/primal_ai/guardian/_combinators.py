"""Boolean combinators over policies.

``AllOf`` and ``AnyOf`` are themselves ``Policy`` instances, so they
nest freely — ``AllOf(p, AnyOf(q, r))`` is a valid policy that means
"p must pass AND at least one of (q, r) must pass".
"""

from __future__ import annotations

from typing import Any

from primal_ai.guardian._policy import Policy, PolicyViolation


class AllOf:
    """All sub-policies must pass. Short-circuits on the first violation.

    For post-hooks, the result is threaded through each sub-policy in
    order; if a sub-policy returns a replacement, subsequent sub-policies
    see (and may further transform) that replacement.

    Example:
        >>> from primal_ai import AllOf, BlockList, RateLimit
        >>> gate = AllOf(RateLimit(per_minute=60), BlockList(patterns=[r"evil"]))
    """

    name = "all_of"

    def __init__(self, *policies: Policy) -> None:
        self.policies: tuple[Policy, ...] = policies

    def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        """Run each sub-policy's pre-hook in order; propagate the first violation."""
        for p in self.policies:
            hook = getattr(p, "check_pre", None)
            if hook is not None:
                hook(args, kwargs)

    def check_post(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        result: Any,
    ) -> Any:
        """Run each sub-policy's post-hook, threading any replacement result."""
        current = result
        replaced = False
        for p in self.policies:
            hook = getattr(p, "check_post", None)
            if hook is None:
                continue
            replacement = hook(args, kwargs, current)
            if replacement is not None:
                current = replacement
                replaced = True
        return current if replaced else None


class AnyOf:
    """At least one sub-policy must pass. Short-circuits on the first success.

    If a sub-policy raises ``PolicyViolation``, ``AnyOf`` tries the next
    one. Only if every sub-policy raises does ``AnyOf`` re-raise the
    final violation. A sub-policy that simply doesn't implement the
    current hook counts as a vacuous pass.

    Example:
        >>> from primal_ai import AllowList, AnyOf
        >>> # Internal tools list OR an externally-vetted allowlist:
        >>> gate = AnyOf(AllowList(tools=["search"]), AllowList(tools=["calc"]))
    """

    name = "any_of"

    def __init__(self, *policies: Policy) -> None:
        self.policies: tuple[Policy, ...] = policies

    def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        """Pass as soon as any sub-policy's pre-hook accepts."""
        last: PolicyViolation | None = None
        for p in self.policies:
            hook = getattr(p, "check_pre", None)
            if hook is None:
                return  # Vacuous pass — this sub-policy doesn't constrain pre.
            try:
                hook(args, kwargs)
                return
            except PolicyViolation as v:
                last = v
        if last is not None:
            raise last

    def check_post(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        result: Any,
    ) -> Any:
        """Pass as soon as any sub-policy's post-hook accepts. Returns the accepting policy's
        replacement (or ``None``)."""
        last: PolicyViolation | None = None
        for p in self.policies:
            hook = getattr(p, "check_post", None)
            if hook is None:
                return None  # Vacuous pass.
            try:
                replacement = hook(args, kwargs, result)
            except PolicyViolation as v:
                last = v
                continue
            return replacement
        if last is not None:
            raise last
        return None


__all__ = ["AllOf", "AnyOf"]
