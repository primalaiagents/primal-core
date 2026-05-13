"""Harness — runtime substrate: health monitoring, tool registry, interval scheduler.

The MVP exposes three independent subsystems behind a shared facade:

  - :class:`HealthMonitor` — pluggable health checks with worst-grade
    aggregation. A raising check becomes ``UNHEALTHY`` automatically.
  - :class:`ToolRegistry` — substring + tag-based tool discovery without
    embeddings. Optional ``Storage`` persistence. Embeddings ship as an
    optional extra (``pip install primal-ai[discovery]``) in Phase 2.
  - :class:`Scheduler` — single-thread, interval-based job runner.
    Exceptions never propagate. Cron syntax + async paths are Phase 2.

All three publish lifecycle events on the shared ``default_bus`` so
external observers see Harness activity from the same subscription that
catches Conductor / Atlas events.

Example:
    >>> from primal_ai import Harness, ToolInfo
    >>> Harness.register_tool(
    ...     ToolInfo(name="search", description="search the web", tags=("web",)),
    ... )
    >>> [t.name for t in Harness.list_tools() if t.name == "search"]
    ['search']
"""

from __future__ import annotations

from primal_ai.harness._core import Harness
from primal_ai.harness.discovery import ToolInfo, ToolRegistry
from primal_ai.harness.health import (
    HealthCheck,
    HealthCheckFn,
    HealthMonitor,
    HealthStatus,
)
from primal_ai.harness.loader import register_tool, unregister_tool
from primal_ai.harness.scheduler import JobStatus, ScheduledJob, Scheduler

__all__ = [
    "Harness",
    "HealthCheck",
    "HealthCheckFn",
    "HealthMonitor",
    "HealthStatus",
    "JobStatus",
    "ScheduledJob",
    "Scheduler",
    "ToolInfo",
    "ToolRegistry",
    "register_tool",
    "unregister_tool",
]
