"""Atlas bandit MVP — Thompson + UCB1, contextual partitioning, Atlas integration, persistence.

Contract for Phase 1 Session 8 Bandit: a stdlib-only bandit-driven selector
that plugs into Atlas without changing the public surface. Deterministic
routing stays the default; the bandit is opt-in.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


def _provider(name: str, *, fn: Any = None) -> Any:
    """Build a BYO provider; ``fn`` overrides the default echo behaviour."""
    from primal_ai import BYOProvider, ProviderInfo

    def default_call(task: str, **kwargs: Any) -> Any:
        return {"task": task, "by": name}

    return BYOProvider(
        name=name,
        call=fn or default_call,
        info=ProviderInfo(name=name, capabilities=("chat",)),
    )


# ──────────────────────────────────────────────────────────────────────────
# BanditOutcome + ArmState round-trips
# ──────────────────────────────────────────────────────────────────────────


def test_bandit_outcome_round_trips_via_to_dict_from_dict() -> None:
    """``BanditOutcome`` round-trips through JSON without loss."""
    from primal_ai import BanditOutcome

    o = BanditOutcome(
        provider_name="alpha",
        success=True,
        reward=1.0,
        cost=0.002,
        latency_ms=120.0,
        context_key="summarize",
        timestamp=1234.5,
    )
    restored = BanditOutcome.from_dict(json.loads(json.dumps(o.to_dict())))
    assert restored.provider_name == "alpha"
    assert restored.success is True
    assert restored.reward == pytest.approx(1.0)
    assert restored.context_key == "summarize"


def test_arm_state_round_trips_via_to_dict_from_dict() -> None:
    """``ArmState`` round-trips through JSON without loss."""
    from primal_ai import ArmState

    s = ArmState(
        provider_name="alpha",
        context_key="",
        successes=10,
        failures=3,
        total_reward=11.0,
        pulls=13,
        last_updated=42.0,
    )
    restored = ArmState.from_dict(json.loads(json.dumps(s.to_dict())))
    assert restored.successes == 10
    assert restored.failures == 3
    assert restored.pulls == 13


def test_bandit_protocol_satisfied_by_concrete_classes() -> None:
    """``ThompsonBandit`` and ``UCB1Bandit`` both structurally satisfy ``Bandit``."""
    from primal_ai import Bandit, ThompsonBandit, UCB1Bandit

    t: Bandit = ThompsonBandit()
    u: Bandit = UCB1Bandit()
    assert isinstance(t, Bandit)
    assert isinstance(u, Bandit)


# ──────────────────────────────────────────────────────────────────────────
# ThompsonBandit
# ──────────────────────────────────────────────────────────────────────────


def test_thompson_seed_makes_selection_deterministic() -> None:
    """Two ``ThompsonBandit(seed=42)`` instances pick the same arm given identical state."""
    from primal_ai import ThompsonBandit

    a = ThompsonBandit(seed=42)
    b = ThompsonBandit(seed=42)
    picks_a = [a.select(["x", "y", "z"]) for _ in range(20)]
    picks_b = [b.select(["x", "y", "z"]) for _ in range(20)]
    assert picks_a == picks_b


def test_thompson_select_with_empty_candidates_returns_none() -> None:
    """Empty candidate list → ``None`` (never raises)."""
    from primal_ai import ThompsonBandit

    assert ThompsonBandit().select([]) is None


def test_thompson_select_with_one_candidate_returns_it() -> None:
    """Degenerate single-candidate case returns that candidate."""
    from primal_ai import ThompsonBandit

    assert ThompsonBandit().select(["solo"]) == "solo"


def test_thompson_update_increments_successes_and_failures() -> None:
    """``update`` with success bumps ``successes``; failure bumps ``failures``."""
    from primal_ai import BanditOutcome, ThompsonBandit

    bandit = ThompsonBandit()
    bandit.update(BanditOutcome(provider_name="a", success=True, reward=1.0))
    bandit.update(BanditOutcome(provider_name="a", success=False, reward=0.0))
    bandit.update(BanditOutcome(provider_name="a", success=True, reward=1.0))
    state = bandit.state_for("a")
    assert state is not None
    assert state.successes == 2
    assert state.failures == 1


def test_thompson_converges_on_better_arm_after_100_updates() -> None:
    """After 100 outcomes with A=always-success, B=always-fail, Thompson picks A overwhelmingly."""
    from primal_ai import BanditOutcome, ThompsonBandit

    bandit = ThompsonBandit(seed=1)
    for _ in range(100):
        bandit.update(BanditOutcome(provider_name="A", success=True, reward=1.0))
        bandit.update(BanditOutcome(provider_name="B", success=False, reward=0.0))
    picks = [bandit.select(["A", "B"]) for _ in range(200)]
    a_share = picks.count("A") / len(picks)
    assert a_share > 0.95


def test_thompson_contextual_partitions_state_by_context_key() -> None:
    """The same provider has separate ``ArmState`` under different ``context_key`` values."""
    from primal_ai import BanditOutcome, ThompsonBandit

    bandit = ThompsonBandit()
    bandit.update(
        BanditOutcome(provider_name="a", success=True, reward=1.0, context_key="ctx1"),
    )
    bandit.update(
        BanditOutcome(provider_name="a", success=False, reward=0.0, context_key="ctx2"),
    )
    s1 = bandit.state_for("a", context_key="ctx1")
    s2 = bandit.state_for("a", context_key="ctx2")
    assert s1 is not None and s1.successes == 1 and s1.failures == 0
    assert s2 is not None and s2.successes == 0 and s2.failures == 1


# ──────────────────────────────────────────────────────────────────────────
# UCB1Bandit
# ──────────────────────────────────────────────────────────────────────────


def test_ucb1_picks_every_untried_arm_before_repeating() -> None:
    """UCB1 explores every arm at least once (untried arms have infinite score)."""
    from primal_ai import UCB1Bandit

    bandit = UCB1Bandit()
    arms = ["a", "b", "c", "d"]
    seen: set[str] = set()
    for _ in range(len(arms)):
        chosen = bandit.select(arms)
        assert chosen is not None
        seen.add(chosen)
        # Simulate one observation per pick so each arm has pulls>=1 after this loop.
        from primal_ai import BanditOutcome

        bandit.update(BanditOutcome(provider_name=chosen, success=True, reward=1.0))
    assert seen == set(arms)


def test_ucb1_select_with_empty_candidates_returns_none() -> None:
    """Empty candidate list → ``None`` (never raises)."""
    from primal_ai import UCB1Bandit

    assert UCB1Bandit().select([]) is None


def test_ucb1_converges_on_better_arm_after_100_updates() -> None:
    """After 100 outcomes with A reward=0.9 and B reward=0.1, UCB1 picks A most of the time."""
    from primal_ai import BanditOutcome, UCB1Bandit

    bandit = UCB1Bandit(exploration_constant=2.0)
    for _ in range(100):
        bandit.update(BanditOutcome(provider_name="A", success=True, reward=0.9))
        bandit.update(BanditOutcome(provider_name="B", success=False, reward=0.1))
    picks = [bandit.select(["A", "B"]) for _ in range(200)]
    # Convergence is deterministic given the same pull counts → 100% on A here.
    a_share = picks.count("A") / len(picks)
    assert a_share > 0.90


def test_ucb1_exploration_constant_scales_exploration_term() -> None:
    """A higher ``exploration_constant`` produces a larger exploration bonus for the chosen arm."""
    from primal_ai import BanditOutcome, UCB1Bandit

    # Seed deterministic state by recording identical pulls on both bandits.
    def seed(bandit: UCB1Bandit) -> None:
        for _ in range(5):
            bandit.update(BanditOutcome(provider_name="a", success=True, reward=0.8))
            bandit.update(BanditOutcome(provider_name="b", success=True, reward=0.8))

    low = UCB1Bandit(exploration_constant=0.1)
    high = UCB1Bandit(exploration_constant=10.0)
    seed(low)
    seed(high)
    _chosen_low, _scores_low, exp_low = low.select_with_metadata(["a", "b"])
    _chosen_high, _scores_high, exp_high = high.select_with_metadata(["a", "b"])
    assert exp_low is not None and exp_high is not None
    assert exp_high > exp_low


def test_ucb1_contextual_partitions_state_by_context_key() -> None:
    """The same provider keeps separate UCB1 state under different ``context_key`` values."""
    from primal_ai import BanditOutcome, UCB1Bandit

    bandit = UCB1Bandit()
    bandit.update(
        BanditOutcome(provider_name="a", success=True, reward=1.0, context_key="ctx1"),
    )
    bandit.update(
        BanditOutcome(provider_name="a", success=False, reward=0.0, context_key="ctx2"),
    )
    s1 = bandit.state_for("a", context_key="ctx1")
    s2 = bandit.state_for("a", context_key="ctx2")
    assert s1 is not None and s1.pulls == 1 and s1.total_reward == pytest.approx(1.0)
    assert s2 is not None and s2.pulls == 1 and s2.total_reward == pytest.approx(0.0)


# ──────────────────────────────────────────────────────────────────────────
# Atlas.set_selector + per-call override
# ──────────────────────────────────────────────────────────────────────────


def test_set_selector_by_string_resolves_via_registry() -> None:
    """``Atlas.set_selector('thompson')`` resolves the registry name into an instance."""
    from primal_ai import Atlas, ThompsonBandit

    Atlas.set_selector("thompson")
    try:
        sel = Atlas.get_selector()
        assert isinstance(sel, ThompsonBandit)
    finally:
        Atlas.set_selector(None)


def test_set_selector_with_instance_uses_it_directly() -> None:
    """Passing an instance bypasses the registry."""
    from primal_ai import Atlas, ThompsonBandit

    custom = ThompsonBandit(seed=99)
    Atlas.set_selector(custom)
    try:
        assert Atlas.get_selector() is custom
    finally:
        Atlas.set_selector(None)


def test_set_selector_none_reverts_to_deterministic() -> None:
    """``set_selector(None)`` clears the active selector."""
    from primal_ai import Atlas, ThompsonBandit

    Atlas.set_selector(ThompsonBandit())
    Atlas.set_selector(None)
    assert Atlas.get_selector() is None


def test_set_selector_unknown_name_raises_value_error_listing_registered() -> None:
    """Unknown DSL name raises with a message listing registered selectors."""
    from primal_ai import Atlas

    with pytest.raises(ValueError) as exc:
        Atlas.set_selector("__not_a_selector__")
    msg = str(exc.value)
    assert "__not_a_selector__" in msg
    assert "thompson" in msg
    assert "ucb1" in msg


def test_per_call_selector_override_in_context() -> None:
    """``context={'selector': 'ucb1'}`` overrides the default per call."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("over-a"))
    Atlas.register_provider(_provider("over-b"))
    try:
        # Default is deterministic. Override with ucb1 for this one call.
        chosen = Atlas.route(
            "x",
            candidates=["over-a", "over-b"],
            context={"selector": "ucb1"},
        )
        assert chosen in {"over-a", "over-b"}
    finally:
        Atlas.unregister_provider("over-a")
        Atlas.unregister_provider("over-b")


# ──────────────────────────────────────────────────────────────────────────
# Atlas.invoke + Cascade feedback
# ──────────────────────────────────────────────────────────────────────────


def test_invoke_records_success_outcome_and_updates_selector() -> None:
    """``Atlas.invoke`` on a healthy provider emits a success ``BanditOutcome`` to the selector."""
    from primal_ai import Atlas, ThompsonBandit

    Atlas.register_provider(_provider("fb-ok"))
    selector = ThompsonBandit(seed=1)
    Atlas.set_selector(selector)
    try:
        Atlas.invoke("hi", candidates=["fb-ok"])
        state = selector.state_for("fb-ok")
        assert state is not None
        assert state.successes >= 1
    finally:
        Atlas.set_selector(None)
        Atlas.reset_health("fb-ok")
        Atlas.unregister_provider("fb-ok")


def test_invoke_records_failure_outcome_when_provider_raises() -> None:
    """A failing provider produces a failure ``BanditOutcome`` on the selector."""
    from primal_ai import Atlas, ThompsonBandit

    def broken(task: str, **kwargs: Any) -> Any:
        raise RuntimeError("boom")

    Atlas.register_provider(_provider("fb-bad", fn=broken))
    selector = ThompsonBandit(seed=1)
    Atlas.set_selector(selector)
    try:
        Atlas.invoke("hi", candidates=["fb-bad"])
        state = selector.state_for("fb-bad")
        assert state is not None
        assert state.failures >= 1
    finally:
        Atlas.set_selector(None)
        Atlas.reset_health("fb-bad")
        Atlas.unregister_provider("fb-bad")


def test_cascade_records_one_outcome_per_attempt() -> None:
    """Each cascade attempt produces a ``BanditOutcome``; the eventual SUCCESS has success=True."""
    from primal_ai import Atlas, Cascade, ThompsonBandit

    def broken(task: str, **kwargs: Any) -> Any:
        raise RuntimeError("nope")

    Atlas.register_provider(_provider("casfb-bad", fn=broken))
    Atlas.register_provider(_provider("casfb-good"))
    selector = ThompsonBandit(seed=1)
    Atlas.set_selector(selector)
    try:
        Cascade(providers=["casfb-bad", "casfb-good"]).run("task")
        good = selector.state_for("casfb-good")
        bad = selector.state_for("casfb-bad")
        assert good is not None and good.successes >= 1
        assert bad is not None and bad.failures >= 1
    finally:
        Atlas.set_selector(None)
        Atlas.reset_health("casfb-bad")
        Atlas.unregister_provider("casfb-bad")
        Atlas.unregister_provider("casfb-good")


# ──────────────────────────────────────────────────────────────────────────
# Trajectory enrichment
# ──────────────────────────────────────────────────────────────────────────


def test_routing_decision_step_carries_selector_metadata_when_bandit_active() -> None:
    """ROUTING_DECISION step.data gains selector_name + arm_scores when bandit selected."""
    from primal_ai import Atlas, StepKind, ThompsonBandit, Trajectory

    Atlas.register_provider(_provider("traj-bandit-a"))
    Atlas.register_provider(_provider("traj-bandit-b"))
    Atlas.set_selector(ThompsonBandit(seed=1))
    try:
        with Trajectory.record() as tr:
            Atlas.route("x", candidates=["traj-bandit-a", "traj-bandit-b"])
        step = tr.find_steps(kind=StepKind.ROUTING_DECISION)[0]
        assert step.data["selector_name"] == "thompson"
        assert "arm_scores" in step.data
        assert set(step.data["arm_scores"].keys()) >= {"traj-bandit-a", "traj-bandit-b"}
    finally:
        Atlas.set_selector(None)
        Atlas.unregister_provider("traj-bandit-a")
        Atlas.unregister_provider("traj-bandit-b")


def test_routing_decision_step_omits_selector_metadata_when_deterministic() -> None:
    """ROUTING_DECISION's ``data`` does NOT carry selector keys under deterministic routing."""
    from primal_ai import Atlas, StepKind, Trajectory

    Atlas.register_provider(_provider("traj-det"))
    Atlas.set_selector(None)  # explicit, just in case
    try:
        with Trajectory.record() as tr:
            Atlas.route("x", candidates=["traj-det"])
        step = tr.find_steps(kind=StepKind.ROUTING_DECISION)[0]
        # Absent — not None. Documented contract.
        assert "selector_name" not in step.data
        assert "arm_scores" not in step.data
    finally:
        Atlas.unregister_provider("traj-det")


# ──────────────────────────────────────────────────────────────────────────
# Persistence
# ──────────────────────────────────────────────────────────────────────────


def test_bandit_save_load_round_trip_via_in_memory_storage() -> None:
    """``save`` + ``load`` round-trips ``ArmState`` through the ``Storage`` Protocol."""
    from primal_ai import BanditOutcome, ThompsonBandit
    from primal_ai.storage import InMemoryStorage

    src = ThompsonBandit(name="persist-test")
    src.update(BanditOutcome(provider_name="a", success=True, reward=1.0))
    src.update(BanditOutcome(provider_name="b", success=False, reward=0.0))

    store = InMemoryStorage()
    src.save(store)

    dst = ThompsonBandit(name="persist-test")
    dst.load(store)

    assert dst.state_for("a") is not None
    assert dst.state_for("a").successes == 1  # type: ignore[union-attr]
    assert dst.state_for("b") is not None
    assert dst.state_for("b").failures == 1  # type: ignore[union-attr]


def test_bandit_save_load_round_trip_via_sqlite_storage(tmp_path: Any) -> None:
    """Same round-trip but persisted across a fresh ``SQLiteStorage`` connection."""
    from primal_ai import BanditOutcome, UCB1Bandit
    from primal_ai.storage import SQLiteStorage

    db = tmp_path / "bandit.db"
    src = UCB1Bandit(name="ucb1-persist")
    for _ in range(3):
        src.update(BanditOutcome(provider_name="a", success=True, reward=1.0))
    with SQLiteStorage(db) as store:
        src.save(store)

    with SQLiteStorage(db) as store:
        dst = UCB1Bandit(name="ucb1-persist")
        dst.load(store)
    state = dst.state_for("a")
    assert state is not None
    assert state.pulls == 3
    assert state.total_reward == pytest.approx(3.0)


# ──────────────────────────────────────────────────────────────────────────
# Atlas.feedback convenience
# ──────────────────────────────────────────────────────────────────────────


def test_atlas_feedback_forwards_to_active_selector() -> None:
    """``Atlas.feedback(outcome)`` calls ``selector.update(outcome)`` on the active selector."""
    from primal_ai import Atlas, BanditOutcome, ThompsonBandit

    selector = ThompsonBandit()
    Atlas.set_selector(selector)
    try:
        Atlas.feedback(BanditOutcome(provider_name="a", success=True, reward=1.0))
        Atlas.feedback(BanditOutcome(provider_name="a", success=False, reward=0.0))
        state = selector.state_for("a")
        assert state is not None
        assert state.successes == 1
        assert state.failures == 1
    finally:
        Atlas.set_selector(None)


# ──────────────────────────────────────────────────────────────────────────
# Thread safety
# ──────────────────────────────────────────────────────────────────────────


def test_bandit_thread_safe_under_concurrent_select_and_update() -> None:
    """Two threads doing select() + update() concurrently produce coherent final counts."""
    from primal_ai import BanditOutcome, ThompsonBandit

    bandit = ThompsonBandit(seed=7)
    total_successes_per_arm = 5000

    def worker(arm: str) -> None:
        for _ in range(total_successes_per_arm):
            bandit.select(["a", "b"])
            bandit.update(BanditOutcome(provider_name=arm, success=True, reward=1.0))

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    sa = bandit.state_for("a")
    sb = bandit.state_for("b")
    assert sa is not None and sa.successes == total_successes_per_arm
    assert sb is not None and sb.successes == total_successes_per_arm


# ──────────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────────


def test_register_selector_makes_a_name_resolvable() -> None:
    """``register_selector('custom', factory)`` lets ``Atlas.set_selector('custom')`` work."""
    from primal_ai import Atlas, ThompsonBandit, register_selector
    from primal_ai.atlas.bandit import _SELECTOR_REGISTRY

    register_selector("__test_custom", lambda: ThompsonBandit(seed=123))
    try:
        Atlas.set_selector("__test_custom")
        assert isinstance(Atlas.get_selector(), ThompsonBandit)
    finally:
        Atlas.set_selector(None)
        _SELECTOR_REGISTRY.pop("__test_custom", None)


# ──────────────────────────────────────────────────────────────────────────
# Health filter integration
# ──────────────────────────────────────────────────────────────────────────


def test_unhealthy_provider_is_excluded_before_selector_sees_it() -> None:
    """Atlas filters out providers in cooldown before handing candidates to ``selector.select``."""
    from primal_ai import Atlas

    Atlas.register_provider(_provider("hf-healthy"))
    Atlas.register_provider(_provider("hf-cooldown"))
    Atlas.get_health("hf-cooldown").record_failure(cooldown_seconds=30.0)  # type: ignore[union-attr]

    seen_candidates: list[list[str]] = []

    class RecordingBandit:
        name = "recorder"

        def select(self, candidates: list[str], context: Any = None) -> str | None:
            seen_candidates.append(list(candidates))
            return candidates[0] if candidates else None

        def update(self, outcome: Any) -> None:
            return None

        def state_for(self, provider_name: str, context_key: str = "") -> Any:
            return None

        def save(self, store: Any) -> None:
            return None

        def load(self, store: Any) -> None:
            return None

    Atlas.set_selector(RecordingBandit())
    try:
        Atlas.route("x", candidates=["hf-healthy", "hf-cooldown"])
        assert "hf-cooldown" not in seen_candidates[0]
        assert "hf-healthy" in seen_candidates[0]
    finally:
        Atlas.set_selector(None)
        Atlas.reset_health("hf-cooldown")
        Atlas.unregister_provider("hf-healthy")
        Atlas.unregister_provider("hf-cooldown")


# ──────────────────────────────────────────────────────────────────────────
# EventBus payload
# ──────────────────────────────────────────────────────────────────────────


def test_routing_decided_event_payload_includes_selector_name_when_bandit_active() -> None:
    """``ROUTING_DECIDED`` event payload's decision carries the active selector's name."""
    from primal_ai import Atlas, Conductor, Event, EventKind, ThompsonBandit

    Atlas.register_provider(_provider("ev-sel"))
    Atlas.set_selector(ThompsonBandit(seed=1))
    seen: list[Event] = []
    sub = Conductor.event_bus.subscribe(EventKind.ROUTING_DECIDED, seen.append)
    try:
        Atlas.route("x", candidates=["ev-sel"])
        assert len(seen) == 1
        assert seen[0].payload["decision"].get("selector_name") == "thompson"
    finally:
        Conductor.event_bus.unsubscribe(sub)
        Atlas.set_selector(None)
        Atlas.unregister_provider("ev-sel")


# ──────────────────────────────────────────────────────────────────────────
# Imports smoke
# ──────────────────────────────────────────────────────────────────────────


def test_all_public_bandit_exports_import() -> None:
    """All documented bandit-related exports import from ``primal_ai``."""
    from primal_ai import (
        ArmState,
        Bandit,
        BanditOutcome,
        ThompsonBandit,
        UCB1Bandit,
        register_selector,
    )

    assert all(
        x is not None
        for x in [
            ArmState,
            Bandit,
            BanditOutcome,
            ThompsonBandit,
            UCB1Bandit,
            register_selector,
        ]
    )
