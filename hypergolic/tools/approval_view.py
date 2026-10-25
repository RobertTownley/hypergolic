"""Declarative approval-UI specification for tools.

Tool authors attach an ``ApprovalView`` to a tool to control how the
approval prompt is rendered. The view is a tree of block primitives
(``CodeBlock``, ``MarkdownBlock``, ``TextBlock``, ``BadgeBlock``,
``ForEachBlock``) that reference fields on the tool's input.

The backend ``resolve_approval_view`` walks a view + a concrete
``tool_input`` and returns a ``ResolvedView`` with all field references
replaced by literal values. The UI is a pure renderer — it does no
field resolution of its own.

Field-resolution rules:

- At root scope, ``field`` reads ``tool_input[field]``.
- Inside a ``ForEachBlock`` template, ``field`` reads from the current
  item. For scalar items (e.g. ``list[str]``) use ``field="."`` or
  ``item_heading="."`` to refer to the item itself.
- ``item_heading`` is a bare field name (no interpolation). Its
  resolved value is rendered as a per-item header above the item's
  template output.
- ``language_from_path`` on a ``CodeBlock`` reads a sibling field's
  value as a file path and infers the syntax language from its
  extension.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Union


# ─── Block primitives ──────────────────────────────────────────────


@dataclass
class CodeBlock:
    """Syntax-highlighted code.

    Provide exactly one of ``field`` or ``value``.
    ``max_height`` accepts ``"half"``, ``"third"``, ``"auto"``, or an
    integer number of pixels.
    """

    field: str | None = None
    value: str | None = None
    language: str = ""
    language_from_path: str | None = None
    label: str | None = None
    max_height: str | int = "half"
    type: Literal["code"] = "code"


@dataclass
class MarkdownBlock:
    field: str | None = None
    value: str | None = None
    label: str | None = None
    type: Literal["markdown"] = "markdown"


@dataclass
class TextBlock:
    field: str
    label: str | None = None
    mono: bool = False
    type: Literal["text"] = "text"


@dataclass
class BadgeBlock:
    field: str
    label: str | None = None
    tone: Literal["neutral", "warn", "danger", "info"] = "neutral"
    type: Literal["badge"] = "badge"


@dataclass
class ForEachBlock:
    """Iterate a list field and render ``template`` once per item.

    Inside the template, ``field`` references resolve against the
    current item. Use ``"."`` to refer to a scalar item itself.
    """

    field: str
    template: list["Block"] = field(default_factory=list)
    item_heading: str | None = None
    label: str | None = None
    separator: Literal["divider", "gap", "none"] = "divider"
    empty_text: str | None = None
    type: Literal["for_each"] = "for_each"


Block = Union[CodeBlock, MarkdownBlock, TextBlock, BadgeBlock, ForEachBlock]


@dataclass
class ApprovalView:
    blocks: list[Block]
    show_raw_json: bool = True


# ─── Resolved (serializable) view ──────────────────────────────────

# The resolved tree is a plain list of dicts, safe to JSON-serialize
# straight to the UI. Each block has the same ``type`` discriminator
# as its spec counterpart plus concrete ``value``/``items``/``label``
# fields. We intentionally use dicts rather than dataclasses here so
# the wire format is obvious and easy to extend.

ResolvedBlock = dict[str, Any]


@dataclass
class ResolvedView:
    blocks: list[ResolvedBlock]
    show_raw_json: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"blocks": self.blocks, "show_raw_json": self.show_raw_json}


def shell_view(command: str) -> ResolvedView:
    return ResolvedView(
        blocks=[{
            "type": "code",
            "value": command,
            "language": "bash",
            "label": None,
            "max_height": "half",
        }],
    )


def shell_presentation(tool_input: dict[str, Any]) -> tuple[str, ResolvedView] | None:
    """``(display_name, view)`` for a pending `cmd` approval.

    The tool is always `cmd` and its input is always a shell line, so the
    presentation is the shell line — the one thing it actually is. Rich per-tool
    views still exist, but they belong to the *broker* invocation of an individual
    command, which raises its own approval card while this one is still running.

    ``None`` when the input isn't a shell string, leaving the caller's generic
    presentation in place.
    """
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return None
    container = tool_input.get("container")
    name = f"Command ({container})" if container else "Command"
    return name, shell_view(command)
