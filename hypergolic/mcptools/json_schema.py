from typing import Any

_UNTYPED = "untyped"

JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def declared_types(prop_schema: Any) -> list[str]:
    """The types a property claims, however it spells the claim.

    An optional string reaches us as ``type: ["string", "null"]`` from one server
    and as ``anyOf: [{"type": "string"}, ...]`` from the next — pydantic-backed
    servers all use the latter — so a reader of only ``type`` sees no type at all
    for the most common declaration there is.
    """
    if not isinstance(prop_schema, dict):
        return []
    raw_type = prop_schema.get("type")
    if isinstance(raw_type, str):
        types = [raw_type]
    elif isinstance(raw_type, list):
        types = [t for t in raw_type if isinstance(t, str)]
    else:
        types = []
    for key in ("anyOf", "oneOf"):
        for variant in prop_schema.get(key) or []:
            types.extend(declared_types(variant) or [_UNTYPED])
    return types


def python_type_for(prop_schema: Any) -> tuple[Any, bool]:
    types = declared_types(prop_schema)
    non_null = list(dict.fromkeys(t for t in types if t != "null"))
    python_type = JSON_TYPE_MAP.get(non_null[0], Any) if len(non_null) == 1 else Any
    return python_type, "null" in types
