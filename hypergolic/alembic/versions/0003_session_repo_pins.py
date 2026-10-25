"""sessions.repo_pins + repo_shas: pinned and resolved per-slot shas

Revision ID: 0003
Revises: 0002

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("repo_pins", sa.JSON(), nullable=True))
    op.add_column("sessions", sa.Column("repo_shas", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "repo_shas")
    op.drop_column("sessions", "repo_pins")
