"""sessions.app_overrides: App settings a dispatched session runs with

Revision ID: 0007
Revises: 0006

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("app_overrides", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "app_overrides")
