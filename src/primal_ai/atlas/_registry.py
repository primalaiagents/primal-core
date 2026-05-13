"""``ProviderRegistry`` — name→Provider map plus per-provider ``ProviderHealth``."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from primal_ai.atlas._health import ProviderHealth

if TYPE_CHECKING:
    from primal_ai.atlas._provider import Provider, ProviderInfo


class ProviderRegistry:
    """Process-local registry of providers + their health state.

    Threadsafe under a single per-registry lock. All accessors return
    snapshot lists, not live references into the internal dict.
    """

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self._health: dict[str, ProviderHealth] = {}
        self._lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────────
    # Mutators
    # ──────────────────────────────────────────────────────────────────

    def register(self, provider: Provider) -> None:
        """Add ``provider`` keyed by ``provider.name``. Raise ``ValueError`` on duplicate."""
        with self._lock:
            if provider.name in self._providers:
                raise ValueError(f"provider {provider.name!r} is already registered")
            self._providers[provider.name] = provider
            self._health[provider.name] = ProviderHealth()

    def unregister(self, name: str) -> None:
        """Remove the provider named ``name`` if present. No-op otherwise."""
        with self._lock:
            self._providers.pop(name, None)
            self._health.pop(name, None)

    # ──────────────────────────────────────────────────────────────────
    # Accessors
    # ──────────────────────────────────────────────────────────────────

    def get(self, name: str) -> Provider | None:
        """Return the provider named ``name``, or ``None`` if absent."""
        with self._lock:
            return self._providers.get(name)

    def get_health(self, name: str) -> ProviderHealth | None:
        """Return the per-provider health record, or ``None`` if the provider is absent."""
        with self._lock:
            return self._health.get(name)

    def all(self) -> list[Provider]:
        """Return a snapshot list of every registered provider."""
        with self._lock:
            return list(self._providers.values())

    def infos(self) -> list[ProviderInfo]:
        """Return every registered provider's info as a snapshot list."""
        with self._lock:
            return [p.info for p in self._providers.values()]

    def find_by_capability(self, capability: str) -> list[Provider]:
        """Return every provider whose info advertises ``capability``."""
        with self._lock:
            return [p for p in self._providers.values() if p.info.has_capability(capability)]

    def find_by_tag(self, tag: str) -> list[Provider]:
        """Return every provider whose info carries ``tag``."""
        with self._lock:
            return [p for p in self._providers.values() if p.info.has_tag(tag)]

    def reset_health(self, name: str | None = None) -> None:
        """Clear cooldown(s). ``None`` clears every provider's health."""
        with self._lock:
            targets = (
                [self._health[name]] if name is not None and name in self._health
                else list(self._health.values())
            )
        for health in targets:
            health.reset()


__all__ = ["ProviderRegistry"]
