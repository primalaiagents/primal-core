"""Tests for the OTel integration shim."""

from __future__ import annotations

import pytest


def test_shim_exports_public_surface() -> None:
    from primal_ai.observability import (
        add_event,
        get_tracer,
        record_exception,
        span,
    )
    assert callable(span)
    assert callable(get_tracer)
    assert callable(add_event)
    assert callable(record_exception)


def test_get_tracer_returns_none_when_otel_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from primal_ai.observability import _otel

    monkeypatch.setattr(_otel, "_otel_available", lambda: False)
    assert _otel.get_tracer() is None


def test_get_tracer_returns_tracer_when_otel_present() -> None:
    pytest.importorskip("opentelemetry.trace")
    from primal_ai.observability import get_tracer

    tracer = get_tracer()
    assert tracer is not None
    # Duck-type sanity check — every OTel tracer exposes start_as_current_span.
    assert hasattr(tracer, "start_as_current_span")


def test_span_noop_branch_yields_silent_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from primal_ai.observability import _otel, span

    monkeypatch.setattr(_otel, "_otel_available", lambda: False)
    with span("primal.test.noop", {"a": 1}) as s:
        # No-op span must tolerate every call without raising.
        s.set_attribute("k", "v")
        s.set_attributes({"k2": 2})
        s.add_event("evt", {"x": "y"})
        s.record_exception(RuntimeError("boom"))
        s.set_status("ERROR", "desc")
        s.end()


def test_span_real_branch_creates_real_span(otel_exporter: object) -> None:
    from primal_ai.observability import span

    with span("primal.test.real", {"alpha": "1", "beta": 2}) as s:
        s.set_attribute("gamma", 3)

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    assert len(spans) == 1
    only = spans[0]
    assert only.name == "primal.test.real"
    assert only.attributes["alpha"] == "1"
    assert only.attributes["beta"] == 2
    assert only.attributes["gamma"] == 3


def test_add_event_noop_safe_when_no_active_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from primal_ai.observability import _otel, add_event

    monkeypatch.setattr(_otel, "_otel_available", lambda: False)
    # Must not raise.
    add_event("primal.test.event", {"k": "v"})


def test_record_exception_attaches_to_active_span(otel_exporter: object) -> None:
    from primal_ai.observability import record_exception, span

    with span("primal.test.exc"):
        try:
            raise ValueError("expected")
        except ValueError as e:
            record_exception(e)

    spans = otel_exporter.get_finished_spans()  # type: ignore[attr-defined]
    assert len(spans) == 1
    events = spans[0].events
    assert any(ev.name == "exception" for ev in events)
