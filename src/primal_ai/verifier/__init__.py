"""Verifier — multi-layer audit framework for agent outputs and trajectories.

The MVP exposes a three-layer architecture:

  1. **Rule-based** (cheap, deterministic): callable rules over either
     the raw output or a full ``Trajectory``.
  2. **LLM-judge** (user-supplied model): bring your own LLM via
     ``BYOLLMJudge``; no first-party HTTP caller in this version, to
     keep the runtime dependency-free.
  3. **Domain-specific**: ``JSONSchemaVerifier`` and ``RegexMatchVerifier``
     ship in MVP; users plug their own under the ``DomainVerifier``
     Protocol.

``Verifier.audit(target, layers=...)`` composes any number of layers and
returns a single overall verdict per the documented aggregation rule
(any FAIL → FAIL, all PASS → PASS, otherwise UNCERTAIN). ``target`` may
be a raw output value or a ``Trajectory`` — duck-typed via
``hasattr(target, "replay")``.

Example:
    >>> from primal_ai import (
    ...     Verifier, RuleBasedVerifier, JSONSchemaVerifier,
    ... )
    >>> def has_answer(out):
    ...     return ("pass", "ok") if "answer" in out else ("fail", "no answer")
    >>> verdict = Verifier.audit(
    ...     {"answer": "tokyo"},
    ...     layers=[
    ...         RuleBasedVerifier(rules=[has_answer]),
    ...         JSONSchemaVerifier(schema={"type": "object", "required": ["answer"]}),
    ...     ],
    ... )
    >>> verdict["status"]
    'PASS'
"""

from __future__ import annotations

from primal_ai.verifier._core import (
    Verifier,
    register_verifier,
    registered_names,
    resolve_layer,
)
from primal_ai.verifier._protocol import VerifierLayer
from primal_ai.verifier._verdict import Verdict, VerdictStatus
from primal_ai.verifier.domain import (
    DomainVerifier,
    JSONSchemaVerifier,
    RegexMatchVerifier,
)
from primal_ai.verifier.llm_judge import DEFAULT_PROMPT, BYOLLMJudge, LLMJudge
from primal_ai.verifier.rule_based import Rule, RuleBasedVerifier

# Pre-register a small set of zero-arg factories so the registry isn't
# empty out of the box. None of these is "useful" without configuration;
# they exist to make the DSL surface discoverable and to back the
# unknown-name error message with a non-empty registered list.
register_verifier("rule_based", lambda: RuleBasedVerifier(rules=[]))
register_verifier("json_schema", lambda: JSONSchemaVerifier(schema={}))
register_verifier("regex_match", lambda: RegexMatchVerifier())

__all__ = [
    "BYOLLMJudge",
    "DEFAULT_PROMPT",
    "DomainVerifier",
    "JSONSchemaVerifier",
    "LLMJudge",
    "RegexMatchVerifier",
    "Rule",
    "RuleBasedVerifier",
    "Verdict",
    "VerdictStatus",
    "Verifier",
    "VerifierLayer",
    "register_verifier",
    "registered_names",
    "resolve_layer",
]
