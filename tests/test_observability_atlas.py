"""OTel span tests for the Atlas pillar."""

from __future__ import annotations

from typing import Any


def test_route_emits_span_with_decision_attrs(otel_exporter: object) -> None:
    from primal_ai.atlas import Atlas, BYOProvider, ProviderInfo

    provider = BYOProvider(
        name="alpha_obs",
        call=lambda task, **kw: "ok",  # noqa: ARG005
        info=ProviderInfo(name="alpha_obs", capabilities=("chat",)),
    )
    Atlas.register_provider(provider)
    try:
        Atlas.route("hi")
    finally:
        Atlas.unregister_provider("alpha_obs")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    route = next((s for s in spans if s.name == "primal.atlas.route"), None)
    assert route is not None
    assert route.attributes["primal.atlas.status"] == "SUCCESS"
    assert route.attributes["primal.atlas.chosen_provider"] == "alpha_obs"
    assert route.attributes["primal.atlas.candidates_count"] == 1


def test_route_no_candidates_sets_error_status(otel_exporter: object) -> None:
    from opentelemetry.trace import StatusCode

    from primal_ai.atlas import Atlas

    Atlas.route("hi", candidates=["does_not_exist_xyz"])

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    route = next((s for s in spans if s.name == "primal.atlas.route"), None)
    assert route is not None
    assert route.attributes["primal.atlas.status"] == "NO_CANDIDATES"
    assert route.status.status_code == StatusCode.ERROR


def test_invoke_emits_child_provider_span(otel_exporter: object) -> None:
    from primal_ai.atlas import Atlas, BYOProvider, ProviderInfo

    provider = BYOProvider(
        name="beta_obs",
        call=lambda task, **kw: "result",  # noqa: ARG005
        info=ProviderInfo(name="beta_obs", capabilities=("chat",)),
    )
    Atlas.register_provider(provider)
    try:
        Atlas.invoke("hi")
    finally:
        Atlas.unregister_provider("beta_obs")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    route = next(s for s in spans if s.name == "primal.atlas.route")
    provider_span = next(
        (s for s in spans if s.name == "primal.atlas.provider"), None,
    )
    assert provider_span is not None
    assert provider_span.parent is not None
    assert provider_span.parent.span_id == route.context.span_id
    assert provider_span.attributes["primal.atlas.provider.name"] == "beta_obs"
    assert provider_span.attributes["primal.atlas.provider.status"] == "SUCCESS"


def test_invoke_provider_failure_records_exception(otel_exporter: object) -> None:
    from opentelemetry.trace import StatusCode

    from primal_ai.atlas import Atlas, BYOProvider, ProviderInfo

    def boom(task: str, **kw: Any) -> Any:  # noqa: ARG001
        raise RuntimeError("provider broke")

    provider = BYOProvider(
        name="boom_obs",
        call=boom,
        info=ProviderInfo(name="boom_obs", capabilities=("chat",)),
    )
    Atlas.register_provider(provider)
    try:
        Atlas.invoke("hi")
    finally:
        Atlas.reset_health("boom_obs")
        Atlas.unregister_provider("boom_obs")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    provider_span = next(s for s in spans if s.name == "primal.atlas.provider")
    assert provider_span.attributes["primal.atlas.provider.status"] == "FAILED"
    assert provider_span.status.status_code == StatusCode.ERROR
    assert any(ev.name == "exception" for ev in provider_span.events)


def test_route_span_child_of_trajectory_session(otel_exporter: object) -> None:
    from primal_ai.atlas import Atlas, BYOProvider, ProviderInfo
    from primal_ai.trajectory import Trajectory

    provider = BYOProvider(
        name="gamma_obs",
        call=lambda task, **kw: "ok",  # noqa: ARG005
        info=ProviderInfo(name="gamma_obs", capabilities=("chat",)),
    )
    Atlas.register_provider(provider)
    try:
        with Trajectory.record():
            Atlas.route("hi")
    finally:
        Atlas.unregister_provider("gamma_obs")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    session = next(s for s in spans if s.name == "primal.trajectory.session")
    route = next(s for s in spans if s.name == "primal.atlas.route")
    assert route.parent is not None
    assert route.parent.span_id == session.context.span_id


def test_cascade_emits_root_span_and_attempt_children(otel_exporter: object) -> None:
    from primal_ai.atlas import Atlas, BYOProvider, ProviderInfo
    from primal_ai.atlas.cascade import Cascade

    counter: dict[str, int] = {"n": 0}

    def flaky(task: str, **kw: Any) -> Any:  # noqa: ARG001
        counter["n"] += 1
        if counter["n"] == 1:
            raise RuntimeError("first attempt fails")
        return "ok"

    Atlas.register_provider(
        BYOProvider(
            name="flaky_a",
            call=flaky,
            info=ProviderInfo(name="flaky_a", capabilities=("chat",)),
        ),
    )
    Atlas.register_provider(
        BYOProvider(
            name="flaky_b",
            call=lambda task, **kw: "ok",  # noqa: ARG005
            info=ProviderInfo(name="flaky_b", capabilities=("chat",)),
        ),
    )
    try:
        Cascade(providers=["flaky_a", "flaky_b"]).run("hi")
    finally:
        Atlas.reset_health("flaky_a")
        Atlas.unregister_provider("flaky_a")
        Atlas.unregister_provider("flaky_b")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    cascade_spans = [s for s in spans if s.name == "primal.atlas.cascade"]
    attempt_spans = [s for s in spans if s.name == "primal.atlas.cascade.attempt"]
    assert len(cascade_spans) == 1
    assert len(attempt_spans) == 2

    cascade_span = cascade_spans[0]
    assert cascade_span.attributes["primal.atlas.cascade.providers"] == 2
    assert cascade_span.attributes["primal.atlas.cascade.status"] == "SUCCESS"
    assert cascade_span.attributes["primal.atlas.cascade.chosen"] == "flaky_b"

    for a in attempt_spans:
        assert a.parent is not None
        assert a.parent.span_id == cascade_span.context.span_id

    first = next(
        s for s in attempt_spans
        if s.attributes["primal.atlas.cascade.attempt.index"] == 0
    )
    second = next(
        s for s in attempt_spans
        if s.attributes["primal.atlas.cascade.attempt.index"] == 1
    )
    assert first.attributes["primal.atlas.cascade.attempt.status"] == "FAILED"
    assert second.attributes["primal.atlas.cascade.attempt.status"] == "SUCCESS"
    assert any(ev.name == "exception" for ev in first.events)


def test_cascade_all_unhealthy_records_status(otel_exporter: object) -> None:
    from primal_ai.atlas import Atlas, BYOProvider, ProviderInfo
    from primal_ai.atlas.cascade import Cascade

    def boom(task: str, **kw: Any) -> Any:  # noqa: ARG001
        raise RuntimeError("x")

    Atlas.register_provider(
        BYOProvider(
            name="cool_a",
            call=boom,
            info=ProviderInfo(name="cool_a", capabilities=("chat",)),
        ),
    )
    # Force provider into cooldown before the cascade runs.
    health = Atlas.get_health("cool_a")
    assert health is not None
    health.record_failure(cooldown_seconds=300.0)
    try:
        Cascade(providers=["cool_a"]).run("hi")
    finally:
        Atlas.reset_health("cool_a")
        Atlas.unregister_provider("cool_a")

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    cascade_span = next(s for s in spans if s.name == "primal.atlas.cascade")
    assert cascade_span.attributes["primal.atlas.cascade.status"] == "ALL_UNHEALTHY"
