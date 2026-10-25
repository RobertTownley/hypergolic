from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.timeout(10)

from hypergolic.dispatch.conclude import (  # noqa: E402
    BranchPreservationError,
    ConcludeInput,
    teardown_worktree_at_conclude,
)
from hypergolic.dispatch.conclude.handler import _handle_conclude  # noqa: E402
from hypergolic.git.sandbox_integrate import SandboxGitError  # noqa: E402
from hypergolic.git.sandbox_repo import hypergolic_ref  # noqa: E402
from hypergolic.git.tests._worktree_thread_helpers import (  # noqa: E402
    join_worktree_threads,
)
from hypergolic.schemas import Session  # noqa: E402
from hypergolic.harness.primitives.tool import ToolContext  # noqa: E402
from tests._factories import build_session  # noqa: E402
from tests.conftest import make_project, make_session as insert_session  # noqa: E402
from tests.helpers.git import run_git  # noqa: E402
from hypergolic.sessions import session_rows  # noqa: E402

PROJECT_ID = "proj-wt"


SESSION_CONTAINER = "hypergolic.dispatch.conclude.worktree.session_container"


@pytest.fixture(autouse=True)
def _sandbox_running():
    with patch(SESSION_CONTAINER, AsyncMock(return_value="ws-container")):
        yield


def _sandbox_stopped():
    return patch(SESSION_CONTAINER, AsyncMock(return_value=None))


def _setup(session_id: str, repo: Path, tmp_path: Path) -> Session:
    make_project(PROJECT_ID, "P", str(repo))
    branch = f"main-{session_id}"
    ws = tmp_path / f"ws-{session_id}"
    ws.mkdir()
    insert_session(PROJECT_ID, session_id, worktree_branch=branch)
    return build_session(
        sid=session_id,
        project_id=PROJECT_ID,
        project_path=str(repo),
        worktree_path=str(ws),
        worktree_branch=branch,
        base_branch="main",
    )


def _ws(session: Session) -> Path:
    assert session.worktree_path
    return Path(session.worktree_path)


def _ref(session: Session) -> str:
    assert session.worktree_branch
    return hypergolic_ref(PROJECT_ID, session.worktree_branch)


def _ref_exists(repo: Path, ref: str) -> bool:
    try:
        run_git(repo, "rev-parse", "--verify", "--quiet", ref)
    except subprocess.CalledProcessError:
        return False
    return True


def _commit_beyond_main(repo: Path, ref: str) -> None:
    main = run_git(repo, "rev-parse", "main").stdout.strip()
    tree = run_git(repo, "rev-parse", "main^{tree}").stdout.strip()
    new = run_git(repo, "commit-tree", tree, "-p", main, "-m", "child work").stdout.strip()
    run_git(repo, "update-ref", ref, new)


def _fetch_back_mocks(session: Session, *, fail: bool = False):
    if fail:
        refresh = AsyncMock(side_effect=SandboxGitError("sandbox gone"))
    else:
        refresh = AsyncMock(return_value=_ref(session))
    return (
        patch("hypergolic.dispatch.conclude.worktree.refresh_session_ref", refresh),
        patch(
            "hypergolic.dispatch.conclude.worktree.base_ref_for",
            AsyncMock(return_value="refs/heads/main"),
        ),
    )


async def test_teardown_clean_branch_without_commits_drops_branch(
    repo: Path, tmp_path: Path,
) -> None:
    session = _setup("s-empty", repo, tmp_path)
    run_git(repo, "update-ref", _ref(session), "main")

    refresh, base = _fetch_back_mocks(session)
    with refresh, base:
        surviving = await teardown_worktree_at_conclude(
            session, delete_branch_flag=False,
        )

    assert surviving is None
    join_worktree_threads()
    assert not _ws(session).exists()
    assert not _ref_exists(repo, _ref(session))
    assert session_rows.fetch_one("s-empty").worktree_branch is None


async def test_teardown_branch_with_commits_survives_as_host_ref(
    repo: Path, tmp_path: Path,
) -> None:
    session = _setup("s-work", repo, tmp_path)
    _commit_beyond_main(repo, _ref(session))

    refresh, base = _fetch_back_mocks(session)
    with refresh, base:
        surviving = await teardown_worktree_at_conclude(
            session, delete_branch_flag=False,
        )

    assert surviving == session.worktree_branch
    join_worktree_threads()
    assert not _ws(session).exists()
    assert _ref_exists(repo, _ref(session))


async def test_teardown_stopped_sandbox_skips_fetch_back(
    repo: Path, tmp_path: Path,
) -> None:
    session = _setup("s-stopped", repo, tmp_path)
    refresh = AsyncMock(side_effect=AssertionError("must not fetch back"))
    with (
        _sandbox_stopped(),
        patch("hypergolic.dispatch.conclude.worktree.refresh_session_ref", refresh),
    ):
        surviving = await teardown_worktree_at_conclude(
            session, delete_branch_flag=False,
        )

    assert surviving is None
    join_worktree_threads()
    assert not _ws(session).exists()
    assert session_rows.fetch_one("s-stopped").worktree_branch is None


async def test_teardown_delete_branch_flag_true_deletes_preserved_ref(
    repo: Path, tmp_path: Path,
) -> None:
    session = _setup("s-drop", repo, tmp_path)
    _commit_beyond_main(repo, _ref(session))

    lookup = AsyncMock(side_effect=AssertionError("must not touch the sandbox"))
    with patch(SESSION_CONTAINER, lookup):
        surviving = await teardown_worktree_at_conclude(
            session, delete_branch_flag=True,
        )

    assert surviving is None
    join_worktree_threads()
    assert not _ws(session).exists()
    assert not _ref_exists(repo, _ref(session))


async def test_teardown_delete_worktree_false_keeps_directory(
    repo: Path, tmp_path: Path,
) -> None:
    session = _setup("s-keep", repo, tmp_path)
    _commit_beyond_main(repo, _ref(session))

    refresh, base = _fetch_back_mocks(session)
    with refresh, base:
        surviving = await teardown_worktree_at_conclude(
            session, delete_worktree=False, delete_branch_flag=False,
        )

    assert surviving == session.worktree_branch
    assert _ws(session).exists()
    assert _ref_exists(repo, _ref(session))


async def test_teardown_failed_fetch_back_blocks_conclude(
    repo: Path, tmp_path: Path,
) -> None:
    session = _setup("s-fetchfail", repo, tmp_path)

    refresh, base = _fetch_back_mocks(session, fail=True)
    with refresh, base:
        with pytest.raises(BranchPreservationError):
            await teardown_worktree_at_conclude(session, delete_branch_flag=False)
    assert _ws(session).exists()


async def test_handle_conclude_unpreservable_branch_is_an_error(
    repo: Path, tmp_path: Path,
) -> None:
    session = _setup("s-nopreserve", repo, tmp_path)

    refresh, base = _fetch_back_mocks(session, fail=True)
    with refresh, base:
        output = await _handle_conclude(
            ConcludeInput(outcome="success", conclusion="done"),
            ToolContext(session=session, broadcast=AsyncMock(), tool_id="conclude"),
        )

    assert output.is_error is True
    assert "could not be preserved" in output.first_text()
    assert _ws(session).exists()


async def test_handle_conclude_passes_conclusion_through(
    repo: Path, tmp_path: Path,
) -> None:
    session = _setup("s-keepc", repo, tmp_path)
    run_git(repo, "update-ref", _ref(session), "main")

    refresh, base = _fetch_back_mocks(session)
    with (
        refresh, base,
        patch("hypergolic.dispatch.conclude.handler.resolve_dispatch", return_value=True) as mock_resolve,
    ):
        await _handle_conclude(
            ConcludeInput(outcome="success", conclusion="done", delete_worktree=False),
            ToolContext(session=session, broadcast=AsyncMock(), tool_id="conclude"),
        )

    result = mock_resolve.call_args[0][1]
    assert result.conclusion == "done"
