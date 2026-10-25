"""Canonical factory helpers for tests.

Use these instead of redefining per-file `_skill`, `_session`, `_workflow`,
etc. helpers. All factories have permissive defaults so call sites only
specify the fields that matter for the test.

Naming convention:
    * `build_*` — returns an in-memory object (no DB write).
    * `make_*` (in tests/conftest.py) — writes a row to the DB.

`build_session` is distinct from `make_session` (conftest) because many
tests need a `Session` domain object that matches (or doesn't match) a
separately-seeded DB row.
"""
from __future__ import annotations

from typing import Any, cast

from anthropic.types import Message, TextBlock, Usage

from hypergolic.enums import ModelTier
from hypergolic.schemas import Session, WorktreeStatus
from hypergolic.harness.primitives import (
    OutputSchema,
    Skill,
    Workflow,
    WorkflowState,
)


def build_app(*, project_id: str = "p-1", set_active: bool = True):
    """Construct an :class:`App` with a default project registered.

    ``build_session`` defaults to ``project_id="p-1"`` and ``get_project`` now
    raises on an unknown id, so any test that builds a session needs its
    project registered. This pairs the two so tests don't re-declare the
    project by hand. Pass ``set_active=False`` to skip ``set_app``.
    """
    from hypergolic.harness.app.core import App
    from hypergolic.harness.app.state import set_app
    from hypergolic.harness.project import Project

    app = App()
    app.register_project(
        Project(id=project_id, name="Test Project", description="d", git_root="/tmp/p")
    )
    if set_active:
        set_app(app)
    return app


def build_skill(
    sid: str,
    *,
    name: str | None = None,
    description: str | None = None,
    prompt: str | None = None,
    prompt_path: str | None = None,
    children: list[Skill] | None = None,
    tools: list | None = None,
) -> Skill:
    """Construct a Skill with sensible defaults."""
    return Skill(
        id=sid,
        name=name or sid,
        description=description or f"Description for {sid}",
        prompt=prompt,
        prompt_path=prompt_path,
        skills=children or [],
        tools=tools or [],
    )


def build_session(
    sid: str = "s-1",
    *,
    project_id: str = "p-1",
    project_path: str = "/tmp/p",
    role: str = "generalist",
    model_tier: ModelTier = ModelTier.MEDIUM,
    parent_id: str | None = None,
    dispatch_prompt: str | None = None,
    origin: str | None = None,
    worktree_path: str | None = None,
    worktree_branch: str | None = None,
    base_branch: str = "main",
    worktree_status: WorktreeStatus = "ready",
) -> Session:
    """Construct a Session domain object (does not touch the DB).

    Covers every field test call sites need, so per-file
    ``_session`` / ``_worktree_session`` helpers can be deleted in favour of
    this one.
    """
    return Session(
        id=sid,
        model_tier=model_tier,
        project_id=project_id,
        project_path=project_path,
        role=role,
        parent_id=parent_id,
        dispatch_prompt=dispatch_prompt,
        origin=origin,
        worktree_path=worktree_path or f"/tmp/hg-test-wt/{sid}",
        worktree_branch=worktree_branch or f"{base_branch}-{sid}",
        base_branch=base_branch,
        worktree_status=worktree_status,
    )


def build_output_schema(
    outcome: str = "done",
    *,
    next_state: str | None = None,
    artifact_id: str | None = None,
) -> OutputSchema:
    return OutputSchema(
        outcome=outcome,
        next_state=next_state,
        artifact_id=artifact_id,
        schema={"type": "object", "properties": {}},
    )


def build_workflow_state(
    sid: str = "st-1",
    *,
    name: str | None = None,
    prompt: str | None = "prompt",
    prompt_path: str | None = None,
    skills: list[Skill] | None = None,
    output_schemas: list[OutputSchema] | None = None,
    truncate_on_entry: bool = False,
    include_artifacts: list[str] | None = None,
) -> WorkflowState:
    return WorkflowState(
        id=sid,
        name=name or sid,
        prompt=prompt if prompt_path is None else None,
        prompt_path=prompt_path,
        skills=skills or [],
        output_schemas=output_schemas or [],
        truncate_on_entry=truncate_on_entry,
        include_artifacts=include_artifacts or [],
    )


def build_workflow(
    wf_id: str = "wf-1",
    *,
    name: str | None = None,
    description: str = "A test workflow",
    state_id: str = "st-1",
    next_state_id: str | None = None,
    outcome: str = "done",
    artifact_id: str | None = None,
    wf_skills: list[Skill] | None = None,
    state_skills: list[Skill] | None = None,
    truncate_on_entry: bool = False,
    include_artifacts: list[str] | None = None,
    states: list[WorkflowState] | None = None,
) -> Workflow:
    """Construct a Workflow.

    The default shape is a two-state workflow when `next_state_id` is given,
    otherwise a single-state workflow. Pass `states=[...]` to fully override
    the state list.
    """
    if states is None:
        output_schemas = [
            build_output_schema(outcome, next_state=next_state_id, artifact_id=artifact_id)
        ]
        first = build_workflow_state(
            state_id,
            name="State One",
            skills=state_skills,
            output_schemas=output_schemas,
        )
        states = [first]
        if next_state_id:
            states.append(
                build_workflow_state(
                    next_state_id,
                    name="State Two",
                    truncate_on_entry=truncate_on_entry,
                    include_artifacts=include_artifacts,
                )
            )
    return Workflow(
        id=wf_id,
        name=name or f"Workflow {wf_id}",
        description=description,
        initial_state=state_id,
        states=states,
        skills=wf_skills or [],
    )


def build_assistant_message(
    stop_reason: Any = "end_turn",
    *,
    mid: str = "msg-1",
    content: list[Any] | None = None,
    text: str = "hello",
    model: str = "claude-sonnet-4-20250514",
    input_tokens: int = 10,
    output_tokens: int = 20,
) -> Message:
    """Construct an assistant Anthropic Message.

    ``content`` (a list of blocks) overrides ``text``, which otherwise becomes
    a single TextBlock. Replaces the per-file ``_make_response`` /
    ``_final_message`` / inline ``Message(...)`` copies.
    """
    if content is None:
        content = [TextBlock(type="text", text=text)]
    return Message(
        id=mid,
        content=cast(Any, content),
        model=model,
        role="assistant",
        stop_reason=stop_reason,
        stop_sequence=None,
        type="message",
        usage=Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )


def commands_for(session, **patches):
    """The session's command set with the DB-backed lookups stubbed out.

    ``session_commands`` reaches for the active workflow and the enabled MCP
    servers; neither is what a command-set test is about, so both are stubbed
    unless a caller overrides them.
    """
    import contextlib
    from unittest.mock import patch

    from hypergolic.commands.registry import session_commands

    targets = {
        "hypergolic.workflows.resolver.get_session_workflow": None,
        "hypergolic.mcptools.sessions.get_enabled_servers": set(),
    }
    targets.update(patches)
    with contextlib.ExitStack() as stack:
        for target, value in targets.items():
            stack.enter_context(patch(target, return_value=value))
        return session_commands(session)


def policy(approval: Any):
    """Coerce the string shorthand harness configs use into an approval policy."""
    from hypergolic.harness.primitives import always

    return always(approval) if isinstance(approval, str) else approval


def approval_of(command, inp: Any = None, session: Session | None = None) -> str:
    """The decision a command's approval policy returns for ``inp``."""
    from hypergolic.harness.primitives import ApprovalContext

    ctx = ApprovalContext(input=inp, session=session or build_session())
    return command.approval_policy(ctx).decision


async def invoke(command, *args: Any):
    """Run a command's handler, failing the test if it has none.

    Variadic because handlers come in both shapes the bridge tolerates:
    ``(input, ctx)`` and ``(ctx)``.
    """
    assert command.run is not None, f"command '{command.id}' has no run"
    return await command.run(*args)
