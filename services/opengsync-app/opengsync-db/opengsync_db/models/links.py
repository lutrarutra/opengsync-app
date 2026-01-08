from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict

from .Base import Base

from opengsync_db.categories import AffiliationType, AffiliationTypeEnum, DeliveryStatus, DeliveryStatusEnum

if TYPE_CHECKING:
    from .Sample import Sample
    from .Library import Library
    from .Plate import Plate
    from .Group import Group
    from .User import User
    from .Pool import Pool
    from .Lane import Lane
    from . import PoolDilution
    from .SeqRequest import SeqRequest
    from .PoolDesign import PoolDesign
    from .FlowCellDesign import FlowCellDesign

class ProjectAssigneeLink(Base):
    __tablename__ = "project_assignee_link"

    project_id: Mapped[int] = mapped_column(sa.ForeignKey("project.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), primary_key=True)

class SeqRequestAssigneeLink(Base):
    __tablename__ = "seq_request_assignee_link"
    seq_request_id: Mapped[int] = mapped_column(sa.ForeignKey("seq_request.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), primary_key=True)
    

class ProtocolKitLink(Base):
    __tablename__ = "protocol_kit_link"

    protocol_id: Mapped[int] = mapped_column(sa.ForeignKey("protocol.id"), primary_key=True)
    kit_id: Mapped[int] = mapped_column(sa.ForeignKey("kit.id"), primary_key=True)
    combination_num: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, primary_key=True)


class UserAffiliation(Base):
    __tablename__ = "user_affiliation"

    user_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(sa.ForeignKey("group.id"), primary_key=True)
    
    user: Mapped["User"] = relationship("User", back_populates="affiliations", lazy="select")
    group: Mapped["Group"] = relationship("Group", back_populates="user_links", lazy="select")

    affiliation_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    sortable_fields: ClassVar[list[str]] = ["affiliation_type_id"]

    @property
    def affiliation_type(self) -> AffiliationTypeEnum:
        return AffiliationType.get(self.affiliation_type_id)
    
    @affiliation_type.setter
    def affiliation_type(self, value: AffiliationTypeEnum) -> None:
        self.affiliation_type_id = value.id
    
    def __str__(self) -> str:
        return f"UserAffiliation(user_id: {self.user_id}, group_id: {self.group_id}, affiliation_type: {self.affiliation_type})"
    

class SamplePlateLink(Base):
    __tablename__ = "sample_plate_link"
    plate_id: Mapped[int] = mapped_column(sa.ForeignKey("plate.id"), primary_key=True)
    well_idx: Mapped[int] = mapped_column(sa.Integer, nullable=False, primary_key=True)
    
    sample_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("sample.id"), nullable=True)
    library_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("library.id"), nullable=True)

    plate: Mapped["Plate"] = relationship("Plate", back_populates="sample_links", lazy="joined")
    sample: Mapped[Optional["Sample"]] = relationship("Sample", back_populates="plate_links", lazy="joined")
    library: Mapped[Optional["Library"]] = relationship("Library", back_populates="plate_links", lazy="joined")


class SampleLibraryLink(Base):
    MAX_MUX_FIELD_LENGTH: ClassVar[int] = 64
    __tablename__ = "sample_library_link"
    __mapper_args__ = {"confirm_deleted_rows": False}

    mux: Mapped[Optional[dict]] = mapped_column(MutableDict.as_mutable(JSONB), nullable=True, default=None)

    sample_id: Mapped[int] = mapped_column(sa.ForeignKey("sample.id", ondelete="CASCADE"), primary_key=True)
    library_id: Mapped[int] = mapped_column(sa.ForeignKey("library.id", ondelete="CASCADE"), primary_key=True)

    sample: Mapped["Sample"] = relationship("Sample", back_populates="library_links", lazy="joined")
    library: Mapped["Library"] = relationship("Library", back_populates="sample_links", lazy="joined")
    
    def __str__(self) -> str:
        return f"SampleLibraryLink(sample_id: {self.sample_id}, library_id: {self.library_id})"
    

class LanePoolLink(Base):
    __tablename__ = "lane_pool_link"
    lane_id: Mapped[int] = mapped_column(sa.ForeignKey("lane.id"), primary_key=True)
    lane: Mapped["Lane"] = relationship("Lane", lazy="select", back_populates="pool_links")
    
    pool_id: Mapped[int] = mapped_column(sa.ForeignKey("pool.id"), primary_key=True)
    pool: Mapped["Pool"] = relationship("Pool", lazy="select", back_populates="lane_links")
    
    experiment_id: Mapped[int] = mapped_column(sa.ForeignKey("experiment.id"), nullable=False)

    dilution_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("pool_dilution.id"), nullable=True, default=None)
    dilution: Mapped[Optional["PoolDilution"]] = relationship("PoolDilution", lazy="select")

    num_m_reads: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True, default=None)
    lane_num: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    def __str__(self) -> str:
        return f"LanePoolLink(e: {self.experiment_id}, lane: {self.lane_num}, pool: {self.pool_id}, num_m_reads: {self.num_m_reads})"
    
    def __repr__(self) -> str:
        return self.__str__()


class LibraryFeatureLink(Base):
    __tablename__ = "library_feature_link"

    library_id: Mapped[int] = mapped_column(sa.ForeignKey("library.id"), primary_key=True)
    feature_id: Mapped[int] = mapped_column(sa.ForeignKey("feature.id"), primary_key=True)

    def __str__(self) -> str:
        return f"LibraryFeatureLink(library_id: {self.library_id}, feature_id: {self.feature_id})"


class SeqRequestDeliveryEmailLink(Base):
    __tablename__ = "seq_request_delivery_email_link"
    seq_request_id: Mapped[int] = mapped_column(sa.ForeignKey("seq_request.id"), primary_key=True, nullable=False)
    email: Mapped[str] = mapped_column(sa.String(128), primary_key=True, nullable=False, index=True)
    
    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=DeliveryStatus.PENDING.id)
    seq_request: Mapped["SeqRequest"] = relationship("SeqRequest", back_populates="delivery_email_links")

    @property
    def status(self) -> DeliveryStatusEnum:
        return DeliveryStatus.get(self.status_id)
    
    @status.setter
    def status(self, value: DeliveryStatusEnum) -> None:
        self.status_id = value.id

    def __str__(self) -> str:
        return f"SeqRequestDeliveryEmail(email: {self.email}, seq_request: {self.seq_request_id}, status: {self.status.display_name})"
    
    def __repr__(self) -> str:
        return self.__str__()