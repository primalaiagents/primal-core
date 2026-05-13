"""``PIIRedact`` — strip emails, phones, and SSNs (or configured fields) from results."""

from __future__ import annotations

import re
from typing import Any

# Default regex set — intentionally conservative. Callers needing
# locale-specific phone formats should pass their own patterns.
_DEFAULT_PATTERNS: list[str] = [
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",      # email
    r"\b\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b",              # US phone
    r"\b\d{3}-\d{2}-\d{4}\b",                                  # US SSN
]

REDACTED = "[REDACTED]"


class PIIRedact:
    """Post-execution scrubber for emails, phones, SSNs, or configured fields.

    Two dimensions, applied to the wrapped agent's result:

    - ``fields``: dict keys (recursive into nested dicts) whose values
      are replaced with ``[REDACTED]``.
    - ``patterns``: regex strings applied to every string anywhere in
      the result tree. Defaults to email + US phone + US SSN.

    String results are immutable, so the redacted copy is returned and
    Guardian substitutes it into the call's return value. Dict and list
    results are mutated in place; the same (now-redacted) reference is
    handed back.

    Example:
        >>> from primal_ai import PIIRedact
        >>> PIIRedact(fields=["ssn", "credit_card"])
        <...>
    """

    name = "pii_redact"

    def __init__(
        self,
        fields: list[str] | None = None,
        patterns: list[str] | None = None,
    ) -> None:
        self.fields = list(fields) if fields else []
        self.patterns = list(patterns) if patterns is not None else list(_DEFAULT_PATTERNS)
        self._compiled = [re.compile(p) for p in self.patterns]

    def check_post(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        result: Any,
    ) -> Any:
        """Return the redacted result. Strings are replaced; dicts/lists mutate in place."""
        del args, kwargs
        return self._redact(result)

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._redact_string(value)
        if isinstance(value, dict):
            for key in list(value.keys()):
                if key in self.fields:
                    value[key] = REDACTED
                else:
                    value[key] = self._redact(value[key])
            return value
        if isinstance(value, list):
            for i, item in enumerate(value):
                value[i] = self._redact(item)
            return value
        return value

    def _redact_string(self, value: str) -> str:
        for pattern in self._compiled:
            value = pattern.sub(REDACTED, value)
        return value


def factory(arg: str) -> PIIRedact:
    """DSL factory: ``"pii_redact:fields=ssn|credit_card"``."""
    from primal_ai.guardian._dsl import parse_kv

    kv = parse_kv(arg)
    fields_raw = kv.get("fields", "")
    fields = [f.strip() for f in fields_raw.split("|") if f.strip()] if fields_raw else None
    return PIIRedact(fields=fields)


__all__ = ["PIIRedact", "factory"]
