"""``AllowList`` — accept only kwargs naming a known tool or domain."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from primal_ai.guardian._policy import PolicyViolation


class AllowList:
    """Whitelist enforcement on the wrapped call's kwargs.

    Two independent dimensions:

    - ``tools``: when the agent is called with a ``tool=`` kwarg, that
      value must appear in ``tools``.
    - ``domains``: when the agent is called with a ``url=`` (or
      ``domain=``) kwarg, the host portion must appear in ``domains``.

    Either dimension is disabled by passing ``None``; an empty list
    means "no value is allowed" (strict deny). With both dimensions
    ``None`` (the default) ``AllowList`` is a no-op — useful as a
    placeholder while a policy set is being assembled.

    Example:
        >>> from primal_ai import AllowList
        >>> AllowList(tools=["search", "calc"], domains=["wikipedia.org"])
        <...>
    """

    name = "allow_list"

    def __init__(
        self,
        tools: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> None:
        self.tools = tools
        self.domains = domains

    def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        """Reject calls whose tool/domain kwarg is not in the configured allow list."""
        del args
        if self.tools is not None:
            tool = kwargs.get("tool")
            if tool is not None and tool not in self.tools:
                raise PolicyViolation(
                    policy_name=self.name,
                    reason=f"tool {tool!r} is not in the allow list",
                    phase="pre",
                    context={"tool": tool, "allowed": list(self.tools)},
                )
        if self.domains is not None:
            host = _extract_host(kwargs)
            if host is not None and host not in self.domains:
                raise PolicyViolation(
                    policy_name=self.name,
                    reason=f"domain {host!r} is not in the allow list",
                    phase="pre",
                    context={"domain": host, "allowed": list(self.domains)},
                )


def _extract_host(kwargs: dict[str, Any]) -> str | None:
    """Resolve a hostname from common kwarg shapes (``url=``, ``domain=``)."""
    raw_url = kwargs.get("url")
    if isinstance(raw_url, str):
        parsed = urlparse(raw_url)
        if parsed.hostname:
            return parsed.hostname
    raw_domain = kwargs.get("domain")
    if isinstance(raw_domain, str):
        return raw_domain
    return None


def factory(arg: str) -> AllowList:
    """DSL factory: ``"allow_list:tools=search|calc"`` (pipe-separated values)."""
    from primal_ai.guardian._dsl import parse_kv

    kv = parse_kv(arg)
    tools = _split_pipe(kv.get("tools"))
    domains = _split_pipe(kv.get("domains"))
    return AllowList(tools=tools, domains=domains)


def _split_pipe(value: str | None) -> list[str] | None:
    if value is None or value == "":
        return None
    return [v.strip() for v in value.split("|") if v.strip()]


__all__ = ["AllowList", "factory"]
