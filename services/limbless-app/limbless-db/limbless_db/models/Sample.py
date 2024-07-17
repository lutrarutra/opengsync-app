from typing import Optional, TYPE_CHECKING, ClassVar
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..categories import SampleStatus, SampleStatusEnum
from .Links import SampleLibraryLink
from .Base import Base

if TYPE_CHECKING:
    from .Project import Project
    from .User import User
    from .SeqRequest import SeqRequest
    from .File import File
    from .SampleAttribute import SampleAttribute
    from .Links import SamplePlateLink


class Sample(Base):
    __tablename__ = "sample"
    
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    status_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    num_libraries: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    qubit_concentration: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    avg_fragment_size: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True, default=None)
    timestamp_stored_utc: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(), nullable=True, default=None)

    project_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("project.id"), nullable=False)
    project: Mapped["Project"] = relationship("Project", back_populates="samples", lazy="select")

    ba_report_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("file.id"), nullable=True, default=None)
    ba_report: Mapped[Optional["File"]] = relationship("File", lazy="select")
    
    plate_links: Mapped[list["SamplePlateLink"]] = relationship("SamplePlateLink", back_populates="sample", lazy="select")

    seq_request_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("seq_request.id"), nullable=False)
    seq_request: Mapped["SeqRequest"] = relationship("SeqRequest", back_populates="samples", lazy="select")

    owner_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", back_populates="samples", lazy="joined")

    library_links: Mapped[list["SampleLibraryLink"]] = relationship(
        SampleLibraryLink, back_populates="sample", lazy="select",
        cascade="save-update, merge, delete"
    )

    attributes: Mapped[list["SampleAttribute"]] = relationship("SampleAttribute", lazy="select")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "project_id", "owner_id", "num_libraries", "status_id"]

    @property
    def status(self) -> SampleStatusEnum:
        return SampleStatus.get(self.status_id)
    
    @property
    def timestamp_stored_str(self) -> str:
        return self.timestamp_stored_utc.strftime("%Y-%m-%d %H:%M:%S") if self.timestamp_stored_utc is not None else ""

    def __str__(self):
        return f"Sample(id: {self.id}, name:{self.name})"
    
    def __repr__(self):
        return self.__str__()

    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> Optional[str]:
        return self.project.name
    
    def is_editable(self) -> bool:
        return self.status == SampleStatus.DRAFT
    