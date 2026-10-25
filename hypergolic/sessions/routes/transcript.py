from pathlib import Path

from fastapi import APIRouter

from hypergolic.messages import message_rows
from hypergolic.commands.registry import session_commands
from hypergolic.db.utils import to_iso_utc
from hypergolic.git.commands import unmerged_commit_count
from hypergolic.git.container_git import SandboxRepoUnavailable
from hypergolic.messages.content_blocks import serialize_content_blocks
from hypergolic.sessions.operations import load_session
from hypergolic.sessions.schemas import ConcludePreview, MessageResponse
from hypergolic.tools.cmd import CMD_ID, CMD_NAME

router = APIRouter()


@router.get("/{session_id}/conclude-preview", response_model=ConcludePreview)
def get_conclude_preview(session_id: str):
    session = load_session(session_id)
    assert session.worktree_path, f"Session {session_id} has no worktree_path"
    wt = Path(session.worktree_path)
    if not wt.exists() or not session.worktree_branch:
        return ConcludePreview(is_worktree_session=True)

    try:
        unmerged = unmerged_commit_count(wt, session.base_branch, session.worktree_branch)
    except SandboxRepoUnavailable:
        return ConcludePreview(is_worktree_session=True)

    return ConcludePreview(
        is_worktree_session=True,
        branch_has_unmerged_commits=unmerged > 0,
        unmerged_count=unmerged,
    )


def _build_tool_display_names(session_id: str) -> dict[str, str]:
    try:
        session = load_session(session_id)
        names = {CMD_ID: CMD_NAME}
        names.update({name: command.name for name, command in session_commands(session).items()})
        return names
    except Exception:
        return {}


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
def get_session_messages(session_id: str):
    tool_display_names = _build_tool_display_names(session_id)
    return [
        MessageResponse(
            id=r.id,
            session_id=r.session_id,
            role=r.role,
            content=serialize_content_blocks(r.content, tool_display_names),
            model=r.model,
            stop_reason=r.stop_reason,
            usage=r.usage,
            truncated=r.truncated,
            created_at=to_iso_utc(r.created_at),
        )
        for r in message_rows.for_session(session_id)
    ]
