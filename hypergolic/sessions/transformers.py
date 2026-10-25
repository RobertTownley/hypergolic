"""Pure helpers for building session API responses.

These are extracted from the router so they can be unit-tested without
HTTP or database fixtures.
"""

import json

from hypergolic.db.models import DBSession
from hypergolic.db.utils import to_iso_utc
from hypergolic.sessions.schemas import (
    SessionResponse,
    SkillInfo,
    ToolInfo,
)
from hypergolic.harness.primitives.tool import Tool
from hypergolic.schemas import Session
from hypergolic.tools.wire import wire_schema
from hypergolic.commands.docs import resolved_decision
from hypergolic.commands.registry import session_commands
from hypergolic.tools.cmd import build_cmd_tool


def session_response(
    row: DBSession,
    project_name: str,
    message_count: int = 0,
    workflow_id: str | None = None,
    workflow_state_id: str | None = None,
    workflow_name: str | None = None,
    workflow_state_name: str | None = None,
) -> SessionResponse:
    """Map a DBSession row to a SessionResponse."""
    return SessionResponse(
        id=row.id,
        model_tier=row.model_tier,
        project_id=row.project_id,
        project_name=project_name,
        role=row.role,
        status=row.status,
        created_at=to_iso_utc(row.created_at),
        updated_at=to_iso_utc(row.updated_at),
        message_count=message_count,
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        workflow_state_id=workflow_state_id,
        workflow_state_name=workflow_state_name,
        parent_id=row.parent_id,
        description=row.description,
        conclusion_rating=row.conclusion_rating,
        conclusion_feedback=row.conclusion_feedback,
        concluded_at=to_iso_utc(row.concluded_at) if row.concluded_at else None,
        worktree_path=row.worktree_path,
        worktree_branch=row.worktree_branch,
        base_branch=row.base_branch,
        worktree_status=row.worktree_status,
    )


def build_tool_info(tool: Tool, reason: str) -> ToolInfo:
    """The one wire tool, priced at what its schema actually costs."""

    schema = None
    token_estimate = 0
    try:
        param = wire_schema(tool)
        raw = param.get("input_schema")
        schema = dict(raw) if raw else None
        token_estimate = len(json.dumps(param)) // 4
    except Exception:
        pass
    return ToolInfo(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        reason=reason,
        requires_approval=_gated(tool),
        token_estimate=token_estimate,
        input_schema=schema,
    )


def _gated(command: Tool) -> bool:
    """Whether invoking the command may block on a human.

    Fail closed: a policy that classifies per argument has no session-wide
    posture, and reporting it as auto-approved would understate what an MCP
    write or a shell command can ask for.
    """

    decision = resolved_decision(command)
    return decision is None or decision.decision != "ALLOW"


def _mcp_server(command: Tool) -> str | None:
    if not command.origin.startswith("mcp:"):
        return None
    return command.origin.removeprefix("mcp:")


def command_tool_infos(session: Session) -> list[ToolInfo]:
    """What the session reports to the UI: the wire tool, then every command.

    Commands aren't tools on the wire — each is a file in ``/tools`` the agent
    discovers on ``PATH`` — so they are priced at zero. The only per-turn cost is
    one line of relevance index per command in the system prompt.
    """

    infos = [build_tool_info(build_cmd_tool(session), "app")]
    commands = session_commands(session)
    for name in sorted(commands):
        command = commands[name]
        infos.append(
            ToolInfo(
                id=name,
                name=command.name,
                description=command.description,
                reason=command.origin,
                requires_approval=_gated(command),
                token_estimate=0,
                mcp_server=_mcp_server(command),
                usage=command.usage or f"(docs only) cat /tools/{name}/README.md",
            )
        )
    return infos


def build_skill_infos(all_skills: list[dict]) -> list[SkillInfo]:
    """Build SkillInfo list from resolved skills."""
    return [
        SkillInfo(
            id=s["id"],
            name=s["name"],
            description=s["description"],
            source=s["source"],
        )
        for s in all_skills
    ]
