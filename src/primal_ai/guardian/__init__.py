"""Guardian — runtime policy enforcement for any agent callable.

The MVP wraps a callable with declarative ``Policy`` objects (or DSL
strings) that run before and after every invocation. Ships with six
built-in policies (rate limit, dollar cap, allow/block list, schema
validator, PII redactor), boolean combinators (``AllOf``, ``AnyOf``),
a small string DSL, a dry-run recording mode, and a pluggable
escalation handler. Sync and async agents are both supported — ``wrap``
auto-detects coroutine functions and returns an awaitable wrapper.

Example:
    >>> from primal_ai import Guardian, RateLimit, DollarCap
    >>> def agent(q: str) -> dict[str, float]:
    ...     return {"cost": 0.02, "answer": "..."}
    >>> wrapped = Guardian.wrap(
    ...     agent,
    ...     policies=[RateLimit(per_minute=60), DollarCap(max_per_call=0.10)],
    ... )
    >>> wrapped("flights to tokyo")
    {'cost': 0.02, 'answer': '...'}
"""

from __future__ import annotations

# Import builtins first so they self-register with the DSL parser before
# any user code calls ``parse_policy``.
from primal_ai.guardian._builtins import (
    AllowList,
    BlockList,
    DollarCap,
    PIIRedact,
    RateLimit,
    SchemaValidator,
)
from primal_ai.guardian._combinators import AllOf, AnyOf
from primal_ai.guardian._core import Guardian
from primal_ai.guardian._dsl import parse_policy, register_policy, registered_names
from primal_ai.guardian._policy import Policy, PolicyViolation

__all__ = [
    "AllOf",
    "AllowList",
    "AnyOf",
    "BlockList",
    "DollarCap",
    "Guardian",
    "PIIRedact",
    "Policy",
    "PolicyViolation",
    "RateLimit",
    "SchemaValidator",
    "parse_policy",
    "register_policy",
    "registered_names",
]
