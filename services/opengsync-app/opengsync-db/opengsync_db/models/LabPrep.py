from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opengsync_db.categories import LabProtocol, LabProtocolEnum, PrepStatus, PrepStatusEnum, FileType, AssayTypeEnum, AssayType

from .Base import Base
from .. import LAB_PROTOCOL_START_NUMBER

if TYPE_CHECKING:
    from .User import User
    from .Library import Library
    from .Plate import Plate
    from .File import File
    from .Pool import Pool
    from .Comment import Comment


class LabPrep(Base):
    __tablename__ = "lab_prep"

    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(32), nullable=False, index=True)
    prep_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    protocol_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=0)
    assay_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    creator_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    creator: Mapped["User"] = relationship("User", back_populates="preps", lazy="joined")

    plates: Mapped[list["Plate"]] = relationship("Plate", back_populates="lab_prep", cascade="save-update, merge, delete, delete-orphan", lazy="select", order_by="Plate.id")

    prep_file: Mapped[Optional["File"]] = relationship(
        "File", lazy="joined", viewonly=True,
        primaryjoin=f"and_(LabPrep.id == File.lab_prep_id, File.type_id == {FileType.LIBRARY_PREP_FILE.id})",
    )

    libraries: Mapped[list["Library"]] = relationship("Library", back_populates="lab_prep", lazy="select", order_by="Library.id")
    pools: Mapped[list["Pool"]] = relationship("Pool", back_populates="lab_prep", lazy="select")
    files: Mapped[list["File"]] = relationship("File", lazy="select", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship("Comment", lazy="select", cascade="all, delete-orphan", order_by="Comment.timestamp_utc.desc()")
    
    @property
    def protocol(self) -> LabProtocolEnum:
        return LabProtocol.get(self.protocol_id)
    
    @protocol.setter
    def protocol(self, value: LabProtocolEnum):
        self.protocol_id = value.id

    @property
    def status(self) -> PrepStatusEnum:
        return PrepStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: PrepStatusEnum):
        self.status_id = value.id

    @property
    def assay_type(self) -> AssayTypeEnum:
        return AssayType.get(self.assay_type_id)
    
    @assay_type.setter
    def assay_type(self, value: AssayTypeEnum):
        self.assay_type_id = value.id

    @property
    def identifier(self) -> str:
        return f"{self.protocol.identifier}{self.prep_number + LAB_PROTOCOL_START_NUMBER:04d}"
    
    @property
    def display_name(self) -> str:
        if self.name == self.identifier:
            return self.name
        
        return f"{self.name} [{self.identifier}]"
    
    def search_value(self) -> int:
        return self.id
    
    def search_name(self) -> str:
        return self.name
    
    def search_description(self) -> str:
        return self.identifier