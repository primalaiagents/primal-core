"""``SchemaValidator`` — minimal JSON-Schema-subset validation, stdlib only.

The actual schema-walk logic lives in :mod:`primal_ai._jsonschema` so that
Guardian's policy layer and Verifier's domain layer enforce exactly the
same subset and produce identical error messages.
"""

from __future__ import annotations

from typing import Any

from primal_ai._jsonschema import first_error
from primal_ai.guardian._policy import PolicyViolation


class SchemaValidator:
    """Validate wrapped-agent args and/or results against a small schema dialect.

    Args:
        pre_schema: Schema applied to the call's args/kwargs as a dict
            ``{"args": (...), "kwargs": {...}}``. Optional.
        post_schema: Schema applied to the agent's return value. Optional.

    Example:
        >>> from primal_ai import SchemaValidator
        >>> SchemaValidator(post_schema={
        ...     "type": "object",
        ...     "required": ["answer"],
        ...     "properties": {"answer": {"type": "string"}},
        ... })
        <...>
    """

    name = "schema"

    def __init__(
        self,
        pre_schema: dict[str, Any] | None = None,
        post_schema: dict[str, Any] | None = None,
    ) -> None:
        self.pre_schema = pre_schema
        self.post_schema = post_schema

    def check_pre(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        """Validate the call args/kwargs against ``pre_schema`` if configured."""
        if self.pre_schema is None:
            return
        payload = {"args": list(args), "kwargs": dict(kwargs)}
        err = first_error(self.pre_schema, payload)
        if err is not None:
            raise PolicyViolation(
                policy_name=self.name,
                reason=err,
                phase="pre",
                context={"schema": self.pre_schema},
            )

    def check_post(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        result: Any,
    ) -> None:
        """Validate the agent's result against ``post_schema`` if configured."""
        del args, kwargs
        if self.post_schema is None:
            return
        err = first_error(self.post_schema, result)
        if err is not None:
            raise PolicyViolation(
                policy_name=self.name,
                reason=err,
                phase="post",
                context={"schema": self.post_schema},
            )


def factory(arg: str) -> SchemaValidator:
    """DSL factory — the schema dialect isn't string-friendly, so the no-arg form is a no-op."""
    del arg
    return SchemaValidator()


__all__ = ["SchemaValidator", "factory"]
