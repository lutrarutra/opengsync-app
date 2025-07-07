from typing import Optional, TYPE_CHECKING
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from .Base import Base

if TYPE_CHECKING:
    from .User import User
    from .File import File


class Comment(Base):
    __tablename__ = "comment"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    text: Mapped[str] = mapped_column(sa.String(2048), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=sa.func.now())
    
    file_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("file.id"), nullable=True)
    file: Mapped[Optional["File"]] = relationship("File", lazy="select", foreign_keys=[file_id])

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