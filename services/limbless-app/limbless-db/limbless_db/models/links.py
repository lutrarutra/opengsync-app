from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from .Base import Base

from limbless_db.categories import DeliveryStatus, DeliveryStatusEnum, AffiliationType, AffiliationTypeEnum, MUXType, MUXTypeEnum

if TYPE_CHECKING:
    from .Sample import Sample
    from .Library import Library
    from .SeqRequest import SeqRequest
    from .Plate import Plate
    from .Group import Group
    from .User import User
    from .Pool import Pool
    from .Lane import Lane
    from . import PoolDilution


class UserAffiliation(Base):
    __tablename__ = "user_affiliation"

    user_id: Mapped[int] = mapped_column(sa.ForeignKey("lims_user.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(sa.ForeignKey("group.id"), primary_key=True)
    
    user: Mapped["User"] = relationship("User", back_populates="affiliations", lazy="select")
    group: Mapped["Group"] = relationship("Group", back_populates="user_links", lazy="select")

    affiliation_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    @property
    def affiliation_type(self) -> AffiliationTypeEnum:
        return AffiliationType.get(self.affiliation_type_id)
    
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

    mux: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=None)
    mux_type_id: Mapped[Optional[int]] = mapped_column(sa.SmallInteger, nullable=True, default=None)

    sample_id: Mapped[int] = mapped_column(sa.ForeignKey("sample.id"), primary_key=True)
    library_id: Mapped[int] = mapped_column(sa.ForeignKey("library.id"), primary_key=True)

    sample: Mapped["Sample"] = relationship(
        "Sample", back_populates="library_links", lazy="joined",
        cascade="save-update, merge"
    )
    library: Mapped["Library"] = relationship(
        "Library", back_populates="sample_links", lazy="joined",
        cascade="save-update, merge"
    )

    @property
    def mux_type(self) -> MUXTypeEnum | None:
        if self.mux_type_id is None:
            return None
        return MUXType.get(self.mux_type_id)
    
    @mux_type.setter
    def mux_type(self, value: MUXTypeEnum | None):
        if value is None:
            self.mux_type_id = None
        else:
            self.mux_type_id = value.id

    def __str__(self) -> str:
        return f"SampleLibraryLink(sample_id: {self.sample_id}, library_id: {self.library_id}, is_multiplexed: {self.mux_type_id is not None})"
    

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
        return f"LanePoolLink(experiment_id: {self.experiment_id}, lane_id: {self.lane_id}, pool_id: {self.pool_id})"


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

    def __str__(self) -> str:
        return f"SeqRequestDeliveryEmail(email: {self.email})"