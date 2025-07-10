from typing import Optional, TYPE_CHECKING, ClassVar
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from .. import localize
from ..categories import ProjectStatus, ProjectStatusEnum

if TYPE_CHECKING:
    from .Sample import Sample
    from .User import User
    from .Group import Group


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(sa.String(1024), default=None, nullable=True)

    timestamp_created_utc: Mapped[datetime] = mapped_column(sa.DateTime(), nullable=False, default=sa.func.now())

    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    num_samples: Mapped[int] = mapped_column(nullable=False, default=0)

    samples: Mapped[list["Sample"]] = relationship("Sample", back_populates="project", lazy="select")

    owner_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", back_populates="projects", lazy="joined")

    group_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("group.id"), nullable=True)
    group: Mapped[Optional["Group"]] = relationship("Group", lazy="joined", foreign_keys=[group_id], cascade="save-update, merge")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "owner_id", "num_samples", "status_id", "group_id", "timestamp_created_utc"]

    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    @property
    def status(self) -> ProjectStatusEnum:
        return ProjectStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: ProjectStatusEnum):
        self.status_id = value.id

    @property
    def timestamp_created(self) -> datetime:
        return localize(self.timestamp_created_utc)

    def timestamp_created_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        return self.timestamp_created.strftime(fmt)
    
    def __str__(self) -> str:
        return f"Project(id: {self.id}, name: {self.name}, owner_id: {self.owner_id})"
    
    def __repr__(self) -> str:
        return self.__str__()