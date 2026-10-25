import pytest
from sqlalchemy import select

from hypergolic.db.engine import _async_url, run_db, sync_url
from hypergolic.db.models import DBSession

pytestmark = pytest.mark.db


async def test_run_db_commits_writes_and_returns_results():
    def _insert(db):
        db.add(
            DBSession(
                worktree_path="/tmp/hg-test-wt", worktree_branch="main-S", base_branch="main", worktree_status="ready",
                id="s-run-db",
                model_tier="Medium",
               
                project_id="p-1",
            )
        )

    await run_db(_insert)

    role = await run_db(
        lambda db: db.execute(
            select(DBSession.role).where(DBSession.id == "s-run-db")
        ).scalar_one()
    )
    assert role == "generalist"


@pytest.mark.parametrize(
    "configured,expected_sync,expected_async",
    [
        (
            "postgresql://u:p@h:5432/db",
            "postgresql+psycopg://u:p@h:5432/db",
            "postgresql+asyncpg://u:p@h:5432/db",
        ),
        (
            "postgresql+psycopg://u:p@h:5432/db",
            "postgresql+psycopg://u:p@h:5432/db",
            "postgresql+asyncpg://u:p@h:5432/db",
        ),
        (
            "postgresql+asyncpg://u:p@h:5432/db",
            "postgresql+psycopg://u:p@h:5432/db",
            "postgresql+asyncpg://u:p@h:5432/db",
        ),
    ],
)
def test_url_rewriting_picks_installed_drivers(
    configured, expected_sync, expected_async
):
    assert sync_url(configured) == expected_sync
    if expected_async is not None:
        assert _async_url(configured) == expected_async
