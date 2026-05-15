"""OpenTelemetry integration for PRIMAL.

This package is the *only* place in PRIMAL that imports from
``opentelemetry``. Every pillar wires its public entrypoints through
:func:`span` / :func:`add_event` / :func:`record_exception` — which are
no-ops unless ``opentelemetry-api`` is installed.

Users who want real spans:

    pip install primal-ai[otel]

Then configure a TracerProvider (e.g. via the OpenTelemetry SDK or a
vendor-supplied distribution like ``opentelemetry-distro``) and PRIMAL
spans show up alongside everything else.
"""

from __future__ import annotations

from primal_ai.observability._otel import (
    add_event,
    get_tracer,
    record_exception,
    span,
)

__all__ = ["add_event", "get_tracer", "record_exception", "span"]
