"""Domain-specific verifiers — ImageReward, JSON-schema, code execution, etc.

The final verification layer. Plug-in checkers for task-specific quality
(image aesthetics, structured-output validity, executable code, etc.).
"""

from __future__ import annotations

from typing import Any


class DomainVerifier:
    """Plug-in domain-specific verifier. STUB.

    Examples of planned domain verifiers:
      - ImageReward (aesthetic score for generated images)
      - JSON-schema validators
      - Code execution sandboxes
      - SQL syntax / EXPLAIN-cost checkers

    NOTE: Stub only. Full implementation extracted in Phase 2.
    """

    @classmethod
    def verify(
        cls,
        output: Any,
        domain: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify an output for a given domain. STUB."""
        raise NotImplementedError("DomainVerifier.verify will be implemented in Phase 2")
