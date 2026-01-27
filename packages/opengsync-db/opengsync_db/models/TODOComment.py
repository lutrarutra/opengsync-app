from typing import TYPE_CHECKING
from datetime import datetime
from datetime import timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from .Base import Base
from ..categories import TaskStatus, TaskStatusEnum

if TYPE_CHECKING:
    from .User import User


class TODOComment(Base):
    __tablename__ = "todo_comment"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    task_status_id: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True, default=0)
    
    author_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    author: Mapped["User"] = relationship("User", lazy="joined")

    pool_design_id: Mapped[int | None] = mapped_column(sa.ForeignKey("pool_design.id", ondelete="CASCADE"), nullable=True)
    flow_cell_design_id: Mapped[int | None] = mapped_column(sa.ForeignKey("flow_cell_design.id", ondelete="CASCADE"), nullable=True)

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
        return f"TODOComment(id={self.id}, text={self.text}, timestamp={self.timestamp}, author_id={self.author_id})"

    @property
    def task_status(self) -> TaskStatusEnum | None:
        if self.task_status_id is None:
            return None
        return TaskStatus.get(self.task_status_id)
    
    @task_status.setter
    def task_status(self, status: TaskStatusEnum | None) -> None:
        if status is None:
            self.task_status_id = None
        else:
            self.task_status_id = status.id