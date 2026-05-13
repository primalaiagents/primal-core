"""``ToolInfo`` + ``ToolRegistry`` — substring/tag-based tool discovery (no embeddings).

This is the **post-ChromaDB rewrite** of KARIS's Tool RAG. The MVP keeps
selection to substring + tag matching so the runtime stays dependency-free;
embedding-driven semantic search ships in Phase 2 behind an optional
install (``pip install primal-ai[discovery]``).

Field shapes mirror Conductor's ``AgentCard`` and Atlas's ``ProviderInfo``
so all three pillars expose the same discoverable surface.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from primal_ai._events import Event, EventKind, default_bus

if TYPE_CHECKING:
    from primal_ai.storage import Storage

_TOOL_KEY_PREFIX = "harness:tool:"


@dataclass(frozen=True)
class ToolInfo:
    """The discoverable identity of one tool.

    ``handler`` is the actual callable that executes the tool. It is
    deliberately omitted from ``to_dict`` — callables don't survive
    JSON. After ``load_from_store``, ``handler`` is ``None`` and the
    caller is responsible for re-binding implementations.

    Args:
        name: Stable identifier; unique within a registry.
        description: One-line human-readable summary (used by
            ``ToolRegistry.find(text_match=...)``).
        tags: Free-form labels for ``ToolRegistry.find(tag=...)``.
        metadata: Vendor-specific extensions (cost hints, MCP server URI,
            etc.). Must be JSON-serializable.
        handler: The implementation callable. ``None`` for remote /
            lazily-bound tools.

    Example:
        >>> from primal_ai import ToolInfo
        >>> ToolInfo(
        ...     name="search",
        ...     description="search the web",
        ...     tags=("web", "research"),
        ...     metadata={"v": 1},
        ...     handler=lambda q: [f"hit:{q}"],
        ... )
        ToolInfo(...)
    """

    name: str
    description: str = ""
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    handler: Callable[..., Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view. The ``handler`` is intentionally omitted."""
        return {
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ToolInfo:
        """Rebuild a ``ToolInfo`` from a ``to_dict`` payload. ``handler`` is ``None``."""
        return cls(
            name=str(payload["name"]),
            description=str(payload.get("description") or ""),
            tags=tuple(payload.get("tags") or ()),
            metadata=dict(payload.get("metadata") or {}),
            handler=None,
        )


class ToolRegistry:
    """Process-local registry of tools with optional Storage persistence.

    Threadsafe under one lock. All accessors return snapshot lists, never
    live references into the internal dict.

    Example:
        >>> from primal_ai import ToolInfo
        >>> from primal_ai.harness import ToolRegistry
        >>> from primal_ai.storage import InMemoryStorage
        >>> store = InMemoryStorage()
        >>> reg = ToolRegistry()
        >>> reg.register(
        ...     ToolInfo(name="search", description="search the web", tags=("web",)),
        ...     store=store,
        ... )
        >>> reg.find(tag="web")[0].name
        'search'
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolInfo] = {}
        self._lock = threading.Lock()

    # ── Mutators ───────────────────────────────────────────────────────

    def register(self, tool: ToolInfo, *, store: Storage | None = None) -> None:
        """Add ``tool`` to the registry; optionally persist via ``store``.

        Raises ``ValueError`` if the name is already registered.
        """
        with self._lock:
            if tool.name in self._tools:
                raise ValueError(f"tool {tool.name!r} is already registered")
            self._tools[tool.name] = tool
        if store is not None:
            store.put(f"{_TOOL_KEY_PREFIX}{tool.name}", tool.to_dict())
        default_bus.publish(
            Event(
                kind=EventKind.TOOL_REGISTERED.value,
                payload={"tool": tool.name},
            ),
        )

    def unregister(self, name: str, *, store: Storage | None = None) -> None:
        """Remove the tool named ``name`` if present. No-op otherwise."""
        with self._lock:
            had = self._tools.pop(name, None)
        if store is not None:
            store.delete(f"{_TOOL_KEY_PREFIX}{name}")
        if had is not None:
            default_bus.publish(
                Event(
                    kind=EventKind.TOOL_UNREGISTERED.value,
                    payload={"tool": name},
                ),
            )

    # ── Accessors ──────────────────────────────────────────────────────

    def get(self, name: str) -> ToolInfo | None:
        """Return the tool named ``name``, or ``None`` if absent."""
        with self._lock:
            return self._tools.get(name)

    def list_all(self) -> list[ToolInfo]:
        """Return a snapshot list of every registered tool."""
        with self._lock:
            return list(self._tools.values())

    def find(
        self,
        tag: str | None = None,
        text_match: str | None = None,
    ) -> list[ToolInfo]:
        """Filter tools by tag and/or substring across name + description.

        Both filters AND together when supplied. Case-insensitive substring
        match on ``text_match``.
        """
        needle = text_match.lower() if text_match else None
        with self._lock:
            tools = list(self._tools.values())
        out: list[ToolInfo] = []
        for tool in tools:
            if tag is not None and tag not in tool.tags:
                continue
            if needle is not None and needle not in (
                tool.name.lower() + " " + tool.description.lower()
            ):
                continue
            out.append(tool)
        return out

    # ── Persistence ────────────────────────────────────────────────────

    def load_from_store(self, store: Storage) -> int:
        """Rebuild the registry from any ``harness:tool:*`` key in ``store``.

        Returns the count of tools loaded. Existing in-memory entries are
        overwritten when a stored entry shares the same name. Handlers are
        always ``None`` after load — the caller re-binds them as needed.

        Uses ``store.list_keys`` when available; falls back to no-op
        otherwise. (``InMemoryStorage`` doesn't expose ``list_keys``;
        ``SQLiteStorage`` does.)
        """
        list_keys = getattr(store, "list_keys", None)
        if list_keys is None:
            return 0
        keys = list_keys(_TOOL_KEY_PREFIX)
        loaded = 0
        for key in keys:
            payload = store.get(key)
            if payload is None:
                continue
            info = ToolInfo.from_dict(payload)
            with self._lock:
                self._tools[info.name] = info
            loaded += 1
        return loaded


__all__ = ["ToolInfo", "ToolRegistry"]
