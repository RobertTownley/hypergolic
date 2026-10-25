"""git.parent_land: fully mocked (no git process, filesystem, or sandbox)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from hypergolic.git import parent_land
from hypergolic.git.sandbox_integrate import SandboxGitError

PROJECT: Any = object()
PARENT: Any = SimpleNamespace(id="p", worktree_branch="main-P", base_branch="main")
LIVE = parent_land.ParentBranch(PARENT, "main-P", live=True)
PIN = parent_land.ParentBranch(PARENT, "pin/711835e0000a-abc123", live=False)


def _child(**kw) -> Any:
    return SimpleNamespace(**{"id": "c", "parent_id": "p", "base_branch": "main-P", "conducted_by": None, **kw})


@pytest.fixture(autouse=True)
def parents(monkeypatch):
    monkeypatch.setattr(parent_land, "_load", lambda sid: PARENT if sid == "p" else None)


@pytest.mark.parametrize("base,expected", [("main-P", LIVE), (PIN.branch, PIN)])
def test_child_of_a_parent_branch_sees_parent_base(base, expected):
    child = _child(base_branch=base)
    assert parent_land.parent_of(child) == expected
    assert parent_land.visible_base(child) == "main"


@pytest.mark.parametrize("child", [
    _child(parent_id=None, base_branch="main"),       # top-level
    _child(parent_id=None, base_branch="pin/711835e0000a"),  # standalone pin: a host branch
    _child(base_branch="feature"),                     # rooted at a host branch
    _child(parent_id="gone"),                          # parent row missing
])
def test_other_sessions_see_their_own_base(child):
    assert parent_land.parent_of(child) is None
    assert parent_land.visible_base(child) == child.base_branch


@pytest.mark.parametrize("branch,lands", [("main", True), ("main-P", True), ("feature", False)])
def test_land_parent_matches_only_the_base_names(branch, lands):
    assert (parent_land.land_parent(_child(), branch) == LIVE) is lands


@pytest.mark.parametrize("branch,lands", [("main", True), (PIN.branch, True), ("main-P", False)])
def test_pinned_child_lands_only_into_its_pin(branch, lands):
    assert (parent_land.land_parent(_child(base_branch=PIN.branch), branch) == PIN) is lands


@pytest.mark.parametrize("base,expected", [("main-P", LIVE), (PIN.branch, PIN)])
def test_conducted_child_lands_any_branch_into_the_parent(base, expected):
    child = _child(base_branch=base, conducted_by="p")
    assert parent_land.land_parent(child, "ABC-9042-feature") == expected


def test_pin_names_are_unique_per_child():
    a, b = parent_land.parent_pin_name("7" * 40), parent_land.parent_pin_name("7" * 40)
    assert a.startswith("pin/777777777777-") and a != b


@pytest.mark.parametrize("out,raises", [("CREATED\n", False), ("", True)])
async def test_create_parent_pin(monkeypatch, out, raises):
    exec_git = AsyncMock(return_value=out)
    monkeypatch.setattr(parent_land, "exec_repo_git", exec_git)
    call = parent_land.create_parent_pin(PARENT, PROJECT, sha="7" * 40, name=PIN.branch)
    if raises:
        with pytest.raises(SandboxGitError):
            await call
    else:
        await call
    assert exec_git.await_args is not None
    assert exec_git.await_args.args[0] is PARENT
    assert f"branch --no-track {PIN.branch} {'7' * 40}" in exec_git.await_args.args[2]


@pytest.mark.parametrize("pb,src,session_branch", [
    (LIVE, "HEAD", "main-P"),
    (PIN, f"refs/heads/{PIN.branch}", PIN.branch),
])
async def test_parent_tip_checkpoints_the_right_branch(monkeypatch, pb, src, session_branch):
    slot: Any = SimpleNamespace(session_branch="main-P", host_repo="/host/repo")
    monkeypatch.setattr(parent_land, "app_slot", lambda s, p: slot)
    monkeypatch.setattr(parent_land, "replace", lambda s, **kw: SimpleNamespace(**{**vars(s), **kw}))
    refresh = AsyncMock(return_value="refs/hypergolic/p1/x")
    monkeypatch.setattr(parent_land, "refresh_slot_ref", refresh)
    monkeypatch.setattr(parent_land, "async_run_git_command", AsyncMock(
        return_value=SimpleNamespace(returncode=0, stdout="d" * 40 + "\n"),
    ))

    assert await parent_land.parent_tip(pb, PROJECT) == "d" * 40

    assert refresh.await_args is not None
    assert refresh.await_args.args[2].session_branch == session_branch
    assert refresh.await_args.kwargs.get("src", "HEAD") == src


@pytest.mark.parametrize("out,ok,text", [
    ("MERGED\n", True, "c" * 40),
    ("STALE " + "d" * 40, False, "moved while gates ran"),
    ("REFUSED error: Your local changes to a.txt would be overwritten", False, "a.txt"),
])
async def test_advance_parent_outcomes(monkeypatch, out, ok, text):
    exec_git = AsyncMock(return_value=out)
    monkeypatch.setattr(parent_land, "exec_repo_git", exec_git)

    result = await parent_land.advance_parent(LIVE, PROJECT, old_sha="b" * 40, new_commit="c" * 40)

    assert result[0] is ok and text in result[1]
    assert exec_git.await_args is not None
    script = exec_git.await_args.args[2]
    assert "merge --ff-only" in script and "b" * 40 in script


async def test_advance_parent_unreachable_sandbox(monkeypatch):
    monkeypatch.setattr(parent_land, "exec_repo_git", AsyncMock(side_effect=SandboxGitError("down")))

    ok, detail = await parent_land.advance_parent(LIVE, PROJECT, old_sha="b", new_commit="c")

    assert not ok and "down" in detail


@pytest.mark.parametrize("out,ok,text", [
    ("MERGED\n", True, "c" * 40),
    ("STALE " + "d" * 40, False, "moved while gates ran"),
    ("NOTFF", False, "does not fast-forward"),
])
async def test_advance_pin_is_a_compare_and_swap_ref_update(monkeypatch, out, ok, text):
    exec_git = AsyncMock(return_value=out)
    monkeypatch.setattr(parent_land, "exec_repo_git", exec_git)

    result = await parent_land.advance_parent(PIN, PROJECT, old_sha="b" * 40, new_commit="c" * 40)

    assert result[0] is ok and text in result[1]
    assert exec_git.await_args is not None
    script = exec_git.await_args.args[2]
    assert f"update-ref refs/heads/{PIN.branch} {'c' * 40} {'b' * 40}" in script
    assert "merge --ff-only" not in script  # never touches the parent's working tree


@pytest.mark.parametrize("out,moved", [("moved\n", True), ("", False)])
async def test_reset_child_onto(monkeypatch, out, moved):
    exec_git = AsyncMock(return_value=out)
    monkeypatch.setattr(parent_land, "exec_repo_git", exec_git)
    assert await parent_land.reset_child_onto(
        _child(), PROJECT, pushed_sha="a", new_tip="c", branch="main",
    ) is moved
    assert exec_git.await_args is not None
    script = exec_git.await_args.args[2]
    # origin/main follows the merge result even when the checkout can't move.
    assert "git update-ref refs/remotes/origin/main c || true" in script
    assert script.index("update-ref refs/remotes/origin/main") < script.index("reset --quiet --hard")


@pytest.mark.parametrize("out,dropped", [("DROPPED\n", True), ("", False)])
async def test_drop_parent_pin_deletes_only_at_its_sha(monkeypatch, out, dropped):
    exec_git = AsyncMock(return_value=out)
    monkeypatch.setattr(parent_land, "exec_repo_git", exec_git)
    assert await parent_land.drop_parent_pin(_child(), PROJECT, name="pin/abc-1", sha="s1") is dropped
    assert exec_git.await_args is not None
    assert "update-ref -d refs/heads/pin/abc-1 s1" in exec_git.await_args.args[2]


async def test_drop_parent_pin_never_raises(monkeypatch):
    monkeypatch.setattr(parent_land, "exec_repo_git", AsyncMock(side_effect=parent_land.SandboxGitError("down")))
    assert await parent_land.drop_parent_pin(_child(), PROJECT, name="pin/abc-1", sha="s1") is False
