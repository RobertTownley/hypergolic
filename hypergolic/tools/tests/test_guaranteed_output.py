from hypergolic.harness.primitives.results import ToolResult
from hypergolic.ids import new_id
from hypergolic.tools.guaranteed_output import append_pending, drain, post

DENIAL = (
    "✗ user approval\n"
    "User denied tool call. Reason: See inline review comments.\n"
    "\n"
    "User annotations:\n"
    '- "settings.py:137": Remove this entire comment\n'
)


def test_appended_to_truncated_output():
    sid = new_id()
    post(sid, DENIAL)
    out = append_pending(
        ToolResult.text(" ! [remote rejected]   main -> main (hook declined)\n"), sid,
    )
    text = "".join(b["text"] for b in out.iter_text_blocks())
    assert "Remove this entire comment" in text
    assert drain(sid) == []


def test_skipped_when_visible_as_remote_lines():
    sid = new_id()
    post(sid, DENIAL)
    push_output = "".join(
        f"remote: {line}        \n" for line in DENIAL.splitlines()
    ) + " ! [remote rejected]   main -> main\n"
    out = append_pending(ToolResult.text(push_output), sid)
    assert len(out.content) == 1


def test_sessions_isolated_and_blank_posts_dropped():
    a, b = new_id(), new_id()
    post(a, "for a")
    post(b, "   \n")
    assert len(append_pending(ToolResult.text(""), b).content) == 1
    assert "for a" in append_pending(ToolResult.text(""), a).content[-1]["text"]


def test_survives_until_a_tool_result_drains_it():
    sid = new_id()
    post(sid, "first")
    post(sid, "second")
    out = append_pending(ToolResult.text("unrelated"), sid)
    text = "".join(b["text"] for b in out.iter_text_blocks())
    assert "first" in text and "second" in text
