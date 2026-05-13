"""``Provider`` Protocol + ``ProviderInfo`` dataclass + ``BYOProvider`` concrete.

Field shapes mirror Conductor's ``AgentCard`` / ``Capability`` so a future
A2A-aware serializer can treat "agents that happen to be models" and
"models that happen to be agents" through the same lens.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ProviderInfo:
    """The discoverable identity of a provider — name, capabilities, hints.

    ``cost_per_call_estimate`` and ``latency_ms_estimate`` are advisory;
    Atlas uses them for ranking once the bandit ships in Session 8. The
    MVP routing layer ignores them but they're already part of the
    serializable shape so providers registered today survive forward.

    Args:
        name: Stable identifier matching ``Provider.name``.
        description: One-line human-readable summary.
        capabilities: Tags for capability-based discovery (e.g.
            ``("chat", "code", "vision")``).
        cost_per_call_estimate: Optional dollar cost per call.
        latency_ms_estimate: Optional p50 latency hint.
        tags: Free-form labels for ``Atlas.find(tag=...)``.
        metadata: Vendor-specific extensions (model id, region, etc.).

    Example:
        >>> from primal_ai import ProviderInfo
        >>> ProviderInfo(
        ...     name="local-llama",
        ...     description="Local 7B model",
        ...     capabilities=("chat", "code"),
        ...     cost_per_call_estimate=0.0,
        ...     latency_ms_estimate=400.0,
        ...     tags=("local", "cheap"),
        ... )
        ProviderInfo(...)
    """

    name: str
    description: str = ""
    capabilities: tuple[str, ...] = ()
    cost_per_call_estimate: float | None = None
    latency_ms_estimate: float | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "cost_per_call_estimate": self.cost_per_call_estimate,
            "latency_ms_estimate": self.latency_ms_estimate,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ProviderInfo:
        """Rebuild a ``ProviderInfo`` from a ``to_dict`` payload."""
        return cls(
            name=str(payload["name"]),
            description=str(payload.get("description") or ""),
            capabilities=tuple(payload.get("capabilities") or ()),
            cost_per_call_estimate=payload.get("cost_per_call_estimate"),
            latency_ms_estimate=payload.get("latency_ms_estimate"),
            tags=tuple(payload.get("tags") or ()),
            metadata=dict(payload.get("metadata") or {}),
        )

    def has_capability(self, name: str) -> bool:
        """True iff this info lists ``name`` in ``capabilities``."""
        return name in self.capabilities

    def has_tag(self, tag: str) -> bool:
        """True iff this info lists ``tag``."""
        return tag in self.tags


@runtime_checkable
class Provider(Protocol):
    """Structural contract for any Atlas-registerable provider.

    Required:
        name (str): Stable identifier; must match ``info.name``.
        info (ProviderInfo): The discoverable description.
        invoke(task, **kwargs) -> Any: Synchronous entry point. May raise —
            Atlas catches and records failure on the provider's health.

    Optional (use ``getattr`` for runtime detection):
        invoke_async(task, **kwargs) -> Awaitable[Any]: Async variant.
            MVP Atlas only uses ``invoke``; async paths are Phase 2.
    """

    name: str
    info: ProviderInfo

    def invoke(self, task: str, **kwargs: Any) -> Any:
        """Synchronous entry point — return the provider's output for ``task``."""
        ...


class BYOProvider:
    """Bring-your-own-provider — wraps a user-supplied callable.

    ``call`` is your wired-up LLM/API/local-model invocation. PRIMAL never
    ships first-party HTTP clients; the BYO pattern is the entire LLM
    surface for this MVP (same boundary Verifier's ``BYOLLMJudge`` set).

    Args:
        name: Unique provider name in the registry.
        call: ``Callable[..., Any]`` invoked as ``call(task, **kwargs)``.
        info: Optional ``ProviderInfo``. Built with defaults if omitted.

    Example:
        >>> from primal_ai import BYOProvider, ProviderInfo
        >>> def my_llm(task, **kwargs):
        ...     # call any model / API / local you like
        ...     return f"result for {task}"
        >>> provider = BYOProvider(
        ...     name="my-llm",
        ...     call=my_llm,
        ...     info=ProviderInfo(name="my-llm", capabilities=("chat",)),
        ... )
    """

    def __init__(
        self,
        name: str,
        call: Callable[..., Any],
        info: ProviderInfo | None = None,
    ) -> None:
        self.name = name
        self.call = call
        self.info = info if info is not None else ProviderInfo(name=name)

    def invoke(self, task: str, **kwargs: Any) -> Any:
        """Forward to the user-supplied callable."""
        return self.call(task, **kwargs)


__all__ = ["BYOProvider", "Provider", "ProviderInfo"]
