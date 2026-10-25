from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from hypergolic.contrib.tools.diff_child import build_diff_child_tool
from hypergolic.contrib.tools.tests._helpers import (
    committed_child_branch,
    make_parent_session,
    seed_parent_and_child,
)
from hypergolic.harness.primitives.tool import ToolContext
from hypergolic.schemas import Session
from tests.conftest import make_project, make_session
from tests._factories import build_session, invoke
from tests.helpers.git import FakeGit

_MOD = "hypergolic.contrib.tools.diff_child"


def _seed(*, parent_id: str, child_id: str, branch: str, repo: Path = Path("/tmp/p")) -> None:
    seed_parent_and_child(
        parent_id=parent_id, child_id=child_id, project_path=repo, branch=branch,
        project_id="proj-d",
    )


async def _run_diff_child(parent: Session, child_id: str):
    tool = build_diff_child_tool(parent)
    assert tool is not None
    input_cls = cast(Any, tool.input_schema)
    ctx = ToolContext(session=parent, broadcast=AsyncMock(), tool_id="diff_child")
    return await invoke(tool, input_cls(child_session_id=child_id), ctx)


async def _scripted(monkeypatch, *, stat: str, diff: str = "") -> str:
    _seed(parent_id="parent-x", child_id="child-x", branch="main-X")
    monkeypatch.setattr(f"{_MOD}.fetch_child_ref", AsyncMock(return_value="FETCH_HEAD"))
    git = FakeGit({("diff", "--stat"): stat, ("diff",): diff})
    monkeypatch.setattr(f"{_MOD}.async_run_git_command", git.run)
    parent = build_session("parent-x", project_id="proj-d", worktree_branch="main-parent-x")
    result = await _run_diff_child(parent, "child-x")
    assert not result.is_error
    return result.content[0]["text"]


def test_diff_child_none_when_no_candidates():
    make_project("proj-d", "P", "/tmp/p")
    make_session("proj-d", "parent-empty")
    assert build_diff_child_tool(build_session("parent-empty", project_id="proj-d")) is None


@pytest.mark.timeout(10)
@pytest.mark.usefixtures("sandbox_git_env")
async def test_diff_child_returns_git_diff(repo: Path, worktrees_home: Path):
    branch = committed_child_branch(
        repo, session_id="D1", project_id="proj-d",
        name="hello.py", content="print('hi')\n",
    )
    _seed(parent_id="parent-d", child_id="child-d", repo=repo, branch=branch)
    parent = make_parent_session("parent-d", repo, project_id="proj-d", base_branch="main")
    result = await _run_diff_child(parent, "child-d")
    assert not result.is_error
    text = result.content[0]["text"]
    assert "hello.py" in text
    assert "print('hi')" in text


async def test_diff_child_empty_when_branch_has_no_commits(monkeypatch):
    text = await _scripted(monkeypatch, stat="")
    assert "no diff" in text.lower()


async def test_diff_child_omits_oversized_diff(monkeypatch):
    monkeypatch.setattr(f"{_MOD}.MAX_INLINE_DIFF_CHARS", 100)
    text = await _scripted(monkeypatch, stat=" big.py | 100 +", diff="+x = 1\n" * 100)
    assert "big.py" in text
    assert "x = 1" not in text
    assert "Too large to inline" in text


async def test_diff_child_lockfile_only_change(monkeypatch):
    text = await _scripted(monkeypatch, stat=" uv.lock | 1 +")
    assert "uv.lock" in text
    assert "Only lock/generated files changed" in text
