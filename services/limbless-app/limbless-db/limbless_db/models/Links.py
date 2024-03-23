from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .Base import Base
from ..categories import DeliveryStatus, DeliveryStatusEnum

if TYPE_CHECKING:
    from .Sample import Sample
    from .Library import Library
    from .CMO import CMO


class SampleLibraryLink(Base):
    __tablename__ = "sample_library_link"
    sample_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("sample.id"), primary_key=True)
    library_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("library.id"), primary_key=True)
    cmo_id: Mapped[Optional[int]] = mapped_column(sa.Integer, sa.ForeignKey("cmo.id"), nullable=True, default=None)

    sample: Mapped["Sample"] = relationship("Sample", back_populates="library_links")
    library: Mapped["Library"] = relationship("Library", back_populates="sample_links")
    cmo: Mapped[Optional["CMO"]] = relationship("CMO")


class SeqRequestDeliveryLink(Base):
    __tablename__ = "seqrequest_delivery_link"
    seq_request_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("seqrequest.id"), nullable=False, primary_key=True)
    email: Mapped[str] = mapped_column(sa.String(128), primary_key=True, nullable=False, index=True)
    status_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=DeliveryStatus.PENDING.id)

    @property
    def status(self) -> DeliveryStatusEnum:
        return DeliveryStatus.get(self.status_id)

    def __str__(self) -> str:
        return f"SeqRequestDeliveryLink(email: {self.email})"

# SampleLibraryLink = sa.Table(
#     "sample_library_link",
#     Base.metadata,
#     sa.Column("sample_id", sa.ForeignKey("sample.id"), primary_key=True),
#     sa.Column("library_id", sa.ForeignKey("library.id"), primary_key=True),
#     sa.Column("cmo_id", sa.ForeignKey("cmo.id"), nullable=True, default=None),
# )

# class SampleLibraryLink(Base):
#     sample_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("sample.id", primary_key=True
#     )
#     library_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("library.id", primary_key=True
#     )
#     cmo_id: Mapped[Optional[int]] = mapped_column(
#         sa.ForeignKey("cmo.id", primary_key=False,
#         nullable=True, default=None
#     )

#     sample: "Sample" = relationship(back_populates="library_links")
#     library: "Library" = relationship(back_populates="sample_links")
#     cmo: Optional["CMO"] = relationship()

#     def __str__(self) -> str:
#         return f"SampleLibraryLink(sample_id: {self.sample_id}, library_id: {self.library_id}, cmo_id: {self.cmo_id})"
    

LanePoolLink = sa.Table(
    "lane_pool_link",
    Base.metadata,
    sa.Column("lane_id", sa.ForeignKey("lane.id"), primary_key=True),
    sa.Column("pool_id", sa.ForeignKey("pool.id"), primary_key=True),
)

ExperimentFileLink = sa.Table(
    "experiment_file_link",
    Base.metadata,
    sa.Column("file_id", sa.ForeignKey("file.id"), primary_key=True),
    sa.Column("experiment_id", sa.ForeignKey("experiment.id"), primary_key=True),
)

SeqRequestFileLink = sa.Table(
    "seq_request_file_link",
    Base.metadata,
    sa.Column("file_id", sa.ForeignKey("file.id"), primary_key=True),
    sa.Column("seq_request_id", sa.ForeignKey("seqrequest.id"), primary_key=True),
)

ExperimentCommentLink = sa.Table(
    "experiment_comment_link",
    Base.metadata,
    sa.Column("experiment_id", sa.ForeignKey("experiment.id"), primary_key=True),
    sa.Column("comment_id", sa.ForeignKey("comment.id"), primary_key=True),
)

SeqRequestCommentLink = sa.Table(
    "seq_request_comment_link",
    Base.metadata,
    sa.Column("seq_request_id", sa.ForeignKey("seqrequest.id"), primary_key=True),
    sa.Column("comment_id", sa.ForeignKey("comment.id"), primary_key=True),
)

LibraryFeatureLink = sa.Table(
    "library_feature_link",
    Base.metadata,
    sa.Column("library_id", sa.ForeignKey("library.id"), primary_key=True),
    sa.Column("feature_id", sa.ForeignKey("feature.id"), primary_key=True),
)

# class LanePoolLink(Base):
#     lane_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("lane.id", primary_key=True
#     )
#     pool_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("pool.id", primary_key=True
#     )
    
#     def __str__(self) -> str:
#         return f"LanePoolLink(lane_id: {self.lane_id}, pool_id: {self.pool_id})"


# class ExperimentFileLink(Base):
#     file_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("file.id", primary_key=True
#     )
#     experiment_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("experiment.id", primary_key=True
#     )
    

# class SeqRequestFileLink(Base):
#     file_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("file.id", primary_key=True
#     )
#     seq_request_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("seqrequest.id", primary_key=True
#     )


# class ExperimentCommentLink(Base):
#     experiment_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("experiment.id", primary_key=True
#     )
#     comment_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("comment.id", primary_key=True
#     )


# class SeqRequestCommentLink(Base):
#     seq_request_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("seqrequest.id", primary_key=True
#     )
#     comment_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("comment.id", primary_key=True
#     )


# class LibraryFeatureLink(Base):
#     library_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("library.id", primary_key=True
#     )
#     feature_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("feature.id", primary_key=True
#     )


# class SeqRequestShareEmailLink(Base):
#     seq_request_id: Mapped[int] = mapped_column(
#         sa.ForeignKey("seqrequest.id", primary_key=True
#     )
#     email: Mapped[str] = mapped_column(primary_key=True, max_length=128)
    
#     status_id: Mapped[int] = mapped_column(nullable=False, default=0)

#     @property
#     def status(self) -> DeliveryStatusEnum:
#         return DeliveryStatus.get(self.status_id)