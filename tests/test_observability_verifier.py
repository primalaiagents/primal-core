"""OTel span tests for the Verifier pillar."""

from __future__ import annotations

from typing import Any


def test_audit_emits_root_span_with_aggregate_attrs(otel_exporter: object) -> None:
    from primal_ai.verifier import RuleBasedVerifier, Verifier

    def has_answer(out: Any) -> tuple[str, str]:
        return ("pass", "ok") if "answer" in out else ("fail", "missing")

    Verifier.audit(
        {"answer": "ok"},
        layers=[RuleBasedVerifier(rules=[has_answer])],
    )

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    audit = next((s for s in spans if s.name == "primal.verifier.audit"), None)
    assert audit is not None
    assert audit.attributes["primal.verifier.status"] == "PASS"
    assert audit.attributes["primal.verifier.layer_count"] == 1


def test_audit_emits_child_span_per_layer(otel_exporter: object) -> None:
    from primal_ai.verifier import RuleBasedVerifier, Verifier

    def has_answer(out: Any) -> tuple[str, str]:
        return ("pass", "ok") if "answer" in out else ("fail", "missing")

    Verifier.audit(
        {"answer": "ok"},
        layers=[
            RuleBasedVerifier(rules=[has_answer]),
            RuleBasedVerifier(rules=[has_answer]),
        ],
    )

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    layer_spans = [s for s in spans if s.name == "primal.verifier.layer"]
    assert len(layer_spans) == 2
    audit = next(s for s in spans if s.name == "primal.verifier.audit")
    for ls in layer_spans:
        assert ls.parent is not None
        assert ls.parent.span_id == audit.context.span_id
        assert ls.attributes["primal.verifier.layer.status"] == "PASS"


def test_audit_layer_exception_recorded_as_uncertain(otel_exporter: object) -> None:
    class BrokenLayer:
        name = "broken"

        def verify(self, target: Any) -> Any:  # noqa: ARG002
            raise RuntimeError("kapow")

    from primal_ai.verifier import Verifier

    Verifier.audit("anything", layers=[BrokenLayer()])

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    layer = next(s for s in spans if s.name == "primal.verifier.layer")
    assert layer.attributes["primal.verifier.layer.status"] == "UNCERTAIN"
    assert any(ev.name == "exception" for ev in layer.events)


def test_audit_span_child_of_trajectory_session(otel_exporter: object) -> None:
    from primal_ai.trajectory import Trajectory
    from primal_ai.verifier import RuleBasedVerifier, Verifier

    def has_answer(out: Any) -> tuple[str, str]:
        return ("pass", "ok") if "answer" in out else ("fail", "missing")

    with Trajectory.record():
        Verifier.audit(
            {"answer": "ok"},
            layers=[RuleBasedVerifier(rules=[has_answer])],
        )

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    session = next(s for s in spans if s.name == "primal.trajectory.session")
    audit = next(s for s in spans if s.name == "primal.verifier.audit")
    assert audit.parent is not None
    assert audit.parent.span_id == session.context.span_id
