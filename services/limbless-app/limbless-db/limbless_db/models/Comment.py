from typing import Optional, TYPE_CHECKING
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from .Base import Base

if TYPE_CHECKING:
    from .User import User


class Comment(Base):
    __tablename__ = "comment"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    text: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=sa.func.now())
    author_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    file_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("file.id"), nullable=True)

    author: Mapped["User"] = relationship("User", lazy="joined")

    @property
    def timestamp(self) -> datetime:
        return localize(self.timestamp_utc)

    def timestamp_str(self) -> str:
        return self.timestamp.strftime('%Y-%m-%d %H:%M')
    
    def date(self) -> str:
        return self.timestamp.strftime('%Y-%m-%d')
    
    def time(self) -> str:
        return self.timestamp.strftime('%H:%M')