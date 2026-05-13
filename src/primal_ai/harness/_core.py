"""Harness facade — start / stop, plus module-level singletons for health, tools, scheduler.

``Harness.start`` is intentionally lazy: with an empty config it does
nothing. Subsystems opt in via flags (``scheduler_enabled``, etc.) so the
package can be imported in environments that don't want a background
thread.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from primal_ai.harness.discovery import ToolInfo, ToolRegistry
from primal_ai.harness.health import HealthCheck, HealthMonitor
from primal_ai.harness.scheduler import Scheduler

if TYPE_CHECKING:
    from primal_ai.storage import Storage

# Module-level singletons. Subsystems are independent — Harness.health
# can be used without ever touching the scheduler, and vice versa.
_HEALTH = HealthMonitor()
_TOOLS = ToolRegistry()
_SCHEDULER = Scheduler()


class Harness:
    """Runtime substrate — health checks, tool registry, scheduler.

    All three subsystems are independent singletons; ``Harness.start`` is
    a tiny config router that activates background work only when asked.
    The default behavior (``Harness.start()`` or ``Harness.start({})``)
    is no-op so importing the package is always free.

    Example:
        >>> from primal_ai import Harness, ToolInfo
        >>> Harness.register_tool(
        ...     ToolInfo(name="search", description="search the web", tags=("web",)),
        ... )
        >>> any(t.name == "search" for t in Harness.list_tools())
        True
        >>> Harness.start(config={"scheduler_enabled": True})
        >>> Harness.stop()
    """

    health: HealthMonitor = _HEALTH
    tools: ToolRegistry = _TOOLS
    scheduler: Scheduler = _SCHEDULER

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def start(cls, config: dict[str, Any] | None = None) -> None:
        """Start opted-in subsystems.

        Honored config keys:
            ``scheduler_enabled`` (bool, default False): start the
                interval scheduler thread.
        """
        cfg = config or {}
        if cfg.get("scheduler_enabled"):
            _SCHEDULER.start()

    @classmethod
    def stop(cls) -> None:
        """Stop every running subsystem. Idempotent."""
        _SCHEDULER.stop()

    # ──────────────────────────────────────────────────────────────────
    # Tools surface (convenience forwarders)
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def register_tool(cls, tool: ToolInfo, *, store: Storage | None = None) -> None:
        """Add ``tool`` to the module-level registry. Raises ``ValueError`` on duplicate."""
        _TOOLS.register(tool, store=store)

    @classmethod
    def unregister_tool(cls, name: str, *, store: Storage | None = None) -> None:
        """Remove the tool named ``name`` from the registry. No-op if absent."""
        _TOOLS.unregister(name, store=store)

    @classmethod
    def list_tools(cls) -> list[ToolInfo]:
        """Return every registered ``ToolInfo`` as a snapshot list."""
        return _TOOLS.list_all()

    # ──────────────────────────────────────────────────────────────────
    # Health surface
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def run_health(cls) -> dict[str, HealthCheck]:
        """Run every registered health check and return their verdicts."""
        return _HEALTH.run_all()


__all__ = ["Harness"]
