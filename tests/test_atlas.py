"""Atlas core MVP — provider abstraction, health-aware routing, cascade with cooldown.

Contract for Phase 1 Session 7 Atlas: a stdlib-only routing layer with BYO
provider integration, deterministic candidate selection (bandit ships in
Session 8), exponential-backoff cascade, and Trajectory contextvar wiring.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


def _provider(
    name: str,
    *,
    capabilities: tuple[str, ...] = ("chat",),
    tags: tuple[str, ...] = (),
    fn: Any = None,
) -> Any:
    """Build a BYO provider with a controllable call function."""
    from primal_ai import BYOProvider, ProviderInfo

    def default_call(task: str, **kwargs: Any) -> Any:
        return {"task": task, "kwargs": kwargs, "by": name}

    info = ProviderInfo(
        name=name,
        description=f"fake provider {name}",
        capabilities=capabilities,
        tags=tags,
    )
    return BYOProvider(name=name, call=fn or default_call, info=info)


# ──────────────────────────────────────────────────────────────────────────
# Provider primitives
# ──────────────────────────────────────────────────────────────────────────


def test_provider_info_round_trips_via_to_dict_from_dict() -> None:
    """``ProviderInfo`` carries the documented fields and round-trips through JSON."""
    from primal_ai import ProviderInfo

    info = ProviderInfo(
        name="fake",
        description="x",
        capabilities=("chat", "vision"),
        cost_per_call_estimate=0.01,
        latency_ms_estimate=200.0,
        tags=("fast", "cheap"),
        metadata={"region": "us-east"},
    )
    restored = ProviderInfo.from_dict(info.to_dict())
    assert restored.name == "fake"
    assert restored.capabilities == ("chat", "vision")
    assert restored.cost_per_call_estimate == pytest.approx(0.01)
    assert restored.metadata == {"region": "us-east"}


def test_byo_provider_constructs_with_user_callable() -> None:
    """``BYOProvider`` wraps a user-supplied callable behind the Provider Protocol."""
    from primal_ai import BYOProvider, ProviderInfo

    def call(task: str, **kwargs: Any) -> str:
        return f"got:{task}"

    p = BYOProvider(name="x", call=call, info=ProviderInfo(name="x", description="x"))
    assert p.name == "x"
    assert p.info.name == "x"


def test_byo_provider_invoke_calls_the_wrapped_callable() -> None:
    """``BYOProvider.invoke`` forwards the call and returns its result."""
    from primal_ai import BYOProvider, ProviderInfo

    seen: list[str] = []

    def call(task: str, **kwargs: Any) -> str:
        seen.append(task)
        return "ok"

    p = BYOProvider(name="x", call=call, info=ProviderInfo(name="x", description="x"))
    assert p.invoke("hello") == "ok"
    assert seen == ["hello"]


def test_provider_protocol_satisfied_by_minimal_class() -> None:
    """Any class exposing ``name``, ``info``, ``invoke`` satisfies ``Provider``."""
    from primal_ai import Provider, ProviderInfo

    class Minimal:
        name = "min"
        info = ProviderInfo(name="min", description="x")

        def invoke(self, task: str, **kwargs: Any) -> Any:
            return task

    instance: Provider = Minimal()
    assert isinstance(instance, Provider)


# ──────────────────────────────────────────────────────────────────────────
# ProviderHealth
# ──────────────────────────────────────────────────────────────────────────


def test_provider_health_record_success_resets_consecutive_failures() -> None:
    """``record_success`` clears ``consecutive_failures`` and increments ``total_calls``."""
    from primal_ai import ProviderHealth

    h = ProviderHealth()
    h.record_failure(cooldown_seconds=0.0)
    h.record_failure(cooldown_seconds=0.0)
    assert h.consecutive_failures == 2

    h.record_success()
    assert h.consecutive_failures == 0
    assert h.total_calls >= 1


def test_provider_health_record_failure_sets_cooldown_until() -> None:
    """``record_failure`` advances ``cooldown_until`` by the given seconds."""
    from primal_ai import ProviderHealth

    h = ProviderHealth()
    before = time.monotonic()
    h.record_failure(cooldown_seconds=10.0)
    # Cooldown should be ~10s ahead of when we called it.
    assert h.cooldown_until >= before + 9.5
    assert h.cooldown_until <= before + 10.5
    assert h.consecutive_failures == 1


def test_provider_health_is_healthy_false_during_cooldown_then_true() -> None:
    """``is_healthy`` returns False while in cooldown, True after."""
    from primal_ai import ProviderHealth

    h = ProviderHealth()
    h.record_failure(cooldown_seconds=0.05)
    assert h.is_healthy() is False
    time.sleep(0.06)
    assert h.is_healthy() is True


# ──────────────────────────────────────────────────────────────────────────
# Atlas registry surface
# ──────────────────────────────────────────────────────────────────────────


def test_register_provider_adds_and_duplicate_raises_value_error() -> None:
    """``register_provider`` adds by name; registering twice raises ``ValueError``."""
    from primal_ai import Atlas

    p = _provider("reg-1")
    Atlas.register_provider(p)
    try:
        with pytest.raises(ValueError):
            Atlas.register_provider(p)
    finally:
        Atlas.unregister_provider("reg-1")


def test_unregister_provider_removes_and_noop_on_missing() -> None:
    """``unregister_provider`` removes; calling on missing is a no-op."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("reg-2"))
    Atlas.unregister_provider("reg-2")
    Atlas.unregister_provider("reg-2")  # silent no-op
    assert all(info.name != "reg-2" for info in Atlas.list_providers())


def test_list_providers_returns_info_objects() -> None:
    """``Atlas.list_providers`` returns ``ProviderInfo`` for every registered provider."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("listed-1"))
    try:
        names = {info.name for info in Atlas.list_providers()}
        assert "listed-1" in names
    finally:
        Atlas.unregister_provider("listed-1")


def test_find_by_capability_returns_matching_providers() -> None:
    """``Atlas.find(capability=X)`` returns providers whose info advertises X."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("find-cap-1", capabilities=("vision",)))
    Atlas.register_provider(_provider("find-cap-2", capabilities=("chat",)))
    try:
        names = {info.name for info in Atlas.find(capability="vision")}
        assert "find-cap-1" in names
        assert "find-cap-2" not in names
    finally:
        Atlas.unregister_provider("find-cap-1")
        Atlas.unregister_provider("find-cap-2")


def test_find_by_tag_returns_matching_providers() -> None:
    """``Atlas.find(tag=X)`` returns providers whose info tags include X."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("find-tag-1", tags=("fast",)))
    Atlas.register_provider(_provider("find-tag-2", tags=("cheap",)))
    try:
        names = {info.name for info in Atlas.find(tag="fast")}
        assert "find-tag-1" in names
        assert "find-tag-2" not in names
    finally:
        Atlas.unregister_provider("find-tag-1")
        Atlas.unregister_provider("find-tag-2")


# ──────────────────────────────────────────────────────────────────────────
# Atlas.route — picking
# ──────────────────────────────────────────────────────────────────────────


def test_route_returns_first_registered_provider_with_no_filters() -> None:
    """With no candidates or context, ``Atlas.route`` returns a registered provider name."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("route-1"))
    try:
        chosen = Atlas.route("anything")
        assert chosen != ""
    finally:
        Atlas.unregister_provider("route-1")


def test_route_respects_candidate_list_order() -> None:
    """``Atlas.route(task, candidates=[a, b])`` prefers the first healthy candidate listed."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("route-a"))
    Atlas.register_provider(_provider("route-b"))
    try:
        assert Atlas.route("x", candidates=["route-a", "route-b"]) == "route-a"
        assert Atlas.route("x", candidates=["route-b", "route-a"]) == "route-b"
    finally:
        Atlas.unregister_provider("route-a")
        Atlas.unregister_provider("route-b")


def test_route_filters_by_capability_from_context() -> None:
    """``context={'capability': X}`` narrows the pool to providers advertising X."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("vision-only", capabilities=("vision",)))
    Atlas.register_provider(_provider("chat-only", capabilities=("chat",)))
    try:
        assert Atlas.route("x", context={"capability": "vision"}) == "vision-only"
    finally:
        Atlas.unregister_provider("vision-only")
        Atlas.unregister_provider("chat-only")


def test_route_filters_by_tags_from_context() -> None:
    """``context={'tags': [...]}`` requires every tag to be present on the provider."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("p-fast", tags=("fast",)))
    Atlas.register_provider(_provider("p-slow", tags=("slow",)))
    try:
        assert Atlas.route("x", context={"tags": ["fast"]}) == "p-fast"
    finally:
        Atlas.unregister_provider("p-fast")
        Atlas.unregister_provider("p-slow")


def test_route_returns_empty_string_when_no_candidates_match() -> None:
    """No providers (or no matches) → empty string return; no raise."""
    from primal_ai import Atlas

    # Don't register anything; pristine registry has at least one earlier test's
    # provider name lingering only on failure — guard against it via candidates filter.
    chosen = Atlas.route("x", candidates=["__definitely_not_registered__"])
    assert chosen == ""


def test_route_returns_empty_when_every_match_is_in_cooldown() -> None:
    """If all matching providers are unhealthy, return ``""`` (status ALL_UNHEALTHY)."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("unhealthy-only"))
    try:
        Atlas.get_health("unhealthy-only").record_failure(cooldown_seconds=30.0)
        assert Atlas.route("x", candidates=["unhealthy-only"]) == ""
    finally:
        Atlas.reset_health("unhealthy-only")
        Atlas.unregister_provider("unhealthy-only")


def test_route_skips_unhealthy_and_picks_next_healthy() -> None:
    """A provider in cooldown is skipped; routing moves to the next healthy candidate."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("skip-a"))
    Atlas.register_provider(_provider("skip-b"))
    try:
        Atlas.get_health("skip-a").record_failure(cooldown_seconds=30.0)
        assert Atlas.route("x", candidates=["skip-a", "skip-b"]) == "skip-b"
    finally:
        Atlas.reset_health("skip-a")
        Atlas.unregister_provider("skip-a")
        Atlas.unregister_provider("skip-b")


# ──────────────────────────────────────────────────────────────────────────
# Atlas.invoke — do-it convenience
# ──────────────────────────────────────────────────────────────────────────


def test_invoke_calls_chosen_provider_and_returns_name_plus_result() -> None:
    """``Atlas.invoke`` returns ``(provider_name, result)`` on a healthy provider."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("inv-ok"))
    try:
        name, result = Atlas.invoke("hi", candidates=["inv-ok"])
        assert name == "inv-ok"
        assert result["task"] == "hi"
    finally:
        Atlas.unregister_provider("inv-ok")


def test_invoke_records_success_on_health() -> None:
    """A successful ``invoke`` resets ``consecutive_failures`` and increments ``total_calls``."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("health-ok"))
    try:
        h = Atlas.get_health("health-ok")
        h.record_failure(0.0)  # bump failure count first
        assert h.consecutive_failures == 1
        Atlas.invoke("x", candidates=["health-ok"])
        assert h.consecutive_failures == 0
        assert h.total_calls >= 1
    finally:
        Atlas.reset_health("health-ok")
        Atlas.unregister_provider("health-ok")


def test_invoke_records_failure_on_health_when_provider_raises() -> None:
    """A raising provider produces a failure record; the call returns (name, None)."""
    from primal_ai import Atlas

    def broken(task: str, **kwargs: Any) -> Any:
        raise RuntimeError("nope")

    Atlas.register_provider(_provider("inv-broken", fn=broken))
    try:
        name, result = Atlas.invoke("x", candidates=["inv-broken"])
        assert name == "inv-broken"
        assert result is None
        h = Atlas.get_health("inv-broken")
        assert h.total_failures >= 1
        assert h.consecutive_failures >= 1
    finally:
        Atlas.reset_health("inv-broken")
        Atlas.unregister_provider("inv-broken")


def test_invoke_returns_empty_name_when_no_candidates_survive() -> None:
    """``Atlas.invoke`` returns ``("", None)`` when route() couldn't pick anyone."""
    from primal_ai import Atlas

    name, result = Atlas.invoke("x", candidates=["__not_registered__"])
    assert name == ""
    assert result is None


# ──────────────────────────────────────────────────────────────────────────
# Cascade
# ──────────────────────────────────────────────────────────────────────────


def test_cascade_run_uses_first_healthy_success() -> None:
    """``Cascade.run`` tries providers in order and stops on the first SUCCESS."""
    from primal_ai import Atlas, Cascade, RoutingStatus

    Atlas.register_provider(_provider("cas-a"))
    Atlas.register_provider(_provider("cas-b"))
    try:
        result = Cascade(providers=["cas-a", "cas-b"]).run("task")
        assert result.status == RoutingStatus.SUCCESS
        assert result.chosen == "cas-a"
    finally:
        Atlas.unregister_provider("cas-a")
        Atlas.unregister_provider("cas-b")


def test_cascade_run_falls_through_failing_provider() -> None:
    """On the first provider's failure, cascade tries the next one."""
    from primal_ai import Atlas, Cascade, RoutingStatus

    def broken(task: str, **kwargs: Any) -> Any:
        raise RuntimeError("nope")

    Atlas.register_provider(_provider("cas-bad", fn=broken))
    Atlas.register_provider(_provider("cas-good"))
    try:
        result = Cascade(providers=["cas-bad", "cas-good"]).run("task")
        assert result.status == RoutingStatus.SUCCESS
        assert result.chosen == "cas-good"
        # The bad provider's attempt is recorded.
        bad_attempts = [a for a in result.attempts if a[0] == "cas-bad"]
        assert len(bad_attempts) == 1
        assert bad_attempts[0][1] == RoutingStatus.FAILED
    finally:
        Atlas.reset_health("cas-bad")
        Atlas.unregister_provider("cas-bad")
        Atlas.unregister_provider("cas-good")


def test_cascade_run_returns_failed_when_all_providers_fail() -> None:
    """If every provider in the cascade fails, the result is FAILED."""
    from primal_ai import Atlas, Cascade, RoutingStatus

    def broken(task: str, **kwargs: Any) -> Any:
        raise RuntimeError("nope")

    Atlas.register_provider(_provider("cas-all-bad-1", fn=broken))
    Atlas.register_provider(_provider("cas-all-bad-2", fn=broken))
    try:
        result = Cascade(providers=["cas-all-bad-1", "cas-all-bad-2"]).run("task")
        assert result.status == RoutingStatus.FAILED
        assert result.chosen is None
    finally:
        Atlas.reset_health("cas-all-bad-1")
        Atlas.reset_health("cas-all-bad-2")
        Atlas.unregister_provider("cas-all-bad-1")
        Atlas.unregister_provider("cas-all-bad-2")


def test_cascade_exponential_backoff_doubles_cooldown_on_consecutive_failures() -> None:
    """Second consecutive failure of one provider yields ~2× the first failure's cooldown."""
    from primal_ai import Atlas, Cascade

    def broken(task: str, **kwargs: Any) -> Any:
        raise RuntimeError("nope")

    Atlas.register_provider(_provider("cas-exp", fn=broken))
    try:
        cascade = Cascade(
            providers=["cas-exp"],
            base_cooldown_seconds=0.05,
            max_cooldown_seconds=10.0,
        )
        # First failure → cooldown ≈ base
        before1 = time.monotonic()
        cascade.run("t1")
        h = Atlas.get_health("cas-exp")
        cd1 = h.cooldown_until - before1
        # Wait for the cooldown to expire so the provider is healthy again.
        time.sleep(cd1 + 0.02)
        # Second failure → cooldown ≈ base * 2
        before2 = time.monotonic()
        cascade.run("t2")
        cd2 = h.cooldown_until - before2
        assert cd2 >= cd1 * 1.5  # tolerant of clock jitter
    finally:
        Atlas.reset_health("cas-exp")
        Atlas.unregister_provider("cas-exp")


def test_cascade_cooldown_is_capped_at_max_cooldown_seconds() -> None:
    """Cooldown growth caps at ``max_cooldown_seconds`` no matter how many failures."""
    from primal_ai import Atlas, Cascade

    def broken(task: str, **kwargs: Any) -> Any:
        raise RuntimeError("nope")

    Atlas.register_provider(_provider("cas-cap", fn=broken))
    try:
        cascade = Cascade(
            providers=["cas-cap"],
            base_cooldown_seconds=0.02,
            max_cooldown_seconds=0.10,
        )
        # Force many failures so 2^n * base would blow past the cap.
        for _ in range(8):
            cascade.run("t")
            time.sleep(0.12)  # let the cooldown expire each time
        h = Atlas.get_health("cas-cap")
        # The last cooldown set should be at most ``max_cooldown_seconds``.
        # Measure by running once more and capturing.
        before = time.monotonic()
        cascade.run("t-final")
        cd = h.cooldown_until - before
        assert cd <= 0.10 + 0.02  # cap + small tolerance
    finally:
        Atlas.reset_health("cas-cap")
        Atlas.unregister_provider("cas-cap")


# ──────────────────────────────────────────────────────────────────────────
# Health management
# ──────────────────────────────────────────────────────────────────────────


def test_reset_health_clears_a_single_provider_cooldown() -> None:
    """``Atlas.reset_health('name')`` clears cooldown for one provider only."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("rh-1"))
    Atlas.register_provider(_provider("rh-2"))
    try:
        Atlas.get_health("rh-1").record_failure(cooldown_seconds=30.0)
        Atlas.get_health("rh-2").record_failure(cooldown_seconds=30.0)

        Atlas.reset_health("rh-1")

        assert Atlas.get_health("rh-1").is_healthy() is True
        assert Atlas.get_health("rh-2").is_healthy() is False
    finally:
        Atlas.reset_health("rh-1")
        Atlas.reset_health("rh-2")
        Atlas.unregister_provider("rh-1")
        Atlas.unregister_provider("rh-2")


def test_reset_health_with_no_args_clears_all() -> None:
    """``Atlas.reset_health()`` with no argument clears every provider's cooldown."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("rh-all-1"))
    Atlas.register_provider(_provider("rh-all-2"))
    try:
        Atlas.get_health("rh-all-1").record_failure(cooldown_seconds=30.0)
        Atlas.get_health("rh-all-2").record_failure(cooldown_seconds=30.0)

        Atlas.reset_health()

        assert Atlas.get_health("rh-all-1").is_healthy() is True
        assert Atlas.get_health("rh-all-2").is_healthy() is True
    finally:
        Atlas.unregister_provider("rh-all-1")
        Atlas.unregister_provider("rh-all-2")


# ──────────────────────────────────────────────────────────────────────────
# Trajectory integration
# ──────────────────────────────────────────────────────────────────────────


def test_route_inside_trajectory_records_routing_decision_step() -> None:
    """A route inside ``Trajectory.record()`` appends a ROUTING_DECISION step."""
    from primal_ai import Atlas, StepKind, Trajectory

    Atlas.register_provider(_provider("traj-route"))
    try:
        with Trajectory.record() as tr:
            Atlas.route("hi", candidates=["traj-route"])
        steps = tr.find_steps(kind=StepKind.ROUTING_DECISION)
        assert len(steps) == 1
        assert steps[0].data["chosen_provider"] == "traj-route"
    finally:
        Atlas.unregister_provider("traj-route")


def test_route_outside_trajectory_does_not_record() -> None:
    """Without an active trajectory in context, no step is appended (no crash)."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("no-traj"))
    try:
        chosen = Atlas.route("hi", candidates=["no-traj"])  # smoke
        assert chosen == "no-traj"
    finally:
        Atlas.unregister_provider("no-traj")


# ──────────────────────────────────────────────────────────────────────────
# Shared EventBus
# ──────────────────────────────────────────────────────────────────────────


def test_route_emits_routing_decided_event_on_shared_bus() -> None:
    """``Atlas.route`` publishes a ROUTING_DECIDED event subscribable from anywhere."""
    from primal_ai import Atlas, Conductor, Event, EventKind

    Atlas.register_provider(_provider("bus-route"))
    seen: list[Event] = []
    # Subscribe via Conductor.event_bus to prove the bus is shared.
    sub = Conductor.event_bus.subscribe(EventKind.ROUTING_DECIDED, seen.append)
    try:
        Atlas.route("x", candidates=["bus-route"])
        assert len(seen) == 1
        assert seen[0].payload["decision"]["chosen_provider"] == "bus-route"
    finally:
        Conductor.event_bus.unsubscribe(sub)
        Atlas.unregister_provider("bus-route")


def test_cascade_lifecycle_events_fire_in_order() -> None:
    """A cascade run emits CASCADE_STARTED → CASCADE_ATTEMPT(s) → CASCADE_COMPLETED."""
    from primal_ai import Atlas, Cascade, Conductor, Event, EventKind

    Atlas.register_provider(_provider("cas-evt-1"))
    seen: list[Event] = []
    sub = Conductor.event_bus.subscribe(None, seen.append)
    try:
        Cascade(providers=["cas-evt-1"]).run("task")
        kinds = [e.kind for e in seen]
        # STARTED before any ATTEMPT before COMPLETED.
        i_start = kinds.index(EventKind.CASCADE_STARTED.value)
        i_attempt = kinds.index(EventKind.CASCADE_ATTEMPT.value)
        i_complete = kinds.index(EventKind.CASCADE_COMPLETED.value)
        assert i_start < i_attempt < i_complete
    finally:
        Conductor.event_bus.unsubscribe(sub)
        Atlas.unregister_provider("cas-evt-1")


# ──────────────────────────────────────────────────────────────────────────
# Concurrent isolation
# ──────────────────────────────────────────────────────────────────────────


def test_concurrent_routes_in_threads_isolate_routing_decision_steps() -> None:
    """Two trajectories in two threads each see only their own ROUTING_DECISION steps."""
    from primal_ai import Atlas, StepKind, Trajectory

    Atlas.register_provider(_provider("conc-a"))
    Atlas.register_provider(_provider("conc-b"))
    captured: dict[str, list[int]] = {"a": [], "b": []}

    def run_a() -> None:
        with Trajectory.record() as tr:
            for _ in range(3):
                Atlas.route("x", candidates=["conc-a"])
        captured["a"].append(len(tr.find_steps(kind=StepKind.ROUTING_DECISION)))

    def run_b() -> None:
        with Trajectory.record() as tr:
            for _ in range(5):
                Atlas.route("x", candidates=["conc-b"])
        captured["b"].append(len(tr.find_steps(kind=StepKind.ROUTING_DECISION)))

    ta = threading.Thread(target=run_a)
    tb = threading.Thread(target=run_b)
    ta.start()
    tb.start()
    ta.join()
    tb.join()
    Atlas.unregister_provider("conc-a")
    Atlas.unregister_provider("conc-b")
    assert captured == {"a": [3], "b": [5]}


def test_all_public_atlas_exports_import() -> None:
    """All documented Atlas exports import from ``primal_ai``."""
    from primal_ai import (
        Atlas,
        BYOProvider,
        Cascade,
        CascadeResult,
        Provider,
        ProviderHealth,
        ProviderInfo,
        RoutingDecision,
        RoutingStatus,
        register_provider,
        unregister_provider,
    )

    assert all(
        x is not None
        for x in [
            Atlas,
            BYOProvider,
            Cascade,
            CascadeResult,
            Provider,
            ProviderHealth,
            ProviderInfo,
            RoutingDecision,
            RoutingStatus,
            register_provider,
            unregister_provider,
        ]
    )
