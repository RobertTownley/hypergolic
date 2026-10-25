import contextlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from hypergolic.harness.primitives.tool import ToolContext
from hypergolic.sessions import session_rows
from tests._factories import build_session
from tests.conftest import make_project, make_session as insert_session


def seed(sid="s1", parent_id=None, project_id="p1"):
    make_project(project_id, "Proj", f"/tmp/{project_id}")
    if parent_id and not session_rows.fetch(parent_id):
        insert_session(project_id, parent_id)
    insert_session(project_id, sid, parent_id=parent_id)


def make_session(sid="s1", parent_id=None):
    return build_session(sid=sid, project_id="p1", project_path="/tmp/p", parent_id=parent_id)


def make_ctx(session, broadcast=None):
    return ToolContext(
        session=session,
        broadcast=broadcast or AsyncMock(),
        tool_id="conclude",
    )


@contextlib.contextmanager
def conclude_patches(resolved=True, teardown_branch=None):
    mocks = SimpleNamespace(
        resolve=MagicMock(return_value=resolved),
        status=AsyncMock(),
        concluded=MagicMock(return_value=datetime.now(timezone.utc)),
        cleanup=MagicMock(),
        teardown=AsyncMock(return_value=teardown_branch),
    )
    with (
        patch("hypergolic.dispatch.conclude.handler.resolve_dispatch", mocks.resolve),
        patch("hypergolic.dispatch.conclude.handler.set_session_status_and_broadcast", mocks.status),
        patch("hypergolic.dispatch.conclude.handler.set_concluded_at", mocks.concluded),
        patch("hypergolic.dispatch.conclude.handler.schedule_session_sandbox_cleanup", mocks.cleanup),
        patch("hypergolic.dispatch.conclude.handler.teardown_worktree_at_conclude", mocks.teardown),
    ):
        yield mocks
