"""Shared JSON-schema transforms for tool-schema payloads sent to the model.

Each transform mutates the schema in-place.

The pipeline used by :func:`hypergolic.tools.wire.wire_schema` is :func:`optimize_schema`, which
applies (in order):

1. :func:`resolve_refs`            — inline ``$ref`` / drop ``$defs``
2. :func:`strip_schema_noise`      — drop ``title``, empty ``description``, ``additionalProperties``
3. :func:`collapse_nullable_anyof` — ``anyOf: [{type: T}, {type: null}]`` → ``type: [T, null]``
4. :func:`drop_default_null`       — remove redundant ``default: null`` on already-nullable fields

Transforms 3 and 4 are pure token-efficiency wins validated against Anthropic
``count_tokens`` input_tokens.
"""

from __future__ import annotations


def resolve_refs(schema: dict) -> None:
    """Inline ``$ref`` references and drop ``$defs`` from the schema."""
    defs = schema.get("$defs", {})
    if not defs:
        return

    def _resolve(node: dict) -> dict:
        if "$ref" in node:
            ref_path = node["$ref"]  # e.g. "#/$defs/SkillIdEnum"
            parts = ref_path.lstrip("#/").split("/")
            resolved = defs
            for part in parts[1:]:  # skip "$defs" prefix
                resolved = resolved[part]
            return dict(resolved)
        for key, value in list(node.items()):
            if isinstance(value, dict):
                node[key] = _resolve(value)
            elif isinstance(value, list):
                node[key] = [
                    _resolve(item) if isinstance(item, dict) else item
                    for item in value
                ]
        return node

    _resolve(schema)
    schema.pop("$defs", None)


def strip_schema_noise(schema: dict) -> None:
    """Resolve refs, drop ``title`` and ``additionalProperties``.

    Applied recursively. Safe to call on any JSON-schema fragment. The
    ``properties`` map is recursed into value-by-value so a *field named*
    ``title`` is never mistaken for schema noise.
    """
    resolve_refs(schema)
    _strip_noise(schema)


def _strip_noise(schema: dict) -> None:
    schema.pop("title", None)
    if schema.get("description") == "":
        schema.pop("description")
    if isinstance(schema.get("additionalProperties"), bool):
        schema.pop("additionalProperties")
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            for prop_schema in value.values():
                if isinstance(prop_schema, dict):
                    _strip_noise(prop_schema)
        elif isinstance(value, dict):
            _strip_noise(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _strip_noise(item)


def collapse_nullable_anyof(schema: dict) -> None:
    """Collapse ``anyOf: [{type: T}, {type: null}]`` into ``type: [T, null]``.

    Pydantic emits ``Optional[X]`` as ``anyOf: [{type: X}, {type: null}]``. The
    equivalent shorthand ``type: [X, null]`` is accepted by Anthropic and uses
    roughly 40% fewer tokens. Applied recursively.

    Only collapses the "simple" shape — an anyOf of exactly two branches where
    each branch is just ``{type: <scalar>}``. More complex anyOf forms (with
    ``enum``, ``items``, nested objects, etc.) are left alone so semantics are
    preserved.
    """
    any_of = schema.get("anyOf")
    if (
        isinstance(any_of, list)
        and len(any_of) == 2
        and all(isinstance(b, dict) for b in any_of)
        and all(set(b.keys()) == {"type"} for b in any_of)
        and all(isinstance(b["type"], str) for b in any_of)
    ):
        types = [b["type"] for b in any_of]
        if "null" in types:
            non_null = next(t for t in types if t != "null")
            schema.pop("anyOf")
            schema["type"] = [non_null, "null"]

    for value in schema.values():
        if isinstance(value, dict):
            collapse_nullable_anyof(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    collapse_nullable_anyof(item)


def drop_default_null(schema: dict) -> None:
    """Remove ``default: null`` where the field is already nullable.

    For ``Optional[X] = None``, Pydantic emits both a nullable type AND
    ``default: null``. The default is inferrable from the nullable type, so
    stripping it saves tokens without changing behavior. Applied recursively.

    A field is considered "already nullable" if either:
      - ``type`` is a list containing ``"null"`` (post-:func:`collapse_nullable_anyof`), or
      - ``anyOf`` contains a branch with ``{type: null}`` (pre-collapse shape).
    """
    if "default" in schema and schema["default"] is None:
        type_val = schema.get("type")
        is_nullable_type = isinstance(type_val, list) and "null" in type_val
        any_of = schema.get("anyOf")
        has_null_branch = isinstance(any_of, list) and any(
            isinstance(b, dict) and b.get("type") == "null" for b in any_of
        )
        if is_nullable_type or has_null_branch:
            schema.pop("default")

    for value in schema.values():
        if isinstance(value, dict):
            drop_default_null(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    drop_default_null(item)


def optimize_schema(schema: dict) -> None:
    """Apply the full pipeline used when sending tool schemas to the model."""
    strip_schema_noise(schema)
    collapse_nullable_anyof(schema)
    drop_default_null(schema)
