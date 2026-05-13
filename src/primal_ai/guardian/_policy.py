"""Policy Protocol and ``PolicyViolation`` exception.

These are the two primitives every other Guardian module is built on. A
Policy is anything with a ``name`` plus an optional ``check_pre`` and/or
``check_post`` hook; either hook may raise ``PolicyViolation`` to abort
a wrapped call. ``Guardian`` dispatches via ``getattr`` so a policy is
free to implement just one side.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

Phase = Literal["pre", "post"]


@runtime_checkable
class Policy(Protocol):
    """Runtime-checkable policy contract.

    Structurally, a ``Policy`` is anything with a ``name: str`` attribute.
    The protocol is kept minimal so users can mix-and-match policies that
    implement just one side of the pre/post pipeline.

    A policy may additionally define either or both of:

      ``check_pre(args, kwargs) -> None``
        Runs before the wrapped agent. Raise ``PolicyViolation`` to abort.

      ``check_post(args, kwargs, result) -> Any | None``
        Runs after the wrapped agent. Raise ``PolicyViolation`` to abort.
        Return ``None`` to leave the result unchanged, or return a
        replacement value to substitute (used by transforming policies
        such as ``PIIRedact``).

    ``Guardian`` dispatches both hooks via ``getattr`` and treats missing
    methods as "no-op", so a policy is free to implement neither, one,
    or both. The hooks are intentionally NOT declared on the Protocol so
    that built-in policies (which usually implement only one side) can
    still satisfy ``Policy`` for type-checking purposes.

    Example:
        class MaxLen:
            name = "max_len"

            def check_pre(
                self,
                args: tuple[object, ...],
                kwargs: dict[str, object],
            ) -> None:
                if any(len(str(a)) > 1000 for a in args):
                    raise PolicyViolation(
                        policy_name=self.name,
                        reason="argument too long",
                        phase="pre",
                        context={},
                    )
    """

    name: str


class PolicyViolation(Exception):  # noqa: N818 — public contract name set by the spec
    """Raised by a policy to abort a wrapped call.

    ``PolicyViolation`` is JSON-serializable via :meth:`to_dict` so it can
    be forwarded to escalation handlers, structured logs, or downstream
    Trajectory records without further marshalling.

    Args:
        policy_name: ``Policy.name`` of the policy that fired.
        reason: Human-readable explanation suitable for logs and alerts.
        phase: ``"pre"`` if raised from ``check_pre``, ``"post"`` otherwise.
        context: Arbitrary JSON-friendly metadata (limits, observed values,
            offending tool/url, etc.).
    """

    def __init__(
        self,
        *,
        policy_name: str,
        reason: str,
        phase: Phase,
        context: dict[str, Any],
    ) -> None:
        super().__init__(f"{policy_name}[{phase}]: {reason}")
        self.policy_name = policy_name
        self.reason = reason
        self.phase: Phase = phase
        self.context = context

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of this violation."""
        return {
            "policy_name": self.policy_name,
            "reason": self.reason,
            "phase": self.phase,
            "context": self.context,
        }


__all__ = ["Phase", "Policy", "PolicyViolation"]
