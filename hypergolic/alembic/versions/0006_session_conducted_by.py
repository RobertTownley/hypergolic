"""sessions.conducted_by: the conducting parent of a `dispatch --eval` child

Revision ID: 0006
Revises: 0005

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("conducted_by", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "conducted_by")
