from unittest.mock import AsyncMock, patch

from hypergolic.sandbox.manager import repo_creation as rc
from hypergolic.sandbox.manager.types import ExecResult
from hypergolic.sessions.operations import load_session


OK = ExecResult(stdout="", stderr="", returncode=0)


async def _checkpoint(sid, tmp_path, branch):
    parent = load_session(sid).model_copy(
        update={"base_branch": "stale/db-only", "worktree_branch": "main-parent"},
    )
    project = rc._find_project(parent.project_id)
    assert project is not None
    push = AsyncMock(return_value=OK)
    with (
        patch.object(rc, "_load_session", return_value=parent),
        patch.object(rc, "session_container", AsyncMock(return_value="c")),
        patch.object(rc, "exec_in_sandbox", push),
        patch.object(rc, "fetch_quarantine_ref", AsyncMock(return_value=OK)),
    ):
        ref = await rc._checkpoint_parent_branch(sid, branch, tmp_path, project)
    return push.call_args.kwargs["command"], ref, project


async def test_checkpoint_pushes_a_pin_branch_by_name(sid, tmp_path):
    command, ref, project = await _checkpoint(sid, tmp_path, "pin/711835e0000a-abc123")
    assert "+refs/heads/pin/711835e0000a-abc123:" in command
    assert ref == rc.hypergolic_ref(project.id, "pin/711835e0000a-abc123")


async def test_checkpoint_pushes_parent_head_not_recorded_base(sid, tmp_path):
    parent = load_session(sid).model_copy(
        update={"base_branch": "stale/db-only", "worktree_branch": "main-parent"},
    )
    project = rc._find_project(parent.project_id)
    assert project is not None
    push = AsyncMock(return_value=OK)
    with (
        patch.object(rc, "_load_session", return_value=parent),
        patch.object(rc, "session_container", AsyncMock(return_value="c")),
        patch.object(rc, "exec_in_sandbox", push),
        patch.object(rc, "fetch_quarantine_ref", AsyncMock(return_value=OK)),
    ):
        ref = await rc._checkpoint_parent_branch(sid, "main-parent", tmp_path, project)
    command = push.call_args.kwargs["command"]
    assert "+HEAD:" in command
    assert "stale/db-only" not in command
    assert ref == rc.hypergolic_ref(project.id, "main-parent")
