"""initial schema

Revision ID: 0001
Revises:

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("model_tier", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("parent_id", sa.String(), nullable=True),
        sa.Column("dispatch_prompt", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("conclusion_rating", sa.Integer(), nullable=True),
        sa.Column("conclusion_feedback", sa.String(), nullable=True),
        sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worktree_path", sa.String(), nullable=False),
        sa.Column("worktree_branch", sa.String(), nullable=True),
        sa.Column("base_branch", sa.String(), nullable=False),
        sa.Column("worktree_status", sa.String(), nullable=True),
        sa.Column("resume_pending", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("origin", sa.String(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["sessions.id"],
            name="fk_sessions_parent",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sessions_created_at"), "sessions", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_sessions_parent_id"), "sessions", ["parent_id"], unique=False
    )
    op.create_index(
        op.f("ix_sessions_project_id"), "sessions", ["project_id"], unique=False
    )
    op.create_table(
        "artifacts",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("state_id", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_artifacts_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_artifacts_artifact_id"), "artifacts", ["artifact_id"], unique=False
    )
    op.create_index(
        op.f("ix_artifacts_created_at"), "artifacts", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_artifacts_session_id"), "artifacts", ["session_id"], unique=False
    )
    op.create_table(
        "errors",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("error_type", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("traceback", sa.String(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_errors_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_errors_created_at"), "errors", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_errors_session_id"), "errors", ["session_id"], unique=False
    )
    op.create_table(
        "messages",
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("sequence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("stop_reason", sa.String(), nullable=True),
        sa.Column("stop_sequence", sa.String(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_messages_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_messages_created_at"), "messages", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_messages_session_id"), "messages", ["session_id"], unique=False
    )
    op.create_index(
        "ix_messages_session_sequence",
        "messages",
        ["session_id", "sequence"],
        unique=False,
    )
    op.create_table(
        "sandboxes",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("tool_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("compose_project", sa.String(), nullable=True),
        sa.Column("config_path", sa.String(), nullable=False),
        sa.Column("port_map", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_sandboxes_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sandboxes_created_at"), "sandboxes", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_sandboxes_session_id"), "sandboxes", ["session_id"], unique=False
    )
    op.create_table(
        "session_workflows",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("current_state_id", sa.String(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_session_workflows_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_session_workflows_created_at"),
        "session_workflows",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_workflows_session_id"),
        "session_workflows",
        ["session_id"],
        unique=False,
    )
    op.create_table(
        "tool_approvals",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("tool_use_id", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("tool_input", sa.JSON(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("denial_reason", sa.String(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_tool_approvals_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tool_approvals_created_at"),
        "tool_approvals",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_approvals_session_id"),
        "tool_approvals",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_approvals_tool_use_id"),
        "tool_approvals",
        ["tool_use_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tool_approvals_tool_use_id"), table_name="tool_approvals")
    op.drop_index(op.f("ix_tool_approvals_session_id"), table_name="tool_approvals")
    op.drop_index(op.f("ix_tool_approvals_created_at"), table_name="tool_approvals")
    op.drop_table("tool_approvals")
    op.drop_index(
        op.f("ix_session_workflows_session_id"), table_name="session_workflows"
    )
    op.drop_index(
        op.f("ix_session_workflows_created_at"), table_name="session_workflows"
    )
    op.drop_table("session_workflows")
    op.drop_index(op.f("ix_sandboxes_session_id"), table_name="sandboxes")
    op.drop_index(op.f("ix_sandboxes_created_at"), table_name="sandboxes")
    op.drop_table("sandboxes")
    op.drop_index("ix_messages_session_sequence", table_name="messages")
    op.drop_index(op.f("ix_messages_session_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_created_at"), table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_errors_session_id"), table_name="errors")
    op.drop_index(op.f("ix_errors_created_at"), table_name="errors")
    op.drop_table("errors")
    op.drop_index(op.f("ix_artifacts_session_id"), table_name="artifacts")
    op.drop_index(op.f("ix_artifacts_created_at"), table_name="artifacts")
    op.drop_index(op.f("ix_artifacts_artifact_id"), table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index(op.f("ix_sessions_project_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_parent_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_created_at"), table_name="sessions")
    op.drop_table("sessions")
