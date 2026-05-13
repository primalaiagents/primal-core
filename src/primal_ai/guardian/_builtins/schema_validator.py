"""``SchemaValidator`` — minimal JSON-Schema-subset validation, stdlib only.

The supported subset is intentionally small:

  - ``type``: one of ``"object"``, ``"array"``, ``"string"``, ``"number"``,
    ``"integer"``, ``"boolean"``, ``"null"``.
  - ``required``: list of property names that must be present on an object.
  - ``properties``: mapping from property name → nested schema (validated
    recursively for keys that are present).

Anything outside this subset is silently ignored. For richer validation,
use jsonschema in a downstream policy wrapper.
"""

from __future__ import annotations

from typing import Any

from primal_ai.guardian._policy import PolicyViolation

_TYPE_TO_PY: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list, tuple),
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "null": (type(None),),
}


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
        err = _validate(payload, self.pre_schema, path="$")
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
        err = _validate(result, self.post_schema, path="$")
        if err is not None:
            raise PolicyViolation(
                policy_name=self.name,
                reason=err,
                phase="post",
                context={"schema": self.post_schema},
            )


def _validate(value: Any, schema: dict[str, Any], path: str) -> str | None:
    """Return an error message describing the first violation, or ``None``."""
    expected_type = schema.get("type")
    if expected_type is not None:
        py_types = _TYPE_TO_PY.get(expected_type)
        if py_types is None:
            return None  # Unknown type — silently skip (subset).
        # ``bool`` is a subclass of ``int``; disambiguate explicitly.
        if expected_type == "integer" and isinstance(value, bool):
            return f"{path}: expected integer, got boolean"
        if expected_type == "boolean" and not isinstance(value, bool):
            return f"{path}: expected boolean, got {type(value).__name__}"
        if not isinstance(value, py_types):
            return f"{path}: expected {expected_type}, got {type(value).__name__}"

    if expected_type == "object" and isinstance(value, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                return f"{path}.{key}: required property missing"
        properties = schema.get("properties") or {}
        for key, sub_schema in properties.items():
            if key in value:
                err = _validate(value[key], sub_schema, f"{path}.{key}")
                if err is not None:
                    return err
    return None


def factory(arg: str) -> SchemaValidator:
    """DSL factory — the schema dialect isn't string-friendly, so the no-arg form is a no-op."""
    del arg
    return SchemaValidator()


__all__ = ["SchemaValidator", "factory"]
