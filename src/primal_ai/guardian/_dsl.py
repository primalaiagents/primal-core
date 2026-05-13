"""String DSL for declaring policies as compact strings.

A policy spec is one of:

  - ``"name"``               — no-arg policy (e.g. ``"no_external_network"``)
  - ``"name:arg"``           — single positional arg
  - ``"name:k1=v1,k2=v2"``   — kwargs form
  - ``"max_cost:$0.10/req"`` — currency-per-unit shorthand (built-in for ``DollarCap``)

Factories live in a small registry; each built-in registers itself when
``primal_ai.guardian`` is imported. Unknown names raise ``ValueError``
that lists every registered policy by name.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from primal_ai.guardian._policy import Policy

PolicyFactory = Callable[[str], Policy]

_REGISTRY: dict[str, PolicyFactory] = {}

_CURRENCY_PER_UNIT = re.compile(r"^\$(\d+(?:\.\d+)?)\s*/\s*(\w+)$")


def register_policy(name: str, factory: PolicyFactory) -> None:
    """Register a DSL name → factory mapping.

    ``factory(arg_str)`` is called with the substring after the first
    ``:`` (or an empty string when the spec has none). The factory
    returns the constructed ``Policy``.
    """
    _REGISTRY[name] = factory


def registered_names() -> list[str]:
    """Return the sorted list of currently-registered DSL names."""
    return sorted(_REGISTRY)


def parse_policy(spec: str) -> Policy:
    """Parse a single DSL spec into a ``Policy`` instance.

    Raises:
        ValueError: If ``spec`` names a policy that isn't registered.
            The error message lists every registered name to help the
            caller correct the typo.
    """
    name, _, arg = spec.partition(":")
    name = name.strip()
    factory = _REGISTRY.get(name)
    if factory is None:
        raise ValueError(
            f"unknown policy {name!r}; registered policies: {registered_names()}"
        )
    return factory(arg.strip())


def parse_kv(arg: str) -> dict[str, str]:
    """Parse ``"k1=v1,k2=v2"`` into a ``dict[str, str]``. Empty arg → empty dict."""
    out: dict[str, str] = {}
    if not arg:
        return out
    for part in arg.split(","):
        token = part.strip()
        if not token:
            continue
        key, sep, value = token.partition("=")
        if not sep:
            # Bare token — store under its own name with empty value.
            out[key.strip()] = ""
        else:
            out[key.strip()] = value.strip()
    return out


def parse_currency_per_unit(arg: str) -> tuple[float, str] | None:
    """Parse ``"$0.10/req"`` → ``(0.10, "req")``. ``None`` if not a currency form."""
    m = _CURRENCY_PER_UNIT.match(arg.strip())
    if m is None:
        return None
    return float(m.group(1)), m.group(2)


__all__ = [
    "PolicyFactory",
    "parse_currency_per_unit",
    "parse_kv",
    "parse_policy",
    "register_policy",
    "registered_names",
]
