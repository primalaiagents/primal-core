"""Verifier facade — audit() entrypoint, registry, default-layer config.

``Verifier`` is the top-level surface users reach for. It composes one or
more ``VerifierLayer`` instances and aggregates their verdicts into a
single overall status.

Aggregation rule (the most important semantic here):

    any FAIL          → FAIL
    all PASS          → PASS
    otherwise         → UNCERTAIN

A layer that raises during ``verify`` is converted into an UNCERTAIN
verdict so one broken layer never breaks the pipeline.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from primal_ai.observability import record_exception, span
from primal_ai.verifier._protocol import VerifierLayer
from primal_ai.verifier._verdict import Verdict, VerdictStatus

# Module-level registry of name → factory. Threadsafe under ``_registry_lock``.
_REGISTRY: dict[str, Callable[[], VerifierLayer]] = {}
_registry_lock = threading.Lock()

# Module-level default-layer chain used when ``audit(layers=None)``.
_default_layers: list[VerifierLayer] = []
_default_layers_lock = threading.Lock()


def register_verifier(name: str, factory: Callable[[], VerifierLayer]) -> None:
    """Register a name → factory mapping for string-based layer resolution.

    The factory is a zero-argument callable that returns a fresh
    ``VerifierLayer`` instance. Names live in a single process-wide
    registry; registering twice with the same name replaces the prior
    entry.

    Example:
        >>> register_verifier("my_rule", lambda: RuleBasedVerifier(rules=[...]))
    """
    with _registry_lock:
        _REGISTRY[name] = factory


def registered_names() -> list[str]:
    """Return the sorted list of currently-registered verifier names."""
    with _registry_lock:
        return sorted(_REGISTRY)


def resolve_layer(name: str) -> VerifierLayer:
    """Resolve a string name into a fresh ``VerifierLayer`` instance.

    Raises ``ValueError`` if the name isn't registered.
    """
    with _registry_lock:
        factory = _REGISTRY.get(name)
    if factory is None:
        raise ValueError(
            f"unknown verifier {name!r}; registered: {registered_names()}",
        )
    return factory()


def _resolve_layers(
    layers: Sequence[str | VerifierLayer] | None,
) -> list[VerifierLayer]:
    """Resolve a mixed list of strings + layers into concrete ``VerifierLayer``s."""
    if layers is None:
        with _default_layers_lock:
            return list(_default_layers)
    resolved: list[VerifierLayer] = []
    for item in layers:
        if isinstance(item, str):
            resolved.append(resolve_layer(item))
        else:
            resolved.append(item)
    return resolved


def _extract_output_from_trajectory(trajectory: Any) -> Any:
    """Pull the most-recent OUTPUT step's data from a trajectory.

    Falls back to ``None`` when the trajectory has no OUTPUT step. Imported
    lazily to keep ``verifier`` independent of ``trajectory`` at import time
    (avoids a hard cycle on package init).
    """
    from primal_ai.trajectory import StepKind  # local import — avoid eager cycle

    outputs = trajectory.find_steps(kind=StepKind.OUTPUT)
    if not outputs:
        return None
    return outputs[-1].data


def _aggregate_status(verdicts: list[Verdict]) -> VerdictStatus:
    """Apply the documented aggregation rule across a list of verdicts."""
    if not verdicts:
        return VerdictStatus.UNCERTAIN
    saw_pass = False
    saw_uncertain = False
    for v in verdicts:
        if v.status == VerdictStatus.FAIL:
            return VerdictStatus.FAIL
        if v.status == VerdictStatus.PASS:
            saw_pass = True
        else:
            saw_uncertain = True
    if saw_pass and not saw_uncertain:
        return VerdictStatus.PASS
    return VerdictStatus.UNCERTAIN


def _aggregate_confidence(verdicts: list[Verdict]) -> float:
    """Mean confidence across verdicts; 0.0 for an empty list."""
    if not verdicts:
        return 0.0
    return sum(v.confidence for v in verdicts) / len(verdicts)


def _aggregate_cost(verdicts: list[Verdict]) -> float | None:
    """Sum of non-None costs, or ``None`` when every verdict's cost is ``None``."""
    costs = [v.cost for v in verdicts if v.cost is not None]
    if not costs:
        return None
    return sum(costs)


class Verifier:
    """Top-level facade for the three-layer audit pipeline.

    ``Verifier.audit(target, layers=...)`` runs ``target`` through every
    configured ``VerifierLayer`` and returns a single overall verdict.
    ``target`` may be either a raw output value or a ``Trajectory`` — the
    facade duck-types the latter via ``hasattr(target, "replay")``.

    Example:
        >>> from primal_ai import RuleBasedVerifier, Verifier
        >>> def has_answer(out):
        ...     return ("pass", "has answer") if "answer" in out else ("fail", "no answer")
        >>> verdict = Verifier.audit(
        ...     {"answer": "tokyo"},
        ...     layers=[RuleBasedVerifier(rules=[has_answer])],
        ... )
        >>> verdict["status"]
        'PASS'
    """

    @classmethod
    def audit(
        cls,
        output: Any,
        layers: Sequence[str | VerifierLayer] | None = None,
    ) -> dict[str, Any]:
        """Audit ``output`` (or a ``Trajectory``) through ``layers``.

        Args:
            output: A raw agent output OR a ``Trajectory`` (duck-typed
                via ``hasattr(output, "replay")``).
            layers: Sequence of ``VerifierLayer`` instances and/or
                registry-name strings. ``None`` uses the default chain
                configured via :meth:`set_default_layers`.

        Returns:
            A dict with:
                ``status`` (str): aggregated VerdictStatus value.
                ``verdicts`` (list[dict]): each layer's verdict (``to_dict``).
                ``aggregate_confidence`` (float): mean of layer confidences.
                ``total_cost`` (float | None): sum of layer costs, or
                    ``None`` if no layer recorded a cost.
                ``layer_count`` (int): number of layers that produced a
                    verdict (including layers that raised — those are
                    UNCERTAIN verdicts).
        """
        is_trajectory = hasattr(output, "replay")
        resolved = _resolve_layers(layers)

        with span(
            "primal.verifier.audit",
            {
                "primal.verifier.layer_count_planned": len(resolved),
                "primal.verifier.target_kind": (
                    "trajectory" if is_trajectory else "output"
                ),
            },
        ) as audit_span:
            verdicts: list[Verdict] = []
            for layer in resolved:
                target = cls._target_for_layer(layer, output, is_trajectory)
                verdicts.append(cls._run_layer(layer, target))

            aggregated = _aggregate_status(verdicts).value
            confidence = _aggregate_confidence(verdicts)
            cost = _aggregate_cost(verdicts)
            audit_span.set_attribute("primal.verifier.status", aggregated)
            audit_span.set_attribute("primal.verifier.layer_count", len(verdicts))
            audit_span.set_attribute("primal.verifier.confidence", confidence)
            if cost is not None:
                audit_span.set_attribute("primal.verifier.total_cost", cost)
            if aggregated == VerdictStatus.FAIL.value:
                audit_span.set_status(_otel_error_status("verdict FAIL"))

            return {
                "status": aggregated,
                "verdicts": [v.to_dict() for v in verdicts],
                "aggregate_confidence": confidence,
                "total_cost": cost,
                "layer_count": len(verdicts),
            }

    @classmethod
    def set_default_layers(
        cls,
        layers: Sequence[str | VerifierLayer],
    ) -> None:
        """Configure the default chain used by ``audit(..., layers=None)``.

        Threadsafe. Strings are resolved at audit time, not registration
        time, so a string layer referencing a name registered later will
        still work.
        """
        # Resolve strings eagerly so misconfiguration fails loudly here
        # rather than deep inside a future ``audit`` call.
        resolved = _resolve_layers(list(layers))
        with _default_layers_lock:
            global _default_layers  # noqa: PLW0603 — single module-level slot
            _default_layers = resolved

    # ──────────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _target_for_layer(
        layer: VerifierLayer,
        output: Any,
        is_trajectory: bool,
    ) -> Any:
        """Decide what to hand a layer: the trajectory itself, or an extracted output."""
        wants_trajectory = bool(getattr(layer, "accepts_trajectory", False))
        if is_trajectory and wants_trajectory:
            return output
        if is_trajectory and not wants_trajectory:
            return _extract_output_from_trajectory(output)
        # Raw output passed at the top level — we have no trajectory to
        # give. A layer that demands one gets the raw output and may
        # respond with UNCERTAIN if it can't cope (its choice, not ours).
        return output

    @staticmethod
    def _run_layer(layer: VerifierLayer, target: Any) -> Verdict:
        """Invoke ``layer.verify(target)``; convert exceptions to UNCERTAIN verdicts."""
        name = getattr(layer, "name", layer.__class__.__name__)
        with span(
            "primal.verifier.layer",
            {"primal.verifier.layer.name": name},
        ) as layer_span:
            started = time.monotonic()
            try:
                verdict = layer.verify(target)
            except Exception as exc:  # noqa: BLE001 — broken layer must not kill chain
                latency_ms = (time.monotonic() - started) * 1000.0
                record_exception(exc)
                layer_span.set_attribute(
                    "primal.verifier.layer.status", VerdictStatus.UNCERTAIN.value,
                )
                layer_span.set_attribute(
                    "primal.verifier.layer.latency_ms", latency_ms,
                )
                layer_span.set_status(_otel_error_status(str(exc)))
                return Verdict(
                    verifier_name=name,
                    status=VerdictStatus.UNCERTAIN,
                    confidence=0.0,
                    reasons=[
                        f"verifier {name!r} raised: {type(exc).__name__}: {exc}",
                    ],
                    details={"exception_type": type(exc).__name__},
                    latency_ms=latency_ms,
                )
            if verdict.latency_ms is None:
                latency_ms = (time.monotonic() - started) * 1000.0
                verdict = Verdict(
                    verifier_name=verdict.verifier_name,
                    status=verdict.status,
                    confidence=verdict.confidence,
                    reasons=verdict.reasons,
                    details=verdict.details,
                    cost=verdict.cost,
                    latency_ms=latency_ms,
                )
            layer_span.set_attribute(
                "primal.verifier.layer.status", verdict.status.value,
            )
            layer_span.set_attribute(
                "primal.verifier.layer.confidence", verdict.confidence,
            )
            if verdict.latency_ms is not None:
                layer_span.set_attribute(
                    "primal.verifier.layer.latency_ms", verdict.latency_ms,
                )
            if verdict.cost is not None:
                layer_span.set_attribute(
                    "primal.verifier.layer.cost", verdict.cost,
                )
            if verdict.status == VerdictStatus.FAIL:
                layer_span.set_status(_otel_error_status("layer verdict FAIL"))
            return verdict


def _otel_error_status(description: str) -> Any:
    """Return an OTel ``Status(StatusCode.ERROR, description)`` or ``None``.

    Deferred import keeps Verifier import-safe when ``opentelemetry-api``
    isn't installed.
    """
    try:
        from opentelemetry.trace import Status, StatusCode
    except ImportError:
        return None
    return Status(StatusCode.ERROR, description)


__all__ = [
    "Verifier",
    "register_verifier",
    "registered_names",
    "resolve_layer",
]
