"""Test fixtures shared across the suite.

Provides the ``otel_exporter`` fixture used by every test in
``tests/test_observability_*.py``. The fixture installs a fresh
``InMemorySpanExporter`` on a shared session-scoped ``TracerProvider``,
so each test sees only the spans it produced.

We use a session-scoped TracerProvider rather than per-test because
OpenTelemetry rejects repeated calls to ``trace.set_tracer_provider``
after the first one — the rest are no-ops with a warning. To keep
test isolation, each test attaches its own ``SimpleSpanProcessor`` +
``InMemorySpanExporter`` to the shared provider and shuts it down on
teardown; dead processors discard incoming spans, so the previous
test's exporter never sees the next test's data.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session")
def _otel_provider() -> object:
    """Session-scoped ``TracerProvider`` set as the global provider once."""
    sdk_trace = pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry import trace as otel_trace

    provider = sdk_trace.TracerProvider()
    otel_trace.set_tracer_provider(provider)
    return provider


@pytest.fixture
def otel_exporter(_otel_provider: object) -> Iterator[object]:
    """Install a fresh in-memory OTel exporter for one test.

    Skips the test if ``opentelemetry-sdk`` isn't installed. Each
    invocation attaches a fresh ``SimpleSpanProcessor`` to the shared
    session provider and shuts it down on teardown — that's how we get
    per-test isolation while still respecting OTel's one-provider-per-
    process constraint.
    """
    in_memory_mod = pytest.importorskip(
        "opentelemetry.sdk.trace.export.in_memory_span_exporter",
    )
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    exporter = in_memory_mod.InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    _otel_provider.add_span_processor(processor)  # type: ignore[attr-defined]
    try:
        yield exporter
    finally:
        processor.shutdown()
        exporter.clear()
