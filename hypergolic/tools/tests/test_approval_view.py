"""Tests for ApprovalView resolution."""

from hypergolic.tools.approval_view import (
    ApprovalView,
    BadgeBlock,
    CodeBlock,
    ForEachBlock,
    MarkdownBlock,
    TextBlock,
)
from hypergolic.tools.approval_view_resolver import resolve_approval_view


# ── Single-block resolution ────────────────────────────────────────


def test_code_block_from_field():
    view = ApprovalView(blocks=[CodeBlock(field="command", language="bash")])
    resolved = resolve_approval_view(view, {"command": "ls -la"})
    (block,) = resolved.blocks
    assert block == {
        "type": "code",
        "value": "ls -la",
        "language": "bash",
        "label": None,
        "max_height": "half",
    }


def test_code_block_literal_value():
    view = ApprovalView(blocks=[CodeBlock(value="static", language="json")])
    resolved = resolve_approval_view(view, {})
    assert resolved.blocks[0]["value"] == "static"


def test_code_block_missing_field_is_empty():
    view = ApprovalView(blocks=[CodeBlock(field="missing")])
    resolved = resolve_approval_view(view, {})
    assert resolved.blocks[0]["value"] == ""


def test_code_block_language_from_path():
    view = ApprovalView(blocks=[
        ForEachBlock(
            field="files",
            template=[CodeBlock(field="content", language_from_path="path")],
        )
    ])
    resolved = resolve_approval_view(view, {
        "files": [{"path": "a.py", "content": "x=1"}],
    })
    inner = resolved.blocks[0]["items"][0]["blocks"][0]
    assert inner["language"] == "python"


def test_code_block_explicit_language_wins_over_path():
    view = ApprovalView(blocks=[
        ForEachBlock(
            field="files",
            template=[CodeBlock(
                field="content", language="bash", language_from_path="path",
            )],
        )
    ])
    resolved = resolve_approval_view(view, {
        "files": [{"path": "a.py", "content": "echo"}],
    })
    inner = resolved.blocks[0]["items"][0]["blocks"][0]
    assert inner["language"] == "bash"


def test_markdown_block_from_field():
    view = ApprovalView(blocks=[MarkdownBlock(field="doc")])
    resolved = resolve_approval_view(view, {"doc": "# hi"})
    assert resolved.blocks[0] == {"type": "markdown", "value": "# hi", "label": None}


def test_text_block_stringifies_non_strings():
    view = ApprovalView(blocks=[TextBlock(field="n", label="Count")])
    resolved = resolve_approval_view(view, {"n": 42})
    assert resolved.blocks[0] == {
        "type": "text", "value": "42", "label": "Count", "mono": False,
    }


def test_badge_block():
    view = ApprovalView(blocks=[BadgeBlock(field="cwd", label="CWD", tone="info")])
    resolved = resolve_approval_view(view, {"cwd": "/tmp"})
    assert resolved.blocks[0] == {
        "type": "badge", "value": "/tmp", "label": "CWD", "tone": "info",
    }


# ── ForEachBlock ────────────────────────────────────────────────


def test_for_each_dict_items_with_heading():
    view = ApprovalView(blocks=[
        ForEachBlock(
            field="files",
            item_heading="path",
            template=[CodeBlock(field="content", language_from_path="path")],
        )
    ])
    resolved = resolve_approval_view(view, {
        "files": [
            {"path": "a.py", "content": "x=1"},
            {"path": "b.ts", "content": "const x=1"},
        ],
    })
    items = resolved.blocks[0]["items"]
    assert [it["heading"] for it in items] == ["a.py", "b.ts"]
    assert items[0]["blocks"][0]["language"] == "python"
    assert items[1]["blocks"][0]["language"] == "typescript"


def test_for_each_scalar_items_with_dot_heading():
    view = ApprovalView(blocks=[
        ForEachBlock(field="paths", item_heading=".", template=[])
    ])
    resolved = resolve_approval_view(view, {"paths": ["a.txt", "b.txt"]})
    items = resolved.blocks[0]["items"]
    assert [it["heading"] for it in items] == ["a.txt", "b.txt"]
    assert items[0]["blocks"] == []


def test_for_each_empty_list_preserves_empty_text():
    view = ApprovalView(blocks=[
        ForEachBlock(field="files", template=[], empty_text="Nothing to do.")
    ])
    resolved = resolve_approval_view(view, {"files": []})
    block = resolved.blocks[0]
    assert block["items"] == []
    assert block["empty_text"] == "Nothing to do."


def test_for_each_missing_field_renders_empty_items():
    view = ApprovalView(blocks=[
        ForEachBlock(field="nope", template=[])
    ])
    resolved = resolve_approval_view(view, {})
    assert resolved.blocks[0]["items"] == []


def test_for_each_edit_files_shape():
    """edit_files-style: each item has old/new strings rendered as two code blocks."""
    view = ApprovalView(blocks=[
        ForEachBlock(
            field="files",
            item_heading="path",
            template=[
                CodeBlock(field="old_str", language_from_path="path", label="Find"),
                CodeBlock(field="new_str", language_from_path="path", label="Replace"),
            ],
        )
    ])
    resolved = resolve_approval_view(view, {
        "files": [{
            "path": "x.py", "old_str": "foo", "new_str": "bar",
        }],
    })
    (item,) = resolved.blocks[0]["items"]
    assert item["heading"] == "x.py"
    find, replace = item["blocks"]
    assert find == {
        "type": "code", "value": "foo", "language": "python",
        "label": "Find", "max_height": "half",
    }
    assert replace["value"] == "bar"
    assert replace["label"] == "Replace"


# ── Top-level ─────────────────────────────────────────────────────


def test_resolved_view_preserves_show_raw_json():
    view = ApprovalView(blocks=[], show_raw_json=False)
    resolved = resolve_approval_view(view, {})
    assert resolved.show_raw_json is False
    assert resolved.to_dict() == {"blocks": [], "show_raw_json": False}
