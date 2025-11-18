from typing import TYPE_CHECKING
from uuid_extensions import uuid7str
from datetime import datetime
from datetime import timezone, timedelta

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .User import User


class APIToken(Base):
    __tablename__ = "api_token"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    uuid: Mapped[str] = mapped_column(sa.CHAR(36), default=lambda: uuid7str(), nullable=False, unique=True)
    time_valid_min: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    _expired: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False, name="expired")

    owner_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", lazy="select")

    @hybrid_property
    def expiration(self) -> datetime:  # type: ignore[override]
        return self.created_utc + timedelta(minutes=self.time_valid_min)

    @expiration.expression
    def expiration(cls) -> sa.ColumnElement[datetime]:
        return sa.func.timezone("UTC", cls.created_utc) + sa.func.make_interval(0, 0, 0, 0, 0, cls.time_valid_min)

    @property
    def is_expired(self) -> bool:
        return self._expired or (datetime.now(timezone.utc) > self.expiration)

    def __repr__(self) -> str:
        return f"APIToken(uuid={self.uuid}, owner_id={self.owner_id}, time_valid_min={self.time_valid_min}, created_utc={self.created_utc.isoformat()})"
    
    def __str__(self) -> str:
        return self.__repr__()
