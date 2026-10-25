"""Resolve an :class:`ApprovalView` against concrete tool input.

The resolver walks the view spec, pulls values from ``tool_input`` (or the
current iteration item for ``ForEachBlock`` templates), and returns a
:class:`ResolvedView` whose blocks are plain JSON-serializable dicts.

Behaviour is deliberately forgiving: a missing field renders as ``None``
rather than raising, so that optional tool inputs don't blow up the
approval UI.
"""

from __future__ import annotations

from typing import Any

from hypergolic.tools.approval_view import (
    ApprovalView,
    BadgeBlock,
    Block,
    CodeBlock,
    ForEachBlock,
    MarkdownBlock,
    ResolvedBlock,
    ResolvedView,
    TextBlock,
)


_LANG_BY_EXT: dict[str, str] = {
    "ts": "typescript", "tsx": "tsx", "js": "javascript", "jsx": "jsx",
    "py": "python", "rs": "rust", "go": "go", "rb": "ruby",
    "css": "css", "html": "html", "json": "json", "yaml": "yaml",
    "yml": "yaml", "toml": "toml", "md": "markdown", "sh": "bash",
    "bash": "bash", "sql": "sql", "xml": "xml", "swift": "swift",
    "kt": "kotlin", "java": "java", "cpp": "cpp", "c": "c", "h": "c",
}


def _infer_language(path: str) -> str:
    if not path:
        return ""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _LANG_BY_EXT.get(ext, "")


def _read_field(scope: Any, field: str) -> Any:
    """Pull ``field`` from ``scope``.

    ``field == "."`` returns the scope itself (for scalar items).
    Otherwise ``scope`` is expected to be a mapping; missing keys
    return ``None``.
    """
    if field == ".":
        return scope
    if isinstance(scope, dict):
        return scope.get(field)
    return getattr(scope, field, None)


def _resolve_code(block: CodeBlock, scope: Any) -> ResolvedBlock:
    if block.value is not None:
        value = block.value
    elif block.field is not None:
        raw = _read_field(scope, block.field)
        value = "" if raw is None else str(raw)
    else:
        value = ""

    language = block.language
    if not language and block.language_from_path:
        path_val = _read_field(scope, block.language_from_path)
        if isinstance(path_val, str):
            language = _infer_language(path_val)

    return {
        "type": "code",
        "value": value,
        "language": language,
        "label": block.label,
        "max_height": block.max_height,
    }


def _resolve_markdown(block: MarkdownBlock, scope: Any) -> ResolvedBlock:
    if block.value is not None:
        value = block.value
    elif block.field is not None:
        raw = _read_field(scope, block.field)
        value = "" if raw is None else str(raw)
    else:
        value = ""
    return {"type": "markdown", "value": value, "label": block.label}


def _resolve_text(block: TextBlock, scope: Any) -> ResolvedBlock:
    raw = _read_field(scope, block.field)
    return {
        "type": "text",
        "value": "" if raw is None else str(raw),
        "label": block.label,
        "mono": block.mono,
    }


def _resolve_badge(block: BadgeBlock, scope: Any) -> ResolvedBlock:
    raw = _read_field(scope, block.field)
    return {
        "type": "badge",
        "value": "" if raw is None else str(raw),
        "label": block.label,
        "tone": block.tone,
    }


def _resolve_for_each(block: ForEachBlock, scope: Any) -> ResolvedBlock:
    raw = _read_field(scope, block.field)
    items_raw = raw if isinstance(raw, list) else []

    resolved_items: list[dict[str, Any]] = []
    for item in items_raw:
        heading = None
        if block.item_heading is not None:
            heading_val = _read_field(item, block.item_heading)
            heading = "" if heading_val is None else str(heading_val)
        resolved_items.append({
            "heading": heading,
            "blocks": [_resolve_block(b, item) for b in block.template],
        })

    return {
        "type": "for_each",
        "label": block.label,
        "separator": block.separator,
        "empty_text": block.empty_text,
        "items": resolved_items,
    }


def _resolve_block(block: Block, scope: Any) -> ResolvedBlock:
    if isinstance(block, CodeBlock):
        return _resolve_code(block, scope)
    if isinstance(block, MarkdownBlock):
        return _resolve_markdown(block, scope)
    if isinstance(block, TextBlock):
        return _resolve_text(block, scope)
    if isinstance(block, BadgeBlock):
        return _resolve_badge(block, scope)
    if isinstance(block, ForEachBlock):
        return _resolve_for_each(block, scope)
    raise TypeError(f"Unknown approval-view block: {type(block).__name__}")


def resolve_approval_view(
    view: ApprovalView, tool_input: dict[str, Any],
) -> ResolvedView:
    """Return a :class:`ResolvedView` with all field references replaced."""
    blocks = [_resolve_block(b, tool_input) for b in view.blocks]
    return ResolvedView(blocks=blocks, show_raw_json=view.show_raw_json)
