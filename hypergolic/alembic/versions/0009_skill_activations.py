"""skill_activations: which skills a session has activated, durable across turn compaction

Revision ID: 0009
Revises: 0008

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skill_activations",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_skill_activations_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "skill_id", name="uq_skill_activations_session_skill"
        ),
    )
    op.create_index(
        op.f("ix_skill_activations_created_at"),
        "skill_activations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_skill_activations_session_id"),
        "skill_activations",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_skill_activations_session_id"), table_name="skill_activations")
    op.drop_index(op.f("ix_skill_activations_created_at"), table_name="skill_activations")
    op.drop_table("skill_activations")
