import functools
from datetime import datetime
from typing import cast

from sqlalchemy import func, select

from hypergolic.db.engine import get_db
from hypergolic.db.models import DBSession
from hypergolic.db.utils import to_iso_utc
from hypergolic.harness.app.state import get_app
from hypergolic.projects.schemas import ProjectResponse


@functools.total_ordering
class _DescStr:
    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _DescStr) and self.value == other.value

    def __lt__(self, other: "_DescStr") -> bool:
        return self.value > other.value


def latest_session_times() -> dict[str, datetime]:
    with get_db() as db:
        return dict(db.execute(
            select(DBSession.project_id, func.max(DBSession.created_at)).group_by(DBSession.project_id)
        ).tuples().all())


def list_all_projects() -> list[ProjectResponse]:
    last_session_at = latest_session_times()
    projects = [
        ProjectResponse(
            id=p.id,
            name=p.name,
            path=p.path,
            last_session_at=(
                to_iso_utc(last_session_at[p.id]) if last_session_at.get(p.id) else None
            ),
        )
        for p in get_app().projects
    ]
    active = sorted(
        (r for r in projects if r.last_session_at is not None),
        key=lambda r: (_DescStr(cast(str, r.last_session_at)), r.name),
    )
    inactive = sorted(
        (r for r in projects if r.last_session_at is None),
        key=lambda r: r.name,
    )
    return active + inactive


def project_name(project_id: str) -> str:
    try:
        return get_app().get_project(project_id).name
    except KeyError:
        return project_id
