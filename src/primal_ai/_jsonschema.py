"""Internal shared JSON-Schema-subset validator.

Used by ``guardian._builtins.schema_validator.SchemaValidator`` and
``verifier.domain.JSONSchemaVerifier``. Single source of truth so both
pillars enforce the same subset and produce the same error messages.

Supported subset:

  - ``type``: ``"object"`` | ``"array"`` | ``"string"`` | ``"number"`` |
    ``"integer"`` | ``"boolean"`` | ``"null"``.
  - ``required``: list of property names that must be present on an object.
  - ``properties``: mapping of property name → nested schema (validated
    recursively only when the key is present in the value).

Anything outside the subset is silently ignored — callers who need richer
schemas should reach for ``jsonschema`` in user code above this boundary.
"""

from __future__ import annotations

from typing import Any

_TYPE_TO_PY: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list, tuple),
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "null": (type(None),),
}


def validate(schema: dict[str, Any], value: Any) -> None:
    """Validate ``value`` against ``schema``. Raise ``ValueError`` on the first mismatch.

    Returns ``None`` on success. The exception message is a JSON-path-style
    string suitable for inclusion in user-facing error reports.
    """
    err = _walk(value, schema, path="$")
    if err is not None:
        raise ValueError(err)


def first_error(schema: dict[str, Any], value: Any) -> str | None:
    """Return the first validation error message, or ``None`` on success.

    A non-raising form of :func:`validate` for callers that already know
    they want to wrap the failure (Guardian wraps it in ``PolicyViolation``;
    Verifier wraps it in a FAIL ``Verdict``).
    """
    return _walk(value, schema, path="$")


def _walk(value: Any, schema: dict[str, Any], path: str) -> str | None:
    """Return the first error path/message walking ``value`` against ``schema``."""
    expected_type = schema.get("type")
    if expected_type is not None:
        py_types = _TYPE_TO_PY.get(expected_type)
        if py_types is None:
            return None  # Unknown type — silently skip per subset rules.
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
                err = _walk(value[key], sub_schema, f"{path}.{key}")
                if err is not None:
                    return err
    return None


__all__ = ["first_error", "validate"]
