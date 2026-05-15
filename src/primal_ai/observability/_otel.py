"""OTel shim — real tracer if opentelemetry-api is importable, no-op otherwise.

The shim is intentionally tiny. The only contract pillar code relies on:

  * :func:`span` — a context manager that yields a Span-like object.
  * :func:`add_event` — attach a named event to the current span.
  * :func:`record_exception` — attach exception detail to the current span.
  * :func:`get_tracer` — fetch the underlying tracer (escape hatch for
    advanced users; PRIMAL itself only uses ``span`` directly).

When ``opentelemetry.trace`` cannot be imported, every function is a
no-op and ``span`` yields a ``_NoOpSpan``. The same call sites work
unchanged whether OTel is installed or not.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Only for static analysis — at runtime we never import unconditionally.
    from opentelemetry.trace import Span as _OtelSpan  # noqa: F401
    from opentelemetry.trace import Tracer as _OtelTracer  # noqa: F401


_TRACER_NAME = "primal_ai"
_TRACER_VERSION = "0.2.0"


def _otel_available() -> bool:
    """Return True iff ``opentelemetry.trace`` can be imported."""
    try:
        importlib.import_module("opentelemetry.trace")
    except ImportError:
        return False
    return True


class _NoOpSpan:
    """Span-shaped sentinel used when OTel is not installed.

    Mirrors the subset of the ``Span`` API that PRIMAL pillars touch:
    ``set_attribute``, ``set_attributes``, ``add_event``,
    ``record_exception``, ``set_status``, ``end``. Every method is a
    silent no-op so pillar code remains branch-free.
    """

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ARG002
        return None

    def set_attributes(self, attributes: Mapping[str, Any]) -> None:  # noqa: ARG002
        return None

    def add_event(
        self,
        name: str,  # noqa: ARG002
        attributes: Mapping[str, Any] | None = None,  # noqa: ARG002
    ) -> None:
        return None

    def record_exception(self, exception: BaseException) -> None:  # noqa: ARG002
        return None

    def set_status(self, status: Any, description: str | None = None) -> None:  # noqa: ARG002
        return None

    def end(self) -> None:
        return None

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        return None


_NOOP_SPAN = _NoOpSpan()


def get_tracer() -> Any:
    """Return the underlying OTel tracer, or ``None`` if OTel isn't installed.

    Pillar code should not call this directly — use :func:`span` instead.
    Exposed primarily for tests and for advanced users who want to attach
    custom instrumentation alongside PRIMAL's.
    """
    if not _otel_available():
        return None
    from opentelemetry import trace as _trace

    return _trace.get_tracer(_TRACER_NAME, _TRACER_VERSION)


@contextmanager
def span(
    name: str,
    attributes: Mapping[str, Any] | None = None,
) -> Iterator[Any]:
    """Open a span as the current span for the duration of the ``with`` block.

    When OTel is installed, this delegates to
    ``tracer.start_as_current_span(name, attributes=...)``. The yielded
    object is a real ``Span``. When OTel is absent, this yields a
    :class:`_NoOpSpan` that swallows every call.

    Pillar code should follow this pattern::

        with span("primal.<pillar>.<op>", {"foo": "bar"}) as s:
            ...
            s.set_attribute("more", value)
    """
    tracer = get_tracer()
    if tracer is None:
        yield _NOOP_SPAN
        return
    attrs = dict(attributes) if attributes else None
    with tracer.start_as_current_span(name, attributes=attrs) as s:
        yield s


def add_event(
    name: str,
    attributes: Mapping[str, Any] | None = None,
) -> None:
    """Attach a named event to the currently-active span.

    No-op when OTel isn't installed *or* when there is no active span.
    """
    if not _otel_available():
        return
    from opentelemetry import trace as _trace

    current = _trace.get_current_span()
    attrs = dict(attributes) if attributes else None
    current.add_event(name, attributes=attrs)


def record_exception(exception: BaseException) -> None:
    """Attach an exception (with traceback) to the currently-active span.

    No-op when OTel isn't installed or there's no active span.
    """
    if not _otel_available():
        return
    from opentelemetry import trace as _trace

    current = _trace.get_current_span()
    current.record_exception(exception)


__all__ = [
    "_NOOP_SPAN",
    "_NoOpSpan",
    "_otel_available",
    "add_event",
    "get_tracer",
    "record_exception",
    "span",
]
