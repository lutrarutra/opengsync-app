from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base

from limbless_db.categories import DeliveryStatus, DeliveryStatusEnum, AffiliationType, AffiliationTypeEnum, AccessType, AccessTypeEnum

if TYPE_CHECKING:
    from .Sample import Sample
    from .Library import Library
    from .SeqRequest import SeqRequest
    from .Plate import Plate
    from .Group import Group
    from .User import User


class SeqRequestGroupLinks(Base):
    __tablename__ = "seq_request_group_link"

    seq_request_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("seq_request.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("group.id"), primary_key=True)

    seq_request: Mapped["SeqRequest"] = relationship("SeqRequest", lazy="select")
    group: Mapped["Group"] = relationship("Group", lazy="select")

    access_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    @property
    def access_type(self) -> AccessTypeEnum:
        return AccessType.get(self.access_type_id)


class UserAffiliation(Base):
    __tablename__ = "user_affiliation"

    user_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lims_user.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("group.id"), primary_key=True)
    
    user: Mapped["User"] = relationship("User", back_populates="affiliations", lazy="select")
    group: Mapped["Group"] = relationship("Group", back_populates="user_links", lazy="select")

    affiliation_type_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)

    @property
    def affiliation_type(self) -> AffiliationTypeEnum:
        return AffiliationType.get(self.affiliation_type_id)
    
    def __str__(self) -> str:
        return f"UserAffiliation(user_id: {self.user_id}, group_id: {self.group_id}, affiliation_type: {self.affiliation_type})"
    

class LibraryLabPrepLink(Base):
    __tablename__ = "library_lab_prep_link"
    library_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("library.id"), primary_key=True)
    lab_prep_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lab_prep.id"), primary_key=True)

    def __str__(self) -> str:
        return f"LibraryLabPrepLink(library_id: {self.library_id}, lab_prep_id: {self.lab_prep_id})"


class SamplePlateLink(Base):
    __tablename__ = "sample_plate_link"
    plate_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("plate.id"), primary_key=True)
    well_idx: Mapped[int] = mapped_column(sa.Integer, nullable=False, primary_key=True)
    
    sample_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("sample.id"), nullable=True)
    library_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("library.id"), nullable=True)

    plate: Mapped["Plate"] = relationship("Plate", back_populates="sample_links", lazy="joined")
    sample: Mapped[Optional["Sample"]] = relationship("Sample", back_populates="plate_links", lazy="joined")
    library: Mapped[Optional["Library"]] = relationship("Library", back_populates="plate_links", lazy="joined")


class ExperimentPoolLink(Base):
    __tablename__ = "experiment_pool_link"
    experiment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("experiment.id"), primary_key=True)
    pool_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("pool.id"), primary_key=True)


class SampleLibraryLink(Base):
    __tablename__ = "sample_library_link"
    __mapper_args__ = {"confirm_deleted_rows": False}

    cmo_sequence: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True, default=None)
    cmo_pattern: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True, default=None)
    cmo_read: Mapped[Optional[str]] = mapped_column(sa.String(8), nullable=True, default=None)
    flex_barcode: Mapped[Optional[str]] = mapped_column(sa.String(8), nullable=True, default=None)

    sample_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("sample.id"), primary_key=True)
    library_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("library.id"), primary_key=True)

    sample: Mapped["Sample"] = relationship(
        "Sample", back_populates="library_links", lazy="joined",
        cascade="save-update, merge"
    )
    library: Mapped["Library"] = relationship(
        "Library", back_populates="sample_links", lazy="joined",
        cascade="save-update, merge"
    )

    def __str__(self) -> str:
        return f"SampleLibraryLink(sample_id: {self.sample_id}, library_id: {self.library_id}, is_multiplexed: {self.cmo_sequence is not None})"
    

class LanePoolLink(Base):
    __tablename__ = "lane_pool_link"
    lane_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("lane.id"), primary_key=True)
    pool_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("pool.id"), primary_key=True)

    def __str__(self) -> str:
        return f"LanePoolLink(lane_id: {self.lane_id}, pool_id: {self.pool_id})"
    

class ExperimentFileLink(Base):
    __tablename__ = "experiment_file_link"
    file_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("file.id"), primary_key=True)
    experiment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("experiment.id"), primary_key=True)

    def __str__(self) -> str:
        return f"ExperimentFileLink(file_id: {self.file_id}, experiment_id: {self.experiment_id})"


class SeqRequestFileLink(Base):
    __tablename__ = "seq_request_file_link"
    file_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("file.id"), primary_key=True)
    seq_request_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("seq_request.id"), primary_key=True)

    def __str__(self) -> str:
        return f"SeqRequestFileLink(file_id: {self.file_id}, seq_request_id: {self.seq_request_id})"


class ExperimentCommentLink(Base):
    __tablename__ = "experiment_comment_link"
    experiment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("experiment.id"), primary_key=True)
    comment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("comment.id"), primary_key=True)

    def __str__(self) -> str:
        return f"ExperimentCommentLink(experiment_id: {self.experiment_id}, comment_id: {self.comment_id})"


class SeqRequestCommentLink(Base):
    __tablename__ = "seq_request_comment_link"
    seq_request_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("seq_request.id"), primary_key=True)
    comment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("comment.id"), primary_key=True)

    def __str__(self) -> str:
        return f"SeqRequestCommentLink(seq_request_id: {self.seq_request_id}, comment_id: {self.comment_id})"


class LibraryFeatureLink(Base):
    __tablename__ = "library_feature_link"

    library_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("library.id"), primary_key=True)
    feature_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("feature.id"), primary_key=True)

    def __str__(self) -> str:
        return f"LibraryFeatureLink(library_id: {self.library_id}, feature_id: {self.feature_id})"


class SeqRequestDeliveryEmailLink(Base):
    __tablename__ = "seq_request_delivery_email_link"
    seq_request_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("seq_request.id"), primary_key=True, nullable=False)
    email: Mapped[str] = mapped_column(sa.String(128), primary_key=True, nullable=False, index=True)
    
    status_id: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, default=DeliveryStatus.PENDING.id)
    seq_request: Mapped["SeqRequest"] = relationship("SeqRequest", back_populates="delivery_email_links")

    @property
    def status(self) -> DeliveryStatusEnum:
        return DeliveryStatus.get(self.status_id)

    def __str__(self) -> str:
        return f"SeqRequestDeliveryEmail(email: {self.email})"