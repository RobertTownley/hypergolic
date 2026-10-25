"""messages.provider_message_id: the provider's reply id, which a response cache can repeat across sessions

Revision ID: 0008
Revises: 0007

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("provider_message_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "provider_message_id")
