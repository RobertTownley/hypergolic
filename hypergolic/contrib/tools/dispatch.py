"""Unified dispatch tool.

One ``dispatch`` tool starts a session from a prompt: a child cut from the
caller's tip (the default) or from a host branch (``base``, or another
``project``'s main), or a standalone session in any project; blocking
on its conclusion or returning as soon as it starts; optionally with /app,
/harness, /shared pinned to given refs or to a past session's recorded shas.
Sessions whose role declares ``dispatch_targets`` get the tool, up to
``App.max_dispatch_depth``; the ``role`` enum is those target role IDs,
computed at build time, and it defaults to generalist.
"""
from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Iterable

from pydantic import Field

from hypergolic.contrib.tools.approvals.paths import decide_read
from hypergolic.tools import approval_delegate
from hypergolic.pins.app_overrides import AppOverrides, overridden_app
from hypergolic.pins.pinned_app import snapshot_app_for
from hypergolic.harness.app.state import get_app
from hypergolic.sessions.pins import resolve_pin_refs
from hypergolic.enums import ModelTier
from hypergolic.schemas import Session
from hypergolic.harness.primitives.results import InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.tools.paths import resolve_path
from hypergolic.commands.argv import dispatch_argv

logger = logging.getLogger(__name__)

_DISPATCH_RULES = """- The user can see your conversation, but strongly prefer to work autonomously
- Your parent's prompt is your specification — follow it precisely
- Be thorough but efficient
- Your repo is a fresh clone cut from your parent's branch at its committed tip when you were dispatched — you see exactly what the parent had committed, nothing it hadn't. Commit your work, then land it with `git push origin HEAD:<your base branch>`; your parent reviews the merge and accepts or rejects it. Never delete your branch
- Conclude "success" with a summary of what you did, or "failure" with the reason you couldn't"""

DISPATCH_PROMPT = (
    "You are an agent dispatched to complete a task; your parent session is blocked until you conclude.\n\n"
    + _DISPATCH_RULES
)

ASYNC_DISPATCH_PROMPT = (
    "You are an agent dispatched to complete a task; your parent session is not waiting on you "
    "and may review your session's history later.\n\n" + _DISPATCH_RULES
)


def _render_file_reference(
    raw_path: str,
    child_session: Session,
    receiver_can_read_files: bool,
) -> str:
    """Load *raw_path* for inclusion in the dispatched prompt.

    Permission model:
    - If the receiver has no shell, it has no way to read files, so mark as
      missing.
    - If the path's read approval for the receiving role is not ALLOW, mark as
      missing (REQUIRE_APPROVAL and DENY both count as "not allowed
      without user intervention").
    - Otherwise read and inline the file contents.
    """
    if not receiver_can_read_files:
        return (
            f"=== {raw_path} ===\n"
            f"[not provided: receiving role cannot read files]"
        )

    decision = decide_read([raw_path], child_session)
    if decision.decision != "ALLOW":
        return (
            f"=== {raw_path} ===\n"
            f"[not provided: receiving role is not permitted to read this path]"
        )

    path = resolve_path(raw_path, child_session)
    if not path.exists():
        return f"=== {raw_path} ===\n[not provided: file not found]"
    if not path.is_file():
        return f"=== {raw_path} ===\n[not provided: not a file]"
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"=== {raw_path} ===\n[not provided: file is not valid UTF-8 text]"
    except PermissionError:
        return f"=== {raw_path} ===\n[not provided: permission denied]"
    except Exception as e:
        return f"=== {raw_path} ===\n[not provided: {e}]"
    return f"=== {raw_path} ===\n{content}"


def _build_child_session_view(parent_session: Session, role: str) -> Session:
    """Build a Session mirroring what the child will see.

    Used only for permission evaluation — no DB row is created here.
    """
    return parent_session.model_copy(
        update={"id": f"{parent_session.id}:dispatch-probe", "role": role},
    )


def _attach_references(prompt: str, refs: list[str], child_view: Session, can_read: bool) -> list[dict]:
    blocks: list[dict] = [{"type": "text", "text": prompt}]
    if refs:
        rendered = [_render_file_reference(r, child_view, can_read) for r in refs]
        blocks.append({"type": "text", "text": "## Attached file references\n\n" + "\n\n".join(rendered)})
    return blocks


def _resolve_pins(pins: dict[str, str], project_id: str) -> dict[str, str]:
    """Effective full-sha pins for *project_id*."""
    if not pins:
        return {}
    project = get_app().find_project(project_id)
    if project is None:
        raise ValueError(f"Unknown project {project_id!r}")
    return resolve_pin_refs(pins, project.id, project.path)


class ResumeOutcome(str, Enum):
    APPROVE = "approve"
    DENY = "deny"
    ESCALATE = "escalate"
    MOCK = "mock"


async def _resume(inp, parent_id: str) -> ToolResult:
    from hypergolic.dispatch.runner import wait_on_child

    if inp.outcome is None:
        return ToolResult.text("resume needs --outcome approve|deny|escalate|mock", is_error=True)
    request_id = inp.resume
    child_id = approval_delegate.child_of(request_id)
    error = approval_delegate.answer(
        request_id, parent_id, inp.outcome.value, inp.message,
        result=inp.result, result_is_error=inp.result_is_error,
    )
    if error is not None or child_id is None:
        return ToolResult.text(error or f"no approval request {request_id!r} is waiting", is_error=True)
    return _result(await wait_on_child(child_id), wait=True)


async def _conclude_child(child_id: str, keep_branch: bool, ctx: ToolContext) -> ToolResult:
    from hypergolic.dispatch.child_end import end_child
    from hypergolic.dispatch.state import _pending_dispatches
    from hypergolic.sessions.operations import load_session

    try:
        child = await asyncio.to_thread(load_session, child_id)
    except Exception:
        return ToolResult.text(f"no session {child_id!r}", is_error=True)
    if child.parent_id != ctx.session.id:
        return ToolResult.text(f"{child_id} is not a child of yours", is_error=True)
    if child_id in _pending_dispatches:
        return ToolResult.text(
            f"{child_id} is still running; answer its request or wait on it first", is_error=True,
        )
    await end_child(child_id, ctx.broadcast, keep_branch=keep_branch)
    kept = " Its branch survives for diff_child/merge_child." if keep_branch else ""
    return ToolResult.text(f"Concluded {child_id}.{kept}")


def _result(result, wait: bool) -> ToolResult:
    if result.outcome == "awaiting_approval":
        return ToolResult.text(result.conclusion)
    child_id = result.child_session_id
    if result.auto_concluded and result.conducted:
        return ToolResult.text(
            f"Child session {child_id} ended its turn. Its message:\n\n{result.reply_text or ''}\n\n"
            f"Reply as the user with `dispatch --reply {child_id} <text>`, or stop here."
        )
    if result.outcome == "failure" and result.conducted:
        return ToolResult.text(
            f"Dispatch failed: {result.conclusion}\n\n{child_id} is still live. Reply as the user "
            f"(for example `dispatch --reply {child_id} continue`), or end it with `dispatch --conclude {child_id}`.",
            is_error=True,
        )
    if not wait:
        return ToolResult.text(f"Started session {result.child_session_id} on branch {result.worktree_branch}")
    if result.outcome == "success":
        return ToolResult.text(result.conclusion)
    if result.outcome == "failure":
        return ToolResult.text(f"Dispatch failed: {result.conclusion}", is_error=True)
    return ToolResult.text(f"Dispatch was interrupted: {result.conclusion}", is_error=True)


def build_dispatch_tool(
    available_role_ids: Iterable[str],
    receiver_can_read_files: bool = True,
) -> Tool | None:
    """Build a ``dispatch`` command bound to the given role set.

    ``receiver_can_read_files`` is False only when the project has no sandbox,
    in which case attached file references are reported as unreadable rather
    than silently inlined for a receiver that cannot open them.
    """
    role_ids = list(available_role_ids)
    if not role_ids:
        return None

    DispatchRoleEnum = Enum(  # type: ignore[misc]
        "DispatchRoleEnum", {rid: rid for rid in role_ids}, type=str
    )

    class DispatchInput(InputSchema, AppOverrides):
        prompt: str | None = Field(default=None, description="Required unless resuming; with reply, the message to send")
        role: DispatchRoleEnum | None = Field(  # type: ignore[valid-type]
            default=None, description="Defaults to generalist"
        )
        child: bool = Field(
            default=True,
            description="True: child cut from your committed tip, reviewable via diff_child/merge_child. False: standalone top-level session",
        )
        project: str | None = Field(
            default=None, description="Target project id; defaults to yours"
        )
        base: str | None = Field(
            default=None,
            description=(
                "Host branch to cut the session from and land into. Defaults: a child in your "
                "project is cut from your committed tip; any other session from the project's main"
            ),
        )
        wait: bool = Field(
            default=True,
            description="True: block until it concludes and return its conclusion. False: return once it starts",
        )
        pins: dict[str, str] = Field(
            default_factory=dict,
            description="Repo slot -> git ref: app, harness, shared. Roots that slot at the ref instead of its tip",
        )
        model_tier: ModelTier | None = Field(
            default=None, description="Defaults to your tier"
        )
        file_references: list[str] = Field(default_factory=list)
        resume: str | None = Field(
            default=None,
            description="Approval request id a child is waiting on; answer it with outcome, then wait on the child again",
        )
        outcome: ResumeOutcome | None = Field(
            default=None,
            description="With resume: approve, deny, escalate (to the user), or mock (the call does not run; the child gets `result`)",
        )
        message: str = Field(default="", description="With resume: your reason or note to the child")
        conduct: bool = Field(
            default=False,
            description=(
                "Conduct a simulated session: a waiting child without the child rules prompt; "
                "each end of turn returns to you for `reply`, and you answer its gated calls"
            ),
        )
        reply: str | None = Field(
            default=None, description="A conducted child that ended its turn: send `prompt` to it as the user",
        )
        result: str | None = Field(default=None, description="With outcome=mock: the tool result the child gets")
        result_is_error: bool = Field(default=False, description="With outcome=mock: the result is a failure")
        conclude: str | None = Field(
            default=None, description="Conclude this child of yours that is not running (it need not call conclude)",
        )
        keep_branch: bool = Field(
            default=False, description="With conclude: keep the child's branch for diff_child/merge_child",
        )

    async def run_dispatch(inp: DispatchInput, ctx: ToolContext) -> ToolResult:
        from hypergolic.dispatch.runner import dispatch, reply_to_child

        if inp.resume is not None:
            return await _resume(inp, ctx.session.id)
        if inp.conclude is not None:
            return await _conclude_child(inp.conclude, inp.keep_branch, ctx)
        if inp.reply is not None:
            if not inp.prompt:
                return ToolResult.text("reply needs the message text", is_error=True)
            return _result(await reply_to_child(inp.reply, ctx.session.id, inp.prompt), wait=True)
        if inp.conduct and not (inp.child and inp.wait):
            return ToolResult.text("--eval conducts a waiting child; drop --standalone/--no-wait", is_error=True)
        if inp.base and inp.pins.get("app"):
            return ToolResult.text("base and an app pin both set the start commit; give one", is_error=True)
        role_value = inp.role.value if inp.role is not None else "generalist"
        project_id = inp.project or ctx.session.project_id
        try:
            pins = _resolve_pins(inp.pins, project_id)
        except ValueError as exc:
            return ToolResult.text(str(exc), is_error=True)
        prompt = inp.prompt
        if not prompt:
            return ToolResult.text("prompt is required", is_error=True)

        pinned_app = await asyncio.to_thread(snapshot_app_for, pins, ctx.session.id)
        overrides = inp.set_values()
        if overrides:
            pinned_app = overridden_app(pinned_app or get_app(), overrides)
        child_view = _build_child_session_view(ctx.session, role_value)
        content_blocks = _attach_references(prompt, inp.file_references, child_view, receiver_can_read_files)
        if not inp.child or inp.conduct:
            dispatch_prompt = None
        else:
            dispatch_prompt = DISPATCH_PROMPT if inp.wait else ASYNC_DISPATCH_PROMPT

        result = await dispatch(
            parent_session_id=ctx.session.id,
            content_blocks=content_blocks,
            dispatch_prompt=dispatch_prompt,
            broadcast=ctx.broadcast,
            role=role_value,
            model_tier=inp.model_tier,
            child=inp.child,
            project_id=project_id,
            base=inp.base,
            wait=inp.wait,
            repo_pins=pins,
            pinned_app=pinned_app,
            conducted=inp.conduct,
            app_overrides=overrides,
        )
        return _result(result, inp.wait)

    return Tool(
        id="dispatch",
        tags=["subagent", "delegate", "parallel", "worker", "fan-out", "spawn", "session", "pins"],
        name="Dispatch",
        description=(
            "Start a session from a prompt. Default: a generalist child in its own "
            "sandbox on a branch cut from your committed tip (commit first — "
            "uncommitted work does not travel), blocking until it concludes; its "
            "committed work survives for diff_child/merge_child. project runs it in "
            "another project, cut from that project's main; base cuts it from another "
            "host branch, which its lands then target. child=false starts a standalone "
            "session; wait=false returns as soon as it starts. A child can dispatch "
            "too, up to the app's nesting limit (3 sessions deep by default). pins root /app, /harness, /shared at past shas "
            "to test how the harness fares on a historical task. A waiting child "
            "that needs an approval returns the call early; answer with "
            "`dispatch --resume <request> --outcome approve|deny|escalate|mock` "
            "(mock: the call does not run and the child gets --result as its result). "
            "--eval conducts a simulated session: no child rules prompt, and each end "
            "of turn returns to you; answer with `dispatch --reply <child> <text>`. "
            "`dispatch --conclude <child>` ends a child that is not running. "
            "--strip-history-thinking, --truncate-token-threshold, --turn-compaction-floor-tokens "
            "and --shape-grep-output override those App settings for the new session, on top of a harness pin."
        ),
        input_schema=DispatchInput,
        argv=dispatch_argv,
        usage=(
            "dispatch [<role>] <prompt...> [--tier T] [--attach PATH] [--standalone] [--project P] [--base B] "
            "[--no-wait] [--pins JSON] [--eval] [--strip-history-thinking=BOOL] [--truncate-token-threshold=N] "
            "[--turn-compaction-floor-tokens=N] [--shape-grep-output=BOOL] | dispatch --reply <child> <text...> | "
            "dispatch --conclude <child> [--keep-branch] | dispatch --resume <request> --outcome "
            "approve|deny|escalate|mock [--message TEXT] [--result TEXT [--error]]"
        ),
        run=run_dispatch,
        requires_worktree=True,
    )


__all__ = [
    "ASYNC_DISPATCH_PROMPT",
    "DISPATCH_PROMPT",
    "build_dispatch_tool",
]
