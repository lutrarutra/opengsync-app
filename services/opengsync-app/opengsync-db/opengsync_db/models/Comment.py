from typing import Optional, TYPE_CHECKING
from datetime import datetime
from datetime import timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from .Base import Base

if TYPE_CHECKING:
    from .User import User
    from .MediaFile import MediaFile


class Comment(Base):
    __tablename__ = "comment"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    file_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("media_file.id"), nullable=True)
    file: Mapped[Optional["MediaFile"]] = relationship("MediaFile", lazy="select", foreign_keys=[file_id])

    author_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    author: Mapped["User"] = relationship("User", lazy="joined")

    seq_request_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("seq_request.id"), nullable=True)
    experiment_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("experiment.id"), nullable=True)
    lab_prep_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("lab_prep.id"), nullable=True)

    @property
    def timestamp(self) -> datetime:
        return localize(self.timestamp_utc)

    def timestamp_str(self) -> str:
        return self.timestamp.strftime('%Y-%m-%d %H:%M')
    
    def date(self) -> str:
        return self.timestamp.strftime('%Y-%m-%d')
    
    def time(self) -> str:
        return self.timestamp.strftime('%H:%M')
    
    def __str__(self) -> str:
        return self.__repr__()
    
    def __repr__(self) -> str:
        return f"Comment(id={self.id}, text={self.text}, timestamp={self.timestamp}, author_id={self.author_id})"