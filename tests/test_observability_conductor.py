"""OTel span tests for the Conductor pillar."""

from __future__ import annotations

from typing import Any


def test_delegate_success_emits_span_with_attrs(otel_exporter: object) -> None:
    from primal_ai.conductor import AgentCard, Capability, Conductor

    class Echo:
        name = "echo_obs"
        card = AgentCard(
            name="echo_obs",
            description="echo agent",
            capabilities=(Capability(name="echo_obs", description="echo back"),),
        )

        def invoke(self, input: Any) -> Any:
            return {"echoed": input}

    Conductor.register_agent(Echo())
    try:
        result = Conductor.delegate("task", capability="echo_obs", input="hi")
    finally:
        Conductor.unregister_agent("echo_obs")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    delegate = next(
        (s for s in spans if s.name == "primal.conductor.delegate"), None,
    )
    assert delegate is not None
    assert delegate.attributes["primal.conductor.to_agent"] == "echo_obs"
    assert delegate.attributes["primal.conductor.capability"] == "echo_obs"
    assert delegate.attributes["primal.conductor.status"] == "SUCCESS"
    assert result.status.value == "SUCCESS"


def test_delegate_refused_records_reason(otel_exporter: object) -> None:
    from primal_ai.conductor import Conductor

    Conductor.delegate("task", capability="nonexistent_cap_xyz", input="x")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    delegate = next(
        (s for s in spans if s.name == "primal.conductor.delegate"), None,
    )
    assert delegate is not None
    assert delegate.attributes["primal.conductor.status"] == "REFUSED"
    assert "no agent advertises capability" in delegate.attributes[
        "primal.conductor.reason"
    ]


def test_delegate_span_is_child_of_active_trajectory(otel_exporter: object) -> None:
    from primal_ai.conductor import AgentCard, Capability, Conductor
    from primal_ai.trajectory import Trajectory

    class Echo:
        name = "echo_obs_tr"
        card = AgentCard(
            name="echo_obs_tr",
            description="echo",
            capabilities=(Capability(name="echo_obs_tr", description="..."),),
        )

        def invoke(self, input: Any) -> Any:
            return {"out": input}

    Conductor.register_agent(Echo())
    try:
        with Trajectory.record():
            Conductor.delegate("task", capability="echo_obs_tr", input="y")
    finally:
        Conductor.unregister_agent("echo_obs_tr")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    by_name = {s.name: s for s in spans}
    session = by_name["primal.trajectory.session"]
    delegate = by_name["primal.conductor.delegate"]
    assert delegate.parent is not None
    assert delegate.parent.span_id == session.context.span_id
