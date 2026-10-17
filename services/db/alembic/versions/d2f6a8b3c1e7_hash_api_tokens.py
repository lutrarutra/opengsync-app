"""store API tokens as sha256 hashes instead of plaintext

Revision ID: d2f6a8b3c1e7
Revises: c7a3e5f19d2b
Create Date: 2026-10-12 12:00:00.000000

Existing tokens keep working: their plaintext (the old ``uuid`` column) is hashed in place,
and authentication hashes the presented token before looking it up. The plaintext cannot be
recovered on downgrade, so downgrading invalidates every token.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2f6a8b3c1e7"
down_revision: Union[str, Sequence[str], None] = "c7a3e5f19d2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("api_token", sa.Column("token_hash", sa.CHAR(64), nullable=True))
    op.execute("UPDATE api_token SET token_hash = encode(sha256(convert_to(uuid, 'UTF8')), 'hex')")
    op.alter_column("api_token", "token_hash", nullable=False)
    op.create_unique_constraint("api_token_token_hash_key", "api_token", ["token_hash"])
    op.drop_column("api_token", "uuid")


def downgrade() -> None:
    op.add_column("api_token", sa.Column("uuid", sa.CHAR(36), nullable=True))
    # Plaintext is gone: give every token a fresh random value and expire it.
    op.execute("UPDATE api_token SET uuid = gen_random_uuid()::text, expired = true")
    op.alter_column("api_token", "uuid", nullable=False)
    op.create_unique_constraint("api_token_uuid_key", "api_token", ["uuid"])
    op.drop_constraint("api_token_token_hash_key", "api_token", type_="unique")
    op.drop_column("api_token", "token_hash")
