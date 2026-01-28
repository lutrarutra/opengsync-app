from datetime import datetime
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from ..categories import EventType, EventTypeEnum
from .Base import Base

if TYPE_CHECKING:
    from .SeqRequest import SeqRequest
    from .User import User


class Event(Base):
    __tablename__ = "event"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    title: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(sa.String(512), nullable=True)
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    creator_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    creator: Mapped["User"] = relationship("User", lazy="select")
 
    seq_request: Mapped[Optional["SeqRequest"]] = relationship("SeqRequest")
    
    @property
    def type(self) -> EventTypeEnum:
        return EventType.get(self.type_id)

    @property
    def timestamp(self) -> datetime:
        return localize(self.timestamp_utc)
    
    def timestamp_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        return self.timestamp.strftime(fmt)
    
    def timestamp_title(self) -> str:
        return self.timestamp.strftime("%A, %B %d, %Y")

    def __str__(self) -> str:
        return f"Event({self.timestamp_str()}, {self.type})"
    
    def __repr__(self) -> str:
        return self.__str__()