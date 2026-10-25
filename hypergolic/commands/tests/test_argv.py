"""Parser tests against the *real* command input models, so a schema change
that outgrows its CLI surface fails here rather than mid-invocation.

This is the code path every broker invocation crosses: the shell hands over
tokens, and what the policy judges and the handler receives is whatever these
parsers make of them.
"""

import pytest
from pydantic import BaseModel

from hypergolic.commands.argv import infer_parser, parser_for, usage_for
from hypergolic.commands.parsers import UsageError
from hypergolic.contrib.tools.apropos import apropos_tool
from hypergolic.contrib.tools.command import command_tool
from hypergolic.contrib.tools.dispatch import build_dispatch_tool
from hypergolic.contrib.tools.git_sync import git_fetch_tool
from hypergolic.contrib.tools.history import history_command
from hypergolic.contrib.tools.land import LandTool
from hypergolic.contrib.tools.pull_request import pull_request_tool
from hypergolic.contrib.tools.readiness import readiness_probes_tool
from hypergolic.contrib.tools.review import ReviewTool
from hypergolic.dispatch.conclude import ConcludeTool
from hypergolic.harness.primitives.tool import Tool


def parse(tool: Tool, argv: list[str]):
    parsed = parser_for(tool.argv, tool.input_schema)(argv)
    assert parsed is not None, "a resolved command must never yield no input"
    return parsed


def _dispatch_tool() -> Tool:
    tool = build_dispatch_tool(["worker"])
    assert tool is not None
    return tool


def test_joined_tail_keeps_prose_intact():
    out = parse(ReviewTool, ["Focus", "on", "the", "gate", "model"])
    assert out.context == "Focus on the gate model"


def test_history_takes_raw_sql():
    out = parse(history_command, ["select", "*", "from", "sessions"])
    assert out.query == "select * from sessions"


def test_optional_joined_tail_allows_empty():
    assert parse(ReviewTool, []).context == ""


def test_flags_and_positional_mix():
    out = parse(git_fetch_tool, ["--pr", "1529"])
    assert out.pr == 1529
    out = parse(ReviewTool, ["--repo", "shared", "check", "docs"])
    assert (out.repo, out.context) == ("shared", "check docs")


def test_git_fetch_pr_flag_coerces_int():
    assert parse(git_fetch_tool, ["--pr", "1529"]).pr == 1529
    assert parse(git_fetch_tool, []).pr is None


def test_pull_request_publish_flags():
    out = parse(
        pull_request_tool,
        [
            "publish", "b", "--title", "Add the thing", "--body=Details here",
            "--reviewer", "a", "--reviewer", "c", "--no-draft",
        ],
    )
    assert (out.action, out.branch, out.title, out.body) == ("publish", "b", "Add the thing", "Details here")
    assert (out.reviewer, out.draft) == (["a", "c"], False)
    listed = parse(pull_request_tool, ["list"])
    assert (listed.action, listed.author, listed.state, listed.draft) == ("list", "@me", "open", True)


def test_unknown_flag_is_a_usage_error_not_a_positional():
    with pytest.raises(UsageError, match="unknown flag"):
        parse(pull_request_tool, ["publish", "b", "--drafts"])


def test_host_single_arg_is_a_host_shell_line():
    out = parse(command_tool, ["git log | head"])
    assert out.commands == ["git log | head"]


def test_host_many_args_are_an_exact_argv():
    out = parse(command_tool, ["sh", "-c", "a && b"])
    assert out.commands == ["sh -c 'a && b'"]


def test_host_flags_after_command_belong_to_it():
    out = parse(command_tool, ["--cwd", "/tmp", "git", "merge", "--ff-only", "X"])
    assert (out.commands, out.working_directory) == (["git merge --ff-only X"], "/tmp")


def test_host_timeout_flag():
    out = parse(command_tool, ["--timeout", "300", "make", "build"])
    assert (out.commands, out.timeout) == (["make build"], 300)


def test_negated_flag_flips_default():
    out = parse(ConcludeTool, ["success", "--keep-worktree", "Shipped", "it"])
    assert (out.outcome, out.conclusion) == ("success", "Shipped it")
    assert out.delete_worktree is False and out.merge_ready is False


def test_invalid_enum_value_is_a_usage_error():
    with pytest.raises(UsageError, match="invalid arguments"):
        parse(ConcludeTool, ["maybe", "hmm"])


def test_double_dash_ends_flag_parsing():
    """Prose that starts with dashes stays expressible via flags."""
    out = parse(ConcludeTool, ["success", "--", "--force", "was", "wrong"])
    assert out.conclusion == "--force was wrong"


def test_inferred_passthrough_for_list_of_str():
    """A `gh`-shaped command (one list[str] field) needs no registration."""

    class Args(BaseModel):
        args: list[str]

    out = infer_parser(Args)(["pr", "list", "--limit", "5"])
    assert out is not None and out.model_dump() == {"args": ["pr", "list", "--limit", "5"]}


def test_a_schema_less_command_takes_no_arguments_but_still_parses():
    parsed = parser_for(None, None)([])
    assert parsed is not None and parsed.model_dump() == {}
    with pytest.raises(UsageError):
        parser_for(None, None)(["now"])


def test_every_declared_parser_declares_its_usage():
    """UsageError and `--help` both quote usage; a declared parser without one
    would advertise the JSON form it does not accept."""
    tools = [
        apropos_tool, command_tool, _dispatch_tool(), git_fetch_tool, LandTool,
        pull_request_tool, readiness_probes_tool, ReviewTool, ConcludeTool,
    ]
    assert [t.id for t in tools if t.argv and not t.usage] == []


class _Query(BaseModel):
    query: str


def test_usage_falls_back_to_the_schema_for_an_undeclared_command():
    assert usage_for("probe", _Query) == "probe <query...>"
    assert usage_for("probe", None) == "probe"


def test_dispatch_role_then_prompt_with_flags():
    out = parse(
        _dispatch_tool(),
        ["worker", "fix", "the", "bug", "--tier", "Low", "--attach", "a.py", "--attach", "b.py"],
    )
    assert out.role.value == "worker"
    assert out.prompt == "fix the bug"
    assert out.model_tier.value == "Low"
    assert out.file_references == ["a.py", "b.py"]


def test_dispatch_standalone_without_role():
    out = parse(
        _dispatch_tool(),
        ["--standalone", "--project", "acme", "--no-wait", "fix", "hooks"],
    )
    assert out.role is None
    assert out.child is False
    assert out.wait is False
    assert out.project == "acme"
    assert out.prompt == "fix hooks"


def test_dispatch_without_prompt_is_usage_error():
    with pytest.raises(UsageError):
        parse(_dispatch_tool(), ["worker"])


def test_dispatch_resume_mock_with_result_and_error():
    out = parse(
        _dispatch_tool(),
        ["--resume", "R1", "--outcome", "mock", "--result", '{"ok": false}', "--error"],
    )
    assert out.resume == "R1"
    assert out.outcome.value == "mock"
    assert out.result == '{"ok": false}'
    assert out.result_is_error is True


def test_dispatch_eval_conducts():
    out = parse(_dispatch_tool(), ["worker", "fix", "it", "--eval"])
    assert out.conduct is True and out.prompt == "fix it"


def test_dispatch_reply():
    out = parse(_dispatch_tool(), ["--reply", "C1", "one", "retry"])
    assert out.reply == "C1" and out.prompt == "one retry"


def test_dispatch_conclude():
    out = parse(_dispatch_tool(), ["--conclude", "C1", "--keep-branch"])
    assert out.conclude == "C1" and out.keep_branch is True


def test_dispatch_conclude_needs_a_child():
    with pytest.raises(UsageError):
        parse(_dispatch_tool(), ["--conclude"])


def test_dispatch_conclude_takes_no_text():
    with pytest.raises(UsageError):
        parse(_dispatch_tool(), ["--conclude", "C1", "now"])


def test_dispatch_one_operation_at_a_time():
    with pytest.raises(UsageError):
        parse(_dispatch_tool(), ["--reply", "C1", "--conclude", "C1", "hi"])


@pytest.mark.parametrize("word", ["reply", "conclude", "resume"])
def test_dispatch_leading_operation_word_is_prompt(word):
    out = parse(_dispatch_tool(), [word, "to", "this", "message"])
    assert out.reply is None and out.conclude is None and out.resume is None
    assert out.prompt == f"{word} to this message"


def test_dispatch_app_override_flags():
    out = parse(_dispatch_tool(), [
        "fix", "it", "--strip-history-thinking=false", "--truncate-token-threshold", "90000",
        "--turn-compaction-floor-tokens=0", "--shape-grep-output=true",
    ])
    assert out.prompt == "fix it"
    assert out.set_values() == {
        "strip_history_thinking": False, "truncate_token_threshold": 90000,
        "turn_compaction_floor_tokens": 0, "shape_grep_output": True,
    }


def test_dispatch_without_override_flags_sets_none():
    assert parse(_dispatch_tool(), ["fix", "it"]).set_values() == {}


def test_dispatch_override_flag_rejects_a_bad_value():
    with pytest.raises(UsageError):
        parse(_dispatch_tool(), ["fix", "--truncate-token-threshold=lots"])
