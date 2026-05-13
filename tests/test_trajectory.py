"""Trajectory MVP — context-manager recording, step kinds, replay, persistence, Guardian handoff.

These tests are the contract for the Phase 1 Trajectory: a stdlib-only,
JSON-round-trippable recorder for agent executions.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────────
# Context manager
# ──────────────────────────────────────────────────────────────────────────


def test_record_returns_context_manageable_trajectory() -> None:
    """``Trajectory.record()`` returns a ``Trajectory`` instance that works as a context manager."""
    from primal_ai import Trajectory, TrajectoryStatus

    tr = Trajectory.record(agent_id="test")
    assert isinstance(tr, Trajectory)
    with tr as inner:
        assert inner is tr
        assert inner.status == TrajectoryStatus.RUNNING


def test_status_is_success_on_clean_exit() -> None:
    """Exiting the context manager without an exception flips status to SUCCESS."""
    from primal_ai import Trajectory, TrajectoryStatus

    with Trajectory.record() as tr:
        pass
    assert tr.status == TrajectoryStatus.SUCCESS


def test_status_is_failed_on_exception_and_error_step_recorded() -> None:
    """An exception inside the ``with`` flips status to FAILED and records an ERROR step."""
    from primal_ai import StepKind, Trajectory, TrajectoryStatus

    with pytest.raises(ValueError), Trajectory.record() as tr:
        raise ValueError("boom")
    assert tr.status == TrajectoryStatus.FAILED
    errors = tr.find_steps(kind=StepKind.ERROR)
    assert len(errors) == 1
    assert "ValueError" in errors[0].data["type"]
    assert "boom" in errors[0].data["message"]


# ──────────────────────────────────────────────────────────────────────────
# add_step + record helpers
# ──────────────────────────────────────────────────────────────────────────


def test_add_step_appends_step_in_order() -> None:
    """``add_step`` appends a ``Step`` and preserves declared order."""
    from primal_ai import Step, StepKind, Trajectory

    with Trajectory.record() as tr:
        tr.add_step(Step(kind=StepKind.INPUT.value, data={"q": "a"}))
        tr.add_step(Step(kind=StepKind.OUTPUT.value, data={"a": 1}))
    steps = list(tr.replay())
    assert [s.kind for s in steps] == [StepKind.INPUT.value, StepKind.OUTPUT.value]


def test_add_step_accepts_dict_and_coerces() -> None:
    """``add_step`` accepts a dict payload and coerces it to a ``Step``."""
    from primal_ai import Step, StepKind, Trajectory

    with Trajectory.record() as tr:
        tr.add_step({"kind": StepKind.INPUT.value, "data": {"q": "hello"}})
    steps = list(tr.replay())
    assert len(steps) == 1
    assert isinstance(steps[0], Step)
    assert steps[0].kind == StepKind.INPUT.value
    assert steps[0].data == {"q": "hello"}


def test_record_input_builds_input_step() -> None:
    """``record_input`` is a thin wrapper that produces an INPUT step."""
    from primal_ai import StepKind, Trajectory

    with Trajectory.record() as tr:
        tr.record_input({"query": "flights"})
    steps = tr.find_steps(kind=StepKind.INPUT)
    assert len(steps) == 1
    assert steps[0].data == {"query": "flights"}


def test_record_tool_call_and_result_link_via_parent_step_id() -> None:
    """A TOOL_RESULT step's ``parent_step_id`` is the originating TOOL_CALL's ``step_id``."""
    from primal_ai import StepKind, Trajectory

    with Trajectory.record() as tr:
        call = tr.record_tool_call("search", {"q": "flights"})
        result = tr.record_tool_result(call.step_id, {"hits": 3}, cost=0.02)
    assert result.parent_step_id == call.step_id
    assert result.cost == pytest.approx(0.02)
    assert tr.find_steps(kind=StepKind.TOOL_CALL)[0].data["tool_name"] == "search"


def test_record_llm_call_and_result_link_and_capture_cost_and_tokens() -> None:
    """LLM_RESULT links back to LLM_CALL and captures cost + tokens."""
    from primal_ai import StepKind, Trajectory

    with Trajectory.record() as tr:
        call = tr.record_llm_call("claude-opus-4-7", [{"role": "user", "content": "hi"}])
        result = tr.record_llm_result(
            call.step_id,
            response={"role": "assistant", "content": "hello"},
            cost=0.0015,
            tokens={"input": 5, "output": 3},
        )
    assert result.parent_step_id == call.step_id
    assert result.cost == pytest.approx(0.0015)
    assert result.data["tokens"] == {"input": 5, "output": 3}
    assert tr.find_steps(kind=StepKind.LLM_CALL)[0].data["model"] == "claude-opus-4-7"


def test_record_error_captures_type_message_traceback() -> None:
    """``record_error`` captures exception type, message, and traceback string."""
    from primal_ai import StepKind, Trajectory

    tr = Trajectory.record()
    try:
        raise RuntimeError("kaboom")
    except RuntimeError as exc:
        tr.record_error(exc)
    errors = tr.find_steps(kind=StepKind.ERROR)
    assert len(errors) == 1
    assert errors[0].data["type"] == "RuntimeError"
    assert "kaboom" in errors[0].data["message"]
    assert "RuntimeError" in errors[0].data["traceback"]


def test_record_output_builds_output_step() -> None:
    """``record_output`` produces an OUTPUT step."""
    from primal_ai import StepKind, Trajectory

    with Trajectory.record() as tr:
        tr.record_output({"answer": "tokyo"})
    outs = tr.find_steps(kind=StepKind.OUTPUT)
    assert len(outs) == 1
    assert outs[0].data == {"answer": "tokyo"}


# ──────────────────────────────────────────────────────────────────────────
# summary / serialization
# ──────────────────────────────────────────────────────────────────────────


def test_summary_returns_documented_schema_with_counts() -> None:
    """``summary()`` returns the documented keys including ``step_kinds`` counts."""
    from primal_ai import StepKind, Trajectory

    with Trajectory.record(agent_id="search") as tr:
        tr.record_input({"q": "x"})
        call = tr.record_tool_call("search", {"q": "x"})
        tr.record_tool_result(call.step_id, {"r": 1})
        tr.record_output({"answer": 1})

    s = tr.summary()
    assert s["agent_id"] == "search"
    assert s["status"] == "SUCCESS"
    assert s["step_count"] == 4
    assert s["step_kinds"][StepKind.INPUT.value] == 1
    assert s["step_kinds"][StepKind.TOOL_CALL.value] == 1
    assert s["step_kinds"][StepKind.TOOL_RESULT.value] == 1
    assert s["step_kinds"][StepKind.OUTPUT.value] == 1
    assert s["duration_ms"] is not None and s["duration_ms"] >= 0
    assert "trajectory_id" in s


def test_summary_aggregates_total_cost() -> None:
    """``summary['total_cost']`` is the sum of every step's ``cost`` (None costs skipped)."""
    from primal_ai import Trajectory

    with Trajectory.record() as tr:
        call1 = tr.record_tool_call("a", {})
        tr.record_tool_result(call1.step_id, {}, cost=0.10)
        call2 = tr.record_tool_call("b", {})
        tr.record_tool_result(call2.step_id, {}, cost=0.25)
    assert tr.summary()["total_cost"] == pytest.approx(0.35)


def test_to_dict_is_json_serializable() -> None:
    """``to_dict()`` round-trips through ``json.dumps``."""
    from primal_ai import Trajectory

    with Trajectory.record(agent_id="x") as tr:
        tr.record_input({"q": "y"})
        tr.record_output({"a": 1})
    blob = json.dumps(tr.to_dict())
    parsed = json.loads(blob)
    assert parsed["agent_id"] == "x"
    assert len(parsed["steps"]) == 2


def test_from_dict_rehydrates_full_trajectory() -> None:
    """``from_dict`` rebuilds a trajectory equal to the original by ID and steps."""
    from primal_ai import Trajectory

    with Trajectory.record(agent_id="agent-1") as tr:
        tr.record_input({"q": "z"})
        call = tr.record_tool_call("search", {"q": "z"})
        tr.record_tool_result(call.step_id, {"hits": 0}, cost=0.01)

    payload = tr.to_dict()
    restored = Trajectory.from_dict(payload)
    assert restored.trajectory_id == tr.trajectory_id
    assert restored.agent_id == tr.agent_id
    assert restored.status == tr.status
    assert [s.step_id for s in restored.replay()] == [s.step_id for s in tr.replay()]


# ──────────────────────────────────────────────────────────────────────────
# replay / filter
# ──────────────────────────────────────────────────────────────────────────


def test_replay_yields_steps_in_insertion_order() -> None:
    """``replay()`` is an iterator over all steps in the order they were added."""
    from primal_ai import StepKind, Trajectory

    with Trajectory.record() as tr:
        tr.record_input({"i": 0})
        tr.record_input({"i": 1})
        tr.record_input({"i": 2})
    indices = [s.data["i"] for s in tr.replay()]
    assert indices == [0, 1, 2]
    # Type sanity — all are the right kind.
    assert {s.kind for s in tr.replay()} == {StepKind.INPUT.value}


def test_find_steps_filters_by_kind() -> None:
    """``find_steps(kind=...)`` returns only steps of that kind."""
    from primal_ai import StepKind, Trajectory

    with Trajectory.record() as tr:
        tr.record_input({"q": "x"})
        call = tr.record_tool_call("a", {})
        tr.record_tool_result(call.step_id, {})
        tr.record_output({"a": 1})

    assert len(tr.find_steps(kind=StepKind.TOOL_CALL)) == 1
    assert len(tr.find_steps(kind=StepKind.INPUT)) == 1


def test_find_steps_filters_by_predicate() -> None:
    """``find_steps(predicate=...)`` returns only steps matching the predicate."""
    from primal_ai import Step, Trajectory

    with Trajectory.record() as tr:
        call = tr.record_tool_call("a", {})
        tr.record_tool_result(call.step_id, {}, cost=0.02)
        call2 = tr.record_tool_call("b", {})
        tr.record_tool_result(call2.step_id, {}, cost=0.10)

    expensive = tr.find_steps(predicate=lambda s: s.cost is not None and s.cost > 0.05)
    assert len(expensive) == 1
    assert isinstance(expensive[0], Step)
    assert expensive[0].cost == pytest.approx(0.10)


# ──────────────────────────────────────────────────────────────────────────
# Persistence
# ──────────────────────────────────────────────────────────────────────────


def test_save_and_load_round_trip_through_storage() -> None:
    """``save(store)`` persists; ``Trajectory.load(id, store)`` restores."""
    from primal_ai import Trajectory
    from primal_ai.storage import InMemoryStorage

    store = InMemoryStorage()
    with Trajectory.record(agent_id="persist") as tr:
        tr.record_input({"q": "hi"})

    tr.save(store)
    restored = Trajectory.load(tr.trajectory_id, store)
    assert restored.agent_id == "persist"
    assert len(list(restored.replay())) == 1


def test_set_default_store_auto_saves_on_context_exit() -> None:
    """With a default store set, exiting the context auto-persists the trajectory."""
    from primal_ai import Trajectory, set_default_store
    from primal_ai.storage import InMemoryStorage

    store = InMemoryStorage()
    set_default_store(store)
    try:
        with Trajectory.record(agent_id="auto") as tr:
            tr.record_input({"q": "hi"})
    finally:
        set_default_store(None)

    restored = Trajectory.load(tr.trajectory_id, store)
    assert restored.agent_id == "auto"


def test_set_default_store_none_disables_auto_save() -> None:
    """``set_default_store(None)`` ensures no auto-save happens."""
    from primal_ai import Trajectory, set_default_store
    from primal_ai.storage import InMemoryStorage

    store = InMemoryStorage()
    set_default_store(None)
    with Trajectory.record(agent_id="no-auto") as tr:
        tr.record_input({"q": "x"})
    # Nothing should have been written for this trajectory.
    assert store.get(f"trajectory:{tr.trajectory_id}") is None


def test_auto_save_is_thread_safe_under_concurrent_trajectories() -> None:
    """Concurrent trajectories each persist exactly one record without corruption."""
    from primal_ai import Trajectory, set_default_store
    from primal_ai.storage import InMemoryStorage

    store = InMemoryStorage()
    set_default_store(store)

    ids: list[str] = []
    lock = threading.Lock()

    def runner() -> None:
        with Trajectory.record() as tr:
            tr.record_input({"thread": True})
        with lock:
            ids.append(tr.trajectory_id)

    threads = [threading.Thread(target=runner) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    set_default_store(None)

    assert len(ids) == 8
    for tid in ids:
        restored = Trajectory.load(tid, store)
        assert restored.trajectory_id == tid


# ──────────────────────────────────────────────────────────────────────────
# IDs and linkage
# ──────────────────────────────────────────────────────────────────────────


def test_trajectory_ids_are_unique_across_instances() -> None:
    """Two simultaneously-created trajectories have different ``trajectory_id``s."""
    from primal_ai import Trajectory

    a = Trajectory.record()
    b = Trajectory.record()
    assert a.trajectory_id != b.trajectory_id


def test_parent_trajectory_id_links_nested_trajectories() -> None:
    """``parent_trajectory_id`` records a child→parent link."""
    from primal_ai import Trajectory

    parent = Trajectory.record(agent_id="parent")
    child = Trajectory.record(agent_id="child", parent_trajectory_id=parent.trajectory_id)
    assert child.parent_trajectory_id == parent.trajectory_id
    assert child.to_dict()["parent_trajectory_id"] == parent.trajectory_id


def test_step_has_both_wallclock_and_monotonic_timestamps() -> None:
    """Each ``Step`` carries ``timestamp`` (wall) and ``monotonic`` (perf) at creation."""
    from primal_ai import Step, StepKind

    s = Step(kind=StepKind.INPUT.value, data={})
    assert isinstance(s.timestamp, float)
    assert isinstance(s.monotonic, float)


def test_step_ids_unique_within_trajectory() -> None:
    """Every step gets a unique ``step_id`` (uuid4 hex)."""
    from primal_ai import Trajectory

    with Trajectory.record() as tr:
        for i in range(10):
            tr.record_input({"i": i})
    ids = [s.step_id for s in tr.replay()]
    assert len(set(ids)) == len(ids)


# ──────────────────────────────────────────────────────────────────────────
# Guardian integration
# ──────────────────────────────────────────────────────────────────────────


def test_guardian_escalate_with_trajectory_adds_policy_violation_step() -> None:
    """``Guardian.escalate(trajectory)`` records a POLICY_VIOLATION step on the trajectory."""
    from primal_ai import Guardian, StepKind, Trajectory

    seen: list[Any] = []
    Guardian.set_escalation_handler(seen.append)
    try:
        tr = Trajectory.record()
        Guardian.escalate(tr)
    finally:
        Guardian.set_escalation_handler(None)

    violations = tr.find_steps(kind=StepKind.POLICY_VIOLATION)
    assert len(violations) == 1
    assert seen == [tr]


def test_guardian_escalate_with_bare_violation_still_works() -> None:
    """Session-2 compatibility: a bare ``PolicyViolation`` flows to the handler unchanged."""
    from primal_ai import Guardian, PolicyViolation

    seen: list[Any] = []
    Guardian.set_escalation_handler(seen.append)
    try:
        v = PolicyViolation(policy_name="x", reason="r", phase="pre", context={})
        Guardian.escalate(v)
    finally:
        Guardian.set_escalation_handler(None)
    assert len(seen) == 1
    assert seen[0] is v


def test_custom_kind_strings_are_accepted_and_round_trip() -> None:
    """A custom ``kind`` string (not in ``StepKind``) round-trips through to/from_dict."""
    from primal_ai import Step, Trajectory

    with Trajectory.record() as tr:
        tr.add_step(Step(kind="CUSTOM_AUDIT", data={"ok": True}))

    restored = Trajectory.from_dict(tr.to_dict())
    customs = restored.find_steps(kind="CUSTOM_AUDIT")
    assert len(customs) == 1
    assert customs[0].data == {"ok": True}
