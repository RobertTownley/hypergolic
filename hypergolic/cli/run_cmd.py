"""`hypergolic run` — drive one headless session turn from the shell.

Loads the harness fresh in this process (picking up uncommitted main.py /
prompt / tool edits), creates a normal session with worktree + sandbox, runs a
single turn with approvals auto-denied, and prints the final assistant
content. `--no-conclude` keeps the worktree and container alive so follow-up
runs (`--session CX...`) can iterate; the default tears both down.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer
from anthropic.types import Message, MessageParam

from hypergolic.cli.broker_server import start_broker
from hypergolic.cli.harness_loader import HarnessLoadError, load_harness_app, prepare_app
from hypergolic.cli.setup import run_migrations
from hypergolic.config.settings import settings
from hypergolic.db import container as db_container
from hypergolic.system.docker import ContainerError
from hypergolic.dispatch.conclude import set_concluded_at
from hypergolic.dispatch.state import register_turn_runner
from hypergolic.enums import ModelTier, SessionStatus
from hypergolic.git.commands import run_git_command
from hypergolic.git.sandbox_repo import delete_hypergolic_ref
from hypergolic.git.worktree_lifecycle import run_teardown, wait_for_ready
from hypergolic.logging import setup_logging
from hypergolic.mcptools.client.manager import get_mcp_manager
from hypergolic.sandbox.manager.lifecycle import cleanup_session_sandboxes
from hypergolic.schemas import Session
from hypergolic.sessions.operations import (
    clear_session_worktree_fields,
    create_session,
    load_session,
)
from hypergolic.sessions.status import set_session_status
from hypergolic.sessions.turn import run_session_turn
from hypergolic.tools.approval import ApprovalResponse

_TIER_ALIASES = {t.name: t for t in ModelTier} | {t.value.upper(): t for t in ModelTier}


def _parse_tier(raw: str) -> ModelTier:
    key = raw.strip().upper().replace("-", "_").replace(" ", "_")
    try:
        return _TIER_ALIASES[key]
    except KeyError:
        raise typer.BadParameter(
            f"Unknown model tier {raw!r}; expected one of {', '.join(t.name for t in ModelTier)}"
        )


def _build_user_message(message: str | None, content_json: str | None) -> MessageParam:
    if bool(message) == bool(content_json):
        raise typer.BadParameter("Provide exactly one of --message or --content-json")
    if message:
        return {"role": "user", "content": [{"type": "text", "text": message}]}
    try:
        blocks = json.loads(content_json or "")
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"--content-json is not valid JSON: {exc}")
    if not isinstance(blocks, list):
        raise typer.BadParameter("--content-json must be a JSON list of content blocks")
    return {"role": "user", "content": blocks}


def _resolve_project(app: Any, ref: str) -> Any:
    project = app.find_project(ref) or next(
        (p for p in app.projects if p.name == ref), None
    )
    if project is None:
        known = ", ".join(p.id for p in app.projects)
        raise typer.BadParameter(f"Unknown project {ref!r}; registered: {known}")
    return project


def _default_base_branch(git_root: str) -> str:
    result = run_git_command("rev-parse", "--abbrev-ref", "HEAD", cwd=Path(git_root))
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch:
        raise typer.BadParameter(
            f"Could not determine current branch of {git_root}; pass --base-branch"
        )
    return branch


async def _deny_approval(req: Any) -> Any:
    # Defense in depth: origin='cli' already denies at the decision layer.

    return ApprovalResponse(
        approved=False,
        denial_reason="Headless `hypergolic run` session: approvals are auto-denied.",
    )


async def _conclude_session(session: Session) -> None:
    await asyncio.to_thread(set_session_status, session.id, SessionStatus.CONCLUDED)
    await asyncio.to_thread(set_concluded_at, session.id)
    await asyncio.to_thread(
        clear_session_worktree_fields, session.id, clear_branch=True
    )
    assert session.worktree_branch  # set at create_session, immutable after
    await asyncio.to_thread(
        delete_hypergolic_ref,
        session.project_path, session.project_id, session.worktree_branch,
    )
    # Synchronous (not schedule_teardown): this process exits right after, so
    # a daemon thread would be killed mid-removal.
    await asyncio.to_thread(run_teardown, worktree_path=session.worktree_path)
    await cleanup_session_sandboxes(session.id)


def _register_cli_turn_runner() -> None:
    """Let dispatch children run their turns in this process: same
    deny-approvals posture as the parent, output discarded (children report
    back through their dispatch future, not stdout)."""
    tasks: set[asyncio.Task] = set()

    async def _drop(payload: Any) -> None:
        pass

    def start_turn(session_id: str, message: MessageParam | None) -> None:
        async def _coro() -> None:
            await run_session_turn(
                session_id, message, asyncio.Event(),
                _drop, _drop, _deny_approval,
            )
        task = asyncio.get_running_loop().create_task(_coro())
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    register_turn_runner(start_turn)


async def _run_turn(
    make_session: Any,
    user_message: MessageParam,
    conclude: bool,
) -> tuple[Session, Message | None, list[dict[str, Any]]]:
    payloads: list[dict[str, Any]] = []

    async def notify(payload: dict[str, Any]) -> None:
        payloads.append(payload)

    async def broadcast(event: Any) -> None:
        pass

    _register_cli_turn_runner()

    # Shims in the sandbox authenticate with tokens minted in this process, so
    # the broker they dial must live here too — not on the default server port.
    # Started before the session exists: container env captures the port.
    broker = await start_broker()

    try:
        # Sessions are created inside the running loop so the worktree ready-
        # event registers against it (wait_for_ready wakes via
        # call_soon_threadsafe).
        session: Session = await asyncio.to_thread(make_session)
        try:
            await wait_for_ready(session.id)
            response = await run_session_turn(
                session.id, user_message, asyncio.Event(),
                notify, broadcast, _deny_approval,
            )
        finally:
            if conclude:
                await _conclude_session(session)
            await get_mcp_manager().shutdown()
    finally:
        await broker.stop()
    return session, response, payloads


def _emit(
    session_id: str,
    response: Message | None,
    payloads: list[dict[str, Any]],
    json_output: bool,
) -> None:
    failure = next(
        (p for p in payloads if p.get("type") in ("error", "interrupted")), None
    )
    content = (
        [b.model_dump(mode="json") for b in response.content] if response else None
    )
    if json_output:
        out: dict[str, Any] = {
            "session_id": session_id,
            "outcome": failure["type"] if failure else "done",
            "content": content,
        }
        if response:
            out["stop_reason"] = response.stop_reason
        if failure and failure.get("detail"):
            out["detail"] = failure["detail"]
        typer.echo(json.dumps(out, indent=2))
    else:
        typer.echo(f"Session ({session_id})")
        if failure:
            typer.echo(f"{failure['type']}: {failure.get('detail', '')}")
        if content is not None:
            typer.echo("Final content:")
            typer.echo(json.dumps(content, indent=2))
    if failure:
        raise typer.Exit(1)


def run(
    project: str | None = typer.Option(None, "--project", "-p", help="Project id or name (new sessions)."),
    message: str | None = typer.Option(None, "--message", "-m", help="User message text."),
    content_json: str | None = typer.Option(None, help="JSON content-block list for the user message."),
    session: str | None = typer.Option(None, "--session", "-s", help="Continue an open `hypergolic run` session."),
    model_tier: str = typer.Option("HIGH", "--model-tier", "-t", help="LOW, MEDIUM, HIGH, or EXTRA_HIGH."),
    base_branch: str | None = typer.Option(None, help="Branch the worktree is based on (default: project HEAD)."),
    conclude: bool = typer.Option(True, help="Tear down worktree + sandbox after the turn. --no-conclude keeps them for follow-up runs."),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Run one headless agent turn against the current harness config."""
    user_message = _build_user_message(message, content_json)
    tier = _parse_tier(model_tier)

    setup_logging()
    try:
        app = load_harness_app()
        prepare_app(app)
    except HarnessLoadError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2)
    if "HYPERGOLIC_DATABASE_URL" not in settings.model_fields_set:
        if not db_container.docker_running():
            typer.echo("Docker is not running; start it and retry.", err=True)
            raise typer.Exit(2)
        try:
            db_container.ensure_postgres()
        except ContainerError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2)
    run_migrations()

    if session:
        existing = load_session(session)
        if existing.origin != "cli":
            typer.echo(f"Session {session} was not started by `hypergolic run`; refusing to drive it.", err=True)
            raise typer.Exit(2)
        make_session = lambda: existing  # noqa: E731
    else:
        if not project:
            raise typer.BadParameter("--project is required for a new session")
        project_obj = _resolve_project(app, project)
        resolved_base = base_branch or _default_base_branch(project_obj.git_root)
        make_session = lambda: create_session(  # noqa: E731
            project_id=project_obj.id,
            base_branch=resolved_base,
            model_tier=tier,
            origin="cli",
        )

    try:
        session_obj, response, payloads = asyncio.run(
            _run_turn(make_session, user_message, conclude)
        )
    except Exception as exc:  # e.g. worktree creation failed
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    _emit(session_obj.id, response, payloads, json_output)
