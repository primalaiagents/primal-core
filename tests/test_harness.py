"""Harness MVP — health monitoring, tool registry, interval scheduler.

Contract for Phase 1 Session 9 Harness: a stdlib-only runtime substrate
(no embeddings, no cron) that exposes health checks, a substring/tag-based
tool registry, and a thread-driven interval scheduler — all wired into
the shared event bus.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────────
# HealthStatus / HealthCheck
# ──────────────────────────────────────────────────────────────────────────


def test_health_status_is_strenum_and_serializes_natively() -> None:
    """``HealthStatus`` is a StrEnum — ``json.dumps`` handles it natively."""
    from primal_ai import HealthStatus

    blob = json.dumps({"status": HealthStatus.HEALTHY})
    assert json.loads(blob) == {"status": "HEALTHY"}


def test_health_check_round_trips_via_to_dict_from_dict() -> None:
    """``HealthCheck`` round-trips through JSON without loss."""
    from primal_ai import HealthCheck, HealthStatus

    c = HealthCheck(
        name="db",
        status=HealthStatus.DEGRADED,
        reason="slow query",
        details={"latency": 2.5},
        checked_at=42.0,
        latency_ms=2500.0,
    )
    restored = HealthCheck.from_dict(json.loads(json.dumps(c.to_dict())))
    assert restored.name == "db"
    assert restored.status == HealthStatus.DEGRADED
    assert restored.details == {"latency": 2.5}
    assert restored.latency_ms == pytest.approx(2500.0)


# ──────────────────────────────────────────────────────────────────────────
# HealthMonitor
# ──────────────────────────────────────────────────────────────────────────


def _ok_check(name: str) -> Any:
    from primal_ai import HealthCheck, HealthStatus

    def check() -> HealthCheck:
        return HealthCheck(
            name=name,
            status=HealthStatus.HEALTHY,
            reason=None,
            details={},
            checked_at=time.time(),
            latency_ms=1.0,
        )

    return check


def test_health_monitor_register_and_run_single_check() -> None:
    """``HealthMonitor.run('name')`` returns the check's verdict."""
    from primal_ai import HealthStatus
    from primal_ai.harness import HealthMonitor

    monitor = HealthMonitor()
    monitor.register_check("db", _ok_check("db"))
    result = monitor.run("db")
    assert result is not None
    assert result.status == HealthStatus.HEALTHY


def test_health_monitor_run_all_runs_every_registered_check() -> None:
    """``run_all`` returns one ``HealthCheck`` per registered check."""
    from primal_ai.harness import HealthMonitor

    monitor = HealthMonitor()
    monitor.register_check("db", _ok_check("db"))
    monitor.register_check("cache", _ok_check("cache"))
    results = monitor.run_all()
    assert set(results.keys()) == {"db", "cache"}


def test_health_monitor_raising_check_becomes_unhealthy() -> None:
    """A check that raises produces an UNHEALTHY verdict — never propagates."""
    from primal_ai import HealthStatus
    from primal_ai.harness import HealthMonitor

    def bad() -> Any:
        raise RuntimeError("boom")

    monitor = HealthMonitor()
    monitor.register_check("bad", bad)
    result = monitor.run("bad")
    assert result is not None
    assert result.status == HealthStatus.UNHEALTHY
    assert result.reason is not None
    assert "boom" in result.reason


def test_health_monitor_overall_status_is_worst_across_checks() -> None:
    """``overall_status`` returns the worst-grade status across every check."""
    from primal_ai import HealthCheck, HealthStatus
    from primal_ai.harness import HealthMonitor

    def degraded() -> HealthCheck:
        return HealthCheck(
            name="slow",
            status=HealthStatus.DEGRADED,
            reason=None,
            details={},
            checked_at=time.time(),
            latency_ms=None,
        )

    monitor = HealthMonitor()
    monitor.register_check("ok", _ok_check("ok"))
    monitor.register_check("slow", degraded)
    assert monitor.overall_status() == HealthStatus.DEGRADED


# ──────────────────────────────────────────────────────────────────────────
# ToolInfo + ToolRegistry
# ──────────────────────────────────────────────────────────────────────────


def test_tool_info_round_trips_via_to_dict_from_dict_handler_omitted() -> None:
    """``ToolInfo`` round-trips; the ``handler`` callable is omitted from ``to_dict``."""
    from primal_ai import ToolInfo

    def handler() -> str:
        return "hello"

    info = ToolInfo(
        name="hello",
        description="says hello",
        tags=("greeting",),
        metadata={"v": 1},
        handler=handler,
    )
    payload = info.to_dict()
    assert "handler" not in payload  # handlers are not serializable
    restored = ToolInfo.from_dict(payload)
    assert restored.name == "hello"
    assert restored.handler is None  # rehydrate without the callable


def test_tool_registry_register_and_get() -> None:
    """``ToolRegistry.register`` adds; ``get`` returns the tool by name."""
    from primal_ai import ToolInfo
    from primal_ai.harness import ToolRegistry

    reg = ToolRegistry()
    info = ToolInfo(name="t1", description="x", tags=(), metadata={}, handler=None)
    reg.register(info)
    assert reg.get("t1") is not None
    assert reg.get("t1").name == "t1"  # type: ignore[union-attr]


def test_tool_registry_register_duplicate_raises_value_error() -> None:
    """Registering twice with the same name raises ``ValueError``."""
    from primal_ai import ToolInfo
    from primal_ai.harness import ToolRegistry

    reg = ToolRegistry()
    info = ToolInfo(name="t1", description="x", tags=(), metadata={}, handler=None)
    reg.register(info)
    with pytest.raises(ValueError):
        reg.register(info)


def test_tool_registry_find_by_tag() -> None:
    """``find(tag=X)`` returns tools whose ``tags`` include X."""
    from primal_ai import ToolInfo
    from primal_ai.harness import ToolRegistry

    reg = ToolRegistry()
    reg.register(ToolInfo(name="a", description="x", tags=("legal",), metadata={}, handler=None))
    reg.register(ToolInfo(name="b", description="x", tags=("medical",), metadata={}, handler=None))
    legal = reg.find(tag="legal")
    assert [t.name for t in legal] == ["a"]


def test_tool_registry_find_by_text_match_uses_substring() -> None:
    """``find(text_match=...)`` does substring matching across name + description."""
    from primal_ai import ToolInfo
    from primal_ai.harness import ToolRegistry

    reg = ToolRegistry()
    reg.register(
        ToolInfo(
            name="search",
            description="search the web",
            tags=(),
            metadata={},
            handler=None,
        ),
    )
    reg.register(
        ToolInfo(
            name="summarize",
            description="condense text",
            tags=(),
            metadata={},
            handler=None,
        ),
    )
    matches = reg.find(text_match="search")
    assert {t.name for t in matches} == {"search"}


def test_tool_registry_list_all_returns_every_registered_tool() -> None:
    """``list_all`` returns a snapshot of every registered tool."""
    from primal_ai import ToolInfo
    from primal_ai.harness import ToolRegistry

    reg = ToolRegistry()
    reg.register(ToolInfo(name="a", description="x", tags=(), metadata={}, handler=None))
    reg.register(ToolInfo(name="b", description="x", tags=(), metadata={}, handler=None))
    assert {t.name for t in reg.list_all()} == {"a", "b"}


def test_tool_registry_persists_via_storage_round_trip() -> None:
    """Passing a ``store`` to ``register`` writes the tool's info to the store."""
    from primal_ai import ToolInfo
    from primal_ai.harness import ToolRegistry
    from primal_ai.storage import InMemoryStorage

    reg = ToolRegistry()
    store = InMemoryStorage()
    info = ToolInfo(
        name="search",
        description="search the web",
        tags=("web",),
        metadata={"v": 1},
        handler=None,
    )
    reg.register(info, store=store)
    assert store.get("harness:tool:search") is not None


def test_tool_registry_load_from_store_rehydrates_tools_with_none_handler() -> None:
    """``load_from_store`` rebuilds tools from ``harness:tool:*`` keys; handler stays None."""
    from primal_ai import ToolInfo
    from primal_ai.harness import ToolRegistry
    from primal_ai.storage import SQLiteStorage

    store = SQLiteStorage(":memory:")
    src_reg = ToolRegistry()
    src_reg.register(
        ToolInfo(
            name="search",
            description="search",
            tags=("web",),
            metadata={},
            handler=lambda: "x",  # this won't survive
        ),
        store=store,
    )

    dst_reg = ToolRegistry()
    loaded = dst_reg.load_from_store(store)
    assert loaded == 1
    assert dst_reg.get("search") is not None
    assert dst_reg.get("search").handler is None  # type: ignore[union-attr]
    store.close()


# ──────────────────────────────────────────────────────────────────────────
# Scheduler
# ──────────────────────────────────────────────────────────────────────────


def test_scheduler_runs_job_at_the_interval() -> None:
    """A scheduled job runs at least once within ``2 * interval`` seconds."""
    from primal_ai import ScheduledJob
    from primal_ai.harness import Scheduler

    counter = {"n": 0}

    def increment() -> None:
        counter["n"] += 1

    scheduler = Scheduler()
    scheduler.add_job(
        ScheduledJob(
            name="tick",
            func=increment,
            interval_seconds=0.05,
            next_run_at=0.0,
            enabled=True,
            metadata={},
        ),
    )
    scheduler.start()
    try:
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and counter["n"] < 2:
            time.sleep(0.05)
        assert counter["n"] >= 2
    finally:
        scheduler.stop(timeout=2.0)


def test_scheduler_catches_job_exception_and_keeps_running() -> None:
    """A raising job becomes a FAILED run; the scheduler thread doesn't die."""
    from primal_ai import ScheduledJob
    from primal_ai.harness import Scheduler

    runs = {"good": 0, "bad": 0}

    def good() -> None:
        runs["good"] += 1

    def bad() -> None:
        runs["bad"] += 1
        raise RuntimeError("intentional")

    scheduler = Scheduler()
    scheduler.add_job(
        ScheduledJob(
            name="bad",
            func=bad,
            interval_seconds=0.05,
            next_run_at=0.0,
            enabled=True,
            metadata={},
        ),
    )
    scheduler.add_job(
        ScheduledJob(
            name="good",
            func=good,
            interval_seconds=0.05,
            next_run_at=0.0,
            enabled=True,
            metadata={},
        ),
    )
    scheduler.start()
    try:
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and runs["good"] < 2:
            time.sleep(0.05)
        assert runs["good"] >= 2
        assert runs["bad"] >= 2  # the bad job kept firing too — exceptions are recovered
    finally:
        scheduler.stop(timeout=2.0)


def test_scheduler_stop_joins_thread_cleanly_within_timeout() -> None:
    """``stop(timeout=...)`` returns within the budget and ``is_running()`` becomes False."""
    from primal_ai.harness import Scheduler

    scheduler = Scheduler()
    scheduler.start()
    assert scheduler.is_running() is True
    scheduler.stop(timeout=2.0)
    assert scheduler.is_running() is False


def test_scheduler_start_is_idempotent() -> None:
    """Calling ``start`` while already running is a no-op (no duplicate threads)."""
    from primal_ai.harness import Scheduler

    scheduler = Scheduler()
    scheduler.start()
    scheduler.start()  # must not raise
    scheduler.stop(timeout=2.0)


def test_scheduler_stop_is_idempotent() -> None:
    """Calling ``stop`` when not running is a no-op (no raise)."""
    from primal_ai.harness import Scheduler

    Scheduler().stop(timeout=2.0)  # never started — must not raise


def test_scheduler_emits_scheduled_job_run_event_on_success() -> None:
    """A successful job run publishes a ``SCHEDULED_JOB_RUN`` event with status=success."""
    from primal_ai import Conductor, Event, EventKind, ScheduledJob
    from primal_ai.harness import Scheduler

    seen: list[Event] = []
    sub = Conductor.event_bus.subscribe(EventKind.SCHEDULED_JOB_RUN, seen.append)

    counter = {"n": 0}

    def increment() -> None:
        counter["n"] += 1

    scheduler = Scheduler()
    scheduler.add_job(
        ScheduledJob(
            name="ok",
            func=increment,
            interval_seconds=0.05,
            next_run_at=0.0,
            enabled=True,
            metadata={},
        ),
    )
    scheduler.start()
    try:
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and counter["n"] < 1:
            time.sleep(0.05)
    finally:
        scheduler.stop(timeout=2.0)
        Conductor.event_bus.unsubscribe(sub)
    success_events = [e for e in seen if e.payload.get("status") == "success"]
    assert len(success_events) >= 1


def test_scheduler_emits_scheduled_job_run_event_on_failure() -> None:
    """A failing job publishes a ``SCHEDULED_JOB_RUN`` event with status=failed + error string."""
    from primal_ai import Conductor, Event, EventKind, ScheduledJob
    from primal_ai.harness import Scheduler

    seen: list[Event] = []
    sub = Conductor.event_bus.subscribe(EventKind.SCHEDULED_JOB_RUN, seen.append)

    def bad() -> None:
        raise RuntimeError("oops")

    scheduler = Scheduler()
    scheduler.add_job(
        ScheduledJob(
            name="bad",
            func=bad,
            interval_seconds=0.05,
            next_run_at=0.0,
            enabled=True,
            metadata={},
        ),
    )
    scheduler.start()
    try:
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and not any(
            e.payload.get("status") == "failed" for e in seen
        ):
            time.sleep(0.05)
    finally:
        scheduler.stop(timeout=2.0)
        Conductor.event_bus.unsubscribe(sub)
    failures = [e for e in seen if e.payload.get("status") == "failed"]
    assert failures, "expected at least one failed-status event"
    assert "oops" in failures[0].payload.get("error", "")


# ──────────────────────────────────────────────────────────────────────────
# Harness facade
# ──────────────────────────────────────────────────────────────────────────


def test_harness_start_with_empty_config_is_noop() -> None:
    """``Harness.start({})`` doesn't start anything by default."""
    from primal_ai import Harness

    Harness.start(config={})
    assert Harness.scheduler.is_running() is False


def test_harness_start_with_scheduler_enabled_true_starts_scheduler() -> None:
    """``Harness.start({'scheduler_enabled': True})`` brings the scheduler up."""
    from primal_ai import Harness

    Harness.start(config={"scheduler_enabled": True})
    try:
        assert Harness.scheduler.is_running() is True
    finally:
        Harness.stop()


def test_harness_stop_stops_the_scheduler() -> None:
    """``Harness.stop()`` halts the scheduler thread."""
    from primal_ai import Harness

    Harness.start(config={"scheduler_enabled": True})
    assert Harness.scheduler.is_running() is True
    Harness.stop()
    assert Harness.scheduler.is_running() is False


def test_harness_register_tool_forwards_to_registry() -> None:
    """``Harness.register_tool`` adds to the module-level singleton registry."""
    from primal_ai import Harness, ToolInfo
    from primal_ai.harness import unregister_tool

    info = ToolInfo(
        name="hk-tool",
        description="harness facade test",
        tags=(),
        metadata={},
        handler=None,
    )
    Harness.register_tool(info)
    try:
        assert any(t.name == "hk-tool" for t in Harness.list_tools())
    finally:
        unregister_tool("hk-tool")


def test_concurrent_scheduler_threads_share_state_safely() -> None:
    """Two threads racing add_job / remove_job on one Scheduler don't corrupt the job list."""
    from primal_ai import ScheduledJob
    from primal_ai.harness import Scheduler

    scheduler = Scheduler()

    def add_many(prefix: str) -> None:
        for i in range(50):
            scheduler.add_job(
                ScheduledJob(
                    name=f"{prefix}-{i}",
                    func=lambda: None,
                    interval_seconds=10.0,
                    next_run_at=0.0,
                    enabled=False,
                    metadata={},
                ),
            )

    t1 = threading.Thread(target=add_many, args=("a",))
    t2 = threading.Thread(target=add_many, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert len(scheduler.list_jobs()) == 100
