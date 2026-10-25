"""child_end: one mocked path for ending children and dropping their host refs."""
from unittest.mock import AsyncMock, MagicMock, call, patch

from hypergolic.dispatch import child_end
from hypergolic.dispatch.state import _child_to_parent, _pending_dispatches
from hypergolic.enums import SessionStatus
from tests._factories import build_session

M = "hypergolic.dispatch.child_end"


def _pinned_child():
    return build_session("c-1", parent_id="p-1", worktree_branch="main-C1", base_branch="pin/711835e00000-abc123")


def test_ref_branches_cover_the_child_branch_and_its_pin():
    child = _pinned_child()
    assert child_end.child_ref_branches(child, keep_branch=False) == ["main-C1", "pin/711835e00000-abc123"]
    assert child_end.child_ref_branches(child, keep_branch=True) == ["pin/711835e00000-abc123"]


def test_ref_branches_of_an_unpinned_child_skip_the_parent_branch():
    child = build_session("c-1", parent_id="p-1", worktree_branch="main-C1", base_branch="main-P1")
    assert child_end.child_ref_branches(child, keep_branch=False) == ["main-C1"]


def test_drop_child_refs_deletes_each_and_never_raises():
    child = _pinned_child()
    with patch(f"{M}.delete_hypergolic_ref", side_effect=[RuntimeError("gone"), None]) as delete:
        child_end.drop_child_refs(child, keep_branch=False)
    assert delete.call_args_list == [
        call(child.project_path, child.project_id, "main-C1"),
        call(child.project_path, child.project_id, "pin/711835e00000-abc123"),
    ]


def _end_patches(child):
    return {
        "load_session": MagicMock(return_value=child),
        "_teardown": AsyncMock(),
        "drop_child_refs": MagicMock(),
        "_drop_unused_pin": AsyncMock(),
        "set_session_status_and_broadcast": AsyncMock(),
        "set_concluded_at": MagicMock(),
        "schedule_session_sandbox_cleanup": MagicMock(),
        "release_harness_snapshots": MagicMock(),
    }


async def test_end_child_forgets_tears_down_drops_refs_and_concludes():
    child = _pinned_child()
    _pending_dispatches["c-1"] = MagicMock()
    _child_to_parent["c-1"] = "p-1"
    mocks = _end_patches(child)
    broadcast = AsyncMock()
    with patch.multiple(M, **mocks), patch(f"{M}.approval_delegate.close") as close:
        await child_end.end_child("c-1", broadcast, keep_branch=True)
    assert "c-1" not in _pending_dispatches and "c-1" not in _child_to_parent
    close.assert_called_once_with("c-1")
    mocks["_teardown"].assert_awaited_once_with(child, keep_branch=True)
    mocks["drop_child_refs"].assert_called_once_with(child, keep_branch=True)
    mocks["set_session_status_and_broadcast"].assert_awaited_once_with("c-1", SessionStatus.CONCLUDED, broadcast)
    mocks["schedule_session_sandbox_cleanup"].assert_called_once_with("c-1")
    mocks["_drop_unused_pin"].assert_awaited_once_with(child)
    assert broadcast.call_args.args[0].type == "dispatch_concluded"


async def test_end_child_with_error_status_keeps_error_and_skips_concluded_event():
    child = _pinned_child()
    mocks = _end_patches(child)
    broadcast = AsyncMock()
    with patch.multiple(M, **mocks):
        await child_end.end_child("c-1", broadcast, status=SessionStatus.ERROR)
    mocks["set_session_status_and_broadcast"].assert_awaited_once_with("c-1", SessionStatus.ERROR, broadcast)
    mocks["drop_child_refs"].assert_called_once()
    mocks["_drop_unused_pin"].assert_awaited_once_with(child)
    broadcast.assert_not_awaited()


async def test_drop_unused_pin_asks_the_parent_to_delete_the_pin_at_its_sha():
    child = _pinned_child()
    child.repo_pins = {"app": "711835e" + "0" * 33}
    parent, project = build_session("p-1"), MagicMock()
    app = MagicMock()
    app.find_project.return_value = project
    with patch(f"{M}.load_session", return_value=parent), patch(f"{M}.get_app", return_value=app), patch(
        f"{M}.drop_parent_pin", new=AsyncMock(return_value=True),
    ) as drop:
        await child_end._drop_unused_pin(child)
    drop.assert_awaited_once_with(parent, project, name="pin/711835e00000-abc123", sha=child.repo_pins["app"])


async def test_drop_unused_pin_skips_an_unpinned_child():
    child = build_session("c-1", parent_id="p-1", worktree_branch="main-C1", base_branch="main-P1")
    with patch(f"{M}.drop_parent_pin", new=AsyncMock()) as drop:
        await child_end._drop_unused_pin(child)
    drop.assert_not_awaited()


async def test_end_child_still_concludes_when_teardown_fails():
    child = _pinned_child()
    mocks = _end_patches(child)
    mocks["_teardown"] = AsyncMock(side_effect=RuntimeError("sandbox gone"))
    with patch.multiple(M, **mocks):
        await child_end.end_child("c-1", AsyncMock())
    mocks["drop_child_refs"].assert_called_once()
    mocks["set_session_status_and_broadcast"].assert_awaited_once()


async def test_end_children_ends_open_ones_and_sweeps_refs_of_ended_ones():
    ended = build_session("c-old", parent_id="p-1", worktree_branch="main-OLD")
    cancel = AsyncMock()
    with patch(f"{M}._children_of", return_value=[("c-open", "idle"), ("c-old", "concluded")]), patch(
        f"{M}.load_session", return_value=ended,
    ), patch(f"{M}.drop_child_refs") as drop, patch(f"{M}.end_child", new=AsyncMock()) as end:
        out = await child_end.end_children("p-1", AsyncMock(), cancel)
    assert out == ["c-open"]
    cancel.assert_awaited_once_with("c-open")
    assert end.call_args.args[0] == "c-open"
    drop.assert_called_once_with(ended, keep_branch=False)


async def test_conclude_tool_ends_children_and_drops_its_own_pin_ref():
    from hypergolic.dispatch.conclude.handler import _end_own_children

    child = _pinned_child()
    ctx = MagicMock(broadcast=AsyncMock())
    with patch(f"{M}.end_children", new=AsyncMock()) as end_all, patch(f"{M}.drop_child_refs") as drop:
        await _end_own_children(child, ctx)
    end_all.assert_awaited_once_with("c-1", ctx.broadcast)
    drop.assert_called_once_with(child, keep_branch=True)
