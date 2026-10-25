"""Shared path-resolution and boundary-check helpers for tool approval functions.

The only remaining consumer is ``decide_read``, used by the dispatch tool to
decide whether it may inline a referenced file when handing it to a child
session. Writes are no longer gated here: the agent edits files through the
sandbox ``cmd`` tool (scoped to the worktree mount) or the always-approved
``host_cmd`` tool, so path-level write approval is handled structurally rather
than by this module.

## Scope

Every session has a worktree; the worktree directory is the session's scope.

Out-of-scope read behavior depends on whether the session is **dispatched**
(has a ``parent_id`` — a subagent with no live user) or **top-level**:

- Dispatched worktree, out-of-scope path: DENY (no user to prompt, and falling
  back to approval would subvert subagent isolation).
- Top-level session, out-of-scope path: REQUIRE_APPROVAL.
"""

from pathlib import Path

from hypergolic.contrib.tools.approvals.constants import READONLY_ALLOWLIST
from hypergolic.harness.primitives.approval import ToolApprovalDecision
from hypergolic.schemas import Session
from hypergolic.tools.paths import resolve_path

ALLOW = ToolApprovalDecision(decision="ALLOW")
REQUIRE_APPROVAL = ToolApprovalDecision(decision="REQUIRE_APPROVAL")


def _worktree_deny(verb: str) -> ToolApprovalDecision:
    """A DENY decision with a message explaining the worktree sandbox."""
    return ToolApprovalDecision(
        decision="DENY",
        reason=(
            f"Worktree sessions can only {verb} paths inside their own "
            "worktree directory. If you need something outside, ask your "
            "parent session via `conclude` instead of attempting it here."
        ),
    )


def _resolved_allowlist(session: Session) -> list[Path]:
    return [resolve_path(p, session) for p in READONLY_ALLOWLIST]


def _worktree_dir(session: Session) -> Path:
    return Path(session.worktree_path).expanduser().resolve()


def _is_within(path: Path, parent: Path) -> bool:
    """Return True if *path* is equal to or nested inside *parent*."""
    try:
        return path == parent or path.is_relative_to(parent)
    except (ValueError, TypeError):
        return False


def in_project_or_readonly_allowlist(
    raw_path: str,
    session: Session,
) -> bool:
    """True if *raw_path* is inside the worktree or on the readonly allowlist."""
    resolved = resolve_path(raw_path, session)
    if _is_within(resolved, _worktree_dir(session)):
        return True
    for allowed in _resolved_allowlist(session):
        if _is_within(resolved, allowed):
            return True
    return False


def decide_read(
    raw_paths: list[str],
    session: Session,
) -> ToolApprovalDecision:
    """Approval decision for reading files.

    - All paths inside scope or on the readonly allowlist: ALLOW.
    - Dispatched session with any out-of-scope path: DENY with message
      (no user to approve).
    - Otherwise, any out-of-scope path: REQUIRE_APPROVAL.
    """
    dispatched = session.parent_id is not None
    for p in raw_paths:
        if not in_project_or_readonly_allowlist(p, session):
            if dispatched:
                return _worktree_deny("read")
            return REQUIRE_APPROVAL
    return ALLOW
