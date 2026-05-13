"""``BlockList`` — deny calls matching named tools, domains, or regex patterns."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from primal_ai.guardian._policy import PolicyViolation


class BlockList:
    """Mirror of ``AllowList`` for explicit deny semantics, plus regex patterns.

    Independent dimensions:

    - ``tools``: kwargs whose ``tool=`` value is in ``tools`` are blocked.
    - ``domains``: kwargs whose ``url=`` host (or ``domain=``) is in
      ``domains`` are blocked.
    - ``patterns``: regex strings checked against every positional arg and
      kwarg value (stringified). Any match anywhere is a block.

    Example:
        >>> from primal_ai import BlockList
        >>> BlockList(patterns=[r"evil\\.com", r"DROP\\s+TABLE"])
        <...>
    """

    name = "block_list"

    def __init__(
        self,
        tools: list[str] | None = None,
        domains: list[str] | None = None,
        patterns: list[str] | None = None,
    ) -> None:
        self.tools = tools
        self.domains = domains
        self.patterns = patterns or []
        self._compiled: list[re.Pattern[str]] = [re.compile(p) for p in self.patterns]

    def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        """Raise on any blocked tool, domain, or pattern match."""
        if self.tools is not None:
            tool = kwargs.get("tool")
            if tool is not None and tool in self.tools:
                raise PolicyViolation(
                    policy_name=self.name,
                    reason=f"tool {tool!r} is on the block list",
                    phase="pre",
                    context={"tool": tool},
                )

        if self.domains is not None:
            host = _extract_host(kwargs)
            if host is not None and host in self.domains:
                raise PolicyViolation(
                    policy_name=self.name,
                    reason=f"domain {host!r} is on the block list",
                    phase="pre",
                    context={"domain": host},
                )

        for pattern in self._compiled:
            for arg in args:
                if pattern.search(str(arg)):
                    raise PolicyViolation(
                        policy_name=self.name,
                        reason=f"argument matched block pattern {pattern.pattern!r}",
                        phase="pre",
                        context={"pattern": pattern.pattern},
                    )
            for k, v in kwargs.items():
                if pattern.search(str(v)):
                    raise PolicyViolation(
                        policy_name=self.name,
                        reason=f"kwarg {k!r} matched block pattern {pattern.pattern!r}",
                        phase="pre",
                        context={"pattern": pattern.pattern, "kwarg": k},
                    )


def _extract_host(kwargs: dict[str, Any]) -> str | None:
    raw_url = kwargs.get("url")
    if isinstance(raw_url, str):
        parsed = urlparse(raw_url)
        if parsed.hostname:
            return parsed.hostname
    raw_domain = kwargs.get("domain")
    if isinstance(raw_domain, str):
        return raw_domain
    return None


def factory(arg: str) -> BlockList:
    """DSL factory: ``"block_list:tools=shell|sudo,patterns=evil\\.com"``."""
    from primal_ai.guardian._dsl import parse_kv

    kv = parse_kv(arg)
    return BlockList(
        tools=_split_pipe(kv.get("tools")),
        domains=_split_pipe(kv.get("domains")),
        patterns=_split_pipe(kv.get("patterns")),
    )


def _split_pipe(value: str | None) -> list[str] | None:
    if value is None or value == "":
        return None
    return [v.strip() for v in value.split("|") if v.strip()]


def no_external_network_factory(arg: str) -> BlockList:
    """DSL factory for ``"no_external_network"`` — block any ``http(s)://`` string."""
    del arg  # no args expected
    return BlockList(patterns=[r"https?://"])


__all__ = ["BlockList", "factory", "no_external_network_factory"]
