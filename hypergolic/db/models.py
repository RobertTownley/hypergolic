from datetime import datetime
from typing import Any

from anthropic.types.tool_result_block_param import Content
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    event,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from hypergolic.enums import (
    ModelTier,
    SessionStatus,
    WorkflowOutcome,
)
from hypergolic.ids import new_id


class Base(DeclarativeBase):
    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        nullable=False,
        default=new_id,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False
    )


class DBSession(Base):
    __tablename__ = "sessions"

    model_tier: Mapped[ModelTier] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="generalist")
    status: Mapped[SessionStatus] = mapped_column(
        String, nullable=False, default=SessionStatus.IDLE
    )
    project_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("sessions.id", name="fk_sessions_parent", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    dispatch_prompt: Mapped[str | None] = mapped_column(String, nullable=True)
    conducted_by: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    description: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    conclusion_rating: Mapped[int | None] = mapped_column(nullable=True, default=None)
    conclusion_feedback: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    concluded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    worktree_path: Mapped[str] = mapped_column(String, nullable=False)
    base_branch: Mapped[str] = mapped_column(String, nullable=False)
    # Nulled at conclusion: branch when merged/discarded, status when the
    # worktree is torn down. See clear_session_worktree_fields.
    worktree_branch: Mapped[str | None] = mapped_column(String, nullable=True)
    worktree_status: Mapped[str | None] = mapped_column(String, nullable=True)
    resume_pending: Mapped[bool] = mapped_column(
        default=False, nullable=False, server_default="0"
    )
    # 'cli' for headless `hypergolic run` sessions; NULL for UI-driven ones.
    origin: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    # Explicit per-slot sha pins ({app|harness|shared: sha}) and the resolved
    # sha of every slot at creation; the latter makes the session replayable.
    repo_pins: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True, default=None)
    repo_shas: Mapped[dict[str, str | None] | None] = mapped_column(JSON, nullable=True, default=None)
    app_overrides: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True, default=None)
    # Frozen at the first turn ([{source, text}]): any byte of system-prompt
    # drift invalidates the whole cached prefix, and sessions edit the very
    # files (knowledge index, proposals) the prompt injects.
    prompt_blocks: Mapped[list[dict[str, str]] | None] = mapped_column(JSON, nullable=True, default=None)


class DBMessage(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_session_sequence", "session_id", "sequence"),
    )

    content: Mapped[list[Content]] = mapped_column(JSON, nullable=False)
    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", name="fk_messages_sessions", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model: Mapped[str] = mapped_column(String, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    stop_sequence: Mapped[str | None] = mapped_column(String, nullable=True)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    truncated: Mapped[bool] = mapped_column(default=False, nullable=False)


MESSAGE_ORDER = (DBMessage.sequence, DBMessage.id)
MESSAGE_ORDER_DESC = (DBMessage.sequence.desc(), DBMessage.id.desc())


class DBSessionWorkflow(Base):
    __tablename__ = "session_workflows"

    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey(
            "sessions.id", name="fk_session_workflows_sessions", ondelete="CASCADE"
        ),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[str] = mapped_column(String, nullable=False)
    current_state_id: Mapped[str] = mapped_column(String, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class DBSkillActivation(Base):
    """A skill the agent has `activate_skill`ed in this session.

    The activation's text lives in a tool_result that turn compaction will
    summarize away; this row is what survives, so the prompt can keep naming
    the skill and the agent knows to reload it. One row per (session, skill):
    re-activation after compaction is expected and not worth a history.
    """

    __tablename__ = "skill_activations"
    __table_args__ = (
        UniqueConstraint("session_id", "skill_id", name="uq_skill_activations_session_skill"),
    )

    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey(
            "sessions.id", name="fk_skill_activations_sessions", ondelete="CASCADE"
        ),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[str] = mapped_column(String, nullable=False)


class DBArtifact(Base):
    __tablename__ = "artifacts"

    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", name="fk_artifacts_sessions", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[str] = mapped_column(String, nullable=False)
    state_id: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[WorkflowOutcome] = mapped_column(String, nullable=False)
    artifact_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)


class DBError(Base):
    __tablename__ = "errors"

    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", name="fk_errors_sessions", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    error_type: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    traceback: Mapped[str | None] = mapped_column(String, nullable=True)


class DBSandbox(Base):
    __tablename__ = "sandboxes"

    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", name="fk_sandboxes_sessions", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    compose_project: Mapped[str | None] = mapped_column(String, nullable=True)
    config_path: Mapped[str] = mapped_column(String, nullable=False)
    config_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    port_map: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)


class DBToolApproval(Base):
    __tablename__ = "tool_approvals"

    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", name="fk_tool_approvals_sessions", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_use_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    tool_input: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    approved: Mapped[bool] = mapped_column(nullable=False)
    denial_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    annotations: Mapped[list[dict[str, str]] | None] = mapped_column(JSON, nullable=True)


@event.listens_for(DBMessage, "before_insert")
def _assign_message_sequence(mapper, connection, target: "DBMessage") -> None:
    """Assign a per-session, monotonically increasing sequence at insert time.

    Message order is defined by this sequence rather than ``created_at`` (which
    only has second granularity); within one wall-clock second several messages
    may be persisted, and ordering by timestamp alone is non-deterministic.
    """
    if getattr(target, "sequence", None):
        return
    next_seq = connection.execute(
        select(func.coalesce(func.max(DBMessage.sequence), 0) + 1).where(
            DBMessage.session_id == target.session_id
        )
    ).scalar_one()
    target.sequence = next_seq
