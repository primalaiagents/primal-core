"""OTel span tests for the Guardian pillar."""

from __future__ import annotations

import pytest


def test_guardian_wrap_emits_invoke_span_per_call(otel_exporter: object) -> None:
    from primal_ai.guardian import Guardian

    def agent(q: str) -> str:
        return f"hi {q}"

    wrapped = Guardian.wrap(agent, policies=[])
    wrapped("alice")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    invoke = next((s for s in spans if s.name == "primal.guardian.invoke"), None)
    assert invoke is not None
    assert invoke.attributes["primal.guardian.policy_count"] == 0
    assert invoke.attributes["primal.guardian.status"] == "OK"


def test_guardian_violation_records_event_and_sets_error_status(
    otel_exporter: object,
) -> None:
    from opentelemetry.trace import StatusCode

    from primal_ai.guardian import Guardian
    from primal_ai.guardian._policy import Policy, PolicyViolation

    class AlwaysBlocks(Policy):
        name = "blocker"

        def check_pre(self, args: object, kwargs: object) -> None:  # noqa: ARG002
            raise PolicyViolation(
                policy_name="blocker",
                reason="nope",
                phase="pre",
                context={},
            )

    def agent(q: str) -> str:
        return q

    wrapped = Guardian.wrap(agent, policies=[AlwaysBlocks()])
    with pytest.raises(PolicyViolation):
        wrapped("anything")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    invoke = next((s for s in spans if s.name == "primal.guardian.invoke"), None)
    assert invoke is not None
    assert invoke.status.status_code == StatusCode.ERROR
    assert invoke.attributes["primal.guardian.status"] == "VIOLATION"
    assert any(
        ev.name == "primal.guardian.violation"
        and ev.attributes["primal.guardian.policy"] == "blocker"
        for ev in invoke.events
    )


def test_guardian_dry_run_does_not_raise_but_still_spans(
    otel_exporter: object,
) -> None:
    from primal_ai.guardian import Guardian
    from primal_ai.guardian._policy import Policy, PolicyViolation

    class AlwaysBlocks(Policy):
        name = "blocker"

        def check_pre(self, args: object, kwargs: object) -> None:  # noqa: ARG002
            raise PolicyViolation(
                policy_name="blocker",
                reason="nope",
                phase="pre",
                context={},
            )

    def agent(q: str) -> str:
        return q

    wrapped = Guardian.wrap(agent, policies=[AlwaysBlocks()])
    with Guardian.dry_run():
        wrapped("anything")  # Must not raise.

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    invoke = next((s for s in spans if s.name == "primal.guardian.invoke"), None)
    assert invoke is not None
    assert invoke.attributes["primal.guardian.dry_run"] is True


def test_guardian_invoke_span_child_of_trajectory_session(
    otel_exporter: object,
) -> None:
    from primal_ai.guardian import Guardian
    from primal_ai.trajectory import Trajectory

    def agent(q: str) -> str:
        return q

    wrapped = Guardian.wrap(agent, policies=[])
    with Trajectory.record():
        wrapped("alice")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    session = next(s for s in spans if s.name == "primal.trajectory.session")
    invoke = next(s for s in spans if s.name == "primal.guardian.invoke")
    assert invoke.parent is not None
    assert invoke.parent.span_id == session.context.span_id
