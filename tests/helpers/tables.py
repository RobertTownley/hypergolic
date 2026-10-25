from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import ModuleType
from typing import Any

import pytest

from hypergolic.artifacts import artifact_rows
from hypergolic.db import audit_rows
from hypergolic.db.models import Base, DBArtifact, DBMessage, DBSandbox, DBSession
from hypergolic.messages import message_rows
from hypergolic.sandbox.manager import sandbox_rows
from hypergolic.sessions import session_rows
from hypergolic.skills import activation_rows
from hypergolic.workflows import workflow_rows

_last_now = datetime.min.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    global _last_now
    _last_now = max(datetime.now(timezone.utc), _last_now + timedelta(microseconds=1))
    return _last_now


def _insert_defaults(row: Base) -> None:
    for col in row.__table__.columns:
        if getattr(row, col.key) is not None or col.default is None:
            continue
        default = col.default
        value = default.arg if default.is_scalar else default.arg(None) if default.is_callable else _now()
        setattr(row, col.key, getattr(value, "value", value))


def _matches(row: Any, criteria: dict[str, Any]) -> bool:
    return all(getattr(row, key) == value for key, value in criteria.items())


class _Fake:
    module: ModuleType
    names: tuple[str, ...]

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in self.names:
            monkeypatch.setattr(self.module, name, getattr(self, name))


class FakeSessionRows(_Fake):
    module, names = session_rows, ("insert", "fetch", "find", "claim_resume_flags", "delete", "afetch", "update", "aupdate", "atransition")

    def __init__(self) -> None:
        self.by_id: dict[str, DBSession] = {}

    def __getitem__(self, session_id: str) -> DBSession:
        return self.by_id[session_id]

    def insert(self, row: DBSession) -> None:
        _insert_defaults(row)
        self.by_id[row.id] = row

    def fetch(self, session_id: str) -> DBSession | None:
        return self.by_id.get(session_id)

    def find(self, **criteria: Any) -> list[DBSession]:
        return [row for row in self.by_id.values() if _matches(row, criteria)]

    def claim_resume_flags(self) -> list[DBSession]:
        claimed = [row for row in self.by_id.values() if row.resume_pending]
        for row in claimed:
            row.resume_pending = False
        return claimed

    def delete(self, session_id: str) -> None:
        for child in self.find(parent_id=session_id):
            self.delete(child.id)
        self.by_id.pop(session_id, None)

    async def afetch(self, session_id: str) -> DBSession | None:
        return self.fetch(session_id)

    def update(self, session_id: str, **values: Any) -> None:
        row = self.by_id.get(session_id)
        for key, value in values.items() if row else ():
            setattr(row, key, value)

    async def aupdate(self, session_id: str, **values: Any) -> None:
        self.update(session_id, **values)

    async def atransition(self, session_id: str, from_status: str, **values: Any) -> bool:
        row = self.by_id.get(session_id)
        if row is None or row.status != from_status:
            return False
        self.update(session_id, **values)
        return True


class FakeMessageRows(_Fake):
    module, names = message_rows, ("for_session", "last", "insert", "truncate", "splice")

    def __init__(self) -> None:
        self.rows: list[DBMessage] = []

    def for_session(self, session_id: str) -> list[DBMessage]:
        return sorted((r for r in self.rows if r.session_id == session_id), key=lambda r: (r.sequence, r.id))

    def last(self, session_id: str, role: str | None = None) -> DBMessage | None:
        live = [r for r in self.for_session(session_id) if not r.truncated and role in (None, r.role)]
        return live[-1] if live else None

    def insert(self, *messages: DBMessage) -> None:
        for m in messages:
            if not m.sequence:
                m.sequence = 1 + max((r.sequence for r in self.rows if r.session_id == m.session_id), default=0)
            _insert_defaults(m)
            self.rows.append(m)

    def truncate(self, session_id: str) -> None:
        for r in self.rows:
            if r.session_id == session_id:
                r.truncated = True

    def splice(self, session_id: str, retire_ids: list[str], message: DBMessage) -> None:
        for r in self.rows:
            r.truncated = r.truncated or r.id in retire_ids
            if r.session_id == session_id and r.sequence >= message.sequence:
                r.sequence += 1
        self.insert(message)


class FakeWorkflowRows(_Fake):
    module, names = workflow_rows, ("active", "start", "move", "end")

    def __init__(self) -> None:
        self.live: dict[str, tuple[str, str]] = {}

    def seed(self, session_id: str = "s-1", workflow_id: str = "wf-1", state_id: str = "st-1") -> None:
        self.live[session_id] = (workflow_id, state_id)

    def active(self, session_id: str) -> tuple[str, str] | None:
        return self.live.get(session_id)

    async def start(self, session_id: str, workflow_id: str, state_id: str) -> None:
        self.live[session_id] = (workflow_id, state_id)

    async def move(self, session_id: str, state_id: str) -> None:
        if session_id in self.live:
            self.live[session_id] = (self.live[session_id][0], state_id)

    async def end(self, session_id: str) -> None:
        self.live.pop(session_id, None)


class FakeArtifactRows(_Fake):
    module, names = artifact_rows, ("get", "find", "insert", "add")

    def __init__(self) -> None:
        self.rows: list[DBArtifact] = []

    def insert(self, row: DBArtifact) -> None:
        _insert_defaults(row)
        self.rows.append(row)

    def get(self, artifact_db_id: str) -> DBArtifact | None:
        return next((r for r in self.rows if r.id == artifact_db_id), None)

    def find(
        self, *, newest_first: bool = False, offset: int = 0, limit: int | None = None, **criteria: Any,
    ) -> list[DBArtifact]:
        rows = sorted((r for r in self.rows if _matches(r, criteria)), key=lambda r: r.created_at, reverse=newest_first)
        return rows[offset:None if limit is None else offset + limit]

    async def add(self, row: DBArtifact) -> None:
        self.insert(row)


class FakeSandboxRows(_Fake):
    module, names = sandbox_rows, ("get", "find", "create", "update")

    def __init__(self) -> None:
        self.rows: list[DBSandbox] = []

    async def get(self, session_id: str, tool_id: str) -> DBSandbox | None:
        return next((r for r in self.rows if (r.session_id, r.tool_id) == (session_id, tool_id)), None)

    async def find(self, *, statuses: Collection[str] = (), **criteria: Any) -> list[DBSandbox]:
        return [r for r in self.rows if _matches(r, criteria) and (not statuses or r.status in statuses)]

    async def create(self, session_id: str, tool_id: str, **fields: Any) -> DBSandbox:
        row = DBSandbox(session_id=session_id, tool_id=tool_id, **fields)
        _insert_defaults(row)
        self.rows.append(row)
        return row

    async def update(self, sandbox_id: str, **values: Any) -> None:
        for row in self.rows:
            if row.id == sandbox_id:
                for key, value in values.items():
                    setattr(row, key, value)


class FakeActivationRows(_Fake):
    module, names = activation_rows, ("record", "skill_ids")

    def __init__(self) -> None:
        self.by_session: dict[str, list[str]] = {}

    async def record(self, session_id: str, skill_id: str) -> None:
        ids = self.by_session.setdefault(session_id, [])
        if skill_id not in ids:
            ids.append(skill_id)

    def skill_ids(self, session_id: str) -> list[str]:
        return list(self.by_session.get(session_id, ()))


class FakeAuditRows(_Fake):
    module, names = audit_rows, ("insert",)

    def __init__(self) -> None:
        self.rows: list[Base] = []

    def insert(self, row: Base) -> None:
        self.rows.append(row)

    def of(self, model: type[Base]) -> list[Any]:
        return [r for r in self.rows if isinstance(r, model)]


@dataclass
class MemoryTables:
    sessions: FakeSessionRows = field(default_factory=FakeSessionRows)
    messages: FakeMessageRows = field(default_factory=FakeMessageRows)
    workflows: FakeWorkflowRows = field(default_factory=FakeWorkflowRows)
    artifacts: FakeArtifactRows = field(default_factory=FakeArtifactRows)
    sandboxes: FakeSandboxRows = field(default_factory=FakeSandboxRows)
    activations: FakeActivationRows = field(default_factory=FakeActivationRows)
    audit: FakeAuditRows = field(default_factory=FakeAuditRows)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for fake in vars(self).values():
            fake.install(monkeypatch)
