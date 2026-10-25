"""Tests for hypergolic/contrib/tools/approvals/paths.py.

The only live consumer is ``decide_read`` (via the dispatch tool), so these
cover the read-approval surface, worktree scoping, and the hypergolic-source
readonly allowlist.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from hypergolic.contrib.tools.approvals.paths import (
    _is_within,
    decide_read,
    in_project_or_readonly_allowlist,
)
from hypergolic.schemas import Session
from tests._factories import build_session
import hypergolic as hypergolic_pkg
from hypergolic.contrib.tools.approvals.constants import READONLY_ALLOWLIST
from hypergolic.contrib.tools.approvals import constants as constants_mod


def _session(project_path: str = "/tmp/myproject") -> Session:
    return build_session(sid="sess-1", project_path=project_path)


def _worktree_session(
    project_path: str = "/tmp/myproject",
    worktree_path: str = "/tmp/myworktree",
    parent_id: str | None = "parent-1",
) -> Session:
    """Default is a *dispatched* worktree (``parent_id`` set) — the strict
    isolation case. Pass ``parent_id=None`` for a top-level worktree.
    """
    return build_session(
        sid="sess-wt",
        project_path=project_path,
        worktree_path=worktree_path,
        worktree_branch="hyp/sess-wt",
        base_branch="main",
        parent_id=parent_id,
    )


@pytest.fixture
def wt_session(tmp_path):
    """Factory for a worktree session backed by real ``proj`` and ``wt`` dirs
    under ``tmp_path``. Returns ``(make, project, worktree)`` where
    ``make(parent_id="parent-1")`` builds the session.
    """
    project = tmp_path / "proj"
    project.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()

    def make(parent_id: str | None = "parent-1") -> Session:
        return _worktree_session(
            project_path=str(project), worktree_path=str(worktree), parent_id=parent_id,
        )

    return make, project, worktree


def test_is_within_raises_type_error_returns_false():
    with patch.object(Path, "is_relative_to", side_effect=TypeError("bad type")):
        assert _is_within(Path("/a/b/c"), Path("/a")) is False


def test_is_within_raises_value_error_returns_false():
    with patch.object(Path, "is_relative_to", side_effect=ValueError("bad value")):
        assert _is_within(Path("/a/b/c"), Path("/a")) is False


def test_is_within_same_path_no_exception_needed():
    """Equal paths short-circuit before calling is_relative_to."""
    p = Path("/a/b")
    assert _is_within(p, p) is True


def test_in_project_or_readonly_allowlist_honors_worktree(wt_session):
    make, project, worktree = wt_session
    session = make()
    assert in_project_or_readonly_allowlist(str(worktree / "hello.txt"), session) is True
    assert in_project_or_readonly_allowlist("hello.txt", session) is True  # relative
    # The original project tree and arbitrary paths are out of scope.
    assert in_project_or_readonly_allowlist(str(project / "README.md"), session) is False
    assert in_project_or_readonly_allowlist("/etc/passwd", session) is False


def test_decide_read_dispatched_worktree_scope(wt_session):
    make, _project, worktree = wt_session
    session = make()
    assert decide_read([str(worktree / "README.md")], session).decision == "ALLOW"
    denied = decide_read(["/etc/passwd"], session)
    assert denied.decision == "DENY"
    assert denied.reason is not None


def test_decide_read_top_level_worktree_out_of_scope_requires_approval(wt_session):
    """Top-level worktree (parent_id=None) + out-of-scope path: REQUIRE_APPROVAL,
    not DENY — there is a user who can approve."""
    make, _project, _worktree = wt_session
    session = make(parent_id=None)
    assert decide_read(["/etc/passwd"], session).decision == "REQUIRE_APPROVAL"


def test_hypergolic_package_dir_on_readonly_allowlist():
    """`from hypergolic import ...` resolves to the package dir; that dir
    must be on the readonly allowlist regardless of install mode."""

    pkg_dir = str(Path(hypergolic_pkg.__file__).resolve().parent)
    assert pkg_dir in READONLY_ALLOWLIST


def test_decide_read_allows_hypergolic_source_from_unrelated_project(tmp_path):
    """A session whose project has nothing to do with hypergolic can still
    read the installed hypergolic source without approval."""

    session = _session(project_path=str(tmp_path / "unrelated-project"))
    pkg_init = str(Path(hypergolic_pkg.__file__).resolve())
    assert decide_read([pkg_init], session).decision == "ALLOW"


def test_decide_read_allows_dev_repo_root_when_editable(tmp_path):
    """In a dev/editable install (``pyproject.toml`` next to the package),
    siblings of the package — ``tests/``, ``pyproject.toml`` — are also
    readable without approval."""

    repo_root = Path(hypergolic_pkg.__file__).resolve().parent.parent
    if not (repo_root / "pyproject.toml").is_file():
        pytest.skip("not running from an editable/dev checkout")

    session = _session(project_path=str(tmp_path / "unrelated-project"))
    assert decide_read([str(repo_root / "pyproject.toml")], session).decision == "ALLOW"
    assert decide_read([str(repo_root / "tests")], session).decision == "ALLOW"


def test_source_roots_excludes_repo_root_for_non_editable(monkeypatch, tmp_path):
    """For a non-editable install (no ``pyproject.toml`` next to the package),
    only the package dir is allowlisted — we don't open up site-packages.
    """
    fake_site_packages = tmp_path / "site-packages"
    fake_pkg = fake_site_packages / "hypergolic"
    fake_pkg.mkdir(parents=True)
    (fake_pkg / "__init__.py").write_text("")


    monkeypatch.setattr(hypergolic_pkg, "__file__", str(fake_pkg / "__init__.py"))
    roots = constants_mod._hypergolic_source_roots()
    assert str(fake_pkg) in roots
    assert str(fake_site_packages) not in roots
