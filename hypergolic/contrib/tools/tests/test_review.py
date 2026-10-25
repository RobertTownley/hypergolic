from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.contrib.tools.review import (
    ReviewInput,
    ReviewRepo,
    ReviewTool,
    _build_harness_request,
    _build_shared_request,
    _ReviewNotReadyError,
)
from hypergolic.contrib.tools.tests._helpers import setup_clone_session
from hypergolic.dispatch.state import DispatchResult
from hypergolic.git.sandbox_integrate import SandboxGitError
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import ToolContext
from hypergolic.schemas import Session
from tests._factories import approval_of, build_session, invoke
from tests.conftest import make_project
from tests.helpers.git import FakeGit, commit_file, init_repo, run_git

_MOD = "hypergolic.contrib.tools.review"


async def _run(
    session: Session, context: str = "", repo: ReviewRepo = "app",
) -> ToolResult:
    ctx = ToolContext(session=session, broadcast=AsyncMock(), tool_id="review")
    return await invoke(ReviewTool, ReviewInput(context=context, repo=repo), ctx)


def _mock_dispatch(outcome: str = "success", conclusion: str = "LGTM"):
    return patch(
        "hypergolic.dispatch.runner.dispatch",
        new=AsyncMock(return_value=DispatchResult(
            outcome=outcome, conclusion=conclusion,
        )),
    )


def _prompt(mock_dispatch) -> str:
    return mock_dispatch.call_args[1]["content_blocks"][0]["text"]


def _git(
    *, ahead: str = "1", commits: str = "abc1234 feat: add feature",
    stat: str = " feature.py | 1 +", diff: str = "+print('hi')\n",
) -> FakeGit:
    return FakeGit({
        ("rev-list", "--count"): ahead,
        ("log",): commits,
        ("diff", "--stat"): stat,
        ("diff",): diff,
    })


@pytest.fixture
def clean():
    with patch(
        "hypergolic.git.sandbox_integrate.assert_sandbox_worktree_clean",
        new=AsyncMock(),
    ) as clean:
        yield clean


@pytest.fixture
def session(clean, monkeypatch) -> Session:
    make_project("proj-r", "P", "/tmp/p")
    monkeypatch.setattr(
        f"{_MOD}._base_rev", AsyncMock(return_value=("FETCH_HEAD", "refs/heads/main")),
    )
    monkeypatch.setattr(f"{_MOD}._git", _git())
    return build_session("R1", project_id="proj-r")


def test_review_tool_metadata():
    assert ReviewTool.id == "review"
    assert approval_of(ReviewTool) == "ALLOW"


async def test_review_fails_with_no_commits_beyond_base(session, monkeypatch):
    monkeypatch.setattr(f"{_MOD}._git", _git(ahead="0"))
    result = await _run(session)
    assert result.is_error
    assert "no commits" in result.content[0]["text"].lower()
    assert "--repo harness" in result.content[0]["text"]


async def test_review_fails_on_dirty_worktree(session, clean):
    clean.side_effect = SandboxGitError("uncommitted changes")
    result = await _run(session)
    assert result.is_error
    assert "dirty" in result.content[0]["text"].lower()


async def test_review_dispatches_reviewer_with_request(session):
    with _mock_dispatch() as mock_dispatch:
        result = await _run(session)

    assert not result.is_error
    assert result.content[0]["text"] == "LGTM"
    assert mock_dispatch.call_args[1]["role"] == "reviewer"
    assert "model_tier" not in mock_dispatch.call_args[1]
    prompt_text = _prompt(mock_dispatch)
    assert session.worktree_branch in prompt_text
    assert "feat: add feature" in prompt_text
    assert "feature.py" in prompt_text
    assert "print('hi')" in prompt_text
    assert "Context from the requesting agent" not in prompt_text


async def test_review_includes_caller_context(session):
    with _mock_dispatch() as mock_dispatch:
        await _run(session, context="Adds the feature; focus on error handling.")

    prompt_text = _prompt(mock_dispatch)
    assert "## Context from the requesting agent" in prompt_text
    assert "focus on error handling" in prompt_text


async def test_review_omits_oversized_diff(session, monkeypatch):
    monkeypatch.setattr(f"{_MOD}.MAX_INLINE_DIFF_CHARS", 100)
    monkeypatch.setattr(f"{_MOD}._git", _git(diff="+x = 1\n" * 100))

    with _mock_dispatch() as mock_dispatch:
        await _run(session)

    prompt_text = _prompt(mock_dispatch)
    assert "x = 1" not in prompt_text
    assert "Too large to inline" in prompt_text
    assert "git fetch origin refs/heads/main" in prompt_text
    assert "diff FETCH_HEAD...HEAD" in prompt_text


async def test_review_with_only_lockfile_changes_still_dispatches(session, monkeypatch):
    monkeypatch.setattr(
        f"{_MOD}._git", _git(commits="abc bump deps", stat=" uv.lock | 1 +", diff=""),
    )

    with _mock_dispatch() as mock_dispatch:
        result = await _run(session)

    assert not result.is_error
    prompt_text = _prompt(mock_dispatch)
    assert "bump deps" in prompt_text
    assert "uv.lock" in prompt_text
    assert "Only lock/generated files changed" in prompt_text


async def test_review_propagates_reviewer_failure(session):
    with _mock_dispatch(outcome="failure", conclusion="crashed"):
        result = await _run(session)

    assert result.is_error
    assert "crashed" in result.content[0]["text"]


async def test_review_repo_selects_workdir_for_clean_check(session, clean):
    build = AsyncMock(return_value="REQ")
    with patch(f"{_MOD}._build_harness_request", new=build), _mock_dispatch():
        result = await _run(session, repo="harness")
    assert not result.is_error
    assert clean.call_args[1]["workdir"] == "/harness"
    build.assert_awaited_once()


@pytest.mark.timeout(10)
@pytest.mark.usefixtures("sandbox_git_env")
async def test_review_against_real_git(repo: Path, worktrees_home: Path):
    session, worktree = setup_clone_session(repo, "R3", project_id="proj-r")
    commit_file(worktree, "uv.lock", "locked-content-marker\n" * 10, "bump deps")
    commit_file(worktree, "feature.py", "print('hi')\n", "feat: add feature")

    with _mock_dispatch() as mock_dispatch:
        result = await _run(session)

    assert not result.is_error
    prompt_text = _prompt(mock_dispatch)
    assert "feat: add feature" in prompt_text and "bump deps" in prompt_text
    assert "uv.lock" in prompt_text
    assert "locked-content-marker" not in prompt_text
    assert "print('hi')" in prompt_text


@pytest.fixture
def harness_ws(tmp_path, monkeypatch) -> Path:
    hw = tmp_path / "hw"
    (hw / ".git").mkdir(parents=True)
    monkeypatch.setattr(f"{_MOD}.harness_workspace_path", lambda sid: hw)
    monkeypatch.setattr(f"{_MOD}.harness_base_branch", lambda: "main")
    monkeypatch.setattr(
        f"{_MOD}._checkpoint_for_reviewer",
        AsyncMock(return_value="refs/hypergolic/harness/x"),
    )
    return hw


async def test_harness_review_request_inlines_diff(session, harness_ws, monkeypatch):
    monkeypatch.setattr(f"{_MOD}._git", _git(
        commits="abc add skill doc", stat=" skill.md | 1 +", diff="+skill body\n",
    ))

    request = await _build_harness_request(session=session, context="focus")
    assert "add skill doc" in request
    assert "skill.md" in request
    assert "skill body" in request
    assert "focus" in request
    assert "main-R1-harness" in request


async def test_harness_review_oversized_diff_points_at_checkpoint(
    session, harness_ws, monkeypatch,
):
    monkeypatch.setattr(f"{_MOD}._git", _git(diff="+" + "x" * 40_000))

    request = await _build_harness_request(session=session, context="")
    assert "x" * 1000 not in request
    assert "git fetch origin refs/hypergolic/harness/x" in request


async def test_harness_review_requires_commits(session, harness_ws, monkeypatch):
    monkeypatch.setattr(f"{_MOD}._git", _git(ahead="0"))

    with pytest.raises(_ReviewNotReadyError, match="No /harness commits"):
        await _build_harness_request(session=session, context="")


async def test_shared_review_requires_session_commits(session, tmp_path, monkeypatch):
    sw = tmp_path / "sw"
    (sw / ".git").mkdir(parents=True)
    monkeypatch.setattr(f"{_MOD}.session_shared_workspace", lambda sid: sw)
    monkeypatch.setattr(f"{_MOD}._git", _git(ahead="0"))

    with pytest.raises(_ReviewNotReadyError, match="No /shared commits"):
        await _build_shared_request(session=session, context="")


@pytest.mark.timeout(10)
async def test_shared_review_covers_only_session_commits(tmp_path, monkeypatch):
    import subprocess

    srepo = tmp_path / "shared-repo"
    init_repo(srepo)
    run_git(srepo, "commit", "--allow-empty", "-m", "pre-session commit")
    sw = tmp_path / "sw"
    subprocess.run(
        ["git", "clone", "--quiet", "--shared", str(srepo), str(sw)],
        check=True, capture_output=True,
    )
    run_git(sw, "config", "user.email", "t@t")
    run_git(sw, "config", "user.name", "t")
    commit_file(sw, "note.md", "session note\n", "during-session commit")
    monkeypatch.setattr(f"{_MOD}.session_shared_workspace", lambda sid: sw)
    monkeypatch.setattr(
        f"{_MOD}._checkpoint_for_reviewer",
        AsyncMock(return_value="refs/hypergolic/shared/x"),
    )

    request = await _build_shared_request(session=build_session("SH1"), context="")
    assert "during-session commit" in request
    assert "pre-session commit" not in request
    assert "session note" in request
    assert "/shared" in request
