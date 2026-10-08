from typing import TYPE_CHECKING
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .User import User


class UserPasskey(Base):
    """A WebAuthn credential (passkey) registered by a user."""
    __tablename__ = "user_passkey"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    credential_id: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False, unique=True, index=True)
    public_key: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, default=0)
    transports: Mapped[str | None] = mapped_column(sa.String(128), nullable=True, default=None)
    aaguid: Mapped[str | None] = mapped_column(sa.String(36), nullable=True, default=None)
    backed_up: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_used_utc: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True, default=None)

    user_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id", ondelete="CASCADE"), nullable=False, index=True)
    user: Mapped["User"] = relationship("User", back_populates="passkeys", lazy="select")

    @property
    def transport_list(self) -> list[str]:
        return self.transports.split(",") if self.transports else []

    def __repr__(self) -> str:
        return f"UserPasskey(id={self.id}, user_id={self.user_id}, name={self.name})"

    def __str__(self) -> str:
        return self.__repr__()
