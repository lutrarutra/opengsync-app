"""add combination_num to protocol_kit_link pk

Revision ID: 418712f21d04
Revises: fd486cb8a2b4
Create Date: 2025-11-14 08:33:42.239666

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '418712f21d04'
down_revision: Union[str, Sequence[str], None] = 'fd486cb8a2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column('protocol_kit_link', sa.Column('combination_num', sa.SmallInteger(), nullable=True))

    # 2. Populate the new column for existing rows
    op.execute("UPDATE protocol_kit_link SET combination_num = 1")

    # 3. Alter the column to be NOT NULL
    op.alter_column('protocol_kit_link', 'combination_num', nullable=False)

    # 4. Drop the existing primary key constraint (CORRECTED)
    op.drop_constraint('protocol_kit_link_pkey', 'protocol_kit_link', type_='primary')

    # 5. Create the new composite primary key constraint
    op.create_primary_key(
        "protocol_kit_link_pkey",
        "protocol_kit_link",
        ["protocol_id", "kit_id", "combination_num"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('protocol_kit_link_pkey', 'protocol_kit_link', type_='primary')

    # 2. Recreate the original primary key
    op.create_primary_key(
        "protocol_kit_link_pkey",
        "protocol_kit_link",
        ["protocol_id", "kit_id"]
    )

    # 3. Drop the new column
    op.drop_column('protocol_kit_link', 'combination_num')
