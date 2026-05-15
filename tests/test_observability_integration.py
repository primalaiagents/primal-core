"""End-to-end OTel integration test across all five pillars."""

from __future__ import annotations

from typing import Any


def test_all_pillars_emit_children_of_trajectory_session(
    otel_exporter: object,
) -> None:
    from primal_ai.atlas import Atlas, BYOProvider, ProviderInfo
    from primal_ai.conductor import AgentCard, Capability, Conductor
    from primal_ai.guardian import Guardian
    from primal_ai.trajectory import Trajectory
    from primal_ai.verifier import RuleBasedVerifier, Verifier

    Atlas.register_provider(
        BYOProvider(
            name="p1_int",
            call=lambda task, **kw: f"ok:{task}",  # noqa: ARG005
            info=ProviderInfo(name="p1_int", capabilities=("chat",)),
        ),
    )

    class Echo:
        name = "echo_int"
        card = AgentCard(
            name="echo_int",
            description="echo",
            capabilities=(Capability(name="chat", description="..."),),
        )

        def invoke(self, input: Any) -> Any:
            return {"out": input}

    Conductor.register_agent(Echo())

    def has_answer(out: Any) -> tuple[str, str]:
        return ("pass", "ok") if "answer" in out else ("fail", "missing")

    def agent_fn(q: str) -> str:
        Conductor.delegate("sub", capability="chat", input=q)
        Atlas.route(q)
        Verifier.audit(
            {"answer": "ok"},
            layers=[RuleBasedVerifier(rules=[has_answer])],
        )
        return q

    wrapped = Guardian.wrap(agent_fn)

    try:
        with Trajectory.record():
            wrapped("hi")
    finally:
        Atlas.unregister_provider("p1_int")
        Conductor.unregister_agent("echo_int")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    by_name = {s.name: s for s in spans}
    session = by_name["primal.trajectory.session"]
    guardian_invoke = by_name["primal.guardian.invoke"]

    # Guardian's invoke is the only direct child of the trajectory session,
    # because the wrapped agent does everything else inside Guardian's span.
    direct_children = {
        s.name
        for s in spans
        if s.parent is not None and s.parent.span_id == session.context.span_id
    }
    assert "primal.guardian.invoke" in direct_children

    # Conductor / Atlas / Verifier all run inside the wrapped agent, so they
    # become children of the Guardian span via OTel context propagation —
    # no manual context plumbing.
    guardian_children = {
        s.name
        for s in spans
        if s.parent is not None
        and s.parent.span_id == guardian_invoke.context.span_id
    }
    assert "primal.conductor.delegate" in guardian_children
    assert "primal.atlas.route" in guardian_children
    assert "primal.verifier.audit" in guardian_children
