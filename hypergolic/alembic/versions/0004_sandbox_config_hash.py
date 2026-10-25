"""sandboxes.config_hash: compiled compose digest for drift convergence

Revision ID: 0004
Revises: 0003

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sandboxes", sa.Column("config_hash", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("sandboxes", "config_hash")
