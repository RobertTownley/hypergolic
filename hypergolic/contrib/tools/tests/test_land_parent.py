"""land: a child's push to its base lands in the parent's sandbox branch.

Fully mocked: no git process, no filesystem, no sandbox.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from hypergolic.contrib.tools import land
from hypergolic.contrib.tools.land.inputs import Target
from hypergolic.git.sandbox_integrate import SandboxGitError
from tests.helpers.land import patch_land
from hypergolic.contrib.tools.land import LandInput, _handle_land
from hypergolic.gates.request import GateVerdict
from hypergolic.git.commands import GitResult
from hypergolic.git.sandbox_integrate import RepoSlot
from hypergolic.harness.primitives.tool import ToolContext

PUSHED = "a" * 40
PARENT_TIP = "b" * 40
CANDIDATE = "c" * 40
NEW_TIP = "d" * 40
REBASED = "e" * 40


def _ok(stdout: str = "") -> GitResult:
    return GitResult(returncode=0, stdout=stdout, stderr="")


@pytest.fixture
def env(monkeypatch):
    project = SimpleNamespace(id="proj", land_mode="squash", on_stale_base="regate")
    child: Any = SimpleNamespace(
        id="child-1", project_id="proj", parent_id="parent-1", base_branch="main-PARENT",
        conducted_by=None,
    )
    parent = SimpleNamespace(id="parent-1", worktree_branch="main-PARENT", base_branch="main")
    slot = RepoSlot(
        repo="app", workdir="/app", host_repo=Path("/host/repo"), base_branch="main-PARENT",
        session_branch="main-CHILD", ref_scope="proj",
    )
    m = SimpleNamespace(
        pipeline=AsyncMock(return_value=GateVerdict(ok=True, lines=["gates ok"])),
        parent_tip=AsyncMock(return_value=PARENT_TIP),
        advance_parent=AsyncMock(return_value=(True, CANDIDATE)),
        reset_child=AsyncMock(return_value=True),
        advance_branch=AsyncMock(return_value=(True, CANDIDATE)),
        resolve_branch=AsyncMock(return_value=PARENT_TIP),
        rebase=AsyncMock(return_value=(REBASED, "")),
        git=AsyncMock(return_value=_ok()),
    )
    app = MagicMock()
    app.find_project.return_value = project
    patches = {
        "get_app": lambda: app,
        "gates_for": lambda *_: [],
        "slot_for": lambda *_: slot,
        "land_parent": lambda s, b: parent if b in {"main", "main-PARENT"} else None,
        "fetch_quarantine_ref": AsyncMock(return_value=_ok()),
        "async_run_git_command": m.git,
        "is_ancestor": AsyncMock(return_value=True),
        "derive_message": AsyncMock(return_value="msg"),
        "build_candidate": AsyncMock(return_value=CANDIDATE),
        "rebase_candidate": m.rebase,
        "run_pipeline": m.pipeline,
        "parent_tip": m.parent_tip,
        "advance_parent": m.advance_parent,
        "reset_child_onto": m.reset_child,
        "advance_branch": m.advance_branch,
        "checkout_blocker": AsyncMock(return_value=None),
        "resolve_branch": m.resolve_branch,
        "resolve_target": AsyncMock(return_value=Target(PARENT_TIP)),
        "post_land": AsyncMock(),
    }
    patch_land(monkeypatch, patches)
    monkeypatch.setattr(land.guaranteed_output, "post", lambda *_: None)
    ctx = ToolContext(session=child, broadcast=AsyncMock(), tool_id="land")
    return SimpleNamespace(ctx=ctx, child=child, parent=parent, project=project, **vars(m))


async def _push(env, branch: str):
    return await _handle_land(LandInput(sha=PUSHED, branch=branch), env.ctx)


@pytest.mark.parametrize("branch", ["main", "main-PARENT"])
async def test_push_to_base_lands_in_parent_sandbox(env, branch):
    result = await _push(env, branch)

    assert result.exit_code == 0, result.stderr
    # A fresh checkpoint before the gates, and a refresh after the merge so
    # the child's next fetch agrees with its origin/<branch>.
    assert env.parent_tip.await_count == 2
    env.advance_parent.assert_awaited_once_with(
        env.parent, env.project, old_sha=PARENT_TIP, new_commit=CANDIDATE,
    )
    env.advance_branch.assert_not_awaited()  # no host branch moves
    assert env.pipeline.await_args.args[1].slot.base_branch == "main-PARENT"  # what the parent approves
    env.reset_child.assert_awaited_once()
    assert env.reset_child.await_args.kwargs["branch"] == branch  # origin/<the name it pushed>
    assert f"merged into {branch} as" in result.stdout
    if branch == "main":  # the child reads the name it pushed, never its parent's branch
        assert "main-PARENT" not in result.stdout


async def test_dirty_parent_overlap_rejects_with_reason(env):
    env.advance_parent.return_value = (False, "the parent session has uncommitted changes: a.txt")

    result = await _push(env, "main")

    assert result.exit_code == 1
    assert "uncommitted changes" in result.stderr
    env.reset_child.assert_not_awaited()


async def test_parent_moved_during_gates_restacks_onto_new_tip(env):
    env.advance_parent.side_effect = [(False, "moved"), (True, REBASED)]
    env.parent_tip.side_effect = [PARENT_TIP, NEW_TIP, NEW_TIP]

    result = await _push(env, "main")

    assert result.exit_code == 0, result.stderr
    assert env.rebase.await_args.kwargs["new_tip"] == NEW_TIP
    assert env.advance_parent.await_args.kwargs == {"old_sha": NEW_TIP, "new_commit": REBASED}


async def test_gate_rejection_leaves_parent_untouched(env):
    env.pipeline.return_value = GateVerdict(ok=False, lines=["denied: scope"])

    result = await _push(env, "main")

    assert result.exit_code == 1
    env.advance_parent.assert_not_awaited()


async def test_push_to_another_branch_takes_the_host_path(env):
    result = await _push(env, "feature-x")

    assert result.exit_code == 0, result.stderr
    env.parent_tip.assert_not_awaited()
    env.advance_parent.assert_not_awaited()
    # The gate sees the real host branch, so a parent can never approve it.
    assert env.pipeline.await_args.args[1].slot.base_branch == "feature-x"


async def test_unreachable_parent_sandbox_rejects(env):
    env.parent_tip.side_effect = SandboxGitError("sandbox not running")

    result = await _push(env, "main")

    assert result.exit_code == 1
    assert "sandbox not running" in result.stderr
