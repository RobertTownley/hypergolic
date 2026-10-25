"""Token-saving reshaping of tool output.

Applies hook/progress collapsing (hook_shaping), grep-match grouping
(grep_shaping), then path-list grouping (path_shaping) to every text block of a ToolResult. Called once, in
tools/handlers, as the last step before the result is truncated,
persisted, and returned to the model — tool implementations and any
programmatic consumers of tool results see raw output. Gated by
``App(shape_grep_output=...)`` (named for the original grep shaper; it
 gates path-list shaping too), default True.
"""

from __future__ import annotations

from hypergolic.harness.primitives.results import ToolResult
from hypergolic.tools.grep_shaping import shape_grep_text
from hypergolic.tools.hook_shaping import shape_hook_text
from hypergolic.tools.path_shaping import shape_path_list_text
from hypergolic.harness.app.state import get_app


def _enabled() -> bool:
    try:
        return get_app().shape_grep_output
    except RuntimeError:
        return True


def _shape(text: str) -> str:
    return shape_path_list_text(shape_grep_text(shape_hook_text(text)))


def shape_tool_output(result: ToolResult) -> ToolResult:
    if not _enabled():
        return result
    content = [
        {**b, "text": _shape(b["text"])}
        if isinstance(b, dict) and b.get("type") == "text"
        else b
        for b in result.content
    ]
    if content == result.content:
        return result
    return ToolResult(content=content, is_error=result.is_error, meta=result.meta)
