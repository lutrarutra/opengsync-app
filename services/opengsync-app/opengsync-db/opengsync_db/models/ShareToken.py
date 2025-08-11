from typing import TYPE_CHECKING

import uuid as uuid_lib
from datetime import datetime
from datetime import timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .User import User
    from .SharePath import SharePath


class ShareToken(Base):
    __tablename__ = "share_token"

    uuid: Mapped[uuid_lib.UUID] = mapped_column(sa.Uuid, primary_key=True, default=sa.func.uuid_generate_v4)
    time_valid_min: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_utc: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=sa.func.now)
    _expired: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False, name="expired")

    owner_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", lazy="select")

    paths: Mapped[list["SharePath"]] = relationship("SharePath", back_populates="token", lazy="select", cascade="all, delete-orphan")

    @property
    def is_expired(self) -> bool:
        return self._expired or (self.created_utc.timestamp() + self.time_valid_min * 60 < datetime.now(timezone.utc).timestamp())
