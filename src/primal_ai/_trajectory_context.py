"""Shared ``ContextVar`` for the currently-active ``Trajectory``.

Lives at the package root so neither ``trajectory`` nor ``conductor``
imports from the other. Trajectory's ``__enter__``/``__exit__`` set and
clear this variable; Conductor reads it from ``delegate`` to record an
``AGENT_HANDOFF`` step into whatever trajectory is currently open in
this context (thread or async task).

The contract is intentionally tiny:

  - ``current_trajectory.get()`` returns the open trajectory or ``None``.
  - ``current_trajectory.set(tr)`` opens scope (returns a Token).
  - ``current_trajectory.reset(token)`` closes scope.

Anything beyond that — explicit scope context managers, multi-trajectory
stacking — is layered on top by the calling module.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Importing ``Trajectory`` here would create a real cycle at runtime;
    # the TYPE_CHECKING guard keeps it static-analysis-only.
    from primal_ai.trajectory._core import Trajectory  # noqa: F401

# ``Any`` widens the type for runtime use — the ContextVar carries either
# ``None`` or a ``Trajectory``, and we keep things loose so a future test
# double or mock can be slotted in without a wrapper.
current_trajectory: ContextVar[Any] = ContextVar(
    "primal_ai_current_trajectory",
    default=None,
)


__all__ = ["current_trajectory"]
