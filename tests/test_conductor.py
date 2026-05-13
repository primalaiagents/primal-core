"""Conductor MVP — agent registry, capability-based delegation, pipelines, event bus.

Contract for Phase 1 Conductor: a stdlib-only orchestration layer that records
inter-agent handoffs into the active Trajectory and exposes an AgentCard shape
ready to map to A2A v1.0 in Phase 2.5.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────────
# Capability + AgentCard
# ──────────────────────────────────────────────────────────────────────────


def test_capability_constructs_and_round_trips() -> None:
    """``Capability`` constructs with required fields and round-trips through to/from_dict."""
    from primal_ai import Capability

    cap = Capability(
        name="summarize",
        description="Summarize a text input",
        tags=("writing", "nlp"),
    )
    restored = Capability.from_dict(cap.to_dict())
    assert restored.name == "summarize"
    assert restored.tags == ("writing", "nlp")


def test_agent_card_constructs_with_capabilities_and_round_trips() -> None:
    """``AgentCard`` carries a tuple of ``Capability`` objects and round-trips via JSON."""
    from primal_ai import AgentCard, Capability

    card = AgentCard(
        name="researcher",
        description="A research-specialized agent",
        capabilities=(Capability(name="summarize", description="..."),),
        version="0.1.0",
        metadata={"model": "fake-1"},
    )
    blob = json.dumps(card.to_dict())
    restored = AgentCard.from_dict(json.loads(blob))
    assert restored.name == "researcher"
    assert len(restored.capabilities) == 1
    assert restored.capabilities[0].name == "summarize"
    assert restored.metadata == {"model": "fake-1"}


# ──────────────────────────────────────────────────────────────────────────
# Agent Protocol
# ──────────────────────────────────────────────────────────────────────────


def test_agent_protocol_satisfied_by_minimal_class() -> None:
    """A class with ``name``, ``card``, and ``invoke`` satisfies the ``Agent`` Protocol."""
    from primal_ai import Agent, AgentCard, Capability

    class Minimal:
        name = "minimal"
        card = AgentCard(
            name="minimal",
            description="x",
            capabilities=(Capability(name="echo", description="echoes input"),),
        )

        def invoke(self, input: Any) -> Any:
            return input

    instance: Agent = Minimal()
    assert isinstance(instance, Agent)


def test_agent_invoke_async_is_optional() -> None:
    """An agent without ``invoke_async`` still satisfies the Protocol — it's optional."""
    from primal_ai import Agent, AgentCard

    class NoAsync:
        name = "no_async"
        card = AgentCard(name="no_async", description="x", capabilities=())

        def invoke(self, input: Any) -> Any:
            return input

    assert isinstance(NoAsync(), Agent)


# ──────────────────────────────────────────────────────────────────────────
# DelegationResult + DelegationStatus
# ──────────────────────────────────────────────────────────────────────────


def test_delegation_result_round_trips_via_json() -> None:
    """``DelegationResult`` is JSON-serializable through to_dict/from_dict."""
    from primal_ai import DelegationResult, DelegationStatus

    r = DelegationResult(
        delegation_id="abc",
        from_agent=None,
        to_agent="x",
        capability="echo",
        task="say hi",
        input={"q": "hi"},
        output={"a": "hi"},
        status=DelegationStatus.SUCCESS,
        reason=None,
        started_at=1.0,
        ended_at=2.0,
        duration_ms=1000.0,
    )
    restored = DelegationResult.from_dict(json.loads(json.dumps(r.to_dict())))
    assert restored.status == DelegationStatus.SUCCESS
    assert restored.duration_ms == pytest.approx(1000.0)


def test_delegation_status_is_strenum_and_json_serializes() -> None:
    """``DelegationStatus`` is a StrEnum — ``json.dumps`` handles it natively."""
    from primal_ai import DelegationStatus

    blob = json.dumps({"status": DelegationStatus.REFUSED})
    assert json.loads(blob) == {"status": "REFUSED"}


# ──────────────────────────────────────────────────────────────────────────
# EventBus
# ──────────────────────────────────────────────────────────────────────────


def test_event_bus_subscribe_and_publish_fires_matching_handler() -> None:
    """A handler subscribed to a specific kind receives matching events."""
    from primal_ai import Event, EventBus, EventKind

    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe(EventKind.DELEGATION_STARTED, seen.append)
    bus.publish(Event(kind=EventKind.DELEGATION_STARTED.value, payload={"k": 1}))
    assert len(seen) == 1
    assert seen[0].payload == {"k": 1}


def test_event_bus_wildcard_handler_receives_every_event() -> None:
    """A handler subscribed with ``kind=None`` is a wildcard — every publish fires it."""
    from primal_ai import Event, EventBus, EventKind

    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe(None, seen.append)
    bus.publish(Event(kind=EventKind.DELEGATION_STARTED.value, payload={}))
    bus.publish(Event(kind="CUSTOM_EVENT", payload={}))
    assert len(seen) == 2


def test_event_bus_unsubscribe_stops_delivery() -> None:
    """After ``unsubscribe``, a previously-subscribed handler no longer fires."""
    from primal_ai import Event, EventBus, EventKind

    bus = EventBus()
    seen: list[Event] = []
    sub_id = bus.subscribe(EventKind.DELEGATION_STARTED, seen.append)
    bus.unsubscribe(sub_id)
    bus.publish(Event(kind=EventKind.DELEGATION_STARTED.value, payload={}))
    assert seen == []


def test_event_bus_handler_exception_does_not_break_publisher_or_other_handlers() -> None:
    """A handler that raises is suppressed; subsequent handlers still fire."""
    from primal_ai import Event, EventBus, EventKind

    bus = EventBus()
    seen: list[Event] = []

    def bad(_event: Event) -> None:
        raise RuntimeError("boom")

    bus.subscribe(EventKind.DELEGATION_STARTED, bad)
    bus.subscribe(EventKind.DELEGATION_STARTED, seen.append)
    bus.publish(Event(kind=EventKind.DELEGATION_STARTED.value, payload={}))
    # The publisher didn't raise AND the second handler still saw the event.
    assert len(seen) == 1


def test_event_bus_is_threadsafe_under_concurrent_publish_and_subscribe() -> None:
    """Many threads publishing + subscribing concurrently produces a coherent count."""
    from primal_ai import Event, EventBus

    bus = EventBus()
    seen: list[Event] = []
    lock = threading.Lock()

    def safe_append(event: Event) -> None:
        with lock:
            seen.append(event)

    bus.subscribe(None, safe_append)

    def publisher(n: int) -> None:
        for i in range(n):
            bus.publish(Event(kind="x", payload={"i": i}))

    threads = [threading.Thread(target=publisher, args=(20,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(seen) == 4 * 20


# ──────────────────────────────────────────────────────────────────────────
# Conductor registry
# ──────────────────────────────────────────────────────────────────────────


def _fake_agent(
    name: str,
    *,
    capability: str = "echo",
    tags: tuple[str, ...] = (),
    fn: Any = None,
) -> Any:
    """Build a minimal Agent for tests. ``fn`` overrides the default echo behavior."""
    from primal_ai import AgentCard, Capability

    class _Fake:
        def __init__(self) -> None:
            self.name = name
            self.card = AgentCard(
                name=name,
                description=f"fake agent {name}",
                capabilities=(
                    Capability(name=capability, description="...", tags=tags),
                ),
            )

        def invoke(self, input: Any) -> Any:
            if fn is not None:
                return fn(input)
            return {"echo": input}

    return _Fake()


def test_register_agent_adds_to_default_registry_and_duplicate_raises() -> None:
    """``Conductor.register_agent`` adds by name; registering twice raises ``ValueError``."""
    from primal_ai import Conductor

    agent = _fake_agent("alpha-reg")
    Conductor.register_agent(agent)
    try:
        with pytest.raises(ValueError):
            Conductor.register_agent(agent)
    finally:
        Conductor.unregister_agent("alpha-reg")


def test_unregister_agent_removes_and_noop_on_missing() -> None:
    """``unregister_agent`` removes; calling it on a missing name is a no-op."""
    from primal_ai import Conductor

    Conductor.register_agent(_fake_agent("beta-reg"))
    Conductor.unregister_agent("beta-reg")
    Conductor.unregister_agent("beta-reg")  # second call is silently a no-op
    assert all(c.name != "beta-reg" for c in Conductor.list_agents())


def test_list_agents_returns_cards_for_registered_agents() -> None:
    """``Conductor.list_agents`` returns the card of every registered agent."""
    from primal_ai import Conductor

    Conductor.register_agent(_fake_agent("listed-1"))
    try:
        names = {c.name for c in Conductor.list_agents()}
        assert "listed-1" in names
    finally:
        Conductor.unregister_agent("listed-1")


def test_find_by_capability_returns_matching_agents() -> None:
    """``Conductor.find(capability=X)`` returns cards whose capabilities include ``X``."""
    from primal_ai import Conductor

    Conductor.register_agent(_fake_agent("findcap-1", capability="search"))
    Conductor.register_agent(_fake_agent("findcap-2", capability="other"))
    try:
        cards = Conductor.find(capability="search")
        names = {c.name for c in cards}
        assert "findcap-1" in names
        assert "findcap-2" not in names
    finally:
        Conductor.unregister_agent("findcap-1")
        Conductor.unregister_agent("findcap-2")


def test_find_by_tag_returns_matching_agents() -> None:
    """``Conductor.find(tag=X)`` returns cards whose capability tags include ``X``."""
    from primal_ai import Conductor

    Conductor.register_agent(_fake_agent("findtag-1", tags=("legal",)))
    Conductor.register_agent(_fake_agent("findtag-2", tags=("medical",)))
    try:
        cards = Conductor.find(tag="legal")
        names = {c.name for c in cards}
        assert "findtag-1" in names
        assert "findtag-2" not in names
    finally:
        Conductor.unregister_agent("findtag-1")
        Conductor.unregister_agent("findtag-2")


# ──────────────────────────────────────────────────────────────────────────
# Conductor.delegate
# ──────────────────────────────────────────────────────────────────────────


def test_delegate_with_explicit_agents_returns_success_result() -> None:
    """``delegate(task, agents=[a])`` invokes ``a`` and returns a SUCCESS result."""
    from primal_ai import Conductor, DelegationStatus

    agent = _fake_agent("delegate-success")
    result = Conductor.delegate("say hi", agents=[agent], input={"q": "hi"})
    assert result.status == DelegationStatus.SUCCESS
    assert result.to_agent == "delegate-success"
    assert result.output == {"echo": {"q": "hi"}}


def test_delegate_returns_failed_result_when_agent_raises() -> None:
    """A raising agent produces a FAILED result rather than propagating the exception."""
    from primal_ai import Conductor, DelegationStatus

    def broken(_input: Any) -> Any:
        raise RuntimeError("intentional")

    agent = _fake_agent("delegate-broken", fn=broken)
    result = Conductor.delegate("anything", agents=[agent])
    assert result.status == DelegationStatus.FAILED
    assert result.reason is not None
    assert "intentional" in result.reason


def test_delegate_with_capability_finds_agent_from_default_registry() -> None:
    """``delegate(task, capability=X)`` resolves an agent from the default registry."""
    from primal_ai import Conductor, DelegationStatus

    agent = _fake_agent("delegate-cap", capability="translate")
    Conductor.register_agent(agent)
    try:
        result = Conductor.delegate("translate hi", capability="translate", input="hi")
        assert result.status == DelegationStatus.SUCCESS
        assert result.to_agent == "delegate-cap"
    finally:
        Conductor.unregister_agent("delegate-cap")


def test_delegate_returns_refused_when_no_agent_matches_capability() -> None:
    """No matching agent for the requested capability → REFUSED."""
    from primal_ai import Conductor, DelegationStatus

    result = Conductor.delegate(
        "imaginary task",
        capability="__definitely_not_a_real_capability__",
    )
    assert result.status == DelegationStatus.REFUSED


def test_delegate_returns_timeout_for_slow_agent() -> None:
    """A blown ``timeout_seconds`` budget yields a TIMEOUT result."""
    from primal_ai import Conductor, DelegationStatus

    def slow(_input: Any) -> Any:
        time.sleep(0.5)
        return "done"

    agent = _fake_agent("delegate-slow", fn=slow)
    result = Conductor.delegate(
        "wait",
        agents=[agent],
        timeout_seconds=0.05,
    )
    assert result.status == DelegationStatus.TIMEOUT


def test_delegate_emits_started_and_completed_events_on_success() -> None:
    """STARTED and COMPLETED events both fire on a successful delegation."""
    from primal_ai import Conductor, Event, EventKind

    seen: list[Event] = []
    sub_id = Conductor.event_bus.subscribe(None, seen.append)
    try:
        agent = _fake_agent("delegate-events")
        Conductor.delegate("hi", agents=[agent])
        kinds = [e.kind for e in seen]
        assert EventKind.DELEGATION_STARTED.value in kinds
        assert EventKind.DELEGATION_COMPLETED.value in kinds
    finally:
        Conductor.event_bus.unsubscribe(sub_id)


def test_delegate_emits_failed_event_when_agent_raises() -> None:
    """A failing delegation emits ``DELEGATION_FAILED`` instead of ``DELEGATION_COMPLETED``."""
    from primal_ai import Conductor, Event, EventKind

    def broken(_input: Any) -> Any:
        raise RuntimeError("nope")

    seen: list[Event] = []
    sub_id = Conductor.event_bus.subscribe(None, seen.append)
    try:
        Conductor.delegate("x", agents=[_fake_agent("delegate-fail-event", fn=broken)])
        kinds = [e.kind for e in seen]
        assert EventKind.DELEGATION_FAILED.value in kinds
        assert EventKind.DELEGATION_COMPLETED.value not in kinds
    finally:
        Conductor.event_bus.unsubscribe(sub_id)


# ──────────────────────────────────────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────────────────────────────────────


def test_pipeline_runs_steps_in_order_threading_outputs() -> None:
    """A ``Pipeline`` runs each step in order, feeding the prior output forward."""
    from primal_ai import Conductor, Pipeline, PipelineStep

    a = _fake_agent("pl-a", fn=lambda input: {"after_a": input})
    b = _fake_agent("pl-b", fn=lambda input: {"after_b": input})
    Conductor.register_agent(a)
    Conductor.register_agent(b)
    try:
        pipeline = Pipeline(
            name="abp",
            steps=[
                PipelineStep(name="step-a", agent_name="pl-a"),
                PipelineStep(name="step-b", agent_name="pl-b"),
            ],
        )
        result = pipeline.run({"start": True})
        assert result["step-a"] == {"after_a": {"start": True}}
        assert result["step-b"] == {"after_b": {"after_a": {"start": True}}}
        assert result["_final"] == result["step-b"]
    finally:
        Conductor.unregister_agent("pl-a")
        Conductor.unregister_agent("pl-b")


def test_pipeline_input_transform_is_applied_between_steps() -> None:
    """A ``PipelineStep.input_transform`` rewrites the prior output before the next step."""
    from primal_ai import Conductor, Pipeline, PipelineStep

    a = _fake_agent("plt-a", fn=lambda input: {"value": input + 1})
    b = _fake_agent("plt-b", fn=lambda input: {"doubled": input * 2})
    Conductor.register_agent(a)
    Conductor.register_agent(b)
    try:
        pipeline = Pipeline(
            name="abp",
            steps=[
                PipelineStep(name="step-a", agent_name="plt-a"),
                PipelineStep(
                    name="step-b",
                    agent_name="plt-b",
                    input_transform=lambda prev: prev["value"],
                ),
            ],
        )
        result = pipeline.run(10)
        # step-a → {"value": 11}; transform extracts 11; step-b doubles → {"doubled": 22}
        assert result["_final"] == {"doubled": 22}
    finally:
        Conductor.unregister_agent("plt-a")
        Conductor.unregister_agent("plt-b")


def test_pipeline_halts_on_failed_step_and_returns_partial_results() -> None:
    """A failed step halts the pipeline; partial outputs remain in the result."""
    from primal_ai import Conductor, Pipeline, PipelineStep

    def broken(_input: Any) -> Any:
        raise RuntimeError("nope")

    a = _fake_agent("plh-a", fn=lambda input: {"ok": True})
    b = _fake_agent("plh-b", fn=broken)
    Conductor.register_agent(a)
    Conductor.register_agent(b)
    try:
        pipeline = Pipeline(
            name="halt-test",
            steps=[
                PipelineStep(name="step-a", agent_name="plh-a"),
                PipelineStep(name="step-b", agent_name="plh-b"),
            ],
        )
        result = pipeline.run("start")
        assert "step-a" in result
        assert result["_failed"] == "step-b"
        assert result["_final"] is None
    finally:
        Conductor.unregister_agent("plh-a")
        Conductor.unregister_agent("plh-b")


def test_pipeline_emits_lifecycle_events_on_success() -> None:
    """A successful pipeline emits STARTED / STEP_COMPLETED (× steps) / COMPLETED."""
    from primal_ai import Conductor, Event, EventKind, Pipeline, PipelineStep

    a = _fake_agent("ple-a", fn=lambda i: {"r": 1})
    b = _fake_agent("ple-b", fn=lambda i: {"r": 2})
    Conductor.register_agent(a)
    Conductor.register_agent(b)

    seen: list[Event] = []
    sub_id = Conductor.event_bus.subscribe(None, seen.append)
    try:
        Pipeline(
            name="events-pipeline",
            steps=[
                PipelineStep(name="s1", agent_name="ple-a"),
                PipelineStep(name="s2", agent_name="ple-b"),
            ],
        ).run("x")
        kinds = [e.kind for e in seen]
        assert EventKind.PIPELINE_STARTED.value in kinds
        assert kinds.count(EventKind.PIPELINE_STEP_COMPLETED.value) == 2
        assert EventKind.PIPELINE_COMPLETED.value in kinds
    finally:
        Conductor.event_bus.unsubscribe(sub_id)
        Conductor.unregister_agent("ple-a")
        Conductor.unregister_agent("ple-b")


def test_pipeline_emits_failed_event_on_failure() -> None:
    """A failing pipeline emits ``PIPELINE_FAILED``."""
    from primal_ai import Conductor, Event, EventKind, Pipeline, PipelineStep

    def broken(_input: Any) -> Any:
        raise RuntimeError("nope")

    Conductor.register_agent(_fake_agent("plf-a", fn=broken))
    seen: list[Event] = []
    sub_id = Conductor.event_bus.subscribe(None, seen.append)
    try:
        Pipeline(
            name="fail-pipeline",
            steps=[PipelineStep(name="s1", agent_name="plf-a")],
        ).run("x")
        kinds = [e.kind for e in seen]
        assert EventKind.PIPELINE_FAILED.value in kinds
    finally:
        Conductor.event_bus.unsubscribe(sub_id)
        Conductor.unregister_agent("plf-a")


# ──────────────────────────────────────────────────────────────────────────
# Trajectory integration
# ──────────────────────────────────────────────────────────────────────────


def test_delegate_inside_trajectory_records_agent_handoff() -> None:
    """A delegation inside ``Trajectory.record()`` appends an ``AGENT_HANDOFF`` step."""
    from primal_ai import Conductor, StepKind, Trajectory

    agent = _fake_agent("traj-handoff")
    with Trajectory.record(agent_id="caller") as tr:
        Conductor.delegate("hi", agents=[agent])

    handoffs = tr.find_steps(kind=StepKind.AGENT_HANDOFF)
    assert len(handoffs) == 1


def test_delegate_outside_trajectory_does_not_record() -> None:
    """Without an active trajectory in context, no step is appended (no crash)."""
    from primal_ai import Conductor

    agent = _fake_agent("no-traj")
    # No Trajectory.record(...) context — simply call.
    result = Conductor.delegate("hi", agents=[agent])
    assert result.status.value == "SUCCESS"  # smoke: still works, no error


def test_agent_handoff_step_carries_expected_fields() -> None:
    """Each handoff step records from_agent / to_agent / capability / status / task / duration."""
    from primal_ai import Conductor, StepKind, Trajectory

    agent = _fake_agent("handoff-fields", capability="translate")
    with Trajectory.record() as tr:
        Conductor.delegate("translate", agents=[agent], capability="translate")

    handoff = tr.find_steps(kind=StepKind.AGENT_HANDOFF)[0]
    data = handoff.data
    assert data["to_agent"] == "handoff-fields"
    assert data["capability"] == "translate"
    assert data["status"] == "SUCCESS"
    assert "task" in data
    assert isinstance(data["duration_ms"], (int, float))


def test_pipeline_records_one_handoff_per_step_inside_trajectory() -> None:
    """Each pipeline step records an ``AGENT_HANDOFF`` into the active trajectory."""
    from primal_ai import Conductor, Pipeline, PipelineStep, StepKind, Trajectory

    Conductor.register_agent(_fake_agent("pipe-h-a", fn=lambda i: {"r": 1}))
    Conductor.register_agent(_fake_agent("pipe-h-b", fn=lambda i: {"r": 2}))
    try:
        with Trajectory.record() as tr:
            Pipeline(
                name="p",
                steps=[
                    PipelineStep(name="s1", agent_name="pipe-h-a"),
                    PipelineStep(name="s2", agent_name="pipe-h-b"),
                ],
            ).run("x")
        handoffs = tr.find_steps(kind=StepKind.AGENT_HANDOFF)
        assert len(handoffs) == 2
    finally:
        Conductor.unregister_agent("pipe-h-a")
        Conductor.unregister_agent("pipe-h-b")


def test_capability_input_schema_is_used_to_validate_input() -> None:
    """``Capability.input_schema`` (when present) validates the input via the shared JSON Schema."""
    from primal_ai import AgentCard, Capability, Conductor, DelegationStatus

    class StrictAgent:
        name = "strict"
        card = AgentCard(
            name="strict",
            description="x",
            capabilities=(
                Capability(
                    name="strict_call",
                    description="needs string input",
                    input_schema={"type": "string"},
                ),
            ),
        )

        def invoke(self, input: Any) -> Any:
            return f"ok:{input}"

    # Wrong type — should refuse.
    result = Conductor.delegate(
        "test",
        agents=[StrictAgent()],
        capability="strict_call",
        input={"not": "a string"},
    )
    assert result.status == DelegationStatus.REFUSED
    # Right type — should succeed.
    ok = Conductor.delegate(
        "test",
        agents=[StrictAgent()],
        capability="strict_call",
        input="hello",
    )
    assert ok.status == DelegationStatus.SUCCESS


def test_concurrent_trajectories_in_threads_have_isolated_handoffs() -> None:
    """ContextVar isolation: two trajectories in two threads each see only their own handoffs."""
    from primal_ai import Conductor, StepKind, Trajectory

    Conductor.register_agent(_fake_agent("ctx-iso-a"))
    Conductor.register_agent(_fake_agent("ctx-iso-b"))
    captured: dict[str, list[int]] = {"a": [], "b": []}

    def run_a() -> None:
        with Trajectory.record() as tr:
            for _ in range(3):
                Conductor.delegate("x", agents=[Conductor.get_agent("ctx-iso-a")])
        captured["a"].append(len(tr.find_steps(kind=StepKind.AGENT_HANDOFF)))

    def run_b() -> None:
        with Trajectory.record() as tr:
            for _ in range(5):
                Conductor.delegate("x", agents=[Conductor.get_agent("ctx-iso-b")])
        captured["b"].append(len(tr.find_steps(kind=StepKind.AGENT_HANDOFF)))

    ta = threading.Thread(target=run_a)
    tb = threading.Thread(target=run_b)
    ta.start()
    tb.start()
    ta.join()
    tb.join()
    Conductor.unregister_agent("ctx-iso-a")
    Conductor.unregister_agent("ctx-iso-b")

    # Each trajectory sees exactly its own delegations.
    assert captured == {"a": [3], "b": [5]}


def test_set_active_trajectory_context_manager_scopes_recording() -> None:
    """``Conductor.set_active_trajectory(tr)`` is a context manager that scopes recording."""
    from primal_ai import Conductor, StepKind, Trajectory

    tr = Trajectory.record()
    agent = _fake_agent("set-active")
    # Outside the explicit scope — no recording.
    Conductor.delegate("x", agents=[agent])
    assert tr.find_steps(kind=StepKind.AGENT_HANDOFF) == []
    # Inside the explicit scope — recorded.
    with Conductor.set_active_trajectory(tr):
        Conductor.delegate("x", agents=[agent])
    assert len(tr.find_steps(kind=StepKind.AGENT_HANDOFF)) == 1


# ──────────────────────────────────────────────────────────────────────────
# Imports smoke
# ──────────────────────────────────────────────────────────────────────────


def test_all_public_conductor_exports_import() -> None:
    """All documented Conductor public exports are importable from ``primal_ai``."""
    from primal_ai import (
        Agent,
        AgentCard,
        Capability,
        Conductor,
        DelegationResult,
        DelegationStatus,
        Event,
        EventBus,
        EventKind,
        Pipeline,
        PipelineStep,
        register_agent,
        unregister_agent,
    )

    assert all(
        x is not None
        for x in [
            Agent,
            AgentCard,
            Capability,
            Conductor,
            DelegationResult,
            DelegationStatus,
            Event,
            EventBus,
            EventKind,
            Pipeline,
            PipelineStep,
            register_agent,
            unregister_agent,
        ]
    )
