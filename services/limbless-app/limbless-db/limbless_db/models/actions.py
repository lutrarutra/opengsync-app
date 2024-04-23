from typing import Optional, TYPE_CHECKING
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from limbless_db.categories import PoolStatus, PoolStatusEnum, ExperimentStatus, ExperimentStatusEnum

from .. import localize
from .Base import Base

if TYPE_CHECKING:
    from .User import User
    from .Comment import Comment
    from .File import File


class PoolAction(Base):
    __tablename__ = "pool_action"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    status_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    pool_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("pool.id"), nullable=False)
    
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=sa.func.now())
    
    user_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    user: Mapped["User"] = relationship("User", lazy="joined")
    
    comment_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("comment.id"), nullable=True)
    comment: Mapped[Optional["Comment"]] = relationship("Comment", lazy="select")

    file_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("file.id"), nullable=True)
    file: Mapped[Optional["File"]] = relationship("File", lazy="select")

    @property
    def timestamp(self) -> datetime:
        return localize(self.timestamp_utc)

    @property
    def timestamp_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    
    @property
    def status(self) -> PoolStatusEnum:
        return PoolStatus.get(self.status_id)
    

class ExperimentAction(Base):
    __tablename__ = "experiment_action"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    status_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    experiment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("experiment.id"), nullable=False)

    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=sa.func.now())

    user_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    user: Mapped["User"] = relationship("User", lazy="joined")

    comment_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("comment.id"), nullable=True)
    comment: Mapped[Optional["Comment"]] = relationship("Comment", lazy="select")

    file_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("file.id"), nullable=True)
    file: Mapped[Optional["File"]] = relationship("File", lazy="select")

    @property
    def timestamp(self) -> datetime:
        return localize(self.timestamp_utc)
    
    @property
    def timestamp_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    
    @property
    def status(self) -> ExperimentStatusEnum:
        return ExperimentStatus.get(self.status_id)