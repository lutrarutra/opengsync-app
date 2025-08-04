from typing import Optional, TYPE_CHECKING, ClassVar, Any
from datetime import datetime
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict

from ..categories import SampleStatus, SampleStatusEnum, AttributeType, AttributeTypeEnum
from .Base import Base

if TYPE_CHECKING:
    from . import links
    from .Project import Project
    from .User import User
    from .SeqRequest import SeqRequest
    from .File import File
    from .Library import Library


@dataclass
class SampleAttribute:
    name: str
    type_id: int
    value: Any

    MAX_NAME_LENGTH: ClassVar[int] = 64

    @property
    def type(self) -> AttributeTypeEnum:
        return AttributeType.get(self.type_id)
    
    @staticmethod
    def from_dict(d: dict[str, dict[str, Any]]) -> list["SampleAttribute"]:
        attributes = []
        for name, attr in d.items():
            type_id = attr["type_id"]
            value = attr["value"]
            attributes.append(SampleAttribute(name=name, type_id=type_id, value=value))
        return attributes
        

class Sample(Base):
    __tablename__ = "sample"
    
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    status_id: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)
    num_libraries: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    qubit_concentration: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    avg_fragment_size: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True, default=None)
    timestamp_stored_utc: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(), nullable=True, default=None)

    project_id: Mapped[int] = mapped_column(sa.ForeignKey("project.id"), nullable=False)
    project: Mapped["Project"] = relationship("Project", back_populates="samples", lazy="select")

    ba_report_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("file.id"), nullable=True, default=None)
    ba_report: Mapped[Optional["File"]] = relationship("File", lazy="select")
    
    plate_links: Mapped[list["links.SamplePlateLink"]] = relationship("SamplePlateLink", back_populates="sample", lazy="select")

    seq_requests: Mapped[list["SeqRequest"]] = relationship(
        "SeqRequest", back_populates="samples", lazy="select",
        secondary="join(SeqRequest, Library, SeqRequest.id == Library.seq_request_id).join(SampleLibraryLink, Library.id == SampleLibraryLink.library_id)",
        primaryjoin="SampleLibraryLink.sample_id == Sample.id",
        viewonly=True
    )

    owner_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), nullable=False)
    owner: Mapped["User"] = relationship("User", back_populates="samples", lazy="joined")

    library_links: Mapped[list["links.SampleLibraryLink"]] = relationship(
        "SampleLibraryLink", back_populates="sample", lazy="select",
        cascade="save-update, merge, delete, delete-orphan"
    )

    _attributes: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSONB), nullable=True, default=None, name="attributes")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "project_id", "owner_id", "num_libraries", "status_id"]

    @property
    def status(self) -> SampleStatusEnum | None:
        if self.status_id is None:
            return None
        return SampleStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: SampleStatusEnum | None):
        if value is None:
            self.status_id = None
        else:
            self.status_id = value.id
    
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
    
    def search_description(self) -> str:
        return self.project.title
    
    def is_editable(self) -> bool:
        if self.status is None:
            return False
        return self.status == SampleStatus.DRAFT

    @property
    def attributes(self) -> list[SampleAttribute]:
        if self._attributes is None:
            return []
        return SampleAttribute.from_dict(self._attributes)
    
    def set_attribute(self, key: str, value: Any, type: AttributeTypeEnum):
        if self._attributes is None:
            self._attributes = {}
        self._attributes[key] = {"type_id": type.id, "value": value}

    def update_attribute(self, key: str, value: Any):
        if self._attributes is None or key not in self._attributes:
            raise KeyError(f"Attribute '{key}' does not exist.")
        self._attributes[key]["value"] = value

    def get_attribute(self, key: str) -> SampleAttribute | None:
        if self._attributes is None or (attr := self._attributes.get(key)) is None:
            return None
        return SampleAttribute(name=key, type_id=attr["type_id"], value=attr["value"])
    
    def delete_sample_attribute(self, key: str):
        if self._attributes is None or key not in self._attributes:
            raise KeyError(f"Attribute '{key}' does not exist.")
        del self._attributes[key]