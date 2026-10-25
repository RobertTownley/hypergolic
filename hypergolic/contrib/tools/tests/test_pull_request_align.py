from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from hypergolic.contrib.tools.pull_request import PullRequestInput
from hypergolic.contrib.tools.pull_request_align import align
from hypergolic.git.sandbox_integrate import SandboxGitError
from hypergolic.harness.primitives.tool import ToolContext
from tests._factories import build_session
from hypergolic.harness.primitives.validation import ValidationResult

MOD = "hypergolic.contrib.tools.pull_request_align"


def _invalid(result: ValidationResult) -> str:
    assert not result.is_valid
    return result.message or ""


def _publish(**overrides: Any) -> PullRequestInput:
    return PullRequestInput.model_validate({"action": "publish", "branch": "b1", "title": "t", **overrides})


def _ctx(worktree_path: str = "/tmp/wt") -> ToolContext:
    return ToolContext(
        session=build_session(worktree_path=worktree_path, worktree_branch="wt-branch"),
        broadcast=AsyncMock(), tool_id="pull_request",
    )


def _proc(returncode=0):
    return MagicMock(returncode=returncode, stdout="", stderr="")


@contextlib.contextmanager
def _host(git_codes, sandbox=None, gh="/usr/bin/gh"):
    app = MagicMock()
    app.find_project.return_value = MagicMock()
    slot = MagicMock(workdir="/app")
    with (
        patch(f"{MOD}.shutil.which", return_value=gh),
        patch(f"{MOD}.get_app", return_value=app),
        patch("hypergolic.git.sandbox_integrate.app_slot", return_value=slot),
        patch("hypergolic.git.sandbox_integrate.refresh_session_ref", AsyncMock(return_value="refs/hypergolic/x")),
        patch(f"{MOD}.async_run_git_command", AsyncMock(side_effect=[_proc(c) for c in git_codes])),
        patch("hypergolic.git.sandbox_integrate.exec_repo_git", AsyncMock(side_effect=sandbox or [""])) as exec_git,
    ):
        yield exec_git


async def test_no_gh_fails_every_action():
    with _host([], gh=None):
        assert "gh" in _invalid(await align(PullRequestInput(action="list"), _ctx()))


async def test_list_passes():
    with _host([]):
        assert (await align(PullRequestInput(action="list"), _ctx())).is_valid


async def test_missing_host_branch():
    with _host([1]):
        assert "git push origin HEAD:b1" in _invalid(await align(_publish(), _ctx()))


async def test_same_tree_passes_and_notes_dirty():
    with _host([0, 0], sandbox=[" M x\n"]):
        result = await align(_publish(), _ctx())
    assert result.is_valid and "uncommitted" in (result.message or "")


async def test_sandbox_ahead_says_land():
    with _host([0, 1, 0]):
        assert "Land it first" in _invalid(await align(_publish(), _ctx()))


async def test_diverged():
    with _host([0, 1, 1, 1]):
        assert "diverged" in _invalid(await align(_publish(), _ctx()))


async def test_host_ahead_fast_forwards():
    with _host([0, 1, 1, 0], sandbox=["", ""]) as exec_git:
        result = await align(_publish(), _ctx())
    assert "merge --ff-only" in exec_git.await_args_list[0].args[2]
    assert result.is_valid and "fast-forwarded" in (result.message or "")


async def test_fast_forward_refused():
    with _host([0, 1, 1, 0], sandbox=[SandboxGitError("would be overwritten")]):
        problem = _invalid(await align(_publish(), _ctx()))
    assert "would be overwritten" in problem and "stash" in problem


async def test_body_file_maps_sandbox_path_to_worktree(tmp_path):
    (tmp_path / "PR.md").write_text("from file")
    inp = _publish(body_file="/app/PR.md")
    with _host([0, 0]):
        assert (await align(inp, _ctx(str(tmp_path)))).is_valid
    assert inp.body == "from file"
