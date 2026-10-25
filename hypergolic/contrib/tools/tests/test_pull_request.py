"""Tests for hypergolic.contrib.tools.pull_request."""
from __future__ import annotations

import contextlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from hypergolic.contrib.tools.pull_request import PullRequestInput, pull_request_tool
from hypergolic.harness.primitives.tool import ToolContext
from tests._factories import approval_of, build_session, invoke

MOD = "hypergolic.contrib.tools.pull_request"


def _publish(**overrides: Any) -> PullRequestInput:
    fields: dict[str, Any] = {"action": "publish", "branch": "ABC-1-x", "title": "t", "body": "b"}
    return PullRequestInput.model_validate({**fields, **overrides})


def _ctx() -> ToolContext:
    return ToolContext(
        session=build_session(worktree_path="/tmp/wt", worktree_branch="wt-branch"),
        broadcast=AsyncMock(), tool_id="pull_request",
    )


def _proc(returncode=0, stdout="", stderr=""):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


@contextlib.contextmanager
def _host(git_results, gh_results):
    with (
        patch(f"{MOD}.async_run_git_command", AsyncMock(side_effect=git_results)) as git,
        patch(f"{MOD}.run_subprocess", AsyncMock(side_effect=gh_results)) as gh,
    ):
        yield git, gh


def _text(result) -> str:
    return result.content[0]["text"]


def test_metadata_and_approval_split():
    assert pull_request_tool.id == "pull_request"
    assert approval_of(pull_request_tool, _publish()) == "REQUIRE_APPROVAL"
    assert approval_of(pull_request_tool, PullRequestInput(action="list")) == "ALLOW"
    assert approval_of(pull_request_tool, PullRequestInput(action="view", branch="1")) == "ALLOW"
    assert PullRequestInput(action="publish").draft is True


async def test_list_defaults_to_me_and_formats_rows():
    prs = [{"number": 7, "title": "Fix", "url": "u", "isDraft": True, "headRefName": "b",
            "statusCheckRollup": [{"conclusion": "SUCCESS"}]}]
    with _host([], [_proc(stdout=json.dumps(prs))]) as (_, gh):
        result = await invoke(pull_request_tool, PullRequestInput(action="list"), _ctx())
    args = gh.await_args.args[0]
    assert args[:6] == ["gh", "pr", "list", "--author", "@me", "--state"]
    assert _text(result) == "#7  b  Fix [draft]  checks:✓  u"


async def test_publish_pushes_host_branch_and_opens_draft_pr():
    git = [_proc(0)]
    gh = [_proc(stdout="[]"), _proc(stdout="https://gh/pr/9\n")]
    with _host(git, gh) as (git_mock, gh_mock):
        result = await invoke(pull_request_tool, _publish(reviewer=["ann"]), _ctx())
    assert not result.is_error, _text(result)
    push = git_mock.await_args_list[-1].args
    assert push == ("push", "--force-with-lease", "origin", "refs/heads/ABC-1-x:refs/heads/ABC-1-x")
    create = gh_mock.await_args_list[-1].args[0]
    assert create[:5] == ["gh", "pr", "create", "--head", "ABC-1-x"]
    assert "--draft" in create and "--base" not in create
    assert create[create.index("--reviewer") + 1] == "ann"
    assert "PR created: https://gh/pr/9" in _text(result)


async def test_publish_updates_existing_pr_without_creating():
    git = [_proc(0)]
    gh = [_proc(stdout=json.dumps([{"number": 3, "url": "u3"}]))]
    with _host(git, gh) as (_, gh_mock):
        result = await invoke(pull_request_tool, _publish(title=None), _ctx())
    assert not result.is_error, _text(result)
    assert "updated PR #3" in _text(result)
    assert gh_mock.await_count == 1


async def test_publish_new_pr_needs_title():
    git = [_proc(0)]
    with _host(git, [_proc(stdout="[]")]):
        result = await invoke(pull_request_tool, _publish(title=None), _ctx())
    assert result.is_error and "--title" in _text(result)
