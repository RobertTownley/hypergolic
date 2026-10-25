from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from anthropic.types import MessageParam, TextBlockParam

from hypergolic.sessions import session_rows
from hypergolic.projects.operations import project_name
from hypergolic.db.utils import to_iso_utc
from hypergolic.dispatch.state import (
    DispatchResult,
    _child_to_parent,
    _finalize_on_auto_conclude,
    _pending_dispatches,
)
from hypergolic.sandbox.manager.lifecycle import schedule_session_sandbox_cleanup
from hypergolic.enums import ModelTier, SessionStatus
from hypergolic.messages.types import BroadcastEvent, BroadcastFn
from hypergolic.sessions.operations import create_session, load_conducted_by, load_session
from hypergolic.sessions.status import get_session_status, set_session_status
from hypergolic.dispatch import state as _state
from hypergolic.pins.runtime import pin_app, register_snapshot_use
from hypergolic.git.commands import run_git_command
from hypergolic.git.sandbox_repo import REPO_APP, REPO_HARNESS
from hypergolic.harness.app.state import app_context, get_app
from hypergolic.schemas import Session
from hypergolic.tools import approval_delegate

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App

logger = logging.getLogger(__name__)

CONCLUDE_INSTRUCTION = (
    "\n\nCRITICAL: You MUST call `conclude` as your final action "
    "\u2014 the parent session is deadlocked until you do. "
    "Never end your turn without calling conclude."
)


def _build_child_session_payload(child_session_id: str) -> dict:
    child_db = session_rows.fetch_one(child_session_id)

    return {
        "id": child_db.id,
        "model_tier": child_db.model_tier,
        "project_id": child_db.project_id,
        "project_name": project_name(child_db.project_id),
        "role": child_db.role,
        "status": child_db.status,
        "created_at": to_iso_utc(child_db.created_at),
        "updated_at": to_iso_utc(child_db.updated_at),
        "message_count": 0,
        "workflow_id": None,
        "workflow_name": None,
        "workflow_state_id": None,
        "workflow_state_name": None,
        "parent_id": child_db.parent_id,
        "description": None,
        "conclusion_rating": None,
        "conclusion_feedback": None,
        "concluded_at": None,
    }


async def send_turn(
    child_session_id: str,
    parent_session_id: str,
    message: str,
    broadcast: BroadcastFn,
) -> DispatchResult:
    if not _state._turn_runner:
        raise RuntimeError("No turn runner registered. Dispatch is not available in this context.")

    user_message: MessageParam = {
        "role": "user",
        "content": [TextBlockParam(type="text", text=message)],
    }

    child_payload = await asyncio.to_thread(_build_child_session_payload, child_session_id)
    await broadcast(BroadcastEvent(
        type="dispatch_started",
        role="system",
        content=[{
            "child_session_id": child_session_id,
            "child_session": child_payload,
        }],
        session_id=parent_session_id,
    ))

    loop = asyncio.get_running_loop()
    future: asyncio.Future[DispatchResult] = loop.create_future()
    _pending_dispatches[child_session_id] = future
    _child_to_parent[child_session_id] = parent_session_id

    _state._turn_runner(child_session_id, user_message)

    try:
        result = await future
        result.child_session_id = child_session_id
        return result
    except asyncio.CancelledError:
        _pending_dispatches.pop(child_session_id, None)
        _child_to_parent.pop(child_session_id, None)
        await asyncio.to_thread(set_session_status, child_session_id, SessionStatus.INTERRUPTED)
        schedule_session_sandbox_cleanup(child_session_id)
        raise
    finally:
        _pending_dispatches.pop(child_session_id, None)
        _child_to_parent.pop(child_session_id, None)


def _pin_branch(project_path: Path, sha: str) -> str:
    branch = f"pin/{sha[:12]}"
    run_git_command("branch", "-f", branch, sha, cwd=project_path, check=True)
    return branch


def _resolve_commit(project_path: Path, ref: str) -> str:
    result = run_git_command("rev-parse", "--verify", f"{ref}^{{commit}}", cwd=project_path, check=True)
    return result.stdout.strip()


async def _make_parent_pin(parent: Session, sha_or_ref: str) -> str:
    from hypergolic.git.parent_land import create_parent_pin, parent_pin_name

    project = get_app().find_project(parent.project_id)
    if project is None:
        raise ValueError(f"Unknown project {parent.project_id!r}")
    sha = await asyncio.to_thread(_resolve_commit, Path(project.path), sha_or_ref)
    name = parent_pin_name(sha)
    await create_parent_pin(parent, project, sha=sha, name=name)
    return name


DEFAULT_BASE = "main"


def _host_base(project_path: Path, base: str | None) -> str:
    name = base or DEFAULT_BASE
    found = run_git_command(
        "rev-parse", "--verify", "--quiet", f"refs/heads/{name}", cwd=project_path,
    )
    if found.returncode == 0:
        return name
    if base:
        raise ValueError(f"No branch {base!r} in {project_path}")
    result = run_git_command("rev-parse", "--abbrev-ref", "HEAD", cwd=project_path, check=True)
    return result.stdout.strip()


def _create_target(
    parent: Session,
    role: str,
    model_tier: ModelTier | None,
    dispatch_prompt: str | None,
    child: bool,
    project_id: str | None,
    repo_pins: dict[str, str],
    pinned_app: "App | None",
    parent_pin: str | None = None,
    base: str | None = None,
    conducted: bool = False,
    app_overrides: dict[str, object] | None = None,
) -> Session:
    app = pinned_app or get_app()
    target_project_id = project_id or parent.project_id
    project = app.find_project(target_project_id)
    if project is None:
        raise ValueError(f"Unknown project {target_project_id!r}")
    app_pin = repo_pins.get(REPO_APP)
    from_parent_tip = child and target_project_id == parent.project_id and base is None
    if from_parent_tip and parent_pin:
        base_branch, worktree_project_path = parent_pin, Path(parent.worktree_path)
    elif app_pin:
        base_branch, worktree_project_path = _pin_branch(Path(project.path), app_pin), None
    elif from_parent_tip:
        base_branch, worktree_project_path = parent.live_branch(), Path(parent.worktree_path)
    else:
        base_branch, worktree_project_path = _host_base(Path(project.path), base), None

    def _create() -> Session:
        return create_session(
            project_id=target_project_id,
            base_branch=base_branch,
            model_tier=model_tier or parent.model_tier,
            role=role,
            parent_id=parent.id if child else None,
            dispatch_prompt=dispatch_prompt,
            worktree_project_path=worktree_project_path,
            origin=None if child else "dispatch",
            repo_pins=repo_pins,
            conducted_by=parent.id if conducted else None,
            app_overrides=app_overrides,
        )

    if pinned_app is None:
        return _create()
    with app_context(pinned_app):
        return _create()


async def dispatch(
    parent_session_id: str,
    content_blocks: list[dict[str, Any]],
    dispatch_prompt: str | None,
    broadcast: BroadcastFn,
    role: str,
    model_tier: ModelTier | None = None,
    *,
    child: bool = True,
    project_id: str | None = None,
    base: str | None = None,
    wait: bool = True,
    repo_pins: dict[str, str] | None = None,
    pinned_app: "App | None" = None,
    conducted: bool = False,
    app_overrides: dict[str, object] | None = None,
) -> DispatchResult:
    if not _state._turn_runner:
        raise RuntimeError("No turn runner registered. Dispatch is not available in this context.")

    parent_session = await asyncio.to_thread(load_session, parent_session_id)
    pins = repo_pins or {}
    full_prompt = (
        dispatch_prompt + CONCLUDE_INSTRUCTION
        if dispatch_prompt is not None and wait
        else dispatch_prompt
    )

    same_project = (project_id or parent_session.project_id) == parent_session.project_id
    parent_pin = (
        await _make_parent_pin(parent_session, pins[REPO_APP])
        if child and same_project and base is None and pins.get(REPO_APP) else None
    )
    target = await asyncio.to_thread(
        _create_target,
        parent_session, role, model_tier, full_prompt, child, project_id, pins, pinned_app,
        parent_pin, base, conducted, app_overrides,
    )
    if pinned_app is not None:
        pin_app(target.id, pinned_app)
        if REPO_HARNESS in pins:
            register_snapshot_use(target.id, pins[REPO_HARNESS])

    user_message: MessageParam = {
        "role": "user",
        "content": [
            TextBlockParam(type="text", text=b["text"])
            for b in content_blocks if b.get("type") == "text"
        ],
    }

    if not wait:
        await _announce(target.id, broadcast, parent_session_id)
        _state._turn_runner(target.id, user_message)
        return DispatchResult(
            outcome="started",
            conclusion=f"Session {target.id} started",
            worktree_branch=target.worktree_branch,
            child_session_id=target.id,
        )

    loop = asyncio.get_running_loop()
    future: asyncio.Future[DispatchResult] = loop.create_future()
    _pending_dispatches[target.id] = future
    _child_to_parent[target.id] = parent_session_id
    if not conducted:
        _finalize_on_auto_conclude.add(target.id)
    if child:
        assert target.base_branch
        approval_delegate.open_inbox(target.id, target.base_branch)

    await _announce(target.id, broadcast, parent_session_id)
    _state._turn_runner(target.id, user_message)
    return await wait_on_child(target.id)


async def wait_on_child(child_id: str) -> DispatchResult:
    future = _pending_dispatches.get(child_id)
    if future is None:
        return DispatchResult(
            outcome="failure",
            conclusion=f"No dispatch is waiting on session {child_id}",
            child_session_id=child_id,
        )
    inbox = approval_delegate.inbox_for(child_id)
    getter = asyncio.ensure_future(inbox.get()) if inbox is not None else None
    try:
        await asyncio.wait(
            {future, getter} if getter is not None else {future},
            return_when=asyncio.FIRST_COMPLETED,
        )
    except asyncio.CancelledError:
        _release(child_id)
        await asyncio.to_thread(set_session_status, child_id, SessionStatus.INTERRUPTED)
        return DispatchResult(
            outcome="suppressed",
            conclusion="Parent session was interrupted",
            child_session_id=child_id,
        )
    finally:
        if getter is not None and not getter.done():
            getter.cancel()
    if not future.done():
        assert getter is not None
        pending = getter.result()
        return DispatchResult(
            outcome="awaiting_approval",
            conclusion=approval_delegate.describe(pending),
            child_session_id=child_id,
        )
    _release(child_id)
    result = future.result()
    result.child_session_id = child_id
    result.conducted = await asyncio.to_thread(load_conducted_by, child_id) is not None
    return result


async def reply_to_child(child_id: str, parent_session_id: str, message: str) -> DispatchResult:
    if not _state._turn_runner:
        raise RuntimeError("No turn runner registered. Dispatch is not available in this context.")
    child = await asyncio.to_thread(load_session, child_id)
    if child.conducted_by != parent_session_id:
        return DispatchResult(
            outcome="failure",
            conclusion=f"{child_id} is not a conducted child of yours (start one with `dispatch --eval`)",
            child_session_id=child_id,
        )
    if await asyncio.to_thread(get_session_status, child_id) == SessionStatus.CONCLUDED:
        return DispatchResult(
            outcome="failure",
            conclusion=f"{child_id} has concluded",
            child_session_id=child_id,
        )
    if child_id in _pending_dispatches:
        return DispatchResult(
            outcome="failure",
            conclusion=f"{child_id} is still running; answer its request or wait on it",
            child_session_id=child_id,
        )
    future: asyncio.Future[DispatchResult] = asyncio.get_running_loop().create_future()
    _pending_dispatches[child_id] = future
    _child_to_parent[child_id] = parent_session_id
    assert child.base_branch
    approval_delegate.open_inbox(child_id, child.base_branch)
    _state._turn_runner(child_id, {"role": "user", "content": [TextBlockParam(type="text", text=message)]})
    return await wait_on_child(child_id)


def _release(child_id: str) -> None:
    _pending_dispatches.pop(child_id, None)
    _child_to_parent.pop(child_id, None)
    _finalize_on_auto_conclude.discard(child_id)
    approval_delegate.close(child_id)


async def _announce(session_id: str, broadcast: BroadcastFn, parent_session_id: str) -> None:
    payload = await asyncio.to_thread(_build_child_session_payload, session_id)
    await broadcast(BroadcastEvent(
        type="dispatch_started",
        role="system",
        content=[{"child_session_id": session_id, "child_session": payload}],
        session_id=parent_session_id,
    ))
