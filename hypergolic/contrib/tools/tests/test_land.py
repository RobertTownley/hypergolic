"""Tests for hypergolic.contrib.tools.land (host-side land pipeline).

Fully mocked: no git process, no filesystem, no sandbox. The git helpers land
calls (candidate building, branch resolution, advancing) are stubbed at the
module boundary; their own behaviour is covered in gates/ and git/ tests.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from hypergolic.commands import approval_bus
from hypergolic.harness.primitives.results import CommandResult
from tests.helpers.land import patch_land
from hypergolic.contrib.tools.land import LandInput, LandTool, _handle_land
from hypergolic.gates.model import UserApproval
from hypergolic.gates.request import GateVerdict
from hypergolic.git.commands import GitResult
from hypergolic.git.sandbox_integrate import RepoSlot
from hypergolic.harness.primitives.tool import ToolContext
from hypergolic.tools import guaranteed_output
from hypergolic.tools.approval import AnnotationItem, ApprovalResponse
from tests._factories import approval_of, build_session

PUSHED = "a" * 40
BASE = "b" * 40
CANDIDATE = "c" * 40
NEW_TIP = "d" * 40
REBASED = "e" * 40
REMOTE = "f" * 40
HOST = Path("/host/repo")


def _git(returncode: int = 0, stdout: str = "", stderr: str = "") -> GitResult:
    return GitResult(returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def env(monkeypatch):
    project = SimpleNamespace(id="proj", land_mode="squash", on_stale_base="regate")
    session = build_session(sid="L1", project_id="proj", project_path=str(HOST))
    slot = RepoSlot(
        repo="app", workdir="/app", host_repo=HOST, base_branch="main",
        session_branch="main-L1", ref_scope="proj",
    )
    branches = {"main": BASE}

    async def git(*args, cwd=None):
        if args[0] == "rev-parse":  # _rev: remote-tracking lookups
            sha = branches.get(args[-1].removesuffix("^{commit}"))
            return _git(0, sha + "\n") if sha else _git(1)
        if args[0] == "merge-base":
            return _git(0, BASE + "\n")
        return _git()

    m = SimpleNamespace(
        branches=branches,
        git=AsyncMock(side_effect=git),
        resolve_branch=AsyncMock(side_effect=lambda host, b: branches.get(b)),
        is_ancestor=AsyncMock(return_value=True),
        build_candidate=AsyncMock(return_value=CANDIDATE),
        derive_message=AsyncMock(return_value="add a\n\nadd b"),
        tip_message=AsyncMock(return_value="add b"),
        rebase=AsyncMock(return_value=(REBASED, "")),
        advance=AsyncMock(return_value=(True, CANDIDATE)),
        blocker=AsyncMock(return_value=None),
        pipeline=AsyncMock(return_value=GateVerdict(ok=True, lines=["✓ gates"])),
        gates=[],
        post_land=AsyncMock(),
        record=MagicMock(),
    )
    app = MagicMock()
    app.find_project.return_value = project
    patch_land(monkeypatch, {
        "get_app": lambda: app,
        "gates_for": lambda *_: m.gates,
        "slot_for": lambda *_: slot,
        "land_parent": lambda *_: None,
        "fetch_quarantine_ref": AsyncMock(return_value=_git()),
        "async_run_git_command": m.git,
        "resolve_branch": m.resolve_branch,
        "is_ancestor": m.is_ancestor,
        "build_candidate": m.build_candidate,
        "derive_message": m.derive_message,
        "tip_message": m.tip_message,
        "rebase_candidate": m.rebase,
        "advance_branch": m.advance,
        "checkout_blocker": m.blocker,
        "run_pipeline": m.pipeline,
        "post_land": m.post_land,
    })
    monkeypatch.setattr("hypergolic.gates.user_approval.record_approval", m.record)
    ctx = ToolContext(session=session, broadcast=AsyncMock(), tool_id="land")
    return SimpleNamespace(ctx=ctx, session=session, project=project, **vars(m))


def _real_pipeline(env, monkeypatch):
    """Run the real gate runner with the default gate (UserApproval)."""
    from hypergolic.gates.runner import run_pipeline

    env.gates.append(UserApproval())
    patch_land(monkeypatch, {"run_pipeline": run_pipeline})


async def test_dirty_base_checkout_rejects_before_any_gate(env):
    env.blocker.return_value = "the `main` checkout has uncommitted changes to uv.lock"
    result = await _land(env)
    assert result.exit_code == 1 and "uv.lock" in result.stderr
    env.pipeline.assert_not_awaited()


async def _land(env, **kw: Any) -> CommandResult:
    fields: dict[str, Any] = {"sha": PUSHED, "branch": "main", **kw}
    return await _handle_land(LandInput.model_validate(fields), env.ctx)


def _out(result) -> str:
    return result.stdout + result.stderr


async def test_land_tool_metadata():
    assert LandTool.id == "land"
    assert approval_of(LandTool) == "ALLOW"


async def test_ungated_push_lands_squash(env):
    result = await _land(env)

    assert result.exit_code == 0, _out(result)
    assert "merged into main as cccccccc" in result.stdout
    env.build_candidate.assert_awaited_once_with(
        HOST, sha=PUSHED, base_sha=BASE, message="add a\n\nadd b",
    )
    env.advance.assert_awaited_once_with(
        base_branch="main", old_base_sha=BASE, new_commit=CANDIDATE, cwd=HOST,
    )
    env.post_land.assert_awaited_once()
    assert env.post_land.await_args.args[-1] == PUSHED


async def test_message_push_option_overrides(env):
    await _land(env, message="Ship the feature")

    env.derive_message.assert_not_awaited()
    assert env.build_candidate.await_args.kwargs["message"] == "Ship the feature"


async def test_fast_forward_mode_lands_the_pushed_commit(env):
    result = await _land(env, mode="fast-forward")

    assert result.exit_code == 0, _out(result)
    assert "fast-forwarded main as aaaaaaaa" in result.stdout
    env.build_candidate.assert_not_awaited()
    env.tip_message.assert_awaited_once_with(HOST, BASE, PUSHED)
    assert env.advance.await_args.kwargs["new_commit"] == PUSHED


async def test_project_land_mode_fast_forward_is_the_default_mode(env):
    env.project.land_mode = "fast-forward"

    result = await _land(env)

    assert result.exit_code == 0 and "fast-forwarded" in result.stdout
    env.build_candidate.assert_not_awaited()


async def test_fast_forward_mode_rejects_a_base_that_moves_during_gates(env):
    env.advance.return_value = (False, "moved")
    env.branches["main"] = BASE
    env.resolve_branch.side_effect = [BASE, NEW_TIP]  # target lookup, then dest.tip()

    result = await _land(env, mode="fast-forward")

    assert result.exit_code == 1 and "up-to-date" in _out(result)
    env.rebase.assert_not_awaited()


async def test_stale_fetch_rejects_with_pull_guidance(env):
    env.is_ancestor.return_value = False

    result = await _land(env)

    assert result.exit_code == 1
    assert "git pull origin main" in _out(result)
    env.pipeline.assert_not_awaited()


async def test_nothing_to_land_rejects(env):
    result = await _land(env, sha=BASE)

    assert result.exit_code == 1 and "nothing to land" in _out(result)


async def test_default_pipeline_requires_a_human(env, monkeypatch):
    _real_pipeline(env, monkeypatch)

    result = await _land(env)

    assert result.exit_code == 1 and "no human" in result.stdout
    env.advance.assert_not_awaited()


async def _with_human(env, response: ApprovalResponse):
    callback = AsyncMock(return_value=response)
    approval_bus.register(env.session.id, callback, AsyncMock())
    try:
        return await _land(env), callback
    finally:
        approval_bus.unregister(env.session.id)


async def test_user_approval_gate_lands_and_records(env, monkeypatch):
    _real_pipeline(env, monkeypatch)
    env.derive_message.return_value = "add a"

    result, callback = await _with_human(env, ApprovalResponse(approved=True))

    assert result.exit_code == 0, _out(result)
    assert "user approval: approved" in result.stdout
    request = callback.call_args[0][0]
    assert request.tool_name == "land"
    assert request.tool_input["repo"] == "app"
    assert request.tool_input["commit_message"] == "add a"
    assert request.tool_input["arguments"]["branch"] == "main"
    env.record.assert_called_once()
    env.advance.assert_awaited_once()


async def test_approval_notes_are_guaranteed_output(env, monkeypatch):
    _real_pipeline(env, monkeypatch)
    guaranteed_output.drain(env.session.id)

    result, _ = await _with_human(env, ApprovalResponse(
        approved=True,
        annotations=[AnnotationItem(highlighted_text="a.txt:1", comment="rename this")],
    ))

    assert result.exit_code == 0, _out(result)
    assert "note on “a.txt:1”: rename this" in result.stdout
    assert any("rename this" in t for t in guaranteed_output.drain(env.session.id))


async def test_denial_reason_reaches_the_push_output(env, monkeypatch):
    _real_pipeline(env, monkeypatch)

    result, _ = await _with_human(env, ApprovalResponse(approved=False, denial_reason="needs tests"))

    assert result.exit_code == 1 and "needs tests" in result.stdout
    env.advance.assert_not_awaited()


async def test_stale_base_during_gates_regates_the_rebased_candidate(env):
    env.advance.side_effect = [(False, "moved"), (True, REBASED)]
    env.resolve_branch.side_effect = [BASE, NEW_TIP]

    result = await _land(env)

    assert result.exit_code == 0, _out(result)
    assert "moved while gates ran; re-running gates" in result.stdout
    env.rebase.assert_awaited_once_with(HOST, candidate=CANDIDATE, new_tip=NEW_TIP, message="add a\n\nadd b")
    assert env.pipeline.await_count == 2
    assert env.advance.await_args.kwargs == {
        "base_branch": "main", "old_base_sha": NEW_TIP, "new_commit": REBASED, "cwd": HOST,
    }


async def test_stale_base_that_cannot_rebase_rejects(env):
    env.advance.return_value = (False, "moved")
    env.resolve_branch.side_effect = [BASE, NEW_TIP]
    env.rebase.return_value = (None, "conflict in a.txt")

    result = await _land(env)

    assert result.exit_code == 1 and "conflict in a.txt" in _out(result)


async def test_stale_base_reject_mode(env):
    env.project.on_stale_base = "reject"
    env.advance.return_value = (False, "moved")
    env.resolve_branch.side_effect = [BASE, NEW_TIP]

    result = await _land(env)

    assert result.exit_code == 1 and "up-to-date" in _out(result)
    env.rebase.assert_not_awaited()


async def test_bad_branch_name_rejected(env):
    env.git.side_effect = None
    env.git.return_value = _git(1)

    result = await _land(env, branch="-f")

    assert result.exit_code == 1 and "branch name" in result.stderr


async def test_bad_sha_rejected(env):
    result = await _land(env, sha="notasha")

    assert result.exit_code == 1
    env.pipeline.assert_not_awaited()


def _git_calls(env, verb: str) -> list[tuple]:
    return [c.args for c in env.git.await_args_list if c.args[0] == verb]


async def test_new_branch_is_created_at_fork_point_after_gates(env):
    result = await _land(env, branch="feat/x")

    assert result.exit_code == 0, _out(result)
    assert "created feat/x at bbbbbbbb" in result.stdout
    assert "merged into feat/x as" in result.stdout
    assert ("merge-base", BASE, PUSHED) in _git_calls(env, "merge-base")
    assert ("branch", "--no-track", "feat/x", BASE) in _git_calls(env, "branch")
    assert env.advance.await_args.kwargs["base_branch"] == "feat/x"


async def test_rejected_land_creates_no_branch(env):
    env.pipeline.return_value = GateVerdict(ok=False, lines=["✗ user approval"])

    result = await _land(env, branch="feat/x")

    assert result.exit_code == 1
    assert _git_calls(env, "branch") == []
    env.advance.assert_not_awaited()


async def test_new_branch_without_shared_history_rejects(env):
    async def git(*args, cwd=None):
        return _git(1) if args[0] in {"merge-base", "rev-parse"} else _git()

    env.git.side_effect = git

    result = await _land(env, branch="feat/x")

    assert result.exit_code == 1 and "share no history" in _out(result)


async def test_existing_branch_needs_fast_forward(env):
    env.branches["feat/x"] = NEW_TIP
    env.is_ancestor.return_value = False

    result = await _land(env, branch="feat/x")

    assert result.exit_code == 1
    assert "git pull origin feat/x" in _out(result)
    env.is_ancestor.assert_awaited_once_with(HOST, NEW_TIP, PUSHED)


async def test_github_branch_roots_a_tracking_branch(env):
    env.branches["refs/remotes/origin/feat/gh"] = REMOTE

    result = await _land(env, branch="feat/gh")

    assert result.exit_code == 0, _out(result)
    assert env.build_candidate.await_args.kwargs["base_sha"] == REMOTE
    assert ("branch", "--no-track", "feat/gh", REMOTE) in _git_calls(env, "branch")
    assert ("branch", "--set-upstream-to=origin/feat/gh", "feat/gh") in _git_calls(env, "branch")


async def test_general_approval_note_has_no_highlight_label(env, monkeypatch):
    _real_pipeline(env, monkeypatch)

    result, _ = await _with_human(env, ApprovalResponse(
        approved=True, annotations=[AnnotationItem(highlighted_text="", comment="ok")],
    ))

    assert result.exit_code == 0, _out(result)
    assert "note: ok" in result.stdout
    assert "note on" not in result.stdout
