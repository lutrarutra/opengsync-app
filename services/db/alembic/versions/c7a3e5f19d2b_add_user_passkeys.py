"""add user passkeys (webauthn)

Revision ID: c7a3e5f19d2b
Revises: b4e9d7c12a6f
Create Date: 2026-10-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7a3e5f19d2b"
down_revision: Union[str, Sequence[str], None] = "b4e9d7c12a6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lims_user",
        sa.Column("webauthn_user_handle", sa.LargeBinary(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "lims_user_webauthn_user_handle_key", "lims_user", ["webauthn_user_handle"],
    )

    op.create_table(
        "user_passkey",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False),
        sa.Column("transports", sa.String(length=128), nullable=True),
        sa.Column("aaguid", sa.String(length=36), nullable=True),
        sa.Column("backed_up", sa.Boolean(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("created_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["lims_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_passkey_credential_id"), "user_passkey", ["credential_id"], unique=True)
    op.create_index(op.f("ix_user_passkey_user_id"), "user_passkey", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_passkey_user_id"), table_name="user_passkey")
    op.drop_index(op.f("ix_user_passkey_credential_id"), table_name="user_passkey")
    op.drop_table("user_passkey")
    op.drop_constraint("lims_user_webauthn_user_handle_key", "lims_user", type_="unique")
    op.drop_column("lims_user", "webauthn_user_handle")
