"""``Cascade`` — ordered provider fallback with exponential-backoff cooldown.

Each ``Cascade.run`` walks the provider list in declared order, skipping
unhealthy providers and invoking the first healthy one. On failure, the
offending provider's health gets a cooldown of
``min(base * 2 ** consecutive_failures, max)`` seconds; the cascade then
falls through to the next provider in the list.

If every provider fails (or is unhealthy), the cascade returns FAILED
without raising. Lifecycle events fire on the shared event bus so
external observers (Inspector UI, logs, OTel exporters in Phase 2) can
follow the attempt sequence.
"""

from __future__ import annotations

import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from primal_ai._events import Event, EventKind
from primal_ai._trajectory_context import current_trajectory
from primal_ai.atlas._decision import RoutingStatus
from primal_ai.atlas.bandit import BanditOutcome, _safe_update
from primal_ai.atlas.router import Atlas
from primal_ai.observability import record_exception, span


@dataclass(frozen=True)
class CascadeResult:
    """Structured outcome of one ``Cascade.run`` call.

    Args:
        cascade_id: uuid4 hex identifier for this cascade run.
        attempts: One tuple per provider tried, in order:
            ``(provider_name, status, reason)``.
        chosen: Name of the provider that ultimately succeeded, or
            ``None`` if the cascade exhausted itself.
        output: The successful provider's output, or ``None`` on failure.
        status: ``SUCCESS`` if any attempt succeeded; ``FAILED`` if all
            attempts failed; ``ALL_UNHEALTHY`` if every provider was in
            cooldown before we even tried.
        started_at / ended_at / duration_ms: Lifetime of the cascade.
    """

    cascade_id: str
    attempts: tuple[tuple[str, RoutingStatus, str | None], ...]
    chosen: str | None
    output: Any
    status: RoutingStatus
    started_at: float
    ended_at: float
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "cascade_id": self.cascade_id,
            "attempts": [
                [name, status.value, reason] for name, status, reason in self.attempts
            ],
            "chosen": self.chosen,
            "output": self.output,
            "status": self.status.value,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CascadeResult:
        """Rebuild a ``CascadeResult`` from a ``to_dict`` payload."""
        return cls(
            cascade_id=str(payload["cascade_id"]),
            attempts=tuple(
                (str(a[0]), RoutingStatus(a[1]), (None if a[2] is None else str(a[2])))
                for a in payload.get("attempts") or []
            ),
            chosen=payload.get("chosen"),
            output=payload.get("output"),
            status=RoutingStatus(payload["status"]),
            started_at=float(payload.get("started_at") or 0.0),
            ended_at=float(payload.get("ended_at") or 0.0),
            duration_ms=float(payload.get("duration_ms") or 0.0),
        )


@dataclass(frozen=True)
class _Attempt:
    """Internal mutable-but-frozen-after-creation attempt record."""

    name: str
    status: RoutingStatus
    reason: str | None
    output: Any = field(default=None)


class Cascade:
    """Ordered provider fallback with health-aware cooldown management.

    Args:
        providers: Provider names to try in order.
        base_cooldown_seconds: Cooldown applied on the first failure
            (per provider). Doubles on each consecutive failure.
        max_cooldown_seconds: Upper bound on the cooldown — once
            ``base * 2 ** n`` exceeds this, the cascade clamps.
        attempts_per_call: Reserved for Phase 2 (retry-the-same-provider).
            MVP ignores it.

    Example:
        >>> from primal_ai import Atlas, BYOProvider, Cascade, ProviderInfo
        >>> Atlas.register_provider(BYOProvider("primary", lambda t, **kw: 1))
        >>> Atlas.register_provider(BYOProvider("backup",  lambda t, **kw: 2))
        >>> result = Cascade(providers=["primary", "backup"]).run("task")
        >>> result.status.value
        'SUCCESS'
    """

    def __init__(
        self,
        providers: list[str],
        *,
        base_cooldown_seconds: float = 30.0,
        max_cooldown_seconds: float = 600.0,
        attempts_per_call: int | None = None,
    ) -> None:
        self.providers = list(providers)
        self.base_cooldown_seconds = base_cooldown_seconds
        self.max_cooldown_seconds = max_cooldown_seconds
        self.attempts_per_call = attempts_per_call

    def run(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> CascadeResult:
        """Try each provider in order; return the first SUCCESS or aggregated FAILED."""
        cascade_id = uuid.uuid4().hex
        started = time.time()
        started_mono = time.monotonic()

        with span(
            "primal.atlas.cascade",
            {
                "primal.atlas.cascade.id": cascade_id,
                "primal.atlas.cascade.providers": len(self.providers),
            },
        ) as cascade_span:
            Atlas.event_bus.publish(
                Event(
                    kind=EventKind.CASCADE_STARTED.value,
                    payload={
                        "cascade_id": cascade_id,
                        "providers": list(self.providers),
                    },
                ),
            )

            attempts: list[_Attempt] = []
            chosen: str | None = None
            output: Any = None
            final_status: RoutingStatus = RoutingStatus.FAILED

            for index, name in enumerate(self.providers):
                attempt = self._try_provider(
                    name, task, cascade_id, context, kwargs,
                    attempt_index=index,
                )
                attempts.append(attempt)
                if attempt.status == RoutingStatus.SUCCESS:
                    chosen = name
                    output = attempt.output
                    final_status = RoutingStatus.SUCCESS
                    break

            if final_status != RoutingStatus.SUCCESS and attempts and all(
                a.status == RoutingStatus.ALL_UNHEALTHY for a in attempts
            ):
                final_status = RoutingStatus.ALL_UNHEALTHY

            ended = time.time()
            duration_ms = (time.monotonic() - started_mono) * 1000.0
            result = CascadeResult(
                cascade_id=cascade_id,
                attempts=tuple(
                    (a.name, a.status, a.reason) for a in attempts
                ),
                chosen=chosen,
                output=output,
                status=final_status,
                started_at=started,
                ended_at=ended,
                duration_ms=duration_ms,
            )

            cascade_span.set_attribute(
                "primal.atlas.cascade.status", final_status.value,
            )
            cascade_span.set_attribute(
                "primal.atlas.cascade.attempt_count", len(attempts),
            )
            cascade_span.set_attribute(
                "primal.atlas.cascade.duration_ms", duration_ms,
            )
            if chosen is not None:
                cascade_span.set_attribute("primal.atlas.cascade.chosen", chosen)
            if final_status != RoutingStatus.SUCCESS:
                cascade_span.set_status(_otel_error_status(final_status.value))

            Atlas.event_bus.publish(
                Event(
                    kind=(
                        EventKind.CASCADE_COMPLETED.value
                        if final_status == RoutingStatus.SUCCESS
                        else EventKind.CASCADE_FAILED.value
                    ),
                    payload={"result": result.to_dict()},
                ),
            )
            self._record_cascade_to_trajectory(result)
            return result

    # ──────────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────────

    def _try_provider(
        self,
        name: str,
        task: str,
        cascade_id: str,
        context: dict[str, Any] | None,
        kwargs: dict[str, Any],
        *,
        attempt_index: int = 0,
    ) -> _Attempt:
        """Run one cascade attempt against a single provider."""
        with span(
            "primal.atlas.cascade.attempt",
            {
                "primal.atlas.cascade.id": cascade_id,
                "primal.atlas.cascade.attempt.provider": name,
                "primal.atlas.cascade.attempt.index": attempt_index,
            },
        ) as attempt_span:
            provider = Atlas.get_provider(name)
            if provider is None:
                attempt = _Attempt(
                    name, RoutingStatus.NO_CANDIDATES, "not_registered",
                )
                attempt_span.set_attribute(
                    "primal.atlas.cascade.attempt.status", attempt.status.value,
                )
                attempt_span.set_status(_otel_error_status("not_registered"))
                self._publish_attempt(cascade_id, attempt)
                return attempt

            health = Atlas.get_health(name)
            if health is not None and not health.is_healthy():
                attempt = _Attempt(
                    name, RoutingStatus.ALL_UNHEALTHY, "in_cooldown",
                )
                attempt_span.set_attribute(
                    "primal.atlas.cascade.attempt.status", attempt.status.value,
                )
                attempt_span.set_status(_otel_error_status("in_cooldown"))
                self._publish_attempt(cascade_id, attempt)
                return attempt

            bandit_ctx_key = (
                ""
                if context is None
                else str(context.get("bandit_context_key") or "")
            )
            try:
                output = provider.invoke(task, **kwargs)
            except Exception as exc:  # noqa: BLE001
                self._apply_exponential_cooldown(name)
                _safe_update(
                    Atlas.get_selector(),
                    BanditOutcome(
                        provider_name=name,
                        success=False,
                        reward=0.0,
                        context_key=bandit_ctx_key,
                    ),
                )
                attempt = _Attempt(
                    name,
                    RoutingStatus.FAILED,
                    f"{type(exc).__name__}: {exc}",
                )
                attempt_span.set_attribute(
                    "primal.atlas.cascade.attempt.status", attempt.status.value,
                )
                attempt_span.set_status(_otel_error_status(attempt.reason or ""))
                record_exception(exc)
                self._publish_attempt(cascade_id, attempt)
                return attempt

            if health is not None:
                health.record_success()
            _safe_update(
                Atlas.get_selector(),
                BanditOutcome(
                    provider_name=name,
                    success=True,
                    reward=1.0,
                    context_key=bandit_ctx_key,
                ),
            )
            attempt = _Attempt(name, RoutingStatus.SUCCESS, None, output=output)
            attempt_span.set_attribute(
                "primal.atlas.cascade.attempt.status", attempt.status.value,
            )
            self._publish_attempt(cascade_id, attempt)
            return attempt

    def _apply_exponential_cooldown(self, provider_name: str) -> None:
        """Record a failure on ``provider_name`` with a doubled-from-base cooldown."""
        health = Atlas.get_health(provider_name)
        if health is None:
            return
        # Read the current ``consecutive_failures`` BEFORE recording this one;
        # the new failure is the (n+1)th, so cooldown = base * 2^n (n = current).
        # ``record_failure`` then increments the counter.
        n = health.consecutive_failures
        cooldown = min(self.base_cooldown_seconds * (2 ** n), self.max_cooldown_seconds)
        health.record_failure(cooldown_seconds=cooldown)

    @staticmethod
    def _publish_attempt(cascade_id: str, attempt: _Attempt) -> None:
        """Emit a single ``CASCADE_ATTEMPT`` event."""
        Atlas.event_bus.publish(
            Event(
                kind=EventKind.CASCADE_ATTEMPT.value,
                payload={
                    "cascade_id": cascade_id,
                    "provider": attempt.name,
                    "status": attempt.status.value,
                    "reason": attempt.reason,
                },
            ),
        )

    @staticmethod
    def _record_cascade_to_trajectory(result: CascadeResult) -> None:
        """Append a ROUTING_DECISION-style step describing the cascade as a whole."""
        tr = current_trajectory.get()
        if tr is None:
            return
        with suppress(Exception):
            tr.add_step(
                {
                    "kind": "ROUTING_DECISION",
                    "data": {
                        "cascade": True,
                        **result.to_dict(),
                    },
                },
            )


def _otel_error_status(description: str) -> Any:
    """Return an OTel ``Status(StatusCode.ERROR, description)`` or ``None``.

    Deferred import keeps cascade.py import-safe when ``opentelemetry-api``
    isn't installed.
    """
    try:
        from opentelemetry.trace import Status, StatusCode
    except ImportError:
        return None
    return Status(StatusCode.ERROR, description)


__all__ = ["Cascade", "CascadeResult"]
