from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

if TYPE_CHECKING:
    from .Sample import Sample
    from .User import User


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(sa.String(64), default=None, nullable=True)

    num_samples: Mapped[int] = mapped_column(nullable=False, default=0)

    samples: Mapped[list["Sample"]] = relationship("Sample", back_populates="project", lazy="select")

    owner_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", back_populates="projects", lazy="joined")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "owner_id", "num_samples"]

    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name