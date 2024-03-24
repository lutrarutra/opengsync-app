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
    seq_request_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("seqrequest.id"), primary_key=True)

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
    seq_request_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("seqrequest.id"), primary_key=True)
    comment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("comment.id"), primary_key=True)

    def __str__(self) -> str:
        return f"SeqRequestCommentLink(seq_request_id: {self.seq_request_id}, comment_id: {self.comment_id})"


class LibraryFeatureLink(Base):
    __tablename__ = "library_feature_link"
    library_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("library.id"), primary_key=True)
    feature_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("feature.id"), primary_key=True)

    def __str__(self) -> str:
        return f"LibraryFeatureLink(library_id: {self.library_id}, feature_id: {self.feature_id})"