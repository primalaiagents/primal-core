"""``Capability`` + ``AgentCard`` — the discoverable surface of every agent.

These dataclasses are the **PRIMAL precursor to A2A v1.0 AgentCards**.
Field names are deliberately chosen so a Phase 2.5 serializer can map
them 1:1 to A2A wire format without renames or schema gymnastics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Capability:
    """A single capability advertised by an agent (precursor to A2A capability).

    ``input_schema`` / ``output_schema`` (when present) use PRIMAL's shared
    JSON Schema subset (see :mod:`primal_ai._jsonschema`) — the same one
    Guardian's ``SchemaValidator`` and Verifier's ``JSONSchemaVerifier``
    enforce. Schemas are optional; many capabilities don't need them.

    Args:
        name: Stable identifier (e.g. ``"summarize"``, ``"book_flight"``).
        description: One-line human-readable explanation.
        input_schema: Optional JSON Schema for the input payload.
        output_schema: Optional JSON Schema for the output payload.
        tags: Free-form labels used by ``Conductor.find(tag=...)``.

    Example:
        >>> from primal_ai import Capability
        >>> Capability(
        ...     name="summarize",
        ...     description="Summarize a text input",
        ...     input_schema={"type": "string"},
        ...     tags=("writing", "nlp"),
        ... )
        Capability(...)
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Capability:
        """Rebuild a ``Capability`` from a ``to_dict`` payload."""
        return cls(
            name=str(payload["name"]),
            description=str(payload.get("description") or ""),
            input_schema=payload.get("input_schema"),
            output_schema=payload.get("output_schema"),
            tags=tuple(payload.get("tags") or ()),
        )


@dataclass(frozen=True)
class AgentCard:
    """The advertised identity of an agent — name, description, capabilities.

    This is the **PRIMAL precursor to A2A v1.0's AgentCard**. The Phase 2.5
    A2A serializer will map these fields 1:1 to A2A wire format:

    - ``name`` / ``description``  → A2A AgentCard ``name`` / ``description``
    - ``capabilities``            → A2A AgentCard ``capabilities`` array
    - ``version``                 → A2A AgentCard ``version``
    - ``metadata``                → A2A AgentCard ``extensions`` (free-form)

    Args:
        name: Globally unique identifier within a Conductor registry.
        description: One-line human-readable summary.
        capabilities: Tuple of ``Capability`` objects.
        version: SemVer-style version string. Defaults to ``"0.0.1"``.
        metadata: Vendor-specific extensions (model, provider, hints).

    Example:
        >>> from primal_ai import AgentCard, Capability
        >>> AgentCard(
        ...     name="researcher",
        ...     description="A research-specialized agent",
        ...     capabilities=(Capability(name="summarize", description="..."),),
        ... )
        AgentCard(...)
    """

    name: str
    description: str = ""
    capabilities: tuple[Capability, ...] = ()
    version: str = "0.0.1"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view, suitable for A2A AgentCard mapping."""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "version": self.version,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AgentCard:
        """Rebuild an ``AgentCard`` from a ``to_dict`` payload."""
        caps_raw = payload.get("capabilities") or []
        return cls(
            name=str(payload["name"]),
            description=str(payload.get("description") or ""),
            capabilities=tuple(Capability.from_dict(c) for c in caps_raw),
            version=str(payload.get("version") or "0.0.1"),
            metadata=dict(payload.get("metadata") or {}),
        )

    def has_capability(self, name: str) -> bool:
        """Return True iff this card advertises a capability called ``name``."""
        return any(c.name == name for c in self.capabilities)

    def has_tag(self, tag: str) -> bool:
        """Return True iff any capability on this card carries ``tag``."""
        return any(tag in c.tags for c in self.capabilities)


__all__ = ["AgentCard", "Capability"]
