"""LLM-judge surface — protocol + BYO concrete (no first-party LLM caller in MVP).

This module defines two things:

  - ``LLMJudge`` — a runtime-checkable Protocol that any user-supplied
    LLM judge satisfies. Use this as a type hint when accepting a
    user's judge.
  - ``BYOLLMJudge`` — a concrete class that takes a user-supplied
    ``call_llm: Callable[[str], str]``. Users wire their own SDK
    (Anthropic, OpenAI, Ollama, local model) above the boundary and
    pass the result here.

The MVP intentionally ships NO first-party HTTP caller. That comes in
Phase 2 as ``Howl``, an optional install (``pip install primal-ai[howl]``)
so the base library stays dependency-free.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from primal_ai.verifier._verdict import Verdict, VerdictStatus

DEFAULT_PROMPT = """\
You are evaluating whether an AI agent's output satisfies its apparent goal.

Output:
{output}

On the very first line of your response, write exactly one of: PASS, FAIL, or UNCERTAIN.
On subsequent lines, write a brief reason. Be terse — one or two sentences is plenty.
"""


@runtime_checkable
class LLMJudge(Protocol):
    """Structural contract for any LLM-based verifier layer.

    Required:
        name (str): Stable identifier surfaced in ``Verdict.verifier_name``.
        verify(target) -> Verdict
    """

    name: str

    def verify(self, target: Any) -> Verdict:
        """Return a ``Verdict`` for ``target``."""
        ...


class BYOLLMJudge:
    """Bring-your-own-LLM verifier layer.

    The MVP boundary: you supply a ``call_llm`` callable that takes a
    prompt string and returns the model's response string. ``BYOLLMJudge``
    formats the prompt, invokes your callable, parses ``PASS`` / ``FAIL``
    / ``UNCERTAIN`` from the first line of the response, and packages
    the rest into a ``Verdict``.

    Args:
        call_llm: ``Callable[[str], str]`` — your wired-up model call.
        prompt_template: Template with a single ``{output}`` slot.
            Defaults to ``DEFAULT_PROMPT``.
        name: Verifier name. Defaults to ``"byo_llm_judge"``.
        per_call_cost: Optional flat dollar cost reported on every
            verdict. Lets ``Verifier.audit`` aggregate cost across layers
            without a per-call billing integration.

    Example:
        >>> def my_llm(prompt: str) -> str:
        ...     # call any model you like; return the string response
        ...     return "PASS\\nlooks correct"
        >>> judge = BYOLLMJudge(call_llm=my_llm)
        >>> judge.verify("the agent answered 42").status.value
        'PASS'
    """

    accepts_trajectory: bool = False

    def __init__(
        self,
        call_llm: Callable[[str], str],
        prompt_template: str = DEFAULT_PROMPT,
        name: str = "byo_llm_judge",
        per_call_cost: float | None = None,
    ) -> None:
        self.call_llm = call_llm
        self.prompt_template = prompt_template
        self.name = name
        self.per_call_cost = per_call_cost

    def verify(self, target: Any) -> Verdict:
        """Format a prompt, call the user's LLM, parse the response into a ``Verdict``."""
        prompt = self.prompt_template.format(output=target)
        started = time.monotonic()
        response = self.call_llm(prompt)
        latency_ms = (time.monotonic() - started) * 1000.0

        status, reason = self._parse_response(response)
        return Verdict(
            verifier_name=self.name,
            status=status,
            confidence=0.8 if status != VerdictStatus.UNCERTAIN else 0.3,
            reasons=[reason],
            details={"response": response, "prompt": prompt},
            cost=self.per_call_cost,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _parse_response(response: str) -> tuple[VerdictStatus, str]:
        """Parse PASS/FAIL/UNCERTAIN from the first line; everything else is the reason."""
        stripped = response.strip()
        if not stripped:
            return VerdictStatus.UNCERTAIN, "empty LLM response"
        first, _, rest = stripped.partition("\n")
        token = first.strip().upper()
        # Look for one of the three valid status words at the very start.
        for candidate in (VerdictStatus.PASS, VerdictStatus.FAIL, VerdictStatus.UNCERTAIN):
            if token == candidate.value or token.startswith(candidate.value + " "):
                reason = rest.strip() or token.lower()
                return candidate, reason
        return VerdictStatus.UNCERTAIN, f"unparseable LLM response: {first[:80]}"


__all__ = ["BYOLLMJudge", "DEFAULT_PROMPT", "LLMJudge"]
