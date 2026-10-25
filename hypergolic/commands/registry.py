"""The command set a session can invoke.

Capability is *pulled* from the filesystem rather than pushed as tool schemas, so
this registry has one job: enumerate every command the session could reach, so it
can be materialized into ``/tools`` and summarized in the system prompt. Nothing
here mutates mid-turn — that is the whole point. Commands from skills the session
has not "activated" are included too: activation existed only to keep a tool list
small, and there is no tool list any more.

One thing is deliberately *not* a command: the sandbox shell. It is the single
tool that ships over the wire, so a shim for it would recurse into the exec it
came from. :func:`sandbox_shell` resolves it for that path instead.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App

from hypergolic.commands.argv import parser_for, usage_for
from hypergolic.config.settings import settings
from hypergolic.harness.primitives.bundles import Skill
from hypergolic.harness.primitives.tool import Tool
from hypergolic.harness.project import Project
from hypergolic.schemas import Session
from hypergolic.harness.primitives.bundles import resolve_prompt
from hypergolic.harness.app.lookup import (
    find_scoped_workflow,
    scoped_workflows,
    unique_workflows,
)
from hypergolic.harness.app.state import get_app
from hypergolic.commands.docs import index_line
from hypergolic.workflows.resolver import get_session_workflow
from hypergolic.contrib.tools.command import dangerous_command_tool
from hypergolic.contrib.tools.dispatch import build_dispatch_tool
from hypergolic.tools.activate_workflow import build_activate_workflow_command
from hypergolic.contrib.tools.diff_child import build_diff_child_tool
from hypergolic.contrib.tools.land import LandTool
from hypergolic.contrib.tools.merge_child import build_merge_child_tool
from hypergolic.dispatch.conclude import ConcludeTool
from hypergolic.mcptools.sessions import get_enabled_servers
from hypergolic.workflows.tools import build_transition_tools

logger = logging.getLogger(__name__)

#: The sandbox shell: the `cmd` tool itself, not a command inside it.
SHELL_COMMAND_ID = "cmd"


def _resolved(command: Tool, origin: str) -> Tool:
    """Fill in what a declaration may leave to the registry.

    A command that doesn't declare an argv parser or a usage line gets one
    inferred from its input schema, so the shim, the README, and the broker all
    read the same contract without every author having to spell it out.
    """
    update: dict[str, Any] = {}
    if command.origin != origin:
        update["origin"] = origin
    if not command.usage:
        update["usage"] = usage_for(command.id, command.input_schema)
    if command.parse is None and command.input_schema is not None:
        update["parse"] = parser_for(command.argv, command.input_schema)
    return command.model_copy(update=update) if update else command


def skill_guidance(skill: Skill) -> str:
    try:
        return resolve_prompt(skill, get_app()) or ""
    except Exception:
        logger.warning("Could not resolve prompt for skill '%s'", skill.id, exc_info=True)
        return ""


def skill_activation_text(skill: Skill, guidance: str | None = None) -> str:
    """What activating a skill delivers: its prompt plus an explicit index of
    the commands and subskills it brings, so depth is one `activate_skill` away.

    Nothing is hidden until activation — every command is already on PATH and
    in `apropos` — this is where they get *named* so the agent knows to look.
    """

    parts = [guidance if guidance is not None else skill_guidance(skill)]
    if skill.tools:
        lines = "\n".join(f"- {index_line(_resolved(t, f'skill:{skill.id}'))}" for t in skill.tools)
        parts.append(f"## Commands this skill provides\n{lines}")
    if skill.skills:
        subs = "\n".join(f"- {s.id} \u2014 {s.description}" for s in skill.skills)
        parts.append(f"## Subskills \u2014 `activate_skill <id>` for depth\n{subs}")
    return "\n\n".join(p for p in parts if p)


def advisory_command(skill: Skill, origin: str, guidance: str | None = None) -> Tool:
    """A skill that ships guidance but nothing to invoke.

    Presence of ``bin/<name>`` is what distinguishes invocable from advisory, so
    a prompt-only skill needs no separate mechanism: it materializes as a
    directory holding a README and no shim.
    """
    return Tool(
        id=skill.id,
        name=skill.name,
        description=skill.description or skill.name,
        tags=skill.tags,
        guidance=skill_activation_text(skill, guidance),
        origin=origin,
        run=None,
    )


def resolvable_skills(session: Session) -> list[tuple[Skill, str]]:
    """Every skill the session could reach, active or not, flattened.

    Scoped deliberately: app-level skills, then this session's project, role, and
    active workflow. A skill another role declares is not reachable here, which
    is what keeps a child role from inheriting the generalist's integration
    commands.
    """

    app = get_app()
    out: list[tuple[Skill, str]] = []
    seen: set[str] = set()

    def add(skill: Skill, origin: str) -> None:
        if skill.id in seen:
            return
        seen.add(skill.id)
        out.append((skill, origin))
        for child in skill.skills:
            add(child, f"skill:{skill.id}")

    for skill in app.skills:
        add(skill, "app")
    project = app.find_project(session.project_id)
    if project:
        for skill in project.skills:
            add(skill, f"project:{project.id}")
    role = app.get_role(session.role)
    if role:
        for skill in role.skills:
            add(skill, f"role:{role.id}")
    wf_state = get_session_workflow(session.id)
    if wf_state:
        workflow_id, current_state_id = wf_state
        workflow = find_scoped_workflow(
            app, project, app.get_role(session.role), workflow_id,
        )
        if workflow:
            for skill in workflow.skills:
                add(skill, f"workflow:{workflow_id}")
            for state in workflow.states:
                if state.id == current_state_id:
                    for skill in state.skills:
                        add(skill, f"workflow_state:{state.id}")
    return out


def sandbox_shell(session: Session) -> Tool | None:
    """What the wire `cmd` tool actually executes.

    - A project with an explicit :class:`ProjectSandbox` registered its own
      ``cmd`` via ``configure_sandbox``; that one wins.
    - An unconfigured project resolves to the egress-denied default sandbox.
    - A project that opted out (``configure_sandbox(None)``) has no shell, and
      neither does a session running under
      ``HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE``, where there is no sandbox at all
      and the host shell takes the ``cmd`` id instead.
    """

    if settings.HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE:
        return None if _commands_disabled() else dangerous_command_tool

    project = get_app().find_project(session.project_id)
    if project is None:
        return None
    declared = next((t for t in project.tools if t.id == SHELL_COMMAND_ID), None)
    if declared is not None:
        return declared
    # Built and memoized on the Project, so this is allocation-free after the
    # first turn and never touches disk on the per-turn build path.
    return project.default_cmd_tool()


def _commands_disabled() -> bool:
    return bool(os.environ.get("HYPERGOLIC_DISABLE_COMMANDS"))


def dispatch_depth(session: Session) -> int:
    """1 for a top-level session, 2 for its child, and so on up the parent chain."""
    from hypergolic.sessions.operations import load_session  # cycle

    depth, parent_id, seen = 1, session.parent_id, {session.id}
    while parent_id is not None and parent_id not in seen:
        seen.add(parent_id)
        depth += 1
        try:
            parent_id = load_session(parent_id).parent_id
        except Exception:
            break
    return depth


def _dispatch_command(app: App, session: Session) -> Tool | None:
    """The ``dispatch`` command, if *session* can dispatch.

    Targets come from the role's ``dispatch_targets``. A session at
    ``app.max_dispatch_depth`` (the top-level session is depth 1) gets no
    dispatch, so a chain of generalists cannot recurse without end.
    """

    role = app.get_role(session.role)
    if role is None or not role.dispatch_targets:
        return None
    if dispatch_depth(session) >= app.max_dispatch_depth:
        return None
    target_role_ids = [r.id for r in app.roles if r.id in set(role.dispatch_targets)]
    # Children run in the parent's project, so they reach the same shell — which
    # is the only capability an attached file reference needs.
    return build_dispatch_tool(target_role_ids, sandbox_shell(session) is not None)


def _activate_workflow_command(
    app: App, project: Project | None, session: Session
) -> Tool | None:
    if get_session_workflow(session.id) is not None:
        return None
    wf_ids = [wf.id for wf in unique_workflows(
        scoped_workflows(app, project, app.get_role(session.role)),
    )]
    return build_activate_workflow_command(wf_ids) if wf_ids else None


def _add(commands: dict[str, Tool], command: Tool | None, origin: str) -> None:
    if command is None:
        return
    existing = commands.get(command.id)
    if existing is not None and existing.origin != origin and existing.run is not command.run:
        # `/tools/bin` is a flat namespace, so the loser here simply vanishes
        # from the agent's PATH. Silence would look like missing capability.
        logger.warning(
            "Tool '%s' is declared by both '%s' and '%s'; '%s' wins",
            command.id, existing.origin, origin, origin,
        )
    commands[command.id] = _resolved(command, origin)


def _add_if_new(commands: dict[str, Tool], command: Tool, origin: str) -> None:
    if command.id not in commands:
        _add(commands, command, origin)


def _add_skill_commands(commands: dict[str, Tool], session: Session) -> None:
    for skill, origin in resolvable_skills(session):
        for command in skill.tools:
            _add(commands, command, f"skill:{skill.id}")
        # A skill's prompt has to land somewhere readable. Usually that is a
        # docs-only directory under the skill's own id; when the skill names its
        # tool after itself (`git` the skill, `git` the command) the prompt is
        # appended to that command's README, never replacing what it documents.
        guidance = skill_guidance(skill)
        collision = commands.get(skill.id)
        if collision is None:
            if guidance or not skill.tools:
                commands[skill.id] = advisory_command(skill, origin, guidance)
        elif guidance and guidance not in collision.guidance:
            merged = f"{collision.guidance}\n\n{guidance}" if collision.guidance else guidance
            commands[skill.id] = collision.model_copy(update={"guidance": merged})


def _add_workflow_commands(
    commands: dict[str, Tool], app, project, session: Session
) -> None:
    wf_state = get_session_workflow(session.id)
    if not wf_state:
        return
    workflow_id, current_state_id = wf_state
    wf = find_scoped_workflow(app, project, app.get_role(session.role), workflow_id)
    if not wf:
        return
    for command in wf.tools:
        _add(commands, command, f"workflow:{workflow_id}")
    for state in wf.states:
        if state.id == current_state_id:
            for command in state.tools:
                _add(commands, command, f"workflow_state:{current_state_id}")


def _add_declared_commands(
    commands: dict[str, Tool], app, project, role, session: Session
) -> None:
    for command in app.tools:
        _add(commands, command, "app")
    if project:
        for command in project.tools:
            _add(commands, command, "project")
    if role:
        for command in role.tools:
            _add(commands, command, "role")
    _add_skill_commands(commands, session)
    _add_workflow_commands(commands, app, project, session)


def _add_builtin_commands(
    commands: dict[str, Tool], app, project, role, session: Session
) -> None:
    from hypergolic.mcptools.tool_bridge import get_mcp_tools_for_session

    _add(commands, _activate_workflow_command(app, project, session), "app")
    _add(commands, _dispatch_command(app, session), "role")
    if role and role.dispatch_targets:
        _add(commands, build_merge_child_tool(session), "app")
        _add(commands, build_diff_child_tool(session), "app")
    enabled_servers = get_enabled_servers(session.id)
    if enabled_servers:
        for command in get_mcp_tools_for_session(enabled_servers):
            _add(commands, command, command.origin)


def _add_fallback_commands(commands: dict[str, Tool], session: Session) -> None:
    transition_commands, transition_state_id = build_transition_tools(session)
    transition_origin = (
        f"workflow_state:{transition_state_id}" if transition_state_id else "app"
    )
    for command in transition_commands:
        _add_if_new(commands, command, transition_origin)
    if session.parent_id:
        _add_if_new(commands, ConcludeTool, "app")
    # The landing broker behind `git push origin HEAD:<branch>`; every session's
    # quarantine hooks call it, so it must resolve for every session.
    _add_if_new(commands, LandTool, "app")


def session_commands(session: Session) -> dict[str, Tool]:
    """Every command the session can reach, keyed by the name the agent types.

    Ordering is deliberate: later sources overwrite earlier ones, so a role can
    replace an app-level command of the same name.
    """

    app = get_app()
    project = app.find_project(session.project_id)
    role = app.get_role(session.role)
    if role is None:
        logger.warning("Session '%s' names unknown role '%s'", session.id, session.role)

    commands: dict[str, Tool] = {}
    _add_declared_commands(commands, app, project, role, session)
    _add_builtin_commands(commands, app, project, role, session)
    _add_fallback_commands(commands, session)

    if settings.HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE or _commands_disabled():
        commands.pop("host_cmd", None)

    # The shell is the wire tool, not a command reachable from inside itself.
    commands.pop(SHELL_COMMAND_ID, None)
    return commands


def shell_capable_containers(session: Session) -> list[str]:
    """Containers the session's `cmd` may target, in declaration order."""

    app = get_app()
    project = app.find_project(session.project_id)
    sandbox = project.resolved_sandbox if project else None
    if sandbox is None:
        return []
    return list(sandbox.container_ids)
