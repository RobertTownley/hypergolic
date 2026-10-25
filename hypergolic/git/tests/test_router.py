from unittest.mock import patch

import pytest

from hypergolic.git.commands import GitCommandError
from hypergolic.git.schemas import (
    ChangedFile,
    GitCommitDetailResponse,
    GitDiffResponse,
    GitLogEntry,
    GitLogResponse,
    GitReviewResponse,
    GitStatusResponse,
)
from tests.conftest import make_project, make_session
from tests.helpers.git import seed_worktree_session as _seed_session


def _status(sid, **overrides):
    defaults: dict = dict(
        session_id=sid, branch="main", ahead=0, behind=0,
        staged=[], unstaged=[], untracked=[],
    )
    return GitStatusResponse(**{**defaults, **overrides})


def _review(sid, **overrides) -> GitReviewResponse:
    defaults: dict = dict(
        session_id=sid, branch="feat", base_branch="main", merge_base="b" * 40,
        ahead=0, behind=0, commits=[], files=[],
    )
    return GitReviewResponse(**{**defaults, **overrides})


def test_git_review_endpoint(api_client, tmp_path):
    sid, wt = _seed_session(tmp_path)
    with (
        patch("hypergolic.git.router.resolve_scoped_repo_and_base", return_value=(wt, "origin/main")),
        patch("hypergolic.git.router.run_git_command") as git,
        patch("hypergolic.git.router.get_git_review", return_value=_review(sid, ahead=1)) as review,
    ):
        git.return_value.stdout = "feat\n"
        resp = api_client.get("/api/git/review", params={"session_id": sid})
    assert resp.status_code == 200
    assert resp.json()["ahead"] == 1
    review.assert_called_once_with(wt, "origin/main", "feat", session_id=sid)


def test_git_review_endpoint_candidate_span(api_client, tmp_path):
    sid, _ = _seed_session(tmp_path)
    host = tmp_path / "base"
    head, base = "c" * 40, "b" * 40
    with (
        patch("hypergolic.git.router.resolve_scoped_host_repo_and_base", return_value=(host, "main")),
        patch("hypergolic.git.router.get_candidate_review", return_value=_review(sid)) as review,
    ):
        params = {"session_id": sid, "head": head, "base": base}
        assert api_client.get("/api/git/review", params=params).status_code == 200
        assert api_client.get(
            "/api/git/review", params={**params, "branch": "ABC-1204"},
        ).status_code == 200
        assert api_client.get(
            "/api/git/review", params={**params, "head": "not-a-sha"},
        ).status_code == 400
        assert api_client.get(
            "/api/git/review", params={**params, "branch": "bad..name"},
        ).status_code == 400

    labels = [c.args[3] for c in review.call_args_list]
    assert labels == ["main", "ABC-1204"]
    assert review.call_args.args[:3] == (host, base, head)
    assert review.call_args.kwargs["root_branch"] == "main"


def test_git_review_endpoint_harness_scope_without_clone(api_client, tmp_path):
    sid, _ = _seed_session(tmp_path)
    resp = api_client.get(
        "/api/git/review", params={"session_id": sid, "repo_scope": "harness"},
    )
    assert resp.status_code == 409


def test_git_review_endpoint_shared_scope_without_clone(api_client, tmp_path):
    sid, _ = _seed_session(tmp_path)
    resp = api_client.get(
        "/api/git/review", params={"session_id": sid, "repo_scope": "shared"},
    )
    assert resp.status_code == 409
    assert "/shared" in resp.json()["detail"]


def test_git_status_returns_session_id(api_client, tmp_path):
    sid, wt = _seed_session(tmp_path)
    status = _status(
        sid, ahead=1,
        staged=[ChangedFile(path="a.py", status="M", staged=True, additions=3, deletions=1)],
        unstaged=[ChangedFile(path="b.py", status="M", staged=False, additions=0, deletions=2)],
        untracked=["new.txt"],
    )
    with patch("hypergolic.git.router.get_git_status", return_value=status) as mock_status:
        resp = api_client.get("/api/git/status", params={"session_id": sid})
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert data["branch"] == "main"
    assert data["ahead"] == 1
    assert len(data["staged"]) == 1
    assert data["staged"][0]["path"] == "a.py"
    assert data["unstaged"][0]["path"] == "b.py"
    assert data["untracked"] == ["new.txt"]
    mock_status.assert_called_once_with(repo=wt, session_id=sid, base_branch=None)


def test_git_status_mode_all_resolves_base_branch(api_client, tmp_path):
    sid, wt = _seed_session(tmp_path)
    status = _status(
        sid, branch="feat",
        all_changes=[ChangedFile(path="x.py", status="M", staged=False, additions=1, deletions=0)],
    )
    with patch("hypergolic.git.router.get_git_status", return_value=status) as mock_status:
        resp = api_client.get("/api/git/status", params={"session_id": sid, "mode": "all"})
    assert resp.status_code == 200
    assert resp.json()["all_changes"][0]["path"] == "x.py"
    mock_status.assert_called_once_with(repo=wt, session_id=sid, base_branch="origin/main")


def test_git_status_requires_session_id(api_client):
    resp = api_client.get("/api/git/status")
    assert resp.status_code == 422


def test_git_status_unknown_session_returns_404(api_client):
    resp = api_client.get("/api/git/status", params={"session_id": "no-such"})
    assert resp.status_code == 404
    assert "session" in resp.json()["detail"].lower()


def test_git_diff(api_client, tmp_path):
    sid, wt = _seed_session(tmp_path)
    diff_resp = GitDiffResponse(
        session_id=sid, path="file.py",
        diff="--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@",
    )
    with patch("hypergolic.git.router.get_git_diff", return_value=diff_resp) as mock_diff:
        resp = api_client.post(
            "/api/git/diff",
            params={"session_id": sid},
            json={"path": "file.py", "staged": False},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert data["path"] == "file.py"
    assert "---" in data["diff"]
    mock_diff.assert_called_once_with("file.py", False, repo=wt, session_id=sid, base_branch=None)


def test_git_diff_base_resolves_base_branch(api_client, tmp_path):
    sid, wt = _seed_session(tmp_path)
    diff_resp = GitDiffResponse(session_id=sid, path="file.py", diff="diff")
    with patch("hypergolic.git.router.get_git_diff", return_value=diff_resp) as mock_diff:
        resp = api_client.post(
            "/api/git/diff",
            params={"session_id": sid},
            json={"path": "file.py", "staged": False, "base": True},
        )
    assert resp.status_code == 200
    mock_diff.assert_called_once_with("file.py", False, repo=wt, session_id=sid, base_branch="origin/main")


@pytest.mark.parametrize("target,endpoint", [
    ("git_stage", "/api/git/stage"),
    ("git_unstage", "/api/git/unstage"),
    ("git_discard", "/api/git/discard"),
])
def test_git_path_actions_success(api_client, tmp_path, target, endpoint):
    sid, wt = _seed_session(tmp_path)
    with patch(f"hypergolic.git.router.{target}") as mock_action:
        resp = api_client.post(
            endpoint,
            params={"session_id": sid},
            json={"paths": ["a.py", "b.py"]},
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "session_id": sid}
    mock_action.assert_called_once_with(["a.py", "b.py"], repo=wt)


@pytest.mark.parametrize("target,endpoint,payload,stderr", [
    ("git_stage", "/api/git/stage", {"paths": ["bad.py"]}, "fatal: not a git repo"),
    ("git_unstage", "/api/git/unstage", {"paths": ["bad.py"]}, "fatal: unstage failed"),
    ("git_discard", "/api/git/discard", {"paths": ["bad.py"]}, "error: discard failed"),
])
def test_git_action_errors_return_422(api_client, tmp_path, target, endpoint, payload, stderr):
    sid, _ = _seed_session(tmp_path)
    err = GitCommandError(command=target, returncode=1, stderr=stderr, stdout="")
    with patch(f"hypergolic.git.router.{target}", side_effect=err):
        resp = api_client.post(endpoint, params={"session_id": sid}, json=payload)
    assert resp.status_code == 422
    assert stderr in resp.json()["detail"]


def test_git_log(api_client, tmp_path):
    sid, wt = _seed_session(tmp_path)
    log = GitLogResponse(session_id=sid, entries=[
        GitLogEntry(
            hash="abc123def456", short_hash="abc123d",
            author="Dev", date="2025-01-01T00:00:00+00:00",
            message="init commit", refs="HEAD -> main",
        ),
    ])
    with patch("hypergolic.git.router.get_git_log", return_value=log) as mock_log:
        resp = api_client.get(
            "/api/git/log", params={"session_id": sid, "count": 10},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert len(data["entries"]) == 1
    assert data["entries"][0]["message"] == "init commit"
    mock_log.assert_called_once_with(10, repo=wt, session_id=sid)


def test_git_show_commit(api_client, tmp_path):
    sid, wt = _seed_session(tmp_path)
    detail = GitCommitDetailResponse(
        session_id=sid,
        hash="abc123def456", short_hash="abc123d",
        author="Dev", date="2025-01-01T00:00:00+00:00",
        message="fix bug", diff="diff --git a/x b/x",
    )
    with patch("hypergolic.git.router.get_git_commit_detail", return_value=detail) as mock_show:
        resp = api_client.get(
            "/api/git/show/abc123def456", params={"session_id": sid},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert data["hash"] == "abc123def456"
    assert data["message"] == "fix bug"
    assert "diff" in data["diff"]
    mock_show.assert_called_once_with("abc123def456", repo=wt, session_id=sid)


def test_git_branches_returns_session_id(api_client, tmp_path):
    sid, wt = _seed_session(tmp_path)
    with patch(
        "hypergolic.git.router.get_git_branches",
        return_value={"session_id": sid, "branches": ["main", "dev"], "current": "main"},
    ) as mock_branches:
        resp = api_client.get("/api/git/branches", params={"session_id": sid})
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert data["branches"] == ["main", "dev"]
    assert data["current"] == "main"
    mock_branches.assert_called_once_with(repo=wt, session_id=sid)


def test_git_checkout_returns_status_with_session_id(api_client, tmp_path):
    sid, wt = _seed_session(tmp_path)
    with (
        patch("hypergolic.git.router.git_checkout") as mock_checkout,
        patch("hypergolic.git.router.get_git_status", return_value=_status(sid, branch="dev")),
    ):
        resp = api_client.post(
            "/api/git/checkout",
            params={"session_id": sid},
            json={"branch": "dev"},
        )
    assert resp.status_code == 200
    assert resp.json()["session_id"] == sid
    assert resp.json()["branch"] == "dev"
    mock_checkout.assert_called_once_with("dev", repo=wt)


def test_git_create_branch(api_client, tmp_path):
    sid, wt = _seed_session(tmp_path)
    with (
        patch("hypergolic.git.router.git_create_branch") as mock_create,
        patch("hypergolic.git.router.get_git_status", return_value=_status(sid, branch="new-branch")),
    ):
        resp = api_client.post(
            "/api/git/branch",
            params={"session_id": sid},
            json={"name": "new-branch"},
        )
    assert resp.status_code == 200
    assert resp.json()["branch"] == "new-branch"
    mock_create.assert_called_once_with("new-branch", repo=wt)


def test_git_with_session_falls_back_to_project_path(api_client, tmp_path):
    project_path = tmp_path / "base"
    project_path.mkdir()
    make_project(pid="p1", path=str(project_path))
    sid = make_session(sid="s-1", project_id="p1")

    with patch(
        "hypergolic.git.router.get_git_status", return_value=_status(sid),
    ) as mock_status:
        resp = api_client.get("/api/git/status", params={"session_id": sid})
    assert resp.status_code == 200
    mock_status.assert_called_once_with(repo=project_path, session_id=sid, base_branch=None)


def test_git_error_detail_fallback(api_client, tmp_path):
    sid, _ = _seed_session(tmp_path)
    err = GitCommandError(command="stage", returncode=1, stderr="", stdout="")
    with patch("hypergolic.git.router.git_stage", side_effect=err):
        resp = api_client.post("/api/git/stage", params={"session_id": sid}, json={"paths": ["a.py"]})
    assert resp.status_code == 422
    assert "git stage failed (exit 1)" in resp.json()["detail"]


def test_sandbox_owned_workspace_down_renders_409(api_client, tmp_path):
    sid, _wt = _seed_session(tmp_path)
    with patch(
        "hypergolic.git.container_git._container_for", return_value=None,
    ):
        resp = api_client.get("/api/git/status", params={"session_id": sid})
    assert resp.status_code == 409
    assert "not running" in resp.json()["detail"]
