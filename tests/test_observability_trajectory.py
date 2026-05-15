"""OTel span tests for the Trajectory pillar."""

from __future__ import annotations

import pytest


def test_trajectory_open_close_emits_session_span(otel_exporter: object) -> None:
    from primal_ai.trajectory import Trajectory

    with Trajectory.record(agent_id="alpha") as tr:
        tr.record_input({"q": "hi"})

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    session = next((s for s in spans if s.name == "primal.trajectory.session"), None)
    assert session is not None
    assert session.attributes["primal.trajectory.id"] == tr.trajectory_id
    assert session.attributes["primal.trajectory.agent_id"] == "alpha"
    assert session.attributes["primal.trajectory.status"] == "SUCCESS"


def test_trajectory_exception_sets_failed_status(otel_exporter: object) -> None:
    from opentelemetry.trace import StatusCode

    from primal_ai.trajectory import Trajectory

    with (
        pytest.raises(RuntimeError, match="boom"),
        Trajectory.record(agent_id="alpha"),
    ):
        raise RuntimeError("boom")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    session = next((s for s in spans if s.name == "primal.trajectory.session"), None)
    assert session is not None
    assert session.attributes["primal.trajectory.status"] == "FAILED"
    assert session.status.status_code == StatusCode.ERROR


def test_unpaired_steps_emit_span_events(otel_exporter: object) -> None:
    from primal_ai.trajectory import Trajectory

    with Trajectory.record() as tr:
        tr.record_input({"q": "hi"})
        tr.record_output({"a": "bye"})
        tr.record_error(ValueError("oops"))

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    session = next((s for s in spans if s.name == "primal.trajectory.session"), None)
    assert session is not None

    kinds = [ev.attributes["primal.trajectory.step.kind"] for ev in session.events]
    assert "INPUT" in kinds
    assert "OUTPUT" in kinds
    assert "ERROR" in kinds


def test_tool_call_result_pair_emits_single_span_with_attrs(
    otel_exporter: object,
) -> None:
    from primal_ai.trajectory import Trajectory

    with Trajectory.record() as tr:
        call = tr.record_tool_call("search", {"q": "x"})
        tr.record_tool_result(call.step_id, {"hits": 3}, cost=0.02, latency_ms=125.0)

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    tool_spans = [s for s in spans if s.name == "primal.trajectory.tool_call"]
    assert len(tool_spans) == 1
    tool = tool_spans[0]
    assert tool.attributes["primal.trajectory.tool_name"] == "search"
    assert tool.attributes["primal.trajectory.cost"] == 0.02
    assert tool.attributes["primal.trajectory.latency_ms"] == 125.0


def test_llm_call_result_pair_emits_single_span_with_attrs(
    otel_exporter: object,
) -> None:
    from primal_ai.trajectory import Trajectory

    with Trajectory.record() as tr:
        call = tr.record_llm_call("haiku", [{"role": "user", "content": "hi"}])
        tr.record_llm_result(
            call.step_id,
            "hi back",
            cost=0.0001,
            tokens={"in": 1, "out": 2},
            latency_ms=88.0,
        )

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    llm_spans = [s for s in spans if s.name == "primal.trajectory.llm_call"]
    assert len(llm_spans) == 1
    llm = llm_spans[0]
    assert llm.attributes["primal.trajectory.model"] == "haiku"
    assert llm.attributes["primal.trajectory.cost"] == 0.0001
    assert llm.attributes["primal.trajectory.latency_ms"] == 88.0


def test_tool_call_without_result_ends_at_trajectory_close(
    otel_exporter: object,
) -> None:
    from primal_ai.trajectory import Trajectory

    with Trajectory.record() as tr:
        tr.record_tool_call("search", {"q": "x"})
        # No matching record_tool_result.

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    tool_spans = [s for s in spans if s.name == "primal.trajectory.tool_call"]
    assert len(tool_spans) == 1
    # Span ended (it's in finished_spans), and was given a clear marker.
    assert tool_spans[0].attributes.get("primal.trajectory.orphaned") is True


def test_open_step_spans_record_exception_on_trajectory_failure(
    otel_exporter: object,
) -> None:
    """An open tool/llm call span, when the trajectory exits via exception,
    must get the exception recorded on it AND be marked orphaned AND have
    error status — it should not leak as a silent completed span."""
    from opentelemetry.trace import StatusCode

    from primal_ai.trajectory import Trajectory

    with (
        pytest.raises(RuntimeError, match="boom"),
        Trajectory.record() as tr,
    ):
        tr.record_tool_call("search", {"q": "x"})
        # No matching record_tool_result before the raise.
        raise RuntimeError("boom")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    tool_spans = [s for s in spans if s.name == "primal.trajectory.tool_call"]
    assert len(tool_spans) == 1
    tool = tool_spans[0]
    assert tool.attributes["primal.trajectory.orphaned"] is True
    assert any(ev.name == "exception" for ev in tool.events), (
        "expected open tool_call span to record the exception that orphaned it"
    )
    assert tool.status.status_code == StatusCode.ERROR


def test_pillar_spans_are_children_of_trajectory_session(
    otel_exporter: object,
) -> None:
    from primal_ai.trajectory import Trajectory

    with Trajectory.record() as tr:
        call = tr.record_tool_call("search", {"q": "x"})
        tr.record_tool_result(call.step_id, {"ok": True})

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    by_name = {s.name: s for s in spans}
    session = by_name["primal.trajectory.session"]
    tool = by_name["primal.trajectory.tool_call"]
    assert tool.parent is not None
    assert tool.parent.span_id == session.context.span_id
