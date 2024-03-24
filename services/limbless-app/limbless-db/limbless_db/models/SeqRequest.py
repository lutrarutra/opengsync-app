from datetime import datetime
from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

from ..categories import SeqRequestStatus, SeqRequestStatusEnum, ReadType, ReadTypeEnum, DataDeliveryMode, DataDeliveryModeEnum
from .Links import SeqRequestFileLink, SeqRequestCommentLink

if TYPE_CHECKING:
    from .User import User
    from .Contact import Contact
    from .Library import Library
    from .Pool import Pool
    from .File import File
    from .Comment import Comment
    from .SeqRequestDeliveryContact import SeqRequestDeliveryContact


class SeqRequest(Base):
    __tablename__ = "seqrequest"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)

    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(sa.String(1024), nullable=True)
    status_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=SeqRequestStatus.DRAFT.id)
    submitted_time: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    sequencing_type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    read_length: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)

    num_lanes: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    num_libraries: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    num_cycles_read_1: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    num_cycles_index_1: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    num_cycles_index_2: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    num_cycles_read_2: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    
    special_requirements: Mapped[Optional[str]] = mapped_column(sa.String(1024), nullable=True)

    data_delivery_mode_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    organization_name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    organization_address: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    organization_department: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    billing_code: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)

    requestor_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    requestor: Mapped["User"] = relationship("User", back_populates="requests", lazy="select")

    bioinformatician_contact_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("contact.id"), nullable=True)
    bioinformatician_contact: Mapped[Optional["Contact"]] = relationship("Contact", lazy="joined", foreign_keys="[SeqRequest.bioinformatician_contact_id]")

    libraries: Mapped[list["Library"]] = relationship("Library", back_populates="seq_request", lazy="select", cascade="delete")
    
    contact_person_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("contact.id"), nullable=False)
    contact_person: Mapped["Contact"] = relationship(lazy="joined", foreign_keys="[SeqRequest.contact_person_id]")

    billing_contact_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("contact.id"), nullable=False)
    billing_contact: Mapped["Contact"] = relationship("Contact", lazy="joined", foreign_keys="[SeqRequest.billing_contact_id]")

    sortable_fields: ClassVar[list[str]] = ["id", "name", "status", "requestor_id", "submitted_time", "num_libraries"]

    pools: Mapped[list["Pool"]] = relationship("Pool", back_populates="seq_request", lazy="select",)
    files: Mapped[list["File"]] = relationship(secondary=SeqRequestFileLink.__tablename__, lazy="select", cascade="delete")
    comments: Mapped[list["Comment"]] = relationship("Comment", secondary=SeqRequestCommentLink.__tablename__, lazy="select", cascade="delete")
    receiver_contacts: Mapped[list["SeqRequestDeliveryContact"]] = relationship("SeqRequestDeliveryContact", lazy="select", cascade="save-update,delete", back_populates="seq_request")

    seq_auth_form_file_id: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True, default=None)

    @property
    def status(self) -> SeqRequestStatusEnum:
        return SeqRequestStatus.get(self.status_id)
    
    @property
    def sequencing_type(self) -> ReadTypeEnum:
        return ReadType.get(self.sequencing_type_id)
    
    @property
    def data_delivery_mode(self) -> DataDeliveryModeEnum:
        return DataDeliveryMode.get(self.data_delivery_mode_id)
    
    def is_indexed(self) -> bool:
        for library in self.libraries:
            if not library.is_indexed():
                return False
            
        return True
    
    def is_authorized(self) -> bool:
        return self.seq_auth_form_file_id is not None
    
    def is_submittable(self) -> bool:
        return self.status == SeqRequestStatus.DRAFT and self.num_libraries > 0 and self.is_authorized()
    
    def submitted_time_to_str(self) -> str:
        if self.submitted_time is None:
            return ""
        return self.submitted_time.strftime('%Y-%m-%d %H:%M')

    def to_dict(self):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.name,
            "submitted_time": self.submitted_time_to_str(),
            "requestor": self.requestor.name,
            "person_contact": f"{self.contact_person.name} ({self.contact_person.email})",
            "billing_contact": f"{self.billing_contact.name} ({self.billing_contact.email})",
            "bioinformatician_contact": f"{self.bioinformatician_contact.name} ({self.bioinformatician_contact.email})" if self.bioinformatician_contact else None,
            "num_libraries": self.num_libraries,
        }
        return data
    
    def __str__(self):
        return f"SeqRequest(id: {self.id}, name:{self.name})"
    
    def __repr__(self) -> str:
        return str(self)