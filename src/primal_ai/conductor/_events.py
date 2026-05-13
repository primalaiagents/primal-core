"""``Event`` + ``EventKind`` + ``EventBus`` — sync pub/sub for orchestration lifecycle events."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventKind(StrEnum):
    """Canonical event kinds the Conductor emits. Custom string kinds are also allowed."""

    AGENT_REGISTERED = "AGENT_REGISTERED"
    AGENT_UNREGISTERED = "AGENT_UNREGISTERED"
    DELEGATION_STARTED = "DELEGATION_STARTED"
    DELEGATION_COMPLETED = "DELEGATION_COMPLETED"
    DELEGATION_FAILED = "DELEGATION_FAILED"
    PIPELINE_STARTED = "PIPELINE_STARTED"
    PIPELINE_STEP_COMPLETED = "PIPELINE_STEP_COMPLETED"
    PIPELINE_COMPLETED = "PIPELINE_COMPLETED"
    PIPELINE_FAILED = "PIPELINE_FAILED"


def _new_event_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Event:
    """A single bus message — kind, payload, and timestamps.

    ``kind`` is a plain ``str`` so callers may publish custom event kinds
    beyond the ``EventKind`` enum.
    """

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=_new_event_id)
    timestamp: float = field(default_factory=time.time)
    monotonic: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of this event."""
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "payload": dict(self.payload),
            "timestamp": self.timestamp,
            "monotonic": self.monotonic,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Event:
        """Rebuild an ``Event`` from a ``to_dict`` payload."""
        return cls(
            kind=str(payload["kind"]),
            payload=dict(payload.get("payload") or {}),
            event_id=str(payload.get("event_id") or _new_event_id()),
            timestamp=float(payload.get("timestamp") or time.time()),
            monotonic=float(payload.get("monotonic") or time.monotonic()),
        )


Handler = Callable[[Event], None]


class EventBus:
    """Thread-safe synchronous pub/sub.

    ``subscribe(kind=None, handler)`` returns a subscription id; passing
    ``None`` for ``kind`` is a wildcard (handler receives every event).
    ``publish(event)`` invokes all matching handlers in registration order
    and silently swallows any handler exception — handlers must not be
    able to break the publisher or starve sibling subscribers.

    Async ``EventBus`` is documented as Phase 2 work; the MVP is sync only.

    Example:
        >>> from primal_ai import Event, EventBus, EventKind
        >>> bus = EventBus()
        >>> received = []
        >>> bus.subscribe(EventKind.DELEGATION_STARTED, received.append)
        '...'
        >>> bus.publish(Event(kind=EventKind.DELEGATION_STARTED.value, payload={}))
    """

    def __init__(self) -> None:
        # subscription_id → (kind|None, handler)
        self._subscriptions: dict[str, tuple[str | None, Handler]] = {}
        self._lock = threading.Lock()

    def subscribe(
        self,
        kind: str | EventKind | None,
        handler: Handler,
    ) -> str:
        """Register ``handler`` for events of ``kind`` (or all, when ``kind=None``)."""
        sub_id = uuid.uuid4().hex
        kind_value: str | None
        if kind is None:
            kind_value = None
        elif isinstance(kind, EventKind):
            kind_value = kind.value
        else:
            kind_value = kind
        with self._lock:
            self._subscriptions[sub_id] = (kind_value, handler)
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a previously-registered handler. No-op if the id is unknown."""
        with self._lock:
            self._subscriptions.pop(subscription_id, None)

    def publish(self, event: Event) -> None:
        """Fan ``event`` out to every matching subscriber. Handler errors are suppressed."""
        # Snapshot the subscriber list so a handler that mutates the bus
        # (subscribe/unsubscribe) during dispatch doesn't deadlock or skip
        # peers. We invoke OUTSIDE the lock so a slow handler doesn't
        # block other publishers.
        with self._lock:
            snapshot = list(self._subscriptions.values())
        for kind_value, handler in snapshot:
            if kind_value is not None and kind_value != event.kind:
                continue
            with suppress(Exception):
                handler(event)


__all__ = ["Event", "EventBus", "EventKind", "Handler"]
