"""sessions.prompt_blocks: system prompt frozen at the session's first turn

Revision ID: 0005
Revises: 0004

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("prompt_blocks", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "prompt_blocks")
