from datetime import datetime
from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import localize
from .Base import Base
from ..categories import SeqRequestStatus, SeqRequestStatusEnum, ReadType, ReadTypeEnum, DataDeliveryMode, DataDeliveryModeEnum
from .Links import SeqRequestFileLink, SeqRequestCommentLink, SeqRequestDeliveryEmailLink

if TYPE_CHECKING:
    from .User import User
    from .Contact import Contact
    from .Library import Library
    from .Pool import Pool
    from .File import File
    from .Comment import Comment


class SeqRequest(Base):
    __tablename__ = "seqrequest"
    id: Mapped[int] = mapped_column(sa.Integer, default=None, primary_key=True)

    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(sa.String(1024), nullable=True)
    read_length: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    special_requirements: Mapped[Optional[str]] = mapped_column(sa.String(1024), nullable=True)
    billing_code: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    
    data_delivery_mode_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    read_type_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=SeqRequestStatus.DRAFT.id)
    
    timestamp_submitted_utc: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(), nullable=True, default=None)
    timestamp_finished_utc: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(), nullable=True, default=None)

    num_lanes: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    num_libraries: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    organization_contact_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("contact.id"), nullable=False)
    organization_contact: Mapped["Contact"] = relationship("Contact", lazy="select", foreign_keys=[organization_contact_id], cascade="save-update, merge, delete")

    requestor_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), nullable=False)
    requestor: Mapped["User"] = relationship("User", back_populates="requests", lazy="joined", foreign_keys=[requestor_id])

    bioinformatician_contact_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("contact.id"), nullable=True)
    bioinformatician_contact: Mapped[Optional["Contact"]] = relationship("Contact", lazy="select", foreign_keys=[bioinformatician_contact_id], cascade="save-update, merge, delete")
    
    contact_person_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("contact.id"), nullable=False)
    contact_person: Mapped["Contact"] = relationship("Contact", lazy="select", foreign_keys=[contact_person_id], cascade="save-update, merge, delete")

    billing_contact_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("contact.id"), nullable=False)
    billing_contact: Mapped["Contact"] = relationship("Contact", lazy="select", foreign_keys=[billing_contact_id], cascade="save-update, merge, delete")

    libraries: Mapped[list["Library"]] = relationship("Library", back_populates="seq_request", lazy="select")
    pools: Mapped[list["Pool"]] = relationship("Pool", back_populates="seq_request", lazy="select",)
    files: Mapped[list["File"]] = relationship(secondary=SeqRequestFileLink.__tablename__, lazy="select")
    comments: Mapped[list["Comment"]] = relationship("Comment", secondary=SeqRequestCommentLink.__tablename__, lazy="select", cascade="save-update,delete")
    delivery_email_links: Mapped[list[SeqRequestDeliveryEmailLink]] = relationship("SeqRequestDeliveryEmailLink", lazy="select", cascade="save-update,delete", back_populates="seq_request")

    seq_auth_form_file_id: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True, default=None)
    
    sortable_fields: ClassVar[list[str]] = ["id", "name", "status_id", "requestor_id", "timestamp_submitted_utc", "timestamp_finished_utc", "num_libraries"]

    @property
    def status(self) -> SeqRequestStatusEnum:
        return SeqRequestStatus.get(self.status_id)
    
    @property
    def data_delivery_mode(self) -> DataDeliveryModeEnum:
        return DataDeliveryMode.get(self.data_delivery_mode_id)
    
    @property
    def read_type(self) -> ReadTypeEnum:
        return ReadType.get(self.read_type_id)
    
    @property
    def timestamp_submitted(self) -> Optional[datetime]:
        if self.timestamp_submitted_utc is None:
            return None
        return localize(self.timestamp_submitted_utc)
    
    @property
    def timestamp_finished(self) -> Optional[datetime]:
        if self.timestamp_finished_utc is None:
            return None
        return localize(self.timestamp_finished_utc)
    
    def is_indexed(self) -> bool:
        for library in self.libraries:
            if not library.is_indexed():
                return False
            
        return True
    
    def is_editable(self) -> bool:
        return self.status == SeqRequestStatus.DRAFT
    
    def is_authorized(self) -> bool:
        return self.seq_auth_form_file_id is not None
    
    def is_submittable(self) -> bool:
        return self.status == SeqRequestStatus.DRAFT and self.num_libraries > 0 and self.is_authorized()
    
    def timestamp_submitted_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        if (ts := self.timestamp_submitted) is None:
            return ""
        return ts.strftime(fmt)
    
    def timestamp_finished_str(self, fmt: str = "%Y-%m-%d %H:%M") -> str:
        if (ts := self.timestamp_finished) is None:
            return ""
        return ts.strftime(fmt)
    
    def __str__(self):
        return f"SeqRequest(id: {self.id}, name:{self.name})"
    
    def __repr__(self) -> str:
        return str(self)