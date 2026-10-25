from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from hypergolic.contrib.tools.merge_child import (
    build_merge_child_tool,
    find_merge_candidates,
)
from hypergolic.contrib.tools.tests._helpers import (
    committed_child_branch,
    make_parent_session,
    seed_parent_and_child,
)
from hypergolic.sessions import session_rows
from hypergolic.git.sandbox_repo import hypergolic_ref
from tests._factories import approval_of, build_session
from hypergolic.harness.primitives.tool import ToolContext
from tests.conftest import make_project, make_session
from tests.helpers.git import run_git


def _build_tool_for_child(repo: Path, *, parent_id: str, child_id: str, branch: str):
    seed_parent_and_child(
        parent_id=parent_id, child_id=child_id, project_path=repo, branch=branch,
        project_id="proj-mc",
    )
    session = make_parent_session(parent_id, repo, project_id="proj-mc")
    tool = build_merge_child_tool(session)
    assert tool is not None
    return session, tool


def _git_free_tool(*, parent_id: str, child_id: str):
    branch = f"main-{child_id}"
    seed_parent_and_child(
        parent_id=parent_id, child_id=child_id, project_path=Path("/tmp/p"),
        branch=branch, project_id="proj-mc",
    )
    session = build_session(parent_id, project_id="proj-mc", worktree_branch=f"main-{parent_id}")
    tool = build_merge_child_tool(session)
    assert tool is not None
    return session, tool


def _seed_parent_only(parent_id: str) -> None:
    make_project("proj-mc", "P", "/tmp/p")
    make_session("proj-mc", parent_id)


def test_find_merge_candidates_empty_when_no_children() -> None:
    _seed_parent_only("parent-1")
    assert find_merge_candidates("parent-1") == []


def test_find_merge_candidates_returns_concluded_with_branch() -> None:
    branch = "main-CHILDA"
    seed_parent_and_child(
        parent_id="parent-a", child_id="child-a",
        project_path=Path("/tmp/p"), branch=branch, project_id="proj-mc",
    )
    candidates = find_merge_candidates("parent-a")
    assert len(candidates) == 1
    assert candidates[0].session_id == "child-a"
    assert candidates[0].worktree_branch == branch


def test_find_merge_candidates_skips_a_child_rooted_at_a_host_branch() -> None:
    branch = "main-CHILDH"
    seed_parent_and_child(
        parent_id="parent-h", child_id="child-h",
        project_path=Path("/tmp/p"), branch=branch, project_id="proj-mc",
    )
    assert len(find_merge_candidates("parent-h", "main-parent-h")) == 1
    assert find_merge_candidates("parent-h", "some-other-branch") == []


def test_find_merge_candidates_excludes_reviewer_children() -> None:
    branch = "main-CHILDREV"
    seed_parent_and_child(
        parent_id="parent-rev", child_id="child-rev",
        project_path=Path("/tmp/p"), branch=branch, project_id="proj-mc",
        child_role="reviewer",
    )
    assert find_merge_candidates("parent-rev") == []


def test_build_merge_child_tool_none_when_no_candidates() -> None:
    _seed_parent_only("parent-empty")
    session = build_session("parent-empty", project_id="proj-mc")
    assert build_merge_child_tool(session) is None


@pytest.mark.timeout(10)
@pytest.mark.usefixtures("sandbox_git_env")
async def test_merge_tool_squashes_child_into_parent_branch(
    repo: Path, worktrees_home: Path,
) -> None:
    branch = committed_child_branch(repo, session_id="CHILDM", project_id="proj-mc")
    session, tool = _build_tool_for_child(repo, parent_id="parent-m", child_id="child-m", branch=branch)

    input_cls = cast(Any, tool.input_schema)
    inp = input_cls(child_session_id="child-m", commit_message="land child-m")
    ctx = ToolContext(session=session, broadcast=AsyncMock(), tool_id="merge_child")
    result = await tool.run(inp, ctx)

    assert not result.is_error, result.content
    ws = Path(session.worktree_path)
    assert (ws / "new.txt").exists()
    log = run_git(ws, "log", "--oneline", "-1").stdout
    assert "land child-m" in log
    assert hypergolic_ref("proj-mc", branch) not in run_git(
        repo, "for-each-ref", "refs/hypergolic",
    ).stdout
    assert find_merge_candidates("parent-m") == []
    assert session_rows.fetch_one("child-m").worktree_branch is None


async def test_merge_tool_requires_commit_message_unless_discarding() -> None:
    session, tool = _git_free_tool(parent_id="parent-r", child_id="child-r")

    input_cls = cast(Any, tool.input_schema)
    inp = input_cls(child_session_id="child-r")
    ctx = ToolContext(session=session, broadcast=AsyncMock(), tool_id="merge_child")
    result = await tool.run(inp, ctx)
    assert result.is_error


@pytest.mark.timeout(10)
@pytest.mark.usefixtures("sandbox_git_env")
async def test_merge_tool_discard_drops_branch(
    repo: Path, worktrees_home: Path,
) -> None:
    branch = committed_child_branch(repo, session_id="CHILDD", project_id="proj-mc")
    session, tool = _build_tool_for_child(repo, parent_id="parent-d", child_id="child-d", branch=branch)

    input_cls = cast(Any, tool.input_schema)
    inp = input_cls(child_session_id="child-d", discard=True)
    ctx = ToolContext(session=session, broadcast=AsyncMock(), tool_id="merge_child")
    result = await tool.run(inp, ctx)

    assert not result.is_error
    assert not (Path(session.worktree_path) / "new.txt").exists()
    assert hypergolic_ref("proj-mc", branch) not in run_git(
        repo, "for-each-ref", "refs/hypergolic",
    ).stdout
    assert find_merge_candidates("parent-d") == []


def test_merge_child_tool_is_auto_approved() -> None:
    _, tool = _git_free_tool(parent_id="parent-a", child_id="child-a")
    assert approval_of(tool) == "ALLOW"
