from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Links import SampleLibraryLink

from .Base import Base

if TYPE_CHECKING:
    from .Project import Project
    from .User import User


class Sample(Base):
    __tablename__ = "sample"
    
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    num_libraries: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    project_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("project.id"), nullable=False)
    project: Mapped["Project"] = relationship("Project", back_populates="samples", lazy="select")

    owner_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", back_populates="samples", lazy="joined")

    library_links: Mapped[list["SampleLibraryLink"]] = relationship(
        SampleLibraryLink, back_populates="sample", lazy="select",
        cascade="save-update, merge, delete"
    )

    sortable_fields: ClassVar[list[str]] = ["id", "name", "project_id", "owner_id", "num_libraries"]

    def __str__(self):
        return f"Sample(id: {self.id}, name:{self.name})"

    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return self.project.name
    
    def is_editable(self) -> bool:
        for link in self.library_links:
            if not link.library.is_editable():
                return False
        return True
