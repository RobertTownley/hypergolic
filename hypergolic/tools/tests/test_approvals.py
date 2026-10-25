"""Tests for path resolution and read-approval logic.

Write approval is no longer gated in-process (files are edited via the sandbox
``cmd`` tool or the always-approved ``host_cmd`` tool), so the surviving
surface is ``resolve_path`` and the ``decide_read`` path used by dispatch.
"""

import hypergolic as hypergolic_pkg
from pathlib import Path

import pytest

from hypergolic.contrib.tools.approvals.constants import READONLY_ALLOWLIST
from hypergolic.contrib.tools.approvals.paths import (
    decide_read,
    in_project_or_readonly_allowlist,
    _is_within,
    _resolved_allowlist,
)
from hypergolic.schemas import Session
from hypergolic.tools.paths import resolve_path
from tests._factories import build_session


def _session(scope: str = "/tmp/myproject") -> Session:
    """Session whose worktree (= working scope) is *scope*."""
    return build_session("sess-1", project_id="proj-1", project_path=scope, worktree_path=scope)


# ── constants ──────────────────────────


def test_readonly_allowlist_contains_installed_hg_source():
    """The allowlist must be a non-trivial list, and the installed hypergolic
    package directory must be on it."""
    assert isinstance(READONLY_ALLOWLIST, list) and len(READONLY_ALLOWLIST) >= 2
    hg_src = Path(hypergolic_pkg.__file__).resolve().parent
    resolved = [Path(p).expanduser().resolve() for p in READONLY_ALLOWLIST]
    assert hg_src in resolved


def test_decide_read_dispatched_worktree_allows_hg_source(tmp_path: Path):
    """A dispatched worktree session must get ALLOW when reading the installed HG source."""
    hg_file = str(Path(hypergolic_pkg.__file__).resolve())
    session = build_session(
        "sess-child",
        project_id="proj-child",
        project_path=str(tmp_path),
        role="reviewer",
        worktree_path=str(tmp_path),
        parent_id="sess-parent",
    )
    assert decide_read([hg_file], session).decision == "ALLOW"


# ── resolve_path ────────────────────


def test_resolve_path_absolute(tmp_path: Path):
    session = _session(str(tmp_path))
    result = resolve_path("/usr/local/bin", session)
    assert result == Path("/usr/local/bin").resolve()
    assert result.is_absolute()


def test_resolve_path_tilde():
    result = resolve_path("~/foo", _session("/tmp/proj"))
    assert result.is_absolute()
    assert "~" not in str(result)


@pytest.mark.parametrize(
    "rel, expected_suffix",
    [
        ("src/main.py", ("src", "main.py")),  # relative resolves against project dir
        (".", ()),                            # '.' is the project dir itself
        ("src/../README.md", ("README.md",)),  # '..' components resolve cleanly
    ],
)
def test_resolve_path_relative_forms(tmp_path: Path, rel, expected_suffix):
    session = _session(str(tmp_path))
    result = resolve_path(rel, session)
    assert result == tmp_path.resolve().joinpath(*expected_suffix)
    assert ".." not in str(result)


# ── _resolved_allowlist ──────────────────


def test_resolved_allowlist_returns_absolute_paths():
    assert all(p.is_absolute() for p in _resolved_allowlist(_session()))


# ── _is_within ────────────────


@pytest.mark.parametrize(
    "path, parent, expected",
    [
        ("/a/b", "/a/b", True),       # same path
        ("/a/b/c", "/a/b", True),     # child
        ("/a/b", "/a/b/c", False),    # not a child
        ("/a/x", "/a/b", False),      # sibling
    ],
)
def test_is_within(path, parent, expected):
    assert _is_within(Path(path), Path(parent)) is expected


# ── in_project_or_readonly_allowlist ──────────────


def test_in_project_or_allowlist_project_and_relative(tmp_path: Path):
    session = _session(str(tmp_path))
    assert in_project_or_readonly_allowlist(str(tmp_path / "file.py"), session) is True
    assert in_project_or_readonly_allowlist("src/file.py", session) is True


@pytest.mark.parametrize(
    "path, expected, desc",
    [
        ("~/.aws/config", True, "aws config is allowlisted"),
        ("~/.aws/credentials", False, "aws credentials NOT allowlisted"),
        ("/etc/passwd", False, "random path"),
    ],
)
def test_in_project_or_allowlist_paths(path, expected, desc):
    session = _session("/tmp/other")
    assert in_project_or_readonly_allowlist(str(Path(path).expanduser()), session) is expected
